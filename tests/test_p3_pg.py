"""A01实际PostgreSQL/会话/T1 SIGKILL/T2固定Graph；approval_mode=simulated_web。"""

import asyncio
import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from commerceops.adapters.commerce.mock import Fixture, MockCommerce
from commerceops.application.commerce.collection import InventoryCollector
from commerceops.application.intake import TestInbound as ControlledInbound
from commerceops.application.intake import TrustedTestContext
from commerceops.application.replenishment.contracts import CreateInput
from commerceops.domain.commerce_values import facts_hash, sku_key, stock_pool_key
from commerceops.entrypoints.api import create_app
from commerceops.entrypoints.database import grant_runtime, migrate, setup_checkpointer
from commerceops.infrastructure.checkpoint import checkpointer
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.intake import PgTestIntakeStore
from commerceops.infrastructure.replenishment_repository import ReplenishmentStore
from fastapi.testclient import TestClient
from langchain_core.runnables import RunnableConfig
from psycopg import sql

from tests.inventory_support import DIRECTORY, run_worker
from tests.p3_support import ORIGIN, P3Fixture, P3Process, initialize_p3, run_graphs

pytestmark = pytest.mark.integration


@pytest.fixture
def fixture(tmp_path: Path) -> Iterator[P3Fixture]:
    settings = DatabaseSettings()
    assert settings.runtime_password_file
    name = "p3_a01_" + uuid4().hex
    owner = settings.model_copy(update={"name": name})
    app = owner.model_copy(
        update={"user": "commerceops_app", "password_file": settings.runtime_password_file}
    )
    with psycopg.connect(**settings.kwargs(), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            migrate(owner)
            asyncio.run(setup_checkpointer(owner))
            grant_runtime(owner)
            f = initialize_p3(owner, app, tmp_path)
            try:
                yield f
            finally:
                f.client.close()
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def counts(f: P3Fixture) -> dict[str, int]:
    with connect(f.config.database) as db:
        result = {}
        for table in (
            "business_tasks",
            "jobs",
            "web_requests",
            "replenishment_plans",
            "approvals",
            "outbox",
        ):
            row = db.execute(
                sql.SQL("SELECT count(*) AS n FROM business.{}").format(sql.Identifier(table))
            ).fetchone()
            assert row
            result[table] = row["n"]
        return result


def test_real_session_cookie_csrf_origin_and_no_client_actor(fixture: P3Fixture) -> None:
    f = fixture
    cookie = f.client.cookies.get("commerceops_session")
    assert cookie is not None
    session = f.client.get("/api/v1/auth/session")
    assert session.status_code == 200
    assert session.json()["identity_mode"] == "session"
    assert session.headers["cache-control"] == "no-store"
    before = counts(f)
    payload = f.new_cycle()
    result = f.client.post("/api/v1/tasks", json=payload, headers={"Origin": ORIGIN})
    assert result.status_code == 403 and result.json()["error"]["code"] == "CSRF_INVALID"
    result = f.client.post(
        "/api/v1/tasks",
        json=payload,
        headers={**f.headers(), "Origin": "http://127.0.0.1.attacker.invalid"},
    )
    assert result.status_code == 403
    result = f.client.post(
        "/api/v1/tasks", json={**payload, "actor": str(uuid4())}, headers=f.headers()
    )
    assert result.status_code == 422 and result.json()["schema_version"] == "p3-web-v1"
    assert counts(f) == before


def test_missing_identity_precedes_invalid_body_and_cross_origin_errors(fixture: P3Fixture) -> None:
    f = fixture
    with TestClient(
        create_app(web_config=f.config, replenishment_store=f.store), base_url=ORIGIN
    ) as c:
        result = c.post(
            "/api/v1/tasks", content="broken", headers={"Origin": "http://127.0.0.1:3410"}
        )
        assert result.status_code == 401 and result.json()["error"]["code"] == "SESSION_INVALID"
        assert result.headers["access-control-allow-origin"] == "http://127.0.0.1:3410"
        preflight = c.options(
            "/api/v1/tasks",
            headers={
                "Origin": "http://127.0.0.1:3410",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,x-csrf-token",
            },
        )
        assert preflight.status_code == 200


def test_logout_and_auth_version_revocation_close_session(fixture: P3Fixture) -> None:
    f = fixture
    result = f.client.post(
        "/api/v1/auth/logout", json={"schema_version": "p3-web-v1"}, headers=f.headers()
    )
    assert result.status_code == 200 and result.json()["logged_out"]
    assert f.client.get("/api/v1/auth/session").status_code == 401
    # 同一服务端主体撤权不能凭保存的actor上下文继续调用T1。
    with connect(f.inventory.owner) as db:
        db.execute(
            "UPDATE business.principals SET roles=ARRAY['approver'],"
            "auth_version=auth_version+1 WHERE id=%s",
            (f.actor.principal_id,),
        )
    from commerceops.application.replenishment.contracts import WebFailure
    from pydantic import TypeAdapter

    with pytest.raises(WebFailure) as caught:
        f.store.create(f.actor, TypeAdapter(CreateInput).validate_json(json.dumps(f.new_cycle())))
    assert caught.value.status == 401


def test_new_cycle_repeat_ten_times_is_one_atomic_pair(fixture: P3Fixture) -> None:
    f = fixture
    before = counts(f)
    payload = f.new_cycle()
    first = f.create(payload)
    for _ in range(9):
        repeated = f.create(payload)
        assert (
            repeated["task_id"] == first["task_id"]
            and repeated["source_task_id"] == first["source_task_id"]
        )
        assert repeated["duplicate"]
    after = counts(f)
    assert after["business_tasks"] - before["business_tasks"] == 2
    assert after["jobs"] - before["jobs"] == 2
    assert after["web_requests"] - before["web_requests"] == 1
    changed = {**payload, "parameters": {**payload["parameters"], "S": 4}}
    result = f.client.post("/api/v1/tasks", json=changed, headers=f.headers())
    assert result.status_code == 409 and result.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert counts(f) == after


@pytest.mark.parametrize("mode", ["new_cycle", "from_report"])
def test_concurrent_t1_same_key_creates_one_atomic_request(fixture: P3Fixture, mode: str) -> None:
    from pydantic import TypeAdapter

    f = fixture
    if mode == "from_report":
        source, job = f.inventory.create()
        asyncio.run(run_worker(f.inventory, job))
        payload = f.from_report(source)
    else:
        payload = f.new_cycle()
    request: CreateInput = TypeAdapter(CreateInput).validate_json(json.dumps(payload))
    before = counts(f)
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(f.store.create, f.actor, request) for _ in range(10)]
        receipts = [future.result(timeout=15) for future in futures]
    assert len({receipt["task_id"] for receipt in receipts}) == 1
    assert sum(not receipt["duplicate"] for receipt in receipts) == 1
    after = counts(f)
    expected = 2 if mode == "new_cycle" else 1
    assert after["business_tasks"] - before["business_tasks"] == expected
    assert after["jobs"] - before["jobs"] == expected
    assert after["web_requests"] - before["web_requests"] == 1


