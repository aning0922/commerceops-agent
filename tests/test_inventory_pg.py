"""P203 真实 PG、真实单 Worker/Graph、模拟身份与受控 OS 恢复。"""

import asyncio
import base64
import json
import signal
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from commerceops.adapters.commerce.mock import Fixture, MockCommerce
from commerceops.application.commerce.analysis_task import InventoryTaskRequest
from commerceops.application.commerce.collection import InventoryCollector
from commerceops.application.commerce.contracts import Quality
from commerceops.entrypoints.api import create_app
from commerceops.entrypoints.database import grant_runtime, migrate, setup_checkpointer
from commerceops.infrastructure.checkpoint import checkpointer
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.inventory_repository import InventoryReadStore, create_analysis_task
from commerceops.infrastructure.repository import TaskRepository, TaskScope
from commerceops.infrastructure.worker_lock import (
    TerminationRequired,
    WorkerSession,
    confirm_termination,
)
from fastapi.testclient import TestClient
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import empty_checkpoint
from psycopg import sql
from psycopg.types.json import Jsonb

from tests.inventory_support import (
    DIRECTORY,
    InventoryFixture,
    InventoryProcess,
    initialize,
    run_worker,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def fixture() -> Iterator[InventoryFixture]:
    settings = DatabaseSettings()
    assert settings.runtime_password_file
    name = "p203_" + uuid4().hex
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
            yield initialize(owner, app)
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def client(f: InventoryFixture, identity: Any = None) -> TestClient:
    return TestClient(
        create_app(
            inventory_store=InventoryReadStore(f.app),
            identity_resolver=lambda _: identity or f.identity,
        )
    )


def test_actual_worker_atomic_report_readback(fixture: InventoryFixture) -> None:
    f = fixture
    task, job = f.create()
    c = client(f)
    assert c.get(f"/tasks/{task}/report").status_code == 409
    asyncio.run(run_worker(f, job))
    result = c.get(f"/tasks/{task}/report")
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["facts"]["items"][0]["D"] == {"numerator": "10", "denominator": "1"}
    assert body["analysis_only"] and not body["execution_available"]
    assert f.row(task)["state"] == "completed" and f.counts(task) == (1, 1)
    with connect(f.app) as db:
        report = db.execute(
            "SELECT * FROM business.analysis_reports WHERE task_id=%s", (task,)
        ).fetchone()
        snapshot = db.execute(
            "SELECT * FROM business.commerce_snapshots WHERE task_id=%s", (task,)
        ).fetchone()
        assert report and snapshot
        assert body["facts"]["facts_hash"] == report["facts_hash"]
        assert body["content_hash"] == snapshot["content_hash"]
        amount = db.execute(
            """SELECT net_amount,tax_amount,payload FROM business.snapshot_order_lines
            WHERE task_id=%s""",
            (task,),
        ).fetchone()
        assert amount and str(amount["net_amount"]) == "10.500000"
        assert amount["payload"]["net_amount"] == "10.5"
        assert f.row(task)["active_plan_id"] is None
    events = c.get(f"/tasks/{task}/events").json()
    assert [e["action"] for e in events["items"]] == ["analysis_started", "analysis_report_saved"]


@pytest.mark.parametrize("point", ["after_snapshot", "after_report", "before_commit"])
def test_transaction_fault_rolls_back_evidence(fixture: InventoryFixture, point: str) -> None:
    f = fixture
    task, job = f.create()

    async def fail(where: str) -> None:
        if where == point:
            raise ValueError("controlled rollback fault")

    asyncio.run(run_worker(f, job, store_hook=fail))
    assert f.counts(task) == (0, 0)
    assert f.row(task)["state"] == "failed"
    assert client(f).get(f"/tasks/{task}/report").status_code == 409


@pytest.mark.parametrize("case", ["unknown_stock", "unknown_inbound", "open_item"])
def test_incomplete_is_explanation_report(fixture: InventoryFixture, case: str) -> None:
    f = fixture
    task, job = f.create(case)
    asyncio.run(run_worker(f, job))
    response = client(f).get(f"/tasks/{task}/report")
    assert response.status_code == 200, response.text
    body = response.json()
    assert f.row(task)["state"] == "completed"
    assert body["outcome"] == "report_ready"
    assert body["facts"]["requires_review"] and not body["facts"]["execution_available"]
    if case == "unknown_stock":
        assert not body["facts"]["complete"]


@pytest.mark.parametrize(
    "roles,status",
    [(["operator"], 200), (["operator", "approver"], 200), (["approver"], 403), (["admin"], 403)],
)
def test_current_roles_not_client_claims(
    fixture: InventoryFixture, roles: list[str], status: int
) -> None:
    f = fixture
    task, _ = f.create()
    with connect(f.owner) as db:
        db.execute(
            "UPDATE business.principals SET roles=%s,auth_version=auth_version+1 WHERE id=%s",
            (roles, f.data.principal),
        )
    current = replace(f.identity, auth_version=2)
    assert (
        client(f, current).get(f"/tasks/{task}", headers={"X-Role": "admin"}).status_code == status
    )
    assert client(f).get(f"/tasks/{task}").status_code == 403


@pytest.mark.parametrize("change", ["scope", "enabled", "identity"])
def test_each_derivative_rechecks_revocation(fixture: InventoryFixture, change: str) -> None:
    f = fixture
    task, job = f.create()
    asyncio.run(run_worker(f, job))
    c = client(f)
    assert c.get(f"/tasks/{task}/report").status_code == 200
    with connect(f.owner) as db:
        if change == "scope":
            db.execute(
                "UPDATE business.principal_shop_scopes SET enabled=false WHERE principal_id=%s",
                (f.data.principal,),
            )
        elif change == "enabled":
            db.execute(
                """UPDATE business.principals SET
                enabled=false,auth_version=auth_version+1 WHERE id=%s""",
                (f.data.principal,),
            )
        else:
            db.execute("DELETE FROM business.identities WHERE id=%s", (f.identity.identity_id,))
    for suffix in ("", "/report", "/events"):
        assert c.get(f"/tasks/{task}" + suffix).status_code == 403


def test_scoped_not_found_and_events_cursor(fixture: InventoryFixture) -> None:
    f = fixture
    task, job = f.create()
    asyncio.run(run_worker(f, job))
    other = initialize(f.owner, f.app)
    c = client(other)
    for suffix in ("", "/report", "/events"):
        hidden = c.get(f"/tasks/{task}" + suffix)
        missing = c.get(f"/tasks/{uuid4()}" + suffix)
        assert hidden.status_code == missing.status_code == 404
        assert hidden.json() == missing.json()
    c = client(f)
    first = c.get(f"/tasks/{task}/events?limit=1").json()
    assert len(first["items"]) == 1 and first["next_cursor"]
    second = c.get(
        f"/tasks/{task}/events", params={"limit": 1, "cursor": first["next_cursor"]}
    ).json()
    assert len(second["items"]) == 1 and second["next_cursor"] is None
    assert first["items"][0]["id"] != second["items"][0]["id"]
    with connect(f.owner) as db:
        db.execute(
            """INSERT INTO business.audit_events
            (id,organization_id,task_id,source,action,entity_type,entity_id,after_state,trace_id)
            VALUES (%s,%s,%s,'inventory_analysis','analysis_failed','task',%s,%s,%s)""",
            (
                uuid4(),
                f.data.organization,
                task,
                str(task),
                Jsonb(
                    {
                        "state": "sensitive-original",
                        "snapshot_id": "raw-secret",
                        "code": "raw-secret",
                        "message": "original message",
                        "outcome": "raw-secret",
                    }
                ),
                uuid4(),
            ),
        )
    clean = c.get(f"/tasks/{task}/events").text
    assert "raw-secret" not in clean and "original message" not in clean
    for cursor in ("bad", "a" * 2049, first["next_cursor"].rstrip("=") + "!"):
        assert c.get(f"/tasks/{task}/events", params={"cursor": cursor}).status_code == 400
    decoded = json.loads(base64.urlsafe_b64decode(first["next_cursor"]))
    decoded[1] = str(uuid4())
    wrong = base64.urlsafe_b64encode(json.dumps(decoded).encode()).decode()
    assert c.get(f"/tasks/{task}/events", params={"cursor": wrong}).status_code == 400
    invalid_ids: tuple[object, ...] = (None, True, 1, [])
    for replacement in invalid_ids:
        decoded[1] = str(task)
        decoded[7] = replacement
        invalid = base64.urlsafe_b64encode(json.dumps(decoded).encode()).decode()
        assert c.get(f"/tasks/{task}/events", params={"cursor": invalid}).status_code == 400
    with connect(f.owner) as db:
        db.execute(
            """INSERT INTO business.audit_events
            (id,organization_id,task_id,source,action,entity_type,entity_id,after_state,trace_id)
            VALUES (%s,%s,%s,'inventory_analysis','analysis_failed','task',%s,%s,%s)""",
            (uuid4(), f.data.organization, task, str(task), Jsonb(["raw-secret"]), uuid4()),
        )
    assert "raw-secret" not in c.get(f"/tasks/{task}/events").text
    assert c.get(f"/tasks/{task}/events?limit=0").status_code == 400
    assert c.get(f"/tasks/{task}/events?limit=101").status_code == 400


def test_safe_database_unavailable(fixture: InventoryFixture) -> None:
    f = fixture
    unavailable = f.app.model_copy(update={"name": "p203_missing_" + uuid4().hex})
    c = TestClient(
        create_app(
            inventory_store=InventoryReadStore(unavailable), identity_resolver=lambda _: f.identity
        )
    )
    response = c.get(f"/tasks/{uuid4()}")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert unavailable.name not in response.text and "SELECT" not in response.text


def test_revoke_during_collection_prevents_commit(fixture: InventoryFixture) -> None:
    f = fixture
    task, job = f.create()

    async def revoke(point: str) -> None:
        if point == "before_collection":
            with connect(f.owner) as db:
                db.execute(
                    "UPDATE business.principal_shop_scopes SET enabled=false WHERE principal_id=%s",
                    (f.data.principal,),
                )

    asyncio.run(run_worker(f, job, hook=revoke))
    assert f.counts(task) == (0, 0) and f.row(task)["state"] == "needs_attention"


def test_runtime_least_privilege_and_evidence_immutable(fixture: InventoryFixture) -> None:
    f = fixture
    task, job = f.create()
    asyncio.run(run_worker(f, job))
    with connect(f.app) as db:
        for table in (
            "commerce_snapshots",
            "snapshot_products",
            "snapshot_order_lines",
            "snapshot_refunds",
            "analysis_reports",
        ):
            for privilege in ("UPDATE", "DELETE", "TRUNCATE"):
                row = db.execute(
                    "SELECT has_table_privilege(current_user,%s,%s) AS allowed",
                    ("business." + table, privilege),
                ).fetchone()
                assert row and not row["allowed"]
        permission = db.execute(
            """SELECT
            has_table_privilege(current_user,'business.principal_shop_scopes','UPDATE')
            AS allowed"""
        ).fetchone()
        assert permission and not permission["allowed"]
    with connect(f.owner) as db:
        for statement in (
            "UPDATE business.analysis_reports SET outcome=outcome WHERE task_id=%s",
            "DELETE FROM business.commerce_snapshots WHERE task_id=%s",
        ):
            with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
                db.execute(statement, (task,))
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute("TRUNCATE business.snapshot_refunds")
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute("UPDATE business.business_tasks SET state='queued' WHERE id=%s", (task,))
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(
                "UPDATE business.business_tasks SET normalized_request='{}' WHERE id=%s", (task,)
            )
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(
                """INSERT INTO business.snapshot_order_lines SELECT
                snapshot_id,organization_id,shop_id,task_id,'owned-new',line_id,sku_key,status,created_at_source,paid_at,completed_at,quantity,1.0000001,tax_amount,currency,jsonb_set(payload,'{net_amount}','\"1.0000001\"')
                FROM business.snapshot_order_lines WHERE task_id=%s""",
                (task,),
            )
        with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
            db.execute(
                """INSERT INTO business.snapshot_order_lines SELECT
                snapshot_id,organization_id,%s,task_id,'owned-cross',line_id,sku_key,status,created_at_source,paid_at,completed_at,quantity,net_amount,tax_amount,currency,payload
                FROM business.snapshot_order_lines WHERE task_id=%s""",
                (uuid4(), task),
            )


def test_missing_checkpoint_never_starts_new_graph(fixture: InventoryFixture) -> None:
    f = fixture
    task, job = f.create()
    with connect(f.owner) as db:
        db.execute("UPDATE business.business_tasks SET state='analyzing' WHERE id=%s", (task,))
    asyncio.run(run_worker(f, job))
    assert f.row(task)["state"] == "needs_attention" and f.counts(task) == (0, 0)
    with connect(f.app) as db:
        checkpoint = db.execute(
            "SELECT count(*) AS n FROM checkpoints.checkpoints WHERE thread_id=%s", (str(task),)
        ).fetchone()
        assert checkpoint and checkpoint["n"] == 0


def test_controlled_process_commit_gap_reuses_receipt(fixture: InventoryFixture) -> None:
    f = fixture
    task, job = f.create()
    first = InventoryProcess(f, "report_committed")
    second = None
    try:
        started = first.until("started")
        first.until("report_committed")
        before = client(f).get(f"/tasks/{task}/report").json()
        assert f.counts(task) == (1, 1) and f.row(task)["state"] == "completed"
        first.process.kill()
        assert first.process.wait(timeout=15) == -signal.SIGKILL

        async def blocked() -> None:
            s = WorkerSession(f.app, f.data.organization)
            with pytest.raises(TerminationRequired):
                await s.start()

        asyncio.run(blocked())
        assert f.row(task)["state"] == "completed"  # 窄保护只认匹配的持久报告。
        asyncio.run(
            confirm_termination(f.app, started["owner"], "P203 parent wait SIGKILL evidence")
        )
        second = InventoryProcess(f)
        second.until("started")
        second.until("persistent_replay")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with connect(f.app) as db:
                status = db.execute(
                    "SELECT status FROM business.jobs WHERE id=%s", (job,)
                ).fetchone()
            if status and status["status"] == "done":
                break
            time.sleep(0.01)
        else:
            raise AssertionError("job replay acknowledgement timed out")
        after = client(f).get(f"/tasks/{task}/report").json()
        assert after == before and f.counts(task) == (1, 1)
        second.process.send_signal(signal.SIGTERM)
        second.until("stopped")
        assert second.process.wait(timeout=15) == 0
    finally:
        first.close()
        if second:
            second.close()


@pytest.mark.parametrize("case", ["normal", "empty_products", "empty_orders"])
def test_complete_no_suggestion_no_action(fixture: InventoryFixture, case: str) -> None:
    f = fixture
    task, job = f.create(case)
    asyncio.run(run_worker(f, job))
    body = client(f).get(f"/tasks/{task}/report").json()
    assert body["facts"]["complete"] and not body["facts"]["requires_review"]
    assert body["facts"]["candidate_count"] == 0 and body["outcome"] == "no_action"


def test_empty_unattributed_quality_survives_database(fixture: InventoryFixture) -> None:
    f = fixture
    task, job = f.create("empty_products")
    raw = Fixture.load(DIRECTORY, "empty_products")
    provenance = raw.source.provenance.model_copy(
        update={"quality_flags": (Quality.PARTIAL_FAILURE,)}
    )
    altered = replace(raw, source=raw.source.model_copy(update={"provenance": provenance}))

    def factory(request: Any) -> InventoryCollector:
        return InventoryCollector(MockCommerce(altered), altered.source, altered.now)

    asyncio.run(run_worker(f, job, factory=factory))
    body = client(f).get(f"/tasks/{task}/report").json()
    assert not body["facts"]["complete"] and body["outcome"] == "report_ready"
    assert "PARTIAL_FAILURE" in body["facts"]["warnings"]


def test_job_done_alone_does_not_complete_analysis(fixture: InventoryFixture) -> None:
    f = fixture
    task, job = f.create()
    with connect(f.owner) as db:
        db.execute("UPDATE business.jobs SET status='done' WHERE id=%s", (job,))
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute("UPDATE business.business_tasks SET state='completed' WHERE id=%s", (task,))
    assert f.row(task)["state"] == "queued" and f.counts(task) == (0, 0)
    assert client(f).get(f"/tasks/{task}/report").status_code == 409


GOLD = json.loads((DIRECTORY / "goldens.json").read_text())["expectations"]


@pytest.mark.parametrize("case", [key for key, g in GOLD.items() if "T" in g])
def test_all_numeric_goldens_persist_and_read(fixture: InventoryFixture, case: str) -> None:
    f = fixture
    source = Fixture.load(DIRECTORY, case).source
    gold = GOLD[case]
    with connect(f.owner) as db:
        db.execute(
            "UPDATE business.shops SET external_shop_key=%s,timezone=%s,currency=%s WHERE id=%s",
            (source.shop_id, source.timezone, source.currency, f.data.shop),
        )
    request = InventoryTaskRequest(fixture_case=case, L=gold["L"], R=gold["R"], S=gold["S"])
    task, job = create_analysis_task(f.app, f.identity, f.data.conversation, request)
    asyncio.run(run_worker(f, job))
    response = client(f).get(f"/tasks/{task}/report")
    assert response.status_code == 200
    actual = response.json()["facts"]["items"][0]
    assert {key: actual[key] for key in gold} == gold
    assert f.counts(task) == (1, 1) and f.row(task)["state"] == "completed"


def test_same_org_operator_cannot_read_others_task(fixture: InventoryFixture) -> None:
    f = fixture
    task, job = f.create()
    asyncio.run(run_worker(f, job))
    principal, identity = uuid4(), uuid4()
    with connect(f.owner) as db:
        db.execute(
            """INSERT INTO business.principals(id,organization_id,display_name,roles)
            VALUES (%s,%s,'owned scope fixture',ARRAY['operator','approver'])""",
            (principal, f.data.organization),
        )
        db.execute(
            """INSERT INTO
            business.identities(id,organization_id,principal_id,provider,app_id,tenant_key,external_subject)
            VALUES (%s,%s,%s,'technical_fixture',%s,%s,%s)""",
            (identity, f.data.organization, principal, f.data.app, f.data.tenant, str(uuid4())),
        )
        db.execute(
            "INSERT INTO business.principal_shop_scopes VALUES (%s,%s,%s,true)",
            (f.data.organization, f.data.shop, principal),
        )
    actor = replace(f.identity, principal_id=principal, identity_id=identity)
    c = client(f, actor)
    for suffix in ("", "/report", "/events"):
        assert c.get(f"/tasks/{task}" + suffix).status_code == 404


@pytest.mark.parametrize("field", ["identity_id", "organization_id", "shop_id", "principal_id"])
def test_trusted_identity_scope_mismatch(fixture: InventoryFixture, field: str) -> None:
    f = fixture
    task, _ = f.create()
    changes: dict[str, Any] = {field: uuid4()}
    actor = replace(f.identity, **changes)
    for suffix in ("", "/report", "/events"):
        assert client(f, actor).get(f"/tasks/{task}" + suffix).status_code == 403


def test_final_bounded_storage_failure_needs_attention(fixture: InventoryFixture) -> None:
    f = fixture
    task, job = f.create()
    with connect(f.owner) as db:
        db.execute("UPDATE business.jobs SET attempts=2 WHERE id=%s", (job,))

    async def fail(point: str) -> None:
        if point == "after_snapshot":
            raise RuntimeError("controlled storage failure")

    asyncio.run(run_worker(f, job, store_hook=fail))
    assert f.counts(task) == (0, 0)
    assert f.row(task)["state"] == "needs_attention"
    assert f.row(task)["failure_code"] == "ANALYSIS_STORAGE_FAILURE"


def test_business_commit_ack_loss_remains_completed(fixture: InventoryFixture) -> None:
    f = fixture
    task, job = f.create()

    async def lose_ack(point: str) -> None:
        if point == "after_commit":
            raise RuntimeError("controlled committed ACK loss")

    asyncio.run(run_worker(f, job, store_hook=lose_ack))
    assert f.counts(task) == (1, 1) and f.row(task)["state"] == "completed"
    assert client(f).get(f"/tasks/{task}/report").status_code == 200


def test_commit_locks_current_grant_until_report_transaction_ends(
    fixture: InventoryFixture,
) -> None:
    f = fixture
    task, job = f.create()
    entered = threading.Event()
    revoker_pid: list[int] = []
    with ThreadPoolExecutor(max_workers=1) as pool:

        def revoke() -> None:
            with connect(f.owner) as db:
                row = db.execute("SELECT pg_backend_pid() AS pid").fetchone()
                assert row
                revoker_pid.append(row["pid"])
                entered.set()
                db.execute(
                    "UPDATE business.principal_shop_scopes SET enabled=false WHERE principal_id=%s",
                    (f.data.principal,),
                )

        futures = []

        async def hold(point: str) -> None:
            if point != "before_commit":
                return
            futures.append(pool.submit(revoke))
            assert entered.wait(2)
            for _ in range(200):
                with connect(f.owner) as db:
                    activity = db.execute(
                        "SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s",
                        (revoker_pid[0],),
                    ).fetchone()
                if activity and activity["wait_event_type"] == "Lock":
                    assert not futures[0].done()
                    return
                await asyncio.sleep(0.01)
            raise AssertionError("grant revocation did not wait for final commit lock")

        asyncio.run(run_worker(f, job, store_hook=hold))
        futures[0].result(5)
    assert f.row(task)["state"] == "completed" and f.counts(task) == (1, 1)
    assert client(f).get(f"/tasks/{task}/report").status_code == 403


def test_mismatched_checkpoint_is_attention_without_new_collection(
    fixture: InventoryFixture,
) -> None:
    f = fixture
    task, job = f.create()
    with connect(f.owner) as db:
        db.execute("UPDATE business.business_tasks SET state='analyzing' WHERE id=%s", (task,))

    async def corrupt() -> None:
        async with checkpointer(f.app) as saver:
            checkpoint = empty_checkpoint()
            checkpoint["channel_values"] = {
                "task_id": str(uuid4()),
                "workflow_version": "p203-inventory-analysis-v1",
                "request_hash": "0" * 64,
            }
            checkpoint["channel_versions"] = {key: "1" for key in checkpoint["channel_values"]}
            config: RunnableConfig = {"configurable": {"thread_id": str(task), "checkpoint_ns": ""}}
            await saver.aput(
                config,
                checkpoint,
                {"source": "input", "step": -1, "parents": {}},
                checkpoint["channel_versions"],
            )
            saved = await saver.aget_tuple(config)
            assert saved and saved.checkpoint["channel_values"]["task_id"] != str(task)

    asyncio.run(corrupt())
    asyncio.run(run_worker(f, job))
    assert f.row(task)["state"] == "needs_attention" and f.counts(task) == (0, 0)


def test_old_workflow_queue_rejection_preserves_history(fixture: InventoryFixture) -> None:
    f = fixture
    task = f.data.task  # 旧kind/g1版本的实际历史fixture，未改写为新analysis版本。
    with connect(f.app) as db:
        job = TaskRepository(db, TaskScope(f.data.organization, f.data.shop)).enqueue(
            task, "analyze", str(uuid4()), "owned old workflow probe"
        )
    asyncio.run(run_worker(f, job, expected_status="dead"))
    assert f.row(task)["state"] == "queued" and f.counts(task) == (0, 0)
    with connect(f.app) as db:
        result = db.execute("SELECT last_error FROM business.jobs WHERE id=%s", (job,)).fetchone()
        assert result and result["last_error"] == "WORKFLOW_VERSION_UNSUPPORTED"
