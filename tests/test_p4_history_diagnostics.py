"""固定诊断通道的秘密排除与父/child非零语义；不连接数据库或平台。"""

import json
import subprocess
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from commerceops.adapters.feishu import business_factory
from commerceops.application.feishu_business.history import history_failure, safe_history_failure
from commerceops.entrypoints import feishu_business as parent
from commerceops.entrypoints import feishu_worker_child as child
from commerceops.infrastructure.web_config import WebConfig

from tests.test_p4_controlled_worker import configured
from tests.test_p4_history import request

pytestmark = pytest.mark.offline


def metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    settings, _, web = configured()
    window = request()
    settings = settings.model_copy(
        update={
            "organization_id": window.organization_id,
            "shop_id": window.shop_id,
            "app_id": window.app_id,
            "tenant_key": window.tenant_key,
            "allowed_open_ids": frozenset({window.open_id}),
        }
    )
    values = {
        Path("/synthetic/config"): settings.model_dump_json(),
        Path("/synthetic/window"): window.model_dump_json(),
    }
    monkeypatch.setattr(business_factory, "private_value", lambda path: values[path])
    monkeypatch.setattr(child, "private_value", lambda path: values[path])
    monkeypatch.setattr(WebConfig, "from_file", staticmethod(lambda path: web))
    monkeypatch.setenv("COMMERCEOPS_MODE", "p4-controlled-test")


def test_error_message_unknown_keys_and_invalid_frames_never_escape() -> None:
    marker = uuid4().hex
    try:
        raise ValueError(marker)
    except ValueError as error:
        value = history_failure(error, "MATERIALIZE")
    assert value["stage"] == "MATERIALIZE" and value["category"] == "ValueError"
    assert marker not in json.dumps(value)
    untrusted = safe_history_failure(
        {
            "stage": [marker],
            "category": "ValueError",
            "message": marker,
            "raw": marker,
            "frames": [{"file": marker + "/secret.py", "function": "f", "line": 5}],
        }
    )
    assert untrusted["stage"] == "NOT_CAPTURED" and untrusted["frames"] == []
    assert marker not in json.dumps(untrusted)


def test_child_bootstrap_failure_emits_only_fixed_JSON_and_keeps_exit_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    metadata(monkeypatch)
    marker = uuid4().hex
    monkeypatch.setattr(
        child, "controlled_history_recovery", AsyncMock(side_effect=ValueError(marker))
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "worker",
            "--config",
            "/synthetic/config",
            "--window-file",
            "/synthetic/window",
            "--mode",
            "history_recovery",
            "--live",
        ],
    )
    with pytest.raises(SystemExit) as stopped:
        child.main()
    assert stopped.value.code == "P4_CONTROLLED_WORKER_FAILED"
    value = json.loads(capsys.readouterr().out)
    assert value["result"] == "failed"
    assert value["failure"]["primary"]["stage"] == "BOOTSTRAP"
    assert value["failure"]["primary"]["category"] == "ValueError"
    assert marker not in json.dumps(value)


@pytest.mark.parametrize("captured", [False, True])
def test_parent_retains_nonzero_PID_and_sanitized_or_missing_diagnostic(
    monkeypatch: pytest.MonkeyPatch, captured: bool
) -> None:
    metadata(monkeypatch)
    marker = uuid4().hex
    row = {
        "verification_mode": "controlled_sdk",
        "result": "failed",
        "raw": marker,
        "failure": {
            "primary": {
                "stage": "REGISTER",
                "category": "UniqueViolation",
                "sqlstate": "23505",
                "message": marker,
            },
            "raw": marker,
        },
    }

    class Process:
        pid = 123
        returncode = 1

        def communicate(self, **kwargs: Any) -> tuple[bytes, bytes]:
            return (json.dumps(row).encode() if captured else b""), b""

        def poll(self) -> int:
            return self.returncode

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: Process())
    monkeypatch.setattr(parent, "confirm_worker_child", AsyncMock())
    result = parent.run_worker(
        Path("/synthetic/config"), Path("/synthetic/window"), mode="history_recovery"
    )
    assert result["result"] == "failed" and result["child_exit"] == 1
    assert result["history_child_PID"] == 123 and result["child_reaped"]
    detail = cast(dict[str, Any], result["official_summary"])["failure"]["primary"]
    assert detail["stage"] == ("REGISTER" if captured else "NOT_CAPTURED")
    assert detail["sqlstate"] == ("23505" if captured else None)
    assert marker not in json.dumps(result)
