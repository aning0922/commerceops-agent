"""固定P3节点/唯一业务interrupt；同thread重验证、整计划执行与永久恢复。"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypedDict, cast
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from commerceops.application.replenishment.contracts import WORKFLOW_VERSION
from commerceops.application.replenishment.planning import PlanRejected
from commerceops.application.runner import RunRequest, RunResult
from commerceops.domain.commerce_values import facts_hash
from commerceops.infrastructure.approval_recovery import ApprovalRecovery, snapshot_binding
from commerceops.infrastructure.checkpoint import checkpointer
from commerceops.infrastructure.inventory_repository import AnalysisUnsafe
from commerceops.infrastructure.replenishment_execution import (
    ExecutionStore,
    RevalidationRequired,
    transition_digest,
)
from commerceops.infrastructure.replenishment_repository import ApprovalStore
from commerceops.infrastructure.worker_lock import open_async
from commerceops.workflows.inventory_analysis import CollectorFactory

Hook = Callable[[str], Awaitable[None]]


async def no_hook(point: str) -> None:
    pass


class ApprovalState(TypedDict, total=False):
    workflow_version: str
    task_id: str
    request_hash: str
    plan_id: str
    approval_id: str
    plan_hash: str
    plan_version: int
    outcome: str
    decision_id: str
    decision_hash: str
    revalidation_snapshot_id: str
    execution_id: str
    failure_code: str


class ApprovalRunner:
    workflow_versions = frozenset({WORKFLOW_VERSION})

    def __init__(
        self,
        store: ApprovalStore,
        *,
        hook: Hook = no_hook,
        collector_factory: CollectorFactory | None = None,
    ):
        self.store, self.hook = store, hook
        self.recovery = ApprovalRecovery(store)
        self.active = 0
        self.execution = ExecutionStore(store, collector_factory)
        self.snapshot_getter: Callable[[], Awaitable[Any]] | None = None

    async def run(self, r: RunRequest) -> RunResult:
        if self.active:
            raise AnalysisUnsafe("P3_GRAPH_SLOT_BUSY")
        self.active += 1
        before = asyncio.all_tasks()
        try:
            return await self._run(r)
        except AnalysisUnsafe as error:
            await self.attention(r, str(error))
            return RunResult()
        except PlanRejected as error:
            await self.store.reject(r, str(error))
            return RunResult()
        except RevalidationRequired:
            if r.attempt >= 3:
                await self.attention(r, "P3_FRESH_REVALIDATION_UNAVAILABLE")
                return RunResult()
            return RunResult("retry", self.store.config.recovery_scan_seconds)
        except (ValueError, TimeoutError):
            await self.attention(r, "P3_REVALIDATION_INPUT_UNSAFE")
            return RunResult()
        finally:
            pending = asyncio.all_tasks() - before
            while pending:
                try:
                    await asyncio.wait(pending)
                except asyncio.CancelledError:
                    pass
                pending = {task for task in pending if not task.done()}
            self.active -= 1
            self.snapshot_getter = None

    def build_graph(self, r: RunRequest, expected: dict[str, str]) -> StateGraph[ApprovalState]:
        def bound(state: ApprovalState) -> None:
            if any(state.get(k) != v for k, v in expected.items()):
                raise AnalysisUnsafe("P3_CHECKPOINT_UNSAFE")

        async def prepare(state: ApprovalState) -> ApprovalState:
            bound(state)
            # 节点入口观测点：官方sync输入checkpoint已落库，尚未开始T2业务事务。
            await self.hook("before_prepare")
            result = await self.store.prepare(r)
            if result["outcome"] == "source_pending":
                raise AnalysisUnsafe("P3_SOURCE_DEPENDENCY_NOT_READY")
            if result["outcome"] == "no_action":
                return {"outcome": "no_action"}
            async with await open_async(self.store.settings) as db:
                cur = await db.execute(
                    """SELECT plan_hash,plan_version FROM business.approvals
                WHERE id=%s AND task_id=%s AND organization_id=%s AND shop_id=%s""",
                    (UUID(result["approval_id"]), r.task_id, r.organization_id, r.shop_id),
                )
                approval = await cur.fetchone()
            if not approval:
                raise AnalysisUnsafe("P3_APPROVAL_MISSING")
            return {
                "plan_id": result["plan_id"],
                "approval_id": result["approval_id"],
                "plan_hash": approval["plan_hash"],
                "plan_version": approval["plan_version"],
                "outcome": "awaiting_approval",
            }

        async def wait(state: ApprovalState) -> ApprovalState:
            bound(state)
            async with await open_async(self.store.settings) as db:
                cur = await db.execute(
                    """SELECT a.* FROM business.approvals a
                JOIN business.business_tasks t ON t.active_plan_id=a.plan_id
                WHERE a.id=%s AND a.task_id=%s AND a.organization_id=%s AND a.shop_id=%s
                AND t.id=a.task_id AND a.plan_id=%s AND a.plan_hash=%s AND
 a.plan_version=%s""",
                    (
                        UUID(state["approval_id"]),
                        r.task_id,
                        r.organization_id,
                        r.shop_id,
                        UUID(state["plan_id"]),
                        state["plan_hash"],
                        state["plan_version"],
                    ),
                )
                approval = await cur.fetchone()
            if not approval:
                raise AnalysisUnsafe("P3_INTERRUPT_BINDING_INVALID")
            # 固定唯一位置。callback/Command的值并非授权；只消费PG持久决定。
            interrupt(
                {
                    "approval_id": state["approval_id"],
                    "plan_id": state["plan_id"],
                    "plan_hash": state["plan_hash"],
                    "plan_version": state["plan_version"],
                }
            )
            approval = await self.recovery.authoritative(r)
            if approval["status"] == "expired":
                return {"outcome": "expired"}
            if approval["status"] not in ("approved", "rejected"):
                raise AnalysisUnsafe("P3_DECISION_NOT_PERSISTED")
            return {
                "decision_id": str(approval["decision_id"]),
                "decision_hash": approval["decision_payload_hash"],
                "outcome": "awaiting_execution" if approval["status"] == "approved" else "rejected",
            }

        async def revalidate(state: ApprovalState) -> ApprovalState:
            bound(state)
            if self.snapshot_getter is None:
                raise AnalysisUnsafe("P3_CURRENT_GRAPH_REQUIRED")
            snapshot = await self.snapshot_getter()
            task = await self.task(r.task_id)
            approval = await self.approval_for_state(task, dict(state))
            if snapshot_binding(snapshot, task, approval) == "execution_boundary":
                # 唯一业务interrupt已完成；持久continue在任何T4之前登记，非静态停机策略。
                if task["active_plan_id"] == approval["plan_id"]:
                    await self.hook("before_delivery_receipt")
                    await self.recovery.publish(r, snapshot)
                    await self.hook("after_delivery_receipt")
            await self.hook("before_revalidate")
            result = await self.execution.revalidate(r, dict(state))
            if result.get("outcome") == "awaiting_approval":
                await self.hook("after_replacement_commit")
            return cast(ApprovalState, result)

        async def execute(state: ApprovalState) -> ApprovalState:
            bound(state)
            await self.hook("before_execute")
            try:
                return cast(ApprovalState, await self.execution.execute(r, dict(state)))
            except RevalidationRequired:
                return {"outcome": "awaiting_execution", "revalidation_snapshot_id": ""}

        async def finish(state: ApprovalState) -> ApprovalState:
            bound(state)
            return {}

        graph = StateGraph(ApprovalState)
        graph.add_node("prepare_approval", prepare)
        graph.add_node("wait_approval", wait)
        graph.add_node("revalidate", revalidate)
        graph.add_node("execute", execute)
        graph.add_node("finish", finish)
        graph.add_edge(START, "prepare_approval")
        graph.add_conditional_edges(
            "prepare_approval",
            lambda state: (
                "wait_approval" if state.get("outcome") == "awaiting_approval" else "finish"
            ),
        )
        graph.add_conditional_edges(
            "wait_approval",
            lambda state: (
                "revalidate" if state.get("outcome") == "awaiting_execution" else "finish"
            ),
        )
        graph.add_conditional_edges(
            "revalidate",
            lambda state: (
                "wait_approval"
                if state.get("outcome") == "awaiting_approval"
                else "execute"
                if state.get("outcome") == "execution_ready"
                else "finish"
            ),
        )
        graph.add_conditional_edges(
            "execute",
            lambda state: (
                "revalidate" if state.get("outcome") == "awaiting_execution" else "finish"
            ),
        )
        graph.add_edge("finish", END)
        return graph

    async def task(self, task_id: UUID) -> dict[str, Any]:
        await self.store.session.check()
        async with await open_async(self.store.settings) as db:
            cur = await db.execute(
                """SELECT t.*,s.state AS source_state
             FROM business.business_tasks t JOIN business.p3_task_sources b ON
 b.task_id=t.id
             JOIN business.business_tasks s ON s.id=b.source_task_id
             WHERE t.id=%s AND t.workflow_version=%s""",
                (task_id, WORKFLOW_VERSION),
            )
            task = await cur.fetchone()
            if not task:
                raise AnalysisUnsafe("P3_TASK_MISSING")
            return task

    async def approval(self, task: dict[str, Any]) -> dict[str, Any] | None:
        async with await open_async(self.store.settings) as db:
            cur = await db.execute(
                "SELECT * FROM business.approvals WHERE plan_id=%s", (task["active_plan_id"],)
            )
            return await cur.fetchone()

    async def approval_for_state(
        self, task: dict[str, Any], state: dict[str, Any]
    ) -> dict[str, Any]:
        async with await open_async(self.store.settings) as db:
            cur = await db.execute(
                """SELECT * FROM business.approvals
 WHERE id=%s AND task_id=%s AND organization_id=%s AND shop_id=%s""",
                (UUID(state["approval_id"]), task["id"], task["organization_id"], task["shop_id"]),
            )
            row = await cur.fetchone()
        if not row:
            raise AnalysisUnsafe("P3_CHECKPOINT_APPROVAL_MISSING")
        return row

    async def attention(self, r: RunRequest, code: str) -> None:
        await self.store.session.check()
        await self.hook("attention:" + code)
        async with await open_async(self.store.settings) as db:
            await db.execute(
                """UPDATE business.business_tasks t SET state='needs_attention',
             failure_code=%s,version=version+1,updated_at=clock_timestamp() WHERE id=%s
             AND organization_id=%s AND shop_id=%s AND workflow_version=%s
             AND state NOT IN ('completed','rejected','expired') AND EXISTS(
             SELECT 1 WHERE t.state<>'needs_attention' OR t.failure_code IS NULL
             OR t.failure_code='WORKER_TERMINATION_UNCONFIRMED') AND EXISTS(
             SELECT 1 FROM business.jobs j WHERE j.id=%s AND j.task_id=t.id
             AND j.status='running' AND j.lease_owner=%s)""",
                (
                    code,
                    r.task_id,
                    r.organization_id,
                    r.shop_id,
                    WORKFLOW_VERSION,
                    r.job_id,
                    r.owner,
                ),
            )

    async def target_approval(self, r: RunRequest) -> dict[str, Any] | None:
        if r.kind == "analyze" or r.payload_ref.startswith("expiry:"):
            return None
        await self.store.session.check()
        async with await open_async(self.store.settings) as db:
            cur = await db.execute(
                """SELECT a.* FROM business.jobs j
                JOIN business.approval_resumes x ON
                ((j.kind='resume' AND j.id=x.job_id AND
 j.payload_ref='decision:'||x.decision_id::text)
                OR (j.kind='recover' AND j.id=x.continuation_job_id
                AND j.payload_ref='continue:'||x.decision_id::text))
                JOIN business.approvals a ON a.id=x.approval_id AND
 a.decision_id=x.decision_id
                WHERE j.id=%s AND j.task_id=%s AND j.organization_id=%s AND j.shop_id=%s
                AND j.status='running' AND j.lease_owner=%s AND j.kind=%s AND
 j.payload_ref=%s
                AND a.task_id=j.task_id AND a.organization_id=j.organization_id AND
 a.shop_id=j.shop_id""",
                (r.job_id, r.task_id, r.organization_id, r.shop_id, r.owner, r.kind, r.payload_ref),
            )
            row = await cur.fetchone()
        if not row:
            raise AnalysisUnsafe("P3_REGISTERED_DECISION_JOB_REQUIRED")
        return row

    async def version_crossing(
        self,
        r: RunRequest,
        task: dict[str, Any],
        snapshot: Any,
        approval: dict[str, Any],
        target: dict[str, Any] | None,
        mode: str,
    ) -> RunResult | None:
        if target is None or target["id"] == approval["id"]:
            return None
        async with await open_async(self.store.settings) as db:
            cur = await db.execute(
                """SELECT * FROM business.p3_revalidation_transitions
                WHERE task_id=%s AND organization_id=%s AND shop_id=%s
                AND ((old_approval_id=%s AND next_approval_id=%s) OR
                (old_approval_id=%s AND next_approval_id=%s))""",
                (
                    r.task_id,
                    r.organization_id,
                    r.shop_id,
                    target["id"],
                    approval["id"],
                    approval["id"],
                    target["id"],
                ),
            )
            transition = await cur.fetchone()
        if not transition:
            raise AnalysisUnsafe("P3_UNPROVEN_VERSION_CROSSING")
        if target["id"] == transition["old_approval_id"]:
            if (
                task["active_plan_id"] != transition["next_plan_id"]
                or approval["plan_id"] != transition["next_plan_id"]
                or approval["plan_version"] != transition["next_plan_version"]
                or mode
                not in (
                    "waiting",
                    "execution_boundary",
                    "ready_to_execute",
                    "executed",
                    "finish_execution",
                    "blocked",
                    "finish_blocked",
                )
            ):
                raise AnalysisUnsafe("P3_OLD_CONTINUATION_NEW_STATE_UNSAFE")
            if mode == "waiting":
                await self.recovery.ready(r.task_id, snapshot)
            elif transition["applied_at"] is None:
                raise AnalysisUnsafe("P3_REPLACEMENT_NOT_APPLIED")
            # 旧决定job只收敛，永不对新中断发Command或执行新版。
            return RunResult()
        if (
            r.kind != "resume"
            or mode != "execution_boundary"
            or transition["applied_at"] is not None
            or task["active_plan_id"] != transition["next_plan_id"]
            or approval["plan_id"] != transition["old_plan_id"]
            or approval["plan_hash"] != transition["old_plan_hash"]
            or approval["plan_version"] != transition["old_plan_version"]
            or str(approval["decision_id"]) != str(transition["decision_id"])
            or target["ready_at"] is not None
        ):
            raise AnalysisUnsafe("P3_NEW_DECISION_OLD_CHECKPOINT_UNSAFE")
        return RunResult("waiting_checkpoint", self.store.config.recovery_scan_seconds)

    async def verify_terminal(self, r: RunRequest, snapshot: Any, mode: str) -> None:
        async with self.execution.locked(r, dict(snapshot.values)) as (db, task, plan, approval, _):
            if mode in ("executed", "finish_execution"):
                receipt = await self.execution.existing(db, plan, approval)
                if (
                    not receipt
                    or str(receipt["id"]) != snapshot.values.get("execution_id")
                    or task["state"] != "completed"
                ):
                    raise AnalysisUnsafe("P3_FINISHED_EXECUTION_UNSAFE")
            else:
                blocked = await self.execution.replacement(
                    db, r, dict(snapshot.values), task, plan, approval
                )
                if not blocked or blocked.get("outcome") != "revalidation_blocked":
                    raise AnalysisUnsafe("P3_FINISHED_REVALIDATION_UNSAFE")

    async def pending_replacement(self, task_id: UUID, snapshot: Any) -> bool:
        """维护扫描识别已提交的新版本/旧CP间隙；不发Command或消费任何决定。"""
        task = await self.task(task_id)
        if not isinstance(snapshot.values, dict) or not snapshot.values.get("approval_id"):
            return False
        approval = await self.approval_for_state(task, snapshot.values)
        if task["active_plan_id"] == approval["plan_id"]:
            return False
        if snapshot_binding(snapshot, task, approval) != "execution_boundary":
            return False
        async with await open_async(self.store.settings) as db:
            cur = await db.execute(
                """SELECT x.* FROM business.p3_revalidation_transitions x
                JOIN business.replenishment_plans old ON old.id=x.old_plan_id
                JOIN business.replenishment_plans new ON new.id=x.next_plan_id
                JOIN business.approvals a ON a.id=x.next_approval_id
                WHERE x.task_id=%s AND x.organization_id=%s AND x.shop_id=%s
                AND x.old_approval_id=%s AND x.old_plan_id=%s AND x.decision_id=%s
                AND x.old_plan_version=%s AND x.old_plan_hash=%s
                AND x.next_plan_id=%s AND x.applied_at IS NULL
                AND old.status='superseded' AND new.status='current'
                AND new.evidence_kind='p3_observation'
                AND new.p3_observation_id=x.observation_id
                AND a.plan_id=new.id AND a.plan_version=x.next_plan_version""",
                (
                    task_id,
                    task["organization_id"],
                    task["shop_id"],
                    approval["id"],
                    approval["plan_id"],
                    approval["decision_id"],
                    approval["plan_version"],
                    approval["plan_hash"],
                    task["active_plan_id"],
                ),
            )
            transition = await cur.fetchone()
        return bool(
            transition
            and approval["consumed_at"] is None
            and transition["transition_hash"] == transition_digest(transition)
        )

    async def reconcile(self, *, task_ids: frozenset[UUID] | None = None) -> None:
        await self.store.session.check()
        async with await open_async(self.store.settings) as db:
            cur = await db.execute(
                """SELECT t.id,j.id AS job_id,t.organization_id,t.shop_id,
             t.thread_id,t.normalized_request FROM business.business_tasks t
             JOIN business.approvals a ON a.task_id=t.id AND a.plan_id=t.active_plan_id
             JOIN business.jobs j ON j.task_id=t.id AND j.dedupe_key='p3:'||t.id::text
             WHERE t.kind='inventory_replenishment' AND t.workflow_version=%s
             AND (%s::uuid[] IS NULL OR t.id=ANY(%s))
             AND (t.state IN ('awaiting_approval','needs_reapproval') OR
 (t.state='needs_attention'
             AND t.failure_code='WORKER_TERMINATION_UNCONFIRMED'))
             AND (a.ready_at IS NULL OR (a.status='pending' AND
 a.expires_at<=clock_timestamp()))
             ORDER BY t.created_at,t.id LIMIT 20""",
                (
                    WORKFLOW_VERSION,
                    None if task_ids is None else list(task_ids),
                    None if task_ids is None else list(task_ids),
                ),
            )
            rows = await cur.fetchall()
        async with checkpointer(self.store.settings) as saver:
            for row in rows:
                r = RunRequest(
                    row["job_id"],
                    row["id"],
                    row["organization_id"],
                    row["shop_id"],
                    row["thread_id"],
                    WORKFLOW_VERSION,
                    "recover",
                    f"task:{row['id']}",
                    self.store.session.owner,
                    0,
                )
                expected = {
                    "workflow_version": WORKFLOW_VERSION,
                    "task_id": str(row["id"]),
                    "request_hash": facts_hash(row["normalized_request"]),
                }
                compiled = self.build_graph(r, expected).compile(checkpointer=saver)
                cfg: RunnableConfig = {"configurable": {"thread_id": r.thread_id}}
                snapshot = await compiled.aget_state(cfg)
                if snapshot.created_at is None:
                    continue
                try:
                    if await self.pending_replacement(r.task_id, snapshot):
                        continue  # 注册的旧job将None接续；不能把旧CP标记为新approval ready。
                    await self.recovery.ready(r.task_id, snapshot)
                except AnalysisUnsafe:
                    # 本maintenance只标记注册的P3等待任务，不创建另一图或重发决定。
                    async with await open_async(self.store.settings) as db:
                        await db.execute(
                            """UPDATE business.business_tasks SET state='needs_attention',
                         failure_code='P3_CHECKPOINT_UNSAFE',version=version+1,
                         updated_at=clock_timestamp() WHERE id=%s
                         AND state NOT IN ('completed','rejected','expired')""",
                            (r.task_id,),
                        )

    async def _run(self, r: RunRequest) -> RunResult:
        if r.workflow_version != WORKFLOW_VERSION or r.kind not in ("analyze", "recover", "resume"):
            raise AnalysisUnsafe("P3_RUN_NOT_AVAILABLE")
        task = await self.task(r.task_id)
        if r.owner != self.store.session.owner or (r.organization_id, r.shop_id, r.thread_id) != (
            task["organization_id"],
            task["shop_id"],
            str(task["id"]),
        ):
            raise AnalysisUnsafe("P3_TASK_SCOPE_INVALID")
        if task["source_state"] != "completed":
            if task["source_state"] in ("failed", "needs_attention"):
                raise PlanRejected("DATA_INCOMPLETE")
            return RunResult("retry", 1)
        expected = {
            "workflow_version": WORKFLOW_VERSION,
            "task_id": str(r.task_id),
            "request_hash": facts_hash(task["normalized_request"]),
        }
        cfg: RunnableConfig = {"configurable": {"thread_id": r.thread_id}, "recursion_limit": 10}
        async with checkpointer(self.store.settings) as saver:
            compiled = self.build_graph(r, expected).compile(checkpointer=saver)

            async def current_snapshot() -> Any:
                return await compiled.aget_state(cfg)

            self.snapshot_getter = current_snapshot
            snapshot = await compiled.aget_state(cfg)
            if (
                task["state"] == "needs_attention"
                and task["failure_code"] == "WORKER_TERMINATION_UNCONFIRMED"
                and task["active_plan_id"] is None
                and r.kind == "analyze"
            ):
                if snapshot.created_at is not None and (
                    snapshot.next != ("prepare_approval",)
                    or snapshot.interrupts
                    or not isinstance(snapshot.values, dict)
                    or set(snapshot.values) != set(expected)
                    or any(snapshot.values.get(k) != v for k, v in expected.items())
                ):
                    raise AnalysisUnsafe("P3_PREPARE_RECOVERY_CHECKPOINT_UNSAFE")
                await self.store.session.check()
                async with await open_async(self.store.settings) as db:
                    restored = await db.execute(
                        """UPDATE business.business_tasks t SET state='queued',
                     failure_code=NULL,version=version+1,updated_at=clock_timestamp()
 WHERE id=%s
                     AND state='needs_attention' AND
 failure_code='WORKER_TERMINATION_UNCONFIRMED'
                     AND EXISTS(SELECT 1 FROM business.jobs j WHERE j.id=%s AND
 j.task_id=t.id
                     AND j.organization_id=t.organization_id AND j.shop_id=t.shop_id
                     AND j.kind='analyze' AND j.payload_ref='task:'||t.id::text
                     AND j.dedupe_key='p3:'||t.id::text AND j.status='running'
                     AND j.lease_owner=%s)
                     AND NOT EXISTS(SELECT 1 FROM business.replenishment_plans p
                     WHERE p.task_id=t.id)
                     AND NOT EXISTS(SELECT 1 FROM business.approvals a WHERE a.task_id=t.id)
                     AND NOT EXISTS(SELECT 1 FROM business.outbox o WHERE o.task_id=t.id)""",
                        (r.task_id, r.job_id, r.owner),
                    )
                    if restored.rowcount != 1:
                        raise AnalysisUnsafe("P3_PREPARE_RECOVERY_JOB_UNSAFE")
                task = await self.task(r.task_id)
            if snapshot.created_at is None:
                if task["state"] != "queued" or r.kind != "analyze":
                    raise AnalysisUnsafe("P3_CHECKPOINT_UNSAFE")
                data: Any = expected
            else:
                if not isinstance(snapshot.values, dict) or any(
                    snapshot.values.get(k) != v for k, v in expected.items()
                ):
                    raise AnalysisUnsafe("P3_CHECKPOINT_UNSAFE")
                if not snapshot.next and snapshot.values.get("outcome") == "no_action":
                    return RunResult()
                approval = await self.approval(task)
                if snapshot.values.get("approval_id"):
                    approval = await self.approval_for_state(task, snapshot.values)
                if not approval:
                    if (
                        task["state"] == "queued"
                        and task["active_plan_id"] is None
                        and r.kind == "analyze"
                        and snapshot.next == ("prepare_approval",)
                        and not snapshot.interrupts
                        and set(snapshot.values) == set(expected)
                    ):
                        await self.store.session.check()
                        async with await open_async(self.store.settings) as db:
                            cur = await db.execute(
                                """SELECT 1 FROM business.jobs j WHERE j.id=%s AND j.task_id=%s
                             AND j.organization_id=%s AND j.shop_id=%s AND
 j.kind='analyze'
                             AND j.dedupe_key='p3:'||j.task_id::text
                             AND j.payload_ref='task:'||j.task_id::text
                             AND j.status='running' AND j.lease_owner=%s
                             AND NOT EXISTS(SELECT 1 FROM business.approvals a
                             WHERE a.task_id=j.task_id AND a.decision_id IS NOT NULL)""",
                                (r.job_id, r.task_id, r.organization_id, r.shop_id, r.owner),
                            )
                            if not await cur.fetchone():
                                raise AnalysisUnsafe("P3_PREPARE_RECOVERY_JOB_UNSAFE")
                        mode = "preparing"
                    else:
                        raise AnalysisUnsafe("P3_APPROVAL_MISSING")
                else:
                    mode = snapshot_binding(snapshot, task, approval)
                target = await self.target_approval(r)
                if approval:
                    crossing = await self.version_crossing(
                        r, task, snapshot, approval, target, mode
                    )
                    if crossing:
                        return crossing
                if mode in ("executed", "finish_execution", "blocked", "finish_blocked"):
                    await self.verify_terminal(r, snapshot, mode)
                    if mode in ("executed", "blocked"):
                        return RunResult()
                    data = None
                elif mode in ("execution_boundary", "ready_to_execute"):
                    if r.kind == "analyze":
                        if mode != "execution_boundary":
                            raise AnalysisUnsafe("P3_INITIAL_JOB_CANNOT_EXECUTE")
                        await self.recovery.authoritative(r)
                        await self.recovery.publish(r, snapshot)
                        return RunResult()
                    if not target or not approval or target["id"] != approval["id"]:
                        raise AnalysisUnsafe("P3_EXECUTION_DECISION_JOB_UNSAFE")
                    # 同一持久中断已经完成；A02旧next与A03execute都只None续跑。
                    data = None
                elif mode in ("rejected", "expired"):
                    await self.recovery.authoritative(r)
                    await self.recovery.publish(r, snapshot)
                    return RunResult()
                elif r.kind == "resume" or r.payload_ref.startswith("expiry:"):
                    approval = await self.recovery.authoritative(r)
                    if mode == "preparing":
                        async with await open_async(self.store.settings) as db:
                            cur = await db.execute(
                                """SELECT 1 FROM business.jobs WHERE task_id=%s
                             AND dedupe_key='p3:'||task_id::text AND kind='analyze'
                             AND status IN ('ready','running','retry_wait')""",
                                (r.task_id,),
                            )
                            if not await cur.fetchone():
                                raise AnalysisUnsafe("P3_PREPARATION_RECEIPT_MISSING")
                        return RunResult(
                            "waiting_checkpoint", self.store.config.recovery_scan_seconds
                        )
                    if mode != "waiting":
                        raise AnalysisUnsafe("P3_RESUME_NEXT_INVALID")
                    await self.recovery.ready(r.task_id, snapshot)
                    data = Command(
                        resume={
                            "approval_id": str(approval["id"]),
                            "decision_id": str(approval["decision_id"]),
                        }
                    )
                elif mode == "waiting":
                    await self.recovery.ready(r.task_id, snapshot)
                    return RunResult("interrupted")
                else:
                    data = None  # 只接续既有prepare checkpoint，永不重建START。
            await self.hook("before_graph")
            await compiled.ainvoke(data, cfg, durability="sync")
            snapshot = await compiled.aget_state(cfg)
            await self.hook("checkpoint_persisted")
            task = await self.task(r.task_id)
            approval = await self.approval(task)
            if not approval and not snapshot.next and snapshot.values.get("outcome") == "no_action":
                return RunResult()
            if not approval:
                raise AnalysisUnsafe("P3_APPROVAL_MISSING")
            mode = snapshot_binding(snapshot, task, approval)
            if mode == "waiting":
                await self.hook("before_ready")
                await self.recovery.ready(r.task_id, snapshot)
                await self.hook("after_ready")
                return RunResult("interrupted")
            if mode in ("execution_boundary", "rejected", "expired"):
                await self.hook("before_delivery_receipt")
                await self.recovery.publish(r, snapshot)
                await self.hook("after_delivery_receipt")
                return RunResult()
            if mode in ("executed", "blocked"):
                await self.verify_terminal(r, snapshot, mode)
                return RunResult()
            raise AnalysisUnsafe("P3_GRAPH_STATE_UNSAFE")
