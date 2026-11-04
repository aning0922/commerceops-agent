"""Default-off deployment and real shared ASGI auth boundary; no PG/provider calls."""

import asyncio
import json
import secrets
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from commerceops.application.commerce.readonly_inquiry_service_contracts import InquiryError
from commerceops.application.replenishment.contracts import WebFailure
from commerceops.application.runner import RunResult
from commerceops.entrypoints.api import create_app
from commerceops.infrastructure.database import DatabaseSettings
from commerceops.infrastructure.inventory_repository import AnalysisUnsafe
from commerceops.infrastructure.readonly_inquiry_config import InquiryDeployment
from commerceops.infrastructure.replenishment_repository import ReplenishmentStore
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.web_sessions import SessionStore
from commerceops.workflows.report_explanation import InventoryCompositeRunner
from fastapi.testclient import TestClient
from pydantic import ValidationError

pytestmark = pytest.mark.offline


def deployment(directory: Path, **changes: object) -> InquiryDeployment:
    return InquiryDeployment.model_validate_json(
        json.dumps(
            {
                "schema_version": "p6-inquiry-deployment-v1",
                "shop_id": str(uuid4()),
                "fixture_directory": str(directory),
                **changes,
            }
        )
    )


def web() -> tuple[WebConfig, ReplenishmentStore]:
    config = WebConfig(
        DatabaseSettings(
            host="127.0.0.1", name="not_used", user="not_used", password_file=Path("/never-read")
        ),
        secrets.token_bytes(32),
        secrets.token_bytes(32),
        ("http://127.0.0.1",),
        transport_mode="local_http",
    )
    return config, ReplenishmentStore(config, Path("/never-loaded"))


def test_explicit_deployment_is_off_and_never_selects_an_actual_provider(tmp_path: Path) -> None:
    value = deployment(tmp_path)
    assert value.runtime().enabled is False
    assert value.runtime().fixture_directory == tmp_path
    for update in (
        {"enabled": 1},
        {"source_kind": "woocommerce_test"},
        {"model_mode": "actual"},
        {"model_requests_enabled": True},
        {"model_requests_enabled": 0},
        {"external_sender_enabled": True},
        {"external_sender_enabled": 0},
        {"fixture_directory": "relative"},
        {"fixture_directory": str(tmp_path / ".." / "other")},
        {"fixture_case": "other"},
        {"source_url": "http://127.0.0.1"},
    ):
        with pytest.raises(ValidationError):
            deployment(tmp_path, **update)


def test_private_deployment_rejects_symlink_and_keeps_fixed_diagnostic(tmp_path: Path) -> None:
    config = tmp_path / "deployment.json"
    config.write_text(deployment(tmp_path).model_dump_json())
    config.chmod(0o600)
    assert InquiryDeployment.load(config).runtime().enabled is False
    link = tmp_path / "link.json"
    link.symlink_to(config)
    with pytest.raises(ValueError, match="^INVALID_INQUIRY_DEPLOYMENT$"):
        InquiryDeployment.load(link)
    config.chmod(0o644)
    with pytest.raises(ValueError, match="^INVALID_INQUIRY_DEPLOYMENT$"):
        InquiryDeployment.load(config)


def test_inquiry_requires_web_and_does_not_appear_by_default(tmp_path: Path) -> None:
    config, store = web()
    default = create_app(web_config=config, replenishment_store=store)
    assert not hasattr(default.state, "inquiry_openapi")
    assert not any(
        path.startswith("/api/v1/readonly-inquiries") for path in default.openapi()["paths"]
    )
    with pytest.raises(ValueError, match="requires explicit Web"):
        create_app(inquiry_config=deployment(tmp_path).runtime())


def test_shared_auth_errors_are_inquiry_dtos_and_legacy_schema_is_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied(_self: object, _token: str | None) -> None:
        raise WebFailure("SESSION_INVALID", 401)

    monkeypatch.setattr(SessionStore, "authenticate", denied)
    config, store = web()
    legacy = create_app(web_config=config, replenishment_store=store).openapi()
    app = create_app(
        web_config=config,
        replenishment_store=store,
        inquiry_config=deployment(tmp_path).runtime(),
    )
    assert app.openapi() == legacy
    assert set(app.state.inquiry_openapi["paths"]) == {
        "/api/v1/readonly-inquiries",
        "/api/v1/readonly-inquiries/{task_id}",
        "/api/v1/readonly-inquiries/requests/{request_key}",
    }
    with TestClient(app, base_url="http://127.0.0.1") as client:
        for path in (
            "/api/v1/readonly-inquiries",
            f"/api/v1/readonly-inquiries/{uuid4()}",
            f"/api/v1/readonly-inquiries/requests/{uuid4()}",
        ):
            response = client.get(path)
            assert response.status_code == 401
            assert InquiryError.model_validate_json(response.content).code == "SESSION_INVALID"
            assert response.headers["cache-control"] == "no-store"
        response = client.post(
            "/api/v1/readonly-inquiries", json={}, headers={"Origin": "https://example.invalid"}
        )
        assert response.status_code == 403
        assert InquiryError.model_validate_json(response.content).code == "ORIGIN_DENIED"


def test_inquiry_dispatch_shares_the_existing_composite_slot() -> None:
    async def scenario() -> None:
        entered, release = asyncio.Event(), asyncio.Event()

        class Port:
            def __init__(self, version: str) -> None:
                self.workflow_versions = frozenset({version})
                self.calls = 0

            async def run(self, request: Any) -> RunResult:
                self.calls += 1
                if request.workflow_version == "p6-readonly-inquiry-v1":
                    entered.set()
                    await release.wait()
                return RunResult()

        analysis, explanation = Port("analysis"), Port("explanation")
        inquiry = Port("p6-readonly-inquiry-v1")
        composite = InventoryCompositeRunner(
            cast(Any, analysis), cast(Any, explanation), inquiry=inquiry
        )
        first = asyncio.create_task(
            composite.run(cast(Any, SimpleNamespace(workflow_version="p6-readonly-inquiry-v1")))
        )
        await asyncio.wait_for(entered.wait(), 1)
        try:
            with pytest.raises(AnalysisUnsafe, match="GLOBAL_GRAPH_SLOT_BUSY"):
                await composite.run(cast(Any, SimpleNamespace(workflow_version="analysis")))
        finally:
            release.set()
            await first
        assert inquiry.calls == 1 and analysis.calls == 0
        await composite.run(cast(Any, SimpleNamespace(workflow_version="analysis")))
        assert analysis.calls == 1

    asyncio.run(scenario())
