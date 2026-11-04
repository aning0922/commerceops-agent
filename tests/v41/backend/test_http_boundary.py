"""In-process HTTP boundary only: stubbed authority, no network listener or database."""

import secrets
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from commerceops.application.replenishment.contracts import WebFailure
from commerceops.entrypoints.v41_http import business_openapi, install_business
from commerceops.infrastructure.database import DatabaseSettings
from commerceops.infrastructure.v4_demo_sessions import DemoConfig
from commerceops.infrastructure.v41_store import BusinessStore
from commerceops.infrastructure.web_config import WebConfig
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scripts.v41_schema import contract

pytestmark = pytest.mark.offline
ORIGIN = "http://127.0.0.1:3100"
API = "http://127.0.0.1:8000"


class BoundaryStore(BusinessStore):
    calls: list[tuple[Any, ...]]

    def __init__(self, config: DemoConfig):
        super().__init__(config)
        self.calls = []

    def read(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(args)
        raise WebFailure("SESSION_INVALID", 401)

    def action(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(args)
        raise WebFailure("CSRF_INVALID", 403)

    def preview(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(args)
        raise ValueError("private parser source must never be public")


@pytest.fixture
def boundary() -> tuple[TestClient, BoundaryStore]:
    database = DatabaseSettings(
        host="127.0.0.1",
        name="v4_demo_offline",
        user="commerceops_app",
        password_file=Path("/never-read/v41-boundary"),
    )
    web = WebConfig(
        database,
        secrets.token_bytes(32),
        secrets.token_bytes(32),
        (ORIGIN,),
        transport_mode="local_http",
    )
    config = DemoConfig(web, API, True)
    store = BoundaryStore(config)
    app = FastAPI()
    install_business(app, config, store)
    return TestClient(app, base_url=API), store


def headers() -> dict[str, str]:
    return {"Origin": ORIGIN, "X-Demo-Epoch": "0", "X-Demo-Generation": "0"}


def test_runtime_paths_match_frozen_contract_and_static_export_precedes_uuid(
    boundary: tuple[TestClient, BoundaryStore],
) -> None:
    schema = business_openapi()
    expected = {(r["path"], r["method"].lower()) for r in contract()["routes"]}
    actual = {(path, method) for path, methods in schema["paths"].items() for method in methods}
    assert actual == expected and len(actual) == 16
    browser, store = boundary
    response = browser.get(
        "/api/v4/products/export", params=dict(shop_id=str(uuid4())), headers=headers()
    )
    assert response.status_code == 401 and store.calls[0][-1] == "product_export"


@pytest.mark.parametrize("origin", [None, "http://untrusted.invalid", "null"])
def test_origin_rejection_precedes_store_even_with_valid_query(
    boundary: tuple[TestClient, BoundaryStore], origin: str | None
) -> None:
    browser, store = boundary
    h = headers()
    if origin is None:
        del h["Origin"]
    else:
        h["Origin"] = origin
    response = browser.get("/api/v4/products", params=dict(shop_id=str(uuid4())), headers=h)
    assert response.status_code == 403 and not store.calls
    assert response.json()["error"]["code"] == "ORIGIN_DENIED"
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("value", ["true", "-1", "01", " 1", "1.0"])
def test_context_headers_are_canonical_integer_not_boolean_or_float(
    boundary: tuple[TestClient, BoundaryStore], value: str
) -> None:
    browser, store = boundary
    h = headers() | {"X-Demo-Epoch": value}
    response = browser.get("/api/v4/products", params=dict(shop_id=str(uuid4())), headers=h)
    assert response.status_code == 422 and not store.calls


@pytest.mark.parametrize(
    "suffix", ["&limit=1&limit=2", "&role=operator", "&limit=true", "&limit=1.0"]
)
def test_duplicate_extra_or_coerced_query_fields_rejected(
    boundary: tuple[TestClient, BoundaryStore], suffix: str
) -> None:
    browser, store = boundary
    response = browser.get("/api/v4/products?shop_id=" + str(uuid4()) + suffix, headers=headers())
    assert response.status_code == 422 and not store.calls


def test_duplicate_json_unknown_fields_and_oversized_stream_rejected(
    boundary: tuple[TestClient, BoundaryStore],
) -> None:
    browser, store = boundary
    for data in (
        '{"shop_id":"x","shop_id":"y"}',
        '{"role":"operator"}',
        " " * (3 * 1024 * 1024 + 1),
    ):
        response = browser.post(
            "/api/v4/imports/previews",
            content=data,
            headers=headers() | {"Content-Type": "application/json"},
        )
        assert response.status_code == 422 and not store.calls


def test_valid_preview_schema_never_echoes_internal_exception(
    boundary: tuple[TestClient, BoundaryStore],
) -> None:
    browser, store = boundary
    response = browser.post(
        "/api/v4/imports/previews",
        json=dict(
            shop_id=str(uuid4()),
            request_key=str(uuid4()),
            expected_epoch=0,
            expected_generation=0,
            expected_data_revision="a" * 64,
            format="csv",
            filename="input.csv",
            file_base64="YQ==",
        ),
        headers=headers(),
    )
    assert response.status_code == 503 and len(store.calls) == 1
    assert response.json()["status"] == "UNKNOWN" and "private parser" not in response.text
    assert response.json()["error"]["retryable"] is False


def test_business_preflight_cors_and_safe_missing_route(
    boundary: tuple[TestClient, BoundaryStore],
) -> None:
    browser, _ = boundary
    response = browser.options("/api/v4/products", headers={"Origin": ORIGIN})
    assert (
        response.status_code == 204
        and response.headers["Access-Control-Allow-Credentials"] == "true"
    )
    assert response.headers["Access-Control-Allow-Origin"] == ORIGIN
    response = browser.get("/api/v4/imports/extra/unknown", headers=headers())
    assert response.status_code == 404 and response.json()["schema_version"] == "v4-business-v1"
