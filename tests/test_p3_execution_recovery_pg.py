"""A03真实SIGKILL/旧PID闸门/持久回执；受控Mock/session/simulated_web。"""

import asyncio
import time
from typing import Any
from uuid import UUID, uuid4

import pytest
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.worker_lock import confirm_termination
from psycopg import sql

from tests.p3_support import P3Fixture, P3Process
from tests.test_p3_approval_pg import checkpoint_state, payload, post, start, wait_state
from tests.test_p3_execution_pg import execute
from tests.test_p3_pg import fixture as fixture

pytestmark = pytest.mark.integration


def reap_and_confirm(f: P3Fixture, child: P3Process, owner: str) -> None:
    child.kill_reap()
    blocked = P3Process(f, "worker", {})
    assert blocked.until("blocked")["category"] == "TerminationRequired"
    blocked.close_exited(2)
    asyncio.run(confirm_termination(f.config.database, owner, "A03 owned SIGKILL; OS wait=-9"))


def wait_jobs(f: P3Fixture, task: UUID) -> None:
    end = time.monotonic() + 15
    while time.monotonic() < end:
        with connect(f.config.database) as db:
            row = db.execute(
                "SELECT count(*) AS n FROM business.jobs WHERE task_id=%s AND status<>'done'",
                (task,),
            ).fetchone()
        if row and row["n"] == 0:
            return
        time.sleep(0.02)
    raise AssertionError("bounded actual execution jobs deadline")


@pytest.mark.parametrize("barrier", ["after_first_t4_item", "before_t4_commit", "after_t4_commit"])
def test_r10_r11_real_kill_whole_t4_transaction_or_permanent_replay_after_item_closed(
    fixture: P3Fixture,
    barrier: str,
) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle("unknown_inbound"))["task_id"])
    child, owner = start(f, task, barrier, controlled="two_unknown")
    restored = None
    try:
        child.until("after_ready")
        assert post(f, payload(f, task, "approve_with_assumptions")).status_code == 200
        child.until(barrier)
        checkpoint = asyncio.run(checkpoint_state(f, task))
        assert checkpoint.next == ("execute",) and not checkpoint.interrupts
        reap_and_confirm(f, child, owner)
        with connect(f.config.database) as db:
            counts = {}
            for table in ("executions", "replenishment_items"):
                row = db.execute(
                    sql.SQL("SELECT count(*) AS n FROM business.{} WHERE task_id=%s").format(
                        sql.Identifier(table)
                    ),
                    (task,),
                ).fetchone()
                assert row
                counts[table] = row["n"]
            a = db.execute(
                "SELECT consumed_at FROM business.approvals WHERE task_id=%s", (task,)
            ).fetchone()
            audit = db.execute(
                "SELECT count(*) AS n FROM business.audit_events WHERE "
                "task_id=%s AND action='execution_committed'",
                (task,),
            ).fetchone()
            projections = db.execute(
                "SELECT count(*) AS n FROM business.outbox WHERE task_id=%s AND "
                "operation='item_projection'",
                (task,),
            ).fetchone()
        committed = barrier == "after_t4_commit"
        assert counts == {"executions": int(committed), "replenishment_items": 2 * int(committed)}
        assert a and (a["consumed_at"] is not None) == committed
        assert (
            audit
            and projections
            and audit["n"] == int(committed)
            and projections["n"] == 2 * int(committed)
        )
        old = None
        if committed:
            old = f.client.get(f"/api/v1/tasks/{task}/execution").json()
            item = old["item_ids"][0]
            closed = f.client.post(
                f"/api/v1/replenishment-items/{item}/resolve",
                json={
                    "schema_version": "p3-web-v1",
                    "request_key": str(uuid4()),
                    "action": "close",
                    "reason": "恢复前关闭仍不得重复执行",
                    "expected_version": 1,
                },
                headers=f.headers(),
            )
            assert closed.status_code == 200
        restored, _ = start(f, task, controlled="two_unknown")
        wait_state(f, task, "completed", restoring=True)
        wait_jobs(f, task)
        after = asyncio.run(checkpoint_state(f, task))
        assert after.next == () and not after.interrupts
        for key in (
            "workflow_version",
            "task_id",
            "request_hash",
            "plan_id",
            "approval_id",
            "plan_hash",
            "decision_id",
            "decision_hash",
        ):
            assert after.values[key] == checkpoint.values[key]
        execution = f.client.get(f"/api/v1/tasks/{task}/execution").json()
        if old:
            assert (
                execution["execution_id"] == old["execution_id"]
                and execution["item_ids"] == old["item_ids"]
            )
            assert (
                f.client.get(f"/api/v1/replenishment-items/{item}").json()["item"]["state"]
                == "closed"
            )
        with connect(f.config.database) as db:
            assert db.execute(
                "SELECT count(*) AS n FROM business.executions WHERE task_id=%s", (task,)
            ).fetchone() == {"n": 1}
            assert db.execute(
                "SELECT count(*) AS n FROM business.replenishment_items WHERE task_id=%s", (task,)
            ).fetchone() == {"n": 2}
    finally:
        if child.process.poll() is None:
            child.kill_reap()
        if restored and restored.process.poll() is None:
            restored.stop_clean()


