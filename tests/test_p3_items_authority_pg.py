"""T6当前同店approver/隐藏源任务/终态并发；实际PG+session。"""

import json
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from commerceops.application.replenishment.contracts import ResolveInput, WebActor, WebFailure
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.replenishment_items import ItemStore

from tests.p3_support import ORIGIN, P3Fixture
from tests.test_p3_approval_pg import second_approver
from tests.test_p3_execution_pg import execute
from tests.test_p3_pg import fixture as fixture

pytestmark = pytest.mark.integration


def test_c01_c02_late_same_shop_approver_can_resolve_without_source_task_or_frozen_eligible(
    fixture: P3Fixture,
) -> None:
    f = fixture
    task, worker, receipt = execute(f)
    other, actor = second_approver(f)  # execution已完成，绝不属于历史eligible。
    try:
        item = receipt["item_ids"][0]
        assert other.get(f"/api/v1/tasks/{task}").status_code == 404
        assert other.get(f"/api/v1/approvals/{receipt['approval_id']}").status_code == 404
        assert other.get("/api/v1/tasks").json()["total"] == 0
        view = other.get(f"/api/v1/replenishment-items/{item}")
        assert view.status_code == 200
        assert (
            view.json()["visible_source_task_id"] is None and view.json()["visible_plan_id"] is None
        )
        assert (
            view.json()["can_resolve"]
            and other.get("/api/v1/replenishment-items").json()["total"] == 1
        )
        request = {
            "schema_version": "p3-web-v1",
            "request_key": str(uuid4()),
            "action": "complete",
            "reason": "当前同店跟进",
            "expected_version": 1,
        }
        headers = {
            "Origin": ORIGIN,
            "X-CSRF-Token": other.get("/api/v1/auth/session").json()["csrf_token"],
        }
        result = other.post(
            f"/api/v1/replenishment-items/{item}/resolve", json=request, headers=headers
        )
        assert result.status_code == 200 and result.json()["resolution"]["resolved_by"] == str(
            actor.principal_id
        )
        assert (
            other.get(f"/api/v1/requests/{request['request_key']}?operation=resolve").status_code
            == 200
        )
        assert other.get(f"/api/v1/tasks/{task}").status_code == 404
    finally:
        other.close()
        if worker.process.poll() is None:
            worker.stop_clean()


@pytest.mark.parametrize("mode", ["operator", "admin", "cross_shop"])
def test_t6_operator_admin_cross_shop_have_no_write_and_no_actor_body_or_count_leak(
    fixture: P3Fixture,
    mode: str,
) -> None:
    f = fixture
    _, worker, receipt = execute(f)
    try:
        worker.stop_clean()
        item = receipt["item_ids"][0]
        with connect(f.inventory.owner) as db:
            db.execute(
                "DELETE FROM business.principal_role_shop_grants WHERE principal_id=%s AND "
                "role='approver'",
                (f.actor.principal_id,),
            )
            if mode == "admin":
                db.execute(
                    "UPDATE business.principals SET roles=ARRAY['admin'],"
                    "auth_version=auth_version+1 WHERE id=%s",
                    (f.actor.principal_id,),
                )
                db.execute(
                    "INSERT INTO business.principal_role_shop_grants VALUES(%s,%s,%s,'admin',true)",
                    (f.actor.organization_id, f.inventory.data.shop, f.actor.principal_id),
                )
            elif mode == "cross_shop":
                shop = uuid4()
                db.execute(
                    "INSERT INTO business.shops(id,organization_id,adapter_kind,"
                    "external_shop_key,timezone,currency,config_ref,"
                    "environment) VALUES(%s,%s,'mock',%s,'Asia/Shanghai',"
                    "'CNY','owned-p3','test')",
                    (shop, f.actor.organization_id, str(shop)),
                )
                db.execute(
                    "INSERT INTO business.principal_shop_scopes VALUES(%s,%s,%s,true)",
                    (f.actor.organization_id, shop, f.actor.principal_id),
                )
                db.execute(
                    "INSERT INTO business.principal_role_shop_grants VALUES(%s,%s,%s,'approver',"
                    "true)",
                    (f.actor.organization_id, shop, f.actor.principal_id),
                )
        assert f.client.get("/api/v1/auth/session").status_code == 401
        f.relogin()
        view = f.client.get(f"/api/v1/replenishment-items/{item}")
        if mode != "admin":
            assert view.status_code == 200 and not view.json()["can_resolve"]
        else:
            assert (
                view.status_code == 403
                and f.client.get("/api/v1/replenishment-items").status_code == 403
            )
        denied = f.client.post(
            f"/api/v1/replenishment-items/{item}/resolve", content="broken", headers=f.headers()
        )
        assert denied.status_code == (404 if mode == "cross_shop" else 403)
        with connect(f.config.database) as db:
            assert db.execute(
                "SELECT status,version FROM business.replenishment_items WHERE id=%s", (UUID(item),)
            ).fetchone() == {"status": "open", "version": 1}
    finally:
        if worker.process.poll() is None:
            worker.stop_clean()


def test_c04_complete_close_two_current_actors_real_transaction_race_one_winner(
    fixture: P3Fixture,
) -> None:
    f = fixture
    task, worker, receipt = execute(f)
    other, actor = second_approver(f)
    try:
        item = UUID(receipt["item_ids"][0])
        store = ItemStore(f.store)
        body = ResolveInput.model_validate_json(
            json.dumps(
                {
                    "schema_version": "p3-web-v1",
                    "request_key": str(uuid4()),
                    "action": "complete",
                    "reason": "并发跟进",
                    "expected_version": 1,
                }
            )
        )
        opposite = body.model_copy(update={"request_key": uuid4(), "action": "close"})

        def send(who: WebActor, request: ResolveInput) -> tuple[int, str]:
            try:
                return 200, str(store.resolve(who, item, request)["item"]["state"])
            except WebFailure as error:
                return error.status, error.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(send, f.actor, body), pool.submit(send, actor, opposite)]
            results = [j.result(timeout=15) for j in jobs]
        assert sorted(code for code, _ in results) == [200, 409]
        assert [code for status, code in results if status == 409] == ["ITEM_STATE_CONFLICT"]
        with connect(f.config.database) as db:
            assert db.execute(
                "SELECT version FROM business.replenishment_items WHERE id=%s", (item,)
            ).fetchone() == {"version": 2}
            assert db.execute(
                "SELECT count(*) AS n FROM business.outbox WHERE aggregate_id=%s AND "
                "aggregate_version=2",
                (item,),
            ).fetchone() == {"n": 1}
            assert db.execute(
                "SELECT count(*) AS n FROM business.audit_events WHERE task_id=%s AND action IN "
                "('item_completed','item_closed')",
                (task,),
            ).fetchone() == {"n": 1}
    finally:
        other.close()
        if worker.process.poll() is None:
            worker.stop_clean()
