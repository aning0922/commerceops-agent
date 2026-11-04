"""Preview version/recovery policy only; persistent/SQL concurrency is a separate gate."""

import base64
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from commerceops.application.v41 import contracts as dto
from commerceops.application.v41.imports import parse_file, quality_preview
from commerceops.application.v41.previews import (
    PreviewRecord,
    PreviewScope,
    confirm_new_preview,
    lookup_preview,
    prepare_preview,
)

pytestmark = pytest.mark.offline
NOW = datetime(2026, 11, 4, tzinfo=UTC)
DATA = b"sku,title,price,currency\nNEW-1,Example,12.5,TWD\n"
MAPPING = dto.ColumnMapping(sku="sku", title="title", price="price", currency="currency")


def owner() -> PreviewScope:
    return PreviewScope(
        tenant_id=uuid4(),
        shop_id=uuid4(),
        owner_session_id=uuid4(),
        principal_id=uuid4(),
        reset_epoch=0,
        auth_generation=0,
        data_revision="a" * 64,
        session_expires_at=NOW + timedelta(minutes=20),
    )


def command(
    scope: PreviewScope, *, parent: UUID | None = None, mapping: dto.ColumnMapping | None = MAPPING
) -> dto.ImportPreviewInput:
    return dto.ImportPreviewInput(
        shop_id=scope.shop_id,
        request_key=uuid4(),
        expected_epoch=scope.reset_epoch,
        expected_generation=scope.auth_generation,
        expected_data_revision=scope.data_revision,
        format="csv",
        filename="products.csv",
        file_base64=base64.b64encode(DATA).decode(),
        mapping=mapping,
        parent_job_id=parent,
    )


def preview(
    scope: PreviewScope,
    cmd: dto.ImportPreviewInput,
    history: tuple[PreviewRecord, ...] = (),
    *,
    confirmed: frozenset[UUID] = frozenset(),
) -> PreviewRecord:
    quality = quality_preview(parse_file(DATA, "csv"), cmd.mapping, "TWD")
    return prepare_preview(scope, cmd, quality, history, NOW, uuid4(), confirmed=confirmed)


def confirm(scope: PreviewScope, row: PreviewRecord) -> dto.ConfirmImport:
    return dto.ConfirmImport(
        shop_id=scope.shop_id,
        request_key=uuid4(),
        expected_epoch=scope.reset_epoch,
        expected_generation=scope.auth_generation,
        expected_data_revision=scope.data_revision,
        expected_job_version=row.data.job.version,
        expected_job_digest=row.data.job.job_digest,
    )


def test_discovery_remap_supersede_and_confirm_same_file() -> None:
    scope = owner()
    discovered = preview(scope, command(scope, mapping=None))
    assert discovered.data.state == "DISCOVERED" and not discovered.data.confirmable
    cmd = command(scope, parent=discovered.data.job.import_job_id)
    mapped = preview(scope, cmd, (discovered,))
    assert mapped.data.job.version == 2 and mapped.data.state == "READY"
    assert mapped.data.job.data_revision == scope.data_revision
    assert mapped.data.job.parser_version == "v41-parser-1"
    assert mapped.data.job.import_schema_version == "v41-import-1"
    products = confirm_new_preview(scope, confirm(scope, mapped), mapped, (discovered, mapped), NOW)
    assert products[0].sku == "NEW-1" and products[0].price == "12.5"
    with pytest.raises(ValueError, match="STATE_CONFLICT"):
        confirm_new_preview(
            scope, confirm(scope, discovered), discovered, (discovered, mapped), NOW
        )
    with pytest.raises(ValueError, match="STATE_CONFLICT"):
        preview(
            scope, command(scope, parent=discovered.data.job.import_job_id), (discovered, mapped)
        )


def test_preview_replay_precedes_new_revision_cas_and_recovery_is_minimal() -> None:
    scope = owner()
    cmd = command(scope)
    row = preview(scope, cmd)
    changed = scope.model_copy(update=dict(data_revision="b" * 64))
    assert preview(changed, cmd, (row,)) is row
    lookup = lookup_preview(changed, cmd.request_key, (row,), NOW)
    assert lookup.status == "COMMITTED" and lookup.job == row.data.job
    assert "file_base64" not in lookup.model_dump_json()
    assert lookup_preview(changed, uuid4(), (row,), NOW).status == "UNKNOWN"
    modified = cmd.model_copy(update=dict(filename="different.csv"))
    with pytest.raises(ValueError, match="IDEMPOTENCY_CONFLICT"):
        preview(changed, modified, (row,))
    with pytest.raises(ValueError, match="SNAPSHOT_CHANGED"):
        preview(changed, command(scope), (row,))


