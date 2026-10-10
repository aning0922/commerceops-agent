"""P3自有临时PG、真实会话和受控进程；不输出密码/token/DSN。"""

import asyncio
import json
import os
import queue
import secrets
import subprocess
import sys
import threading
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
from commerceops.application.replenishment.contracts import WebActor
from commerceops.application.replenishment.security import password_hash
from commerceops.entrypoints.api import create_app
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.inventory_repository import InventoryStore
from commerceops.infrastructure.replenishment_repository import ApprovalStore, ReplenishmentStore
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.web_sessions import SessionStore, json_native
from commerceops.infrastructure.worker import Worker
from commerceops.infrastructure.worker_lock import WorkerSession
from commerceops.workflows.inventory_analysis import InventoryRunner, MockCollectorFactory
from commerceops.workflows.replenishment import ApprovalRunner
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.inventory_support import DIRECTORY, InventoryFixture, initialize

ORIGIN = "http://127.0.0.1"


@dataclass
class P3Fixture:
    inventory: InventoryFixture
    config: WebConfig
    store: ReplenishmentStore
    client: TestClient
    actor: WebActor
    config_file: Path
    private: Path
    login: str
    password: SecretStr = field(repr=False)

    def relogin(self) -> None:
        bootstrap = self.client.get("/api/v1/auth/csrf").json()
        result = self.client.post(
            "/api/v1/auth/login",
            json={
                "schema_version": "p3-web-v1",
                "login": self.login,
                "password": self.password.get_secret_value(),
            },
            headers={"Origin": ORIGIN, "X-CSRF-Token": bootstrap["csrf_token"]},
        )
        assert result.status_code == 200
        self.actor = SessionStore(self.config).authenticate(
            self.client.cookies.get("commerceops_session")
        )

    def new_cycle(self, case: str = "baseline", request_key: UUID | None = None) -> dict[str, Any]:
        return {
            "schema_version": "p3-web-v1",
            "mode": "new_cycle",
            "request_key": str(request_key or uuid4()),
            "shop_id": str(self.inventory.data.shop),
            "parameters": {
                "source_mode": "mock",
                "dataset_version": "inventory-v1",
                "fixture_case": case,
                "L": 3,
                "R": 7,
                "S": 2,
            },
        }

    def headers(self) -> dict[str, str]:
        data = self.client.get("/api/v1/auth/session").json()
        return {"Origin": ORIGIN, "X-CSRF-Token": data["csrf_token"]}

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.client.post("/api/v1/tasks", json=payload, headers=self.headers())
        assert result.status_code == 202
        return cast(dict[str, Any], result.json())

    def from_report(self, task: UUID, request_key: UUID | None = None) -> dict[str, Any]:
        with connect(self.config.database) as db:
            row = db.execute(
                "SELECT * FROM business.analysis_reports WHERE task_id=%s", (task,)
            ).fetchone()
        assert row
        return {
            "schema_version": "p3-web-v1",
            "mode": "from_report",
            "request_key": str(request_key or uuid4()),
            "source_task_id": str(task),
            "source_report_id": str(row["id"]),
            "snapshot_id": str(row["snapshot_id"]),
            "facts_hash": row["facts_hash"],
        }


def _initialize_p3(owner: DatabaseSettings, app: DatabaseSettings, directory: Path) -> P3Fixture:
    f = initialize(owner, app)
    login = "u-" + uuid4().hex[:16]
    plain = secrets.token_urlsafe(32)
    hashed = password_hash(plain)
    identity = uuid4()
    with connect(owner) as db:
        db.execute(
            "UPDATE business.principals SET roles=ARRAY['operator','approver'],"
            "auth_version=auth_version+1 WHERE id=%s",
            (f.data.principal,),
        )
        db.execute(
            """INSERT INTO business.identities
        (id,organization_id,principal_id,provider,app_id,tenant_key,external_subject)
        VALUES (%s,%s,%s,'web',%s,%s,%s)""",
            (identity, f.data.organization, f.data.principal, f.data.app, f.data.tenant, login),
        )
        db.execute(
            "INSERT INTO business.web_credentials VALUES (%s,%s,%s,%s,%s,true)",
            (login, f.data.organization, f.data.principal, identity, hashed),
        )
        for role in ("operator", "approver"):
            db.execute(
                "INSERT INTO business.principal_role_shop_grants VALUES (%s,%s,%s,%s,true)",
                (f.data.organization, f.data.shop, f.data.principal, role),
            )
        row = db.execute(
            "SELECT auth_version FROM business.principals WHERE id=%s", (f.data.principal,)
        ).fetchone()
        assert row
    f.identity = replace(f.identity, identity_id=identity, auth_version=row["auth_version"])
    directory.chmod(0o700)
    for name in ("csrf-material", "nonce-material"):
        (directory / name).write_bytes(secrets.token_bytes(32))
        (directory / name).chmod(0o600)
    config = WebConfig(
        app,
        (directory / "csrf-material").read_bytes(),
        (directory / "nonce-material").read_bytes(),
        (ORIGIN, "http://127.0.0.1:3410"),
        transport_mode="local_http",
    )
    configuration = {
        "database": app.model_dump(mode="json"),
        "csrf_secret_file": str(directory / "csrf-material"),
        "nonce_secret_file": str(directory / "nonce-material"),
        "origins": list(config.origins),
        "transport_mode": "local_http",
    }
    config_file = directory / "configuration.json"
    config_file.write_text(json.dumps(configuration))
    config_file.chmod(0o600)
    store = ReplenishmentStore(config, DIRECTORY)
    client = TestClient(create_app(web_config=config, replenishment_store=store), base_url=ORIGIN)
    bootstrap = client.get("/api/v1/auth/csrf").json()
    response = client.post(
        "/api/v1/auth/login",
        json={"schema_version": "p3-web-v1", "login": login, "password": plain},
        headers={"Origin": ORIGIN, "X-CSRF-Token": bootstrap["csrf_token"]},
    )
    assert response.status_code == 200
    actor = SessionStore(config).authenticate(client.cookies.get("commerceops_session"))
    return P3Fixture(
        f, config, store, client, actor, config_file, directory, login, SecretStr(plain)
    )


