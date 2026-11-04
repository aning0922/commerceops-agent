"""Pure immutable preview-chain/replay policy; callers provide locked authoritative rows."""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from uuid import UUID

from commerceops.application.v4_demo.contracts import Contract, Counter, Digest, Timestamp
from commerceops.application.v41 import contracts as dto
from commerceops.application.v41.imports import (
    QualityPreview,
    decode_file,
    preview_request_digest,
)
from commerceops.domain.commerce_values import facts_hash


class PreviewScope(Contract):
    tenant_id: UUID
    shop_id: UUID
    owner_session_id: UUID
    principal_id: UUID
    reset_epoch: Counter
    auth_generation: Counter
    data_revision: Digest
    session_expires_at: Timestamp


@dataclass(frozen=True)
class PreviewRecord:
    scope: PreviewScope
    preview_key: UUID
    request_digest: str
    data: dto.ImportPreviewData
    products: tuple[dto.NormalizedProduct, ...]
    normalized_digest: str
    mapping_digest: str


def _identity(scope: PreviewScope) -> tuple[object, ...]:
    return (
        scope.tenant_id,
        scope.shop_id,
        scope.owner_session_id,
        scope.principal_id,
        scope.reset_epoch,
        scope.auth_generation,
    )


def _versions(scope: PreviewScope) -> tuple[int, int]:
    return scope.reset_epoch, scope.auth_generation


def _context(scope: PreviewScope, now: datetime, command: dto.WriteContext | None = None) -> None:
    if now.utcoffset() is None or now >= scope.session_expires_at:
        raise ValueError("SESSION_INVALID")
    if command is not None:
        if command.shop_id != scope.shop_id:
            raise ValueError("RESOURCE_NOT_FOUND")
        if command.expected_epoch != scope.reset_epoch:
            raise ValueError("EPOCH_CHANGED")
        if command.expected_generation != scope.auth_generation:
            raise ValueError("GENERATION_CHANGED")


def _normalized(products: tuple[dto.NormalizedProduct, ...]) -> str:
    return facts_hash(
        dict(
            rows=[row.model_dump(mode="json") for row in products],
            parser_version="v41-parser-1",
            import_schema_version="v41-import-1",
        )
    )


def _job_digest(
    scope: PreviewScope,
    data: dto.ImportPreviewData,
    products_digest: str,
    request_digest: str,
    mapping_digest: str,
) -> str:
    material = data.model_dump(mode="json")
    del material["job"]["job_digest"]
    return facts_hash(
        dict(
            scope=scope.model_dump(mode="json"),
            data=material,
            normalized_digest=products_digest,
            request_digest=request_digest,
            mapping_digest=mapping_digest,
        )
    )