def test_from_report_does_not_create_or_mutate_source_task(fixture: P3Fixture) -> None:
    f = fixture
    source, job = f.inventory.create()
    asyncio.run(run_worker(f.inventory, job))
    with connect(f.inventory.owner) as db:
        original = db.execute(
            "SELECT row_to_json(t)::text AS value FROM business.business_tasks t WHERE id=%s",
            (source,),
        ).fetchone()
    before = counts(f)
    payload = f.from_report(source)
    first = f.create(payload)
    for _ in range(9):
        assert f.create(payload)["task_id"] == first["task_id"]
    after = counts(f)
    assert after["business_tasks"] - before["business_tasks"] == 1
    assert after["jobs"] - before["jobs"] == 1
    with connect(f.inventory.owner) as db:
        current = db.execute(
            "SELECT row_to_json(t)::text AS value FROM business.business_tasks t WHERE id=%s",
            (source,),
        ).fetchone()
    assert current == original


@pytest.mark.parametrize("mode", ["new_cycle", "from_report", "inbox"])
def test_r01_commit_before_ack_real_sigkill_replay(fixture: P3Fixture, mode: str) -> None:
    f = fixture
    if mode == "from_report":
        source, job = f.inventory.create()
        asyncio.run(run_worker(f.inventory, job))
        payload = f.from_report(source)
    elif mode == "new_cycle":
        payload = f.new_cycle()
    else:
        payload = {"event_id": str(uuid4()), "message_id": str(uuid4())}
    before = counts(f)
    child = P3Process(f, "inbox" if mode == "inbox" else "create", payload)
    try:
        barrier = child.until("after_commit")
        assert barrier["pid"] == child.process.pid
        child.kill_reap()
        assert child.process.poll() == -9
        if mode == "inbox":
            d = f.inventory.data
            context = TrustedTestContext(
                d.organization, d.shop, d.principal, d.conversation, "test"
            )
            event = ControlledInbound(
                app_id=d.app,
                tenant_key=d.tenant,
                event_id=payload["event_id"],
                message_id=payload["message_id"],
                workflow_version="p103-technical-v1",
                normalized_request={"schema_version": 1},
            )
            first_inbox = PgTestIntakeStore(f.config.database).accept(context, event)
            for _ in range(9):
                assert PgTestIntakeStore(f.config.database).accept(context, event) == first_inbox
        else:
            first = f.create(payload)
            for _ in range(9):
                assert f.create(payload)["task_id"] == first["task_id"]
        after = counts(f)
        expected = 2 if mode == "new_cycle" else 1
        assert after["business_tasks"] - before["business_tasks"] == expected
        assert after["jobs"] - before["jobs"] == expected
        if mode != "inbox":
            assert after["web_requests"] - before["web_requests"] == 1
    finally:
        if child.process.poll() is None:
            child.kill_reap()


