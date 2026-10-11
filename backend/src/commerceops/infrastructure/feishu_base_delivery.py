"""唯一Worker的正式Base伴随投影；不改原outbox或内部item终态。"""

import asyncio
import json
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from commerceops.application.feishu_business.contracts import (
    BaseProjectionAdapter,
    ItemProjection,
    ProjectionRequest,
    ProjectionResult,
)
from commerceops.application.feishu_business.delivery import (
    DeliveryGate,
    disposition,
    next_operation,
)
from commerceops.application.feishu_business.sdk_window import SDKScope
from commerceops.domain.commerce_values import facts_hash
from commerceops.infrastructure.feishu_sdk_ledger import PersistentSDKLedger
from commerceops.infrastructure.worker_lock import WorkerSession, open_async


def item_snapshot(item: dict[str, Any], plan: dict[str, Any], version: int) -> ItemProjection:
    """v1即使在T6之后才领取仍还原原创建快照；v2仅取不可变终态。"""
    if version not in (1, 2) or version > item["version"]:
        raise ValueError("INVALID_ORIGINAL_ITEM_VERSION")
    matches = [i for i in plan["items"] if i["sku_key"] == item["sku_key"]]
    if len(matches) != 1 or matches[0]["quantity"] != int(item["quantity"]):
        raise ValueError("INVALID_ORIGINAL_ITEM_PLAN")
    terminal = version == 2
    window = plan["window"]
    return ItemProjection(
        item_id=item["id"],
        task_id=item["task_id"],
        sku=item["sku_key"],
        quantity=int(item["quantity"]),
        risk=matches[0]["fact"]["risk"],
        window=f"[{window['start']},{window['end']})",
        source_mode="mock",
        approval_status="approved",
        approved_by=str(item["approved_by"]),
        business_status=item["status"] if terminal else "open",
        resolution_reason=item["resolution_reason"] if terminal else None,
        resolved_by=str(item["resolved_by"]) if terminal else None,
        resolved_at=item["resolved_at"] if terminal else None,
        sync_version=version,
        updated_at=item["updated_at"] if terminal else item["created_at"],
    )


