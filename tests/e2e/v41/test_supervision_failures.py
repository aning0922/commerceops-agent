"""Real child failures at identity/registration boundaries; never signal unknown PID."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from pytest import MonkeyPatch

from . import process as owned
from . import runner

pytestmark = pytest.mark.offline


def probe_failure(pid: int) -> str:
    return subprocess.check_output([sys.executable, "-c", "raise SystemExit(6)"], text=True)


def probe_timeout(pid: int) -> str:
    return subprocess.check_output(
        [sys.executable, "-c", "import time;time.sleep(30)"], text=True, timeout=0.02
    )


@pytest.mark.parametrize("fault", [probe_failure, probe_timeout])
def test_identity_failure_after_popen_still_reaps(
    tmp_path: Path, monkeypatch: MonkeyPatch, fault: Any
) -> None:
    monkeypatch.setattr(owned, "identity", fault)

    def forbidden(*args: object) -> None:
        pytest.fail("must not signal an unverified group")

    monkeypatch.setattr(os, "killpg", forbidden)
    result = owned.command(tmp_path, "required", "sleep", 0.3)
    assert result["native_exit"] in {-15, -9}
    assert result["group_absent"] and owned.group_absent(result["pid"])
    assert not result["passed"] and result["errors"]
    assert result["errors"][0]["type"] in {"CalledProcessError", "TimeoutExpired"}


def test_actual_registration_file_failure_still_reaps(tmp_path: Path) -> None:
    (tmp_path / "required.process.json").mkdir()
    result = owned.command(tmp_path, "required", "sleep", 0.3)
    assert result["native_exit"] in {-15, -9}
    assert result["group_absent"] and not result["passed"]
    assert result["errors"][0]["type"] in {"IsADirectoryError", "FileExistsError"}


@pytest.mark.parametrize("fault", [probe_failure, probe_timeout])
def test_registered_identity_unknown_does_not_signal_or_skip_other_entries(
    tmp_path: Path, monkeypatch: MonkeyPatch, fault: Any
) -> None:
    with subprocess.Popen(
        [sys.executable, "-c", "import time;time.sleep(30)"], start_new_session=True
    ) as child:
        registration = tmp_path / "live.process.json"
        registration.write_text(json.dumps({"pid": child.pid, "birth": owned.identity(child.pid)}))
        (tmp_path / "invalid.process.json").write_text("invalid JSON")
        monkeypatch.setattr(owned, "identity", fault)
        signals: list[object] = []
        monkeypatch.setattr(os, "killpg", lambda *args: signals.append(args))
        try:
            inventory = owned.stop_registered(tmp_path)
            assert len(inventory["remaining"]) == 2
            assert all(x["status"] == "UNKNOWN" for x in inventory["remaining"])
            assert not signals and child.poll() is None
        finally:
            child.kill()
            child.wait(timeout=2)
        assert owned.group_absent(child.pid)


def test_exited_group_leader_records_unknown_without_signal(tmp_path: Path) -> None:
    script = (
        "import subprocess,sys; "
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(0.7)']); "
        "print(p.pid,flush=True)"
    )
    with subprocess.Popen(
        [sys.executable, "-c", script], stdout=subprocess.PIPE, start_new_session=True
    ) as leader:
        assert leader.stdout is not None
        descendant = int(leader.stdout.readline())
        (tmp_path / "leader.process.json").write_text(
            json.dumps({"pid": leader.pid, "birth": "owned-original"})
        )
        assert leader.wait(timeout=2) == 0
        inventory = owned.stop_registered(tmp_path)
        assert inventory["remaining"][0]["pid"] == leader.pid
        assert inventory["remaining"][0]["status"] == "UNKNOWN"
        assert inventory["observations"][0]["type"] == "CalledProcessError"
        # The fixed bounded descendant ends naturally; no unverified group is signalled.
        until = time.monotonic() + 3
        while not owned.group_absent(leader.pid) and time.monotonic() < until:
            time.sleep(0.02)
        assert owned.group_absent(leader.pid), descendant


def test_outer_persists_real_worker_native_when_inventory_raises(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    def broken(directory: Path) -> dict[str, Any]:
        probe_failure(os.getpid())
        raise AssertionError("unreachable")

    monkeypatch.setattr(runner, "stop_registered", broken)
    directory = tmp_path / "new-run"
    result = runner.run(directory, "normal")
    assert result["worker_native_exit"] == 0 and result["worker_reaped"]
    assert result["requested_outer_exit"] == 1
    assert result["remaining_registered_resources"][0]["status"] == "UNKNOWN"
    saved = json.loads((directory / "outer.json").read_text())
    assert saved == result
    assert saved["cleanup_observations"][0]["type"] == "CalledProcessError"
    assert json.loads((directory / "checks.json").read_text())["checks_pass"]