@pytest.mark.parametrize("case", ["baseline", "unknown_inbound", "normal", "unknown_stock"])
def test_t2_immutable_plan_and_fixed_pg_interrupt(fixture: P3Fixture, case: str) -> None:
    f = fixture
    receipt = f.create(f.new_cycle(case))
    task = UUID(receipt["task_id"])
    asyncio.run(run_graphs(f, task))
    response = f.client.get(f"/api/v1/tasks/{task}")
    assert response.status_code == 200
    data = response.json()
    with connect(f.config.database) as db:
        row = db.execute("SELECT * FROM business.business_tasks WHERE id=%s", (task,)).fetchone()
        plans = db.execute(
            "SELECT * FROM business.replenishment_plans WHERE task_id=%s", (task,)
        ).fetchall()
        approvals = db.execute(
            "SELECT * FROM business.approvals WHERE task_id=%s", (task,)
        ).fetchall()
        outbox = db.execute("SELECT * FROM business.outbox WHERE task_id=%s", (task,)).fetchall()
    assert row
    if case == "normal":
        assert row["state"] == "completed" and not plans and not approvals and not outbox
        assert data["task"]["outcome"] == "no_action"
    elif case == "unknown_stock":
        assert row["state"] == "failed" and row["failure_code"] == "DATA_INCOMPLETE"
        assert not plans and not approvals and not outbox
    else:
        assert (
            row["state"] == "awaiting_approval" and len(plans) == len(approvals) == len(outbox) == 1
        )
        assert outbox[0]["status"] == "pending" and not outbox[0]["sender_enabled"]
        assert approvals[0]["ready_at"] is not None
        detail = f.client.get(f"/api/v1/approvals/{approvals[0]['id']}").json()
        assert bool(detail["nonce"]) and detail["approval"]["can_decide"]
        if case == "unknown_inbound":
            assert detail["plan"]["items"][0]["raw_inbound_units"] is None
            assert len(detail["plan"]["required_assumptions"]) == 1

        async def checkpoint() -> None:
            async with checkpointer(f.config.database) as saver:
                cfg: RunnableConfig = {"configurable": {"thread_id": str(task)}}
                saved = await saver.aget_tuple(cfg)
                assert saved
                assert saved.checkpoint["channel_values"]["approval_id"] == str(approvals[0]["id"])

        asyncio.run(checkpoint())


