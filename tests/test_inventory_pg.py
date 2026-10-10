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
from decimal import Decimal
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from commerceops.adapters.commerce.mock import Fixture, MockCommerce
from commerceops.application.commerce.analysis_task import InventoryTaskRequest
from commerceops.application.commerce.collection import InventoryCollector
from commerceops.application.commerce.contracts import Quality
from commerceops.application.commerce.inventory_analysis import (
    InventoryAnalysisError,
    analyze_inventory,
)
from commerceops.domain.inventory_rules import RuleParameters
from commerceops.entrypoints.api import create_app
from commerceops.entrypoints.database import grant_runtime, migrate, setup_checkpointer
from commerceops.infrastructure.checkpoint import checkpointer
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.inventory_repository import (
    AnalysisUnsafe,
    InventoryReadStore,
    InventoryStore,
    create_analysis_task,
)
from commerceops.infrastructure.queue import JobQueue
from commerceops.infrastructure.repository import TaskRepository, TaskScope
from commerceops.infrastructure.worker_lock import (
    TerminationRequired,
    WorkerSession,
    confirm_termination,
)
from commerceops.workflows.inventory_analysis import MockCollectorFactory
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
    before = f.row(task)
    with connect(f.app) as db:
        job = TaskRepository(db, TaskScope(f.data.organization, f.data.shop)).enqueue(
            task, "analyze", str(uuid4()), "owned old workflow probe"
        )
    asyncio.run(run_worker(f, job, expected_status="dead"))
    after = f.row(task)
    assert after["state"] == "needs_attention"
    assert after["failure_code"] == "WORKFLOW_VERSION_UNSUPPORTED" and f.counts(task) == (0, 0)
    for field in ("kind", "workflow_version", "thread_id", "normalized_request"):
        assert after[field] == before[field]
    with connect(f.app) as db:
        result = db.execute("SELECT last_error FROM business.jobs WHERE id=%s", (job,)).fetchone()
        assert result and result["last_error"] == "WORKFLOW_VERSION_UNSUPPORTED"


@pytest.mark.parametrize(
    "mismatch", ["stock", "parameters", "window", "display", "invalid_dto", "invalid_input_dto"]
)
def test_store_rejects_valid_hash_but_unbound_report(
    fixture: InventoryFixture, mismatch: str
) -> None:
    f = fixture
    task, _ = f.create()

    async def attempt() -> None:
        session = WorkerSession(f.app, f.data.organization)
        await session.start()
        queue = JobQueue(session)
        r = await queue.claim()
        assert r and r.task_id == task
        store = InventoryStore(f.app, session)
        try:
            await store.mark(r, "analyzing")
            collected = await MockCollectorFactory(DIRECTORY)(InventoryTaskRequest()).collect()
            data = collected.data
            provided = analyze_inventory(data)
            if mismatch == "stock":
                altered = data.model_copy(
                    update={
                        "inventories": (
                            data.inventories[0].model_copy(update={"available_stock": 999}),
                        )
                    }
                )
                provided = analyze_inventory(altered)
            elif mismatch == "parameters":
                provided = analyze_inventory(data, RuleParameters(L=99))
            elif mismatch == "window":
                from datetime import timedelta

                altered = data.model_copy(
                    update={"now": data.now + timedelta(days=1), "window": None}
                )
                provided = analyze_inventory(altered)
            elif mismatch == "display":
                item = provided.items[0].model_copy(
                    update={
                        "display": provided.items[0].display.model_copy(update={"D": "999.000000"})
                    }
                )
                provided = provided.model_copy(update={"items": (item,)})
            elif mismatch == "invalid_input_dto":
                collected = replace(
                    collected,
                    data=data.model_copy(
                        update={
                            "inventories": (
                                data.inventories[0].model_copy(update={"available_stock": 1.5}),
                            )
                        }
                    ),
                )
            else:
                provided = provided.model_copy(update={"complete": "true"})
            with pytest.raises(AnalysisUnsafe, match="ANALYSIS_REPORT_BINDING_MISMATCH"):
                await store.save(r, collected, provided)
            assert f.counts(task) == (0, 0) and f.row(task)["state"] == "analyzing"
            await queue.done(r)
        finally:
            await session.close(clean=True)

    asyncio.run(attempt())


def child_insert_sql(table: str, *, late: bool = True) -> sql.Composed:
    # 表名/列片段固定白名单，参数值仍用绑定；普通app可成功的原始结构。
    columns = {
        "snapshot_products": (
            "sku_key||':late',stock_pool_key,payload,available_stock,inbound_units"
        ),
        "snapshot_order_lines": (
            "order_id||':late',line_id,sku_key,status,created_at_source,paid_at,completed_at,"
            "quantity,net_amount,tax_amount,currency,payload"
        ),
        "snapshot_refunds": (
            "refund_id||':late',order_id,occurred_at,refund_amount,currency,payload"
        ),
    }
    selected = columns[table] if late else columns[table].replace("||':late'", "")
    return sql.SQL("""INSERT INTO business.{table}
        SELECT %s,organization_id,shop_id,%s,{columns}
        FROM business.{table} WHERE task_id=%s""").format(
        table=sql.Identifier(table), columns=sql.SQL(selected)
    )


