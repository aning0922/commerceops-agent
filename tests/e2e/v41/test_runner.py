"""Actual short child processes; these results never count as V41 runtime Gates."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from .process import ROOT, group_absent
from .runner import run

pytestmark = pytest.mark.offline


@pytest.mark.parametrize(
    ("recipe", "exit_code"),
    [
        ("normal", 0),
        ("nonzero", 1),
        ("timeout", 1),
        ("observer_missing", 1),
        ("cleanup_fail", 1),
        ("summary_fail", 1),
    ],
)
def test_real_process_failure_accounting(tmp_path: Path, recipe: str, exit_code: int) -> None:
    directory = tmp_path / recipe
    cli = subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.e2e.v41.runner",
            "run",
            "--recipe",
            recipe,
            "--directory",
            str(directory),
        ],
        cwd=ROOT,
        env={},
        capture_output=True,
        timeout=15,
    )
    assert cli.returncode == exit_code
    # The launcher observes the actual outer CLI exit, separately from worker/checks.
    fd = os.open(directory / "launcher.native.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump({"outer_cli_native_exit": cli.returncode, "scope": "SIMULATION_ONLY"}, stream)
    outer = json.loads((directory / "outer.json").read_text())
    checks = json.loads((directory / "checks.json").read_text())
    summary = json.loads((directory / "stdout_summary.json").read_text())
    assert outer["worker_native_exit"] == exit_code and outer["worker_reaped"]
    assert outer["stage_gate"] == "NOT_RUN"
    assert not outer["outer_timed_out"] and outer["remaining_registered_resources"] == []
    assert (
        hashlib.sha256(Path(outer["worker_log"]["path"]).read_bytes()).hexdigest()
        == outer["worker_log"]["sha256"]
    )
    assert checks["information"] == {"refs_equal": False}
    assert "passed" not in checks["information"]
    assert checks["binding_unchanged"]
    assert checks["remaining_registered_resources"] == []
    assert checks["cleanup"]["native_exit"] == (4 if recipe == "cleanup_fail" else 0)
    assert checks["cleanup"]["group_absent"]
    assert checks["checks_pass"] == (recipe in {"normal", "cleanup_fail", "summary_fail"})
    for record in [*checks["required"].values(), checks["cleanup"]]:
        assert record["native_exit"] is not None
        assert record["group_absent"] and group_absent(record["pid"])
        path = Path(record["log"]["path"])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["log"]["sha256"]
    if recipe == "nonzero":
        assert checks["required"]["probe"]["native_exit"] == 3
    if recipe == "timeout":
        assert checks["required"]["probe"]["timed_out"]
        assert checks["required"]["probe"]["native_exit"] == -9
        assert "simulation-ready" in Path(checks["required"]["probe"]["log"]["path"]).read_text()
    if recipe == "observer_missing":
        assert checks["required"]["observer"]["native_exit"] == 0
        assert not checks["required"]["observer"]["observation_present"]
    assert summary["status"] == ("FAILED" if recipe == "summary_fail" else "WRITTEN")
    if recipe == "summary_fail":
        assert summary["error_type"] == "KeyError"
        assert checks["checks_pass"] and outer["worker_native_exit"] == 1
    assert directory.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in directory.iterdir())
    assert (
        hashlib.sha256((directory / "checks.json").read_bytes()).hexdigest()
        == outer["checks_receipt"]["sha256"]
    )


def test_unknown_recipe_and_existing_directory_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="fixed recipe"):
        run(tmp_path / "bad", "arbitrary-command")
    with pytest.raises(FileExistsError):
        run(tmp_path, "normal")