def test_list_count_pagination_and_hidden_object_equal(fixture: P3Fixture) -> None:
    f = fixture
    for _ in range(3):
        f.create(f.new_cycle())
    first = f.client.get("/api/v1/tasks?limit=1").json()
    assert first["total"] == 6 and sum(first["counts"].values()) == 6
    assert len(first["items"]) == 1 and first["next_cursor"]
    next_page = f.client.get(
        "/api/v1/tasks", params={"limit": 1, "cursor": first["next_cursor"]}
    ).json()
    assert (
        next_page["total"] == first["total"]
        and next_page["items"][0]["task_id"] != first["items"][0]["task_id"]
    )
    tampered = f.client.get(
        "/api/v1/tasks", params={"limit": 1, "cursor": first["next_cursor"] + "x"}
    )
    assert tampered.status_code == 400
    missing = f.client.get(f"/api/v1/tasks/{uuid4()}")
    # 同主体的technical fixture同样不在P3公开task kind中。
    hidden = f.client.get(f"/api/v1/tasks/{f.inventory.data.task}")
    assert missing.status_code == hidden.status_code == 404
    for body in (missing.json(), hidden.json()):
        assert set(body) == {"schema_version", "server_time", "trace_id", "error"}
        assert body["error"]["code"] == "RESOURCE_NOT_FOUND" and body["error"]["receipt"] is None


def test_t2_ten_replays_use_one_plan_approval_card_and_audit(fixture: P3Fixture) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle())["task_id"])
    asyncio.run(run_graphs(f, task, repeat_prepare=10))
    actual = counts(f)
    assert actual["replenishment_plans"] == actual["approvals"] == actual["outbox"] == 1
    with connect(f.config.database) as db:
        audit = db.execute(
            "SELECT count(*) AS n FROM business.audit_events "
            "WHERE task_id=%s AND action='approval_prepared'",
            (task,),
        ).fetchone()
    assert audit and audit["n"] == 1


def test_t2_precommit_failure_rolls_back_all_three_effects(fixture: P3Fixture) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle())["task_id"])
    visits = 0

    async def fault(point: str) -> None:
        nonlocal visits
        if point != "before_t2_commit":
            return
        visits += 1
        current = counts(f)
        assert current["replenishment_plans"] == current["approvals"] == current["outbox"] == 0
        if visits == 1:
            raise RuntimeError("controlled_t2_precommit_rollback")

    asyncio.run(run_graphs(f, task, store_hook=fault))
    assert visits == 2
    current = counts(f)
    assert current["replenishment_plans"] == current["approvals"] == current["outbox"] == 1