def prepare_preview(
    scope: PreviewScope,
    command: dto.ImportPreviewInput,
    quality: QualityPreview,
    history: tuple[PreviewRecord, ...],
    now: datetime,
    job_id: UUID,
    *,
    confirmed: frozenset[UUID] = frozenset(),
) -> PreviewRecord:
    """No locking/authentication here. Persistent admission must serialize this same policy."""
    _context(scope, now, command)
    if sha256(decode_file(command.file_base64)).hexdigest() != quality.table.file_digest:
        raise ValueError("PREVIEW_FILE_MISMATCH")
    digest = preview_request_digest(command, quality.table.file_digest)
    for record in history:
        if (record.scope.owner_session_id, record.preview_key) == (
            scope.owner_session_id,
            command.request_key,
        ):
            if _identity(record.scope) != _identity(scope):
                raise ValueError("RESOURCE_NOT_FOUND")
            if record.request_digest != digest:
                raise ValueError("IDEMPOTENCY_CONFLICT")
            return record  # Original result precedes *new-effect* business-revision CAS.
    if command.expected_data_revision != scope.data_revision:
        raise ValueError("SNAPSHOT_CHANGED")
    own = [row for row in history if row.scope.tenant_id == scope.tenant_id]
    if len(own) >= 12 or any(row.data.job.import_job_id == job_id for row in history):
        raise ValueError("LIMIT_EXCEEDED")
    parents = {row.data.job.parent_job_id for row in own if row.data.job.parent_job_id is not None}
    parent = next((row for row in own if row.data.job.import_job_id == command.parent_job_id), None)
    version = 1
    if command.parent_job_id is not None:
        if parent is None or _identity(parent.scope) != _identity(scope):
            raise ValueError("RESOURCE_NOT_FOUND")
        ref = parent.data.job
        if ref.import_job_id in parents or ref.import_job_id in confirmed or ref.expires_at <= now:
            raise ValueError("STATE_CONFLICT")
        if parent.data.file_digest != quality.table.file_digest:
            raise ValueError("PREVIEW_FILE_MISMATCH")
        version = ref.version + 1
        if version > 5:
            raise ValueError("LIMIT_EXCEEDED")
    active = [
        row
        for row in own
        if _versions(row.scope) == _versions(scope)
        and row.data.job.expires_at > now
        and row.data.job.import_job_id not in parents
        and row.data.job.import_job_id not in confirmed
    ]
    if len(active) - int(parent in active) >= 3:
        raise ValueError("LIMIT_EXCEEDED")
    products_digest = _normalized(quality.products)
    mapping_digest = facts_hash(
        dict(
            mapping=command.mapping.model_dump(mode="json") if command.mapping else None,
            mapping_version=1,
        )
    )
    data = dto.ImportPreviewData(
        job=dto.ImportJobRef(
            import_job_id=job_id,
            version=version,
            parent_job_id=command.parent_job_id,
            job_digest="0" * 64,
            data_revision=scope.data_revision,
            expires_at=min(now + timedelta(minutes=10), scope.session_expires_at),
        ),
        state=quality.state,
        file_digest=quality.table.file_digest,
        mapping=command.mapping,
        headers=quality.table.headers,
        sample=quality.sample,
        row_count=len(quality.table.rows),
        issue_count=quality.issue_count,
        issues=quality.issues,
        confirmable=quality.state == "READY",
    )
    material = data.model_dump(mode="json")
    material["job"]["job_digest"] = _job_digest(
        scope, data, products_digest, digest, mapping_digest
    )
    data = dto.ImportPreviewData.model_validate_json(json.dumps(material))
    return PreviewRecord(
        scope, command.request_key, digest, data, quality.products, products_digest, mapping_digest
    )


def lookup_preview(
    scope: PreviewScope, key: UUID, history: tuple[PreviewRecord, ...], now: datetime
) -> dto.PreviewLookup:
    _context(scope, now)
    record = next(
        (
            row
            for row in history
            if row.preview_key == key and _identity(row.scope) == _identity(scope)
        ),
        None,
    )
    return dto.PreviewLookup(
        request_key=key,
        status="COMMITTED" if record else "UNKNOWN",
        job=record.data.job if record else None,
    )


def confirm_new_preview(
    scope: PreviewScope,
    command: dto.ConfirmImport,
    record: PreviewRecord,
    history: tuple[PreviewRecord, ...],
    now: datetime,
    *,
    confirmed: frozenset[UUID] = frozenset(),
    existing_skus: frozenset[str] = frozenset(),
) -> tuple[dto.NormalizedProduct, ...]:
    """New effects only. Store must first check the original committed action receipt."""
    _context(scope, now, command)
    if _identity(scope) != _identity(record.scope):
        raise ValueError("RESOURCE_NOT_FOUND")
    ref = record.data.job
    if ref.parser_version != "v41-parser-1" or ref.import_schema_version != "v41-import-1":
        raise ValueError("VERSION_CONFLICT")
    if (
        scope.data_revision != command.expected_data_revision
        or scope.data_revision != ref.data_revision
        or record.scope.data_revision != ref.data_revision
    ):
        raise ValueError("SNAPSHOT_CHANGED")
    if (
        command.expected_job_version != ref.version
        or command.expected_job_digest != ref.job_digest
        or record.normalized_digest != _normalized(record.products)
        or ref.job_digest
        != _job_digest(
            record.scope,
            record.data,
            record.normalized_digest,
            record.request_digest,
            record.mapping_digest,
        )
    ):
        raise ValueError("VERSION_CONFLICT")
    if now >= ref.expires_at:
        raise ValueError("IMPORT_EXPIRED")
    if (
        not record.data.confirmable
        or ref.import_job_id in confirmed
        or any(row.data.job.parent_job_id == ref.import_job_id for row in history)
    ):
        raise ValueError("STATE_CONFLICT")
    labels = {row.canonical_sku for row in record.products}
    if (
        len(labels) != len(record.products)
        or labels & {sku.casefold() for sku in existing_skus}
        or not 1 <= len(record.products) <= 500
    ):
        raise ValueError("IMPORT_INVALID")
    return record.products
