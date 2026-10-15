"""无PG的实际新解释器来源/安全诊断/阶段与最终结果负例。"""

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from scripts.p4_acceptance import (
    CONTRACT,
    AcceptanceFailure,
    Deadline,
    StageReport,
    bound_bytes,
    digest,
    materialize_entry,
    safe_failure,
    source_manifest,
    write_private,
)

pytestmark = pytest.mark.offline
ROOT = Path(__file__).resolve().parents[1]


def invocation(tmp_path: Path) -> tuple[list[str], dict[str, Any]]:
    tmp_path.chmod(0o700)
    entry = materialize_entry(tmp_path)
    manifest = source_manifest(ROOT, entry)
    manifest_file, request = tmp_path / "manifest.json", tmp_path / "request.json"
    write_private(manifest_file, manifest)
    write_private(request, {"contract": CONTRACT, "action": "source_probe"})
    command = [
        sys.executable,
        "-I",
        str(entry),
        "--manifest",
        str(manifest_file),
        "--manifest-sha256",
        digest(manifest_file.read_bytes()),
        "--request",
        str(request),
        "--request-sha256",
        digest(request.read_bytes()),
    ]
    return command, manifest


@pytest.mark.parametrize(
    "pollution", ["none", "pythonpath", "cwd", "helper", "asset", "entry", "request"]
)
def test_actual_outer_source_closed_before_any_PG_or_SDK(tmp_path: Path, pollution: str) -> None:
    command, manifest = invocation(tmp_path)
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    cwd = ROOT
    if pollution == "pythonpath":
        env["PYTHONPATH"] = str(tmp_path)
    elif pollution == "cwd":
        cwd = tmp_path
    elif pollution in ("entry", "request"):
        path = tmp_path / ("run_once.py" if pollution == "entry" else "request.json")
        path.write_bytes(path.read_bytes() + b"\n")
    elif pollution in ("helper", "asset"):
        file = (
            "scripts/p4_acceptance.py"
            if pollution == "helper"
            else "backend/src/commerceops/assets/p3-web-v1.openapi.json"
        )
        manifest["files"][file] = "0" * 64
        write_private(tmp_path / "manifest.json", manifest)
        command[command.index("--manifest-sha256") + 1] = digest(
            (tmp_path / "manifest.json").read_bytes()
        )
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, timeout=30)
    assert result.returncode == (0 if pollution == "none" else 1)
    assert b"Traceback" not in result.stderr
    if pollution != "none":
        assert json.loads(result.stdout)["code"] == "P4A_BOOTSTRAP"


def test_final_pass_requires_all_stages_and_cleanup_not_just_business() -> None:
    report = StageReport(("CALL", "COLLECT", "CLEANUP"))
    with report.enter("CALL"):
        pass
    assert report.terminal(cleanup=True, reaped=True, owned=True)["exit_code"] == 1
    assert report.stages["COLLECT"]["state"] == "NOT_RUN"
    with pytest.raises(AcceptanceFailure), report.enter("COLLECT"):
        raise AcceptanceFailure("P4A_QUERY_SHAPE", query_id="ITEMS")
    with report.enter("CLEANUP"):
        pass
    final = report.terminal(cleanup=True, reaped=True, owned=True)
    assert final["result"] == "FAIL"
    assert final["stages"]["COLLECT"]["failure"]["query_id"] == "ITEMS"


def test_safe_DTO_error_only_contract_loc_type_no_input_context_or_message() -> None:
    class Input(BaseModel):
        model_config = ConfigDict(strict=True, extra="forbid")
        required_number: int

    try:
        Input.model_validate({"required_number": "never-print-me", "never-print-key": "secret"})
    except ValidationError as error:
        value = safe_failure(error, "PREPARE")
    encoded = json.dumps(value)
    assert "required_number" in encoded and "int_type" in encoded
    assert all(
        text not in encoded for text in ("never-print", "secret", '"input"', '"ctx"', '"msg"')
    )


def test_deadline_cannot_roll_or_arm_inside_cleanup_reserve() -> None:
    with pytest.raises(AcceptanceFailure):
        Deadline.register(datetime.now(UTC) + timedelta(seconds=100))
    fixed = Deadline.register(datetime.now(UTC) + timedelta(seconds=240))
    assert 0 < fixed.remaining() <= 60
    assert 180 < fixed.remaining(cleanup=True) <= 240


