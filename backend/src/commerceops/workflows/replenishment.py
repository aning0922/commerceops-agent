"""从首个P3 checkpoint固定节点/单interrupt；A01只实现T2与持久等待。"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypedDict
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from commerceops.application.replenishment.contracts import WORKFLOW_VERSION
from commerceops.application.replenishment.planning import PlanRejected
from commerceops.application.runner import RunRequest, RunResult
from commerceops.domain.commerce_values import facts_hash
from commerceops.infrastructure.checkpoint import checkpointer
from commerceops.infrastructure.inventory_repository import AnalysisUnsafe
from commerceops.infrastructure.replenishment_repository import ApprovalStore
from commerceops.infrastructure.worker_lock import open_async

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


class ApprovalRunner:
    workflow_versions = frozenset({WORKFLOW_VERSION})

    def __init__(self, store: ApprovalStore, *, hook: Hook = no_hook):
        self.store, self.hook = store, hook
        self.active = 0

    async def run(self, r: RunRequest) -> RunResult:
        if self.active:
            raise AnalysisUnsafe("P3_GRAPH_SLOT_BUSY")
        self.active += 1
        before = asyncio.all_tasks()
        try:
            return await self._run(r)
        except PlanRejected as error:
            await self.store.reject(r, str(error))
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

    async def _run(self, r: RunRequest) -> RunResult:
        if r.workflow_version != WORKFLOW_VERSION or r.kind not in ("analyze", "recover"):
            raise AnalysisUnsafe("P3_RUN_NOT_AVAILABLE")
        await self.store.session.check()
        async with await open_async(self.store.settings) as db:
            cur = await db.execute(
                """SELECT t.normalized_request,t.state,s.state AS source_state
            FROM business.business_tasks t JOIN business.p3_task_sources b ON b.task_id=t.id
            JOIN business.business_tasks s ON s.id=b.source_task_id
            WHERE t.id=%s AND t.organization_id=%s AND t.shop_id=%s AND t.workflow_version=%s""",
                (r.task_id, r.organization_id, r.shop_id, WORKFLOW_VERSION),
            )
            task = await cur.fetchone()
        if not task:
            raise AnalysisUnsafe("P3_TASK_MISSING")
        if task["source_state"] != "completed":
            if task["source_state"] in ("failed", "needs_attention"):
                raise PlanRejected("DATA_INCOMPLETE")
            return RunResult("retry", 1)
        expected = {
            "workflow_version": WORKFLOW_VERSION,
            "task_id": str(r.task_id),
            "request_hash": facts_hash(task["normalized_request"]),
        }

        def bound(state: ApprovalState) -> None:
            if any(state.get(k) != v for k, v in expected.items()):
                raise AnalysisUnsafe("P3_CHECKPOINT_UNSAFE")

        async def prepare(state: ApprovalState) -> ApprovalState:
            bound(state)
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
                AND t.id=a.task_id AND a.plan_id=%s AND a.plan_hash=%s AND a.plan_version=%s""",
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
            # 固定唯一位置。callback/Command的值并非授权；A02才消费PG决定。
            interrupt(
                {
                    "approval_id": state["approval_id"],
                    "plan_id": state["plan_id"],
                    "plan_hash": state["plan_hash"],
                    "plan_version": state["plan_version"],
                }
            )
            raise AnalysisUnsafe("P3_DECISION_NOT_IMPLEMENTED")

        async def unavailable(state: ApprovalState) -> ApprovalState:
            bound(state)
            raise AnalysisUnsafe("P3_EXECUTION_NOT_IMPLEMENTED")

        async def finish(state: ApprovalState) -> ApprovalState:
            bound(state)
            return {}

        graph = StateGraph(ApprovalState)
        graph.add_node("prepare_approval", prepare)
        graph.add_node("wait_approval", wait)
        graph.add_node("revalidate", unavailable)
        graph.add_node("execute", unavailable)
        graph.add_node("finish", finish)
        graph.add_edge(START, "prepare_approval")
        graph.add_conditional_edges(
            "prepare_approval",
            lambda state: (
                "wait_approval" if state.get("outcome") == "awaiting_approval" else "finish"
            ),
        )
        graph.add_edge("wait_approval", "revalidate")
        graph.add_edge("revalidate", "execute")
        graph.add_edge("execute", "finish")
        graph.add_edge("finish", END)
        config: RunnableConfig = {"configurable": {"thread_id": r.thread_id}, "recursion_limit": 10}
        async with checkpointer(self.store.settings) as saver:
            compiled = graph.compile(checkpointer=saver)
            checkpoint = await compiled.aget_state(config)
            if checkpoint.created_at is None:
                if task["state"] != "queued" or r.kind != "analyze":
                    raise AnalysisUnsafe("P3_CHECKPOINT_UNSAFE")
                payload: Any = expected
            else:
                values = checkpoint.values
                if not isinstance(values, dict) or any(
                    values.get(k) != v for k, v in expected.items()
                ):
                    raise AnalysisUnsafe("P3_CHECKPOINT_UNSAFE")
                if not checkpoint.next:
                    if values.get("outcome") == "source_pending":
                        # 依赖源分析的job仍未结束：新P3首次图不能伪造完成后重启START。
                        raise AnalysisUnsafe("P3_SOURCE_DEPENDENCY_NOT_READY")
                    return RunResult()
                payload = None
            await self.hook("before_graph")
            result = await compiled.ainvoke(payload, config, durability="sync")
            snapshot = await compiled.aget_state(config)
            await self.hook("checkpoint_persisted")
            if snapshot.next == ("wait_approval",) and result.get("__interrupt__"):
                return RunResult("interrupted")
            if not snapshot.next and result.get("outcome") == "no_action":
                return RunResult()
            raise AnalysisUnsafe("P3_GRAPH_STATE_UNSAFE")
