"""A02实际PG/HTTP决定、唯一业务中断与持久A03边界；simulated_web/Mock。"""

import asyncio
import json
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from commerceops.application.replenishment.contracts import (
    WORKFLOW_VERSION,
    DecisionInput,
    WebFailure,
)
from commerceops.application.replenishment.security import password_hash
from commerceops.application.runner import RunRequest
from commerceops.domain.commerce_values import facts_hash
from commerceops.entrypoints.api import create_app
from commerceops.infrastructure.approval_decisions import DecisionStore
from commerceops.infrastructure.approval_recovery import snapshot_binding
from commerceops.infrastructure.checkpoint import checkpointer
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.replenishment_repository import ApprovalStore, ReplenishmentStore
from commerceops.infrastructure.web_sessions import SessionStore
from commerceops.infrastructure.worker_lock import WorkerSession, confirm_termination
from commerceops.workflows.replenishment import ApprovalRunner, ApprovalState
from fastapi.testclient import TestClient
from langgraph.graph import END, START, StateGraph
from langgraph.types import StateSnapshot
from psycopg import sql
from psycopg.errors import CheckViolation, InsufficientPrivilege

from tests.inventory_support import DIRECTORY
from tests.p3_support import ORIGIN, P3Fixture, P3Process
from tests.test_p3_pg import fixture as fixture

pytestmark = pytest.mark.integration


def task_state(f: P3Fixture, task: UUID) -> dict[str, Any]:
    with connect(f.config.database) as db:
        row = db.execute(
            "SELECT state,failure_code,active_plan_id FROM business.business_tasks WHERE id=%s",
            (task,),
        ).fetchone()
    assert row
    return row


def wait_state(f: P3Fixture, task: UUID, expected: str, *, restoring: bool = False) -> None:
    end = time.monotonic() + 20
    while time.monotonic() < end:
        current = task_state(f, task)
        if current["state"] == expected:
            return
        if not (restoring and current["failure_code"] == "WORKER_TERMINATION_UNCONFIRMED"):
            assert current["state"] not in ("failed", "needs_attention"), current["failure_code"]
        time.sleep(0.02)
    raise AssertionError("bounded P3 state deadline")


def wait_ready(f: P3Fixture, task: UUID) -> dict[str, Any]:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        with connect(f.config.database) as db:
            row = db.execute(
                "SELECT id,plan_id,ready_at FROM business.approvals WHERE task_id=%s", (task,)
            ).fetchone()
        if (
            row
            and row["ready_at"] is not None
            and task_state(f, task)["state"] == "awaiting_approval"
        ):
            return row
        time.sleep(0.02)
    raise AssertionError("bounded actual checkpoint-ready deadline")


def start(
    f: P3Fixture, task: UUID, barrier: str = "never", *, controlled: str | None = None
) -> tuple[P3Process, str]:
    child = P3Process(f, "worker", {"task_id": str(task), "controlled": controlled}, barrier)
    event = child.until("started")
    return child, event["owner"]


def payload(
    f: P3Fixture, task: UUID, action: str = "approve", request_key: UUID | None = None
) -> dict[str, Any]:
    detail = f.client.get(f"/api/v1/tasks/{task}").json()
    approval = f.client.get(f"/api/v1/approvals/{detail['approval_id']}").json()
    row = approval["approval"]
    return {
        "schema_version": "p3-web-v1",
        "request_key": str(request_key or uuid4()),
        "approval_id": row["approval_id"],
        "plan_id": row["plan_id"],
        "plan_version": row["plan_version"],
        "plan_hash": row["plan_hash"],
        "action": action,
        "acknowledged_assumption_keys": [a["key"] for a in approval["plan"]["required_assumptions"]]
        if action == "approve_with_assumptions"
        else [],
        "nonce": approval["nonce"],
    }


def post(f: P3Fixture, body: dict[str, Any]) -> Any:
    return f.client.post(
        f"/api/v1/approvals/{body['approval_id']}/decision", json=body, headers=f.headers()
    )


def decision_counts(f: P3Fixture, task: UUID) -> dict[str, int]:
    with connect(f.config.database) as db:
        resume = db.execute(
            "SELECT count(*) AS n FROM business.approval_resumes WHERE task_id=%s", (task,)
        ).fetchone()
        audit = db.execute(
            "SELECT count(*) AS n FROM business.audit_events "
            "WHERE task_id=%s AND action='approval_decided'",
            (task,),
        ).fetchone()
        jobs = db.execute(
            "SELECT count(*) AS n FROM business.jobs WHERE task_id=%s AND kind='resume'", (task,)
        ).fetchone()
    assert resume and audit and jobs
    return {"decision": resume["n"], "audit": audit["n"], "resume_job": jobs["n"]}


@pytest.mark.parametrize(
    "case,action,target",
    [
        ("baseline", "approve", "completed"),
        ("unknown_inbound", "approve_with_assumptions", "completed"),
        ("baseline", "reject", "rejected"),
        ("unknown_inbound", "reject_assumptions", "rejected"),
    ],
)
def test_t3_one_decision_ten_replays_and_safe_execution_boundary(
    fixture: P3Fixture,
    case: str,
    action: str,
    target: str,
) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle(case))["task_id"])
    child, _ = start(f, task)
    try:
        child.until("after_ready")
        body = payload(f, task, action)
        first = post(f, body)
        assert first.status_code == 200
        for _ in range(9):
            repeated = post(f, body)
            assert (
                repeated.status_code == 200
                and repeated.json()["decision_id"] == first.json()["decision_id"]
            )
            assert repeated.json()["duplicate"]
        wait_state(f, task, target)
        assert decision_counts(f, task) == {"decision": 1, "audit": 1, "resume_job": 1}
        with connect(f.config.database) as db:
            row = db.execute(
                """SELECT a.status,a.consumed_at,r.delivery_state,r.continuation_job_id
             FROM business.approvals a JOIN business.approval_resumes r ON r.approval_id=a.id
             WHERE a.task_id=%s""",
                (task,),
            ).fetchone()
        assert row and row["delivery_state"] == "consumed"
        assert (row["consumed_at"] is not None) == (target == "completed")
        assert bool(row["continuation_job_id"]) == (target == "completed")
        detail = f.client.get(f"/api/v1/approvals/{body['approval_id']}").json()
        assert (
            detail["nonce"] is None
            and detail["decision"]["decision_id"] == first.json()["decision_id"]
        )
        assert not detail["approval"]["can_decide"]
    finally:
        if child.process.poll() is None:
            child.stop_clean()