def test_private_fd_rejects_symlink_and_changed_expected_bytes(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    target = tmp_path / "target.json"
    write_private(target, {"synthetic": True})
    with pytest.raises(AcceptanceFailure):
        bound_bytes(target, "0" * 64, private=True)
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(AcceptanceFailure):
        bound_bytes(link, private=True)


def test_cleanup_worker_capture_cannot_lend_its_reserve_to_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import p4_acceptance as shared
    from tests.p4_acceptance_support import reference

    tmp_path.chmod(0o700)
    run, owner, organization = uuid4().hex, str(uuid4()), str(uuid4())
    ready, config_file, handoff_file = (
        tmp_path / n for n in ("ready.json", "app.json", "handoff.json")
    )
    write_private(ready, {"owner": owner, "organization": organization})
    write_private(config_file, {"synthetic": True})
    clock = {
        "deadline_utc": (datetime.now(UTC) + timedelta(seconds=60)).isoformat(),
        "monotonic_end": time.monotonic() + 60,
        "cleanup_reserve_seconds": 180,
    }
    runner = {"host_private_dir": str(tmp_path), "container_private_dir": "/run/owned"}
    handoff = {
        "contract": CONTRACT,
        "resource": {"run_id": run, "runtime": clock},
        "fixture": {
            "organization_id": organization,
            "schema_revision": "0016_p4_clarification_requests",
            **{
                k: str(uuid4())
                for k in ("shop_id", "task_id", "target_item_id", "principal_id", "web_identity_id")
            },
            "auth_version": 1,
            "checkpoint_threads": ["synthetic-thread"],
            "case_kind": "recover_single_item",
            "item_count": 1,
            "quantity_total": "70",
        },
        "private_refs": {"app_database_config": reference(config_file)},
    }
    write_private(handoff_file, handoff)
    monkeypatch.setitem(shared._APP_OWNERS, (run, owner), reference(ready))
    entered = []

    def verified(value: Any, *, cleanup: bool = False) -> dict[str, Any]:
        shared._runtime(clock).remaining(cleanup=cleanup)
        entered.append(cleanup)
        return runner

    monkeypatch.setattr(shared, "_verified_runner", verified)
    monkeypatch.setattr(shared, "_runner_start", lambda *args: object())
    monkeypatch.setattr(shared, "_runner_result", lambda *args, **kwargs: {"value": {"events": []}})
    assert (
        shared.capture_bridge(
            "worker",
            handoff,
            handoff_ref=reference(handoff_file),
            phase="final-worker",
            owner=owner,
        )["phase"]
        == "final-worker"
    )
    assert entered == [True]
    with pytest.raises(AcceptanceFailure, match="P4A_DEADLINE"):
        shared.capture_bridge(
            "snapshot", handoff, handoff_ref=reference(handoff_file), phase="post-replay"
        )
    with pytest.raises(AcceptanceFailure, match="P4A_APP_OWNER_UNBOUND"):
        shared.capture_bridge(
            "worker",
            handoff,
            handoff_ref=reference(handoff_file),
            phase="final-worker",
            owner=str(uuid4()),
        )


def test_app_stop_still_attempts_API_when_worker_evidence_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import p4_acceptance as shared
    from tests.p4_acceptance_support import reference

    tmp_path.chmod(0o700)
    run = uuid4().hex
    app = tmp_path / "app.json"
    write_private(app, {"synthetic": True})
    h = {
        "contract": CONTRACT,
        "resource": {"run_id": run},
        "private_refs": {"web_config": reference(app), "app_database_config": reference(app)},
    }
    handoff_file = tmp_path / "handoff.json"
    write_private(handoff_file, h)
    runner = {"host_private_dir": str(tmp_path), "container_private_dir": "/run/owned"}
    monkeypatch.setattr(shared, "_verified_runner", lambda *args, **kwargs: runner)
    children = {}
    for name in ("worker", "api"):
        ready = tmp_path / (name + ".json")
        write_private(ready, {"kind": name})
        children[name] = SimpleNamespace(process=SimpleNamespace(poll=lambda: None), ready=ready)
    monkeypatch.setitem(shared._APP_EPOCHS, run, {**children, "epoch": {}})
    signals = []

    def start(value: Any, request: dict[str, Any]) -> object:
        signals.append(request["action"])
        return object()

    def result(child: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if child is children["worker"]:
            raise AcceptanceFailure("P4A_QUERY_SHAPE", query_id="WORKER_LIFECYCLE")
        return {"exit_code": 0}

    monkeypatch.setattr(shared, "_runner_start", start)
    monkeypatch.setattr(shared, "_runner_result", result)
    with pytest.raises(AcceptanceFailure, match="P4A_APP_STOP_FAILED"):
        shared.app_lifecycle("stop", h, handoff_ref=reference(handoff_file))
    assert signals == ["signal_process", "signal_process"]
    assert (tmp_path / "app-stop-failures.safe.json").exists()