@pytest.mark.parametrize(
    "barrier,early",
    [
        ("before_replacement_commit", False),
        ("after_replacement_commit", False),
        ("after_replacement_commit", True),
    ],
)
def test_r09_replacement_commit_checkpoint_gap_reuses_one_version_and_early_t3_waits(
    fixture: P3Fixture,
    barrier: str,
    early: bool,
) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle())["task_id"])
    child = P3Process(
        f, "worker", {"task_id": str(task), "revalidation_controlled": "stock_change"}, barrier
    )
    owner = child.until("started")["owner"]
    restored = None
    try:
        child.until("after_ready")
        old = payload(f, task)
        assert post(f, old).status_code == 200
        child.until(barrier)
        saved = asyncio.run(checkpoint_state(f, task))
        assert saved.next == ("revalidate",) and saved.values["plan_version"] == 1
        if early:
            current = payload(f, task)
            result = post(f, current)
            assert (
                result.status_code == 200 and result.json()["resume_state"] == "waiting_checkpoint"
            )
        reap_and_confirm(f, child, owner)
        with connect(f.config.database) as db:
            count = db.execute(
                "SELECT count(*) AS n FROM business.replenishment_plans WHERE task_id=%s", (task,)
            ).fetchone()
            observations = db.execute(
                "SELECT count(*) AS n FROM business.p3_observations WHERE task_id=%s", (task,)
            ).fetchone()
        assert count == {"n": 1 if barrier == "before_replacement_commit" else 2}
        assert observations == {"n": 0 if barrier == "before_replacement_commit" else 1}
        restored = P3Process(
            f, "worker", {"task_id": str(task), "revalidation_controlled": "stock_change"}, "never"
        )
        if not early:
            restored.until("after_ready")
            current = payload(f, task)
            assert current["plan_version"] == 2
            assert post(f, current).status_code == 200
        wait_state(f, task, "completed", restoring=True)
        wait_jobs(f, task)
        with connect(f.config.database) as db:
            assert db.execute(
                "SELECT count(*) AS n FROM business.replenishment_plans WHERE task_id=%s", (task,)
            ).fetchone() == {"n": 2}
            assert db.execute(
                "SELECT count(*) AS n FROM business.p3_revalidation_transitions "
                "WHERE task_id=%s AND applied_at IS NOT NULL",
                (task,),
            ).fetchone() == {"n": 1}
        receipt = f.client.get(f"/api/v1/tasks/{task}/execution").json()
        assert receipt["plan_id"] == current["plan_id"]
        assert receipt["approval_id"] != old["approval_id"]
        assert post(f, old).status_code == 200
    finally:
        if child.process.poll() is None:
            child.kill_reap()
        if restored and restored.process.poll() is None:
            restored.stop_clean()


@pytest.mark.parametrize("barrier", ["before_t6_commit", "after_t6_commit"])
def test_t6_actual_sigkill_atomic_or_original_receipt(fixture: P3Fixture, barrier: str) -> None:
    f = fixture
    task, worker, execution = execute(f)
    worker.stop_clean()
    request: dict[str, Any] = {
        "schema_version": "p3-web-v1",
        "request_key": str(uuid4()),
        "action": "complete",
        "reason": "实际提交恢复",
        "expected_version": 1,
    }
    item = execution["item_ids"][0]
    child = P3Process(f, "resolve", {"item_id": item, "request": request}, barrier)
    try:
        child.until(barrier)
        child.kill_reap()
        with connect(f.config.database) as db:
            row = db.execute(
                "SELECT status,version FROM business.replenishment_items WHERE id=%s", (UUID(item),)
            ).fetchone()
            receipts = db.execute(
                "SELECT count(*) AS n FROM business.web_requests WHERE "
                "operation='resolve' AND request_key=%s",
                (UUID(request["request_key"]),),
            ).fetchone()
        committed = barrier == "after_t6_commit"
        assert row == {
            "status": "completed" if committed else "open",
            "version": 2 if committed else 1,
        }
        assert receipts == {"n": int(committed)}
        replay = f.client.post(
            f"/api/v1/replenishment-items/{item}/resolve", json=request, headers=f.headers()
        )
        assert replay.status_code == 200 and replay.json()["duplicate"] == committed
        assert f.client.get(f"/api/v1/tasks/{task}").json()["task"]["state"] == "completed"
    finally:
        if child.process.poll() is None:
            child.kill_reap()