def test_plain_approve_and_partial_unknown_ack_never_write_decision(fixture: P3Fixture) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle("unknown_inbound"))["task_id"])
    child, _ = start(f, task)
    try:
        child.until("after_ready")
        plain = payload(f, task)
        result = post(f, plain)
        assert (
            result.status_code == 409
            and result.json()["error"]["code"] == "ASSUMPTION_ACK_REQUIRED"
        )
        assert decision_counts(f, task) == {"decision": 0, "audit": 0, "resume_job": 0}
        joint = payload(f, task, "approve_with_assumptions")
        extra = {
            **joint,
            "acknowledged_assumption_keys": joint["acknowledged_assumption_keys"]
            + ["inbound_unknown_zero:extra"],
        }
        result = post(f, extra)
        assert (
            result.status_code == 409
            and result.json()["error"]["code"] == "ASSUMPTION_SET_MISMATCH"
        )
        for change in (
            {"plan_version": True},
            {"plan_version": 1.0},
            {"actor": str(uuid4())},
            {"acknowledged_assumption_keys": joint["acknowledged_assumption_keys"] * 2},
        ):
            assert post(f, {**joint, **change}).status_code == 422
        assert decision_counts(f, task) == {"decision": 0, "audit": 0, "resume_job": 0}
        assert task_state(f, task)["state"] == "awaiting_approval"
    finally:
        if child.process.poll() is None:
            child.stop_clean()


@pytest.mark.parametrize(
    "barrier,early",
    [
        ("after_t2_commit", False),
        ("before_ready", False),
        ("after_t2_commit", True),
    ],
)
def test_r05_r06_r07_real_kill_old_process_gate_and_same_checkpoint_resume(
    fixture: P3Fixture,
    barrier: str,
    early: bool,
) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle("unknown_inbound"))["task_id"])
    child, owner = start(f, task, barrier)
    replacement: P3Process | None = None
    try:
        child.until(barrier)
        request = payload(f, task, "approve_with_assumptions")
        with connect(f.config.database) as db:
            row = db.execute(
                "SELECT id,plan_id,ready_at FROM business.approvals WHERE task_id=%s", (task,)
            ).fetchone()
        assert row and row["ready_at"] is None
        if early:
            first = post(f, request)
            assert first.status_code == 200 and first.json()["resume_state"] == "waiting_checkpoint"
        child.kill_reap()
        assert child.process.poll() == -9
        blocked = P3Process(f, "worker", {"task_id": str(task)})
        failure = blocked.until("blocked")
        assert failure["category"] == "TerminationRequired"
        blocked.close_exited(2)
        assert task_state(f, task)["state"] == "needs_attention"
        asyncio.run(
            confirm_termination(f.config.database, owner, "A02 controlled SIGKILL and OS wait -9")
        )
        replacement, _ = start(f, task)
        if not early:
            same = wait_ready(f, task)
            assert same and same["id"] == row["id"] and same["plan_id"] == row["plan_id"]
            assert same["ready_at"] is not None
            assert post(f, request).status_code == 200
        wait_state(f, task, "completed", restoring=True)
        assert decision_counts(f, task) == {"decision": 1, "audit": 1, "resume_job": 1}
        with connect(f.config.database) as db:
            count = db.execute(
                "SELECT count(*) AS n FROM business.replenishment_plans WHERE task_id=%s", (task,)
            ).fetchone()
            intent = db.execute(
                "SELECT status,sender_enabled FROM business.outbox WHERE "
                "task_id=%s AND operation='approval_card'",
                (task,),
            ).fetchone()
        assert count and count["n"] == 1
        assert intent and intent["status"] == "pending" and not intent["sender_enabled"]
    finally:
        if child.process.poll() is None:
            child.kill_reap()
        if replacement is not None and replacement.process.poll() is None:
            replacement.stop_clean()


def second_approver(f: P3Fixture) -> tuple[TestClient, Any]:
    principal, identity = uuid4(), uuid4()
    login = "v-" + uuid4().hex
    plain = secrets.token_urlsafe(32)
    encoded = password_hash(plain)
    d = f.inventory.data
    with connect(f.inventory.owner) as db:
        db.execute(
            """INSERT INTO business.principals
         (id,organization_id,display_name,roles)
         VALUES (%s,%s,'Second controlled approver',ARRAY['approver'])""",
            (principal, d.organization),
        )
        db.execute(
            "INSERT INTO business.principal_shop_scopes VALUES (%s,%s,%s,true)",
            (d.organization, d.shop, principal),
        )
        db.execute(
            """INSERT INTO business.identities
         (id,organization_id,principal_id,provider,app_id,tenant_key,external_subject)
         VALUES (%s,%s,%s,'web',%s,%s,%s)""",
            (identity, d.organization, principal, d.app, d.tenant, login),
        )
        db.execute(
            "INSERT INTO business.web_credentials VALUES (%s,%s,%s,%s,%s,true)",
            (login, d.organization, principal, identity, encoded),
        )
        db.execute(
            "INSERT INTO business.principal_role_shop_grants VALUES (%s,%s,%s,'approver',true)",
            (d.organization, d.shop, principal),
        )
    client = TestClient(
        create_app(web_config=f.config, replenishment_store=f.store), base_url=ORIGIN
    )
    bootstrap = client.get("/api/v1/auth/csrf").json()
    logged = client.post(
        "/api/v1/auth/login",
        json={"schema_version": "p3-web-v1", "login": login, "password": plain},
        headers={"Origin": ORIGIN, "X-CSRF-Token": bootstrap["csrf_token"]},
    )
    assert logged.status_code == 200
    actor = SessionStore(f.config).authenticate(client.cookies.get("commerceops_session"))
    return client, actor


