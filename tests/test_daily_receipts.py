"""原键receipt wire与实际ASGI序列化；不冒充PG或身份授权测试。"""

import copy
import json
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from commerceops.application.daily.http_models import CreationReceiptRead
from commerceops.application.replenishment.contracts import WebActor
from commerceops.entrypoints.daily_http import (
    QUESTION_RECEIPT_PATH,
    REPORT_RECEIPT_PATH,
    daily_openapi,
    install_daily,
)
from commerceops.infrastructure.daily_operations import DailyOperations
from commerceops.infrastructure.daily_read import DailyReadStore
from commerceops.infrastructure.daily_sources import DailyDeployment
from commerceops.infrastructure.database import DatabaseSettings
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError

pytestmark = pytest.mark.offline


@pytest.mark.parametrize("operation", ["capability", "receipt"])
def test_daily_date_projection_reaches_actual_envelope_as_iso(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    from commerceops.infrastructure import daily_operations

    from tests.test_daily_source import metadata, request

    meta = metadata(tmp_path)
    value = request(meta)
    task = {
        "id": UUID(int=30),
        "conversation_id": value.conversation_id,
        "state": "queued",
        "failure_code": None,
        "normalized_request": value.model_dump(mode="json"),
    }
    queries: list[str] = []

    class DB:
        def execute(self, statement: str, params: Any = ()) -> Any:
            queries.append(statement)
            row: Any
            if "clock_timestamp()" in statement:
                row = {"time": datetime(2026, 11, 3, 5, tzinfo=UTC)}
            elif "FROM business.business_tasks" in statement:
                row = task
            else:
                row = None
            return SimpleNamespace(fetchone=lambda: row)

    monkeypatch.setattr(daily_operations, "connect", lambda settings: nullcontext(DB()))
    monkeypatch.setattr(daily_operations, "actor_guard", lambda *args: None)
    monkeypatch.setattr(daily_operations, "role_scope", lambda *args: True)
    monkeypatch.setattr(daily_operations, "bound_metadata", lambda *args: meta)
    files = SimpleNamespace(
        active=lambda *args: SimpleNamespace(binding_id=value.daily_source.source_binding_id)
    )
    settings = DatabaseSettings(
        host="127.0.0.1", name="unused", user="unused", password_file=tmp_path / "not-read"
    )
    operations = DailyOperations(
        settings,
        cast(DailyDeployment, files) if operation == "capability" else None,
        b"unused-cursor-material",
    )
    actor = WebActor(UUID(int=7), UUID(int=8), UUID(int=9), meta.organization_id, 1)
    if operation == "capability":
        result = operations.capabilities(actor, meta.shop_id)
        assert result.capabilities.earliest_business_day == meta.earliest_business_day
    else:
        receipt = operations.creation_receipt(actor, meta.shop_id, value.request_key)
        assert receipt.receipt.operation == "daily_report.create"
        assert receipt.receipt.business_day == value.business_day
    assert queries and all(statement.lstrip().startswith("SELECT ") for statement in queries)


def receipt_wire(question: bool = False) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema_version": "p6-m3-web-v1",
        "lookup_status": "accepted",
        "operation": "daily_question.create" if question else "daily_report.create",
        "request_key": str(UUID(int=1)),
        "shop_id": str(UUID(int=2)),
        "task_id": str(UUID(int=3)),
        "state": "queued",
        "failure_code": None,
        "request_hash": "a" * 64,
    }
    if question:
        receipt.update(
            parent_task_id=str(UUID(int=4)),
            report_id=str(UUID(int=5)),
            snapshot_id=str(UUID(int=6)),
            content_hash="b" * 64,
            facts_hash="c" * 64,
            question={"kind": "data_quality", "metric_key": None, "finding_id": None},
        )
    else:
        receipt.update(source_config_version="source-1", business_day="2026-11-02")
    return {
        "schema_version": "p3-web-v1",
        "identity_mode": "session",
        "server_time": "2026-11-03T05:00:00Z",
        "trace_id": str(UUID(int=7)),
        "receipt": receipt,
    }


@pytest.mark.parametrize("question", [False, True])
def test_receipt_wire_roundtrip_and_discriminator(question: bool) -> None:
    body = receipt_wire(question)
    value = CreationReceiptRead.model_validate_json(json.dumps(body))
    assert CreationReceiptRead.model_validate_json(value.model_dump_json()) == value
    changed = copy.deepcopy(body)
    changed["receipt"]["operation"] = "daily_report.create" if question else "daily_question.create"
    with pytest.raises(ValidationError):
        CreationReceiptRead.model_validate_json(json.dumps(changed))


@pytest.mark.parametrize(
    "field", ["report_id", "snapshot_id", "content_hash", "facts_hash", "parent_task_id"]
)
def test_question_receipt_requires_complete_parent_binding(field: str) -> None:
    body = receipt_wire(True)
    body["receipt"].pop(field)
    with pytest.raises(ValidationError):
        CreationReceiptRead.model_validate_json(json.dumps(body))


def test_receipt_paths_are_get_only_authenticated_and_use_actual_response_model() -> None:
    document = daily_openapi()
    for path in (REPORT_RECEIPT_PATH, QUESTION_RECEIPT_PATH):
        assert set(document["paths"][path]) == {"get"}
        operation = document["paths"][path]["get"]
        assert operation["security"] == [{"SessionCookie": []}]
        assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/CreationReceiptRead"
        }
        assert "404" in operation["responses"]


def test_receipt_asgi_parses_explicit_scopes_and_serializes_strict_response() -> None:
    calls: list[tuple[UUID, ...]] = []

    class Operations:
        def creation_receipt(self, actor: WebActor, shop: UUID, key: UUID) -> CreationReceiptRead:
            calls.append((shop, key))
            return CreationReceiptRead.model_validate_json(json.dumps(receipt_wire()))

        def question_receipt(
            self, actor: WebActor, shop: UUID, parent: UUID, report: UUID, key: UUID
        ) -> CreationReceiptRead:
            calls.append((shop, parent, report, key))
            return CreationReceiptRead.model_validate_json(json.dumps(receipt_wire(True)))

    app = FastAPI()

    @app.middleware("http")
    async def identity(request: Request, call_next: Any) -> Any:
        request.state.web_actor = None
        return await call_next(request)

    install_daily(app, cast(DailyReadStore, None), cast(DailyOperations, Operations()))
    with TestClient(app) as client:
        first = client.get(
            REPORT_RECEIPT_PATH.format(request_key=UUID(int=1)),
            params={"shop_id": str(UUID(int=2))},
        )
        second = client.get(
            QUESTION_RECEIPT_PATH.format(task_id=UUID(int=4), request_key=UUID(int=1)),
            params={"shop_id": str(UUID(int=2)), "report_id": str(UUID(int=5))},
        )
    assert first.status_code == second.status_code == 200
    assert (
        CreationReceiptRead.model_validate_json(first.content).receipt.operation
        == "daily_report.create"
    )
    assert (
        CreationReceiptRead.model_validate_json(second.content).receipt.operation
        == "daily_question.create"
    )
    assert calls == [
        (UUID(int=2), UUID(int=1)),
        (UUID(int=2), UUID(int=4), UUID(int=5), UUID(int=1)),
    ]