@pytest.mark.parametrize("table", ["snapshot_products", "snapshot_order_lines", "snapshot_refunds"])
def test_runtime_cannot_append_any_sealed_child(fixture: InventoryFixture, table: str) -> None:
    f = fixture
    task, job = f.create("partial_refund")
    asyncio.run(run_worker(f, job))
    with connect(f.app) as db:
        actor = db.execute("SELECT current_user AS actor").fetchone()
        assert actor and actor["actor"] == "commerceops_app"
        row = db.execute(
            "SELECT id,content_hash FROM business.commerce_snapshots WHERE task_id=%s", (task,)
        ).fetchone()
        assert row
        with (
            pytest.raises(psycopg.errors.CheckViolation, match="snapshot children are sealed"),
            db.transaction(),
        ):
            db.execute(child_insert_sql(table), (row["id"], task, task))
        count = db.execute(
            sql.SQL("SELECT count(*) AS n FROM business.{} WHERE task_id=%s").format(
                sql.Identifier(table)
            ),
            (task,),
        ).fetchone()
        assert count and count["n"] == 1
    assert client(f).get(f"/tasks/{task}/report").status_code == 200
    assert f.counts(task) == (1, 1)


@pytest.mark.parametrize("table", ["snapshot_products", "snapshot_order_lines", "snapshot_refunds"])
def test_child_insert_waits_then_rechecks_report_seal(
    fixture: InventoryFixture, table: str
) -> None:
    f = fixture
    original, job = f.create("partial_refund")
    asyncio.run(run_worker(f, job))
    task, _ = f.create("partial_refund")
    snapshot = uuid4()
    with connect(f.app) as db:
        db.execute("UPDATE business.business_tasks SET state='analyzing' WHERE id=%s", (task,))
        db.execute(
            """INSERT INTO business.commerce_snapshots
            SELECT %s,organization_id,shop_id,%s,%s,request_content,request_hash,schema_version,
            source_kind,fixture_version,shop_timezone,currency,window_start,window_end,
            collection_started_at,collected_at,complete,warnings,consistency,content,
            canonical_content,content_hash FROM business.commerce_snapshots WHERE task_id=%s""",
            (snapshot, task, f"analysis:{task}:p203-inventory-analysis-v1", original),
        )
        for child in ("snapshot_products", "snapshot_order_lines", "snapshot_refunds"):
            # 首次未封存写入实际通过；替换后缀为原ID保持canonical规范化副本一致。
            db.execute(child_insert_sql(child, late=False), (snapshot, task, original))
    locked, release, inserting = threading.Event(), threading.Event(), threading.Event()
    pid: list[int] = []

    def seal() -> None:
        with connect(f.app) as db:
            db.execute("SELECT id FROM business.business_tasks WHERE id=%s FOR UPDATE", (task,))
            locked.set()
            assert release.wait(5)
            db.execute(
                """INSERT INTO business.analysis_reports
                SELECT %s,organization_id,shop_id,%s,%s,%s,rule_version,schema_version,
                facts,canonical_facts,facts_hash,report,outcome,clock_timestamp()
                FROM business.analysis_reports WHERE task_id=%s""",
                (uuid4(), task, snapshot, f"analysis:{task}:p203-inventory-analysis-v1", original),
            )
            db.execute("UPDATE business.business_tasks SET state='completed' WHERE id=%s", (task,))

    def append() -> None:
        with connect(f.app) as db:
            who = db.execute("SELECT current_user AS actor,pg_backend_pid() AS pid").fetchone()
            assert who and who["actor"] == "commerceops_app"
            pid.append(who["pid"])
            inserting.set()
            with pytest.raises(psycopg.errors.CheckViolation, match="snapshot children are sealed"):
                db.execute(child_insert_sql(table), (snapshot, task, original))
            db.rollback()

    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(seal)
        assert locked.wait(2)
        inserting_future = pool.submit(append)
        try:
            assert inserting.wait(2)
            for _ in range(200):
                with connect(f.owner) as db:
                    wait = db.execute(
                        "SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s", (pid[0],)
                    ).fetchone()
                if wait and wait["wait_event_type"] == "Lock":
                    assert not inserting_future.done()
                    break
                time.sleep(0.01)
            else:
                raise AssertionError("child insert did not lock shared task")
        finally:
            release.set()
        writer.result(5)
        inserting_future.result(5)
    with connect(f.app) as db:
        count = db.execute(
            sql.SQL("SELECT count(*) AS n FROM business.{} WHERE task_id=%s").format(
                sql.Identifier(table)
            ),
            (task,),
        ).fetchone()
        assert count and count["n"] == 1
    assert f.counts(task) == (1, 1) and client(f).get(f"/tasks/{task}/report").status_code == 200


