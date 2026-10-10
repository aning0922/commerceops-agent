"""A03实际PG/会话/T4/T6；mock/session/simulated_web，零库存或外部写。"""

from typing import Any
from uuid import UUID, uuid4

import pytest
from commerceops.application.replenishment.contracts import ResolveInput
from commerceops.application.replenishment.execution import resolution_hash
from commerceops.infrastructure.database import connect
from psycopg.errors import CheckViolation, InsufficientPrivilege

from tests.p3_support import P3Fixture, P3Process
from tests.test_p3_approval_pg import payload, post, wait_state
from tests.test_p3_pg import fixture as fixture

pytestmark = pytest.mark.integration


def execute(f: P3Fixture, case: str = "baseline") -> tuple[UUID, P3Process, dict[str, Any]]:
    task = UUID(f.create(f.new_cycle(case))["task_id"])
    child = P3Process(f, "worker", {"task_id": str(task)}, "never")
    try:
        child.until("after_ready")
        request = payload(
            f, task, "approve_with_assumptions" if case == "unknown_inbound" else "approve"
        )
        assert post(f, request).status_code == 200
        wait_state(f, task, "completed")
        result = f.client.get(f"/api/v1/tasks/{task}/execution")
        assert result.status_code == 200
        return task, child, result.json()
    except BaseException:
        if child.process.poll() is None:
            child.kill_reap()
        raise


@pytest.mark.parametrize("case", ["baseline", "unknown_inbound"])
def test_t4_one_permanent_execution_all_items_consumption_and_task_commit(
    fixture: P3Fixture, case: str
) -> None:
    f = fixture
    task, child, receipt = execute(f, case)
    try:
        with connect(f.config.database) as db:
            row = db.execute(
                "SELECT count(*) AS n FROM business.executions WHERE task_id=%s", (task,)
            ).fetchone()
            a = db.execute(
                "SELECT status,consumed_at FROM business.approvals WHERE task_id=%s", (task,)
            ).fetchone()
            rows = db.execute(
                "SELECT * FROM business.replenishment_items WHERE task_id=%s", (task,)
            ).fetchall()
            event = db.execute(
                """SELECT count(*) AS n FROM business.audit_events
                WHERE task_id=%s AND action='execution_committed'""",
                (task,),
            ).fetchone()
        assert (
            row
            and row["n"] == 1
            and a
            and a["status"] == "approved"
            and a["consumed_at"] is not None
        )
        assert len(rows) == 1 and rows[0]["quantity"] == 100 and rows[0]["status"] == "open"
        assert event and event["n"] == 1 and receipt["item_ids"] == [str(rows[0]["id"])]
        assert receipt["sync"]["state"] == "pending" and not receipt["sync"]["sender_enabled"]
        item = f.client.get(f"/api/v1/replenishment-items/{rows[0]['id']}")
        assert item.status_code == 200 and item.json()["can_resolve"]
        listing = f.client.get("/api/v1/replenishment-items").json()
        assert listing["total"] == 1 and listing["counts"] == {
            "open": 1,
            "completed": 0,
            "closed": 0,
        }
        detail = f.client.get(f"/api/v1/tasks/{task}").json()
        assert (
            detail["execution_id"] == receipt["execution_id"]
            and detail["visible_item_ids"] == receipt["item_ids"]
        )
    finally:
        if child.process.poll() is None:
            child.stop_clean()