def test_saved_request_and_current_revisions_must_all_match_for_new_confirm() -> None:
    scope = owner()
    row = preview(scope, command(scope))
    changed = scope.model_copy(update=dict(data_revision="b" * 64))
    # Updating just the client's expected revision cannot revive this old preview.
    with pytest.raises(ValueError, match="SNAPSHOT_CHANGED"):
        confirm_new_preview(changed, confirm(changed, row), row, (row,), NOW)
    with pytest.raises(ValueError, match="VERSION_CONFLICT"):
        confirm_new_preview(scope, confirm(scope, row), replace(row, products=()), (row,), NOW)
    with pytest.raises(ValueError, match="IMPORT_INVALID"):
        confirm_new_preview(
            scope, confirm(scope, row), row, (row,), NOW, existing_skus=frozenset({"new-1"})
        )


def test_chain_five_versions_tenant_twelve_and_three_active_heads() -> None:
    scope = owner()
    history: tuple[PreviewRecord, ...] = ()
    for _ in range(5):
        parent = history[-1].data.job.import_job_id if history else None
        history += (preview(scope, command(scope, parent=parent), history),)
    assert history[-1].data.job.version == 5
    with pytest.raises(ValueError, match="LIMIT_EXCEEDED"):
        preview(scope, command(scope, parent=history[-1].data.job.import_job_id), history)
    heads: tuple[PreviewRecord, ...] = ()
    for _ in range(3):
        heads += (preview(scope, command(scope), heads),)
    with pytest.raises(ValueError, match="LIMIT_EXCEEDED"):
        preview(scope, command(scope), heads)
    # Replacing an active parent consumes the same active-head position.
    child = preview(scope, command(scope, parent=heads[0].data.job.import_job_id), heads)
    assert child.data.job.version == 2
    all_rows: tuple[PreviewRecord, ...] = ()
    confirmed: frozenset[UUID] = frozenset()
    for _ in range(12):
        row = preview(scope, command(scope), all_rows, confirmed=confirmed)
        all_rows += (row,)
        confirmed |= {row.data.job.import_job_id}
    with pytest.raises(ValueError, match="LIMIT_EXCEEDED"):
        preview(scope, command(scope), all_rows, confirmed=confirmed)


def test_confirmed_terminal_current_identity_epoch_generation_and_expiry() -> None:
    scope = owner()
    cmd = command(scope)
    row = preview(scope, cmd)
    confirmed = frozenset({row.data.job.import_job_id})
    with pytest.raises(ValueError, match="STATE_CONFLICT"):
        preview(
            scope, command(scope, parent=row.data.job.import_job_id), (row,), confirmed=confirmed
        )
    with pytest.raises(ValueError, match="STATE_CONFLICT"):
        confirm_new_preview(scope, confirm(scope, row), row, (row,), NOW, confirmed=confirmed)
    with pytest.raises(ValueError, match="IMPORT_EXPIRED"):
        confirm_new_preview(scope, confirm(scope, row), row, (row,), NOW + timedelta(minutes=10))
    changed = scope.model_copy(update=dict(auth_generation=1))
    assert lookup_preview(changed, cmd.request_key, (row,), NOW).status == "UNKNOWN"
    with pytest.raises(ValueError, match="GENERATION_CHANGED"):
        preview(changed, cmd, (row,))
    with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
        confirm_new_preview(changed, confirm(changed, row), row, (row,), NOW)
    changed = scope.model_copy(update=dict(reset_epoch=1))
    with pytest.raises(ValueError, match="EPOCH_CHANGED"):
        preview(changed, cmd, (row,))
    with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
        confirm_new_preview(owner(), confirm(owner(), row), row, (row,), NOW)


def test_preview_ttl_cannot_extend_session_deadline_or_change_parent_file() -> None:
    scope = owner().model_copy(update=dict(session_expires_at=NOW + timedelta(minutes=2)))
    row = preview(scope, command(scope))
    assert row.data.job.expires_at == scope.session_expires_at
    quality = quality_preview(parse_file(DATA + b"NEW-2,Extra,1,TWD\n", "csv"), MAPPING, "TWD")
    cmd = command(scope, parent=row.data.job.import_job_id).model_copy(
        update=dict(file_base64=base64.b64encode(DATA + b"NEW-2,Extra,1,TWD\n").decode())
    )
    with pytest.raises(ValueError, match="PREVIEW_FILE_MISMATCH"):
        prepare_preview(scope, cmd, quality, (row,), NOW, uuid4())