@pytest.mark.parametrize(
    "amount,kind",
    [
        ("1.0000001", psycopg.errors.CheckViolation),
        ("100000000000000", psycopg.errors.NumericValueOutOfRange),
    ],
)
def test_runtime_money_precision_before_seal(
    fixture: InventoryFixture, amount: str, kind: type[Exception]
) -> None:
    f = fixture
    original, job = f.create("partial_refund")
    asyncio.run(run_worker(f, job))
    task, _ = f.create("partial_refund")
    snapshot = uuid4()
    with connect(f.app) as db:
        actor = db.execute("SELECT current_user AS actor").fetchone()
        assert actor and actor["actor"] == "commerceops_app"
        db.execute("UPDATE business.business_tasks SET state='analyzing' WHERE id=%s", (task,))
        db.execute(
            """INSERT INTO business.commerce_snapshots
            SELECT %s,organization_id,shop_id,%s,%s,request_content,request_hash,schema_version,
            source_kind,fixture_version,shop_timezone,currency,window_start,window_end,
            collection_started_at,collected_at,complete,warnings,consistency,content,
            canonical_content,content_hash FROM business.commerce_snapshots WHERE task_id=%s""",
            (snapshot, task, f"analysis:{task}:p203-inventory-analysis-v1", original),
        )
        with pytest.raises(kind), db.transaction():
            db.execute(
                """INSERT INTO business.snapshot_order_lines
                SELECT %s,organization_id,shop_id,%s,order_id,line_id,sku_key,status,
                created_at_source,
                paid_at,completed_at,quantity,%s,tax_amount,currency,
                jsonb_set(payload,'{net_amount}',to_jsonb(%s::text))
                FROM business.snapshot_order_lines WHERE task_id=%s""",
                (snapshot, task, amount, amount, original),
            )
        count = db.execute(
            "SELECT count(*) AS n FROM business.snapshot_order_lines WHERE task_id=%s", (task,)
        ).fetchone()
        assert count and count["n"] == 0  # 金额检查发生于未封存合法写入阶段，非sealed先行拒绝。
        db.execute(child_insert_sql("snapshot_order_lines", late=False), (snapshot, task, original))
        valid = db.execute(
            "SELECT count(*) AS n FROM business.snapshot_order_lines WHERE task_id=%s", (task,)
        ).fetchone()
        assert valid and valid["n"] == 1


BAD_NATIVE_MONEY: tuple[object, ...] = (
    10.5,
    10.5000001,
    Decimal("10.5000000"),
    True,
    float("nan"),
    float("inf"),
)


@pytest.mark.parametrize("field", ["net_amount", "tax_amount", "refund_amount"])
@pytest.mark.parametrize("bad", BAD_NATIVE_MONEY)
def test_native_money_rejected_before_any_serializer(
    fixture: InventoryFixture, field: str, bad: object
) -> None:
    f = fixture
    task, _ = f.create("partial_refund")

    async def attempt() -> None:
        session = WorkerSession(f.app, f.data.organization)
        await session.start()
        queue = JobQueue(session)
        r = await queue.claim()
        assert r and r.task_id == task
        store = InventoryStore(f.app, session)
        try:
            await store.mark(r, "analyzing")
            collected = await MockCollectorFactory(DIRECTORY)(
                InventoryTaskRequest(fixture_case="partial_refund")
            ).collect()
            data = collected.data
            valid_report = analyze_inventory(data)
            if field == "refund_amount":
                invalid = data.model_copy(
                    update={"refunds": (data.refunds[0].model_copy(update={"refund_amount": bad}),)}
                )
            else:
                invalid = data.model_copy(
                    update={"order_lines": (data.order_lines[0].model_copy(update={field: bad}),)}
                )
            # 独立纯规则边界先证明原值非法；不以serializer后的值作为期望输入。
            with pytest.raises(InventoryAnalysisError):
                analyze_inventory(invalid)
            with pytest.raises(AnalysisUnsafe, match="ANALYSIS_REPORT_BINDING_MISMATCH"):
                await store.save(r, replace(collected, data=invalid), valid_report)
            assert f.counts(task) == (0, 0) and f.row(task)["state"] != "completed"
            # 原始合法Decimal在同一正常app/Worker所有权下仍能原子保存。
            saved = await store.save(r, collected, valid_report)
            assert saved.report == valid_report and f.counts(task) == (1, 1)
            assert f.row(task)["state"] == "completed"
            await queue.done(r)
        finally:
            await session.close(clean=True)

    asyncio.run(attempt())
