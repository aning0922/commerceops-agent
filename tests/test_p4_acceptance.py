"""无PG的实际新解释器来源/安全诊断/阶段与最终结果负例。"""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

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


@pytest.mark.parametrize("pollution", ["none", "pythonpath", "cwd", "helper", "entry", "request"])
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
    elif pollution == "helper":
        manifest["files"]["scripts/p4_acceptance.py"] = "0" * 64
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