def test_two_current_eligible_actors_approve_reject_race_has_one_winner(fixture: P3Fixture) -> None:
    f = fixture
    other, actor = second_approver(f)
    task = UUID(f.create(f.new_cycle())["task_id"])
    child, _ = start(f, task)
    try:
        child.until("after_ready")
        first = DecisionInput.model_validate_json(json.dumps(payload(f, task)))
        opposite = first.model_copy(update={"request_key": uuid4(), "action": "reject"})

        def send(who: Any, body: DecisionInput) -> tuple[int, str]:
            try:
                result = DecisionStore(f.config).decide(who, body.approval_id, body)
                return 200, result["action"]
            except WebFailure as error:
                return error.status, error.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(send, f.actor, first), pool.submit(send, actor, opposite)]
            results = [future.result(timeout=15) for future in futures]
        assert sorted(code for code, _ in results) == [200, 409]
        assert [text for code, text in results if code == 409] == ["DECISION_CONFLICT"]
        assert decision_counts(f, task) == {"decision": 1, "audit": 1, "resume_job": 1}
    finally:
        other.close()
        if child.process.poll() is None:
            child.stop_clean()


def test_r08_t3_commit_before_ack_real_sigkill_ten_replays(fixture: P3Fixture) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle())["task_id"])
    worker, _ = start(f, task)
    child: P3Process | None = None
    try:
        worker.until("after_ready")
        request = payload(f, task)
        child = P3Process(f, "decide", request, "after_t3_commit")
        child.until("after_t3_commit")
        child.kill_reap()
        assert child.process.poll() == -9
        identifiers = []
        for _ in range(10):
            result = post(f, request)
            assert result.status_code == 200 and result.json()["duplicate"]
            identifiers.append(result.json()["decision_id"])
        assert len(set(identifiers)) == 1
        assert decision_counts(f, task) == {"decision": 1, "audit": 1, "resume_job": 1}
    finally:
        if child is not None and child.process.poll() is None:
            child.kill_reap()
        if worker.process.poll() is None:
            worker.stop_clean()


async def checkpoint_state(f: P3Fixture, task: UUID) -> StateSnapshot:
    with connect(f.config.database) as db:
        row = db.execute("SELECT * FROM business.business_tasks WHERE id=%s", (task,)).fetchone()
        job = db.execute(
            "SELECT id FROM business.jobs WHERE task_id=%s AND dedupe_key=%s", (task, f"p3:{task}")
        ).fetchone()
    assert row and job
    session = WorkerSession(f.config.database, row["organization_id"])
    runner = ApprovalRunner(ApprovalStore(f.config, session))
    request = RunRequest(
        job["id"],
        task,
        row["organization_id"],
        row["shop_id"],
        str(task),
        WORKFLOW_VERSION,
        "analyze",
        f"task:{task}",
        "read-only-probe",
        0,
    )
    expected = {
        "workflow_version": WORKFLOW_VERSION,
        "task_id": str(task),
        "request_hash": facts_hash(row["normalized_request"]),
    }
    async with checkpointer(f.config.database) as saver:
        compiled = runner.build_graph(request, expected).compile(
            checkpointer=saver, interrupt_before=["revalidate"]
        )
        return await compiled.aget_state({"configurable": {"thread_id": str(task)}})


@pytest.mark.parametrize("barrier", ["before_delivery_receipt", "after_delivery_receipt"])
def test_r17_delivery_boundary_kill_restores_none_and_one_permanent_execution(
    fixture: P3Fixture,
    barrier: str,
) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle())["task_id"])
    child, owner = start(f, task, barrier)
    restored: P3Process | None = None
    try:
        child.until("after_ready")
        request = payload(f, task)
        assert post(f, request).status_code == 200
        child.until(barrier)
        saved = asyncio.run(checkpoint_state(f, task))
        assert saved.next == ("revalidate",) and not saved.interrupts
        original_checkpoint = saved.config["configurable"]["checkpoint_id"]
        child.kill_reap()
        assert child.process.poll() == -9
        blocked = P3Process(f, "worker", {"task_id": str(task)})
        assert blocked.until("blocked")["category"] == "TerminationRequired"
        blocked.close_exited(2)
        asyncio.run(
            confirm_termination(f.config.database, owner, "A02 static boundary SIGKILL/reaped")
        )
        restored, _ = start(f, task)
        wait_state(f, task, "completed", restoring=True)
        with connect(f.config.database) as db:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                result = db.execute(
                    """SELECT a.consumed_at,r.delivery_state,r.continuation_job_id,
                 j.status,j.payload_ref FROM business.approvals a
                 JOIN business.approval_resumes r ON r.approval_id=a.id
                 LEFT JOIN business.jobs j ON j.id=r.continuation_job_id WHERE a.task_id=%s""",
                    (task,),
                ).fetchone()
                if result and result["status"] == "done":
                    break
                time.sleep(0.02)
            assert (
                result
                and result["consumed_at"] is not None
                and result["delivery_state"] == "consumed"
            )
            assert result["continuation_job_id"] and result["status"] == "done"
            assert result["payload_ref"].startswith("continue:")
        same = asyncio.run(checkpoint_state(f, task))
        assert same.next == () and not same.interrupts
        assert same.config["configurable"]["checkpoint_id"] != original_checkpoint
        assert same.values["decision_id"] == saved.values["decision_id"]
        assert same.values["plan_hash"] == saved.values["plan_hash"]
        assert decision_counts(f, task) == {"decision": 1, "audit": 1, "resume_job": 1}
    finally:
        if child.process.poll() is None:
            child.kill_reap()
        if restored is not None and restored.process.poll() is None:
            restored.stop_clean()


