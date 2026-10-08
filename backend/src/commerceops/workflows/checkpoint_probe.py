"""G2 技术 Graph：一个固定 interrupt，无模型、正式审批或库存副作用。"""

from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from commerceops.application.runner import RunRequest, RunResult
from commerceops.infrastructure.checkpoint import checkpointer
from commerceops.infrastructure.checkpoint_probe import ProbeStore, ProbeUnsafe
from commerceops.infrastructure.repository import PersistenceConflict

WORKFLOW_VERSION = "p104-checkpoint-v1"
Hook = Callable[[str, dict[str, Any]], Awaitable[None]]


class ProbeState(TypedDict, total=False):
    schema_version: int
    workflow_version: str
    task_id: str
    request_hash: str
    decision_ref: str
    approved: bool
    result_ref: str
    outcome: str
    approval_mode: str


async def no_hook(event: str, data: dict[str, Any]) -> None:
    pass


class ProbeRunner:
    workflow_versions = frozenset({WORKFLOW_VERSION})

    def __init__(self, store: ProbeStore, *, hook: Hook = no_hook):
        self.store = store
        self.hook = hook
        self.active = 0

    async def run(self, request: RunRequest) -> RunResult:
        if self.active:
            raise ProbeUnsafe("global graph slot already occupied")
        self.active += 1
        try:
            return await self._run(request)
        except (ProbeUnsafe, PersistenceConflict):
            await self.store.mark(request, "needs_attention")
            return RunResult()
        finally:
            self.active -= 1
            await self.hook("runner_left", {"task": str(request.task_id), "active": self.active})

    async def _run(self, r: RunRequest) -> RunResult:
        row = await self.store.load(r)
        if r.workflow_version != WORKFLOW_VERSION or row["status"] == "needs_attention":
            raise ProbeUnsafe("workflow version/status unsupported")
        hashed = row["request_hash"]

        async def prepare(state: ProbeState) -> ProbeState:
            await self.hook("prepare_entered", {"task": str(r.task_id)})
            return {"outcome": "prepared"}

        async def wait_decision(state: ProbeState) -> ProbeState:
            # 固定位置、固定一个 interrupt；本节点从头重跑。所有节点为 async，
            # 不让同步节点/to_thread 的后台线程在取消后继续业务写入。
            await self.hook("wait_entered", {"task": str(r.task_id)})
            ref = interrupt({"task_id": str(r.task_id), "workflow_version": WORKFLOW_VERSION,
                             "request_hash": hashed, "approval_mode": "simulated"})
            if not isinstance(ref, str):
                raise ProbeUnsafe("resume must contain only decision_ref")
            approved = await self.store.decision(r, ref, hashed)
            return {"decision_ref": ref, "approved": approved}

        async def execute(state: ProbeState) -> ProbeState:
            await self.hook("execute_entered", {"task": str(r.task_id)})
            if not state.get("approved"):
                return {"outcome": "rejected"}
            result = await self.store.receipt(r, hashed, state["decision_ref"])
            # 尚未返回节点输出，因此对应的 result_ref checkpoint 不可能已写。
            await self.hook("receipt_committed", {"task": str(r.task_id), "result_ref": result})
            return {"result_ref": result, "outcome": "receipt_saved"}

        graph = StateGraph(ProbeState)
        graph.add_node("prepare", prepare)
        graph.add_node("wait_decision", wait_decision)
        graph.add_node("execute", execute)
        graph.add_edge(START, "prepare")
        graph.add_edge("prepare", "wait_decision")
        graph.add_edge("wait_decision", "execute")
        graph.add_edge("execute", END)
        config: RunnableConfig = {"configurable": {"thread_id": r.thread_id}, "recursion_limit": 10}
        async with checkpointer(self.store.settings) as saver:
            compiled = graph.compile(checkpointer=saver)
            snapshot = await compiled.aget_state(config)
            receipt = await self.store.existing_receipt(r, hashed)
            payload: Any = None
            if snapshot.created_at is None:
                if row["started"] or receipt or r.kind != "analyze":
                    raise ProbeUnsafe("missing checkpoint after start or recovery request")
                await self.store.mark(r, "running", started=True)
                payload = {"schema_version": 1, "workflow_version": WORKFLOW_VERSION,
                           "task_id": str(r.task_id), "request_hash": hashed,
                           "approval_mode": "simulated"}
                action = "start"
            else:
                values = snapshot.values
                if not isinstance(values, dict) or any(values.get(k) != v for k, v in {
                    "schema_version": 1, "workflow_version": WORKFLOW_VERSION,
                    "task_id": str(r.task_id), "request_hash": hashed,
                    "approval_mode": "simulated",
                }.items()):
                    raise ProbeUnsafe("checkpoint identity/version mismatch")
                pending = [i for task in snapshot.tasks for i in task.interrupts]
                if pending:
                    expected = {"task_id": str(r.task_id), "workflow_version": WORKFLOW_VERSION,
                                "request_hash": hashed, "approval_mode": "simulated"}
                    if len(pending) != 1 or pending[0].value != expected or (
                        snapshot.next != ("wait_decision",) or receipt
                    ):
                        raise ProbeUnsafe("pending interrupt cannot be explained")
                    if row["decision_ref"] is None:
                        if r.kind == "resume":
                            return RunResult("retry", 1)
                        await self.store.mark(r, "waiting")
                        return RunResult("interrupted")
                    ref = str(row["decision_ref"])
                    if r.kind == "resume" and r.payload_ref != ref:
                        raise ProbeUnsafe("resume job differs from durable decision")
                    await self.store.decision(r, ref, hashed)
                    payload = Command(resume=ref)
                    action = "resume"
                elif snapshot.next:
                    if snapshot.next not in (("prepare",), ("wait_decision",), ("execute",)):
                        raise ProbeUnsafe("unknown unfinished node")
                    action = "continue"
                else:
                    if values.get("outcome") == "rejected" and receipt is None:
                        await self.store.mark(r, "finished")
                        return RunResult()
                    if not receipt or values.get("result_ref") != receipt:
                        raise ProbeUnsafe("finished checkpoint lacks matching receipt")
                    await self.store.mark(r, "finished")
                    return RunResult()
            await self.hook("invoke", {"task": str(r.task_id), "thread": r.thread_id,
                                       "action": action, "active": self.active})
            await compiled.ainvoke(payload, config=config, durability="sync")
            # 必须重新从真实 saver 读到中断 checkpoint 才能释放 Worker 槽。
            saved = await compiled.aget_state(config)
            pending = [i for task in saved.tasks for i in task.interrupts]
            if pending:
                if saved.next != ("wait_decision",) or len(pending) != 1:
                    raise ProbeUnsafe("unexpected saved interrupt")
                await self.store.mark(r, "waiting")
                await self.hook("interrupt_persisted", {"task": str(r.task_id),
                                                        "checkpoint": saved.config})
                # 决定可能先于 runner 观察中断到达；持久延期，不能将 resume 丢弃。
                current = await self.store.load(r)
                if current["decision_ref"] is not None:
                    return RunResult("retry", 1)
                return RunResult("interrupted")
            if saved.next:
                raise ProbeUnsafe("invoke returned unfinished graph")
            await self.store.mark(r, "finished")
            await self.hook("graph_finished", {"task": str(r.task_id), "values": saved.values})
            return RunResult()
