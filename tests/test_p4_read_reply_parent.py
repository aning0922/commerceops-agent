"""原parent显式read_reply接线、成功语义及准入前零child/Secret；offline。"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from commerceops.adapters.feishu import business_factory
from commerceops.entrypoints import feishu_business as parent
from commerceops.infrastructure.web_config import WebConfig

from tests.test_p4_controlled_worker import configured
from tests.test_p4_read_reply import window

pytestmark = pytest.mark.offline


@pytest.mark.parametrize(
    "outcome,child_exit,confirmed,expected",
    [
        ("sent", 0, True, "window_stopped"),
        ("window_stopped", 0, True, "failed"),
        ("unknown", 0, True, "failed"),
        ("sent", 1, True, "failed"),
        ("sent", 0, False, "failed"),
    ],
)
def test_parent_binds_selected_carrier_and_requires_sent_reap_and_termination(
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
    child_exit: int,
    confirmed: bool,
    expected: str,
) -> None:
    settings, value = window()
    _, _, web = configured()
    metadata = {
        Path("/synthetic/config"): settings.model_dump_json(),
        Path("/synthetic/window"): json.dumps(value),
    }
    monkeypatch.setenv("COMMERCEOPS_MODE", "p4-controlled-test")
    monkeypatch.setattr(business_factory, "private_value", lambda path: metadata[path])
    monkeypatch.setattr(WebConfig, "from_file", staticmethod(lambda path: web))
    confirmation = AsyncMock(side_effect=None if confirmed else PermissionError("missing pair"))
    monkeypatch.setattr(parent, "confirm_worker_child", confirmation)
    calls: list[Any] = []

    class Process:
        returncode = child_exit
        pid = 123

        def communicate(self, **kwargs: Any) -> tuple[bytes, bytes]:
            return json.dumps(
                {"verification_mode": "controlled_sdk", "result": outcome, "model_requests": 0}
            ).encode(), b""

        def poll(self) -> int:
            return self.returncode

    def spawn(argv: list[str], **kwargs: Any) -> Process:
        calls.append(argv)
        return Process()

    monkeypatch.setattr(subprocess, "Popen", spawn)
    result = parent.run_worker(
        Path("/synthetic/config"), Path("/synthetic/window"), mode="read_reply"
    )
    assert result["result"] == expected and result["child_reaped"] is True
    assert result["lifecycle_termination_confirmed"] is confirmed
    assert calls == [
        [
            sys.executable,
            "-m",
            "commerceops.entrypoints.feishu_worker_child",
            "--live",
            "--config",
            "/synthetic/config",
            "--window-file",
            "/synthetic/window",
            "--mode",
            "read_reply",
        ]
    ]
    confirmation.assert_awaited_once_with(web, settings.organization_id, 123)


@pytest.mark.parametrize("change", ["disabled", "wrong_shop", "extra_method", "workflow_shape"])
def test_parent_read_reply_window_rejected_before_web_secret_or_child(
    monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    settings, value = window()
    if change == "disabled":
        value["enabled"] = False
    elif change == "wrong_shop":
        value["shop_id"] = str(uuid4())
    elif change == "extra_method":
        value["method_caps"]["bitable.v1.app_table_record.create"] = 1
    else:
        value.pop("reply_id")
        value["task_ids"] = [value.pop("task_id")]
    metadata = {
        Path("/synthetic/config"): settings.model_dump_json(),
        Path("/synthetic/window"): json.dumps(value),
    }

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("no WebConfig Secret read or child allowed")

    monkeypatch.setenv("COMMERCEOPS_MODE", "p4-controlled-test")
    monkeypatch.setattr(business_factory, "private_value", lambda path: metadata[path])
    monkeypatch.setattr(WebConfig, "from_file", staticmethod(forbidden))
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    with pytest.raises((PermissionError, ValueError)):
        parent.run_worker(Path("/synthetic/config"), Path("/synthetic/window"), mode="read_reply")


def test_parent_CLI_explicit_read_reply_mode_only_on_live_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []

    def run(config: Path, window_file: Path, **kwargs: Any) -> dict[str, str]:
        calls.append((config, window_file, kwargs))
        return {"result": "window_stopped"}

    monkeypatch.setattr(parent, "run_worker", run)
    argv = [
        "feishu_business",
        "worker",
        "--config",
        "/synthetic/config",
        "--window-file",
        "/synthetic/window",
        "--worker-mode",
        "read_reply",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit):
        parent.main()
    assert calls == []
    monkeypatch.setattr(sys, "argv", [*argv, "--live"])
    parent.main()
    assert calls == [(Path("/synthetic/config"), Path("/synthetic/window"), {"mode": "read_reply"})]
    monkeypatch.setattr(sys, "argv", [argv[0], "gateway", *argv[2:], "--live"])
    with pytest.raises(SystemExit):
        parent.main()
    assert len(calls) == 1
