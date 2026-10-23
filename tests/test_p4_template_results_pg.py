"""全新自有 PG 的模板原事务/当前读取权限；无 SDK/provider/IM 外发。"""

import asyncio
import copy
from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

import pytest
from commerceops.application.replenishment.template_result import TemplateRenderError
from commerceops.domain.commerce_values import canonical_bytes, facts_hash
from commerceops.infrastructure import p3_template_results as templates
from commerceops.infrastructure.database import connect
from psycopg import sql
from psycopg.errors import CheckViolation, InsufficientPrivilege
from psycopg.types.json import Jsonb

from tests.p3_support import P3Fixture, P3Process, run_graphs
from tests.test_p3_approval_pg import payload, post, wait_state
from tests.test_p3_pg import fixture as fixture
from tests.test_p4_gateway_pg import message, service

pytestmark = pytest.mark.integration


def counts(f: P3Fixture) -> dict[str, int]:
    names = (
        "business_tasks",
        "jobs",
        "replenishment_plans",
        "approvals",
        "executions",
        "replenishment_items",
        "outbox",
        "model_calls",
        "explanation_links",
        "model_explanations",
        "p3_template_results",
        "p3_observations",
    )
    with connect(f.config.database) as db:
        result = {}
        for name in names:
            row = db.execute(
                sql.SQL("SELECT count(*) AS n FROM business.{}").format(sql.Identifier(name))
            ).fetchone()
            assert row
            result[name] = row["n"]
        return result


def cached(f: P3Fixture, task: UUID, kind: str = "p2_original") -> dict[str, Any]:
    with connect(f.config.database) as db:
        row = db.execute(
            "SELECT * FROM business.p3_template_results WHERE p3_task_id=%s AND source_kind=%s",
            (task, kind),
        ).fetchone()
    assert row
    return row


def read(f: P3Fixture, task: UUID, report: UUID) -> Any:
    return f.client.get(f"/api/v1/tasks/{task}/explanation?report_id={report}")


@pytest.mark.parametrize("case", ["baseline", "normal", "unknown_inbound"])
def test_original_freeze_no_child_ten_read_replays_and_no_action(
    fixture: P3Fixture,
    case: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle(case))["task_id"])
    asyncio.run(run_graphs(f, task, repeat_prepare=10))
    row = cached(f, task)
    before = counts(f)
    assert before["p3_template_results"] == 1
    assert before["model_calls"] == before["explanation_links"] == before["model_explanations"] == 0
    if case == "normal":
        assert f.client.get(f"/api/v1/tasks/{task}").json()["task"]["outcome"] == "no_action"
        assert before["replenishment_plans"] == before["approvals"] == 0

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("GET attempted template generation")

    monkeypatch.setattr(templates, "render", forbidden)
    values = []
    for _ in range(10):
        response = read(f, task, row["report_id"])
        assert response.status_code == 200
        value = response.json()["explanation"]
        assert value["schema_version"] == "p4-p3-template-read-v1"
        assert "child_task_id" not in value and value["task_id"] == str(task)
        assert value["source_task_id"] == str(row["source_task_id"])
        assert value["result"]["reference_ids"] == {
            "snapshot_id": str(row["snapshot_id"]),
            "report_id": str(row["report_id"]),
        }
        assert value["result"]["metadata"]["evidence_mode"] == "not_used"
        values.append(value)
    assert all(value == values[0] for value in values)
    assert counts(f) == before
    assert read(f, task, uuid4()).status_code == 404
    assert read(f, row["source_task_id"], row["report_id"]).status_code == 409
    assert counts(f) == before


def test_original_precommit_rolls_back_cache_and_retry_same_key(
    fixture: P3Fixture,
) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle())["task_id"])
    visits = 0

    async def fault(point: str) -> None:
        nonlocal visits
        if point == "before_t2_commit":
            visits += 1
            current = counts(f)
            assert current["p3_template_results"] == current["replenishment_plans"] == 0
            if visits == 1:
                raise RuntimeError("controlled_bc02_precommit")

    asyncio.run(run_graphs(f, task, store_hook=fault, repeat_prepare=10))
    assert visits == 2 and counts(f)["p3_template_results"] == 1
    row = cached(f, task)
    assert (
        row["id"]
        == templates.TemplateBinding(
            **{key: row[key] for key in templates.TemplateBinding.__dataclass_fields__}
        ).identity()["id"]
    )


