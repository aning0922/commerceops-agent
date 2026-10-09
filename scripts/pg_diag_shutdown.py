"""Issue23 诊断进程的停止证据；不授权任何业务 Worker 恢复。"""

import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

Record = Callable[[dict[str, object]], None]
Capture = Callable[[list[str], float], subprocess.CompletedProcess[str]]


def remaining(deadline: float, cap: float) -> float:
    value = min(cap, deadline - time.monotonic())
    if value <= 0:
        raise TimeoutError("absolute diagnostic deadline expired")
    return value


def container_stop(name: str, project: str, capture: Capture, record: Record) -> bool:
    checked = capture(
        [
            "docker",
            "inspect",
            "--format",
            '{{index .Config.Labels "com.docker.compose.project"}}',
            name,
        ],
        5,
    )
    if checked.returncode or checked.stdout.strip() != project:
        record({"event": "container_unconfirmed", "container": name, "reason": "label_unverified"})
        return False

    def running() -> bool:
        state = capture(["docker", "inspect", "--format", "{{.State.Running}}", name], 5)
        if state.returncode or state.stdout.strip() not in ("true", "false"):
            raise RuntimeError("container state unconfirmed")
        return state.stdout.strip() == "true"

    if running():
        stopped = capture(["docker", "stop", "-t", "3", name], 8)
        record({"event": "container_stop", "container": name, "exit": stopped.returncode})
        if running():
            killed = capture(["docker", "kill", name], 5)
            record({"event": "container_kill", "container": name, "exit": killed.returncode})
    waited = capture(["docker", "wait", name], 8)
    confirmed = waited.returncode == 0 and waited.stdout.strip().lstrip("-").isdigit()
    if confirmed:
        confirmed = not running()
    record(
        {
            "event": "container_wait",
            "container": name,
            "confirmed": confirmed,
            "exit": waited.returncode,
            "container_exit": int(waited.stdout.strip()) if confirmed else None,
        }
    )
    return confirmed


@dataclass(frozen=True)
class StopEvidence:
    cli_confirmed: bool
    reader_confirmed: bool
    observation_confirmed: bool

    @property
    def confirmed(self) -> bool:
        return self.cli_confirmed and self.reader_confirmed and self.observation_confirmed


def finish(
    process: subprocess.Popen[str],
    reader: threading.Thread,
    deadline: float,
    observe: Callable[[], bool],
    record: Record,
) -> StopEvidence:
    observed = cli = reader_done = False
    recorded = True

    def note(data: dict[str, object]) -> None:
        nonlocal recorded
        try:
            record(data)
        except Exception:
            # 记录失败不能跳过终止；无法留证时不能报告总体确认。
            recorded = False

    try:
        observed = observe()
    except Exception as error:
        note({"event": "observation_failed", "code": type(error).__name__})
    finally:
        try:
            # returncode 已设置表示本 Popen 已 wait/reap，数字 PID/PGID 可复用。
            # 正常完成或观察期间恰好完成时只记录既有结果，不再对该数字发信号。
            # 本 supervisor 是该 Popen 唯一 reaper；reader 只读取 stdout。
            live = process.returncode is None and process.poll() is None
            if live:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    note({"event": "cli_term", "pid": process.pid})
                except ProcessLookupError:
                    note({"event": "cli_term", "pid": process.pid, "already_absent": True})
                try:
                    process.wait(timeout=remaining(deadline, 3))
                except subprocess.TimeoutExpired:
                    # poll 可 reap 已结束进程；只有仍未完成的自有 child 才发 KILL。
                    if process.returncode is None and process.poll() is None:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                            note({"event": "cli_kill", "pid": process.pid})
                        except ProcessLookupError:
                            note({"event": "cli_kill", "pid": process.pid, "already_absent": True})
                    process.wait(timeout=remaining(deadline, 5))
            else:
                note({"event": "cli_existing_wait", "pid": process.pid, "exit": process.returncode})
            cli = process.returncode is not None
            note(
                {
                    "event": "cli_os_wait",
                    "pid": process.pid,
                    "confirmed": cli,
                    "exit": process.returncode,
                }
            )
        except Exception as error:
            note({"event": "cli_unconfirmed", "pid": process.pid, "code": type(error).__name__})
        finally:
            try:
                reader.join(timeout=remaining(deadline, 3))
                reader_done = not reader.is_alive()
                if reader_done and process.stdout is not None:
                    process.stdout.close()
                note({"event": "reader_end", "confirmed": reader_done})
            except Exception as error:
                note({"event": "reader_unconfirmed", "code": type(error).__name__})
    return StopEvidence(cli, reader_done, observed and recorded)
