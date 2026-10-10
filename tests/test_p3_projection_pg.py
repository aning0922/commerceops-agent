"""实际PG/本地controlled_stub projection故障/对账；sender永久关闭。"""

from typing import Any
from uuid import UUID, uuid4

import pytest
from commerceops.infrastructure.database import connect
from psycopg.errors import CheckViolation

from tests.p3_support import P3Fixture, P3Process
from tests.test_p3_execution_pg import execute
from tests.test_p3_pg import fixture as fixture

pytestmark = pytest.mark.integration


def command(
    f: P3Fixture, identifier: UUID, operation: str, *, unknown: bool = False
) -> dict[str, Any]:
    child = P3Process(
        f,
        "projection",
        {"outbox_id": str(identifier), "operation": operation, "unknown": unknown},
        "never",
    )
    try:
        result = child.until("ack")
        child.close_exited(0)
        return result
    finally:
        if child.process.poll() is None:
            child.kill_reap()


@pytest.mark.parametrize("unknown", [False, True])
def test_c01_c04_failure_unknown_repair_stale_does_not_mutate_business_terminal(
    fixture: P3Fixture,
    unknown: bool,
) -> None:
    f = fixture
    task, worker, execution = execute(f)
    worker.stop_clean()
    item = UUID(execution["item_ids"][0])
    with connect(f.config.database) as db:
        intent = db.execute(
            "SELECT * FROM business.outbox WHERE aggregate_id=%s AND operation='item_projection'",
            (item,),
        ).fetchone()
    assert intent
    original = {
        key: intent[key]
        for key in (
            "id",
            "aggregate_id",
            "aggregate_version",
            "dedupe_key",
            "request_hash",
            "payload",
            "provider_idempotency_key",
        )
    }
    command(f, intent["id"], "failure", unknown=unknown)
    view = f.client.get(f"/api/v1/replenishment-items/{item}").json()
    assert view["item"]["sync"]["state"] == ("unknown" if unknown else "failed")
    assert view["item"]["sync"]["projections"][0]["source_mode"] == "controlled_stub"
    for _ in range(2):
        assert command(f, intent["id"], "reconcile")["outcome"] == (
            "unknown_held" if unknown else "missing"
        )
    view = f.client.get(f"/api/v1/replenishment-items/{item}").json()
    assert view["item"]["state"] == "open" and view["item"]["version"] == 1
    assert view["item"]["sync"]["state"] == ("unknown" if unknown else "pending")
    request = {
        "schema_version": "p3-web-v1",
        "request_key": str(uuid4()),
        "action": "close",
        "reason": "业务关闭与projection故障分离",
        "expected_version": 1,
    }
    assert (
        f.client.post(
            f"/api/v1/replenishment-items/{item}/resolve", json=request, headers=f.headers()
        ).status_code
        == 200
    )
    assert command(f, intent["id"], "reconcile")["outcome"] == "stale"
    view = f.client.get(f"/api/v1/replenishment-items/{item}").json()
    assert view["item"]["state"] == "closed" and view["item"]["version"] == 2
    assert view["item"]["sync"]["state"] == "pending"
    assert not view["item"]["sync"]["sender_enabled"]
    assert all(p["state"] != "synced" for p in view["item"]["sync"]["projections"])
    with connect(f.config.database) as db:
        after = db.execute("SELECT * FROM business.outbox WHERE id=%s", (intent["id"],)).fetchone()
        assert after and {key: after[key] for key in original} == original
        assert after["status"] == "dead" and after["external_id"] is None
        assert db.execute(
            "SELECT count(*) AS n FROM business.outbox_reconciliations WHERE outbox_id=%s",
            (intent["id"],),
        ).fetchone() == {"n": 2}
        assert db.execute(
            "SELECT state FROM business.business_tasks WHERE id=%s", (task,)
        ).fetchone() == {"state": "completed"}


def test_c05_original_projection_identity_immutable_no_false_sent_or_unknown_retry(
    fixture: P3Fixture,
) -> None:
    f = fixture
    _, worker, execution = execute(f)
    worker.stop_clean()
    item = UUID(execution["item_ids"][0])
    with connect(f.config.database) as db:
        row = db.execute("SELECT id FROM business.outbox WHERE aggregate_id=%s", (item,)).fetchone()
    assert row
    command(f, row["id"], "failure", unknown=True)
    with connect(f.inventory.owner) as db:
        for statement in (
            "UPDATE business.outbox SET payload='{}'::jsonb WHERE id=%s",
            "UPDATE business.outbox SET request_hash=repeat('0',64) WHERE id=%s",
            "UPDATE business.outbox SET provider_idempotency_key=gen_random_uuid() WHERE id=%s",
            "UPDATE business.outbox SET status='sent',external_id='fake' WHERE id=%s",
            "UPDATE business.outbox SET sender_enabled=true WHERE id=%s",
            "UPDATE business.outbox SET status='pending' WHERE id=%s",
            "UPDATE business.outbox SET source_mode='mock' WHERE id=%s",
            "DELETE FROM business.outbox WHERE id=%s",
        ):
            with pytest.raises(CheckViolation), db.transaction():
                db.execute(statement, (row["id"],))
