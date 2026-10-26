"""Owned PG + ASGI + Fake Woo HTTP: parent seed/receipt contracts, not real Woo or restore."""

import asyncio
import math
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from commerceops.adapters.commerce.woocommerce import WooCommerce
from commerceops.adapters.commerce.woocommerce_config import WooReadOnlyConfig
from commerceops.entrypoints.api import create_app
from commerceops.entrypoints.worker import unavailable_mock
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.inventory_repository import InventoryStore
from commerceops.infrastructure.replenishment_repository import ApprovalStore, ReplenishmentStore
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.woo_collection import BoundWooCollectorFactory
from commerceops.infrastructure.worker import Worker
from commerceops.infrastructure.worker_lock import WorkerSession
from commerceops.workflows.inventory_analysis import InventoryRunner
from commerceops.workflows.replenishment import ApprovalRunner
from fastapi.testclient import TestClient

from scripts.m2_state import (
    bind_source,
    completed_receipt,
    pending_receipt,
    save,
    seed,
    web_configuration,
)
from scripts.woo_lab.expectations import expected_document, positive_golden
from tests.inventory_support import DIRECTORY
from tests.p3_support import ORIGIN
from tests.test_p4_acceptance_pg import database as database
from tests.test_p4_acceptance_pg import initialize_schema
from tests.test_woo_positive_lab import mapping_for, resolved
from tests.test_woocommerce_readonly import config as config
from tests.test_woocommerce_readonly import order, product, response

pytestmark = pytest.mark.integration


