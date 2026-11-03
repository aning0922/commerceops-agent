"""新owned receipt PG候选：原键隔离、当前权限、无来源文件和GET零业务增量。"""

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from commerceops.application.daily.http_models import CreationReceiptRead
from commerceops.application.daily.source import DailyTaskRequest
from commerceops.entrypoints.api import create_app
from commerceops.entrypoints.daily_http import QUESTION_RECEIPT_PATH, REPORT_RECEIPT_PATH
from commerceops.infrastructure.daily_questions import create_question
from commerceops.infrastructure.database import connect
from fastapi.testclient import TestClient

from tests.p3_support import ORIGIN, P3Fixture
from tests.test_daily_operations_pg import completed
from tests.test_p3_pg import fixture as fixture

pytestmark = pytest.mark.integration


def counts(f: P3Fixture) -> dict[str, int]:
    with connect(f.config.database) as db:
        row = db.execute("""SELECT (SELECT count(*) FROM business.business_tasks) AS tasks,
        (SELECT count(*) FROM business.jobs) AS jobs,
        (SELECT count(*) FROM business.p6_daily_snapshots) AS snapshots,
        (SELECT count(*) FROM business.p6_daily_reports) AS reports,
        (SELECT count(*) FROM business.p6_daily_questions) AS answers,
        (SELECT count(*) FROM business.audit_events) AS audit""").fetchone()
        assert row is not None
        return row


def test_receipts_same_key_isolated_and_get_without_source_files_is_read_only(
    fixture: P3Fixture, tmp_path: Path
) -> None:
    f = fixture
    files, _, parent, body, _ = completed(f, tmp_path / "daily")
    with connect(f.config.database) as db:
        row = db.execute(
            "SELECT normalized_request FROM business.business_tasks WHERE id=%s", (parent,)
        ).fetchone()
        assert row is not None
        request = DailyTaskRequest.model_validate_json(json.dumps(row["normalized_request"]))
    body = body.model_copy(update={"request_key": request.request_key})
    question = create_question(f.config.database, f.actor, parent, body)
    # 当前源不可读也只查原持久task；GET不fallback、不重采。
    filename = files.directory / f"{files.bindings[0].binding_id}.json"
    filename.rename(filename.with_suffix(".held"))
    app = create_app(
        web_config=f.config, replenishment_store=f.store, daily_enabled=True, daily_files=files
    )
    original = counts(f)
    with TestClient(app, base_url=ORIGIN) as client:
        client.cookies.update(f.client.cookies)
        report_path = REPORT_RECEIPT_PATH.format(request_key=request.request_key)
        question_path = QUESTION_RECEIPT_PATH.format(
            task_id=parent, request_key=request.request_key
        )
        params = {"shop_id": str(f.inventory.data.shop)}
        first = client.get(report_path, params=params)
        second = client.get(question_path, params={**params, "report_id": str(body.report_id)})
        assert first.status_code == second.status_code == 200
        report_receipt = CreationReceiptRead.model_validate_json(first.content).receipt
        question_receipt = CreationReceiptRead.model_validate_json(second.content).receipt
        assert (
            report_receipt.operation == "daily_report.create" and report_receipt.task_id == parent
        )
        assert (
            question_receipt.operation == "daily_question.create"
            and question_receipt.task_id == question
        )
        assert {report_receipt.request_key, question_receipt.request_key} == {request.request_key}
        assert (
            question_receipt.parent_task_id == parent
            and question_receipt.report_id == body.report_id
        )
        assert first.headers["cache-control"] == "no-store"
        for path, query in [
            (REPORT_RECEIPT_PATH.format(request_key=uuid4()), params),
            (report_path, {"shop_id": str(uuid4())}),
            (
                QUESTION_RECEIPT_PATH.format(task_id=uuid4(), request_key=request.request_key),
                {**params, "report_id": str(body.report_id)},
            ),
            (question_path, {**params, "report_id": str(uuid4())}),
        ]:
            missing = client.get(path, params=query)
            assert (
                missing.status_code == 404
                and missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
            )
    assert counts(f) == original


def test_receipt_current_identity_and_scope_rechecked_after_revocation(
    fixture: P3Fixture, tmp_path: Path
) -> None:
    f = fixture
    files, _, parent, body, _ = completed(f, tmp_path / "daily")
    question = create_question(f.config.database, f.actor, parent, body)
    with connect(f.config.database) as db:
        row = db.execute(
            "SELECT normalized_request FROM business.business_tasks WHERE id=%s", (parent,)
        ).fetchone()
        assert row is not None
        key = UUID(row["normalized_request"]["request_key"])
    app = create_app(
        web_config=f.config, replenishment_store=f.store, daily_enabled=True, daily_files=files
    )
    with TestClient(app, base_url=ORIGIN) as client:
        client.cookies.update(f.client.cookies)
        path = REPORT_RECEIPT_PATH.format(request_key=key)
        params = {"shop_id": str(f.inventory.data.shop)}
        assert client.get(path, params=params).status_code == 200
        with connect(f.inventory.owner) as db:
            db.execute(
                """UPDATE business.principal_role_shop_grants SET enabled=false
            WHERE principal_id=%s AND role='operator'""",
                (f.actor.principal_id,),
            )
        assert client.get(path, params=params).status_code == 401
        f.relogin()
        client.cookies.update(f.client.cookies)
        assert client.get(path, params=params).status_code == 404
        qpath = QUESTION_RECEIPT_PATH.format(task_id=parent, request_key=body.request_key)
        denied = client.get(qpath, params={**params, "report_id": str(body.report_id)})
        assert denied.status_code == 404 and question != parent
