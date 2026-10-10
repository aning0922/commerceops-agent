"""A03最后时刻权限/实际clock/冻结参数；actual PG，Mock/simulated_web。"""

import json
import time
from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

import pytest
from commerceops.entrypoints.api import create_app
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.replenishment_repository import ReplenishmentStore
from fastapi.testclient import TestClient

from tests.inventory_support import DIRECTORY
from tests.p3_support import ORIGIN, P3Fixture
from tests.test_p3_approval_pg import payload, post, start, wait_state
from tests.test_p3_execution_pg import execute
from tests.test_p3_pg import fixture as fixture

pytestmark = pytest.mark.integration


def configure(f: P3Fixture, **changes: Any) -> None:
    f.config = replace(f.config, **changes)
    private = json.loads(f.config_file.read_text())
    private.update(changes)
    f.config_file.write_text(json.dumps(private))
    f.config_file.chmod(0o600)
    f.store = ReplenishmentStore(f.config, DIRECTORY)
    f.client.close()
    f.client = TestClient(
        create_app(web_config=f.config, replenishment_store=f.store), base_url=ORIGIN
    )
    f.relogin()


@pytest.mark.parametrize(
    "target", ["principal", "auth_version", "credential", "base_scope", "approver_scope"]
)
def test_a01_a04_last_revalidation_checks_current_identity_auth_version_and_role_scope(
    fixture: P3Fixture,
    target: str,
) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle())["task_id"])
    child, _ = start(f, task, "before_revalidate")
    try:
        child.until("after_ready")
        old = payload(f, task)
        assert post(f, old).status_code == 200
        child.until("before_revalidate")
        mutations = {
            "principal": "UPDATE business.principals SET enabled=false,"
            "auth_version=auth_version+1 WHERE id=%s",
            "auth_version": "UPDATE business.principals SET auth_version=auth_version+1 WHERE "
            "id=%s",
            "credential": "UPDATE business.web_credentials SET enabled=false WHERE principal_id=%s",
            "base_scope": "UPDATE business.principal_shop_scopes SET enabled=false WHERE "
            "principal_id=%s",
            "approver_scope": "UPDATE business.principal_role_shop_grants SET enabled=false "
            "WHERE principal_id=%s AND role='approver'",
        }
        with connect(f.inventory.owner) as db:
            db.execute(mutations[target], (f.actor.principal_id,))
        child.release()
        wait_state(f, task, "needs_reapproval")
        with connect(f.config.database) as db:
            assert db.execute(
                "SELECT count(*) AS n FROM business.executions WHERE task_id=%s", (task,)
            ).fetchone() == {"n": 0}
            assert db.execute(
                "SELECT count(*) AS n FROM business.replenishment_items WHERE task_id=%s", (task,)
            ).fetchone() == {"n": 0}
            assert db.execute(
                "SELECT status,consumed_at FROM business.approvals WHERE task_id=%s", (task,)
            ).fetchone() == {"status": "approved", "consumed_at": None}
            assert db.execute(
                "SELECT failure_code FROM business.business_tasks WHERE id=%s", (task,)
            ).fetchone() == {"failure_code": "P3_EXECUTION_PERMISSION_REVOKED"}
    finally:
        if child.process.poll() is None:
            child.stop_clean()


def test_a05_actual_db_expiry_after_historical_approval_has_no_t4_effect(
    fixture: P3Fixture,
) -> None:
    f = fixture
    configure(f, approval_ttl_seconds=60)
    task = UUID(f.create(f.new_cycle())["task_id"])
    child, _ = start(f, task, "before_revalidate")
    try:
        child.until("after_ready")
        old = payload(f, task)
        assert post(f, old).status_code == 200
        child.until("before_revalidate")
        with connect(f.config.database) as db:
            while True:
                row = db.execute(
                    "SELECT expires_at<=clock_timestamp() AS expired FROM business.approvals "
                    "WHERE task_id=%s",
                    (task,),
                ).fetchone()
                if row and row["expired"]:
                    break
                time.sleep(0.25)
        child.release()
        wait_state(f, task, "needs_reapproval")
        with connect(f.config.database) as db:
            assert db.execute(
                "SELECT count(*) AS n FROM business.executions WHERE task_id=%s", (task,)
            ).fetchone() == {"n": 0}
            assert db.execute(
                "SELECT failure_code FROM business.business_tasks WHERE id=%s", (task,)
            ).fetchone() == {"failure_code": "P3_EXECUTION_APPROVAL_EXPIRED"}
    finally:
        if child.process.poll() is None:
            child.stop_clean()


