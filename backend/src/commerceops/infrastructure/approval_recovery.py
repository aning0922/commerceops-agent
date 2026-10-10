"""单Worker内P3官方checkpoint匹配、ready、唯一决定送达与持久A03接续意图。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

from langgraph.types import StateSnapshot
from psycopg import AsyncConnection

from commerceops.application.replenishment.contracts import WORKFLOW_VERSION
from commerceops.application.runner import RunRequest
from commerceops.domain.commerce_values import facts_hash
from commerceops.infrastructure.inventory_repository import AnalysisUnsafe
from commerceops.infrastructure.replenishment_repository import ApprovalStore
from commerceops.infrastructure.worker_lock import open_async

AsyncDB = AsyncConnection[dict[str, Any]]


def snapshot_binding(
    snapshot: StateSnapshot, task: dict[str, Any], approval: dict[str, Any]
) -> str:
    values = snapshot.values
    core = {
        "workflow_version": WORKFLOW_VERSION,
        "task_id": str(task["id"]),
        "request_hash": facts_hash(task["normalized_request"]),
    }
    if (
        not isinstance(values, dict)
        or any(values.get(k) != v for k, v in core.items())
        or snapshot.config.get("configurable", {}).get("thread_id") != str(task["id"])
    ):
        raise AnalysisUnsafe("P3_CHECKPOINT_BINDING_INVALID")
    if snapshot.next == ("prepare_approval",) and not snapshot.interrupts:
        return "preparing"
    binding = {
        "approval_id": str(approval["id"]),
        "plan_id": str(approval["plan_id"]),
        "plan_version": approval["plan_version"],
        "plan_hash": approval["plan_hash"],
    }
    if (
        any(values.get(k) != v for k, v in binding.items())
        or type(values.get("plan_version")) is not int
    ):
        raise AnalysisUnsafe("P3_CHECKPOINT_PLAN_INVALID")
    if snapshot.next == ("wait_approval",):
        if len(snapshot.interrupts) != 1 or snapshot.interrupts[0].value != binding:
            raise AnalysisUnsafe("P3_CHECKPOINT_INTERRUPT_INVALID")
        return "waiting"
    if snapshot.interrupts:
        raise AnalysisUnsafe("P3_CHECKPOINT_UNEXPECTED_INTERRUPT")
    if approval["decision_id"] is not None:
        if (values.get("decision_id"), values.get("decision_hash")) != (
            str(approval["decision_id"]),
            approval["decision_payload_hash"],
        ):
            raise AnalysisUnsafe("P3_CHECKPOINT_DECISION_INVALID")
        if (
            snapshot.next == ("revalidate",)
            and values.get("outcome") == "awaiting_execution"
            and approval["status"] == "approved"
        ):
            return "execution_boundary"
        if (
            not snapshot.next
            and values.get("outcome") == "rejected"
            and approval["status"] == "rejected"
        ):
            return "rejected"
    if not snapshot.next and values.get("outcome") == "expired" and approval["status"] == "expired":
        return "expired"
    raise AnalysisUnsafe("P3_CHECKPOINT_NEXT_UNSAFE")


class ApprovalRecovery:
    def __init__(self, store: ApprovalStore):
        self.store, self.settings, self.session = store, store.settings, store.session

    @asynccontextmanager
    async def locked(
        self, task_id: UUID, *, request: RunRequest | None = None
    ) -> AsyncIterator[tuple[AsyncDB, dict[str, Any], dict[str, Any], dict[str, Any]]]:
        await self.session.check()
        async with await open_async(self.settings) as db, db.transaction():
            cur = await db.execute(
                """SELECT * FROM business.business_tasks WHERE id=%s
             AND kind='inventory_replenishment' AND workflow_version=%s FOR UPDATE""",
                (task_id, WORKFLOW_VERSION),
            )
            task = await cur.fetchone()
            if not task or not task["active_plan_id"]:
                raise AnalysisUnsafe("P3_ACTIVE_PLAN_MISSING")
            cur = await db.execute(
                "SELECT * FROM business.replenishment_plans WHERE id=%s FOR UPDATE",
                (task["active_plan_id"],),
            )
            plan = await cur.fetchone()
            cur = await db.execute(
                "SELECT * FROM business.approvals WHERE plan_id=%s FOR UPDATE",
                (task["active_plan_id"],),
            )
            approval = await cur.fetchone()
            if (
                not plan
                or not approval
                or approval["task_id"] != task_id
                or plan["status"] != "current"
            ):
                raise AnalysisUnsafe("P3_ACTIVE_APPROVAL_INVALID")
            if request is not None:
                if request.owner != self.session.owner or (
                    request.organization_id,
                    request.shop_id,
                    request.thread_id,
                    request.workflow_version,
                ) != (task["organization_id"], task["shop_id"], str(task_id), WORKFLOW_VERSION):
                    raise AnalysisUnsafe("P3_RECOVERY_SCOPE_INVALID")
                cur = await db.execute(
                    """SELECT * FROM business.jobs WHERE id=%s AND task_id=%s
                 AND status='running' AND lease_owner=%s AND kind=%s AND payload_ref=%s
                 FOR SHARE""",
                    (request.job_id, task_id, request.owner, request.kind, request.payload_ref),
                )
                if not await cur.fetchone():
                    raise AnalysisUnsafe("P3_RECOVERY_JOB_OWNER_INVALID")
            yield db, task, plan, approval
            await self.session.check()

    async def ready(self, task_id: UUID, snapshot: StateSnapshot) -> None:
        async with self.locked(task_id) as (db, task, _, approval):
            mode = snapshot_binding(snapshot, task, approval)
            if mode != "waiting":
                return  # preparing/静态批准边界不能被当成缺人工interrupt重新索要确认。
            checkpoint_id = snapshot.config.get("configurable", {}).get("checkpoint_id")
            if not isinstance(checkpoint_id, str) or not checkpoint_id:
                raise AnalysisUnsafe("P3_READY_CHECKPOINT_ID_MISSING")
            if approval["ready_at"] is None:
                await db.execute(
                    """UPDATE business.approvals SET ready_at=clock_timestamp(),
                 ready_checkpoint_id=%s WHERE id=%s AND ready_at IS NULL""",
                    (checkpoint_id, approval["id"]),
                )
                await self.audit(db, task, "approval_checkpoint_ready", str(approval["id"]))
            # 仅明确的旧Worker未确认标记，在session.start已证明旧进程结束后恢复等待。
            if (
                task["state"] == "needs_attention"
                and task["failure_code"] == "WORKER_TERMINATION_UNCONFIRMED"
            ):
                await db.execute(
                    """UPDATE business.business_tasks SET state='awaiting_approval',
                 failure_code=NULL,version=version+1,updated_at=clock_timestamp() WHERE id=%s""",
                    (task_id,),
                )
            cur = await db.execute("SELECT clock_timestamp() AS time")
            clock = await cur.fetchone()
            if not clock:
                raise AnalysisUnsafe("P3_RECOVERY_CLOCK_UNAVAILABLE")
            if approval["status"] == "pending" and clock["time"] >= approval["expires_at"]:
                await db.execute(
                    "UPDATE business.approvals SET status='expired' "
                    "WHERE id=%s AND status='pending'",
                    (approval["id"],),
                )
                await self.enqueue(
                    db, task, "recover", f"p3-expiry:{approval['id']}", f"expiry:{approval['id']}"
                )
                await self.audit(db, task, "approval_expired", str(approval["id"]))
            elif approval["status"] in ("pending", "approved", "rejected"):
                await db.execute(
                    """UPDATE business.outbox SET status='pending' WHERE task_id=%s
                 AND aggregate_id=%s AND operation='approval_card' AND status='blocked'
                 AND NOT sender_enabled""",
                    (task_id, approval["id"]),
                )
            if approval["decision_id"]:
                await db.execute(
                    """UPDATE business.jobs j SET available_at=clock_timestamp(),
                 updated_at=clock_timestamp() FROM business.approval_resumes r
                 WHERE r.decision_id=%s AND r.job_id=j.id AND j.status='retry_wait'
                 AND r.delivery_state='waiting_checkpoint'""",
                    (approval["decision_id"],),
                )
                await db.execute(
                    """UPDATE business.approval_resumes SET delivery_state='queued'
                 WHERE decision_id=%s AND delivery_state='waiting_checkpoint'""",
                    (approval["decision_id"],),
                )

    async def authoritative(self, request: RunRequest) -> dict[str, Any]:
        async with self.locked(request.task_id, request=request) as (db, _, _, approval):
            if await self.original_job(db, request):
                return approval
            if request.payload_ref == f"expiry:{approval['id']}" and request.kind == "recover":
                if approval["status"] != "expired":
                    raise AnalysisUnsafe("P3_EXPIRY_NOT_AUTHORITATIVE")
                return approval
            cur = await db.execute(
                "SELECT * FROM business.approval_resumes WHERE approval_id=%s FOR UPDATE",
                (approval["id"],),
            )
            resume = await cur.fetchone()
            if not resume or (
                not (
                    request.kind == "resume"
                    and request.job_id == resume["job_id"]
                    and request.payload_ref == f"decision:{resume['decision_id']}"
                )
                and not (
                    request.kind == "recover"
                    and request.job_id == resume["continuation_job_id"]
                    and request.payload_ref == f"continue:{resume['decision_id']}"
                )
            ):
                raise AnalysisUnsafe("P3_RESUME_DECISION_BINDING_INVALID")
            return approval

    async def publish(self, request: RunRequest, snapshot: StateSnapshot) -> None:
        async with self.locked(request.task_id, request=request) as (db, task, _, approval):
            mode = snapshot_binding(snapshot, task, approval)
            if mode not in ("execution_boundary", "rejected", "expired"):
                raise AnalysisUnsafe("P3_DECISION_NOT_DELIVERED")
            if mode == "expired":
                if request.payload_ref != f"expiry:{approval['id']}" or request.kind != "recover":
                    raise AnalysisUnsafe("P3_EXPIRY_JOB_INVALID")
                if task["state"] != "expired":
                    await db.execute(
                        """UPDATE business.business_tasks SET state='expired',
                     failure_code=NULL,version=version+1,updated_at=clock_timestamp()
                     WHERE id=%s""",
                        (task["id"],),
                    )
                return
            cur = await db.execute(
                "SELECT * FROM business.approval_resumes WHERE decision_id=%s FOR UPDATE",
                (approval["decision_id"],),
            )
            resume = await cur.fetchone()
            if not resume or (
                request.job_id
                not in (
                    resume["job_id"],
                    resume["continuation_job_id"],
                )
                and not await self.original_job(db, request)
            ):
                raise AnalysisUnsafe("P3_DELIVERY_JOB_INVALID")
            if resume["delivery_state"] == "consumed":
                if (
                    task["state"] == "needs_attention"
                    and task["failure_code"] == "WORKER_TERMINATION_UNCONFIRMED"
                    and mode == "execution_boundary"
                ):
                    await db.execute(
                        """UPDATE business.business_tasks SET state='executing',
                     failure_code=NULL,version=version+1,updated_at=clock_timestamp()
                     WHERE id=%s""",
                        (task["id"],),
                    )
                    await self.audit(
                        db,
                        task,
                        "approval_execution_boundary_restored",
                        str(approval["decision_id"]),
                    )
                return
            checkpoint_id = snapshot.config.get("configurable", {}).get("checkpoint_id")
            if not isinstance(checkpoint_id, str):
                raise AnalysisUnsafe("P3_DELIVERY_CHECKPOINT_MISSING")
            continuation = None
            if mode == "execution_boundary":
                continuation = await self.enqueue(
                    db,
                    task,
                    "recover",
                    f"p3-continue:{approval['decision_id']}",
                    f"continue:{approval['decision_id']}",
                )
            await db.execute(
                """UPDATE business.approval_resumes SET delivery_state='consumed',
             checkpoint_id=%s,delivered_at=clock_timestamp(),continuation_job_id=%s
             WHERE decision_id=%s""",
                (checkpoint_id, continuation, approval["decision_id"]),
            )
            await db.execute(
                """UPDATE business.business_tasks SET state=%s,failure_code=NULL,
             version=version+1,updated_at=clock_timestamp() WHERE id=%s""",
                ("executing" if mode == "execution_boundary" else "rejected", task["id"]),
            )
            await self.audit(db, task, "approval_decision_delivered", str(approval["decision_id"]))

    @staticmethod
    async def original_job(db: AsyncDB, request: RunRequest) -> bool:
        if request.kind != "analyze" or request.payload_ref != f"task:{request.task_id}":
            return False
        cur = await db.execute(
            "SELECT 1 FROM business.jobs WHERE id=%s AND dedupe_key=%s",
            (request.job_id, f"p3:{request.task_id}"),
        )
        return await cur.fetchone() is not None

    @staticmethod
    async def enqueue(
        db: AsyncDB, task: dict[str, Any], kind: str, dedupe: str, payload: str
    ) -> UUID:
        cur = await db.execute(
            """INSERT INTO business.jobs
         (id,organization_id,shop_id,task_id,kind,dedupe_key,payload_ref)
         VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(dedupe_key) DO NOTHING RETURNING id""",
            (uuid4(), task["organization_id"], task["shop_id"], task["id"], kind, dedupe, payload),
        )
        result = await cur.fetchone()
        if result:
            return result["id"]  # type: ignore[no-any-return]
        cur = await db.execute(
            """SELECT id FROM business.jobs WHERE dedupe_key=%s AND payload_ref=%s
         AND organization_id=%s AND shop_id=%s AND task_id=%s AND kind=%s""",
            (dedupe, payload, task["organization_id"], task["shop_id"], task["id"], kind),
        )
        result = await cur.fetchone()
        if not result:
            raise AnalysisUnsafe("P3_RECOVERY_JOB_CONFLICT")
        return result["id"]  # type: ignore[no-any-return]

    @staticmethod
    async def audit(db: AsyncDB, task: dict[str, Any], action: str, entity: str) -> None:
        await db.execute(
            """INSERT INTO business.audit_events
         (id,organization_id,task_id,source,action,entity_type,entity_id,trace_id)
         VALUES (%s,%s,%s,'replenishment',%s,'approval',%s,%s)""",
            (uuid4(), task["organization_id"], task["id"], action, entity, uuid4()),
        )
