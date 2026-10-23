"""薄demo源码负约束；不启动Docker/SDK/PG，不以此签cleanCompose。"""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from commerceops.application.feishu_business.contracts import bind_projection_result

from scripts.m1_offline_demo import OfflineProjection, request, save
from tests.test_p4_contracts import projection_pair

pytestmark = pytest.mark.offline


@pytest.mark.parametrize("mutation", ["mode", "project", "sdk", "provider", "expired", "dns"])
def test_demo_requires_matching_owned_project_mock_fixed_window_and_loopback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    monkeypatch.setenv("COMMERCEOPS_MODE", "m1-offline-demo")
    monkeypatch.setenv("COMMERCEOPS_DEMO_PROJECT", "m1off-synthetic")
    value: dict[str, Any] = {
        "project": "m1off-synthetic",
        "source_mode": "mock",
        "external_sender_enabled": False,
        "provider_enabled": False,
        "expires_at": (datetime.now(UTC) + timedelta(seconds=60)).isoformat(),
        "web_origin": "http://127.0.0.1:34401",
        "api_origin": "http://127.0.0.1:34402",
    }
    if mutation == "mode":
        monkeypatch.setenv("COMMERCEOPS_MODE", "test")
    elif mutation == "project":
        value["project"] = "another-project"
    elif mutation == "sdk":
        value["external_sender_enabled"] = True
    elif mutation == "provider":
        value["provider_enabled"] = True
    elif mutation == "expired":
        value["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    else:
        value["api_origin"] = "http://m1-api:8000"
    save(tmp_path / "demo-request.json", value)
    with pytest.raises(ValueError):
        request(tmp_path)


def test_offline_projection_is_only_synthetic_full_current_fields_and_preserves_anchor() -> None:
    original, _ = projection_pair()
    original = original.model_copy(update={"operation": "create", "external_id": None})
    result = asyncio.run(OfflineProjection().project(original))
    assert result.code == "OFFLINE_DEMO_FAKE"
    assert result.external_id and result.external_id.startswith("synthetic-")
    assert bind_projection_result(original, result).outcome == "verified"
    update = original.model_copy(update={"operation": "update", "external_id": result.external_id})
    assert asyncio.run(OfflineProjection().project(update)).external_id == result.external_id
