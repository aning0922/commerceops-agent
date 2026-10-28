"""Real local subprocess failure, timeout and interruption; no infrastructure."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from pytest import MonkeyPatch as Patch

from scripts import verify

pytestmark = pytest.mark.offline


def test_changed_path_collection_includes_all_git_states(
    tmp_path: Path, monkeypatch: Patch
) -> None:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=tmp_path, check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init", "-q")
    git("config", "user.name", "Offline Test")
    git("config", "user.email", "offline@example.invalid")
    for name in ("cancelled.py", "committed.py", "staged.py", "unstaged.py", "deleted.py"):
        (tmp_path / name).write_text("x = 1\n")
    git("add", ".")
    git("commit", "-qm", "synthetic base")
    base = git("rev-parse", "HEAD")
    (tmp_path / "committed.py").write_text("x = 2\n")
    git("add", "committed.py")
    git("commit", "-qm", "synthetic change")
    (tmp_path / "staged.py").write_text("x = 2\n")
    git("add", "staged.py")
    (tmp_path / "unstaged.py").write_text("x = 2\n")
    # Staged and unstaged changes can cancel in base-to-worktree comparison.
    (tmp_path / "cancelled.py").write_text("def invalid(:\n")
    git("add", "cancelled.py")
    (tmp_path / "cancelled.py").write_text("x = 1\n")
    (tmp_path / "deleted.py").unlink()
    (tmp_path / "untracked.py").write_text("x = 1\n")
    monkeypatch.setattr(verify, "ROOT", tmp_path)
    assert verify.changed_paths(base) == [
        "cancelled.py",
        "committed.py",
        "deleted.py",
        "staged.py",
        "unstaged.py",
        "untracked.py",
    ]


def test_risk_and_impacted_unknown_fail_closed() -> None:
    assert verify.full_reasons(["backend/src/commerceops/new.py"], "low")
    assert verify.full_reasons(["docs/new.md"], "unknown")
    assert verify.full_reasons(["tests/test_harness_verify.py"], "low")
    assert verify.full_reasons([".github/workflows/quality.yml"], "low")
    checks, unmapped = verify.plan("impacted", ["backend/src/commerceops/new.py"])
    assert unmapped
    assert checks[-1].status == "NOT_RUN"
    assert checks[-1].command == []
    assert any(
        check.command[-3:] == ["-m", "scripts.scan_secrets", "--current-only"] for check in checks
    )


def test_real_child_pass_failure_and_timeout() -> None:
    success = verify.CheckResult("success", [sys.executable, "-c", "print('safe')"])
    verify.run_check(success, 2)
    assert success.status == "PASSED" and success.exit_code == 0
    failed = verify.CheckResult("failure", [sys.executable, "-c", "raise SystemExit(7)"])
    verify.run_check(failed, 2)
    assert failed.status == "FAILED" and failed.exit_code == 7
    killed = verify.CheckResult(
        "killed child",
        [sys.executable, "-c", "import os,signal; os.kill(os.getpid(),signal.SIGTERM)"],
    )
    verify.run_check(killed, 2)
    assert killed.status == "INTERRUPTED" and killed.exit_code == 143
    timeout = verify.CheckResult("timeout", [sys.executable, "-c", "import time; time.sleep(30)"])
    verify.run_check(timeout, 1)
    assert timeout.status == "FAILED" and timeout.exit_code == 124
    assert 1 <= timeout.wall_seconds < 5


def test_syntax_invalid_json_python_and_symlink(tmp_path: Path, monkeypatch: Patch) -> None:
    (tmp_path / "broken.py").write_text("def broken(:\n")
    (tmp_path / "docs/harness").mkdir(parents=True)
    (tmp_path / "docs/harness/broken.json").write_text("{")
    (tmp_path / "linked.py").symlink_to(tmp_path / "broken.py")
    monkeypatch.setattr(verify, "ROOT", tmp_path)
    assert len(verify.syntax_checks(["broken.py", "docs/harness/broken.json", "linked.py"])) == 3
    with pytest.raises(ValueError):
        verify.syntax_checks(["../outside.py"])


def test_real_signal_reaps_owned_child(tmp_path: Path) -> None:
    pidfile = tmp_path / "child-pid"
    helper = tmp_path / "signal_helper.py"
    child_code = (
        f"import os,time; open({str(pidfile)!r},'w').write(str(os.getpid())); time.sleep(30)"
    )
    helper.write_text(
        "import json,signal,sys\n"
        "from dataclasses import asdict\n"
        "from scripts.verify import CheckResult,run_check,interrupt,Interrupted\n"
        "signal.signal(signal.SIGTERM,interrupt)\n"
        f"check=CheckResult('signal',[sys.executable,'-c',{child_code!r}])\n"
        "try:\n run_check(check,60)\n"
        "except Interrupted:\n print(json.dumps(asdict(check)))\n sys.exit(143)\n"
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(verify.ROOT)
    process = subprocess.Popen(
        [sys.executable, str(helper)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )
    try:
        deadline = time.monotonic() + 5
        while not pidfile.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert pidfile.exists()
        child_pid = int(pidfile.read_text())
        process.send_signal(signal.SIGTERM)
        output, error = process.communicate(timeout=5)
        assert process.returncode == 143, error.decode()
        report = json.loads(output)
        assert report["status"] == "INTERRUPTED"
        assert report["exit_code"] == 143
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
