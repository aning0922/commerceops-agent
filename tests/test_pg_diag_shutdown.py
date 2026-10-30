"""停止控制流 fake 回归：观察错误不得漏 TERM/KILL/OSwait，未知不得报确认。"""

import ast
import io
import json
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, cast

import pytest
import yaml  # type: ignore[import-untyped]  # 已锁定依赖，仅SafeLoader解析。

from scripts import pg_diagnostic
from scripts.pg_diag_shutdown import container_stop, finish, remaining

pytestmark = pytest.mark.offline


def test_rollback_workflow_preserves_gate_and_single_diagnostic_step() -> None:
    data = yaml.safe_load(
        subprocess.check_output(
            [
                "git",
                "show",
                "226917d4dba57bdb2eef54180df97e57510e4169:.github/workflows/quality.yml",
            ],
            cwd=pg_diagnostic.ROOT,
        )
    )
    job = data["jobs"]["quality"]
    assert job["timeout-minutes"] == 45
    assert data["jobs"]["phase3"]["timeout-minutes"] == 50
    assert data["permissions"] == {"contents": "read"}
    # PyYAML YAML1.1 将键 on 解析为True；不改变Actions文件的on字段。
    triggers = data.get("on", data.get(True))
    assert triggers["pull_request"]["types"] == ["opened", "synchronize", "reopened", "edited"]
    steps = job["steps"]
    assert set(data["jobs"]) == {
        "quality",
        "phase3",
        "pg-pair",
        "frontend",
        "n01-web",
        "merge-gate",
    }
    foundation = [
        (name, step)
        for name, value in data["jobs"].items()
        for step in value["steps"]
        if "python -m scripts.check\n" in step.get("run", "")
    ]
    assert len(foundation) == 1 and foundation[0][0] == "n01-web"
    assert "run_before_cleanup uv run --frozen python -m scripts.check\n" in foundation[0][1]["run"]
    assert "if" not in foundation[0][1] and "continue-on-error" not in foundation[0][1]
    assert all("scripts.check" not in step.get("run", "") for step in steps)
    assert data["jobs"]["pg-pair"]["needs"] == ["quality", "phase3"]
    runs = [step for step in steps if "scripts.pg_diagnostic" in step.get("run", "")]
    assert len(runs) == 1
    command = runs[0]["run"]
    for flag in (
        "--session ci",
        "--round 1",
        "--combined",
        "--full-smoke",
        "--no-child-trace",
        '--deadline "$(cat .audit/ci-deadline)"',
    ):
        assert flag in command


@pytest.mark.parametrize("job_name,minutes", [("quality", 43), ("phase3", 48)])
def test_rollback_workflow_registers_deadline_before_install_and_valid_python(
    job_name: str,
    minutes: int,
) -> None:
    data = yaml.safe_load(
        subprocess.check_output(
            [
                "git",
                "show",
                "226917d4dba57bdb2eef54180df97e57510e4169:.github/workflows/quality.yml",
            ],
            cwd=pg_diagnostic.ROOT,
        )
    )
    steps = data["jobs"][job_name]["steps"]
    deadline_index = next(
        i for i, s in enumerate(steps) if s.get("name") == "Register absolute diagnostic deadline"
    )
    install_index = next(
        i for i, s in enumerate(steps) if s.get("name") == "Install locked Python environment"
    )
    assert deadline_index == 1 and deadline_index < install_index
    lines = steps[deadline_index]["run"].splitlines()
    assert lines[0] == "python3 - <<'PY'" and lines[-1] == "PY"
    source = "\n".join(lines[1:-1])
    ast.parse(source)
    assert f"timedelta(minutes={minutes})" in source and "datetime.now(timezone.utc)" in source


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

    def poll(self) -> int | None:
        return self.returncode

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


@pytest.mark.parametrize("observation", ["success", "exception", "unconfirmed"])
@pytest.mark.parametrize("reader_alive", [False, True])
def test_completed_reaped_process_never_signals_reusable_pgid(
    monkeypatch: pytest.MonkeyPatch,
    observation: str,
    reader_alive: bool,
) -> None:
    calls: list[str] = []

    def forbidden(pid: int, sig: int) -> None:
        calls.append("signal")
        raise AssertionError("reaped PGID must never be signalled")

    monkeypatch.setattr("scripts.pg_diag_shutdown.os.killpg", forbidden)
    process = Process(calls)
    process.returncode = 0

    def observe() -> bool:
        if observation == "exception":
            raise RuntimeError("fake observation failed")
        return observation == "success"

    result = finish(
        cast(subprocess.Popen[str], process),
        cast(threading.Thread, Reader(alive=reader_alive)),
        time.monotonic() + 20,
        observe,
        lambda record: None,
    )
    assert calls == []  # 既有 wait 结果不重复wait，更不能killpg。
    assert result.cli_confirmed
    assert result.reader_confirmed is not reader_alive
    assert result.observation_confirmed is (observation == "success")
    assert result.confirmed is (observation == "success" and not reader_alive)
    assert process.stdout.closed is not reader_alive


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


