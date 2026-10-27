"""Original mixed catalog in a registered seven-day cohort: PG/ASGI + Fake HTTP only."""

import asyncio
import hashlib
import json
import math
import time
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import httpx
import pytest
from commerceops.adapters.commerce.woocommerce import WooCommerce
from commerceops.adapters.commerce.woocommerce_config import WooReadOnlyConfig
from commerceops.entrypoints.worker import unavailable_mock
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.inventory_repository import InventoryStore
from commerceops.infrastructure.replenishment_repository import ApprovalStore
from commerceops.infrastructure.woo_collection import BoundWooCollectorFactory
from commerceops.infrastructure.worker import Worker
from commerceops.infrastructure.worker_lock import WorkerSession
from commerceops.workflows.inventory_analysis import InventoryRunner
from commerceops.workflows.replenishment import ApprovalRunner
from psycopg import sql

from scripts.woo_lab.lab import FIXTURE
from scripts.woo_lab.profiles import MIXED_SHA256
from tests.p3_support import P3Fixture
from tests.test_p3_pg import fixture as fixture
from tests.test_p5_m2_pending_pg import wire
from tests.test_p5_sources_pg import configure, woo_request
from tests.test_woo_positive_lab import mapping_for
from tests.test_woocommerce_readonly import config as config
from tests.test_woocommerce_readonly import response

pytestmark = pytest.mark.integration


def test_complete_mixed_catalog_quality_preserved_and_formal_zero_execution(
    fixture: P3Fixture,
    config: WooReadOnlyConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    f = fixture
    raw = FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MIXED_SHA256
    spec = json.loads(raw)
    metadata, _ = configure(f, config, profile="mixed-v1", anchor_day=date(2026, 10, 2))
    mapping = mapping_for(spec)
    paths = wire(spec, mapping)
    definitions = {p["key"]: p for p in spec["products"]}
    for p in paths["products"]:
        original = next(d for d in definitions.values() if mapping["products"][d["key"]] == p["id"])
        p["backorders"] = original.get("backorders", "no")
    orders = {row["id"]: row for row in paths["orders"]}
    for definition in spec["orders"]:
        row = orders[mapping["orders"][definition["key"]]["id"]]
        if definition["status"] not in ("processing", "completed"):
            row["date_paid_gmt"] = None
        if definition["key"] == "full_refund":
            row["status"] = "refunded"
    for index, definition in enumerate(spec["refunds"]):
        original = mapping["orders"][definition["order"]]
        identifier = 300 + index
        quantity = definition["quantity"]
        stamp = datetime.fromisoformat(definition["created_at"]).astimezone(UTC)
        refund = dict(
            id=identifier,
            date_created_gmt=stamp.replace(tzinfo=None).isoformat(),
            amount=definition["amount"],
            line_items=[]
            if quantity is None
            else [
                dict(
                    quantity=-quantity,
                    meta_data=[dict(key="_refunded_item_id", value=original["lines"][0]["id"])],
                )
            ],
        )
        paths[f"orders/{original['id']}/refunds"].append(refund)
        orders[original["id"]]["refunds"].append({"id": identifier})
    seen = set()

    def http(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET" and request.url.host == "127.0.0.1"
        path = request.url.path.removeprefix("/wp-json/wc/v3/")
        seen.add(path)
        rows = paths[path]
        page, size = int(request.url.params["page"]), int(request.url.params["per_page"])
        return response(
            rows[(page - 1) * size : page * size],
            total=len(rows),
            pages=math.ceil(len(rows) / size),
        )

    def transport(cfg: WooReadOnlyConfig, **kwargs: Any) -> WooCommerce:
        return WooCommerce(cfg, transport=httpx.MockTransport(http), **kwargs)

    monkeypatch.setattr("commerceops.infrastructure.woo_collection.WooCommerce", transport)
    accepted = f.create(woo_request(f))
    task, source_task = UUID(accepted["task_id"]), UUID(accepted["source_task_id"])

    async def run() -> None:
        session = WorkerSession(f.config.database, f.inventory.data.organization)
        await session.start()
        assert f.config.commerce_sources is not None
        factory = BoundWooCollectorFactory(f.config.database, f.config.commerce_sources)
        inventory = InventoryRunner(
            InventoryStore(f.config.database, session, commerce_sources=f.config.commerce_sources),
            unavailable_mock,
            woo_collector_factory=factory,
        )
        approval = ApprovalRunner(ApprovalStore(f.config, session), woo_collector_factory=factory)

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
        worker = asyncio.create_task(
            Worker(
                session,
                Router(),
                heartbeat_seconds=0.1,
                poll_seconds=0.02,
                reconcile=approval.reconcile,
            ).run(stop)
        )
        until = time.monotonic() + 40
        try:
            while time.monotonic() < until:
                if worker.done():
                    worker.result()
                    raise AssertionError("mixed worker exited early")
                with connect(f.config.database) as db:
                    row = db.execute(
                        "SELECT state FROM business.business_tasks WHERE id=%s", (task,)
                    ).fetchone()
                if row == {"state": "failed"}:
                    return
                assert row and row["state"] not in (
                    "completed",
                    "awaiting_approval",
                    "needs_attention",
                )
                await asyncio.sleep(0.05)
            raise AssertionError("mixed formal task deadline")
        finally:
            stop.set()
            await worker

    asyncio.run(run())
    with connect(f.config.database) as db:
        snapshot = db.execute(
            "SELECT id,window_start,window_end FROM business.commerce_snapshots WHERE task_id=%s",
            (source_task,),
        ).fetchone()
        assert snapshot and snapshot["window_start"] == metadata.window.start
        assert snapshot["window_end"] == metadata.window.end
        for table, count in [
            ("snapshot_products", 9),
            ("snapshot_order_lines", 9),
            ("snapshot_refunds", 3),
        ]:
            assert db.execute(
                sql.SQL("SELECT count(*) AS n FROM business.{} WHERE snapshot_id=%s").format(
                    sql.Identifier(table)
                ),
                (snapshot["id"],),
            ).fetchone() == {"n": count}
        stocks = db.execute(
            "SELECT payload,available_stock FROM business.snapshot_products WHERE snapshot_id=%s",
            (snapshot["id"],),
        ).fetchall()
        assert sum(row["available_stock"] is None for row in stocks) == 1
        assert sum(row["available_stock"] == -3 for row in stocks) == 1
        assert (
            sum(row["payload"]["inventory"]["pool_allocation"] == "unresolved" for row in stocks)
            == 2
        )
        assert sum(row["payload"]["product"]["sku_label"] is None for row in stocks) == 1
        report = db.execute(
            "SELECT report FROM business.analysis_reports WHERE task_id=%s", (source_task,)
        ).fetchone()
        assert report and report["report"]["requires_review"]
        for table in ("executions", "replenishment_items", "approvals", "approval_resumes"):
            assert db.execute(
                sql.SQL("SELECT count(*) AS n FROM business.{} WHERE task_id=%s").format(
                    sql.Identifier(table)
                ),
                (task,),
            ).fetchone() == {"n": 0}
    public = f.client.get(f"/api/v1/tasks/{task}/report")
    assert public.status_code == 200
    assert public.json()["facts"]["requires_review"]
    assert len(public.json()["facts"]["items"]) == 9
    assert f.client.get(f"/api/v1/tasks/{task}/execution").status_code == 409
    assert {"products", "orders"} <= seen
    assert sum(path.endswith("/refunds") for path in seen) == 9
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == MIXED_SHA256
