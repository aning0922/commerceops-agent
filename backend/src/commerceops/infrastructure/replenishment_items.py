"""T6同店当前approver单项终态事务；无采购/库存写入/重新打开。"""

import json
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from commerceops.application.commerce.inventory_analysis import _native_input_value
from commerceops.application.replenishment.contracts import ResolveInput, WebActor, WebFailure
from commerceops.application.replenishment.execution import resolution_hash
from commerceops.domain.commerce_values import canonical_bytes, facts_hash
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.replenishment_repository import (
    ReplenishmentStore,
    has_capability,
    visible_task,
)
from commerceops.infrastructure.web_sessions import DB, actor_guard, envelope, now, role_scope


class ItemStore:
    def __init__(self, store: ReplenishmentStore):
        from commerceops.infrastructure.replenishment_read import ReplenishmentReadStore

        self.config, self.settings = store.config, store.settings
        self.reads = ReplenishmentReadStore(store)

    def visible(
        self,
        db: DB,
        actor: WebActor,
        identifier: UUID,
        *,
        resolve: bool = False,
        locked: bool = False,
    ) -> dict[str, Any]:
        actor_guard(db, actor)  # principal→item；绝不回锁task/plan/approval。
        if resolve:
            if not has_capability(db, actor, "approver"):
                raise WebFailure("ACCESS_DENIED", 403)
        else:
            self.reads._business(db, actor)
        statement = (
            "SELECT * FROM business.replenishment_items "
            "WHERE id=%s AND organization_id=%s FOR UPDATE"
            if locked
            else "SELECT * FROM business.replenishment_items WHERE id=%s AND organization_id=%s"
        )
        row = db.execute(
            statement,
            (identifier, actor.organization_id),
        ).fetchone()
        if not row:
            raise WebFailure("RESOURCE_NOT_FOUND", 404)
        if role_scope(db, actor, row["shop_id"], "approver"):
            return row
        if resolve:
            raise WebFailure("RESOURCE_NOT_FOUND", 404)
        visible_task(db, actor, row["task_id"])
        return row

    def authorize(self, actor: WebActor, identifier: UUID) -> None:
        with connect(self.settings) as db:
            self.visible(db, actor, identifier, resolve=True)

    def summary(self, db: DB, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "item_id": row["id"],
            "shop_id": row["shop_id"],
            "sku_key": row["sku_key"],
            "stock_pool_key": row["stock_pool_key"],
            "quantity": int(row["quantity"]),
            "state": row["status"],
            "version": row["version"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "sync": self.reads._sync(db, row["task_id"], row["id"]),
        }

    @staticmethod
    def resolution(row: dict[str, Any]) -> dict[str, Any] | None:
        if row["resolution_id"] is None:
            return None
        return {
            "resolution_id": row["resolution_id"],
            "request_key": row["resolution_request_key"],
            "action": "complete" if row["status"] == "completed" else "close",
            "reason": row["resolution_reason"],
            "resolved_by": row["resolved_by"],
            "resolved_at": row["resolved_at"],
            "before_version": row["version"] - 1,
            "after_version": row["version"],
            "resolution_payload_hash": row["resolution_payload_hash"],
        }

    def read(self, actor: WebActor, identifier: UUID) -> dict[str, Any]:
        with connect(self.settings) as db:
            row = self.visible(db, actor, identifier)
            source_task, plan = None, None
            try:
                visible_task(db, actor, row["task_id"])
                source_task, plan = row["task_id"], row["approved_plan_id"]
            except WebFailure as error:
                if error.status != 404:
                    raise
            can_resolve = row["status"] == "open" and role_scope(
                db, actor, row["shop_id"], "approver"
            )
            return envelope(
                db,
                item=self.summary(db, row),
                resolution=self.resolution(row),
                visible_source_task_id=source_task,
                visible_plan_id=plan,
                can_resolve=can_resolve,
                disabled_reasons=[] if can_resolve else ["ITEM_NOT_RESOLVABLE"],
            )

    def resolve(
        self,
        actor: WebActor,
        identifier: UUID,
        request: ResolveInput,
        *,
        hook: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        self.authorize(actor, identifier)
        request = ResolveInput.model_validate(_native_input_value(request))
        semantic = resolution_hash(str(identifier), request)
        with connect(self.settings) as db:
            db.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (f"web:resolve:{actor.principal_id}:{request.request_key}",),
            )
            row = self.visible(db, actor, identifier, resolve=True, locked=True)
            previous = db.execute(
                """SELECT * FROM business.web_requests WHERE principal_id=%s
                AND operation='resolve' AND request_key=%s""",
                (actor.principal_id, request.request_key),
            ).fetchone()
            if previous:
                if previous["request_hash"] != semantic:
                    raise WebFailure("IDEMPOTENCY_CONFLICT")
                return {**previous["result"], "duplicate": True}
            if row["status"] != "open":
                raise WebFailure("ITEM_STATE_CONFLICT")
            if row["version"] != request.expected_version:
                raise WebFailure("ITEM_VERSION_CONFLICT")
            stamp = now(db)
            status = "completed" if request.action == "complete" else "closed"
            updated = db.execute(
                """UPDATE business.replenishment_items SET status=%s,
                version=version+1,updated_at=%s,resolution_id=%s,resolved_by=%s,resolved_at=%s,
                resolved_identity_id=%s,resolved_auth_version=%s,
                resolution_reason=%s,resolution_request_key=%s,resolution_payload_hash=%s
                WHERE id=%s AND status='open' AND version=%s RETURNING *""",
                (
                    status,
                    stamp,
                    uuid4(),
                    actor.principal_id,
                    stamp,
                    actor.identity_id,
                    actor.auth_version,
                    request.reason.strip(),
                    request.request_key,
                    semantic,
                    identifier,
                    request.expected_version,
                ),
            ).fetchone()
            if not updated:
                raise WebFailure("ITEM_STATE_CONFLICT")
            payload = {
                "schema_version": "p3-web-v1",
                "item_id": str(identifier),
                "version": updated["version"],
                "state": status,
            }
            db.execute(
                """INSERT INTO business.outbox(id,organization_id,shop_id,task_id,
                destination,aggregate_id,aggregate_version,operation,dedupe_key,request_hash,
                payload,provider_idempotency_key,status) VALUES(%s,%s,%s,%s,'bitable',%s,%s,
                'item_projection',%s,%s,%s,%s,'pending')""",
                (
                    uuid4(),
                    actor.organization_id,
                    row["shop_id"],
                    row["task_id"],
                    identifier,
                    updated["version"],
                    f"item:{identifier}:{updated['version']}",
                    facts_hash(payload),
                    Jsonb(payload),
                    uuid4(),
                ),
            )
            db.execute(
                """INSERT INTO business.audit_events(id,organization_id,task_id,actor_id,
                source,action,entity_type,entity_id,trace_id) VALUES(%s,%s,%s,%s,
                'replenishment',%s,'replenishment_item',%s,%s)""",
                (
                    uuid4(),
                    actor.organization_id,
                    row["task_id"],
                    actor.principal_id,
                    "item_" + status,
                    str(identifier),
                    uuid4(),
                ),
            )
            receipt = envelope(
                db,
                request_key=request.request_key,
                item=self.summary(db, updated),
                resolution=self.resolution(updated),
                duplicate=False,
            )
            db.execute(
                """INSERT INTO business.web_requests(organization_id,principal_id,
                operation,request_key,request_hash,task_id,result)
                VALUES(%s,%s,'resolve',%s,%s,%s,%s)""",
                (
                    actor.organization_id,
                    actor.principal_id,
                    request.request_key,
                    semantic,
                    row["task_id"],
                    Jsonb(json.loads(canonical_bytes(receipt))),
                ),
            )
            if hook:
                hook("before_t6_commit")
        if hook:
            hook("after_t6_commit")
        return receipt

    def list(
        self,
        actor: WebActor,
        *,
        state: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        if (
            state not in (None, "open", "completed", "closed")
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            raise WebFailure("INVALID_FILTER", 400)
        with connect(self.settings) as db:
            self.reads._business(db, actor)
            after, after_id = self.reads.page_after(actor, "items", [state], cursor)
            result = db.execute(
                """WITH visible AS MATERIALIZED(
                SELECT i.* FROM business.replenishment_items i
                JOIN business.business_tasks t ON t.id=i.task_id
                WHERE i.organization_id=%s AND EXISTS(
                SELECT 1 FROM business.principal_role_shop_grants g
                JOIN business.principal_shop_scopes s ON s.organization_id=g.organization_id
                 AND s.shop_id=g.shop_id AND s.principal_id=g.principal_id
                JOIN business.principals p ON p.id=g.principal_id
                 AND p.organization_id=g.organization_id
                WHERE g.principal_id=%s AND g.organization_id=i.organization_id
                 AND g.shop_id=i.shop_id
                AND g.enabled AND s.enabled AND p.enabled AND g.role=ANY(p.roles)
                AND (g.role='approver' OR (g.role='operator' AND t.requester_id=g.principal_id)))),
                filtered AS MATERIALIZED(SELECT * FROM visible WHERE %s::text IS NULL OR status=%s)
                SELECT (SELECT count(*) FROM filtered) AS total,
                (SELECT COALESCE(jsonb_agg(to_jsonb(page)),'[]'::jsonb) FROM(
                SELECT * FROM filtered WHERE %s::timestamptz IS NULL OR (created_at,id)<(%s,%s)
                ORDER BY created_at DESC,id DESC LIMIT %s) page) AS items,
                (SELECT COALESCE(jsonb_object_agg(status,n),'{}'::jsonb) FROM(
                SELECT status,count(*) AS n FROM filtered GROUP BY status)c) AS counts,
                clock_timestamp() AS as_of""",
                (
                    actor.organization_id,
                    actor.principal_id,
                    state,
                    state,
                    after,
                    after,
                    after_id,
                    limit + 1,
                ),
            ).fetchone()
            if not result:
                raise WebFailure("SERVICE_UNAVAILABLE", 503)
            page = result["items"][:limit]
            for row in page:
                for key in ("id", "task_id", "shop_id"):
                    row[key] = UUID(row[key])
            return envelope(
                db,
                items=[self.summary(db, row) for row in page],
                total=result["total"],
                counts={
                    key: result["counts"].get(key, 0) for key in ("open", "completed", "closed")
                },
                as_of=result["as_of"],
                next_cursor=self.reads.cursor(actor, "items", [state], page[-1])
                if len(result["items"]) > limit
                else None,
            )
