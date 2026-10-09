"""停止控制流 fake 回归：观察错误不得漏 TERM/KILL/OSwait，未知不得报确认。"""

import io
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import cast

import pytest

from scripts import pg_diagnostic
from scripts.pg_diag_shutdown import container_stop, finish, remaining

pytestmark = pytest.mark.offline


def test_expired_entry_creates_no_resources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(pg_diagnostic, "ROOT", tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "pg_diagnostic",
            "--deadline",
            "2000-01-01T00:00:00+00:00",
            "--round",
            "1",
            "--session",
            "followup",
        ],
    )
    with pytest.raises(SystemExit):
        pg_diagnostic.main()
    assert list(tmp_path.iterdir()) == []


class Process:
    pid = 4321

    def __init__(self, calls: list[str], *, hang: bool = False):
        self.calls = calls
        self.hang = hang
        self.returncode: int | None = None
        self.stdout = io.StringIO()

    def wait(self, *, timeout: float) -> int:
        self.calls.append("wait")
        if self.hang:
            self.hang = False
            raise subprocess.TimeoutExpired("fake", timeout)
        self.returncode = -9
        return self.returncode


class Reader:
    def __init__(self, *, alive: bool = False):
        self.alive = alive

    def join(self, *, timeout: float) -> None:
        pass

    def is_alive(self) -> bool:
        return self.alive


@pytest.mark.parametrize("failure", [RuntimeError, ValueError, subprocess.TimeoutExpired])
def test_observation_error_still_terminates_group_and_waits(
    monkeypatch: pytest.MonkeyPatch,
    failure: type[Exception],
) -> None:
    calls: list[str] = []

    def kill(pid: int, sig: int) -> None:
        assert pid == 4321
        calls.append("term" if sig == signal.SIGTERM else "kill")

    monkeypatch.setattr("scripts.pg_diag_shutdown.os.killpg", kill)

    def observe() -> bool:
        if failure is subprocess.TimeoutExpired:
            raise subprocess.TimeoutExpired("fake", 1)
        raise failure("fake observation")

    proc = Process(calls, hang=True)
    result = finish(
        cast(subprocess.Popen[str], proc),
        cast(threading.Thread, Reader()),
        time.monotonic() + 20,
        observe,
        lambda record: None,
    )
    assert calls == ["term", "wait", "kill", "wait"]
    assert result.cli_confirmed and result.reader_confirmed
    assert not result.observation_confirmed and not result.confirmed
    assert proc.stdout.closed


def test_reader_not_finished_does_not_close_or_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scripts.pg_diag_shutdown.os.killpg", lambda pid, sig: None)
    proc = Process([])
    result = finish(
        cast(subprocess.Popen[str], proc),
        cast(threading.Thread, Reader(alive=True)),
        time.monotonic() + 20,
        lambda: True,
        lambda record: None,
    )
    assert result.cli_confirmed and not result.reader_confirmed and not result.confirmed
    assert not proc.stdout.closed


def test_expired_absolute_deadline_does_not_restart_budget() -> None:
    with pytest.raises(TimeoutError):
        remaining(time.monotonic() - 1, 60)


def test_record_failure_does_not_skip_kill_or_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "scripts.pg_diag_shutdown.os.killpg",
        lambda pid, sig: calls.append("term" if sig == signal.SIGTERM else "kill"),
    )

    def record(data: dict[str, object]) -> None:
        raise OSError("fake evidence sink failure")

    result = finish(
        cast(subprocess.Popen[str], Process(calls, hang=True)),
        cast(threading.Thread, Reader()),
        time.monotonic() + 20,
        lambda: True,
        record,
    )
    assert calls == ["term", "wait", "kill", "wait"]
    assert result.cli_confirmed and result.reader_confirmed and not result.confirmed


def test_kill_race_still_performs_os_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def kill(pid: int, sig: int) -> None:
        calls.append("term" if sig == signal.SIGTERM else "kill")
        if sig == signal.SIGKILL:
            raise ProcessLookupError("fake already exited")

    monkeypatch.setattr("scripts.pg_diag_shutdown.os.killpg", kill)
    result = finish(
        cast(subprocess.Popen[str], Process(calls, hang=True)),
        cast(threading.Thread, Reader()),
        time.monotonic() + 20,
        lambda: True,
        lambda record: None,
    )
    assert calls == ["term", "wait", "kill", "wait"]
    assert result.confirmed


@pytest.mark.parametrize("case", ["foreign", "inspect_error", "running", "stopped", "wait_failed"])
def test_container_confirmation_requires_owner_and_successful_wait(case: str) -> None:
    commands: list[str] = []
    states = iter(["true", "true", "false"] if case == "running" else ["false", "false"])

    def capture(command: list[str], seconds: float) -> subprocess.CompletedProcess[str]:
        commands.append(command[1])
        if command[1] == "inspect" and "com.docker.compose.project" in command[3]:
            if case == "inspect_error":
                raise RuntimeError("fake inspect failure")
            return subprocess.CompletedProcess(
                command, 0, "foreign" if case == "foreign" else "p123-own", ""
            )
        if command[1] == "inspect":
            return subprocess.CompletedProcess(command, 0, next(states), "")
        if command[1] == "wait":
            return subprocess.CompletedProcess(
                command, 1 if case == "wait_failed" else 0, "137", ""
            )
        return subprocess.CompletedProcess(command, 0, "", "")

    if case == "inspect_error":
        with pytest.raises(RuntimeError):
            container_stop("owned", "p123-own", capture, lambda record: None)
    else:
        result = container_stop("owned", "p123-own", capture, lambda record: None)
        assert result is (case in ("running", "stopped"))
    if case in ("foreign", "inspect_error"):
        assert commands == ["inspect"]
    elif case == "running":
        assert commands == ["inspect", "inspect", "stop", "inspect", "kill", "wait", "inspect"]
    else:
        assert "stop" not in commands and "kill" not in commands
