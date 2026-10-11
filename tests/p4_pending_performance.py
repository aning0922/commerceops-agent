"""固定idle/busy真实官方PG interrupt调度补证；只使用自有测试库。"""

import asyncio
import time
from typing import Any
from uuid import UUID

from commerceops.application.runner import RunRequest, RunResult
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.inventory_repository import InventoryStore
from commerceops.infrastructure.replenishment_repository import ApprovalStore
from commerceops.infrastructure.worker import Worker
from commerceops.infrastructure.worker_lock import WorkerSession, confirm_termination
from commerceops.workflows.inventory_analysis import InventoryRunner, MockCollectorFactory
from commerceops.workflows.replenishment import ApprovalRunner

from tests.inventory_support import DIRECTORY
from tests.p3_support import P3Fixture, P3Process


async def idle_pending(f: P3Fixture) -> dict[str, Any]:
    task = UUID(f.create(f.new_cycle())["task_id"])
    old = P3Process(f, "worker", {"task_id": str(task)}, "before_ready")
    started = old.until("started")
    old.until("before_ready")
    with connect(f.config.database) as db:
        before = db.execute(
            "SELECT ready_at FROM business.approvals WHERE task_id=%s", (task,)
        ).fetchone()
        assert before and before["ready_at"] is None
    old.kill_reap()
    await confirm_termination(
        f.config.database, started["owner"], "p4 pending perf old child SIGKILL reaped"
    )
    session = WorkerSession(f.config.database, f.inventory.data.organization)
    await session.start()
    approval = ApprovalRunner(
        ApprovalStore(f.config, session), collector_factory=MockCollectorFactory(DIRECTORY)
    )
    stop = asyncio.Event()
    samples: list[float] = []
    begin = time.perf_counter()

    async def scan() -> None:
        await approval.reconcile()
        with connect(f.config.database) as db:
            ready = db.execute(
                "SELECT ready_at FROM business.approvals WHERE task_id=%s", (task,)
            ).fetchone()
        assert ready and ready["ready_at"] is not None
        samples.append(time.perf_counter() - begin)
        stop.set()

    await Worker(
        session,
        approval,
        reconcile=scan,
        recovery_scan_seconds=1,
        poll_seconds=0.02,
        heartbeat_seconds=0.1,
    ).run(stop)
    assert len(samples) == 1 and samples[0] <= 30
    return {
        "old_pid_reaped": True,
        "explicit_termination_confirmed": True,
        "actual_pending_interrupt_ready": True,
        "delay_seconds": samples[0],
        "scan_config_seconds": 1,
    }


async def busy_pending(f: P3Fixture) -> dict[str, Any]:
    task = UUID(f.create(f.new_cycle())["task_id"])
    session = WorkerSession(f.config.database, f.inventory.data.organization)
    await session.start()
    stop = asyncio.Event()
    marks: dict[str, float] = {}
    scans: list[float] = []

    class BeforeReadyGap(Exception):
        pass

    async def hook(point: str) -> None:
        if point == "before_ready":
            with connect(f.config.database) as db:
                row = db.execute(
                    "SELECT ready_at FROM business.approvals WHERE task_id=%s", (task,)
                ).fetchone()
            assert row and row["ready_at"] is None
            marks["pending"] = time.perf_counter()
            raise BeforeReadyGap()

    approval = ApprovalRunner(
        ApprovalStore(f.config, session),
        collector_factory=MockCollectorFactory(DIRECTORY),
        hook=hook,
    )
    analysis = InventoryRunner(
        InventoryStore(f.config.database, session), MockCollectorFactory(DIRECTORY)
    )

    class Router:
        workflow_versions = analysis.workflow_versions | approval.workflow_versions

        async def run(self, request: RunRequest) -> RunResult:
            if request.workflow_version in analysis.workflow_versions:
                return await analysis.run(request)
            try:
                return await approval.run(request)
            except BeforeReadyGap:
                # 已持久的真实wait interrupt，暂缓ready模拟同Graph调用尚未结束。
                await asyncio.sleep(1.2)
                marks["finished"] = time.perf_counter()
                return RunResult("retry", 100)

    async def scan() -> None:
        scans.append(time.perf_counter())
        await approval.reconcile()
        if "finished" in marks:
            with connect(f.config.database) as db:
                row = db.execute(
                    "SELECT ready_at FROM business.approvals WHERE task_id=%s", (task,)
                ).fetchone()
            assert row and row["ready_at"] is not None
            marks["ready"] = time.perf_counter()
            stop.set()

    await Worker(
        session,
        Router(),
        reconcile=scan,
        recovery_scan_seconds=1,
        poll_seconds=0.02,
        heartbeat_seconds=0.1,
    ).run(stop)
    assert set(marks) == {"pending", "finished", "ready"}
    assert not any(marks["pending"] < point < marks["finished"] for point in scans)
    delay = marks["ready"] - marks["finished"]
    assert delay <= 30
    return {
        "actual_pending_interrupt_ready": True,
        "busy_hold_seconds": marks["finished"] - marks["pending"],
        "next_point_delay_seconds": delay,
        "scan_during_busy": False,
        "scan_config_seconds": 1,
    }
