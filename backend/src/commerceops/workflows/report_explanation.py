"""显式P204说明子任务，新thread/version；同Worker串行，持久receipt优先。"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, TypedDict

import httpx
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from pydantic import SecretStr

from commerceops.adapters.model_explanation.deepseek import DeepSeekAdapter
from commerceops.application.commerce.explanation_task import (
    EXPLANATION_WORKFLOW,
    ExplanationTaskRequest,
)
from commerceops.application.commerce.intent_task import IntentTaskRequest
from commerceops.application.model_explanation.contracts import ReferenceIds
from commerceops.application.model_explanation.service import ModelExplanationService
from commerceops.application.runner import RunRequest, RunResult
from commerceops.infrastructure.checkpoint import checkpointer
from commerceops.infrastructure.explanation_repository import ExplanationStore
from commerceops.infrastructure.inventory_repository import AnalysisUnsafe
from commerceops.infrastructure.model_budget_repository import PRICING, PersistentAdmission
from commerceops.infrastructure.model_probe_config import read_probe_key
from commerceops.infrastructure.p204_token_counter import VerifiedTextCounter
from commerceops.workflows.inventory_analysis import InventoryRunner

Hook = Callable[[str], Awaitable[None]]


async def no_hook(point: str) -> None:
    pass


class ProviderFactory:
    def __init__(
        self,
        *,
        allow_actual: bool = False,
        key_file: Path | None = None,
        offline_transport: httpx.MockTransport | None = None,
    ):
        self.allow_actual = allow_actual
        self.key_file = key_file
        self.offline_transport = offline_transport
        self.counter = VerifiedTextCounter()

    def completion(
        self, req: ExplanationTaskRequest | IntentTaskRequest, admission: PersistentAdmission
    ) -> DeepSeekAdapter | None:
        if req.evidence_mode == "template":
            return None
        if req.evidence_mode == "actual_provider":
            if not self.allow_actual or self.key_file is None:
                return None  # 默认不读取key、不network。
            # 仅Root批准实际入口时执行此分支；不把key/原始错误带入checkpoint/日志。
            api_key = read_probe_key(self.key_file)
            transport = None
        else:
            api_key = SecretStr("offline-only")
            transport = self.offline_transport
            if req.evidence_mode == "local_fault":

                def fault(request: httpx.Request) -> httpx.Response:
                    raise httpx.ReadTimeout("controlled local fault")

                transport = httpx.MockTransport(fault)
            if transport is None:
                return None
        return DeepSeekAdapter(
            api_key=api_key,
            token_counter=self.counter,
            admission=admission,
            pricing=PRICING,
            offline_transport=transport,
            prompt_version=req.prompt_version,
        )

    def service(
        self, req: ExplanationTaskRequest, admission: PersistentAdmission
    ) -> ModelExplanationService:
        return ModelExplanationService(self.completion(req, admission))


class ExplanationState(TypedDict, total=False):
    workflow_version: str
    task_id: str
    logical_key: str
    result_id: str


class ExplanationRunner:
    workflow_versions = frozenset({EXPLANATION_WORKFLOW})

    def __init__(self, store: ExplanationStore, factory: ProviderFactory, *, hook: Hook = no_hook):
        self.store, self.factory, self.hook = store, factory, hook
        self.active = 0

    async def run(self, r: RunRequest) -> RunResult:
        if self.active:
            raise AnalysisUnsafe("EXPLANATION_GRAPH_SLOT_BUSY")
        self.active += 1
        before = asyncio.all_tasks()
        try:
            return await self._run(r)
        except AnalysisUnsafe:
            task, _, _ = await self.store.load(r, authorize=False)
            if task["state"] == "completed":
                raise
            await self.store.mark(r, "needs_attention", "EXPLANATION_UNSAFE")
            return RunResult()
        except Exception:
            if await self.store.existing(r) is not None:
                return RunResult()
            if r.attempt >= 3:
                await self.store.mark(r, "needs_attention", "EXPLANATION_STORAGE_FAILURE")
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

    async def _run(self, r: RunRequest) -> RunResult:
        if await self.store.existing(r) is not None:
            await self.hook("persistent_replay")
            return RunResult()
        task, req, report = await self.store.load(r)
        recovery = PersistentAdmission(self.store, r)
        if await recovery.recover_prior():
            await self.store.mark(r, "analyzing")
            if recovery.cached is not None:
                fallback = recovery.cached
            else:
                fallback = await ModelExplanationService().explain(
                    report, reference_ids=ReferenceIds(str(req.snapshot_id), str(req.report_id))
                )
                fallback = replace(
                    fallback,
                    metadata=replace(
                        fallback.metadata, error_code="TRANSPORT_ERROR", stop_required=True
                    ),
                )
            await self.store.save(r, fallback)
            await self.hook("prior_request_recovered_without_http")
            return RunResult()
        if r.kind not in ("analyze", "recover") or task["state"] not in ("queued", "analyzing"):
            raise AnalysisUnsafe("EXPLANATION_STATE_INVALID")
        expected = {
            "workflow_version": EXPLANATION_WORKFLOW,
            "task_id": str(r.task_id),
            "logical_key": req.logical_key,
        }

        async def explain(state: ExplanationState) -> ExplanationState:
            if any(state.get(key) != value for key, value in expected.items()):
                raise AnalysisUnsafe("EXPLANATION_CHECKPOINT_UNSAFE")
            await self.store.mark(r, "analyzing")
            _, current, current_report = await self.store.load(r)
            admission = PersistentAdmission(self.store, r)
            result = await self.factory.service(current, admission).explain(
                current_report,
                reference_ids=ReferenceIds(str(current.snapshot_id), str(current.report_id)),
            )
            await self.hook("provider_returned")
            if admission.cached is not None:
                result = admission.cached
            elif admission.prior_uncertain:
                result = replace(
                    result,
                    metadata=replace(
                        result.metadata, error_code="TRANSPORT_ERROR", stop_required=True
                    ),
                )
            result = replace(result, metadata=await admission.settle(result.metadata))
            await self.hook("call_observation_committed")
            saved = await self.store.save(r, result)
            await self.hook("explanation_committed")
            return {"result_id": str(saved.result_id)}

        graph = StateGraph(ExplanationState)
        graph.add_node("explain", explain)
        graph.add_edge(START, "explain")
        graph.add_edge("explain", END)
        config: RunnableConfig = {"configurable": {"thread_id": r.thread_id}, "recursion_limit": 5}
        async with checkpointer(self.store.settings) as saver:
            compiled = graph.compile(checkpointer=saver)
            state = await compiled.aget_state(config)
            if state.created_at is None:
                if task["state"] != "queued" or r.kind != "analyze":
                    raise AnalysisUnsafe("EXPLANATION_CHECKPOINT_UNSAFE")
                initial: Any = expected
            else:
                if (
                    not isinstance(state.values, dict)
                    or any(state.values.get(k) != v for k, v in expected.items())
                    or state.next != ("explain",)
                ):
                    raise AnalysisUnsafe("EXPLANATION_CHECKPOINT_UNSAFE")
                initial = None
            await compiled.ainvoke(initial, config)
        if await self.store.existing(r) is None:
            raise AnalysisUnsafe("EXPLANATION_RESULT_MISSING")
        return RunResult()


class InventoryCompositeRunner:
    def __init__(
        self,
        analysis: InventoryRunner,
        explanation: ExplanationRunner,
        intent: Any = None,
        approval: Any = None,
    ):
        self.analysis, self.explanation = analysis, explanation
        self.workflow_versions = analysis.workflow_versions | explanation.workflow_versions
        self.intent = intent
        self.approval = approval
        if intent is not None:
            self.workflow_versions |= intent.workflow_versions
        if approval is not None:
            self.workflow_versions |= approval.workflow_versions
        self.active = 0

    async def run(self, r: RunRequest) -> RunResult:
        if self.active:
            raise AnalysisUnsafe("GLOBAL_GRAPH_SLOT_BUSY")
        self.active += 1
        try:
            runner = (
                self.explanation if r.workflow_version == EXPLANATION_WORKFLOW else self.analysis
            )
            if self.intent is not None and r.workflow_version in self.intent.workflow_versions:
                runner = self.intent
            if self.approval is not None and r.workflow_version in self.approval.workflow_versions:
                runner = self.approval
            return await runner.run(r)
        finally:
            self.active -= 1
