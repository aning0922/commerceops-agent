"""P4固定100入站/20分析/空闲与忙时恢复调度；真实PG与离线SDK，无外部调用。"""

import asyncio
import json
import math
import platform
import signal
import tempfile
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import lark_oapi as lark  # type: ignore[import-untyped]
import psycopg
from commerceops.adapters.feishu.business_gateway import BusinessGateway
from commerceops.adapters.feishu.contracts import ProbePolicy
from commerceops.application.commerce.inventory_facts import InventoryReport
from commerceops.application.runner import RunRequest, RunResult
from commerceops.entrypoints.database import grant_runtime, migrate, setup_checkpointer
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.repository import TaskRepository, TaskScope
from commerceops.infrastructure.worker import Worker
from commerceops.infrastructure.worker_lock import WorkerSession
from lark_oapi.ws.pb.pbbp2_pb2 import Frame  # type: ignore[import-untyped]
from psycopg import sql

from tests.inventory_support import InventoryProcess
from tests.p3_support import P3Fixture, initialize_p3
from tests.p4_pending_performance import busy_pending, idle_pending
from tests.test_feishu_sdk import frame
from tests.test_p4_gateway_pg import service

ANALYSIS_SAMPLE_IDS = tuple(f"p4-baseline-{n:02d}" for n in range(1, 21))


def percentile95(values: list[float]) -> float:
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


async def inbound(f: P3Fixture) -> dict[str, Any]:
    store = service(f)
    policy = ProbePolicy(
        f.inventory.data.app,
        f.inventory.data.tenant,
        "p4-synthetic-bot",
        frozenset({"p4-synthetic-user"}),
        frozenset(),
    )
    client = lark.ws.Client(
        policy.app_id, "REDACTED", event_handler=BusinessGateway(store, policy).dispatcher()
    )
    replies: list[bytes] = []

    async def write(data: bytes) -> None:
        replies.append(data)

    client._write_message = write
    times: list[float] = []
    try:
        for _ in range(100):
            unique = uuid4().hex
            payload = {
                "schema": "2.0",
                "header": {
                    "event_id": "event-" + unique,
                    "event_type": "im.message.receive_v1",
                    "app_id": policy.app_id,
                    "tenant_key": policy.tenant_key,
                },
                "event": {
                    "sender": {
                        "sender_type": "user",
                        "tenant_key": policy.tenant_key,
                        "sender_id": {"open_id": "p4-synthetic-user"},
                    },
                    "message": {
                        "message_id": "message-" + unique,
                        "chat_type": "p2p",
                        "chat_id": "p4-synthetic-chat",
                        "message_type": "text",
                        "content": json.dumps({"text": "分析库存并生成补货建议"}),
                    },
                },
            }
            started = time.perf_counter()
            await client._handle_data_frame(frame(payload))
            times.append(time.perf_counter() - started)
            reply = Frame()
            reply.ParseFromString(replies[-1])
            assert json.loads(reply.payload)["code"] == 200
        with connect(f.config.database) as db:
            row = db.execute(
                "SELECT count(*) AS n FROM business.inbox_events WHERE source='feishu_business'"
            ).fetchone()
            assert row and row["n"] == 100 and len(replies) == 100
        value = percentile95(times)
        assert value < 1
        return {
            "n": 100,
            "p95_seconds": value,
            "max_seconds": max(times),
            "commit_and_sdk_ack_verified": True,
            "platform_network_included": False,
        }
    finally:
        client._cache._cron.cancel()
        await asyncio.gather(client._cache._cron, return_exceptions=True)


