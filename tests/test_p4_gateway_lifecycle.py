"""正式WS生命周期候选仅offline：固定普通sleep child，不SDK/PG/旧私配。"""

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from commerceops.application.feishu_business.gateway_window import GatewayWindow
from commerceops.application.replenishment.contracts import WebFailure
from commerceops.entrypoints.feishu_business import run_gateway
from commerceops.entrypoints.feishu_gateway_child import BoundedReceiver
from commerceops.infrastructure.feishu_gateway_window import guard_gateway
from commerceops.infrastructure.web_sessions import DB
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


class WindowRow:
    """仅offline审计读取；不模拟PG lease/schema/业务事务成功。"""

    def __init__(self, original: GatewayWindow) -> None:
        self.calls = 0
        self.row = {
            "after_state": {
                **original.model_dump(mode="json"),
                "verification_mode": "controlled_sdk",
                "ws_endpoint_discovery": "not_verified",
                "ws_handshake": "not_verified",
            }
        }

    def execute(self, *args: Any) -> "WindowRow":
        self.calls += 1
        return self

    def fetchone(self) -> dict[str, Any]:
        return self.row


def test_original_complete_window_json_accepts_original_scope_without_business_query() -> None:
    original = window(enabled=True)
    db = WindowRow(original)
    guard_gateway(cast(DB, db), original, False)
    assert db.calls == 1


@pytest.mark.parametrize(
    "field",
    [
        "shop_id",
        "organization_id",
        "window_id",
        "expires_at",
        "parameters",
        "max_workflows",
        "max_callbacks",
        "enabled",
    ],
)
def test_changed_window_binding_rejects_before_workflow_query(field: str) -> None:
    original = window(enabled=True)
    changes: dict[str, Any] = {
        "shop_id": uuid4(),
        "organization_id": uuid4(),
        "window_id": uuid4(),
        "expires_at": original.expires_at + timedelta(seconds=1),
        "parameters": original.parameters.model_copy(update={"L": 4}),
        "max_workflows": 4,
        "max_callbacks": 99,
        "enabled": False,
    }
    db = WindowRow(original)
    with pytest.raises(WebFailure, match="GATEWAY_WINDOW_CLOSED"):
        guard_gateway(cast(DB, db), original.model_copy(update={field: changes[field]}), True)
    assert db.calls == 1
