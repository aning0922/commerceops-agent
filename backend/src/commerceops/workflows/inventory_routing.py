"""同Worker固定意图Graph；receipt优先，未知调用不重发；无业务执行。"""

import asyncio
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from commerceops.adapters.commerce.deepseek_routing import DeepSeekRoutingPort
from commerceops.application.commerce.intent_task import INTENT_WORKFLOW, IntentTaskRequest
from commerceops.application.commerce.inventory_routing import ModelRoute
from commerceops.application.model_explanation.contracts import ModelReply
from commerceops.application.runner import RunRequest, RunResult
from commerceops.infrastructure.checkpoint import checkpointer
from commerceops.infrastructure.intent_repository import IntentStore
from commerceops.infrastructure.inventory_repository import AnalysisUnsafe
from commerceops.infrastructure.model_budget_repository import PersistentAdmission
from commerceops.infrastructure.worker_lock import open_async
from commerceops.workflows.report_explanation import Hook, ProviderFactory, no_hook


class IntentState(TypedDict, total=False):
    workflow_version: str
    task_id: str
    logical_key: str


class IntentRunner:
    workflow_versions = frozenset({INTENT_WORKFLOW})

    def __init__(self, store: IntentStore, factory: ProviderFactory, *, hook: Hook = no_hook):
        self.store, self.factory, self.hook = store, factory, hook
        self.active = 0

    async def load(self, r: RunRequest) -> tuple[dict[str, Any], IntentTaskRequest]:
        async with await open_async(self.store.settings) as db, db.transaction():
            task, req, _ = await self.store.guard(db, r)
            return task, req

    async def save_cached(self, r: RunRequest, value: dict[str, Any]) -> None:
        import json

        from commerceops.infrastructure.explanation_repository import decode

        proposal = ModelRoute.model_validate_json(json.dumps(value["proposal"]))
        reply = decode(
            {
                "metadata": value["metadata"],
                "reference_ids": None,
                "lines": [],
                "facts_hash": "",
                "narrative_mode": "template",
                "binding_mode": "standalone",
                "summary": "",
            }
        ).metadata
        await self.store.save(r, proposal, reply)

    async def run(self, r: RunRequest) -> RunResult:
        if self.active:
            raise AnalysisUnsafe("GLOBAL_GRAPH_SLOT_BUSY")
        self.active += 1
        before = asyncio.all_tasks()
        try:
            if await self.store.existing(r) is not None:
                await self.hook("persistent_replay")
                return RunResult()
            task, req = await self.load(r)
            recovery = PersistentAdmission(self.store, r)
            if await recovery.recover_prior():
                await self.store.mark(r, "analyzing")
                if recovery.cached is not None:
                    await self.save_cached(r, recovery.cached)
                else:
                    await self.store.save(
                        r,
                        ModelRoute(intent="clarify", evidence_mode="not_used"),
                        ModelReply(
                            error_code="TRANSPORT_ERROR",
                            prompt_version=req.prompt_version,
                            stop_required=True,
                        ),
                    )
                await self.hook("prior_request_recovered_without_http")
                return RunResult()
            if r.kind not in ("analyze", "recover") or task["state"] not in ("queued", "analyzing"):
                raise AnalysisUnsafe("INTENT_STATE_INVALID")
            expected = {
                "workflow_version": INTENT_WORKFLOW,
                "task_id": str(r.task_id),
                "logical_key": req.logical_key,
            }

            async def route(state: IntentState) -> IntentState:
                if any(state.get(k) != v for k, v in expected.items()):
                    raise AnalysisUnsafe("INTENT_CHECKPOINT_UNSAFE")
                await self.store.mark(r, "analyzing")
                _, current = await self.load(r)
                admission = PersistentAdmission(self.store, r)
                port = DeepSeekRoutingPort(
                    self.factory.completion(current, admission), current.facts_hash
                )
                proposal = await port.route(current.input.text)
                reply = port.reply
                await self.hook("provider_returned")
                reply = await admission.settle(reply)
                await self.hook("call_observation_committed")
                if admission.cached is not None:
                    await self.save_cached(r, admission.cached)
                elif admission.prior_uncertain:
                    await self.store.save(
                        r,
                        ModelRoute(intent="clarify", evidence_mode="not_used"),
                        ModelReply(
                            error_code="TRANSPORT_ERROR",
                            prompt_version=current.prompt_version,
                            stop_required=True,
                        ),
                    )
                else:
                    await self.store.save(r, proposal, reply)
                await self.hook("intent_committed")
                return {}

            graph = StateGraph(IntentState)
            graph.add_node("route", route)
            graph.add_edge(START, "route")
            graph.add_edge("route", END)
            config: RunnableConfig = {
                "configurable": {"thread_id": r.thread_id},
                "recursion_limit": 5,
            }
            async with checkpointer(self.store.settings) as saver:
                compiled = graph.compile(checkpointer=saver)
                state = await compiled.aget_state(config)
                if state.created_at is None:
                    if task["state"] != "queued" or r.kind != "analyze":
                        raise AnalysisUnsafe("INTENT_CHECKPOINT_UNSAFE")
                    initial: Any = expected
                else:
                    if (
                        not isinstance(state.values, dict)
                        or any(state.values.get(k) != v for k, v in expected.items())
                        or state.next != ("route",)
                    ):
                        raise AnalysisUnsafe("INTENT_CHECKPOINT_UNSAFE")
                    initial = None
                await compiled.ainvoke(initial, config)
            if await self.store.existing(r) is None:
                raise AnalysisUnsafe("INTENT_RESULT_MISSING")
            return RunResult()
        except AnalysisUnsafe:
            async with await open_async(self.store.settings) as db, db.transaction():
                task, _, _ = await self.store.guard(db, r, authorize=False)
                if task["state"] == "completed":
                    raise
            await self.store.mark(r, "needs_attention", "INTENT_UNSAFE")
            return RunResult()
        except Exception:
            if await self.store.existing(r) is not None:
                return RunResult()
            if r.attempt >= 3:
                await self.store.mark(r, "needs_attention", "INTENT_STORAGE_FAILURE")
                return RunResult()
            raise
        finally:
            pending = asyncio.all_tasks() - before
            while pending:
                try:
                    await asyncio.wait(pending)
                except asyncio.CancelledError:
                    pass
                pending = {t for t in pending if not t.done()}
            self.active -= 1
