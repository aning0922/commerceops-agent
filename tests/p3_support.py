"""P3自有临时PG、真实会话和受控进程；不输出密码/token/DSN。"""

import asyncio
import hashlib
import json
import os
import queue
import secrets
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass, field, replace
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
from commerceops.adapters.commerce.mock import Fixture, MockCommerce
from commerceops.application.commerce.collection import InventoryCollector
from commerceops.application.replenishment.contracts import WebActor
from commerceops.application.replenishment.security import password_hash
from commerceops.domain.commerce_values import facts_hash, sku_key, stock_pool_key
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


class ControlledP3Factory:
    """私有测试进程声明Mock变体；不是API参数、客户端改库存或路径扩权。"""

    def __init__(self, mode: str):
        assert mode in (
            "long_sku",
            "two_unknown",
            "stock_change",
            "demand_change",
            "null_to_known",
            "hard_quality",
            "time_only",
        )
        self.mode = mode

    def __call__(self, request: Any) -> InventoryCollector:
        if self.mode in ("long_sku", "two_unknown") and request.fixture_case != "unknown_inbound":
            return MockCollectorFactory(DIRECTORY)(request)
        if self.mode not in ("long_sku", "two_unknown"):
            base = Fixture.load(
                DIRECTORY, "unknown_inbound" if self.mode == "null_to_known" else "baseline"
            )
            provenance = base.source.provenance.model_copy(
                update={
                    "captured_at": base.now + timedelta(seconds=1),
                    "raw_hash": facts_hash({"controlled_revalidation": self.mode}),
                }
            )
            source = base.source.model_copy(update={"provenance": provenance})
            fresh_products = tuple(
                row.model_copy(update={"source": provenance}) for row in base.products
            )
            fresh_orders = tuple(
                row.model_copy(update={"source": provenance}) for row in base.orders
            )
            refunds = tuple(row.model_copy(update={"source": provenance}) for row in base.refunds)
            fresh_stocks = tuple(
                row.model_copy(
                    update={"source": provenance, "observed_at": base.now + timedelta(seconds=1)}
                )
                for row in base.inventories
            )
            if self.mode == "stock_change":
                fresh_stocks = (
                    fresh_stocks[0].model_copy(update={"available_stock": 30}),
                    *fresh_stocks[1:],
                )
            elif self.mode == "demand_change":
                fresh_orders = (
                    fresh_orders[0].model_copy(update={"quantity": 77}),
                    *fresh_orders[1:],
                )
            elif self.mode == "null_to_known":
                fresh_stocks = (
                    fresh_stocks[0].model_copy(
                        update={
                            "inbound_units": 0,
                            "inbound_reason": None,
                            "inbound_quality": "reliable",
                        }
                    ),
                    *fresh_stocks[1:],
                )
            elif self.mode == "hard_quality":
                fresh_stocks = (
                    fresh_stocks[0].model_copy(
                        update={"available_stock": None, "stock_reason": "UNKNOWN_STOCK"}
                    ),
                    *fresh_stocks[1:],
                )
            changed = replace(
                base,
                source=source,
                products=fresh_products,
                orders=fresh_orders,
                refunds=refunds,
                inventories=fresh_stocks,
            )
            return InventoryCollector(MockCommerce(changed), source, base.now)
        base = Fixture.load(DIRECTORY, "unknown_inbound")
        version = "p3-owned-" + self.mode + "-v1"
        provenance = base.source.provenance.model_copy(
            update={
                "fixture_version": version,
                "raw_hash": facts_hash({"controlled_fixture": version}),
            }
        )
        source = base.source.model_copy(update={"provenance": provenance})
        length = 256 - len(sku_key(source.shop_id, "x", None)) + 1
        identifiers = ["x" * length] if self.mode == "long_sku" else ["ack-a", "ack-b"]
        products, orders, stocks = [], [], []
        for number, identifier in enumerate(identifiers):
            key = sku_key(source.shop_id, identifier, None)
            pool = stock_pool_key(source.shop_id, identifier)
            products.append(
                base.products[0].model_copy(
                    update={
                        "product_id": identifier,
                        "sku_key": key,
                        "stock_pool_key": pool,
                        "source": provenance,
                    }
                )
            )
            orders.append(
                base.orders[0].model_copy(
                    update={
                        "order_id": "controlled-" + str(number),
                        "sku_key": key,
                        "source": provenance,
                    }
                )
            )
            stocks.append(
                base.inventories[0].model_copy(
                    update={"sku_key": key, "stock_pool_key": pool, "source": provenance}
                )
            )
        controlled = replace(
            base,
            source=source,
            products=tuple(products),
            orders=tuple(orders),
            inventories=tuple(stocks),
        )
        return InventoryCollector(MockCommerce(controlled), source, base.now)


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
        ApprovalStore(f.config, session, hook=store_hook),
        collector_factory=factory or MockCollectorFactory(DIRECTORY),
        **({"hook": hook} if hook else {}),
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
        checkout = Path(__file__).resolve().parents[1]
        self.expected_sources = {
            name: hashlib.sha256(
                (checkout / "backend/src/commerceops" / path).read_bytes()
            ).hexdigest()
            for name, path in {
                "Worker": "infrastructure/worker.py",
                "ApprovalRunner": "workflows/replenishment.py",
                "InventoryRunner": "workflows/inventory_analysis.py",
                "WorkerSession": "infrastructure/worker_lock.py",
            }.items()
        }
        self.sources_match: bool | None = None
        env.update(
            PYTHONPATH=os.pathsep.join((str(checkout / "backend/src"), str(checkout))),
            LANGSMITH_TRACING="false",
        )
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
        self.history: list[dict[str, Any]] = []
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def release(self) -> None:
        assert self.process.stdin
        self.process.stdin.write("release\n")
        self.process.stdin.flush()

    def stop_clean(self) -> None:
        self.process.send_signal(signal.SIGTERM)
        self.until("stopped")
        assert self.process.wait(timeout=10) == 0
        self.thread.join(timeout=5)
        for stream in (self.process.stdin, self.process.stdout):
            if stream:
                stream.close()

    def close_exited(self, expected: int) -> None:
        assert self.process.wait(timeout=10) == expected
        self.thread.join(timeout=5)
        for stream in (self.process.stdin, self.process.stdout):
            if stream:
                stream.close()

    def _read(self) -> None:
        assert self.process.stdout
        for line in self.process.stdout:
            event = json.loads(line)
            if event.get("event") == "source_checked":
                self.sources_match = event.get("hashes") == self.expected_sources
                proof = {"four_imports_match": self.sources_match, "hashes": event.get("hashes")}
                evidence = Path("/run/owned") if Path("/run/owned").is_dir() else self.path.parent
                leaf = evidence / ("imports-" + self.path.stem + ".safe.json")
                leaf.write_text(json.dumps(proof, sort_keys=True))
                leaf.chmod(0o600)
                if not self.sources_match:
                    event = {"event": "failed", "category": "SOURCE_HASH_MISMATCH"}
            self.history.append(event)
            self.events.put(event)

    def until(self, event: str) -> dict[str, Any]:
        for _ in range(50):
            row = self.events.get(timeout=15)
            assert row["event"] != "failed", {key: row.get(key) for key in ("category", "trace")}
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