async def analysis(f: P3Fixture) -> dict[str, Any]:
    times: list[float] = []
    samples: list[dict[str, Any]] = []
    gold = json.loads(Path("tests/fixtures/commerce/inventory-v1/goldens.json").read_text())[
        "expectations"
    ]["baseline"]
    for sample_id in ANALYSIS_SAMPLE_IDS:
        task, job = f.inventory.create("baseline")
        started = time.perf_counter()
        child = InventoryProcess(f.inventory)
        try:
            child.until("started")
            end = time.monotonic() + 8
            while time.monotonic() < end:
                with connect(f.config.database) as db:
                    status = db.execute(
                        "SELECT status FROM business.jobs WHERE id=%s", (job,)
                    ).fetchone()
                assert status and status["status"] != "dead"
                if status["status"] == "done":
                    break
                await asyncio.sleep(0.01)
            else:
                raise AssertionError("bounded analysis deadline")
            child.process.send_signal(signal.SIGTERM)
            child.until("stopped")
            assert child.process.wait(timeout=8) == 0
        finally:
            child.close()
        times.append(time.perf_counter() - started)
        assert f.inventory.counts(task) == (1, 1)
        with connect(f.config.database) as db:
            saved = db.execute(
                """SELECT r.report,t.state FROM business.analysis_reports r
                JOIN business.business_tasks t ON t.id=r.task_id WHERE t.id=%s""",
                (task,),
            ).fetchone()
            assert saved and saved["state"] == "completed"
            report = InventoryReport.model_validate_json(json.dumps(saved["report"]))
            assert report.complete and report.source_complete and len(report.items) == 1
            actual = report.items[0].model_dump(mode="json")
            assert {key: actual[key] for key in gold} == gold
            samples.append(
                {
                    "sample_id": sample_id,
                    "complete": True,
                    "gold_match": True,
                    "facts_hash": report.facts_hash,
                }
            )
    value = percentile95(times)
    assert value < 10
    return {
        "n": 20,
        "fixture": "inventory-v1/baseline",
        "p95_seconds": value,
        "max_seconds": max(times),
        "queue_depth": 1,
        "warmup_excluded": False,
        "samples": samples,
        "worker_start_and_stop_included": True,
        "provider_calls": 0,
    }


async def recovery(f: P3Fixture) -> dict[str, Any]:
    session = WorkerSession(f.config.database, f.inventory.data.organization)
    await session.start()
    calls: list[float] = []
    starts: list[float] = []
    ends: list[float] = []
    stop = asyncio.Event()

    class BusyRunner:
        workflow_versions = frozenset({"g1-fixture-v1"})

        async def run(self, request: RunRequest) -> RunResult:
            starts.append(time.perf_counter())
            await asyncio.sleep(1.2)
            ends.append(time.perf_counter())
            return RunResult()

    async def scan() -> None:
        calls.append(time.perf_counter())
        if len(calls) == 2:
            with connect(f.config.database) as db:
                TaskRepository(
                    db, TaskScope(f.inventory.data.organization, f.inventory.data.shop)
                ).enqueue(
                    f.inventory.data.task, "analyze", "p4-perf-busy:" + uuid4().hex, "technical"
                )
        if ends:
            stop.set()

    await Worker(
        session,
        BusyRunner(),
        reconcile=scan,
        recovery_scan_seconds=1,
        poll_seconds=0.02,
        heartbeat_seconds=0.1,
    ).run(stop)
    assert len(calls) == 3 and len(starts) == len(ends) == 1
    gap = calls[1] - calls[0]
    delay = calls[-1] - ends[0]
    assert gap <= 30 and delay < 1
    assert not any(starts[0] < point < ends[0] for point in calls)
    return {
        "idle_scan_config_seconds": 1,
        "idle_observed_gap_seconds": gap,
        "idle_bound_seconds": 30,
        "busy_hold_seconds": ends[0] - starts[0],
        "busy_next_point_delay_seconds": delay,
        "scan_during_busy": False,
    }


def main() -> None:
    settings = DatabaseSettings()
    assert settings.runtime_password_file
    report: dict[str, Any] = {
        "source_mode": "mock",
        "model_mode": "not_used",
        "approval_mode": "simulated_feishu",
        "machine": platform.machine(),
        "system": platform.system(),
        "python": platform.python_version(),
        "real_platform_calls": 0,
        "provider_calls": 0,
    }
    with (
        psycopg.connect(**settings.kwargs(), autocommit=True) as admin,
        tempfile.TemporaryDirectory(prefix="p4-perf-") as directory,
    ):
        for label, operation in (
            ("inbound", inbound),
            ("analysis", analysis),
            ("recovery", recovery),
            ("pending_idle", idle_pending),
            ("pending_busy", busy_pending),
        ):
            name = "p4_perf_" + uuid4().hex
            owner = settings.model_copy(update={"name": name})
            app = owner.model_copy(
                update={"user": "commerceops_app", "password_file": settings.runtime_password_file}
            )
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
            try:
                migrate(owner)
                asyncio.run(setup_checkpointer(owner))
                grant_runtime(owner)
                private = Path(directory) / label
                private.mkdir(mode=0o700)
                fixture = initialize_p3(owner, app, private)
                try:
                    report[label] = asyncio.run(operation(fixture))
                finally:
                    fixture.client.close()
            finally:
                admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