def test_second_worker_is_rejected_while_waiting_releases_graph_slot(fixture: P3Fixture) -> None:
    f = fixture
    first = UUID(f.create(f.new_cycle())["task_id"])
    child, _ = start(f, first)
    second: P3Process | None = None
    try:
        child.until("after_ready")
        second = P3Process(f, "worker", {})
        assert second.until("blocked")["category"] == "WorkerBusy"
        second.close_exited(2)
        next_task = UUID(f.create(f.new_cycle())["task_id"])
        child.until("after_ready")
        assert task_state(f, next_task)["state"] == "awaiting_approval"
        assert task_state(f, first)["state"] == "awaiting_approval"
    finally:
        if second is not None and second.process.poll() is None:
            second.kill_reap()
        if child.process.poll() is None:
            child.stop_clean()


def test_t3_semantic_new_keys_conflicts_and_bad_bindings_have_no_extra_effect(
    fixture: P3Fixture,
) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle())["task_id"])
    child, _ = start(f, task)
    try:
        child.until("after_ready")
        request = payload(f, task)
        for change, code in (
            ({"nonce": "X" * 43}, 422),
            ({"plan_hash": "0" * 64}, 409),
            ({"plan_version": 2}, 409),
            ({"plan_id": str(uuid4())}, 409),
        ):
            assert post(f, {**request, **change}).status_code == code
        assert decision_counts(f, task) == {"decision": 0, "audit": 0, "resume_job": 0}
        first = post(f, request)
        assert first.status_code == 200
        assert (
            post(f, {**request, "action": "reject"}).json()["error"]["code"]
            == "IDEMPOTENCY_CONFLICT"
        )
        for _ in range(9):
            same = post(f, {**request, "request_key": str(uuid4())})
            assert same.status_code == 200 and same.json()["duplicate"]
            assert same.json()["decision_id"] == first.json()["decision_id"]
        opposite = post(f, {**request, "request_key": str(uuid4()), "action": "reject"})
        assert (
            opposite.status_code == 409 and opposite.json()["error"]["code"] == "DECISION_CONFLICT"
        )
        assert decision_counts(f, task) == {"decision": 1, "audit": 1, "resume_job": 1}
    finally:
        if child.process.poll() is None:
            child.stop_clean()


def test_partial_two_assumptions_are_rejected_and_full_reversed_set_commits_once(
    fixture: P3Fixture,
) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle("unknown_inbound"))["task_id"])
    child, _ = start(f, task, controlled="two_unknown")
    try:
        child.until("after_ready")
        request = payload(f, task, "approve_with_assumptions")
        assert len(request["acknowledged_assumption_keys"]) == 2
        result = post(
            f,
            {
                **request,
                "acknowledged_assumption_keys": request["acknowledged_assumption_keys"][:1],
            },
        )
        assert (
            result.status_code == 409
            and result.json()["error"]["code"] == "ASSUMPTION_SET_MISMATCH"
        )
        assert decision_counts(f, task) == {"decision": 0, "audit": 0, "resume_job": 0}
        request["acknowledged_assumption_keys"].reverse()
        first = post(f, request)
        assert first.status_code == 200
        original = post(f, request)
        assert (
            original.status_code == 200
            and original.json()["decision_id"] == first.json()["decision_id"]
        )
        assert decision_counts(f, task) == {"decision": 1, "audit": 1, "resume_job": 1}
    finally:
        if child.process.poll() is None:
            child.stop_clean()


def test_legitimate_256_sku_keeps_complete_277_ack_and_replays(fixture: P3Fixture) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle("unknown_inbound"))["task_id"])
    child, _ = start(f, task, controlled="long_sku")
    try:
        child.until("after_ready")
        joint = payload(f, task, "approve_with_assumptions")
        acks = joint["acknowledged_assumption_keys"]
        assert len(acks) == 1 and len(acks[0]) == len("inbound_unknown_zero:") + 256
        assert (
            post(f, {**joint, "action": "approve", "acknowledged_assumption_keys": []}).status_code
            == 409
        )
        first = post(f, joint)
        assert first.status_code == 200 and first.json()["acknowledged_assumption_keys"] == acks
        for _ in range(9):
            duplicate = post(f, joint)
            assert (
                duplicate.status_code == 200
                and duplicate.json()["decision_id"] == first.json()["decision_id"]
            )
        result = f.client.get(f"/api/v1/requests/{joint['request_key']}?operation=decision").json()
        assert result["receipt"]["result"]["acknowledged_assumption_keys"] == acks
        assert decision_counts(f, task) == {"decision": 1, "audit": 1, "resume_job": 1}
    finally:
        if child.process.poll() is None:
            child.stop_clean()


def test_postdecision_role_revocation_allows_only_original_readable_receipt(
    fixture: P3Fixture,
) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle())["task_id"])
    child, _ = start(f, task)
    try:
        child.until("after_ready")
        request = payload(f, task)
        first = post(f, request)
        assert first.status_code == 200
        with connect(f.inventory.owner) as db:
            db.execute(
                "SELECT id FROM business.principals WHERE id=%s FOR UPDATE", (f.actor.principal_id,)
            )
            db.execute(
                "UPDATE business.principal_role_shop_grants SET enabled=false "
                "WHERE principal_id=%s AND role='approver'",
                (f.actor.principal_id,),
            )
        assert f.client.get("/api/v1/auth/session").status_code == 401
        f.relogin()  # operator原owner查看权仍有，不能重新批准。
        same = post(f, request)
        assert same.status_code == 200 and same.json()["decision_id"] == first.json()["decision_id"]
        assert same.json()["duplicate"]
        assert decision_counts(f, task) == {"decision": 1, "audit": 1, "resume_job": 1}
        next_task = UUID(f.create(f.new_cycle())["task_id"])
        wait_ready(f, next_task)
        detail = f.client.get(f"/api/v1/tasks/{next_task}").json()
        denied = f.client.post(
            f"/api/v1/approvals/{detail['approval_id']}/decision",
            content="broken",
            headers=f.headers(),
        )
        assert denied.status_code == 403 and denied.json()["error"]["code"] == "ACCESS_DENIED"
        assert decision_counts(f, next_task) == {"decision": 0, "audit": 0, "resume_job": 0}
    finally:
        if child.process.poll() is None:
            child.stop_clean()


