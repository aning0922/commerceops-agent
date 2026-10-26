"""新 owned PG 的来源登记/ACL/T1/N01 拒绝；不执行 HTTP 或 Woo 采集。"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from commerceops.adapters.commerce.woocommerce_config import WooReadOnlyConfig
from commerceops.application.commerce.source_binding import SourceBindingError, WooSourceMetadata
from commerceops.entrypoints.api import create_app
from commerceops.entrypoints.commerce_source import register_owned_source
from commerceops.infrastructure.commerce_sources import CommerceSourceFiles
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.replenishment_repository import ReplenishmentStore
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from tests.inventory_support import DIRECTORY
from tests.p3_support import ORIGIN, P3Fixture
from tests.test_p3_pg import counts
from tests.test_p3_pg import fixture as fixture
from tests.test_woocommerce_readonly import config as config

pytestmark = pytest.mark.integration


def configure(
    f: P3Fixture, transport_config: WooReadOnlyConfig | None = None
) -> tuple[WooSourceMetadata, Path]:
    data = f.inventory.data
    metadata = WooSourceMetadata(
        organization_id=data.organization,
        shop_id=data.shop,
        config_ref="owned-p5",
        source_config_version="owned-p5-v1",
        origin="https://127.0.0.1:19443",
        external_shop_key=str(data.shop),
        timezone="Asia/Shanghai",
        currency="CNY",
        profile="positive-v1",
        anchor_day=date(2026, 10, 1),
        consumer_key_file=str(f.private / "nonexistent-key"),
        consumer_secret_file=str(f.private / "nonexistent-secret"),
        ca_file=str(f.private / "nonexistent-ca"),
        private_pin_ref="owned-p5-pin",
    )
    if transport_config is not None:
        metadata = metadata.model_copy(
            update={
                "consumer_key_file": transport_config.consumer_key_file,
                "consumer_secret_file": transport_config.consumer_secret_file,
                "ca_file": transport_config.ca_file,
                "origin": transport_config.base_url,
                "anchor_day": date(2026, 10, 26),
            }
        )
    with connect(f.inventory.owner) as db:
        db.execute(
            "UPDATE business.shops SET adapter_kind='woocommerce_test',"
            "external_shop_key=%s,config_ref=%s WHERE id=%s",
            (str(data.shop), metadata.config_ref, data.shop),
        )
    identifier = uuid4()
    registered = register_owned_source(f.inventory.owner, identifier, metadata)
    assert register_owned_source(f.inventory.owner, identifier, metadata) == registered
    path = f.private / f"{identifier}.json"
    path.write_text(metadata.model_dump_json())
    path.chmod(0o600)
    pin_digest = "0" * 64
    if transport_config is not None:
        pin = {
            "schema_version": "p5-private-pins-v1",
            "binding_id": str(identifier),
            "config_digest": metadata.config_digest,
            **{
                name: hashlib.sha256(Path(getattr(metadata, field)).read_bytes()).hexdigest()
                for name, field in (
                    (
                        "key",  # explicit field reference
                        "consumer_key_file",
                    ),
                    (
                        "secret",  # explicit field reference
                        "consumer_secret_file",
                    ),
                    ("ca", "ca_file"),
                )
            },
        }
        encoded = json.dumps(pin).encode()
        manifest = f.private / "owned-p5-pin.pins.json"
        manifest.write_bytes(encoded)
        manifest.chmod(0o600)
        pin_digest = hashlib.sha256(encoded).hexdigest()
    sources = CommerceSourceFiles(
        f.private,
        {(data.organization, data.shop): identifier},
        {"owned-p5-pin": pin_digest},
    )
    f.client.close()
    f.config = replace(f.config, commerce_sources=sources)
    f.store = ReplenishmentStore(f.config, DIRECTORY)
    f.client = TestClient(
        create_app(web_config=f.config, replenishment_store=f.store), base_url=ORIGIN
    )
    f.relogin()
    return metadata, path


def woo_request(f: P3Fixture) -> dict[str, object]:
    request = f.new_cycle()
    request["parameters"] = {
        "source_mode": "woocommerce_test",
        "source_config_version": "owned-p5-v1",
        "L": 3,
        "R": 7,
        "S": 2,
    }
    return request


def test_registration_is_immutable_owner_only_and_scope_bound(fixture: P3Fixture) -> None:
    f = fixture
    metadata, path = configure(f)
    identifier = path.stem
    for query in (
        "UPDATE business.p5_commerce_source_bindings "
        "SET source_config_version='changed' WHERE id=%s",
        "DELETE FROM business.p5_commerce_source_bindings WHERE id=%s",
    ):
        with pytest.raises(psycopg.errors.CheckViolation), connect(f.inventory.owner) as db:
            db.execute(query, (identifier,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege), connect(f.inventory.app) as db:
            db.execute(query, (identifier,))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        register_owned_source(f.inventory.app, uuid4(), metadata)
    with pytest.raises(SourceBindingError):
        register_owned_source(f.inventory.owner, uuid4(), metadata)
    changed = metadata.model_copy(update={"max_requests": 255})
    with pytest.raises(SourceBindingError):
        register_owned_source(f.inventory.owner, UUID(identifier), changed)


def _woo_capability_n01_zero_write_and_atomic_t1_replays(fixture: P3Fixture) -> None:
    f = fixture
    metadata, _ = configure(f)
    capability = f.client.get("/api/v1/config", params={"shop_id": str(metadata.shop_id)})
    assert capability.status_code == 200
    assert capability.json()["config"]["commerce_source"]["creation_enabled"] is True
    before = counts(f)
    result = f.client.post(
        "/api/v1/tasks/preflight",
        headers=f.headers(),
        json={
            "schema_version": "p3-web-v1",
            "source_mode": "woocommerce_test",
            "shop_id": str(metadata.shop_id),
            "source_config_version": metadata.source_config_version,
            "text": "分析库存 L=3 R=7 S=2",
        },
    )
    assert result.status_code == 200, result.text
    preflight = result.json()["preflight"]
    assert preflight["schema_version"] == "p5-n01-web-v1"
    assert preflight["window"]["source"] == "commerce_configuration"
    assert preflight["scope"]["kind"] == "all_shop_products"
    assert counts(f) == before
    request = woo_request(f)
    first = f.create(request)
    for _ in range(10):
        replay = f.create(request)
        assert replay["task_id"] == first["task_id"] and replay["duplicate"] is True
    after = counts(f)
    assert after["business_tasks"] == before["business_tasks"] + 2
    assert after["jobs"] == before["jobs"] + 2
    with connect(f.inventory.app) as db:
        row = db.execute(
            "SELECT * FROM business.p3_task_sources WHERE task_id=%s",
            (first["task_id"],),
        ).fetchone()
        assert row and row["parameters"]["source_config_version"] == metadata.source_config_version
        assert row["parameters"]["organization_id"] == str(metadata.organization_id)
    assert not (f.private / "nonexistent-key").exists()
    with connect(f.inventory.owner) as db:
        db.execute(
            "UPDATE business.principal_role_shop_grants SET enabled=false "
            "WHERE principal_id=%s AND shop_id=%s AND role='operator'",
            (f.actor.principal_id, metadata.shop_id),
        )
    # Permission changes invalidate the old session; use a new current approver session.
    f.relogin()
    read_only = f.client.get("/api/v1/config", params={"shop_id": str(metadata.shop_id)})
    assert read_only.status_code == 200
    assert read_only.json()["config"]["commerce_source"]["creation_enabled"] is False
    denied = f.client.post("/api/v1/tasks", json=woo_request(f), headers=f.headers())
    assert denied.status_code == 403
    assert counts(f) == after


def test_known_woo_drift_and_forged_binding_rejected_without_task_pair(fixture: P3Fixture) -> None:
    f = fixture
    metadata, path = configure(f)
    first = f.create(woo_request(f))
    with pytest.raises(psycopg.errors.CheckViolation), connect(f.inventory.app) as db:
        db.execute(
            "UPDATE business.p3_task_sources SET parameters=parameters||%s WHERE task_id=%s",
            (Jsonb({"source_binding_id": str(uuid4())}), first["task_id"]),
        )
    before = counts(f)
    for field, value in (
        ("origin", "https://127.0.0.1:29443"),
        ("anchor_day", "2026-09-30"),
        ("max_requests", 255),
    ):
        changed = metadata.model_dump(mode="json")
        changed[field] = value
        path.write_text(json.dumps(changed))
        capability = f.client.get("/api/v1/config", params={"shop_id": str(metadata.shop_id)})
        assert capability.status_code == 200
        source = capability.json()["config"]["commerce_source"]
        assert source["source_kind"] == "woocommerce_test" and source["creation_enabled"] is False
        result = f.client.post("/api/v1/tasks", json=woo_request(f), headers=f.headers())
        assert result.status_code == 503
        assert counts(f) == before
    path.write_text(metadata.model_dump_json())
    rejected = f.client.post("/api/v1/tasks", json=f.new_cycle(), headers=f.headers())
    assert rejected.status_code == 404 and counts(f) == before


def _actual_pg_woo_factory_two_graphs_t4_and_original_key_replay(
    fixture: P3Fixture,
    config: WooReadOnlyConfig,
    monkeypatch: pytest.MonkeyPatch,
    *,
    create_task: Callable[[P3Fixture], UUID] | None = None,
) -> UUID:
    import asyncio
    import time
    from typing import Any

    import httpx
    from commerceops.adapters.commerce.woocommerce import WooCommerce
    from commerceops.entrypoints.worker import unavailable_mock
    from commerceops.infrastructure.inventory_repository import InventoryStore
    from commerceops.infrastructure.replenishment_repository import ApprovalStore
    from commerceops.infrastructure.woo_collection import BoundWooCollectorFactory
    from commerceops.infrastructure.worker import Worker
    from commerceops.infrastructure.worker_lock import WorkerSession
    from commerceops.workflows.inventory_analysis import InventoryRunner
    from commerceops.workflows.replenishment import ApprovalRunner

    from tests.test_p3_approval_pg import payload, post
    from tests.test_woocommerce_readonly import order, product, response

    f = fixture
    configure(f, config)
    http_paths: list[str] = []

    def http(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET" and request.url.host == "127.0.0.1"
        path = request.url.path.removeprefix("/wp-json/wc/v3/")
        http_paths.append(path)
        if path == "products":
            rows = [product(stock_quantity=0)]
        elif path == "orders":
            rows = [{**order(quantity=70, total="70.00", total_tax="0.00"), "refunds": []}]
        else:
            assert path == "orders/101/refunds"
            rows = []
        return response(rows, total=len(rows), pages=1 if rows else 0)

    def transport(cfg: WooReadOnlyConfig, **kwargs: Any) -> WooCommerce:
        return WooCommerce(cfg, transport=httpx.MockTransport(http), **kwargs)

    monkeypatch.setattr("commerceops.infrastructure.woo_collection.WooCommerce", transport)
    task = create_task(f) if create_task is not None else UUID(f.create(woo_request(f))["task_id"])

    async def run() -> None:
        session = WorkerSession(f.config.database, f.inventory.data.organization)
        await session.start()
        assert f.config.commerce_sources is not None
        factory = BoundWooCollectorFactory(f.config.database, f.config.commerce_sources)
        analysis = InventoryRunner(
            InventoryStore(f.config.database, session, commerce_sources=f.config.commerce_sources),
            unavailable_mock,
            woo_collector_factory=factory,
        )
        approval = ApprovalRunner(ApprovalStore(f.config, session), woo_collector_factory=factory)

        class Router:
            workflow_versions = analysis.workflow_versions | approval.workflow_versions

            async def run(self, request: Any) -> Any:
                selected = (
                    approval if request.workflow_version in approval.workflow_versions else analysis
                )
                return await selected.run(request)

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
        decision = None
        deadline = time.monotonic() + 40
        try:
            while time.monotonic() < deadline:
                if worker.done():
                    worker.result()
                    raise AssertionError("owned worker exited early")
                with connect(f.inventory.app) as db:
                    row = db.execute(
                        "SELECT state,failure_code FROM business.business_tasks WHERE id=%s",
                        (task,),
                    ).fetchone()
                    ready = db.execute(
                        "SELECT ready_at FROM business.approvals WHERE task_id=%s", (task,)
                    ).fetchone()
                assert row and row["state"] not in ("failed", "needs_attention"), row
                if (
                    row["state"] == "awaiting_approval"
                    and ready
                    and ready["ready_at"]
                    and decision is None
                ):
                    decision = await asyncio.to_thread(payload, f, task, "approve_with_assumptions")
                    assert len(decision["acknowledged_assumption_keys"]) == 1
                    assert (await asyncio.to_thread(post, f, decision)).status_code == 200
                if row["state"] == "completed":
                    assert decision is not None
                    for _ in range(10):
                        assert (await asyncio.to_thread(post, f, decision)).status_code == 200
                    break
                await asyncio.sleep(0.02)
            else:
                raise AssertionError("bounded Woo PG graph deadline")
        finally:
            stop.set()
            await worker

    asyncio.run(run())
    with connect(f.inventory.app) as db:
        execution = db.execute(
            "SELECT count(*) AS n FROM business.executions WHERE task_id=%s", (task,)
        ).fetchone()
        items = db.execute(
            "SELECT quantity FROM business.replenishment_items WHERE task_id=%s", (task,)
        ).fetchall()
        observations = db.execute(
            "SELECT input FROM business.p3_observations WHERE task_id=%s", (task,)
        ).fetchall()
    assert execution == {"n": 1} and items == [{"quantity": 120}]
    assert observations and all(
        row["input"]["source"]["provenance"]["source_kind"] == "woocommerce_test"
        for row in observations
    )
    assert set(http_paths) == {"products", "orders", "orders/101/refunds"}
    detail = f.client.get(f"/api/v1/tasks/{task}/plans/1")
    assert detail.status_code == 200
    assert set(detail.json()["plan"]["parameters"]) == {
        "source_mode",
        "source_config_version",
        "L",
        "R",
        "S",
    }
    return task


def test_actual_pg_woo_factory_two_graphs_t4_and_original_key_replay(
    fixture: P3Fixture,
    config: WooReadOnlyConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import traceback

    try:
        _actual_pg_woo_factory_two_graphs_t4_and_original_key_replay(fixture, config, monkeypatch)
    except BaseException as error:
        print(
            "P5_GRAPH_TEST_FAILURE",
            type(error).__name__,
            [
                (Path(frame.filename).name, frame.name, frame.lineno)
                for frame in traceback.extract_tb(error.__traceback__)
            ],
            flush=True,
        )
        raise


def test_woo_capability_n01_zero_write_and_atomic_t1_replays(fixture: P3Fixture) -> None:
    import traceback

    try:
        _woo_capability_n01_zero_write_and_atomic_t1_replays(fixture)
    except BaseException as error:
        print(
            "P5_CAPABILITY_TEST_FAILURE",
            type(error).__name__,
            [
                (Path(frame.filename).name, frame.name, frame.lineno)
                for frame in traceback.extract_tb(error.__traceback__)
            ],
            flush=True,
        )
        raise


def test_actual_pg_factory_deadline_closes_blocked_read_before_http(
    fixture: P3Fixture,
    config: WooReadOnlyConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio
    import time

    from commerceops.application.replenishment.contracts import WooCreateParameters
    from commerceops.infrastructure import commerce_sources
    from commerceops.infrastructure.woo_collection import BoundWooCollectorFactory

    f = fixture
    metadata, _ = configure(f, config)
    assert f.config.commerce_sources is not None
    with connect(f.inventory.app) as db:
        registered, _ = commerce_sources.resolve_woo_source(
            db,
            f.config.commerce_sources,
            metadata.organization_id,
            metadata.shop_id,
        )
    request = WooCreateParameters(
        source_mode="woocommerce_test",
        source_config_version=metadata.source_config_version,
        L=3,
        R=7,
        S=2,
    ).bind(registered)
    before = counts(f)
    # Actual PostgreSQL wait, no fake result/connection and no business-row mutation.
    monkeypatch.setattr(
        commerce_sources,
        "SOURCE_SQL",
        "SELECT pg_sleep(1) FROM business.p5_commerce_source_bindings "
        "WHERE id=%s AND organization_id=%s AND shop_id=%s",
    )
    monkeypatch.setattr(
        "commerceops.infrastructure.woo_collection.WooCommerce",
        lambda *a, **k: pytest.fail("no HTTP after DB expiry"),
    )

    async def run() -> None:
        tasks = asyncio.all_tasks()
        assert f.config.commerce_sources is not None
        factory = BoundWooCollectorFactory(f.config.database, f.config.commerce_sources)
        start = time.monotonic()
        with pytest.raises((TimeoutError, psycopg.errors.QueryCanceled)):
            await factory(request, absolute_deadline=start + 0.1)
        assert time.monotonic() - start < 0.5
        assert asyncio.all_tasks() == tasks
        # Let the server's matching statement timeout release its read connection.
        await asyncio.sleep(0.15)
        with connect(f.inventory.owner) as db:
            row = db.execute(
                "SELECT count(*) AS n FROM pg_stat_activity WHERE datname=current_database() "
                "AND usename='commerceops_app' AND state='active'"
            ).fetchone()
            assert row == {"n": 0}

    asyncio.run(run())
    assert counts(f) == before
