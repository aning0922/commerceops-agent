"""In-process ASGI boundary tests with explicit doubles; no API service or PG."""

import json
import secrets
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from commerceops.application.commerce.readonly_inquiry_contracts import Window
from commerceops.application.commerce.readonly_inquiry_service_contracts import (
    CreateInquiry,
    InquiryRead,
    InquiryReceipt,
)
from commerceops.application.replenishment.contracts import WebActor, WebFailure
from commerceops.entrypoints.inquiry_http import inquiry_openapi, inquiry_router
from commerceops.infrastructure.database import DatabaseSettings
from commerceops.infrastructure.web_config import WebConfig
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.offline
SESSION_VALUE = secrets.token_urlsafe(18)
CSRF_VALUE = secrets.token_urlsafe(18)


class Sessions:
    revoked = False
    actor = WebActor(uuid4(), uuid4(), uuid4(), uuid4(), 1)

    def authenticate(self, token: str | None) -> WebActor:
        if self.revoked or token != SESSION_VALUE:
            raise WebFailure("SESSION_INVALID", 401)
        return self.actor

    def check_csrf(self, token: str | None, supplied: str | None) -> None:
        if supplied != CSRF_VALUE:
            raise WebFailure("CSRF_INVALID", 403)


class Store:
    def __init__(self) -> None:
        self.created = 0
        self.reads = 0
        self.receipt: InquiryReceipt | None = None

    def authorize_entry(self, actor: WebActor) -> None:
        pass

    def create(self, actor: WebActor, request: CreateInquiry) -> InquiryReceipt:
        self.created += 1
        self.receipt = InquiryReceipt(
            task_id=uuid4(),
            shop_id=request.shop_id,
            request_key=request.request_key,
            source_binding="0" * 64,
            source_domain=Window(
                start=datetime(2026, 10, 1, tzinfo=UTC), end=datetime(2026, 10, 8, tzinfo=UTC)
            ),
            state="queued",
            duplicate=False,
            server_time=datetime.now(UTC),
            trace_id=uuid4(),
        )
        return self.receipt

    def read(
        self, actor: WebActor, task_id: UUID | None = None, request_key: UUID | None = None
    ) -> InquiryRead:
        self.reads += 1
        if self.receipt is None:
            raise WebFailure("RESOURCE_NOT_FOUND", 404)
        return InquiryRead.model_validate(
            {**self.receipt.model_dump(), "result": None, "answer": None}
        )


def client() -> tuple[TestClient, Store, Sessions]:
    config = WebConfig(
        DatabaseSettings(
            host="localhost", name="unused", user="unused", password_file=Path("/unused")
        ),
        secrets.token_bytes(32),
        secrets.token_bytes(32),
        ("http://localhost",),
        transport_mode="local_http",
    )
    store, sessions = Store(), Sessions()
    app = FastAPI()
    app.include_router(inquiry_router(store, sessions, config))
    value = TestClient(app, base_url="http://localhost")
    value.cookies.set("commerceops_session", SESSION_VALUE)
    return value, store, sessions


def body() -> dict[str, object]:
    return {
        "schema_version": "p6-inquiry-web-v1",
        "shop_id": str(uuid4()),
        "question": "库存 DEMO",
        "request_key": str(uuid4()),
    }


HEADERS = {"Origin": "http://localhost", "X-CSRF-Token": CSRF_VALUE}


def test_post_returns_202_and_get_only_reads_persisted_receipt() -> None:
    http, store, _ = client()
    result = http.post("/api/v1/readonly-inquiries", json=body(), headers=HEADERS)
    assert result.status_code == 202 and result.json()["evidence_mode"] == "offline_stub"
    key = result.json()["request_key"]
    read = http.get(f"/api/v1/readonly-inquiries/requests/{key}")
    assert read.status_code == 200 and read.json()["result"] is None
    assert read.json()["data_label"] == "本地演示数据 / 离线模型替身"
    assert store.created == store.reads == 1 and read.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("field", ["role", "source_url", "model_key", "budget", "identity_id"])
def test_extra_authority_fields_never_reach_store(field: str) -> None:
    http, store, _ = client()
    payload = body()
    payload[field] = "untrusted"
    result = http.post("/api/v1/readonly-inquiries", json=payload, headers=HEADERS)
    assert result.status_code == 422 and store.created == 0
    assert "untrusted" not in result.text


def test_csrf_origin_revocation_and_duplicate_json_keys_fail_closed() -> None:
    http, store, sessions = client()
    assert http.post("/api/v1/readonly-inquiries", json=body()).status_code == 403
    assert (
        http.post(
            "/api/v1/readonly-inquiries",
            json=body(),
            headers={**HEADERS, "Origin": "https://untrusted.invalid"},
        ).status_code
        == 403
    )
    raw = json.dumps(body())[:-1] + ',"question":"duplicate"}'
    assert (
        http.post(
            "/api/v1/readonly-inquiries",
            content=raw,
            headers={**HEADERS, "Content-Type": "application/json"},
        ).status_code
        == 400
    )
    sessions.revoked = True
    assert http.get(f"/api/v1/readonly-inquiries/{uuid4()}").status_code == 401
    assert store.created == store.reads == 0


def test_openapi_asset_is_generated_from_current_dtos() -> None:
    path = (
        Path(__file__).parents[1] / "backend/src/commerceops/assets/p6-inquiry-web-v1.openapi.json"
    )
    document = inquiry_openapi()
    assert json.loads(path.read_text()) == document
    assert document["components"]["schemas"]["CreateInquiry"]["additionalProperties"] is False
    assert set(document["paths"]) == {
        "/api/v1/readonly-inquiries",
        "/api/v1/readonly-inquiries/{task_id}",
        "/api/v1/readonly-inquiries/requests/{request_key}",
    }
