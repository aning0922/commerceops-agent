"""P203 自有真实 PG 与受控 Worker 证据；无模型、审批或生产资源。"""

import asyncio
import json
import os
import queue
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from commerceops.application.commerce.analysis_task import InventoryTaskRequest, TrustedReadIdentity
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.inventory_repository import create_analysis_task

from tests.pg_support import Seed, seed

DIRECTORY = Path(__file__).parent / "fixtures/commerce/inventory-v1"


@dataclass
class InventoryFixture:
    owner: DatabaseSettings
    app: DatabaseSettings
    data: Seed
    identity: TrustedReadIdentity

    def create(self, case: str = "baseline") -> tuple[UUID, UUID]:
        return create_analysis_task(
            self.app, self.identity, self.data.conversation, InventoryTaskRequest(fixture_case=case)
        )

    def row(self, task: UUID) -> dict[str, Any]:
        with connect(self.app) as db:
            row = db.execute(
                "SELECT * FROM business.business_tasks WHERE id=%s", (task,)
            ).fetchone()
            assert row
            return row

    def counts(self, task: UUID) -> tuple[int, int]:
        with connect(self.app) as db:
            snapshot = db.execute(
                "SELECT count(*) AS n FROM business.commerce_snapshots WHERE task_id=%s", (task,)
            ).fetchone()
            report = db.execute(
                "SELECT count(*) AS n FROM business.analysis_reports WHERE task_id=%s", (task,)
            ).fetchone()
            assert snapshot and report
            return snapshot["n"], report["n"]


def initialize(owner: DatabaseSettings, app: DatabaseSettings) -> InventoryFixture:
    with connect(owner) as db:
        data = seed(db)
        db.execute("UPDATE business.shops SET external_shop_key='demo' WHERE id=%s", (data.shop,))
        db.execute(
            "INSERT INTO business.principal_shop_scopes VALUES (%s,%s,%s,true)",
            (data.organization, data.shop, data.principal),
        )
        row = db.execute(
            "SELECT id FROM business.identities WHERE principal_id=%s", (data.principal,)
        ).fetchone()
        assert row
    identity = TrustedReadIdentity(row["id"], data.principal, data.organization, data.shop, 1)
    return InventoryFixture(owner, app, data, identity)


async def run_worker(
    f: InventoryFixture,
    job: UUID,
    *,
    hook: Any = None,
    store_hook: Any = None,
    factory: Any = None,
    expected_status: str = "done",
) -> None:
    from commerceops.infrastructure.inventory_repository import InventoryStore, no_store_hook
    from commerceops.infrastructure.worker import Worker
    from commerceops.infrastructure.worker_lock import WorkerSession
    from commerceops.workflows.inventory_analysis import (
        InventoryRunner,
        MockCollectorFactory,
        no_hook,
    )

    session = WorkerSession(f.app, f.data.organization)
    await session.start()
    runner = InventoryRunner(
        InventoryStore(f.app, session, hook=store_hook or no_store_hook),
        factory or MockCollectorFactory(DIRECTORY),
        hook=hook or no_hook,
    )

    class DiagnosticRunner:
        workflow_versions = runner.workflow_versions

        async def run(self, request: Any) -> Any:
            try:
                return await runner.run(request)
            except Exception as error:
                print(
                    "P203_TEST_FAULT",
                    type(error).__name__,
                    [
                        (frame.name, frame.lineno)
                        for frame in traceback.extract_tb(error.__traceback__)
                    ],
                )
                raise

    stop = asyncio.Event()
    worker = asyncio.create_task(
        Worker(session, DiagnosticRunner(), heartbeat_seconds=0.1, poll_seconds=0.01).run(stop)
    )
    try:
        for _ in range(1000):
            if worker.done():
                worker.result()
                raise AssertionError("worker exited before job")
            with connect(f.app) as db:
                row = db.execute("SELECT status FROM business.jobs WHERE id=%s", (job,)).fetchone()
            assert row
            if row["status"] == expected_status:
                return
            assert row["status"] != "dead", row
            await asyncio.sleep(0.01)
        raise AssertionError("owned worker timed out")
    finally:
        stop.set()
        await worker


class InventoryProcess:
    def __init__(self, f: InventoryFixture, barrier: str = ""):
        env = os.environ.copy()
        s = f.app
        env.update(
            COMMERCEOPS_DB_HOST=s.host,
            COMMERCEOPS_DB_PORT=str(s.port),
            COMMERCEOPS_DB_NAME=s.name,
            COMMERCEOPS_DB_USER=s.user,
            COMMERCEOPS_DB_PASSWORD_FILE=str(s.password_file),
            COMMERCEOPS_MODE="test",
            P203_BARRIER=barrier,
            LANGSMITH_TRACING="false",
        )
        self.process = subprocess.Popen(
            [sys.executable, "-m", "tests.inventory_process", str(f.data.organization)],
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self.events: queue.Queue[dict[str, Any]] = queue.Queue()
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self) -> None:
        assert self.process.stdout
        for line in self.process.stdout:
            self.events.put(json.loads(line))

    def until(self, event: str) -> dict[str, Any]:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            row = self.events.get(timeout=max(0.01, deadline - time.monotonic()))
            assert row["event"] != "failed", row
            if row["event"] == event:
                return row
        raise AssertionError("owned process event timed out")

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=15)
        self.thread.join(timeout=5)
        for stream in (self.process.stdin, self.process.stdout):
            if stream:
                stream.close()
