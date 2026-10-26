"""单Worker/单Graph内analysis-only工作流；PG业务回执优先于checkpoint重放。"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from commerceops.adapters.commerce.mock import Fixture, MockCommerce
from commerceops.application.commerce.analysis_task import (
    WORKFLOW_VERSION,
    InventoryTaskRequest,
    WooInventoryTaskRequest,
    parse_analysis_request,
)
from commerceops.application.commerce.collection import InventoryCollector
from commerceops.application.commerce.inventory_analysis import (
    InventoryAnalysisError,
    analyze_inventory,
)
from commerceops.application.commerce.inventory_facts import OpenWorkItemInput
from commerceops.application.runner import RunRequest, RunResult
from commerceops.domain.commerce_values import facts_hash, utc_time
from commerceops.domain.inventory_rules import RuleParameters
from commerceops.infrastructure.checkpoint import checkpointer
from commerceops.infrastructure.inventory_repository import AnalysisUnsafe, InventoryStore
from commerceops.infrastructure.repository import PersistenceConflict

Hook = Callable[[str], Awaitable[None]]
CollectorFactory = Callable[[InventoryTaskRequest], InventoryCollector]
WooCollectorFactory = Callable[[WooInventoryTaskRequest], InventoryCollector]


async def no_hook(point: str) -> None:
    pass


class AnalysisState(TypedDict, total=False):
    workflow_version: str
    task_id: str
    request_hash: str
    report_ref: str


class InventoryRunner:
    workflow_versions = frozenset({WORKFLOW_VERSION})

    def __init__(
        self,
        store: InventoryStore,
        collector_factory: CollectorFactory,
        *,
        hook: Hook = no_hook,
        woo_collector_factory: WooCollectorFactory | None = None,
    ):
        self.store, self.collector_factory, self.hook = store, collector_factory, hook
        self.woo_collector_factory = woo_collector_factory
        self.active = 0

    async def run(self, r: RunRequest) -> RunResult:
        if self.active:
            raise AnalysisUnsafe("ANALYSIS_GRAPH_SLOT_BUSY")
        self.active += 1
        before = asyncio.all_tasks()
        try:
            return await self._run(r)
        except (AnalysisUnsafe, PersistenceConflict) as error:
            task = await self.store.load(r, authorize=False)
            if task["state"] == "completed":
                raise AnalysisUnsafe("ANALYSIS_RESULT_CONFLICT") from None
            code = (
                "ANALYSIS_SOURCE_SCOPE_MISMATCH"
                if isinstance(error, AnalysisUnsafe)
                and error.args == ("ANALYSIS_SOURCE_SCOPE_MISMATCH",)
                else "ANALYSIS_CHECKPOINT_UNSAFE"
            )
            await self.store.mark(r, "needs_attention", code)
            return RunResult()
        except (ValueError, InventoryAnalysisError):
            await self.store.mark(r, "failed", "ANALYSIS_INPUT_INVALID")
            return RunResult()
        except Exception:
            # 业务已提交而回执/检查点调用失败时，仍只复用校验过的持久结果。
            receipt = await self.store.existing(r, authorize=False)
            if receipt is not None:
                return RunResult()
            if r.attempt >= 3:
                await self.store.mark(r, "needs_attention", "ANALYSIS_STORAGE_FAILURE")
                return RunResult()
            raise
        finally:
            # 沿用P1保守取消合同：本调用期间新建的库任务未退出时不释放runner槽。
            pending = asyncio.all_tasks() - before
            while pending:
                try:
                    await asyncio.wait(pending)
                except asyncio.CancelledError:
                    pass
                pending = {task for task in pending if not task.done()}
            self.active -= 1

    async def _run(self, r: RunRequest) -> RunResult:
        existing = await self.store.existing(r, authorize=False)
        if existing is not None:
            await self.hook("persistent_replay")
            return RunResult()
        task = await self.store.load(r)
        if r.kind not in ("analyze", "recover") or task["state"] not in ("queued", "analyzing"):
            raise AnalysisUnsafe("ANALYSIS_STATE_INVALID")
        request = parse_analysis_request(task["normalized_request"])
        digest = facts_hash(task["normalized_request"])
        expected = {
            "workflow_version": WORKFLOW_VERSION,
            "task_id": str(r.task_id),
            "request_hash": digest,
        }

        async def analyze(state: AnalysisState) -> AnalysisState:
            if any(state.get(key) != value for key, value in expected.items()):
                raise AnalysisUnsafe("ANALYSIS_CHECKPOINT_UNSAFE")
            await self.store.mark(r, "analyzing")
            saved = await self.store.existing(r)
            if saved is not None:
                return {"report_ref": str(saved.report_id)}
            await self.hook("before_collection")
            if isinstance(request, WooInventoryTaskRequest):
                if self.woo_collector_factory is None:
                    raise ValueError("COMMERCE_SOURCE_UNAVAILABLE")
                collected = await self.woo_collector_factory(request).collect()
            else:
                collected = await self.collector_factory(request).collect()
            report = analyze_inventory(
                collected.data, RuleParameters(request.L, request.R, request.S)
            )
            persisted = await self.store.save(r, collected, report)
            await self.hook("report_committed")
            return {"report_ref": str(persisted.report_id)}

        graph = StateGraph(AnalysisState)
        graph.add_node("analyze", analyze)
        graph.add_edge(START, "analyze")
        graph.add_edge("analyze", END)
        config: RunnableConfig = {"configurable": {"thread_id": r.thread_id}, "recursion_limit": 5}
        async with checkpointer(self.store.settings) as saver:
            compiled = graph.compile(checkpointer=saver)
            checkpoint = await compiled.aget_state(config)
            if checkpoint.created_at is None:
                if task["state"] != "queued" or r.kind != "analyze":
                    raise AnalysisUnsafe("ANALYSIS_CHECKPOINT_UNSAFE")
                payload: Any = expected
            else:
                values = checkpoint.values
                if not isinstance(values, dict) or any(
                    values.get(k) != v for k, v in expected.items()
                ):
                    raise AnalysisUnsafe("ANALYSIS_CHECKPOINT_UNSAFE")
                if not checkpoint.next or checkpoint.next != ("analyze",):
                    raise AnalysisUnsafe("ANALYSIS_RESULT_MISSING")
                payload = None
            await compiled.ainvoke(payload, config)
        result = await self.store.existing(r, authorize=False)
        if result is None:
            raise AnalysisUnsafe("ANALYSIS_RESULT_MISSING")
        return RunResult()


class MockCollectorFactory:
    def __init__(self, directory: Path):
        self.directory = directory

    def __call__(self, request: InventoryTaskRequest) -> InventoryCollector:
        fixture = Fixture.load(self.directory, request.fixture_case)
        port = MockCommerce(fixture)
        # Fixture.load 已验证 manifest；自有 open_items 仍是只读观测。
        try:
            raw = json.loads((self.directory / "datasets.json").read_text())
            rows = raw["cases"][request.fixture_case]["open_items"]
            open_items = tuple(OpenWorkItemInput.model_validate(row) for row in rows)
            now = fixture.now
            if request.fixture_case == "dst":
                gold = json.loads((self.directory / "goldens.json").read_text())
                now = utc_time(gold["expectations"][request.fixture_case]["explicit_now"])
        except (OSError, ValueError, KeyError, TypeError):
            raise ValueError("ANALYSIS_FIXTURE_INVALID") from None
        return InventoryCollector(port, fixture.source, now, open_items=open_items)
