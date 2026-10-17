"""A03同thread新版显式审批与不可变来源；实际PG/Mock/simulated_web。"""

import hashlib
from uuid import UUID

import pytest
from commerceops.infrastructure.database import connect
from psycopg import sql

from tests.p3_support import P3Fixture, P3Process
from tests.test_p3_approval_pg import payload, post, wait_state
from tests.test_p3_pg import fixture as fixture

pytestmark = pytest.mark.integration


def original_hashes(f: P3Fixture, task: UUID) -> dict[str, str]:
    with connect(f.config.database) as db:
        bound = db.execute(
            "SELECT * FROM business.p3_task_sources WHERE task_id=%s", (task,)
        ).fetchone()
        assert bound
        parent = bound["source_task_id"]
        result = {}
        for name, column, key in [
            ("business.business_tasks", "id", parent),
            ("business.commerce_snapshots", "task_id", parent),
            ("business.snapshot_products", "snapshot_id", bound["snapshot_id"]),
            ("business.snapshot_order_lines", "snapshot_id", bound["snapshot_id"]),
            ("business.snapshot_refunds", "snapshot_id", bound["snapshot_id"]),
            ("business.analysis_reports", "task_id", parent),
            ("checkpoints.checkpoints", "thread_id", str(parent)),
            ("checkpoints.checkpoint_blobs", "thread_id", str(parent)),
            ("checkpoints.checkpoint_writes", "thread_id", str(parent)),
            ("business.p3_task_sources", "task_id", task),
        ]:
            schema, table = name.split(".")
            rows = db.execute(
                sql.SQL(
                    "SELECT to_jsonb(t)::text AS body FROM {}.{} t WHERE {}=%s ORDER BY body"
                ).format(sql.Identifier(schema), sql.Identifier(table), sql.Identifier(column)),
                (key,),
            ).fetchall()
            result[name] = hashlib.sha256("\n".join(r["body"] for r in rows).encode()).hexdigest()
        return result


