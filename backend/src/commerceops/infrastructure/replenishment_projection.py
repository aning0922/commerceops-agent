"""Phase3受控本地projection失败/对账；无sender、网络或业务终态修改。"""

from uuid import UUID, uuid4

from commerceops.infrastructure.inventory_repository import AnalysisUnsafe
from commerceops.infrastructure.worker_lock import WorkerSession, open_async


class ProjectionStore:
    def __init__(self, session: WorkerSession, *, controlled_stub: bool = False):
        self.session, self.controlled_stub = session, controlled_stub

    async def record_failure(self, identifier: UUID, *, unknown: bool = False) -> None:
        if not self.controlled_stub:
            raise AnalysisUnsafe("P3_PROJECTION_SENDER_DISABLED")
        await self.session.check()
        async with await open_async(self.session.settings) as db, db.transaction():
            cur = await db.execute(
                """SELECT o.* FROM business.outbox o
                JOIN business.shops s ON s.id=o.shop_id AND s.organization_id=o.organization_id
                WHERE o.id=%s AND o.organization_id=%s AND o.operation='item_projection'
                AND NOT o.sender_enabled AND s.adapter_kind='mock'
                AND s.environment IN ('mock','test')
                FOR UPDATE OF o""",
                (identifier, self.session.organization),
            )
            row = await cur.fetchone()
            if not row or row["status"] in ("sent", "sending") or row["external_id"] is not None:
                raise AnalysisUnsafe("P3_PROJECTION_STUB_SCOPE_UNSAFE")
            status = "unknown" if unknown or row["status"] == "unknown" else "dead"
            code = "CONTROLLED_STUB_UNKNOWN" if status == "unknown" else "CONTROLLED_STUB_FAILURE"
            if row["status"] != status or row["last_error"] != code:
                await db.execute(
                    """UPDATE business.outbox SET status=%s,source_mode='controlled_stub',
                    last_error=%s,attempts=attempts+1 WHERE id=%s""",
                    (status, code, identifier),
                )
            await self.session.check()

    async def reconcile(self, identifier: UUID) -> str:
        if not self.controlled_stub:
            raise AnalysisUnsafe("P3_PROJECTION_SENDER_DISABLED")
        await self.session.check()
        async with await open_async(self.session.settings) as db, db.transaction():
            cur = await db.execute(
                """SELECT o.*,i.version AS observed_version FROM business.outbox o
                JOIN business.replenishment_items i ON i.id=o.aggregate_id
                AND i.task_id=o.task_id AND i.organization_id=o.organization_id
                AND i.shop_id=o.shop_id
                WHERE o.id=%s AND o.organization_id=%s AND o.operation='item_projection'
                AND o.source_mode='controlled_stub' AND NOT o.sender_enabled FOR UPDATE OF o""",
                (identifier, self.session.organization),
            )
            row = await cur.fetchone()
            if (
                not row
                or row["external_id"] is not None
                or row["status"] not in ("dead", "unknown", "pending")
            ):
                raise AnalysisUnsafe("P3_PROJECTION_RECONCILIATION_UNSAFE")
            outcome = (
                "stale"
                if row["aggregate_version"] != row["observed_version"]
                else "unknown_held"
                if row["status"] == "unknown"
                else "missing"
            )
            cur = await db.execute(
                """INSERT INTO business.outbox_reconciliations(outbox_id,
                observed_version,outcome,source_mode) VALUES(%s,%s,%s,'controlled_stub')
                ON CONFLICT DO NOTHING RETURNING outbox_id""",
                (identifier, row["observed_version"], outcome),
            )
            new = await cur.fetchone()
            if outcome == "stale":
                await db.execute(
                    """UPDATE business.outbox SET status='dead',last_error='STALE_PROJECTION'
                    WHERE id=%s""",
                    (identifier,),
                )
            elif outcome == "missing":
                await db.execute(
                    "UPDATE business.outbox SET status='pending',last_error=NULL WHERE id=%s",
                    (identifier,),
                )
            # unknown保持unknown；没有外部回执绝不标sent/synced或自动回pending。
            if new:
                await db.execute(
                    """INSERT INTO business.audit_events(id,organization_id,task_id,
                    source,action,entity_type,entity_id,trace_id) VALUES(%s,%s,%s,'controlled_stub',
                    'projection_reconciled','outbox',%s,%s)""",
                    (uuid4(), row["organization_id"], row["task_id"], str(identifier), uuid4()),
                )
            await self.session.check()
            return outcome
