"""Pure/time/process-only contracts; never PG/API/Web or HTTP Gate evidence."""

import os
import sys
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from .http_probe import loopback_origin
from .supervisor import Budget, Supervisor

pytestmark = pytest.mark.offline


def budget() -> Budget:
    now = datetime.now(UTC)
    return Budget.bind(now - timedelta(seconds=1), now + timedelta(minutes=5))


@pytest.mark.parametrize(
    "origin",
    [
        "https://example.com",
        "http://localhost:18080",
        "http://127.0.0.1",
        "http://127.0.0.1:80",
        "http://user:password@127.0.0.1:18080",
        "http://127.0.0.1:18080/api/v4",
        "http://127.0.0.1:18080?token=private",
        "http://127.0.0.1:18080#fragment",
    ],
)
def test_external_or_ambiguous_origins_refused(origin: str) -> None:
    with pytest.raises(ValueError):
        loopback_origin(origin)


def test_window_refuses_future_expired_naive_and_missing_reserve() -> None:
    now = datetime.now(UTC)
    cases = [
        (now + timedelta(seconds=1), now + timedelta(minutes=5), 180),
        (now - timedelta(minutes=5), now - timedelta(seconds=1), 180),
        (now.replace(tzinfo=None), now + timedelta(minutes=5), 180),
        (now, now + timedelta(minutes=5), 0),
        (now, now + timedelta(seconds=180), 180),
    ]
    for start, end, reserve in cases:
        with pytest.raises(ValueError):
            Budget.bind(start, end, reserve)


def test_monotonic_ceiling_cannot_be_extended_by_wall_clock() -> None:
    expired = replace(budget(), monotonic_deadline=time.monotonic() - 1)
    with pytest.raises(TimeoutError):
        expired.timeout(1, cleanup=True)


def test_native_nonzero_reaped_and_unknown_handle_refused(tmp_path: Path) -> None:
    owner = Supervisor(budget(), tmp_path, tmp_path / "evidence")
    child = owner.start("probe", (sys.executable, "-c", "raise SystemExit(7)"), {})
    try:
        assert owner.wait(child, 3) == 7
        with pytest.raises(ValueError, match="unowned"):
            owner.stop(replace(child))
        assert owner.stop_writers() == {"probe": 7}
        assert child.stopped and child.process.poll() == 7
        assert (tmp_path / "evidence/probe.raw.log").stat().st_mode & 0o777 == 0o600
        with pytest.raises(ValueError, match="cleanup"):
            owner.start("api", (sys.executable, "-c", "pass"), {})
    finally:
        owner.stop_writers()
        owner.close_pg()


def test_term_ignored_escalates_kill_and_reaps(tmp_path: Path) -> None:
    owner = Supervisor(budget(), tmp_path, tmp_path / "evidence")
    script = (
        "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        "print('ready',flush=True); time.sleep(60)"
    )
    child = owner.start("probe", (sys.executable, "-c", script), {})
    try:
        until = time.monotonic() + 2
        while "ready" not in (tmp_path / "evidence/probe.raw.log").read_text():
            if time.monotonic() > until:
                pytest.fail("test child did not become ready")
            time.sleep(0.01)
        assert owner.stop(child) == -9
        assert child.stopped and child.process.poll() == -9
        assert owner.stop(child) == -9  # Idempotent: do not signal a recycled PID.
    finally:
        owner.stop_writers()
        owner.close_pg()


def test_only_explicit_environment_and_no_auto_restart(tmp_path: Path) -> None:
    owner = Supervisor(budget(), tmp_path, tmp_path / "evidence")
    script = "import os; assert 'HOME' not in os.environ; print(os.environ['V4_QA_TEST'])"
    child = owner.start("probe", (sys.executable, "-c", script), {"V4_QA_TEST": "owned"})
    try:
        assert owner.wait(child, 3) == 0
        assert (tmp_path / "evidence/probe.raw.log").read_text().strip() == "owned"
        with pytest.raises(ValueError, match="restart"):
            owner.start("probe", (sys.executable, "-c", "pass"), {})
    finally:
        owner.stop_writers()
        owner.close_pg()


def test_launch_failure_preserves_log_and_does_not_adopt_process(tmp_path: Path) -> None:
    owner = Supervisor(budget(), tmp_path, tmp_path / "evidence")
    with pytest.raises(FileNotFoundError):
        owner.start("probe", (str(tmp_path / "no-such-executable"),), {})
    assert owner.owned == []
    assert (tmp_path / "evidence/probe.raw.log").exists()


def test_cleanup_continues_after_one_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = Supervisor(budget(), tmp_path, tmp_path / "evidence")
    one = owner.start("probe", (sys.executable, "-c", "pass"), {})
    two = owner.start("api", (sys.executable, "-c", "pass"), {})
    calls: list[str] = []
    original = owner.stop

    def stop(child: object) -> int:
        if child is two:
            calls.append("api")
            raise OSError("test stop failure")
        calls.append("probe")
        return original(one)

    try:
        with monkeypatch.context() as patch:
            patch.setattr(owner, "stop", stop)
            with pytest.raises(RuntimeError, match="api"):
                owner.stop_writers()
        assert calls == ["api", "probe"]
    finally:
        owner.stop_writers()
        owner.close_pg()


def test_pg_close_requires_writer_group_cleanup(tmp_path: Path) -> None:
    owner = Supervisor(budget(), tmp_path, tmp_path / "evidence")
    child = owner.start("probe", (sys.executable, "-c", "pass"), {})
    try:
        owner.wait(child, 3)
        with pytest.raises(RuntimeError, match="group"):
            owner.close_pg()
    finally:
        owner.stop_writers()
        owner.close_pg()


def test_watchdog_stops_owned_child_without_wait_call(tmp_path: Path) -> None:
    # Compressed internal clock only for the harmless process unit contract.
    compressed = replace(budget(), reserve=0.1, monotonic_deadline=time.monotonic() + 5.2)
    owner = Supervisor(compressed, tmp_path, tmp_path / "evidence")
    child = owner.start("probe", (sys.executable, "-c", "import time;time.sleep(60)"), {})
    try:
        assert child.process.wait(timeout=3) < 0
        # Watchdog owns reaping/state; join its bounded final cleanup callback.
        for timer in owner._timers:
            if timer.interval < 1:
                timer.join(timeout=2)
        assert child.stopped
        assert owner.watchdog_errors == []
        with pytest.raises(ProcessLookupError):
            os.killpg(child.process.pid, 0)
    finally:
        owner.stop_writers()
        owner.close_pg()


def test_exited_leader_does_not_leave_descendant_writer(tmp_path: Path) -> None:
    owner = Supervisor(budget(), tmp_path, tmp_path / "evidence")
    marker = tmp_path / "must-not-be-written"
    grandchild = (
        "import sys,time;from pathlib import Path;time.sleep(0.5);"
        "Path(sys.argv[1]).write_text('late writer')"
    )
    leader = "import subprocess,sys;subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2]])"
    child = owner.start("probe", (sys.executable, "-c", leader, grandchild, str(marker)), {})
    try:
        assert owner.wait(child, 3) == 0
        owner.stop_writers()
        time.sleep(0.7)
        assert not marker.exists()
    finally:
        owner.stop_writers()
        owner.close_pg()