@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "foreign",
        "running",
        "pid",
        "missing",
        "partial",
        "timeout",
        "duplicate-name",
        "duplicate-id",
        "slow-removal",
        "removal-timeout",
        "expired-removal",
    ],
)
def test_registered_cleanup_batch_requires_every_owner_stopped_state_and_removal(
    case: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    names = ["p123-own-" + str(n) for n in range(29)]
    records: list[dict[str, Any]] = [
        {
            "Name": "/" + name,
            "Id": format(n + 1, "064x"),
            "Config": {"Labels": {"com.docker.compose.project": "p123-own"}},
            "State": {"Running": False, "Pid": 0, "Status": "exited"},
        }
        for n, name in enumerate(names)
    ]
    if case == "foreign":
        records[-1]["Config"]["Labels"]["com.docker.compose.project"] = "foreign"
    elif case == "running":
        records[-1]["State"]["Running"] = True
    elif case == "pid":
        records[-1]["State"]["Pid"] = 1
    elif case == "missing":
        records.pop()
    elif case == "duplicate-name":
        records[-1]["Name"] = names[0]
    elif case == "duplicate-id":
        records[-1]["Id"] = records[0]["Id"]
    commands: list[list[str]] = []
    stages: list[tuple[str, int, int]] = []
    clock = [100.0]
    cleanup_deadline = 160.0
    limits: list[float] = []
    monkeypatch.setattr("scripts.pg_diag_shutdown.time.monotonic", lambda: clock[0])

    def capture(command: list[str], seconds: float) -> subprocess.CompletedProcess[str]:
        limit = remaining(cleanup_deadline, seconds)
        commands.append(command)
        limits.append(limit)
        if case == "timeout":
            raise subprocess.TimeoutExpired("redacted", limit)
        if command[1] == "inspect":
            assert seconds == 5
            clock[0] += 0.036
            return subprocess.CompletedProcess(command, 0, json.dumps(records), "")
        assert seconds == 60
        assert command == ["docker", "rm", *[r["Id"] for r in records]]
        if case in {"slow-removal", "removal-timeout"}:
            duration = 6.0 if case == "slow-removal" else 61.0
            clock[0] += min(duration, limit)
            if duration > limit:
                raise subprocess.TimeoutExpired("redacted", limit)
        ids = [r["Id"] for r in records]
        return subprocess.CompletedProcess(
            command,
            1 if case == "partial" else 0,
            "\n".join(ids[:3] if case == "partial" else ids),
            "",
        )

    def stage(name: str, verified: int, removed: int) -> None:
        stages.append((name, verified, removed))
        if case == "expired-removal" and name == "remove-registered":
            clock[0] = cleanup_deadline

    if case in {"valid", "slow-removal"}:
        assert pg_diagnostic.cleanup_registered_containers(names, "p123-own", capture, stage) == 29
        assert len(commands) == 2 and stages[-1] == ("removed-registered", 29, 29)
        assert limits == [5, pytest.approx(59.964)]
        if case == "slow-removal":
            assert clock[0] == pytest.approx(106.036) and clock[0] < cleanup_deadline
    else:
        error = (
            subprocess.TimeoutExpired
            if case in {"timeout", "removal-timeout"}
            else TimeoutError
            if case == "expired-removal"
            else RuntimeError
        )
        with pytest.raises(error):
            pg_diagnostic.cleanup_registered_containers(names, "p123-own", capture, stage)
        assert len(commands) == (2 if case in {"partial", "removal-timeout"} else 1)
        if case == "partial":
            assert stages[-1] == ("partial-removal", 29, 3)
        elif case in {"removal-timeout", "expired-removal"}:
            assert stages[-1] == ("remove-registered", 29, 0)
            assert clock[0] == cleanup_deadline
    assert all("--force" not in c and "-f" not in c and "-v" not in c for c in commands)


def test_registered_cleanup_empty_and_duplicate_names_never_delete() -> None:
    def forbidden(command: list[str], seconds: float) -> subprocess.CompletedProcess[str]:
        raise AssertionError("no command required")

    assert (
        pg_diagnostic.cleanup_registered_containers([], "p123-own", forbidden, lambda *a: None) == 0
    )
    with pytest.raises(RuntimeError):
        pg_diagnostic.cleanup_registered_containers(
            ["same", "same"], "p123-own", forbidden, lambda *a: None
        )