def test_expiry_uses_real_db_clock_after_business_locks(fixture: P3Fixture) -> None:
    f = fixture
    f.config = replace(f.config, approval_ttl_seconds=60)
    config = json.loads(f.config_file.read_text())
    config["approval_ttl_seconds"] = 60
    f.config_file.write_text(json.dumps(config))
    f.config_file.chmod(0o600)
    f.store = ReplenishmentStore(f.config, DIRECTORY)
    f.client.close()
    f.client = TestClient(
        create_app(web_config=f.config, replenishment_store=f.store), base_url=ORIGIN
    )
    f.relogin()
    task = UUID(f.create(f.new_cycle())["task_id"])
    child, _ = start(f, task)
    try:
        child.until("after_ready")
        request = DecisionInput.model_validate_json(json.dumps(payload(f, task)))
        child.stop_clean()
        # 真PG期限，未修改历史plan/expires/hash，也不注入fake clock。
        with connect(f.inventory.owner) as clock_db:
            while True:
                row = clock_db.execute(
                    "SELECT expires_at-clock_timestamp() AS remaining "
                    "FROM business.approvals WHERE task_id=%s",
                    (task,),
                ).fetchone()
                assert row
                seconds = row["remaining"].total_seconds()
                if seconds <= 1.5:
                    break
                time.sleep(min(0.5, seconds - 1.5))
        with ThreadPoolExecutor(max_workers=1) as pool:
            with connect(f.inventory.owner) as blocker:
                blocker.execute(
                    "SELECT id FROM business.business_tasks WHERE id=%s FOR UPDATE", (task,)
                )

                def attempt() -> tuple[int, str]:
                    try:
                        DecisionStore(f.config).decide(f.actor, request.approval_id, request)
                        return 200, "unexpected"
                    except WebFailure as error:
                        return error.status, error.code

                future = pool.submit(attempt)
                end = time.monotonic() + 5
                with connect(f.inventory.owner) as observer:
                    while time.monotonic() < end:
                        observer.execute("SELECT pg_stat_clear_snapshot()")
                        waiting = observer.execute(
                            "SELECT count(*) AS n FROM pg_stat_activity "
                            "WHERE datname=%s AND wait_event_type='Lock'",
                            (f.config.database.name,),
                        ).fetchone()
                        if waiting and waiting["n"]:
                            break
                        time.sleep(0.01)
                    if not (waiting and waiting["n"]):
                        result = future.result(timeout=5)
                        raise AssertionError(f"safe expiry pre-lock result: {result}")
                    while True:
                        expired = observer.execute(
                            "SELECT expires_at<=clock_timestamp() AS expired "
                            "FROM business.approvals WHERE task_id=%s",
                            (task,),
                        ).fetchone()
                        if expired and expired["expired"]:
                            break
                        time.sleep(0.01)
            assert future.result(timeout=10) == (410, "APPROVAL_EXPIRED")
        assert decision_counts(f, task) == {"decision": 0, "audit": 0, "resume_job": 0}
        expiry_worker, _ = start(f, task)
        try:
            wait_state(f, task, "expired")
            assert decision_counts(f, task) == {"decision": 0, "audit": 0, "resume_job": 0}
            with connect(f.config.database) as db:
                row = db.execute(
                    """SELECT a.status,a.consumed_at,
                 (SELECT count(*) FROM business.jobs j WHERE j.task_id=a.task_id
                 AND j.kind='recover' AND j.payload_ref='expiry:'||a.id::text) AS expiry_jobs
                 FROM business.approvals a WHERE a.task_id=%s""",
                    (task,),
                ).fetchone()
            assert row == {"status": "expired", "consumed_at": None, "expiry_jobs": 1}
        finally:
            if expiry_worker.process.poll() is None:
                expiry_worker.stop_clean()
    finally:
        if child.process.poll() is None:
            child.kill_reap()


def test_actual_pg_static_checkpoint_none_continuation_skips_start_and_second_decision(
    fixture: P3Fixture,
) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle())["task_id"])
    child, owner = start(f, task, "before_delivery_receipt")
    try:
        child.until("after_ready")
        assert post(f, payload(f, task)).status_code == 200
        child.until("before_delivery_receipt")
        child.kill_reap()
        asyncio.run(
            confirm_termination(f.config.database, owner, "A03 compatibility CP SIGKILL/reaped")
        )
        before = asyncio.run(checkpoint_state(f, task))
        assert before.next == ("revalidate",) and not before.interrupts
        counts_before = decision_counts(f, task)
        called: list[str] = []

        async def probe() -> None:
            # 仅兼容探针，revalidate为只读无业务测试node，after断点阻止execute。
            session = WorkerSession(f.config.database, f.inventory.data.organization)
            await session.start()  # 官方旧clean PID已不存在的启动闸门，未伪造确认。
            try:
                with connect(f.config.database) as db:
                    t = db.execute(
                        "SELECT * FROM business.business_tasks WHERE id=%s", (task,)
                    ).fetchone()
                    a = db.execute(
                        "SELECT * FROM business.approvals WHERE task_id=%s", (task,)
                    ).fetchone()
                assert t and a and snapshot_binding(before, t, a) == "execution_boundary"
                graph = StateGraph(ApprovalState)

                async def node(name: str, state: ApprovalState) -> ApprovalState:
                    called.append(name)
                    assert name == "revalidate"
                    assert state["decision_id"] == str(a["decision_id"])
                    return {}

                for name in (
                    "prepare_approval",
                    "wait_approval",
                    "revalidate",
                    "execute",
                    "finish",
                ):

                    async def bound(state: ApprovalState, n: str = name) -> ApprovalState:
                        return await node(n, state)

                    graph.add_node(name, bound)
                graph.add_edge(START, "prepare_approval")
                graph.add_edge("prepare_approval", "wait_approval")
                graph.add_edge("wait_approval", "revalidate")
                graph.add_edge("revalidate", "execute")
                graph.add_edge("execute", "finish")
                graph.add_edge("finish", END)
                async with checkpointer(f.config.database) as saver:
                    compiled = graph.compile(checkpointer=saver, interrupt_after=["revalidate"])
                    await compiled.ainvoke(
                        None, {"configurable": {"thread_id": str(task)}}, durability="sync"
                    )
                    after = await compiled.aget_state({"configurable": {"thread_id": str(task)}})
                    assert after.next == ("execute",) and not after.interrupts
                    assert after.values["decision_id"] == before.values["decision_id"]
            finally:
                await session.close(clean=True)

        asyncio.run(probe())
        assert called == ["revalidate"] and decision_counts(f, task) == counts_before
        with connect(f.config.database) as db:
            a = db.execute(
                "SELECT consumed_at FROM business.approvals WHERE task_id=%s", (task,)
            ).fetchone()
        assert a and a["consumed_at"] is None
        assert task_state(f, task)["state"] == "awaiting_approval"
    finally:
        if child.process.poll() is None:
            child.kill_reap()


