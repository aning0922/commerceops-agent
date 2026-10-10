"""R12单Worker/串行同池整批failclosed；终态释放后显式新cycle。"""

from uuid import UUID, uuid4

import pytest
from commerceops.infrastructure.database import connect

from tests.p3_support import P3Fixture
from tests.test_p3_approval_pg import payload, post, start, wait_state
from tests.test_p3_pg import fixture as fixture

pytestmark = pytest.mark.integration


def test_r12_two_approved_two_item_plans_same_pools_second_whole_plan_has_no_effect(
    fixture: P3Fixture,
) -> None:
    f = fixture
    first = UUID(f.create(f.new_cycle("unknown_inbound"))["task_id"])
    child, _ = start(f, first, "before_revalidate", controlled="two_unknown")
    try:
        child.until("after_ready")
        second = UUID(f.create(f.new_cycle("unknown_inbound"))["task_id"])
        child.until("after_ready")
        first_request = payload(f, first, "approve_with_assumptions")
        second_request = payload(f, second, "approve_with_assumptions")
        assert post(f, first_request).status_code == 200
        child.until("before_revalidate")
        assert post(f, second_request).status_code == 200  # 第一个Graph在途，第二个仍持久排队。
        child.release()
        wait_state(f, first, "completed")
        child.until("before_revalidate")
        child.release()
        wait_state(f, second, "needs_reapproval")
        with connect(f.config.database) as db:
            assert db.execute(
                "SELECT count(*) AS n FROM business.replenishment_items WHERE task_id=%s", (first,)
            ).fetchone() == {"n": 2}
            assert db.execute(
                "SELECT count(*) AS n FROM business.replenishment_items WHERE task_id=%s", (second,)
            ).fetchone() == {"n": 0}
            assert db.execute(
                "SELECT count(*) AS n FROM business.executions WHERE task_id=%s", (second,)
            ).fetchone() == {"n": 0}
            assert db.execute(
                "SELECT consumed_at FROM business.approvals WHERE task_id=%s", (second,)
            ).fetchone() == {"consumed_at": None}
        old_execution = f.client.get(f"/api/v1/tasks/{first}/execution").json()
        keys = []
        for item in old_execution["item_ids"]:
            request = {
                "schema_version": "p3-web-v1",
                "request_key": str(uuid4()),
                "action": "close",
                "reason": "关闭整批后独立周期",
                "expected_version": 1,
            }
            assert (
                f.client.post(
                    f"/api/v1/replenishment-items/{item}/resolve", json=request, headers=f.headers()
                ).status_code
                == 200
            )
            keys.append((item, request))
        third = UUID(f.create(f.new_cycle("unknown_inbound"))["task_id"])
        child.until("after_ready")
        current = payload(f, third, "approve_with_assumptions")
        assert (
            current["plan_id"] != first_request["plan_id"]
            and current["nonce"] != first_request["nonce"]
        )
        assert post(f, current).status_code == 200
        child.until("before_revalidate")
        child.release()
        wait_state(f, third, "completed")
        for item, request in keys:
            repeated = f.client.post(
                f"/api/v1/replenishment-items/{item}/resolve", json=request, headers=f.headers()
            )
            assert repeated.status_code == 200 and repeated.json()["duplicate"]
        new = f.client.get(f"/api/v1/tasks/{third}/execution").json()
        assert new["execution_id"] != old_execution["execution_id"] and set(
            new["item_ids"]
        ).isdisjoint(old_execution["item_ids"])
        assert (
            f.client.get(f"/api/v1/tasks/{first}/execution").json()["execution_id"]
            == old_execution["execution_id"]
        )
    finally:
        if child.process.poll() is None:
            child.kill_reap()
