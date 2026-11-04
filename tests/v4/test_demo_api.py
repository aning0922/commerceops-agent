"""ASGI contract/boundary checks with explicit stubs; never a PG authentication claim."""

import secrets
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from commerceops.application.replenishment.contracts import WebFailure
from commerceops.application.v4_demo import contracts as dto
from commerceops.entrypoints.api import create_app
from commerceops.entrypoints.v4_demo_http import demo_openapi, install_demo
from commerceops.infrastructure.database import DatabaseSettings
from commerceops.infrastructure.v4_demo_sessions import DemoConfig
from commerceops.infrastructure.v4_demo_store import DemoStore
from commerceops.infrastructure.web_config import WebConfig
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.offline
ORIGIN = "http://127.0.0.1:3100"
API = "http://127.0.0.1:8000"


def config(*, enabled: bool = True) -> DemoConfig:
    database = DatabaseSettings(
        host="127.0.0.1",
        name="v4_demo_offline",
        user="commerceops_app",
        password_file=Path("/never-read/v4-offline-credential"),
    )
    web = WebConfig(database, b"c" * 32, b"n" * 32, (ORIGIN,), transport_mode="local_http")
    return DemoConfig(web, API, enabled)


class StubStore(DemoStore):
    def __init__(self, settings: DemoConfig):
        super().__init__(settings)
        self.calls: list[str] = []

    def bootstrap(self, token: str | None, peer: str) -> tuple[dict[str, Any], str | None]:
        self.calls.append("bootstrap")
        return dict(
            server_time="2026-11-03T00:00:00Z",
            data=dict(
                csrf_token=secrets.token_urlsafe(32),
                expires_at="2026-11-03T00:05:00Z",
                state="anonymous_bootstrap",
            ),
        ), "v4b_" + "a" * 43

    def create(
        self,
        token: str | None,
        supplied_csrf: str | None,
        command: dto.CreateSessionInput,
        peer: str,
    ) -> tuple[dict[str, Any], str]:
        self.calls.append("create")
        raise WebFailure(
            "CSRF_INVALID" if not supplied_csrf else "SESSION_INVALID",
            403 if not supplied_csrf else 401,
        )

    def control(
        self,
        token: str | None,
        supplied_csrf: str | None,
        operation: dto.Operation,
        command: dto.PersonaInput | dto.ResetInput | dto.LogoutInput,
    ) -> dict[str, Any]:
        self.calls.append(operation)
        raise WebFailure("SESSION_INVALID", 401)

    def summary(self, token: str | None, shop: UUID, epoch: int, generation: int) -> dict[str, Any]:
        self.calls.append("summary")
        raise WebFailure("EPOCH_CHANGED", 409)

    def operation(self, token: str | None, operation: dto.Operation, key: UUID) -> dict[str, Any]:
        self.calls.append("operation")
        return dict(
            server_time="2026-11-03T00:00:00Z",
            data=dict(
                operation="session_create",
                request_key=str(key),
                status="UNKNOWN",
                recovery="WAIT_READ_ONLY",
            ),
        )


@pytest.fixture
def client() -> tuple[TestClient, StubStore]:
    settings = config()
    store = StubStore(settings)
    app = FastAPI()
    install_demo(app, settings, store)
    return TestClient(app, base_url=API), store


def test_default_application_and_explicit_disabled_config_do_not_register_v4() -> None:
    app = create_app()
    assert not any(path.startswith("/api/v4/") for path in app.openapi()["paths"])
    app = create_app(v4_demo_config=config(enabled=False))
    assert not any(path.startswith("/api/v4/") for path in app.openapi()["paths"])
    assert not hasattr(app.state, "v4_demo_openapi")


