"""Actual application composition with strict copy configuration; no PG/provider."""

import json

import pytest
from commerceops.application.replenishment.contracts import WebFailure
from commerceops.entrypoints.api import create_app
from commerceops.infrastructure.knowledge_copy_config import CopyDeployment
from commerceops.infrastructure.web_sessions import SessionStore
from fastapi.testclient import TestClient

from tests.test_m3_inquiry_wiring import web
from tests.test_p6_copy_config import config_body

pytestmark = pytest.mark.offline


def configured() -> CopyDeployment:
    return CopyDeployment.model_validate_json(json.dumps(config_body()))


@pytest.mark.parametrize("daily_enabled", [False, True])
@pytest.mark.parametrize("copy_enabled", [False, True])
def test_copy_and_daily_are_independent_and_preserve_legacy_schema(
    daily_enabled: bool, copy_enabled: bool
) -> None:
    config, store = web()
    legacy = create_app(web_config=config, replenishment_store=store).openapi()
    app = create_app(
        web_config=config,
        replenishment_store=store,
        daily_enabled=daily_enabled,
        copy_deployment=configured() if copy_enabled else None,
    )
    assert app.openapi() == legacy
    assert hasattr(app.state, "copy_openapi") is copy_enabled
    assert hasattr(app.state, "daily_openapi") is daily_enabled
    if copy_enabled:
        assert len(app.state.copy_openapi["paths"]) == 5


def test_copy_explicitly_requires_the_real_web_boundary() -> None:
    with pytest.raises(ValueError, match="copy requires explicit Web"):
        create_app(copy_deployment=configured())


def test_shared_copy_auth_failure_uses_original_frozen_error_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def denied(_self: object, _token: str | None) -> None:
        raise WebFailure("SESSION_INVALID", 401)

    monkeypatch.setattr(SessionStore, "authenticate", denied)
    config, store = web()
    app = create_app(web_config=config, replenishment_store=store, copy_deployment=configured())
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.get(
            "/api/v1/copy/candidate-requests/00000000-0000-4000-8000-000000000001"
        )
        assert response.status_code == 401
        value = response.json()
        assert value["schema_version"] == "p3-web-v1"
        assert value["error"]["code"] == "SESSION_INVALID"
        assert response.headers["cache-control"] == "no-store"