def test_named_render_failure_unavailable_is_read_only_not_ready(
    fixture: P3Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    f = fixture

    async def fail(*args: Any, **kwargs: Any) -> Any:
        raise TemplateRenderError("controlled_formatter")

    monkeypatch.setattr(templates, "render", fail)
    task = UUID(f.create(f.new_cycle())["task_id"])
    asyncio.run(run_graphs(f, task, repeat_prepare=10))
    row = cached(f, task)
    assert row["status"] == "unavailable" and row["safe_error_code"] == "TEMPLATE_RENDER_FAILED"
    assert all(row[key] is None for key in ("result", "canonical_result", "result_hash"))
    before = counts(f)
    for _ in range(10):
        response = read(f, task, row["report_id"])
        assert response.status_code == 409 and response.json()["error"]["code"] == "NOT_READY"
    assert counts(f) == before


def test_database_exact_binding_nonprovider_and_immutable_constraints(fixture: P3Fixture) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle())["task_id"])
    asyncio.run(run_graphs(f, task))
    original = cached(f, task)
    with connect(f.inventory.owner) as db:
        for changes in (
            {"logical_key": "p3-template-v1:" + "0" * 64},
            {"requester_id": uuid4()},
            {"report_id": uuid4()},
            {"snapshot_id": uuid4()},
            {"facts_hash": "0" * 64},
            {"source_kind": "p3_observation"},
        ):
            clone = {**original, "id": uuid4(), **changes}
            query = sql.SQL("INSERT INTO business.p3_template_results({}) VALUES({})").format(
                sql.SQL(",").join(map(sql.Identifier, clone)),
                sql.SQL(",").join(sql.Placeholder() for _ in clone),
            )
            with pytest.raises(CheckViolation), db.transaction():
                db.execute(
                    query, tuple(Jsonb(v) if isinstance(v, dict) else v for v in clone.values())
                )
        bad = copy.deepcopy(original["result"])
        bad["metadata"]["provider"] = "deepseek"
        clone = {
            **original,
            "id": uuid4(),
            "result": bad,
            "canonical_result": canonical_bytes(bad).decode(),
            "result_hash": facts_hash(bad),
        }
        query = sql.SQL("INSERT INTO business.p3_template_results({}) VALUES({})").format(
            sql.SQL(",").join(map(sql.Identifier, clone)),
            sql.SQL(",").join(sql.Placeholder() for _ in clone),
        )
        with pytest.raises(CheckViolation), db.transaction():
            db.execute(query, tuple(Jsonb(v) if isinstance(v, dict) else v for v in clone.values()))
        for statement in (
            "UPDATE business.p3_template_results SET result=result",
            "DELETE FROM business.p3_template_results",
            "TRUNCATE business.p3_template_results",
        ):
            with pytest.raises(CheckViolation), db.transaction():
                db.execute(statement)
    with connect(f.config.database) as db:
        for statement in (
            "UPDATE business.p3_template_results SET result=result",
            "DELETE FROM business.p3_template_results",
            "TRUNCATE business.p3_template_results",
        ):
            with pytest.raises(InsufficientPrivilege), db.transaction():
                db.execute(statement)


@pytest.mark.parametrize("control", ["time_only", "stock_change"])
def test_observation_real_report_ids_same_facts_are_separate_read_results(
    fixture: P3Fixture,
    control: str,
) -> None:
    f = fixture
    task = UUID(f.create(f.new_cycle())["task_id"])
    child = P3Process(
        f, "worker", {"task_id": str(task), "revalidation_controlled": control}, "never"
    )
    try:
        child.until("after_ready")
        first = cached(f, task)
        assert post(f, payload(f, task)).status_code == 200
        if control == "stock_change":
            child.until("after_replacement_commit")
            child.until("after_ready")
            wait_state(f, task, "needs_reapproval")
        else:
            wait_state(f, task, "completed")
        second = cached(f, task, "p3_observation")
        assert second["id"] != first["id"] and second["report_id"] != first["report_id"]
        assert second["snapshot_id"] == second["observation_id"]
        if control == "time_only":
            # canonical facts 含 captured provenance；time_only 是 material 相同，非 bytes 相同。
            assert counts(f)["replenishment_plans"] == 1
        before = counts(f)
        for row in (first, second):
            response = read(f, task, row["report_id"])
            assert response.status_code == 200
            assert response.json()["explanation"]["explanation_id"] == str(row["id"])
        assert counts(f) == before
    finally:
        if child.process.poll() is None:
            child.stop_clean()


def test_feishu_explicit_reads_trusted_chat_current_role_and_incoming_only(
    fixture: P3Fixture,
) -> None:
    f = fixture
    s = service(f)
    incoming = message(f)
    task = UUID(s.message(incoming)["task_id"])
    asyncio.run(run_graphs(f, task))
    row = cached(f, task)
    before = counts(f)
    for text in (f"查询任务{task}进度", f"解释任务{task}的报告{row['report_id']}"):
        request = replace(
            incoming, event_id="read-" + uuid4().hex, message_id="read-" + uuid4().hex, text=text
        )
        receipt = s.message(request)
        assert receipt["state"] == "read_completed" and receipt["reply_delivery"] == "pending"
        assert receipt["facts"]["identity_mode"] == "feishu"
        for _ in range(10):
            assert s.message(request) == {**receipt, "duplicate": True}
        assert counts(f) == before
        with pytest.raises(Exception) as denial:
            s.message(
                replace(
                    request,
                    event_id="read-" + uuid4().hex,
                    message_id="read-" + uuid4().hex,
                    chat_id="untrusted-chat",
                )
            )
        assert getattr(denial.value, "code", None) == "RESOURCE_NOT_FOUND"
    with connect(f.inventory.owner) as db:
        db.execute(
            "UPDATE business.principals SET roles=ARRAY['approver'],"
            "auth_version=auth_version+1 WHERE id=%s",
            (f.inventory.data.principal,),
        )
    # 原 requester 仅保留原 eligible approver，读取没有全局 operator 前置门禁。
    request = replace(
        incoming,
        event_id="read-" + uuid4().hex,
        message_id="read-" + uuid4().hex,
        text=f"解释任务{task}的报告{row['report_id']}",
    )
    assert s.message(request)["state"] == "read_completed"
    with connect(f.inventory.owner) as db:
        db.execute(
            "UPDATE business.principal_role_shop_grants SET enabled=false WHERE principal_id=%s",
            (f.inventory.data.principal,),
        )
    with pytest.raises(Exception) as denial:
        s.message(request)
    assert getattr(denial.value, "code", None) in ("ACCESS_DENIED", "RESOURCE_NOT_FOUND")
    assert counts(f) == before
