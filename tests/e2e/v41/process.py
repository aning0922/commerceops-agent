"""Bounded, fixed local simulation children; no arbitrary executable interface."""

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
MODES = frozenset({"ok", "fail", "sleep", "observer", "observer_missing", "cleanup_fail"})


def stamp() -> str:
    return datetime.now(UTC).isoformat()


def group_absent(pid: int) -> bool:
    result = subprocess.run(
        ["/bin/ps", "-g", str(pid), "-o", "stat="],
        capture_output=True,
        env={},
        timeout=1,
        check=False,
    )
    return result.returncode == 1 and not result.stdout.strip() and not result.stderr.strip()


def identity(pid: int) -> str:
    return subprocess.check_output(
        ["/bin/ps", "-p", str(pid), "-o", "lstart="], text=True, timeout=1
    ).strip()


def stop_registered(directory: Path) -> list[int]:
    remaining = []
    for path in directory.glob("*.process.json"):
        item = json.loads(path.read_text())
        pid = item["pid"]
        if group_absent(pid):
            continue
        # Never signal a reused PID or adopt an unregistered group.
        if identity(pid) != item["birth"]:
            remaining.append(pid)
            continue
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(pid, sig)
            except ProcessLookupError:
                pass
            until = time.monotonic() + 0.2
            while not group_absent(pid) and time.monotonic() < until:
                time.sleep(0.01)
            if group_absent(pid):
                break
        if not group_absent(pid):
            remaining.append(pid)
    return remaining


def command(directory: Path, label: str, mode: str, cap: float) -> dict[str, Any]:
    if mode not in MODES or label not in {"required", "observer", "cleanup"} or not 0 < cap <= 5:
        raise ValueError("fixed simulation command required")
    path = directory / (label + ".private.log")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    argv = (sys.executable, "-m", "tests.e2e.v41.simulated_child", mode, str(directory))
    start = time.monotonic()
    record: dict[str, Any] = {
        "argv": list(argv),
        "started_utc": stamp(),
        "native_exit": None,
        "timed_out": False,
        "pid": None,
        "group_absent": False,
    }
    with os.fdopen(fd, "wb") as log:
        process = subprocess.Popen(
            argv,
            cwd=ROOT,
            env={},
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        record["pid"] = process.pid
        # Child can exit before ps; use a live process handle registration before wait.
        try:
            birth = identity(process.pid)
        except subprocess.CalledProcessError:
            birth = "EXITED_BEFORE_IDENTITY"
        registration = directory / (label + ".process.json")
        registered = os.open(registration, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(registered, "w") as stream:
            json.dump({"pid": process.pid, "birth": birth}, stream)
        try:
            record["native_exit"] = process.wait(timeout=cap)
        except subprocess.TimeoutExpired:
            record["timed_out"] = True
        finally:
            # Always stop this created group, including descendants after leader exit.
            for sig in (signal.SIGTERM, signal.SIGKILL):
                if group_absent(process.pid):
                    break
                try:
                    os.killpg(process.pid, sig)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    pass
            record["native_exit"] = process.wait(timeout=1)
            record["group_absent"] = group_absent(process.pid)
    record.update(
        finished_utc=stamp(),
        elapsed_seconds=time.monotonic() - start,
        log={"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
    )
    record["passed"] = (
        record["native_exit"] == 0 and not record["timed_out"] and record["group_absent"]
    )
    return record