@pytest.mark.parametrize("action,state", [("complete", "completed"), ("close", "closed")])
def test_t6_unicode_reason_original_key_ten_replays_and_terminal_conflicts(
    fixture: P3Fixture, action: str, state: str
) -> None:
    f = fixture
    task, child, execution = execute(f)
    try:
        identifier = execution["item_ids"][0]
        reason = "\u001c\u3000库存跟进 Cafe\u0301 Ａ\u3000\u001f"
        request = {
            "schema_version": "p3-web-v1",
            "request_key": str(uuid4()),
            "action": action,
            "reason": reason,
            "expected_version": 1,
        }
        url = f"/api/v1/replenishment-items/{identifier}/resolve"
        first = f.client.post(url, json=request, headers=f.headers())
        assert first.status_code == 200
        receipt = first.json()
        assert receipt["item"]["state"] == state and receipt["item"]["version"] == 2
        assert receipt["resolution"]["reason"] == reason.strip()
        typed = ResolveInput.model_validate_json(__import__("json").dumps(request))
        assert receipt["resolution"]["resolution_payload_hash"] == resolution_hash(
            identifier, typed
        )
        for _ in range(9):
            repeated = f.client.post(url, json=request, headers=f.headers())
            assert repeated.status_code == 200 and repeated.json()["duplicate"]
            assert repeated.json()["resolution"] == receipt["resolution"]
        restored = f.client.get(f"/api/v1/requests/{request['request_key']}?operation=resolve")
        assert restored.status_code == 200 and restored.json()["receipt"]["result"] == receipt
        for change in (
            {"reason": "库存跟进 Café Ａ"},
            {"action": "close" if action == "complete" else "complete"},
        ):
            conflict = f.client.post(url, json={**request, **change}, headers=f.headers())
            assert (
                conflict.status_code == 409
                and conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
            )
        conflict = f.client.post(
            url, json={**request, "request_key": str(uuid4())}, headers=f.headers()
        )
        assert (
            conflict.status_code == 409
            and conflict.json()["error"]["code"] == "ITEM_STATE_CONFLICT"
        )
        with connect(f.config.database) as db:
            audit = db.execute(
                "SELECT count(*) AS n FROM business.audit_events WHERE task_id=%s AND action=%s",
                (task, "item_" + state),
            ).fetchone()
            intents = db.execute(
                """SELECT count(*) AS n FROM business.outbox WHERE aggregate_id=%s
                AND aggregate_version=2 AND operation='item_projection'""",
                (UUID(identifier),),
            ).fetchone()
        assert audit and audit["n"] == 1 and intents and intents["n"] == 1
        assert f.client.get(f"/api/v1/tasks/{task}").json()["task"]["state"] == "completed"
    finally:
        if child.process.poll() is None:
            child.stop_clean()


def test_t6_strict_version_empty_reason_and_database_terminal_immutability(
    fixture: P3Fixture,
) -> None:
    f = fixture
    _, child, execution = execute(f)
    try:
        identifier = execution["item_ids"][0]
        url = f"/api/v1/replenishment-items/{identifier}/resolve"
        request = {
            "schema_version": "p3-web-v1",
            "request_key": str(uuid4()),
            "action": "close",
            "reason": "无需继续",
            "expected_version": 1,
        }
        for changed in (
            {"reason": " \t\n\u3000"},
            {"expected_version": True},
            {"expected_version": 1.0},
            {"actor": str(uuid4())},
        ):
            assert (
                f.client.post(url, json={**request, **changed}, headers=f.headers()).status_code
                == 422
            )
        conflict = f.client.post(url, json={**request, "expected_version": 2}, headers=f.headers())
        assert (
            conflict.status_code == 409
            and conflict.json()["error"]["code"] == "ITEM_VERSION_CONFLICT"
        )
        assert f.client.post(url, json=request, headers=f.headers()).status_code == 200
        with connect(f.config.database) as db:
            for statement in (
                "UPDATE business.replenishment_items SET status='open' WHERE id=%s",
                "UPDATE business.replenishment_items SET quantity=quantity+1 WHERE id=%s",
            ):
                with pytest.raises(CheckViolation), db.transaction():
                    db.execute(statement, (UUID(identifier),))
            with pytest.raises(InsufficientPrivilege), db.transaction():
                db.execute(
                    "DELETE FROM business.executions WHERE id=%s",
                    (UUID(execution["execution_id"]),),
                )
    finally:
        if child.process.poll() is None:
            child.stop_clean()