class BaseDeliveryStore:
    def __init__(
        self,
        session: WorkerSession,
        adapter: BaseProjectionAdapter,
        gate: DeliveryGate,
        ledger: PersistentSDKLedger | None = None,
    ):
        if gate.organization_id != session.organization:
            raise ValueError("INVALID_P4_DELIVERY_ORGANIZATION")
        self.session, self.adapter, self.gate = session, adapter, gate
        if gate.verification_mode == "controlled_sdk" and ledger is None:
            raise ValueError("CONTROLLED_BASE_REQUIRES_METHOD_LEDGER")
        self.ledger = ledger

    async def _enroll(self) -> None:
        # 固定原task白名单+单shop/Mock，绝不扫描/升级历史probe或controlled_stub outbox。
        async with await open_async(self.session.settings) as db, db.transaction():
            cur = await db.execute(
                """SELECT o.* FROM business.outbox o JOIN business.shops s
                ON s.id=o.shop_id AND s.organization_id=o.organization_id
                JOIN business.business_tasks t ON t.id=o.task_id
                WHERE o.organization_id=%s AND o.shop_id=%s AND o.task_id=ANY(%s)
                AND t.kind='inventory_replenishment'
                AND t.workflow_version='p3-inventory-replenishment-v1'
                AND s.adapter_kind='mock' AND s.environment IN ('test','mock')
                AND o.operation='item_projection' AND o.destination='bitable'
                AND NOT o.sender_enabled
                AND o.source_mode='mock' AND o.status='pending'
                AND NOT EXISTS(SELECT 1 FROM business.p4_base_deliveries d WHERE d.outbox_id=o.id)
                ORDER BY o.created_at,o.aggregate_version,o.id""",
                (self.gate.organization_id, self.gate.shop_id, list(self.gate.task_ids)),
            )
            for outbox in await cur.fetchall():
                cur = await db.execute(
                    "SELECT * FROM business.replenishment_items WHERE id=%s AND organization_id=%s"
                    " AND shop_id=%s AND task_id=%s FOR SHARE",
                    (
                        outbox["aggregate_id"],
                        self.gate.organization_id,
                        self.gate.shop_id,
                        outbox["task_id"],
                    ),
                )
                item = await cur.fetchone()
                if not item:
                    raise ValueError("INVALID_P4_ITEM_BINDING")
                cur = await db.execute(
                    "SELECT content FROM business.replenishment_plans WHERE id=%s AND task_id=%s",
                    (item["approved_plan_id"], item["task_id"]),
                )
                plan = await cur.fetchone()
                if not plan:
                    raise ValueError("INVALID_P4_ITEM_PLAN")
                snapshot = item_snapshot(item, plan["content"], outbox["aggregate_version"])
                original = {
                    "schema_version": "p3-web-v1",
                    "item_id": str(item["id"]),
                    "version": snapshot.sync_version,
                    "state": snapshot.business_status,
                }
                if outbox["payload"] != original or outbox["request_hash"] != facts_hash(original):
                    raise ValueError("INVALID_P4_ORIGINAL_OUTBOX")
                await db.execute(
                    """INSERT INTO business.p4_base_deliveries(outbox_id,organization_id,shop_id,
                    task_id,item_id,target_key,client_token,version,projection,projection_hash,
                    verification_mode) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(outbox_id) DO NOTHING""",
                    (
                        outbox["id"],
                        self.gate.organization_id,
                        self.gate.shop_id,
                        item["task_id"],
                        item["id"],
                        self.gate.target_key,
                        outbox["provider_idempotency_key"],
                        snapshot.sync_version,
                        Jsonb(snapshot.model_dump(mode="json")),
                        facts_hash(snapshot.model_dump(mode="json")),
                        self.gate.verification_mode,
                    ),
                )
            await self.session.check()

    async def recover_unknown(self) -> None:
        await self.session.check()
        async with await open_async(self.session.settings) as db:
            # 启动已经旧OS死亡确认。旧sending不能凭无PG回执重发，只原快照reconcile。
            await db.execute(
                """UPDATE business.p4_base_deliveries SET status='unknown',
                last_error='BASE_ACK_UNPROVEN'
                WHERE organization_id=%s AND status='sending' AND claimed_by<>%s""",
                (self.session.organization, self.session.owner),
            )

    async def dispatch_one(self) -> str:
        await self.session.check()
        if self.session.connection is None:
            raise ValueError("P4_WORKER_NOT_READY")
        async with await open_async(self.session.settings) as db:
            await db.execute(
                """INSERT INTO business.p4_sender_state(organization_id,shop_id,destination_alias,
                configured_enabled,expires_at,worker_owner,worker_backend_pid,verification_mode)
                VALUES(%s,%s,'Base',%s,%s,%s,%s,%s)
                ON CONFLICT(organization_id,shop_id,destination_alias) DO UPDATE SET
                configured_enabled=EXCLUDED.configured_enabled,expires_at=EXCLUDED.expires_at,
                worker_owner=EXCLUDED.worker_owner,worker_backend_pid=EXCLUDED.worker_backend_pid,
                verification_mode=EXCLUDED.verification_mode,checked_at=clock_timestamp()""",
                (
                    self.gate.organization_id,
                    self.gate.shop_id,
                    self.gate.enabled,
                    self.gate.expires_at,
                    self.session.owner,
                    self.session.connection.info.backend_pid,
                    self.gate.verification_mode,
                ),
            )
        if not self.gate.active():
            return "disabled"
        await self._enroll()
        await self.recover_unknown()
        request: ProjectionRequest | None = None
        attempts = 0
        async with await open_async(self.session.settings) as db, db.transaction():
            cur = await db.execute(
                """SELECT d.*,l.external_id AS anchor FROM business.p4_base_deliveries d
                LEFT JOIN business.p4_base_links l ON l.organization_id=d.organization_id
                AND l.shop_id=d.shop_id AND l.target_key=d.target_key AND l.item_id=d.item_id
                WHERE d.organization_id=%s AND d.shop_id=%s AND d.task_id=ANY(%s)
                AND d.target_key=%s AND d.verification_mode=%s
                AND d.status IN ('pending','unknown') AND d.attempts<3
                AND d.next_attempt_at<=clock_timestamp()
                ORDER BY d.created_at,d.version,d.outbox_id FOR UPDATE OF d""",
                (
                    self.gate.organization_id,
                    self.gate.shop_id,
                    list(self.gate.task_ids),
                    self.gate.target_key,
                    self.gate.verification_mode,
                ),
            )
            for row in await cur.fetchall():
                operation = next_operation(
                    status=row["status"],
                    version=row["version"],
                    anchor=row["anchor"],
                    attempts=row["attempts"],
                )
                if operation is None:
                    continue
                # 原任务operator及原审批actor均需当前有效。读取snapshot不借外写许可绕业务权。
                cur = await db.execute(
                    """SELECT business.lock_p3_permission(t.requester_id,
                    t.organization_id,t.shop_id,(t.normalized_request->>'identity_id')::uuid,
                    p.auth_version,'operator') AS creator_ok,
                    business.lock_p3_permission(a.decided_by,a.organization_id,a.shop_id,
                    a.decided_identity_id,a.decided_auth_version,'approver') AS approver_ok
                    FROM business.business_tasks t JOIN business.principals p ON p.id=t.requester_id
                    JOIN business.replenishment_items i ON i.task_id=t.id AND i.id=%s
                    JOIN business.approvals a ON a.plan_id=i.approved_plan_id WHERE t.id=%s""",
                    (row["item_id"], row["task_id"]),
                )
                permission = await cur.fetchone()
                if not permission or not permission["creator_ok"] or not permission["approver_ok"]:
                    await db.execute(
                        "UPDATE business.p4_base_deliveries SET status='fatal',"
                        "last_error='CURRENT_PERMISSION_DENIED' WHERE outbox_id=%s",
                        (row["outbox_id"],),
                    )
                    continue
                snapshot = ItemProjection.model_validate_json(json.dumps(row["projection"]))
                if facts_hash(snapshot.model_dump(mode="json")) != row["projection_hash"]:
                    raise ValueError("INVALID_P4_STORED_PROJECTION")
                request = ProjectionRequest(
                    outbox_id=row["outbox_id"],
                    organization_id=row["organization_id"],
                    shop_id=row["shop_id"],
                    target_key=row["target_key"],
                    operation=operation,
                    client_token=row["client_token"],
                    external_id=row["anchor"],
                    projection=snapshot,
                )
                attempts = row["attempts"] + 1
                await db.execute(
                    """UPDATE business.p4_base_deliveries SET status='sending',
                    attempts=%s,claimed_by=%s,
                    last_operation=%s,first_attempt_at=COALESCE(first_attempt_at,clock_timestamp())
                    WHERE outbox_id=%s""",
                    (attempts, self.session.owner, operation, row["outbox_id"]),
                )
                break
            await self.session.check()
        if request is None:
            return "idle"
        if not self.gate.active():
            result = ProjectionResult(outcome="unknown", code="DELIVERY_WINDOW_EXPIRED")
        else:
            try:
                async with asyncio.timeout(request.timeout_seconds):
                    if self.ledger:
                        with self.ledger.scope(
                            SDKScope(
                                request.outbox_id, request.projection.task_id, "base_projection"
                            )
                        ):
                            result = await self.adapter.project(request)
                    else:
                        result = await self.adapter.project(request)
                result = ProjectionResult.model_validate(result.model_dump())
            except Exception:
                result = ProjectionResult(outcome="unknown", code="BASE_OPERATION_UNKNOWN")
        await self.session.check()
        async with await open_async(self.session.settings) as db, db.transaction():
            cur = await db.execute(
                "SELECT version FROM business.replenishment_items "
                "WHERE id=%s AND task_id=%s FOR SHARE",
                (request.projection.item_id, request.projection.task_id),
            )
            current = await cur.fetchone()
            if not current:
                raise ValueError("INVALID_P4_CURRENT_ITEM")
            final = disposition(
                request, result, current_version=current["version"], attempts=attempts
            )
            await db.execute(
                """UPDATE business.p4_base_deliveries SET status=%s,last_error=%s,
                external_id=COALESCE(external_id,%s),observed_version=%s,complete_unique_verified=%s,
                last_checked_at=clock_timestamp(),
                next_attempt_at=clock_timestamp()+%s*interval '1 second'
                WHERE outbox_id=%s AND status='sending' AND claimed_by=%s AND attempts=%s""",
                (
                    final.status,
                    None if final.status == "verified" else final.code,
                    final.anchor,
                    final.observed_version,
                    final.status == "verified",
                    final.delay_seconds,
                    request.outbox_id,
                    self.session.owner,
                    attempts,
                ),
            )
            if final.anchor and request.projection.sync_version == 1:
                await db.execute(
                    """INSERT INTO business.p4_base_links(organization_id,shop_id,
                    target_key,item_id,
                    original_outbox_id,external_id) VALUES(%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(organization_id,shop_id,target_key,item_id) DO NOTHING""",
                    (
                        request.organization_id,
                        request.shop_id,
                        request.target_key,
                        request.projection.item_id,
                        request.outbox_id,
                        final.anchor,
                    ),
                )
            await db.execute(
                """INSERT INTO business.audit_events(id,organization_id,task_id,source,action,
                entity_type,entity_id,after_state,trace_id)
                VALUES(%s,%s,%s,'feishu_delivery','base_projection_checked','outbox',%s,%s,%s)""",
                (
                    uuid4(),
                    request.organization_id,
                    request.projection.task_id,
                    str(request.outbox_id),
                    Jsonb(
                        {
                            "operation": request.operation,
                            "status": final.status,
                            "version": request.projection.sync_version,
                            "observed_version": final.observed_version,
                            "complete_unique_verified": final.status == "verified",
                            "verification_mode": self.gate.verification_mode,
                            "safe_code": final.code,
                        }
                    ),
                    uuid4(),
                ),
            )
            await self.session.check()
        return final.status

    async def reconcile(self) -> None:
        await self.dispatch_one()