def test_twenty_one_candidates_are_rejected_without_truncation(fixture: P3Fixture) -> None:
    f = fixture
    baseline = Fixture.load(DIRECTORY)
    provenance = baseline.source.provenance.model_copy(
        update={
            "fixture_version": "p3-owned-capacity-v1",
            "raw_hash": facts_hash({"controlled_fixture": "p3-owned-capacity-v1"}),
        }
    )
    source = baseline.source.model_copy(update={"provenance": provenance})
    products, orders, inventories = [], [], []
    for number in range(21):
        product_id = "capacity-" + str(number)
        key = sku_key(source.shop_id, product_id, None)
        pool = stock_pool_key(source.shop_id, product_id)
        products.append(
            baseline.products[0].model_copy(
                update={
                    "product_id": product_id,
                    "sku_key": key,
                    "stock_pool_key": pool,
                    "source": provenance,
                }
            )
        )
        orders.append(
            baseline.orders[0].model_copy(
                update={
                    "order_id": "capacity-order-" + str(number),
                    "sku_key": key,
                    "source": provenance,
                }
            )
        )
        inventories.append(
            baseline.inventories[0].model_copy(
                update={"sku_key": key, "stock_pool_key": pool, "source": provenance}
            )
        )
    controlled = replace(
        baseline,
        source=source,
        products=tuple(products),
        orders=tuple(orders),
        inventories=tuple(inventories),
    )
    collector = InventoryCollector(MockCommerce(controlled), source, baseline.now)
    task = UUID(f.create(f.new_cycle())["task_id"])
    asyncio.run(run_graphs(f, task, factory=lambda request: collector))
    current = counts(f)
    assert current["replenishment_plans"] == current["approvals"] == current["outbox"] == 0
    with connect(f.config.database) as db:
        rejected = db.execute(
            "SELECT state,failure_code FROM business.business_tasks WHERE id=%s", (task,)
        ).fetchone()
        report = db.execute(
            "SELECT r.report FROM business.p3_task_sources s JOIN business.analysis_reports r "
            "ON r.task_id=s.source_task_id WHERE s.task_id=%s",
            (task,),
        ).fetchone()
    assert (
        rejected and rejected["state"] == "failed" and rejected["failure_code"] == "SCOPE_REQUIRED"
    )
    assert report and report["report"]["candidate_count"] == 21
    assert report["report"]["source"]["provenance"]["fixture_version"] == "p3-owned-capacity-v1"


def test_login_rotates_session_and_cookie_attributes(fixture: P3Fixture) -> None:
    f = fixture
    previous = f.client.cookies.get("commerceops_session")
    f.relogin()
    changed = previous != f.client.cookies.get("commerceops_session")
    assert changed
    with TestClient(
        create_app(web_config=f.config, replenishment_store=f.store), base_url=ORIGIN
    ) as other:
        other.cookies.set("commerceops_session", previous or "")
        assert other.get("/api/v1/auth/session").status_code == 401
    bootstrap = f.client.get("/api/v1/auth/csrf")
    assert bootstrap.json()["identity_mode"] == "session"
    with connect(f.config.database) as db:
        row = db.execute(
            "SELECT token_hash FROM business.web_sessions WHERE id=%s", (f.actor.session_id,)
        ).fetchone()
    assert row
    stored_as_digest = len(row["token_hash"]) == 64 and row["token_hash"] != f.client.cookies.get(
        "commerceops_session"
    )
    assert stored_as_digest


@pytest.mark.parametrize("column", ["absolute_expires_at", "idle_expires_at"])
def test_real_session_expiry_is_generic_and_does_not_write_task(
    fixture: P3Fixture, column: str
) -> None:
    f = fixture
    before = counts(f)
    with connect(f.inventory.owner) as db:
        # 将整个会话窗口移至过去，仍保持expires>created约束。
        db.execute(
            sql.SQL(
                "UPDATE business.web_sessions SET created_at=clock_timestamp()-interval '2 hours', "
                "{}=clock_timestamp()-interval '1 minute' WHERE id=%s"
            ).format(sql.Identifier(column)),
            (f.actor.session_id,),
        )
    response = f.client.post(
        "/api/v1/tasks", json=f.new_cycle(), headers={"Origin": ORIGIN, "X-CSRF-Token": "invalid"}
    )
    assert response.status_code == 401 and response.json()["error"]["code"] == "SESSION_INVALID"
    assert counts(f) == before


