"""G2 的隔离数据库与 simulated 决定；不修改正式 migration/grant。"""

import asyncio
import json
import os
import queue
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from commerceops.entrypoints.database import grant_runtime, migrate, setup_checkpointer
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.repository import TaskRepository, TaskScope
from commerceops.workflows.checkpoint_probe import WORKFLOW_VERSION

from tests.pg_support import Seed, seed

DDL = """
CREATE SCHEMA checkpoint_probe;
CREATE TABLE checkpoint_probe.runs (
 task_id uuid PRIMARY KEY REFERENCES business.business_tasks(id),
 organization_id uuid NOT NULL,shop_id uuid NOT NULL,thread_id text NOT NULL UNIQUE,
 workflow_version text NOT NULL,request_hash text NOT NULL,
 started boolean NOT NULL DEFAULT false,status text NOT NULL DEFAULT 'new'
 CHECK(status IN ('new','running','waiting','finished','needs_attention'))
);
CREATE TABLE checkpoint_probe.decisions (
 task_id uuid PRIMARY KEY REFERENCES checkpoint_probe.runs(task_id),
 decision_ref uuid NOT NULL UNIQUE, organization_id uuid NOT NULL, shop_id uuid NOT NULL,
 principal_id uuid NOT NULL,workflow_version text NOT NULL,request_hash text NOT NULL,
 approved boolean NOT NULL,approval_mode text NOT NULL CHECK(approval_mode='simulated')
);
CREATE TABLE checkpoint_probe.receipts (
 operation_key text PRIMARY KEY,
 task_id uuid NOT NULL UNIQUE REFERENCES checkpoint_probe.runs(task_id),
 organization_id uuid NOT NULL,shop_id uuid NOT NULL,request_hash text NOT NULL,
 result_ref text NOT NULL UNIQUE
);
GRANT USAGE ON SCHEMA checkpoint_probe TO commerceops_app;
GRANT SELECT,INSERT,UPDATE ON checkpoint_probe.runs TO commerceops_app;
GRANT SELECT ON checkpoint_probe.decisions TO commerceops_app;
GRANT SELECT,INSERT ON checkpoint_probe.receipts TO commerceops_app;
"""


@dataclass
class Fixture:
    owner: DatabaseSettings
    app: DatabaseSettings
    data: Seed

    def new_task(self, *, version: str = WORKFLOW_VERSION) -> Seed:
        with connect(self.app) as db:
            return seed(db, workflow_version=version)

    def enqueue(self, data: Seed, kind: str = "analyze", ref: str = "technical_fixture") -> UUID:
        with connect(self.app) as db:
            return TaskRepository(db, TaskScope(data.organization, data.shop)).enqueue(
                data.task,
                kind,
                str(uuid4()),
                ref,
            )

    def decide(self, data: Seed, *, approved: bool = True, ref: str | None = None) -> str:
        ref = ref or str(uuid4())
        with connect(self.owner) as db:
            row = db.execute(
                "SELECT * FROM checkpoint_probe.runs WHERE task_id=%s",
                (data.task,),
            ).fetchone()
            assert row
            db.execute(
                """INSERT INTO checkpoint_probe.decisions VALUES
                (%s,%s,%s,%s,%s,%s,%s,%s,'simulated')""",
                (
                    data.task,
                    ref,
                    data.organization,
                    data.shop,
                    data.principal,
                    row["workflow_version"],
                    row["request_hash"],
                    approved,
                ),
            )
        return ref

    def rows(self, task: UUID) -> dict[str, Any]:
        with connect(self.owner) as db:
            row = db.execute(
                """SELECT x.*,r.result_ref FROM checkpoint_probe.runs x
                LEFT JOIN checkpoint_probe.receipts r ON r.task_id=x.task_id WHERE x.task_id=%s""",
                (task,),
            ).fetchone()
            assert row
            return row


def initialize(owner: DatabaseSettings) -> Fixture:
    assert owner.runtime_password_file
    app = owner.model_copy(
        update={"user": "commerceops_app", "password_file": owner.runtime_password_file}
    )
    migrate(owner)
    asyncio.run(setup_checkpointer(owner))
    grant_runtime(owner)
    with connect(owner) as db:
        for statement in DDL.split(";"):
            if statement.strip():
                db.execute(statement)
    with connect(app) as db:
        data = seed(db, workflow_version=WORKFLOW_VERSION)
    return Fixture(owner, app, data)


class Process:
    def __init__(
        self,
        f: Fixture,
        *,
        barriers: str = "",
        ignore_cancel: bool = False,
        once: bool = False,
    ):
        environment = os.environ.copy()
        s = f.app
        environment.update(
            COMMERCEOPS_DB_HOST=s.host,
            COMMERCEOPS_DB_PORT=str(s.port),
            COMMERCEOPS_DB_NAME=s.name,
            COMMERCEOPS_DB_USER=s.user,
            COMMERCEOPS_DB_PASSWORD_FILE=str(s.password_file),
            COMMERCEOPS_MODE="test",
            P104_BARRIERS=barriers,
            LANGSMITH_TRACING="false",
            P104_IGNORE_CANCEL="1" if ignore_cancel else "0",
            P104_ONCE_BARRIERS="1" if once else "0",
        )
        self.process = subprocess.Popen(
            [sys.executable, "-m", "tests.checkpoint_process", str(f.data.organization)],
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self.events: queue.Queue[dict[str, Any]] = queue.Queue()
        self.history: list[dict[str, Any]] = []
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self) -> None:
        assert self.process.stdout
        for line in self.process.stdout:
            self.events.put(json.loads(line))

    def until(self, name: str) -> dict[str, Any]:
        import time

        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            event = self.events.get(timeout=max(0.01, deadline - time.monotonic()))
            self.history.append(event)
            if event["event"] == name:
                return event
            assert event["event"] != "failed", event
        raise AssertionError("process event timeout")

    def release(self) -> None:
        assert self.process.stdin
        self.process.stdin.write("release\n")
        self.process.stdin.flush()

    def wait(self) -> int:
        code = self.process.wait(timeout=15)
        self.thread.join(timeout=5)
        return code

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
            self.wait()
        for stream in (self.process.stdin, self.process.stdout):
            if stream:
                stream.close()
