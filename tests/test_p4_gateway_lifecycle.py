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


@pytest.mark.parametrize("replacement", ["before-spawn", "after-spawn"])
def test_parent_bound_webjson_replacement_rejects_child_before_secret_sdk_or_claim(
    tmp_path: Path,
    monkeypatch: Patch,
    replacement: str,
) -> None:
    import hashlib
    from unittest.mock import Mock

    from commerceops.entrypoints import feishu_gateway_child as child
    from commerceops.infrastructure import web_config as private

    from tests.test_p4_controlled_worker import configured

    settings, _, config = configured()
    web_path = tmp_path / "web.json"
    original_body = json.dumps(
        {
            "database": config.database.model_dump(mode="json"),
            "csrf_secret_file": "/never-read/original-csrf",
            "nonce_secret_file": "/never-read/original-nonce",
            "origins": list(config.origins),
            "transport_mode": config.transport_mode,
        }
    ).encode()
    changed = json.dumps(
        {
            "database": config.database.model_dump(mode="json"),
            "csrf_secret_file": "/never-read/replaced",
        }
    ).encode()
    web_path.write_bytes(original_body)
    web_path.chmod(0o600)
    settings = settings.model_copy(update={"web_config_file": web_path})
    config_path, window_path = tmp_path / "business.json", tmp_path / "window.json"
    config_path.write_text(settings.model_dump_json())
    config_path.chmod(0o600)
    current = window(enabled=True).model_copy(
        update={
            "organization_id": settings.organization_id,
            "shop_id": settings.shop_id,
        }
    )
    window_path.write_text(current.model_dump_json())
    window_path.chmod(0o600)
    expected = hashlib.sha256(original_body).hexdigest()
    protected = private.private_bytes
    secret_reads: list[Path] = []

    def read(path: Path) -> bytes:
        if path == web_path:
            return protected(path)
        secret_reads.append(path)
        raise AssertionError("secret read before WebJSON binding")

    monkeypatch.setattr(private, "private_bytes", read)
    monkeypatch.setattr(
        "commerceops.entrypoints.feishu_gateway_child.signal.setitimer", lambda *args: None
    )
    claim, database, sdk = Mock(), Mock(), Mock()
    monkeypatch.setattr(child, "claim_gateway", claim)
    monkeypatch.setattr(child, "connect", database)
    monkeypatch.setattr("commerceops.entrypoints.feishu_gateway_child.lark.ws.Client", sdk)
    calls: list[list[str]] = []

    class FailedChild:
        pid = 123456
        returncode = 1

        def wait(self, timeout: float) -> int:
            return 1

        def poll(self) -> int:
            return 1

    def spawn(argv: list[str], **kwargs: Any) -> FailedChild:
        calls.append(argv)
        assert argv[-2:] == ["--web-config-sha256", expected]
        if replacement == "after-spawn":
            web_path.write_bytes(changed)
        with pytest.raises(ValueError, match="INVALID_WEB_CONFIGURATION"):
            child.serve(config_path, window_path, web_config_sha256=argv[-1])
        return FailedChild()

    monkeypatch.setattr(subprocess, "Popen", spawn)
    if replacement == "before-spawn":
        web_path.write_bytes(changed)
    result = run_gateway(config_path, window_path, web_config_sha256=expected)
    assert result["result"] == "failed" and result["child_reaped"] is True
    assert len(calls) == 1 and secret_reads == []
    claim.assert_not_called()
    database.assert_not_called()
    sdk.assert_not_called()


def test_bound_webconfig_parses_one_buffer_despite_later_path_replacement(
    tmp_path: Path,
    monkeypatch: Patch,
) -> None:
    import hashlib

    from commerceops.infrastructure import web_config as private

    from tests.test_p4_controlled_worker import configured

    _, _, config = configured()
    path = tmp_path / "web.json"
    body = json.dumps(
        {
            "database": config.database.model_dump(mode="json"),
            "csrf_secret_file": "/never-read/original-csrf",
            "nonce_secret_file": "/never-read/original-nonce",
            "origins": list(config.origins),
            "transport_mode": config.transport_mode,
        }
    ).encode()
    path.write_bytes(body)
    path.chmod(0o600)
    protected = private.private_bytes
    reads: list[Path] = []

    def read(target: Path) -> bytes:
        reads.append(target)
        if target == path:
            return protected(target)
        path.write_text('{"database":{},"csrf_secret_file":"/replaced"}')
        return b"a" * 32 if target.name == "original-csrf" else b"b" * 32

    monkeypatch.setattr(private, "private_bytes", read)
    actual = private.WebConfig.from_file(path, expected_sha256=hashlib.sha256(body).hexdigest())
    assert actual.database == config.database
    assert reads == [path, Path("/never-read/original-csrf"), Path("/never-read/original-nonce")]
    assert actual.csrf_secret == b"a" * 32 and actual.nonce_secret == b"b" * 32


