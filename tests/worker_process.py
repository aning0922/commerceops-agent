"""受控 test runner 子进程；stdin barrier，stdout 只输出技术标识，无真实图。"""

import argparse
import asyncio
import json
import os
import signal
import sys
from uuid import UUID

from commerceops.application.runner import RunRequest, RunResult
from commerceops.infrastructure.database import DatabaseSettings
from commerceops.infrastructure.worker import UnsafeShutdown, Worker
from commerceops.infrastructure.worker_lock import WorkerSession


def emit(event: str, **data: object) -> None:
    print(json.dumps({"event": event, **data}), flush=True)


class BarrierRunner:
    workflow_versions = frozenset({"p103-technical-v1"})

    def __init__(self, reader: asyncio.StreamReader):
        self.reader = reader
        self.active = 0
        self.maximum = 0

    async def run(self, request: RunRequest) -> RunResult:
        self.active += 1
        self.maximum = max(self.active, self.maximum)
        emit(
            "entered",
            job=str(request.job_id),
            task=str(request.task_id),
            kind=request.kind,
            thread=request.thread_id,
            version=request.workflow_version,
            active=self.active,
            maximum=self.maximum,
            attempt=request.attempt,
        )
        try:
            command = (await self.reader.readline()).decode().strip()
            if command == "fail":
                raise RuntimeError("controlled runner fault")
            if command == "interrupt":
                return RunResult("interrupted")
            if command == "retry":
                return RunResult("retry", 0)
            if command == "hang-cancel":
                emit("hanging")
                # 受控非合作调用：父进程注入锁失效后验证硬退出。
                while True:
                    try:
                        await asyncio.Event().wait()
                    except asyncio.CancelledError:
                        emit("cancel_ignored")
            if command != "release":
                raise ValueError("unexpected test barrier command")
            return RunResult()
        except asyncio.CancelledError:
            emit("cancelled", job=str(request.job_id))
            raise
        finally:
            self.active -= 1
            emit("left", job=str(request.job_id), active=self.active, maximum=self.maximum)


async def main_async(organization: UUID) -> None:
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_running_loop().connect_read_pipe(lambda: protocol, sys.stdin)
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    session = WorkerSession(DatabaseSettings(), organization)
    await session.start()
    assert session.connection is not None
    cursor = await session.connection.execute("SELECT pg_backend_pid() AS pid")
    row = await cursor.fetchone()
    assert row is not None
    emit("started", owner=session.owner, pid=os.getpid(), lock_pid=row["pid"])
    try:
        await Worker(
            session,
            BarrierRunner(reader),
            heartbeat_seconds=0.05,
            poll_seconds=0.02,
            cancel_seconds=0.2,
        ).run(stop)
    except UnsafeShutdown:
        emit("unsafe_shutdown")
        os._exit(75)
    emit("stopped")
    if os.environ.get("TEST_HOLD_AFTER_STOP") == "1":
        emit("awaiting_exit")
        if (await reader.readline()).decode().strip() != "exit":
            raise ValueError("test exit barrier required")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("organization", type=UUID)
    args = parser.parse_args()
    try:
        asyncio.run(main_async(args.organization))
    except UnsafeShutdown:
        emit("unsafe_shutdown")
        os._exit(75)
    except Exception as error:
        emit("failed", code=type(error).__name__)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