@pytest.mark.parametrize(
    "boundary,corrupt_empty",
    [("before_prepare", False), ("before_prepare", True), ("before_graph", False)],
)
def test_p3_lost_worker_lock_exits_and_requires_os_confirmation(
    fixture: P3Fixture, boundary: str, corrupt_empty: bool
) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle())["task_id"])
    child = P3Process(f, "worker", {"task_id": str(task)}, boundary)
    try:
        started = child.until("started")
        child.until(boundary)
        entered = asyncio.run(checkpoint_state(f, task))
        if boundary == "before_graph":
            assert entered.created_at is None and entered.next == () and entered.values == {}
        else:
            assert entered.created_at is not None and entered.next == ("prepare_approval",)
        assert not entered.interrupts
        with connect(f.config.database) as db:
            row = db.execute(
                """SELECT active_plan_id,
                (SELECT count(*) FROM business.replenishment_plans WHERE task_id=%s) AS plans,
                (SELECT count(*) FROM business.approvals WHERE task_id=%s) AS approvals
                FROM business.business_tasks WHERE id=%s""",
                (task, task, task),
            ).fetchone()
        assert row == {"active_plan_id": None, "plans": 0, "approvals": 0}
        with connect(f.config.database) as db:
            original = db.execute(
                "SELECT normalized_request FROM business.business_tasks WHERE id=%s", (task,)
            ).fetchone()
            original_job = db.execute(
                "SELECT id FROM business.jobs WHERE task_id=%s AND kind='analyze'", (task,)
            ).fetchone()
        assert original and original_job
        core = {
            "workflow_version": WORKFLOW_VERSION,
            "task_id": str(task),
            "request_hash": facts_hash(original["normalized_request"]),
        }
        with connect(f.inventory.owner) as db:
            result = db.execute(
                "SELECT pg_terminate_backend(%s) AS stopped", (started["lock_pid"],)
            ).fetchone()
        assert result and result["stopped"]
        if boundary == "before_graph":
            cancelled = child.until("barrier_cancelled")
            assert cancelled["point"] == "before_graph"
        child.release()  # 测试stdin屏障也退出，不把未停线程冒称取消完成。
        child.close_exited(2)
        assert task_state(f, task)["state"] == "needs_attention"
        before = asyncio.run(checkpoint_state(f, task))
        if boundary == "before_graph":
            assert before.created_at is None and before.next == () and before.values == {}
        else:
            assert before.created_at is not None and before.next == ("prepare_approval",)
            assert (
                before.config["configurable"]["checkpoint_id"]
                == entered.config["configurable"]["checkpoint_id"]
            )
            assert before.values == core
        assert not before.interrupts and before.values == entered.values
        with connect(f.config.database) as db:
            for table in ("replenishment_plans", "approvals", "outbox", "executions"):
                empty = db.execute(
                    sql.SQL("SELECT count(*) AS n FROM business.{} WHERE task_id=%s").format(
                        sql.Identifier(table)
                    ),
                    (task,),
                ).fetchone()
                assert empty == {"n": 0}
        blocked = P3Process(f, "worker", {})
        assert blocked.until("blocked")["category"] == "TerminationRequired"
        blocked.close_exited(2)
        asyncio.run(
            confirm_termination(
                f.config.database, started["owner"], "A02 lost-lock process exited and reaped"
            )
        )
        if corrupt_empty:

            async def corrupt_finished_checkpoint() -> None:
                # 本测fresh DB，官方update_state构造有durable CP但未知空next的反例。
                session = WorkerSession(f.config.database, f.inventory.data.organization)
                runner = ApprovalRunner(ApprovalStore(f.config, session))
                with connect(f.config.database) as db:
                    t = db.execute(
                        "SELECT * FROM business.business_tasks WHERE id=%s", (task,)
                    ).fetchone()
                    job = db.execute(
                        "SELECT * FROM business.jobs WHERE task_id=%s", (task,)
                    ).fetchone()
                assert t and job
                request = RunRequest(
                    job["id"],
                    task,
                    t["organization_id"],
                    t["shop_id"],
                    str(task),
                    WORKFLOW_VERSION,
                    "analyze",
                    f"task:{task}",
                    "read-only-probe",
                    0,
                )
                async with checkpointer(f.config.database) as saver:
                    graph = runner.build_graph(request, dict(before.values)).compile(
                        checkpointer=saver
                    )
                    await graph.aupdate_state(
                        {"configurable": {"thread_id": str(task)}},
                        cast(ApprovalState, dict(before.values)),
                        as_node="finish",
                    )

            asyncio.run(corrupt_finished_checkpoint())
            malformed = asyncio.run(checkpoint_state(f, task))
            assert malformed.created_at is not None and malformed.next == ()
            assert malformed.values == before.values and not malformed.interrupts
        restored, _ = start(f, task, "never" if corrupt_empty else "after_t2_commit")
        restored_released = corrupt_empty
        try:
            if corrupt_empty:
                end = time.monotonic() + 10
                while time.monotonic() < end:
                    failure = task_state(f, task)
                    if failure["failure_code"] == "P3_PREPARE_RECOVERY_CHECKPOINT_UNSAFE":
                        break
                    time.sleep(0.02)
                assert failure["state"] == "needs_attention"
                assert failure["failure_code"] == "P3_PREPARE_RECOVERY_CHECKPOINT_UNSAFE"
                unsafe = asyncio.run(checkpoint_state(f, task))
                assert (
                    unsafe.config["configurable"]["checkpoint_id"]
                    == malformed.config["configurable"]["checkpoint_id"]
                )
                assert unsafe.values == malformed.values and unsafe.next == ()
                with connect(f.config.database) as db:
                    for table in ("replenishment_plans", "approvals", "executions", "outbox"):
                        row = db.execute(
                            sql.SQL(
                                "SELECT count(*) AS n FROM business.{} WHERE task_id=%s"
                            ).format(sql.Identifier(table)),
                            (task,),
                        ).fetchone()
                        assert row == {"n": 0}
                return
            restored.until("after_t2_commit")
            # PG T2先提交awaiting_approval，官方wait checkpoint此刻尚未落库。
            # 精确观测合法间隙，不把task状态当作业务interrupt持久证明。
            wait_state(f, task, "awaiting_approval", restoring=True)
            gap = asyncio.run(checkpoint_state(f, task))
            assert gap.created_at is not None and gap.next == ("prepare_approval",)
            assert not gap.interrupts and gap.values == core
            if boundary == "before_prepare":
                assert (
                    gap.config["configurable"]["checkpoint_id"]
                    == before.config["configurable"]["checkpoint_id"]
                )
            with connect(f.config.database) as db:
                readiness = db.execute(
                    "SELECT ready_at FROM business.approvals WHERE task_id=%s", (task,)
                ).fetchone()
                assert readiness == {"ready_at": None}
                execution = db.execute(
                    "SELECT count(*) AS n FROM business.executions WHERE task_id=%s", (task,)
                ).fetchone()
                assert execution == {"n": 0}
            restored.release()
            restored_released = True
            wait_ready(f, task)
            after = asyncio.run(checkpoint_state(f, task))
            assert all(after.values[key] == value for key, value in core.items())
            assert after.next == ("wait_approval",) and len(after.interrupts) == 1
            with connect(f.config.database) as db:
                assert db.execute(
                    "SELECT id FROM business.jobs WHERE task_id=%s AND kind='analyze'", (task,)
                ).fetchall() == [original_job]
                for table in ("replenishment_plans", "approvals", "outbox"):
                    row = db.execute(
                        sql.SQL("SELECT count(*) AS n FROM business.{} WHERE task_id=%s").format(
                            sql.Identifier(table)
                        ),
                        (task,),
                    ).fetchone()
                    assert row and row["n"] == 1
        finally:
            if restored.process.poll() is None:
                if not restored_released:
                    restored.release()
                restored.stop_clean()
    finally:
        if child.process.poll() is None:
            child.kill_reap()


