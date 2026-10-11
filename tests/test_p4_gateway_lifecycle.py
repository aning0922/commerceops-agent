"""正式WS生命周期候选仅offline：固定普通sleep child，不SDK/PG/旧私配。"""

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from commerceops.application.feishu_business.gateway_window import GatewayWindow
from commerceops.application.replenishment.contracts import WebFailure
from commerceops.entrypoints.feishu_business import run_gateway
from commerceops.entrypoints.feishu_gateway_child import BoundedReceiver
from pytest import MonkeyPatch as Patch

pytestmark = pytest.mark.offline


def window(**changes: Any) -> GatewayWindow:
    return GatewayWindow.model_validate_json(
        json.dumps(
            {
                "schema_version": "p4-gateway-v1",
                "window_id": str(uuid4()),
                "organization_id": "00000000-0000-4000-8000-000000000001",
                "shop_id": "00000000-0000-4000-8000-000000000002",
                "expires_at": (datetime.now(UTC) + timedelta(seconds=12)).isoformat(),
                "parameters": {
                    "source_mode": "mock",
                    "dataset_version": "inventory-v1",
                    "fixture_case": "baseline",
                    "L": 3,
                    "R": 7,
                    "S": 2,
                },
                **changes,
            }
        )
    )


@pytest.mark.parametrize(
    "change", [{"max_callbacks": 101}, {"max_workflows": 6}, {"max_callbacks": True}]
)
def test_window_cannot_expand_original_callback_or_workflow_bounds(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        window(**change)


def test_disabled_window_never_spawns_sdk_child(tmp_path: Path, monkeypatch: Patch) -> None:
    config = tmp_path / "config.json"
    config.write_bytes(Path("docs/contracts/p4-config.example.json").read_bytes())
    config.chmod(0o600)
    file = tmp_path / "window.json"
    file.write_text(window().model_dump_json())
    file.chmod(0o600)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("DISABLED_SDK_START_REJECTED")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    with pytest.raises(PermissionError, match="P4_GATEWAY_WINDOW_CLOSED"):
        run_gateway(config, file)


def test_parent_fixed_cutoff_terminates_and_reaps_one_plain_child_without_sdk(
    tmp_path: Path,
    monkeypatch: Patch,
) -> None:
    config = tmp_path / "config.json"
    config.write_bytes(Path("docs/contracts/p4-config.example.json").read_bytes())
    config.chmod(0o600)
    file = tmp_path / "window.json"
    file.write_text(window(enabled=True).model_dump_json())
    file.chmod(0o600)
    original = subprocess.Popen
    children = []

    def fake(argv: list[str], **kwargs: Any) -> Any:
        assert argv[1:3] == ["-m", "commerceops.entrypoints.feishu_gateway_child"]
        child = original([sys.executable, "-c", "import time; time.sleep(60)"], **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(subprocess, "Popen", fake)
    result = run_gateway(config, file)
    assert len(children) == 1 and children[0].poll() is not None
    assert result["result"] == "window_stopped" and result["child_reaped"] is True
    assert result["ws_handshake"] == result["ws_endpoint_discovery"] == "not_verified"


def test_callback_admission_cap_is_not_reported_as_raw_frame_or_ack_count() -> None:
    receiver = BoundedReceiver(None, window(enabled=True, max_callbacks=1))  # type: ignore[arg-type]
    receiver.admit()
    with pytest.raises(WebFailure, match="GATEWAY_CALLBACK_CAP_EXHAUSTED"):
        receiver.admit()
    assert receiver.admitted == 1
