"""Tenant-locked same-source business reads and fixed atomic SQL actions, without retries."""

import hashlib
import json
import secrets
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID, uuid4

from psycopg import sql
from psycopg.types.json import Jsonb

from commerceops.application.replenishment.contracts import WebFailure
from commerceops.application.v4_demo.contracts import Contract
from commerceops.application.v4_demo.seed_contract import FixtureContent
from commerceops.application.v41 import contracts as dto
from commerceops.application.v41 import queries
from commerceops.application.v41.analytics import dashboard, snapshot_for
from commerceops.application.v41.effective import (
    EffectiveView,
    FulfillmentEffect,
    ImportedProduct,
    TagEffect,
    ViewScope,
    build_view,
    product_detail,
)
from commerceops.application.v41.imports import decode_file
from commerceops.application.v41.parse_protocol import ParseInput
from commerceops.application.v41.previews import PreviewRecord, PreviewScope, prepare_preview
from commerceops.domain.commerce_values import canonical_bytes
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.v4_demo_sessions import (
    DB,
    DemoConfig,
    DemoIdentity,
    DemoSessions,
    bounded,
)
from commerceops.infrastructure.v41_parse import run_parser
from commerceops.infrastructure.v41_security import assert_policy, binding_proof
from commerceops.infrastructure.web_sessions import now

ReadKind = Literal[
    "dashboard",
    "drilldown",
    "products",
    "product",
    "orders",
    "order",
    "product_export",
    "order_export",
    "read_context",
]


@dataclass(frozen=True)
class LockedScope:
    identity: DemoIdentity
    binding: str
    revision: str


def receipt(row: dict[str, Any]) -> dto.ActionReceipt:
    return dto.ActionReceipt(
        receipt_id=row["id"],
        operation=row["operation"],
        request_key=row["request_id"],
        payload_digest=row["payload_digest"],
        resource_id=row["resource_id"],
        resource_version=row["resource_version"],
        committed_at=row["committed_at"],
        before_revision=row["before_revision"],
        after_revision=row["after_revision"],
    )