@pytest.mark.parametrize("mutation", ["workflow_version", "plan_version", "unknown_next"])
def test_persisted_checkpoint_mismatch_goes_attention_without_resume_side_effect(
    fixture: P3Fixture, mutation: str
) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle())["task_id"])
    child, _ = start(f, task)
    child.until("after_ready")
    request = payload(f, task)
    child.stop_clean()
    assert post(f, request).status_code == 200

    async def corrupt_test_checkpoint() -> None:
        # 仅本测自有临时数据库。官方update_state构造不可信持久状态，不改业务授权。
        with connect(f.config.database) as db:
            row = db.execute(
                "SELECT * FROM business.business_tasks WHERE id=%s", (task,)
            ).fetchone()
            job = db.execute(
                "SELECT id FROM business.jobs WHERE task_id=%s AND kind='resume'", (task,)
            ).fetchone()
        assert row and job
        session = WorkerSession(f.config.database, row["organization_id"])
        runner = ApprovalRunner(ApprovalStore(f.config, session))
        r = RunRequest(
            job["id"],
            task,
            row["organization_id"],
            row["shop_id"],
            str(task),
            WORKFLOW_VERSION,
            "resume",
            "read-only-probe",
            "read-only-probe",
            0,
        )
        expected = {
            "workflow_version": WORKFLOW_VERSION,
            "task_id": str(task),
            "request_hash": facts_hash(row["normalized_request"]),
        }
        values: ApprovalState = {}
        if mutation == "workflow_version":
            values["workflow_version"] = "unknown-test-version"
        elif mutation == "plan_version":
            values["plan_version"] = 2
        async with checkpointer(f.config.database) as saver:
            graph = runner.build_graph(r, expected).compile(
                checkpointer=saver, interrupt_before=["revalidate"]
            )
            await graph.aupdate_state(
                {"configurable": {"thread_id": str(task)}},
                values,
                as_node="revalidate" if mutation == "unknown_next" else "wait_approval",
            )

    asyncio.run(corrupt_test_checkpoint())
    restored, _ = start(f, task)
    try:
        wait_state(f, task, "needs_attention")
        assert decision_counts(f, task) == {"decision": 1, "audit": 1, "resume_job": 1}
        with connect(f.config.database) as db:
            row = db.execute(
                """SELECT a.consumed_at,r.delivery_state,r.continuation_job_id
             FROM business.approvals a JOIN business.approval_resumes r ON r.approval_id=a.id
             WHERE a.task_id=%s""",
                (task,),
            ).fetchone()
        assert row and row["consumed_at"] is None and row["delivery_state"] == "queued"
        assert row["continuation_job_id"] is None
    finally:
        if restored.process.poll() is None:
            restored.stop_clean()


