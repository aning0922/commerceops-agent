"""薄demo结案只认同一个own child；真实普通child无SDK/PG，DB证据用明确Fake。"""

import asyncio
import json
import multiprocessing
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from commerceops.infrastructure.worker_lock import (
    TerminationRequired,
    process_namespace,
    require_process_absent,
)
from pytest import MonkeyPatch as Patch

from scripts import m1_offline_demo as demo

pytestmark = pytest.mark.offline


@pytest.mark.parametrize(
    "case",
    [
        "normal",
        "unreaped",
        "nonzero",
        "live_pid",
        "wrong_owner",
        "wrong_org",
        "wrong_namespace",
        "no_stopped",
        "wrong_persistent_pid",
    ],
)
def test_only_clean_reaped_exact_child_can_confirm_original_owner(
    tmp_path: Path,
    monkeypatch: Patch,
    case: str,
) -> None:
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait(timeout=5)
    organization, owner = str(uuid4()), str(uuid4())
    file = tmp_path / "demo-facts.json"
    file.write_text(json.dumps({"organization": organization}))
    file.chmod(0o600)
    receipt = {
        "owner": owner,
        "pid": process.pid,
        "organization": organization,
        "host": socket.gethostname(),
        "pid_namespace": process_namespace(),
    }
    persistent: dict[str, Any] = {key: receipt[key] for key in ("pid", "host", "pid_namespace")}
    expected_pid = process.pid
    if case == "live_pid":
        receipt["pid"] = expected_pid = os.getpid()
        persistent["pid"] = expected_pid
    elif case == "wrong_owner":
        receipt["owner"] = str(uuid4())
    elif case == "wrong_org":
        receipt["organization"] = str(uuid4())
    elif case == "wrong_namespace":
        receipt["pid_namespace"] = "another-namespace"
    elif case == "wrong_persistent_pid":
        persistent["pid"] += 1
    confirmed = []

    class Cursor:
        async def fetchall(self) -> list[dict[str, Any]]:
            return [] if case in ("wrong_owner", "no_stopped") else [{"after_state": persistent}]

    class Database:
        async def __aenter__(self) -> "Database":
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def execute(self, sql: str, args: tuple[Any, ...]) -> Cursor:
            assert "e.action='stopped'" in sql and args[0] == __import__("uuid").UUID(organization)
            return Cursor()

    async def opened(settings: Any) -> Database:
        return Database()

    async def confirm(settings: Any, identifier: str, evidence: str) -> None:
        confirmed.append(identifier)
        assert identifier == owner and evidence == "M1 original child clean stop and OS reap"

    monkeypatch.setattr(demo, "open_async", opened)
    monkeypatch.setattr(demo, "owned_config", lambda *args: SimpleNamespace(database=object()))
    monkeypatch.setattr(demo, "confirm_termination", confirm)
    call = demo.finish_child(
        tmp_path, {}, expected_pid, 75 if case == "nonzero" else 0, case != "unreaped", receipt
    )
    if case == "normal":
        asyncio.run(call)
        assert confirmed == [owner]
    else:
        with pytest.raises(TerminationRequired):
            asyncio.run(call)
        assert confirmed == []


def plain_owned_child(directory: Path, started: Any) -> None:
    stop = False

    def stopped(signum: int, frame: Any) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, stopped)
    signal.signal(signal.SIGINT, stopped)
    started.send(
        {
            "owner": str(uuid4()),
            "pid": os.getpid(),
            "organization": "synthetic",
            "host": socket.gethostname(),
            "pid_namespace": process_namespace(),
        }
    )
    started.close()
    with (directory / "child-pids.txt").open("a") as file:
        file.write(str(os.getpid()) + "\n")
    while not stop:
        time.sleep(0.02)


def test_sigusr1_reaps_first_child_before_only_second_child_and_final_confirmation(
    tmp_path: Path,
    monkeypatch: Patch,
) -> None:
    # 实际普通process/signal/join，不SDK/PG；fork仅测试继承Fake，不改生产spawn。
    ctx = multiprocessing.get_context("fork")
    monkeypatch.setattr(multiprocessing, "get_context", lambda _: ctx)
    monkeypatch.setattr(
        demo,
        "request",
        lambda _: {
            "expires_at": (datetime.now(UTC) + timedelta(seconds=20)).isoformat(),
        },
    )
    monkeypatch.setattr(demo, "child", plain_owned_child)
    confirmed = []

    async def finish(
        directory: Path, value: Any, pid: int, exitcode: int, reaped: bool, receipt: Any
    ) -> None:
        assert reaped and exitcode == 0 and receipt["pid"] == pid
        require_process_absent(receipt)
        confirmed.append(pid)

    monkeypatch.setattr(demo, "finish_child", finish)
    errors = []

    def steer() -> None:
        try:
            for count, sig in ((1, signal.SIGUSR1), (2, signal.SIGTERM)):
                end = time.monotonic() + 8
                while time.monotonic() < end:
                    file = tmp_path / "child-pids.txt"
                    pids = file.read_text().splitlines() if file.exists() else []
                    if len(pids) == count:
                        if count == 2:
                            assert len(confirmed) == 1
                        os.kill(os.getpid(), sig)
                        break
                    time.sleep(0.02)
                else:
                    raise AssertionError("owned plain child startup deadline")
        except BaseException as error:
            errors.append(type(error).__name__)
            os.kill(os.getpid(), signal.SIGTERM)

    previous = {
        sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGUSR1)
    }
    thread = threading.Thread(target=steer)
    thread.start()
    try:
        demo.supervise(tmp_path)
    finally:
        thread.join(timeout=10)
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    assert not errors and not thread.is_alive() and len(confirmed) == 2
    assert len(set(confirmed)) == 2