def initialize_p3(owner: DatabaseSettings, app: DatabaseSettings, directory: Path) -> P3Fixture:
    try:
        return _initialize_p3(owner, app, directory)
    except psycopg.Error as error:
        # PG credential/session约束DETAIL可能含合成敏感值，不回显。
        raise RuntimeError(f"P3 fixture SQL class {error.sqlstate}") from None


async def run_graphs(
    f: P3Fixture,
    task: UUID,
    *,
    hook: Any = None,
    store_hook: Any = None,
    factory: Any = None,
    repeat_prepare: int = 0,
) -> None:
    session = WorkerSession(f.config.database, f.inventory.data.organization)
    await session.start()
    analysis = InventoryRunner(
        InventoryStore(f.config.database, session), factory or MockCollectorFactory(DIRECTORY)
    )
    approval = ApprovalRunner(
        ApprovalStore(f.config, session, hook=store_hook), **({"hook": hook} if hook else {})
    )

    class Router:
        workflow_versions = analysis.workflow_versions | approval.workflow_versions

        async def run(self, request: Any) -> Any:
            runner = (
                approval if request.workflow_version in approval.workflow_versions else analysis
            )
            result = await runner.run(request)
            if runner is approval and result.status == "interrupted":
                # 同一持锁Worker、同一running job内重放，不伪造旧进程终止证明。
                receipts = [await approval.store.prepare(request) for _ in range(repeat_prepare)]
                assert not receipts or all(receipt == receipts[0] for receipt in receipts)
            return result

    stop = asyncio.Event()
    worker = asyncio.create_task(
        Worker(session, Router(), heartbeat_seconds=0.1, poll_seconds=0.02).run(stop)
    )
    try:
        for _ in range(1200):
            if worker.done():
                worker.result()
                raise AssertionError("P3 owned worker exited early")
            with connect(f.config.database) as db:
                row = db.execute(
                    """SELECT t.state,j.status FROM business.business_tasks t
                JOIN business.jobs j ON j.task_id=t.id WHERE t.id=%s""",
                    (task,),
                ).fetchone()
            assert row
            if row["status"] == "done":
                assert row["state"] in ("awaiting_approval", "completed", "failed")
                return
            assert row["status"] != "dead"
            await asyncio.sleep(0.02)
        raise AssertionError("P3 bounded worker deadline")
    finally:
        stop.set()
        await worker


class P3Process:
    def __init__(
        self, f: P3Fixture, action: str, payload: dict[str, Any], barrier: str = "after_commit"
    ):
        self.path = f.private / ("request-" + uuid4().hex + ".json")
        self.path.write_text(
            json.dumps(
                {
                    "action": action,
                    "payload": payload,
                    "actor": json_native(f.actor.__dict__),
                    "configuration": str(f.config_file),
                    "barrier": barrier,
                    "legacy": json_native(f.inventory.data.__dict__),
                }
            )
        )
        self.path.chmod(0o600)
        env = os.environ.copy()
        env.update(PYTHONPATH=str(Path(__file__).resolve().parents[1]), LANGSMITH_TRACING="false")
        self.process = subprocess.Popen(
            [sys.executable, "-m", "tests.p3_process", str(self.path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
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
        for _ in range(50):
            row = self.events.get(timeout=15)
            assert row["event"] != "failed"
            if row["event"] == event:
                return row
        raise AssertionError("P3 owned process barrier not reached")

    def kill_reap(self) -> None:
        self.process.kill()
        self.process.wait(timeout=15)
        self.thread.join(timeout=5)
        assert self.process.returncode == -9
        assert not self.thread.is_alive()
        for stream in (self.process.stdin, self.process.stdout):
            if stream:
                stream.close()