def test_t3_database_rejects_receipt_rewrite_resume_splice_and_premature_consumption(
    fixture: P3Fixture,
) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle())["task_id"])
    child, _ = start(f, task, "after_delivery_receipt")
    try:
        child.until("after_ready")
        request = payload(f, task)
        assert post(f, request).status_code == 200
        child.until("after_delivery_receipt")
        statements = (
            "UPDATE business.approvals SET consumed_at=clock_timestamp() WHERE task_id=%s",
            "UPDATE business.approval_resumes SET continuation_job_id=job_id WHERE task_id=%s",
            "UPDATE business.web_requests SET result='{}'::jsonb WHERE task_id=%s",
            "UPDATE business.business_tasks SET state='completed' WHERE id=%s",
        )
        with connect(f.config.database) as db:
            for statement in statements:
                with pytest.raises(CheckViolation), db.transaction():
                    db.execute(statement, (task,))
            with pytest.raises(InsufficientPrivilege), db.transaction():
                db.execute("DELETE FROM business.web_requests WHERE task_id=%s", (task,))
        with connect(f.inventory.owner) as db:
            with pytest.raises(CheckViolation), db.transaction():
                db.execute("DELETE FROM business.web_requests WHERE task_id=%s", (task,))
        assert decision_counts(f, task) == {"decision": 1, "audit": 1, "resume_job": 1}
        assert task_state(f, task)["state"] == "executing"
        repeated = post(f, request)
        assert repeated.status_code == 200 and repeated.json()["duplicate"]
        child.release()
        wait_state(f, task, "completed")
    finally:
        if child.process.poll() is None:
            child.stop_clean()


@pytest.mark.parametrize("orphan_kind", ["plan_pending_card", "card_only"])
def test_no_checkpoint_recovery_refuses_database_reachable_orphan_t2_records(
    fixture: P3Fixture, orphan_kind: str
) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle())["task_id"])
    barrier = "never" if orphan_kind == "plan_pending_card" else "before_graph"
    child = P3Process(f, "worker", {"task_id": str(task)}, barrier)
    restored = None
    try:
        owner = child.until("started")["owner"]
        if orphan_kind == "plan_pending_card":
            child.until("after_ready")
            child.kill_reap()
        else:
            child.until("before_graph")
            no_cp = asyncio.run(checkpoint_state(f, task))
            assert no_cp.created_at is None
            # 取本owned进程专用锁PID，当前测试没有其他Worker。
            started = next(row for row in child.history if row["event"] == "started")
            with connect(f.inventory.owner) as db:
                assert db.execute(
                    "SELECT pg_terminate_backend(%s) AS stopped", (started["lock_pid"],)
                ).fetchone() == {"stopped": True}
            assert child.until("barrier_cancelled")["point"] == "before_graph"
            child.release()
            child.close_exited(2)
        blocked = P3Process(f, "worker", {})
        assert blocked.until("blocked")["category"] == "TerminationRequired"
        blocked.close_exited(2)
        with connect(f.config.database) as db:
            # 验证runtime角色下现有FK/trigger确实接受此孤立状态，未停用约束。
            if orphan_kind == "plan_pending_card":
                changed = db.execute(
                    "UPDATE business.business_tasks SET active_plan_id=NULL "
                    "WHERE id=%s RETURNING id",
                    (task,),
                ).fetchone()
                assert changed == {"id": task}
            else:
                from psycopg.types.json import Jsonb

                card = {"schema_version": "p3-web-v1", "approval_id": str(uuid4())}
                db.execute(
                    """INSERT INTO business.outbox(id,organization_id,shop_id,task_id,
                    destination,aggregate_id,aggregate_version,operation,dedupe_key,
                    request_hash,payload,provider_idempotency_key,status)
                    VALUES(%s,%s,%s,%s,'feishu_card',%s,1,'approval_card',%s,%s,%s,%s,'blocked')""",
                    (
                        uuid4(),
                        f.actor.organization_id,
                        f.inventory.data.shop,
                        task,
                        uuid4(),
                        "owned-orphan:" + str(uuid4()),
                        facts_hash(card),
                        Jsonb(card),
                        uuid4(),
                    ),
                )

        async def remove_owned_p3_checkpoint() -> None:
            async with checkpointer(f.config.database) as saver:
                await saver.adelete_thread(str(task))

        asyncio.run(remove_owned_p3_checkpoint())
        before = asyncio.run(checkpoint_state(f, task))
        assert before.created_at is None and before.values == {}
        with connect(f.config.database) as db:
            prior = {}
            for table in ("replenishment_plans", "approvals", "outbox", "executions"):
                prior[table] = db.execute(
                    sql.SQL("SELECT count(*) AS n FROM business.{} WHERE task_id=%s").format(
                        sql.Identifier(table)
                    ),
                    (task,),
                ).fetchone()
            assert prior["outbox"] == {"n": 1} and prior["executions"] == {"n": 0}
            assert prior["approvals"] == {"n": int(orphan_kind == "plan_pending_card")}
        asyncio.run(
            confirm_termination(f.config.database, owner, "A03 orphan fixture OS exit/reaped")
        )
        restored, _ = start(f, task)
        end = time.monotonic() + 10
        while time.monotonic() < end:
            current = task_state(f, task)
            if current["failure_code"] == "P3_PREPARE_RECOVERY_JOB_UNSAFE":
                break
            time.sleep(0.02)
        assert current["state"] == "needs_attention"
        assert current["failure_code"] == "P3_PREPARE_RECOVERY_JOB_UNSAFE"
        after = asyncio.run(checkpoint_state(f, task))
        assert after.created_at is None and after.values == {} and after.next == ()
        with connect(f.config.database) as db:
            for table, expected in prior.items():
                assert (
                    db.execute(
                        sql.SQL("SELECT count(*) AS n FROM business.{} WHERE task_id=%s").format(
                            sql.Identifier(table)
                        ),
                        (task,),
                    ).fetchone()
                    == expected
                )
    finally:
        if child.process.poll() is None:
            child.kill_reap()
        if restored and restored.process.poll() is None:
            restored.stop_clean()
