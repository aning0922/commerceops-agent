"""P204隔离Worker子进程/OS终止证明测试工具。"""

import json
import os
import queue
import subprocess
import sys
import threading
import time
from typing import Any

from tests.inventory_support import InventoryFixture


class ExplanationProcess:
    def __init__(self, f: InventoryFixture, barrier: str = ""):
        env = os.environ.copy()
        s = f.app
        env.update(
            COMMERCEOPS_DB_HOST=s.host,
            COMMERCEOPS_DB_PORT=str(s.port),
            COMMERCEOPS_DB_NAME=s.name,
            COMMERCEOPS_DB_USER=s.user,
            COMMERCEOPS_DB_PASSWORD_FILE=str(s.password_file),
            COMMERCEOPS_MODE="test",
            P204_BARRIER=barrier,
            LANGSMITH_TRACING="false",
        )
        self.process = subprocess.Popen(
            [sys.executable, "-m", "tests.p204_process", str(f.data.organization)],
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self.events: queue.Queue[dict[str, Any]] = queue.Queue()
        self.seen: list[dict[str, Any]] = []
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self) -> None:
        assert self.process.stdout
        for line in self.process.stdout:
            row = json.loads(line)
            self.seen.append(row)
            self.events.put(row)

    def until(self, event: str) -> dict[str, Any]:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            row = self.events.get(timeout=max(0.01, deadline - time.monotonic()))
            assert row["event"] != "failed", row
            if row["event"] == event:
                return row
        raise AssertionError("owned process event timed out")

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=15)
        self.thread.join(timeout=5)
        for stream in (self.process.stdin, self.process.stdout):
            if stream:
                stream.close()