def test_role_bound_scope_cannot_join_operator_shop_a_with_approver_shop_b(
    fixture: P3Fixture,
) -> None:
    f = fixture
    other = uuid4()
    with connect(f.inventory.owner) as db:
        db.execute(
            "SELECT 1 FROM business.principals WHERE id=%s FOR UPDATE", (f.actor.principal_id,)
        )
        db.execute(
            "DELETE FROM business.principal_role_shop_grants "
            "WHERE principal_id=%s AND role='approver'",
            (f.actor.principal_id,),
        )
        db.execute(
            """INSERT INTO business.shops
        (id,organization_id,adapter_kind,external_shop_key,timezone,currency,config_ref,environment)
        VALUES (%s,%s,'mock',%s,'Asia/Shanghai','CNY','owned-p3','test')""",
            (other, f.actor.organization_id, str(uuid4())),
        )
        db.execute(
            "INSERT INTO business.principal_shop_scopes VALUES (%s,%s,%s,true)",
            (f.actor.organization_id, other, f.actor.principal_id),
        )
        db.execute(
            "INSERT INTO business.principal_role_shop_grants VALUES (%s,%s,%s,'approver',true)",
            (f.actor.organization_id, other, f.actor.principal_id),
        )
    assert f.client.get("/api/v1/auth/session").status_code == 401
    f.relogin()
    payload = {**f.new_cycle(), "shop_id": str(other)}
    denied = f.client.post("/api/v1/tasks", json=payload, headers=f.headers())
    assert denied.status_code == 404
    allowed = f.create(f.new_cycle())
    asyncio.run(run_graphs(f, UUID(allowed["task_id"])))
    with connect(f.config.database) as db:
        row = db.execute(
            "SELECT eligible_principal_ids FROM business.approvals WHERE task_id=%s",
            (UUID(allowed["task_id"]),),
        ).fetchone()
    assert row and f.actor.principal_id not in row["eligible_principal_ids"]


def test_admin_only_has_safe_home_and_no_object_or_count_access(fixture: P3Fixture) -> None:
    f = fixture
    with connect(f.inventory.owner) as db:
        db.execute(
            "UPDATE business.principals SET roles=ARRAY['admin'],"
            "auth_version=auth_version+1 WHERE id=%s",
            (f.actor.principal_id,),
        )
        db.execute(
            "INSERT INTO business.principal_role_shop_grants VALUES (%s,%s,%s,'admin',true)",
            (f.actor.organization_id, f.inventory.data.shop, f.actor.principal_id),
        )
    f.relogin()
    session = f.client.get("/api/v1/auth/session").json()
    assert session["principal"]["capabilities"]["home_path"] == "/admin/operations"
    for path in (
        "/api/v1/tasks",
        "/api/v1/tasks/not-a-uuid",
        f"/api/v1/tasks/{uuid4()}",
        "/api/v1/approvals",
    ):
        denied = f.client.get(path)
        assert denied.status_code == 403
        assert set(denied.json()) == {"schema_version", "server_time", "trace_id", "error"}
    operations = f.client.get("/api/v1/admin/operations")
    assert operations.status_code == 200
    assert not {"task_id", "shop_id", "sku_key", "count", "nonce", "principal_id"}.intersection(
        operations.json()
    )