def test_bootstrap_cookie_and_dedicated_response(client: tuple[TestClient, StubStore]) -> None:
    browser, stub = client
    response = browser.get("/api/v4/demo/bootstrap", headers={"Origin": ORIGIN})
    assert response.status_code == 200
    dto.BootstrapEnvelope.model_validate_json(response.content)
    cookie = response.headers["set-cookie"]
    assert "commerceops_v4_demo=" in cookie and "HttpOnly" in cookie
    assert "Path=/api/v4" in cookie and "SameSite=lax" in cookie
    assert "commerceops_session=" not in cookie
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"
    assert stub.calls == ["bootstrap"]


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "https://untrusted.invalid"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
        {"Sec-Fetch-Site": "same-origin", "Host": "untrusted.invalid"},
    ],
)
def test_untrusted_get_is_rejected_before_store(
    client: tuple[TestClient, StubStore], headers: dict[str, str]
) -> None:
    browser, stub = client
    response = browser.get("/api/v4/demo/bootstrap", headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ORIGIN_DENIED"
    assert stub.calls == []


def test_same_origin_get_exception_does_not_apply_to_post(
    client: tuple[TestClient, StubStore],
) -> None:
    browser, stub = client
    assert (
        browser.get("/api/v4/demo/bootstrap", headers={"Sec-Fetch-Site": "same-origin"}).status_code
        == 200
    )
    result = browser.post(
        "/api/v4/demo/sessions",
        headers={"Sec-Fetch-Site": "same-origin"},
        json=dict(request_key=str(uuid4()), fixture_version="v4-demo-seed-1"),
    )
    assert result.status_code == 403
    assert stub.calls == ["bootstrap"]


@pytest.mark.parametrize(
    "body",
    [
        dict(request_key="invalid", fixture_version="v4-demo-seed-1"),
        dict(request_key=str(UUID(int=4)), fixture_version="v4-demo-seed-1", role="admin"),
    ],
)
def test_invalid_authority_body_rejected_before_store(
    client: tuple[TestClient, StubStore], body: dict[str, Any]
) -> None:
    browser, stub = client
    response = browser.post(
        "/api/v4/demo/sessions", headers={"Origin": ORIGIN, "X-CSRF-Token": "offline"}, json=body
    )
    assert response.status_code == 422
    dto.FailureEnvelope.model_validate_json(response.content)
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert stub.calls == []


def test_duplicate_json_and_unsupported_content_type_have_fixed_v4_errors(
    client: tuple[TestClient, StubStore],
) -> None:
    browser, stub = client
    headers = {"Origin": ORIGIN, "Content-Type": "application/json"}
    response = browser.post(
        "/api/v4/demo/sessions", headers=headers, content='{"request_key":"a","request_key":"b"}'
    )
    assert response.status_code == 422 and response.json()["schema_version"] == "v4-demo-v1"
    response = browser.post(
        "/api/v4/demo/sessions",
        headers={"Origin": ORIGIN, "Content-Type": "text/plain"},
        content="invalid",
    )
    assert response.status_code == 422
    assert stub.calls == []


def test_operation_minimal_unknown_has_no_context_or_identity(
    client: tuple[TestClient, StubStore],
) -> None:
    browser, _ = client
    response = browser.get(
        f"/api/v4/demo/operations/session_create/{uuid4()}", headers={"Origin": ORIGIN}
    )
    assert response.status_code == 200
    value = dto.OperationEnvelope.model_validate_json(response.content)
    assert set(value.data.model_dump()) == {"operation", "request_key", "status", "recovery"}
    assert "context" not in response.json()


@pytest.mark.parametrize(
    "epoch,generation",
    [(None, "0"), ("0", None), ("true", "0"), ("1.0", "0"), ("-1", "0"), ("１２", "0")],
)
def test_summary_requires_strict_epoch_headers(
    client: tuple[TestClient, StubStore], epoch: str | None, generation: str | None
) -> None:
    browser, stub = client
    headers: list[tuple[bytes, bytes]] = [(b"origin", ORIGIN.encode())]
    if epoch is not None:
        headers.append((b"x-demo-epoch", epoch.encode("utf-8")))
    if generation is not None:
        headers.append((b"x-demo-generation", generation.encode("utf-8")))
    response = browser.get(f"/api/v4/demo/seed-summary?shop_id={uuid4()}", headers=headers)
    assert response.status_code == 422
    assert stub.calls == []


def test_generated_openapi_has_all_eight_routes_and_security() -> None:
    schema = demo_openapi()
    assert len(schema["paths"]) == 8
    assert schema["components"]["securitySchemes"]["demoCookie"]["name"] == "commerceops_v4_demo"
    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            if not path.endswith("/bootstrap"):
                assert operation["security"] == [{"demoCookie": []}]
            if method == "post":
                assert {p["name"] for p in operation["parameters"]} >= {"Origin", "X-CSRF-Token"}
    for path, model in (
        ("sessions", dto.CreateSessionInput),
        ("persona", dto.PersonaInput),
        ("reset", dto.ResetInput),
        ("logout", dto.LogoutInput),
    ):
        request = schema["paths"]["/api/v4/demo/" + path]["post"]["requestBody"]
        assert request["required"] is True
        assert request["content"]["application/json"]["schema"] == model.model_json_schema()
    summary = schema["paths"]["/api/v4/demo/seed-summary"]["get"]
    assert {p["name"] for p in summary["parameters"]} >= {
        "shop_id",
        "X-Demo-Epoch",
        "X-Demo-Generation",
    }


@pytest.mark.parametrize("operation", ["sessions", "persona", "reset", "logout"])
def test_valid_json_uuid_reaches_each_post_store(
    client: tuple[TestClient, StubStore], operation: str
) -> None:
    browser, stub = client
    wire: dict[str, Any] = {"request_key": str(uuid4())}
    if operation in ("sessions", "reset"):
        wire["fixture_version"] = "v4-demo-seed-1"
    if operation != "sessions":
        wire.update(expected_epoch=0, expected_generation=0)
    if operation == "persona":
        wire["persona_id"] = "operator"
    response = browser.post(
        "/api/v4/demo/" + operation,
        headers={"Origin": ORIGIN, "X-CSRF-Token": "offline"},
        json=wire,
    )
    # Authentication still fails in this stub, after successful strict wire parsing.
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SESSION_INVALID"
    assert stub.calls == ["create" if operation == "sessions" else operation]


@pytest.mark.parametrize("operation", ["persona", "reset", "logout"])
@pytest.mark.parametrize("invalid", [True, "0", 0.0, -1, None])
def test_json_aware_post_keeps_counters_strict(
    client: tuple[TestClient, StubStore], operation: str, invalid: Any
) -> None:
    browser, stub = client
    wire = dict(request_key=str(uuid4()), expected_epoch=invalid, expected_generation=0)
    if operation == "reset":
        wire["fixture_version"] = "v4-demo-seed-1"
    if operation == "persona":
        wire["persona_id"] = "operator"
    response = browser.post(
        "/api/v4/demo/" + operation,
        headers={"Origin": ORIGIN, "X-CSRF-Token": "offline"},
        json=wire,
    )
    assert response.status_code == 422 and stub.calls == []
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