@pytest.mark.parametrize("expected", ["", "0" * 64, "A" * 64, "x" * 64])
def test_invalid_or_changed_webjson_hash_reads_no_secret(
    tmp_path: Path,
    monkeypatch: Patch,
    expected: str,
) -> None:
    from commerceops.infrastructure import web_config as private

    path = tmp_path / "web.json"
    path.write_text("{}")
    path.chmod(0o600)
    reads: list[Path] = []
    protected = private.private_bytes

    def read(target: Path) -> bytes:
        reads.append(target)
        assert target == path
        return protected(target)

    monkeypatch.setattr(private, "private_bytes", read)
    with pytest.raises(ValueError, match="INVALID_WEB_CONFIGURATION"):
        private.WebConfig.from_file(path, expected_sha256=expected)
    assert reads == [path]


def test_bound_canonical_claim_failure_reads_no_appsecret_sdk_or_business(
    tmp_path: Path,
    monkeypatch: Patch,
) -> None:
    import hashlib
    from unittest.mock import Mock

    from commerceops.entrypoints import feishu_gateway_child as child
    from commerceops.infrastructure import web_config as private

    from tests.test_p4_controlled_worker import configured

    settings, _, config = configured()
    path = tmp_path / "web.json"
    body = json.dumps(
        {
            "database": config.database.model_dump(mode="json"),
            "csrf_secret_file": "/never-read/csrf",
            "nonce_secret_file": "/never-read/nonce",
            "origins": list(config.origins),
            "transport_mode": config.transport_mode,
        }
    ).encode()
    path.write_bytes(body)
    path.chmod(0o600)
    settings = settings.model_copy(update={"web_config_file": path})
    current = window(enabled=True).model_copy(
        update={
            "organization_id": settings.organization_id,
            "shop_id": settings.shop_id,
        }
    )
    files = {
        Path("/fake/business"): settings.model_dump_json(),
        Path("/fake/window"): current.model_dump_json(),
    }
    config_reads: list[Path] = []

    def value(target: Path) -> str:
        config_reads.append(target)
        return files[target]

    monkeypatch.setattr(child, "private_value", value)
    protected = private.private_bytes
    reads: list[Path] = []

    def read(target: Path) -> bytes:
        reads.append(target)
        return (
            protected(target)
            if target == path
            else b"a" * 32
            if target.name == "csrf"
            else b"b" * 32
        )

    monkeypatch.setattr(private, "private_bytes", read)
    monkeypatch.setattr(
        "commerceops.entrypoints.feishu_gateway_child.signal.setitimer", lambda *args: None
    )

    class Lease:
        def __enter__(self) -> "Lease":
            return self

        def __exit__(self, *args: Any) -> None:
            pass

    monkeypatch.setattr(child, "connect", lambda _: Lease())
    monkeypatch.setattr(
        child, "claim_gateway", Mock(side_effect=PermissionError("synthetic claim"))
    )
    started, sdk, business = Mock(), Mock(), Mock()
    monkeypatch.setattr(child, "gateway_process_started", started)
    monkeypatch.setattr("commerceops.entrypoints.feishu_gateway_child.lark.ws.Client", sdk)
    monkeypatch.setattr(child, "FeishuBusinessStore", business)
    with pytest.raises(PermissionError):
        child.serve(
            Path("/fake/business"),
            Path("/fake/window"),
            web_config_sha256=hashlib.sha256(body).hexdigest(),
        )
    assert reads == [path, Path("/never-read/csrf"), Path("/never-read/nonce")]
    assert settings.app_secret_file not in config_reads
    started.assert_not_called()
    sdk.assert_not_called()
    business.assert_not_called()
