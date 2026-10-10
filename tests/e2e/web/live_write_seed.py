"""B03新自有窗口专用Mock种子；独立进程及单次连续Worker，无凭据输出。"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from commerceops.entrypoints.api import create_app
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.inventory_repository import InventoryStore
from commerceops.infrastructure.replenishment_repository import ApprovalStore, ReplenishmentStore
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.web_sessions import SessionStore
from commerceops.infrastructure.worker import Worker
from commerceops.infrastructure.worker_lock import WorkerSession
from commerceops.workflows.inventory_analysis import InventoryRunner, MockCollectorFactory
from commerceops.workflows.replenishment import ApprovalRunner
from fastapi.testclient import TestClient

from tests.e2e.web.live_origins import registered_origins
from tests.e2e.web.live_seed import save
from tests.inventory_support import DIRECTORY
from tests.p3_support import ControlledP3Factory


async def prepare_plans(
    config: WebConfig, organization: UUID, tasks: dict[str, UUID], expiry_config: WebConfig
) -> None:
    session = WorkerSession(config.database, organization)
    await session.start()
    ordinary = InventoryRunner(
        InventoryStore(config.database, session), MockCollectorFactory(DIRECTORY)
    )
    controlled = InventoryRunner(
        InventoryStore(config.database, session), ControlledP3Factory("two_unknown")
    )
    approval = ApprovalRunner(ApprovalStore(config, session))
    expiry = ApprovalRunner(ApprovalStore(expiry_config, session))

    class Router:
        workflow_versions = ordinary.workflow_versions | approval.workflow_versions

        async def run(self, request: Any) -> Any:
            if request.workflow_version in approval.workflow_versions:
                return await (expiry if request.task_id == tasks["expiry"] else approval).run(
                    request
                )
            return await (
                controlled if request.task_id == tasks["decline_source"] else ordinary
            ).run(request)

    stop = asyncio.Event()
    worker = asyncio.create_task(
        Worker(session, Router(), heartbeat_seconds=0.1, poll_seconds=0.02).run(stop)
    )
    try:
        for _ in range(1500):
            if worker.done():
                worker.result()
                raise AssertionError("owned seed worker exited")
            with connect(config.database) as db:
                row = db.execute(
                    "SELECT count(*) AS n FROM business.jobs "
                    "WHERE task_id=ANY(%s) AND status<>'done'",
                    (list(tasks.values()),),
                ).fetchone()
            assert row
            if row["n"] == 0:
                return
            await asyncio.sleep(0.02)
        raise AssertionError("owned seed bounded deadline")
    finally:
        stop.set()
        await worker


def main(directory: Path) -> None:
    # The approved B02 seeder exits and is reaped before a new Worker is started.
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("live_seed.py")), str(directory)],
        env=os.environ,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=300,
    )
    if result.returncode:
        raise RuntimeError("owned base seed failed")
    web_origin, api_origin = registered_origins(directory)
    base = json.loads((directory / "web-facts.json").read_text())
    accounts = json.loads((directory / "web-accounts.json").read_text())
    config_file = directory / "configuration.json"
    configuration = json.loads(config_file.read_text())
    config = WebConfig.from_file(config_file)
    client = TestClient(
        create_app(web_config=config, replenishment_store=ReplenishmentStore(config, DIRECTORY)),
        base_url=api_origin,
    )
    bootstrap = client.get("/api/v1/auth/csrf").json()
    response = client.post(
        "/api/v1/auth/login",
        json={
            "schema_version": "p3-web-v1",
            "login": accounts["operator"]["login"],
            "password": accounts["operator"]["password"],
        },
        headers={"Origin": web_origin, "X-CSRF-Token": bootstrap["csrf_token"]},
    )
    assert response.status_code == 200
    actor = SessionStore(config).authenticate(client.cookies.get("commerceops_session"))
    records = {
        "combined20": {
            "task": base["task"],
            "approval": base["approval"],
            "report": base["report"],
            "source_task": base["source_task"],
        }
    }
    receipts: dict[str, dict[str, Any]] = {}
    for name, case in [
        ("approve", "baseline"),
        ("reject", "baseline"),
        ("unknown", "baseline"),
        ("decline", "unknown_inbound"),
        ("second_combined", "unknown_inbound"),
        ("revocation", "baseline"),
        ("supersede", "baseline"),
        ("expiry", "baseline"),
    ]:
        if name == "expiry":
            expiry_configuration = {
                **configuration,
                "approval_ttl_seconds": 60,
                "config_version": "p3b03-expiry-v1",
            }
            save(config_file, expiry_configuration)
            expiry_config = WebConfig.from_file(config_file)
            previous = client
            client = TestClient(
                create_app(
                    web_config=expiry_config,
                    replenishment_store=ReplenishmentStore(expiry_config, DIRECTORY),
                ),
                base_url=api_origin,
            )
            client.cookies.update(previous.cookies)
            previous.close()
        current = client.get("/api/v1/auth/session").json()
        response = client.post(
            "/api/v1/tasks",
            json={
                "schema_version": "p3-web-v1",
                "mode": "new_cycle",
                "request_key": str(uuid4()),
                "shop_id": base["shop_a"],
                "parameters": {
                    "source_mode": "mock",
                    "dataset_version": "inventory-v1",
                    "fixture_case": case,
                    "L": 3,
                    "R": 7,
                    "S": 2,
                },
            },
            headers={"Origin": web_origin, "X-CSRF-Token": current["csrf_token"]},
        )
        assert response.status_code == 202
        receipts[name] = response.json()
    tasks = {name: UUID(r["task_id"]) for name, r in receipts.items()}
    tasks.update({name + "_source": UUID(r["source_task_id"]) for name, r in receipts.items()})
    asyncio.run(prepare_plans(config, actor.organization_id, tasks, expiry_config))
    with connect(config.database) as db:
        for name, receipt in receipts.items():
            row = db.execute(
                "SELECT id,expires_at FROM business.approvals WHERE task_id=%s",
                (UUID(receipt["task_id"]),),
            ).fetchone()
            assert row
            records[name] = {
                "task": receipt["task_id"],
                "approval": str(row["id"]),
                "source_task": receipt["source_task_id"],
                "expires_at": row["expires_at"].isoformat(),
            }
    save(
        directory / "write-facts.json",
        {"records": records, "organization": str(actor.organization_id), "shop": base["shop_a"]},
    )
    save(config_file, configuration)
    client.close()
    print("B03 owned Mock T1/T2 seed ready; credentials and raw responses withheld")


if __name__ == "__main__":
    try:
        main(Path(sys.argv[1]))
    except Exception as error:
        print(json.dumps({"stage": "B03 seed", "category": type(error).__name__}))
        raise SystemExit(2) from None