def wire(spec: dict[str, Any], mapping: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    ids = mapping["products"]
    definitions = {p["key"]: p for p in spec["products"]}
    paths: dict[str, list[dict[str, Any]]] = {"products": [], "orders": []}
    for row in spec["products"]:
        item = product(
            ids[row["key"]],
            type=row["type"],
            name=row.get("color", row["name"]),
            sku=row["sku"],
            manage_stock=row["manage_stock"],
            stock_quantity=row["stock_quantity"],
            stock_status=row["stock_status"],
        )
        if row["type"] == "variable":
            item["variations"] = [
                ids[x["key"]] for x in spec["products"] if x.get("parent") == row["key"]
            ]
        key = (
            f"products/{ids[row['parent']]}/variations"
            if row["type"] == "variation"
            else "products"
        )
        paths.setdefault(key, []).append(item)
    for row in spec["orders"]:
        record = mapping["orders"][row["key"]]
        line = row["lines"][0]
        definition = definitions[line["product"]]
        stamp = (
            datetime.fromisoformat(row["created_at"])
            .astimezone(UTC)
            .replace(tzinfo=None)
            .isoformat()
        )
        item = order(
            record["id"],
            created=stamp,
            id=record["lines"][0]["id"],
            product_id=ids[definition.get("parent", definition["key"])],
            variation_id=ids[definition["key"]] if definition["type"] == "variation" else 0,
            quantity=line["quantity"],
            total=line["total"],
            total_tax="0.00",
        )
        item.update(
            status=row["status"],
            date_paid_gmt=stamp,
            date_completed_gmt=stamp if row["status"] == "completed" else None,
            refunds=[],
        )
        paths["orders"].append(item)
        paths[f"orders/{record['id']}/refunds"] = []
    return paths


def login(client: TestClient, account: dict[str, Any]) -> None:
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    result = client.post(
        "/api/v1/auth/login",
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
        json={
            "schema_version": "p3-web-v1",
            "login": account["login"],
            "password": account["password"],
        },
    )
    assert result.status_code == 200


def post(client: TestClient, path: str, payload: dict[str, Any]) -> Any:
    csrf = client.get("/api/v1/auth/session").json()["csrf_token"]
    return client.post(path, headers={"Origin": ORIGIN, "X-CSRF-Token": csrf}, json=payload)


@pytest.mark.parametrize(
    "mode", ["positive", "unknown_stock", "timeout", "missing_page", "changed", "material"]
)
def test_owned_m2_seed_source_pending_and_completed_receipts(
    database: tuple[DatabaseSettings, DatabaseSettings],
    tmp_path: Path,
    config: WooReadOnlyConfig,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    owner, app = database
    initialize_schema(owner, "0018")
    seeded = seed(owner, tmp_path, str(uuid4()))
    spec = resolved()
    spec["shop_id"] = seeded["shop_id"]
    mapping = mapping_for(spec)
    expected = expected_document(spec, mapping)
    gold = positive_golden(spec, mapping)
    lab = tmp_path / "lab"
    lab.mkdir(mode=0o700)
    probe = config.model_dump(mode="json")
    probe.update(shop_id=seeded["shop_id"], window=expected["window"])
    save(lab / "probe-config.private.json", probe)
    save(lab / "expected.private.json", expected)
    binding = bind_source(owner, tmp_path, lab, spec["anchor_day"])
    cfg_path = tmp_path / "configuration.json"
    save(cfg_path, web_configuration(tmp_path, app, ORIGIN))
    cfg = WebConfig.from_file(cfg_path)
    paths = wire(spec, mapping)
    if mode == "unknown_stock":
        paths["products"][0]["stock_quantity"] = None
    seen: dict[str, int] = {}

    def http(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET" and request.url.host == "127.0.0.1"
        path = request.url.path.removeprefix("/wp-json/wc/v3/")
        rows = paths[path]
        page = int(request.url.params["page"])
        if mode == "timeout":
            raise httpx.ReadTimeout("synthetic owned timeout", request=request)
        if mode == "missing_page" and path == "products" and page == 2:
            return httpx.Response(503, json={"code": "synthetic_unavailable"})
        key = str(request.url)
        seen[key] = seen.get(key, 0) + 1
        if mode == "changed" and path == "products" and page == 1 and seen[key] % 2 == 0:
            rows = [{**row, "stock_quantity": 21} if i == 0 else row for i, row in enumerate(rows)]
        size = int(request.url.params["per_page"])
        return response(
            rows[(page - 1) * size : page * size],
            total=len(rows),
            pages=math.ceil(len(rows) / size),
        )

    def transport(conf: WooReadOnlyConfig, **kwargs: Any) -> WooCommerce:
        return WooCommerce(conf, transport=httpx.MockTransport(http), **kwargs)

    monkeypatch.setattr("commerceops.infrastructure.woo_collection.WooCommerce", transport)
    api = create_app(web_config=cfg, replenishment_store=ReplenishmentStore(cfg, DIRECTORY))
    with TestClient(api, base_url=ORIGIN) as operator, TestClient(api, base_url=ORIGIN) as approver:
        login(operator, seeded["accounts"]["operator"])
        login(approver, seeded["accounts"]["approver"])
        created = post(
            operator,
            "/api/v1/tasks",
            dict(
                schema_version="p3-web-v1",
                mode="new_cycle",
                request_key=str(uuid4()),
                shop_id=seeded["shop_id"],
                parameters=dict(
                    source_mode="woocommerce_test",
                    source_config_version=binding["source_config_version"],
                    L=3,
                    R=7,
                    S=2,
                ),
            ),
        )
        assert created.status_code == 202
        original = created.json()
        task = UUID(original["task_id"])

        async def run() -> None:
            session = WorkerSession(app, UUID(seeded["organization_id"]))
            await session.start()
            assert cfg.commerce_sources is not None
            factory = BoundWooCollectorFactory(app, cfg.commerce_sources)
            inventory = InventoryRunner(
                InventoryStore(app, session, commerce_sources=cfg.commerce_sources),
                unavailable_mock,
                woo_collector_factory=factory,
            )
            approval = ApprovalRunner(ApprovalStore(cfg, session), woo_collector_factory=factory)

            class Router:
                workflow_versions = inventory.workflow_versions | approval.workflow_versions

                async def run(self, request: Any) -> Any:
                    runner = (
                        approval
                        if request.workflow_version in approval.workflow_versions
                        else inventory
                    )
                    return await runner.run(request)

            stop = asyncio.Event()
            child = asyncio.create_task(
                Worker(
                    session,
                    Router(),
                    heartbeat_seconds=0.1,
                    poll_seconds=0.02,
                    reconcile=approval.reconcile,
                ).run(stop)
            )
            until = time.monotonic() + 45
            try:
                while time.monotonic() < until:
                    if child.done():
                        child.result()
                        raise AssertionError("owned worker exited")
                    with connect(app) as db:
                        row = db.execute(
                            "SELECT t.state,a.ready_at FROM business.business_tasks t "
                            "LEFT JOIN business.approvals a ON a.task_id=t.id WHERE t.id=%s",
                            (task,),
                        ).fetchone()
                    assert row
                    if mode not in ("positive", "material") and row["state"] == "failed":
                        with connect(app) as db:
                            for table in ("executions", "replenishment_items", "approvals"):
                                from psycopg import sql

                                count = db.execute(
                                    sql.SQL(
                                        "SELECT count(*) AS n FROM business.{} WHERE task_id=%s"
                                    ).format(sql.Identifier(table)),
                                    (task,),
                                ).fetchone()
                                assert count == {"n": 0}
                            report = db.execute(
                                "SELECT report FROM business.analysis_reports WHERE task_id=%s",
                                (UUID(original["source_task_id"]),),
                            ).fetchone()
                            assert report and (
                                not report["report"]["complete"]
                                or report["report"]["requires_review"]
                            )
                        return
                    assert row["state"] not in ("failed", "needs_attention")
                    if row["state"] == "awaiting_approval" and row["ready_at"]:
                        break
                    await asyncio.sleep(0.05)
                else:
                    raise AssertionError("pending deadline")
                task_read = (await asyncio.to_thread(operator.get, f"/api/v1/tasks/{task}")).json()
                approval_read = (
                    await asyncio.to_thread(
                        approver.get, f"/api/v1/approvals/{task_read['approval_id']}"
                    )
                ).json()
                plan = approval_read["plan"]
                observed = dict(
                    organization_id=seeded["organization_id"],
                    shop_id=seeded["shop_id"],
                    task_id=str(task),
                    source_task_id=original["source_task_id"],
                    plan_id=plan["plan_id"],
                    plan_version=plan["plan_version"],
                    plan_hash=plan["plan_hash"],
                    report_id=plan["source"]["report_id"],
                    snapshot_id=plan["source"]["snapshot_id"],
                    facts_hash=plan["source"]["facts_hash"],
                    approval_id=task_read["approval_id"],
                    expires_at=plan["expires_at"],
                    create_request_key=original["request_key"],
                    required_assumption_keys=[a["key"] for a in plan["required_assumptions"]],
                    operator_principal_id=seeded["accounts"]["operator"]["expected_principal_id"],
                    approver_principal_id=seeded["accounts"]["approver"]["expected_principal_id"],
                )
                with connect(app) as db:
                    receipt = pending_receipt(db, observed, approval_read, gold, seeded, binding)
                assert receipt["total_quantity"] == 219
                decision = dict(
                    schema_version="p3-web-v1",
                    request_key=str(uuid4()),
                    approval_id=observed["approval_id"],
                    plan_id=observed["plan_id"],
                    plan_version=observed["plan_version"],
                    plan_hash=observed["plan_hash"],
                    action="approve_with_assumptions",
                    acknowledged_assumption_keys=observed["required_assumption_keys"],
                    nonce=approval_read["nonce"],
                )
                url = f"/api/v1/approvals/{observed['approval_id']}/decision"
                for changed, status in (
                    ({"nonce": "X" * 43}, 422),
                    ({"plan_hash": "0" * 64}, 409),
                    ({"plan_version": 2}, 409),
                    ({"plan_id": str(uuid4())}, 409),
                ):
                    assert (
                        await asyncio.to_thread(post, approver, url, {**decision, **changed})
                    ).status_code == status
                assert (await asyncio.to_thread(post, operator, url, decision)).status_code == 403
                with connect(app) as db:
                    assert db.execute(
                        "SELECT count(*) AS n FROM business.executions WHERE task_id=%s", (task,)
                    ).fetchone() == {"n": 0}
                    assert db.execute(
                        "SELECT count(*) AS n FROM business.approval_resumes WHERE task_id=%s",
                        (task,),
                    ).fetchone() == {"n": 0}
                if mode == "material":
                    paths["products"][0]["stock_quantity"] = 30
                assert (await asyncio.to_thread(post, approver, url, decision)).status_code == 200
                if mode == "material":
                    while time.monotonic() < until:
                        with connect(app) as db:
                            replacement = db.execute(
                                "SELECT t.state,a.ready_at,a.id FROM business.business_tasks t "
                                "JOIN business.approvals a ON a.plan_id=t.active_plan_id "
                                "WHERE t.id=%s",
                                (task,),
                            ).fetchone()
                        if (
                            replacement
                            and replacement["state"] == "needs_reapproval"
                            and replacement["ready_at"]
                        ):
                            break
                        await asyncio.sleep(0.05)
                    else:
                        raise AssertionError("material reapproval deadline")
                    current = (
                        await asyncio.to_thread(
                            approver.get, f"/api/v1/approvals/{replacement['id']}"
                        )
                    ).json()
                    next_plan = current["plan"]
                    assert next_plan["plan_version"] == 2
                    assert next_plan["plan_id"] != decision["plan_id"]
                    assert next_plan["plan_hash"] != decision["plan_hash"]
                    assert current["nonce"] != decision["nonce"]
                    with connect(app) as db:
                        assert db.execute(
                            "SELECT count(*) AS n FROM business.executions WHERE task_id=%s",
                            (task,),
                        ).fetchone() == {"n": 0}
                    # Original key returns only the original recorded decision, never approves v2.
                    assert (
                        await asyncio.to_thread(post, approver, url, decision)
                    ).status_code == 200
                    next_decision = {
                        **decision,
                        "request_key": str(uuid4()),
                        "approval_id": str(replacement["id"]),
                        "plan_id": next_plan["plan_id"],
                        "plan_version": 2,
                        "plan_hash": next_plan["plan_hash"],
                        "nonce": current["nonce"],
                        "acknowledged_assumption_keys": [
                            a["key"] for a in next_plan["required_assumptions"]
                        ],
                    }
                    url = f"/api/v1/approvals/{replacement['id']}/decision"
                    assert (
                        await asyncio.to_thread(
                            post, approver, url, {**next_decision, "nonce": decision["nonce"]}
                        )
                    ).status_code == 422
                    assert (
                        await asyncio.to_thread(post, approver, url, next_decision)
                    ).status_code == 200
                    decision = next_decision
                for _ in range(10):
                    assert (
                        await asyncio.to_thread(post, approver, url, decision)
                    ).status_code == 200
                while time.monotonic() < until:
                    with connect(app) as db:
                        state = db.execute(
                            "SELECT state FROM business.business_tasks WHERE id=%s", (task,)
                        ).fetchone()
                    if state == {"state": "completed"}:
                        break
                    await asyncio.sleep(0.05)
                else:
                    raise AssertionError("completion deadline")
                execution_response = await asyncio.to_thread(
                    operator.get, f"/api/v1/tasks/{task}/execution"
                )
                assert execution_response.status_code == 200
                execution = execution_response.json()
                if mode == "material":
                    assert execution["plan_id"] == decision["plan_id"]
                    assert execution["approval_id"] == decision["approval_id"]
                    with connect(app) as db:
                        assert db.execute(
                            "SELECT count(*) AS n,sum(quantity) AS q "
                            "FROM business.replenishment_items WHERE task_id=%s",
                            (task,),
                        ).fetchone() == {"n": 4, "q": 209}
                        assert db.execute(
                            "SELECT count(*) AS n FROM business.executions WHERE task_id=%s",
                            (task,),
                        ).fetchone() == {"n": 1}
                        assert db.execute(
                            "SELECT plan_version FROM business.executions WHERE task_id=%s",
                            (task,),
                        ).fetchone() == {"plan_version": 2}
                    return
                observed.update(
                    decision_request_key=decision["request_key"],
                    execution_id=execution["execution_id"],
                    item_ids=execution["item_ids"],
                )
                with connect(app) as db:
                    result = completed_receipt(db, observed, gold, seeded)
                assert result["execution_count"] == 1 and result["item_count"] == 4
            finally:
                stop.set()
                await child

        asyncio.run(run())