def test_r12_stale_fresh_observation_recollects_without_second_human_interrupt(
    fixture: P3Fixture,
) -> None:
    f = fixture
    configure(f, revalidation_max_age_seconds=1)
    task = UUID(f.create(f.new_cycle())["task_id"])
    child, _ = start(f, task, "before_execute")
    try:
        child.until("after_ready")
        old = payload(f, task)
        assert post(f, old).status_code == 200
        child.until("before_execute")
        with connect(f.config.database) as db:
            while True:
                row = db.execute(
                    "SELECT collected_at+interval '1 second'<=clock_timestamp() AS stale FROM "
                    "business.p3_observations WHERE task_id=%s ORDER BY "
                    "collected_at DESC LIMIT 1",
                    (task,),
                ).fetchone()
                if row and row["stale"]:
                    break
                time.sleep(0.05)
        child.release()
        child.until("before_execute")
        child.release()
        wait_state(f, task, "completed")
        with connect(f.config.database) as db:
            assert db.execute(
                "SELECT count(*) AS n FROM business.approvals WHERE task_id=%s", (task,)
            ).fetchone() == {"n": 1}
            assert db.execute(
                "SELECT count(*) AS n FROM business.p3_observations WHERE task_id=%s", (task,)
            ).fetchone() == {"n": 2}
    finally:
        if child.process.poll() is None:
            child.kill_reap()


def test_frozen_lrs_survives_private_deployment_config_version_change(fixture: P3Fixture) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle())["task_id"])
    child, _ = start(f, task)
    child.until("after_ready")
    old = payload(f, task)
    child.stop_clean()
    configure(f, config_version="private-restart-version-only")
    assert post(f, old).status_code == 200
    restored, _ = start(f, task)
    try:
        wait_state(f, task, "completed")
        with connect(f.config.database) as db:
            assert db.execute(
                "SELECT version FROM business.replenishment_plans WHERE task_id=%s", (task,)
            ).fetchall() == [{"version": 1}]
        receipt = f.client.get(f"/api/v1/tasks/{task}/execution").json()
        assert receipt["approval_id"] == old["approval_id"] and receipt["plan_id"] == old["plan_id"]
    finally:
        if restored.process.poll() is None:
            restored.stop_clean()


def test_legitimate_new_cycle_changed_lrs_same_quantity_requires_new_source_and_confirmation(
    fixture: P3Fixture,
) -> None:
    f = fixture
    first, child, old_receipt = execute(f)
    try:
        item = old_receipt["item_ids"][0]
        assert (
            f.client.post(
                f"/api/v1/replenishment-items/{item}/resolve",
                json={
                    "schema_version": "p3-web-v1",
                    "request_key": str(uuid4()),
                    "action": "close",
                    "reason": "新周期独立分析",
                    "expected_version": 1,
                },
                headers=f.headers(),
            ).status_code
            == 200
        )
        new = f.new_cycle()
        new["parameters"].update(L=2, R=8, S=2)
        second = UUID(f.create(new)["task_id"])
        child.until("after_ready")
        request = payload(f, second)
        assert (
            request["plan_id"] != old_receipt["plan_id"]
            and request["approval_id"] != old_receipt["approval_id"]
        )
        with connect(f.config.database) as db:
            sources = db.execute(
                "SELECT source_task_id,parameters,facts_hash FROM business.p3_task_sources "
                "WHERE task_id IN (%s,%s) ORDER BY parameters->>'L'",
                (first, second),
            ).fetchall()
            assert (
                len(sources) == 2 and sources[0]["source_task_id"] != sources[1]["source_task_id"]
            )
            assert sources[0]["facts_hash"] != sources[1]["facts_hash"]
        assert post(f, request).status_code == 200
        wait_state(f, second, "completed")
        execution = f.client.get(f"/api/v1/tasks/{second}/execution").json()
        assert execution["operation_key"] != old_receipt["operation_key"]
        assert (
            f.client.get(f"/api/v1/replenishment-items/{execution['item_ids'][0]}").json()["item"][
                "quantity"
            ]
            == 100
        )
        assert (
            f.client.get(f"/api/v1/tasks/{first}/execution").json()["execution_id"]
            == old_receipt["execution_id"]
        )
    finally:
        if child.process.poll() is None:
            child.stop_clean()