def test_read_config_version_history_events_and_approval_counts(fixture: P3Fixture) -> None:
    f = fixture
    created = f.create(f.new_cycle("unknown_inbound"))
    task = created["task_id"]
    asyncio.run(run_graphs(f, UUID(task)))
    config = f.client.get("/api/v1/config", params={"shop_id": str(f.inventory.data.shop)})
    assert config.status_code == 200
    assert config.json()["config"]["approval_ttl_seconds"] == 86400
    assert config.json()["config"]["revalidation_max_age_seconds"] == 900
    versions = f.client.get(f"/api/v1/tasks/{task}/plans").json()
    assert versions["total"] == 1 and versions["current_plan_version"] == 1
    first = f.client.get(f"/api/v1/tasks/{task}/events?limit=1").json()
    assert first["items"][0]["action"] == "workflow_created" and first["next_cursor"]
    pages = [first]
    cursor = first["next_cursor"]
    cursors = {cursor}
    # 原query允许<=100，完整分页与同一来源的完整响应对照，不猜某一页就是终页。
    for _ in range(99):
        following = f.client.get(
            f"/api/v1/tasks/{task}/events", params={"limit": 1, "cursor": cursor}
        ).json()
        assert len(following["items"]) == 1
        pages.append(following)
        cursor = following["next_cursor"]
        if cursor is None:
            break
        assert cursor not in cursors
        cursors.add(cursor)
    else:
        raise AssertionError("owned event pagination did not terminate within 100 pages")
    events = [page["items"][0] for page in pages]
    complete = f.client.get(f"/api/v1/tasks/{task}/events", params={"limit": 100}).json()
    assert complete["next_cursor"] is None and complete["items"] == events
    assert len({event["event_id"] for event in events}) == len(events)
    assert [event["action"] for event in events] == [
        "workflow_created",
        "analysis_started",
        "analysis_report_saved",
        "approval_prepared",
        "approval_checkpoint_ready",
    ]
    report_id = f.client.get(f"/api/v1/tasks/{task}/report").json()["source"]["report_id"]
    approval_id = f.client.get("/api/v1/approvals?view=mine").json()["items"][0]["approval_id"]
    bindings = {
        "workflow_created": ("task", task),
        "analysis_started": ("task", created["source_task_id"]),
        "analysis_report_saved": ("report", report_id),
        "approval_prepared": ("plan", versions["items"][0]["plan_id"]),
        "approval_checkpoint_ready": ("approval", approval_id),
    }
    for event in events:
        relation = "source" if event["action"].startswith("analysis_") else "task"
        related = created["source_task_id"] if relation == "source" else task
        kind, result_id = bindings[event["action"]]
        assert event["relation"] == relation and event["task_id"] == related
        assert event["result_ref"] == result_id
        assert event["references"] == [
            {"kind": "task", "id": related},
            {"kind": kind, "id": result_id},
        ]
        if event["action"] == "approval_checkpoint_ready":
            assert event["tool"] is None
        else:
            assert event["tool"]["category"] == "deterministic"
            assert event["tool"]["selected_by_model"] is False
    listed = f.client.get("/api/v1/approvals?view=mine").json()
    assert listed["total"] == 1 and listed["counts"]["pending"] == 1 and len(listed["items"]) == 1
    history = f.client.get("/api/v1/approvals?view=history").json()
    assert history["total"] == 0 and all(v == 0 for v in history["counts"].values())
    missing = f.client.get(
        f"/api/v1/tasks/{task}/explanation",
        params={
            "report_id": f.client.get(f"/api/v1/tasks/{task}/report").json()["source"]["report_id"]
        },
    )
    assert missing.status_code == 409 and missing.json()["error"]["code"] == "NOT_READY"


def test_database_plan_and_source_evidence_remain_immutable(fixture: P3Fixture) -> None:
    f = fixture
    created = f.create(f.new_cycle())
    task = UUID(created["task_id"])
    asyncio.run(run_graphs(f, task))
    with connect(f.inventory.owner) as db:
        row = db.execute(
            "SELECT id FROM business.replenishment_plans WHERE task_id=%s", (task,)
        ).fetchone()
    assert row
    with pytest.raises(psycopg.errors.CheckViolation), connect(f.inventory.owner) as db:
        db.execute(
            "UPDATE business.replenishment_plans "
            "SET expires_at=expires_at+interval '1 hour' WHERE id=%s",
            (row["id"],),
        )
    with pytest.raises(psycopg.errors.CheckViolation), connect(f.inventory.owner) as db:
        db.execute(
            "UPDATE business.p3_task_sources SET parameters='{}'::jsonb WHERE task_id=%s", (task,)
        )
    with pytest.raises(psycopg.errors.CheckViolation), connect(f.inventory.owner) as db:
        db.execute("TRUNCATE business.replenishment_plans CASCADE")
    with connect(f.config.database) as db:
        count = db.execute(
            "SELECT count(*) AS n FROM business.replenishment_plans WHERE task_id=%s", (task,)
        ).fetchone()
        assert count and count["n"] == 1


def test_database_cannot_complete_p3_before_bound_no_action_facts(fixture: P3Fixture) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle())["task_id"])
    with pytest.raises(psycopg.errors.CheckViolation), connect(f.config.database) as db:
        db.execute("UPDATE business.business_tasks SET state='completed' WHERE id=%s", (task,))
    asyncio.run(run_graphs(f, task))
    with pytest.raises(psycopg.errors.CheckViolation), connect(f.config.database) as db:
        db.execute("UPDATE business.business_tasks SET state='completed' WHERE id=%s", (task,))