class BusinessStore:
    def __init__(self, config: DemoConfig):
        self.config = config
        self.sessions = DemoSessions(config)

    def _guard(
        self,
        db: DB,
        token: str | None,
        shop: UUID,
        epoch: int,
        generation: int,
        *,
        csrf: str | None = None,
        writing: bool = False,
    ) -> LockedScope:
        bounded(db)
        subject = self.sessions.resolve_locked(db, token)
        assert_policy(db, self.config)
        s = subject.session
        if s["reset_epoch"] != epoch:
            raise WebFailure("EPOCH_CHANGED", 409)
        if s["auth_generation"] != generation:
            raise WebFailure("GENERATION_CHANGED", 409)
        binding = binding_proof(self.config, s["bound_web_session_id"])
        if writing:
            self.sessions.supplied_csrf(s, csrf)
            row = db.execute(
                "SELECT business.v41_write_guard(%s,%s,%s,%s,%s,%s) AS data_revision",
                (token, csrf, binding, shop, epoch, generation),
            ).fetchone()
        else:
            row = db.execute(
                "SELECT business.v41_read_guard(%s,%s,%s,%s,%s) AS data_revision",
                (token, binding, shop, epoch, generation),
            ).fetchone()
        assert_policy(db, self.config)  # The SQL guard holds the current policy row SHARE lock.
        if row is None:
            raise WebFailure("SERVICE_UNAVAILABLE", 503)
        return LockedScope(subject, binding, row["data_revision"])

    @staticmethod
    def _reply(db: DB, guard: LockedScope, shop: UUID, data: Contract) -> dict[str, Any]:
        stamp = now(db)
        if stamp >= min(guard.identity.session["expires_at"], guard.identity.tenant["expires_at"]):
            raise WebFailure("SESSION_INVALID", 401)
        return dict(server_time=stamp, context=guard.identity.context(stamp, shop), data=data)

    @staticmethod
    def _view(db: DB, guard: LockedScope, shop: UUID) -> EffectiveView:
        t, s = guard.identity.tenant, guard.identity.session
        source = db.execute(
            """SELECT f.content,m.template_key FROM business.v4_demo_fixture_versions f
            JOIN business.v4_demo_shops m ON m.tenant_id=%s AND m.shop_id=%s
            WHERE f.version=%s AND f.content_hash=%s""",
            (t["id"], shop, t["fixture_version"], t["fixture_digest"]),
        ).fetchone()
        if source is None:
            raise WebFailure("SERVICE_UNAVAILABLE", 503)
        fixture = FixtureContent.model_validate_json(json.dumps(source["content"]))
        scope = ViewScope(
            tenant_id=t["id"],
            shop_id=shop,
            reset_epoch=s["reset_epoch"],
            template_key=source["template_key"],
        )
        models: dict[str, type[Contract]] = {
            "product_tags": TagEffect,
            "order_fulfillments": FulfillmentEffect,
            "import_products": ImportedProduct,
        }
        values: dict[str, Any] = {}
        for suffix, model in models.items():
            rows = db.execute(
                sql.SQL(
                    "SELECT canonical_payload,payload_digest FROM {} "
                    "WHERE tenant_id=%s AND shop_id=%s AND reset_epoch=%s"
                ).format(sql.Identifier("business", "v41_" + suffix)),
                (t["id"], shop, s["reset_epoch"]),
            ).fetchall()
            parsed = []
            for row in rows:
                raw = row["canonical_payload"]
                if hashlib.sha256(raw.encode()).hexdigest() != row["payload_digest"]:
                    raise WebFailure("SERVICE_UNAVAILABLE", 503)
                value = model.model_validate_json(raw)
                if canonical_bytes(value.model_dump(mode="json")).decode() != raw:
                    raise WebFailure("SERVICE_UNAVAILABLE", 503)
                parsed.append(value)
            values[suffix] = tuple(parsed)
        result = build_view(
            fixture,
            t["fixture_digest"],
            scope,
            tags=values["product_tags"],
            fulfillments=values["order_fulfillments"],
            imports=values["import_products"],
        )
        if result.revision() != guard.revision:
            raise WebFailure("SERVICE_UNAVAILABLE", 503)
        return result

    def read(
        self,
        token: str | None,
        epoch: int,
        generation: int,
        query: dto.Query,
        kind: ReadKind,
        resource_id: UUID | None = None,
    ) -> dict[str, Any]:
        with connect(self.config.web.database) as db:
            guard = self._guard(db, token, query.shop_id, epoch, generation)
            view = self._view(db, guard, query.shop_id)
            stamp = now(db)
            signing = self.config.web.nonce_secret
            data: Contract
            if kind == "dashboard" and isinstance(query, dto.PeriodQuery):
                data = dashboard(view, query, stamp)
            elif kind == "drilldown" and isinstance(query, dto.DrilldownQuery):
                data = queries.drilldown(view, query, stamp, generation, signing)
            elif kind == "products" and isinstance(query, dto.ProductQuery):
                data = queries.products_page(view, query, stamp, generation, signing)
            elif kind == "orders" and isinstance(query, dto.OrderQuery):
                data = queries.orders_page(view, query, stamp, generation, signing)
            elif kind == "product_export" and isinstance(query, dto.ProductQuery):
                data = queries.export_products(view, query, stamp, generation, signing)
            elif kind == "order_export" and isinstance(query, dto.OrderQuery):
                data = queries.export_orders(view, query, stamp, generation, signing)
            elif kind == "read_context" and isinstance(query, dto.ReadContextQuery):
                data = queries.read_context(view, query, stamp)
            elif kind == "product" and resource_id is not None:
                data = product_detail(
                    view, resource_id, snapshot_for(view, dict(product_id=str(resource_id)), stamp)
                )
            elif kind == "order" and resource_id is not None:
                data = queries.order_detail(view, resource_id, stamp)
            else:
                raise WebFailure("INVALID_REQUEST", 422)
            return self._reply(db, guard, query.shop_id, data)

    def action(
        self,
        token: str | None,
        csrf: str | None,
        command: dto.WriteContext,
        operation: dto.Operation,
        target: UUID,
    ) -> dict[str, Any]:
        suffix = {
            "product_tags": f"products/{target}/tags",
            "order_fulfillment": f"orders/{target}/fulfillment",
            "import_confirm": f"imports/{target}/confirm",
        }[operation]
        canonical = canonical_bytes(
            dict(method="POST", path="/api/v4/" + suffix, body=command.model_dump(mode="json"))
        ).decode()
        with connect(self.config.web.database) as db:
            guard = self._guard(
                db,
                token,
                command.shop_id,
                command.expected_epoch,
                command.expected_generation,
                csrf=csrf,
                writing=True,
            )
            row = db.execute(
                "SELECT * FROM business.v41_apply_action(%s,%s,%s,%s,%s,%s)",
                (token, csrf, guard.binding, canonical, operation, target),
            ).fetchone()
            if row is None:
                raise WebFailure("SERVICE_UNAVAILABLE", 503)
            return self._reply(db, guard, command.shop_id, dto.ActionResult(receipt=receipt(row)))

    def action_lookup(
        self,
        token: str | None,
        epoch: int,
        generation: int,
        query: dto.Query,
        operation: dto.Operation,
        key: UUID,
    ) -> dict[str, Any]:
        with connect(self.config.web.database) as db:
            guard = self._guard(db, token, query.shop_id, epoch, generation)
            s = guard.identity.session
            row = db.execute(
                """SELECT * FROM business.v41_action_receipts WHERE tenant_id=%s AND shop_id=%s
                AND owner_session_id=%s AND principal_id=%s AND reset_epoch=%s
                AND auth_generation=%s AND operation=%s AND request_id=%s""",
                (
                    guard.identity.tenant["id"],
                    query.shop_id,
                    s["id"],
                    s["principal_id"],
                    epoch,
                    generation,
                    operation,
                    key,
                ),
            ).fetchone()
            result = dto.ActionLookup(
                operation=operation,
                request_key=key,
                status="COMMITTED" if row else "UNKNOWN",
                receipt=receipt(row) if row else None,
            )
            return self._reply(db, guard, query.shop_id, result)

    @staticmethod
    def _jobs(db: DB, guard: LockedScope, shop: UUID) -> list[dict[str, Any]]:
        s = guard.identity.session
        return db.execute(
            """SELECT * FROM business.v41_import_jobs WHERE tenant_id=%s AND shop_id=%s
            AND owner_session_id=%s AND principal_id=%s AND reset_epoch=%s AND auth_generation=%s
            ORDER BY created_at,id""",
            (
                guard.identity.tenant["id"],
                shop,
                s["id"],
                s["principal_id"],
                s["reset_epoch"],
                s["auth_generation"],
            ),
        ).fetchall()

    @staticmethod
    def _preview_record(row: dict[str, Any], subject: DemoIdentity) -> PreviewRecord:
        return PreviewRecord(
            scope=PreviewScope(
                tenant_id=row["tenant_id"],
                shop_id=row["shop_id"],
                owner_session_id=row["owner_session_id"],
                principal_id=row["principal_id"],
                reset_epoch=row["reset_epoch"],
                auth_generation=row["auth_generation"],
                data_revision=row["data_revision"],
                session_expires_at=subject.session["expires_at"],
            ),
            preview_key=row["preview_key"],
            request_digest=row["request_digest"],
            data=dto.ImportPreviewData.model_validate_json(row["canonical_preview"]),
            products=tuple(
                dto.NormalizedProduct.model_validate_json(json.dumps(p))
                for p in row["normalized_rows"]
            ),
            normalized_digest=row["normalized_digest"],
            mapping_digest=row["mapping_digest"],
        )

    @staticmethod
    def _display_job(db: DB, row: dict[str, Any]) -> dto.ImportPreviewData:
        if row["preview_data"] is None:
            raise WebFailure("SERVICE_UNAVAILABLE", 503)
        data = dto.ImportPreviewData.model_validate_json(row["canonical_preview"])
        state = data.state
        if db.execute(
            "SELECT 1 FROM business.v41_action_receipts WHERE operation='import_confirm' "
            "AND resource_id=%s",
            (row["id"],),
        ).fetchone():
            state = "COMMITTED"
        elif db.execute(
            "SELECT 1 FROM business.v41_import_jobs WHERE parent_job_id=%s", (row["id"],)
        ).fetchone():
            state = "SUPERSEDED"
        payload = data.model_dump(mode="json") | dict(state=state, confirmable=state == "READY")
        return dto.ImportPreviewData.model_validate_json(json.dumps(payload))

    def preview_lookup(
        self,
        token: str | None,
        epoch: int,
        generation: int,
        query: dto.Query,
        key: UUID,
        *,
        by_id: bool = False,
    ) -> dict[str, Any]:
        with connect(self.config.web.database) as db:
            guard = self._guard(db, token, query.shop_id, epoch, generation)
            row = next(
                (
                    r
                    for r in self._jobs(db, guard, query.shop_id)
                    if r["id" if by_id else "preview_key"] == key
                ),
                None,
            )
            if by_id:
                if row is None:
                    raise WebFailure("RESOURCE_NOT_FOUND", 404)
                data: Contract = self._display_job(db, row)
            else:
                data = dto.PreviewLookup(
                    request_key=key,
                    status="COMMITTED" if row and row["preview_data"] else "UNKNOWN",
                    job=self._display_job(db, row).job if row and row["preview_data"] else None,
                )
            return self._reply(db, guard, query.shop_id, data)

    def preview(
        self, token: str | None, csrf: str | None, command: dto.ImportPreviewInput
    ) -> dict[str, Any]:
        lease, process_ref = secrets.token_urlsafe(32), uuid4()
        with connect(self.config.web.database) as db:
            guard = self._guard(
                db,
                token,
                command.shop_id,
                command.expected_epoch,
                command.expected_generation,
                csrf=csrf,
                writing=True,
            )
            view = self._view(db, guard, command.shop_id)
            raw_digest = hashlib.sha256(decode_file(command.file_base64)).hexdigest()
            canonical = canonical_bytes(
                dict(
                    command=command.model_dump(mode="json", exclude={"file_base64"}),
                    file_digest=raw_digest,
                )
            ).decode()
            row = db.execute(
                "SELECT * FROM business.v41_reserve_preview(%s,%s,%s,%s,%s,%s)",
                (
                    token,
                    csrf,
                    guard.binding,
                    canonical,
                    hashlib.sha256(lease.encode()).hexdigest(),
                    process_ref,
                ),
            ).fetchone()
            if row is None:
                raise WebFailure("SERVICE_UNAVAILABLE", 503)
            if row["process_ref"] != process_ref:
                return self._reply(db, guard, command.shop_id, self._display_job(db, row))
            job = row["id"]
            parse_input = ParseInput(
                format=command.format,
                file_base64=command.file_base64,
                mapping=command.mapping,
                currency=view.currency,
                existing_skus=tuple(sku.label for p in view.products for sku in p.skus),
            )

        # The durable reservation COMMIT completed before Popen. No business lock during CPU parse.
        def bind(pid: int) -> None:
            with connect(self.config.web.database) as lifecycle:
                bounded(lifecycle)
                lifecycle.execute(
                    "SELECT business.v41_bind_parser(%s,%s,%s,%s)", (job, lease, process_ref, pid)
                )

        def stop(proof: dict[str, Any]) -> None:
            with connect(self.config.web.database) as lifecycle:
                bounded(lifecycle)
                lifecycle.execute(
                    "SELECT business.v41_stop_parser(%s,%s,%s,%s)",
                    (job, lease, process_ref, Jsonb(proof)),
                )

        native = run_parser(parse_input, process_ref, bind, stop)
        if native.result.file_digest != raw_digest:
            raise WebFailure("IMPORT_INVALID", 422)
        with connect(self.config.web.database) as db:
            guard = self._guard(
                db,
                token,
                command.shop_id,
                command.expected_epoch,
                command.expected_generation,
                csrf=csrf,
                writing=True,
            )
            history = tuple(
                self._preview_record(r, guard.identity)
                for r in self._jobs(db, guard, command.shop_id)
                if r["preview_data"] is not None
            )
            confirmed = frozenset(
                r["resource_id"]
                for r in db.execute(
                    "SELECT resource_id FROM business.v41_action_receipts WHERE tenant_id=%s "
                    "AND operation='import_confirm'",
                    (guard.identity.tenant["id"],),
                ).fetchall()
            )
            scope = PreviewScope(
                tenant_id=row["tenant_id"],
                shop_id=command.shop_id,
                owner_session_id=row["owner_session_id"],
                principal_id=row["principal_id"],
                reset_epoch=command.expected_epoch,
                auth_generation=command.expected_generation,
                data_revision=guard.revision,
                session_expires_at=guard.identity.session["expires_at"],
            )
            record = prepare_preview(
                scope, command, native.result, history, row["created_at"], job, confirmed=confirmed
            )
            result = db.execute(
                "SELECT * FROM business.v41_publish_preview(%s,%s,%s,%s,%s,%s,%s)",
                (
                    token,
                    csrf,
                    guard.binding,
                    job,
                    lease,
                    canonical_bytes(record.data.model_dump(mode="json")).decode(),
                    canonical_bytes([p.model_dump(mode="json") for p in record.products]).decode(),
                ),
            ).fetchone()
            if result is None:
                raise WebFailure("SERVICE_UNAVAILABLE", 503)
            return self._reply(db, guard, command.shop_id, self._display_job(db, result))