@pytest.mark.parametrize(
    "control,case,quantity",
    [
        ("stock_change", "baseline", 90),
        ("demand_change", "baseline", 112),
        ("null_to_known", "unknown_inbound", 100),
    ],
)
def test_material_change_one_real_new_version_nonce_confirmation_and_p2_bytes_preserved(
    fixture: P3Fixture, control: str, case: str, quantity: int
) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle(case))["task_id"])
    child = P3Process(
        f, "worker", {"task_id": str(task), "revalidation_controlled": control}, "never"
    )
    try:
        child.until("after_ready")
        before = original_hashes(f, task)
        old = payload(
            f, task, "approve_with_assumptions" if case == "unknown_inbound" else "approve"
        )
        first = post(f, old)
        assert first.status_code == 200
        try:
            child.until("after_replacement_commit")
        except Exception:
            with connect(f.config.database) as db:
                safe = db.execute(
                    "SELECT state,failure_code FROM business.business_tasks WHERE id=%s", (task,)
                ).fetchone()
            raise AssertionError(
                f"safe replacement state {safe}; safe events "
                f"{[e for e in child.history if e['event'].startswith(('safe_', 'attention:'))]}"
            ) from None
        child.until("after_ready")
        wait_state(f, task, "needs_reapproval")
        current = payload(f, task)
        assert current["plan_version"] == 2 and current["plan_id"] != old["plan_id"]
        assert current["approval_id"] != old["approval_id"] and current["nonce"] != old["nonce"]
        assert current["plan_hash"] != old["plan_hash"]
        with connect(f.config.database) as db:
            count = db.execute(
                "SELECT count(*) AS n FROM business.executions WHERE task_id=%s", (task,)
            ).fetchone()
            olda = db.execute(
                "SELECT status,consumed_at FROM business.approvals WHERE id=%s",
                (UUID(old["approval_id"]),),
            ).fetchone()
            plans = db.execute(
                "SELECT version,status,evidence_kind FROM "
                "business.replenishment_plans WHERE task_id=%s ORDER BY version",
                (task,),
            ).fetchall()
            original_receipt = db.execute(
                "SELECT result FROM business.web_requests WHERE "
                "operation='decision' AND request_key=%s",
                (UUID(old["request_key"]),),
            ).fetchone()
        assert count and count["n"] == 0 and olda == {"status": "approved", "consumed_at": None}
        assert plans == [
            {"version": 1, "status": "superseded", "evidence_kind": "p2_original"},
            {"version": 2, "status": "current", "evidence_kind": "p3_observation"},
        ]
        assert original_receipt and original_receipt["result"] == first.json()
        assert post(f, old).status_code == 200  # 只回旧意见，不授权新版。
        forged = {**current, "nonce": old["nonce"]}
        assert post(f, forged).status_code == 422
        assert post(f, current).status_code == 200
        wait_state(f, task, "completed")
        execution = f.client.get(f"/api/v1/tasks/{task}/execution").json()
        assert (
            execution["plan_id"] == current["plan_id"]
            and execution["approval_id"] == current["approval_id"]
        )
        item = f.client.get(f"/api/v1/replenishment-items/{execution['item_ids'][0]}").json()
        assert item["item"]["quantity"] == quantity
        report = f.client.get(f"/api/v1/tasks/{task}/report")
        assert (
            report.status_code == 200
            and report.json()["facts"]["items"][0]["suggested_units"] == quantity
        )
        explanation = f.client.get(
            f"/api/v1/tasks/{task}/explanation?report_id={report.json()['source']['report_id']}"
        )
        assert explanation.status_code == 200
        assert explanation.json()["explanation"]["schema_version"] == "p4-p3-template-read-v1"
        with connect(f.config.database) as db:
            assert db.execute("SELECT count(*) AS n FROM business.model_calls").fetchone() == {
                "n": 0
            }
        assert original_hashes(f, task) == before
    finally:
        if child.process.poll() is None:
            child.stop_clean()


def test_only_capture_time_refresh_does_not_create_plan_nonce_or_second_confirmation(
    fixture: P3Fixture,
) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle())["task_id"])
    child = P3Process(
        f, "worker", {"task_id": str(task), "revalidation_controlled": "time_only"}, "never"
    )
    try:
        child.until("after_ready")
        request = payload(f, task)
        assert post(f, request).status_code == 200
        wait_state(f, task, "completed")
        with connect(f.config.database) as db:
            plans = db.execute(
                "SELECT count(*) AS n FROM business.replenishment_plans WHERE task_id=%s", (task,)
            ).fetchone()
            approval = db.execute(
                "SELECT id,nonce_hash,consumed_at FROM business.approvals WHERE task_id=%s", (task,)
            ).fetchone()
        assert (
            plans and plans["n"] == 1 and approval and str(approval["id"]) == request["approval_id"]
        )
        assert approval["consumed_at"] is not None
    finally:
        if child.process.poll() is None:
            child.stop_clean()


def test_fresh_hard_quality_is_not_waived_by_historical_approve(fixture: P3Fixture) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle())["task_id"])
    child = P3Process(
        f, "worker", {"task_id": str(task), "revalidation_controlled": "hard_quality"}, "never"
    )
    try:
        child.until("after_ready")
        assert post(f, payload(f, task)).status_code == 200
        wait_state(f, task, "needs_reapproval")
        with connect(f.config.database) as db:
            rows = db.execute(
                "SELECT count(*) AS n FROM business.replenishment_items WHERE task_id=%s", (task,)
            ).fetchone()
            approval = db.execute(
                "SELECT status,consumed_at FROM business.approvals WHERE task_id=%s", (task,)
            ).fetchone()
        assert rows and rows["n"] == 0 and approval == {"status": "approved", "consumed_at": None}
    finally:
        if child.process.poll() is None:
            child.stop_clean()