@pytest.mark.parametrize("target", ["principal", "base_scope", "role_scope", "credentials"])
def test_current_revocation_invalidates_live_cookie(fixture: P3Fixture, target: str) -> None:
    f = fixture
    before = counts(f)
    queries = {
        "principal": "UPDATE business.principals SET enabled=false,"
        "auth_version=auth_version+1 WHERE id=%s",
        "base_scope": "UPDATE business.principal_shop_scopes SET enabled=false "
        "WHERE principal_id=%s",
        "role_scope": "UPDATE business.principal_role_shop_grants SET enabled=false "
        "WHERE principal_id=%s AND role='operator'",
        "credentials": "UPDATE business.web_credentials SET enabled=false WHERE principal_id=%s",
    }
    with connect(f.inventory.owner) as db:
        # 配置管理员遵守principal先锁；runtime没有这些配置表的写权限。
        db.execute(
            "SELECT id FROM business.principals WHERE id=%s FOR UPDATE", (f.actor.principal_id,)
        )
        db.execute(queries[target], (f.actor.principal_id,))
    result = f.client.get("/api/v1/auth/session")
    assert result.status_code == 401 and result.json()["error"]["code"] == "SESSION_INVALID"
    assert counts(f) == before


def test_login_rate_limit_is_persistent_and_generic(fixture: P3Fixture) -> None:
    f = fixture
    for expected in (401, 401, 401, 401, 429):
        result = f.client.post(
            "/api/v1/auth/login",
            json={"schema_version": "p3-web-v1", "login": f.login, "password": "incorrect-test"},
            headers=f.headers(),
        )
        assert result.status_code == expected
        assert result.json()["error"]["code"] == (
            "RATE_LIMITED" if expected == 429 else "LOGIN_FAILED"
        )
    assert result.headers["retry-after"] == "300"
    # 失败登录不能撤销原来合法的会话。
    assert f.client.get("/api/v1/auth/session").status_code == 200


def test_disabled_writes_have_safe_error_envelope_and_no_effect(fixture: P3Fixture) -> None:
    f = fixture
    before = counts(f)
    result = f.client.post(
        f"/api/v1/approvals/{uuid4()}/decision", json={"actor": "untrusted"}, headers=f.headers()
    )
    assert result.status_code == 404 and result.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert not f.client.get("/api/v1/auth/session").json()["principal"]["capabilities"][
        "can_resolve_items"
    ]
    assert counts(f) == before


@pytest.mark.parametrize("mode", ["local_http", "https"])
def test_cookie_security_attributes_and_logout_expiration(fixture: P3Fixture, mode: str) -> None:
    f = fixture
    origin = "https://127.0.0.1" if mode == "https" else ORIGIN
    config = replace(f.config, origins=(origin,), transport_mode=mode)
    store = ReplenishmentStore(config, DIRECTORY)
    with TestClient(create_app(web_config=config, replenishment_store=store), base_url=origin) as c:
        bootstrap = c.get("/api/v1/auth/csrf")
        logged_in = c.post(
            "/api/v1/auth/login",
            json={
                "schema_version": "p3-web-v1",
                "login": f.login,
                "password": f.password.get_secret_value(),
            },
            headers={"Origin": origin, "X-CSRF-Token": bootstrap.json()["csrf_token"]},
        )
        assert logged_in.status_code == 200
        for result in (bootstrap, logged_in):
            header = result.headers["set-cookie"].lower()
            flags = (
                "httponly" in header,
                "samesite=lax" in header,
                "path=/" in header,
                "domain=" not in header,
                ("secure" in header) == (mode == "https"),
            )
            assert all(flags)
        logged_out = c.post(
            "/api/v1/auth/logout",
            json={"schema_version": "p3-web-v1"},
            headers={"Origin": origin, "X-CSRF-Token": logged_in.json()["csrf_token"]},
        )
        assert logged_out.status_code == 200
        expired = "max-age=0" in logged_out.headers["set-cookie"].lower()
        assert expired
        assert c.get("/api/v1/auth/session").status_code == 401
