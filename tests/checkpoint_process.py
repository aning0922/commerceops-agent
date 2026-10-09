"""真实 Graph/Worker 的独立 OS 进程；async stdin barrier 不启动业务线程。"""

import argparse
import asyncio
import json
import os
import signal
import sys
from typing import Any
from uuid import UUID

from commerceops.infrastructure.checkpoint_probe import ProbeStore
from commerceops.infrastructure.database import DatabaseSettings
from commerceops.infrastructure.worker import UnsafeShutdown, Worker
from commerceops.infrastructure.worker_lock import WorkerSession
from commerceops.workflows.checkpoint_probe import ProbeRunner


def emit(event: str, **data: Any) -> None:
    print(json.dumps({"event": event, **data}), flush=True)


async def serve(organization: UUID) -> None:
    if os.environ.get("COMMERCEOPS_MODE") != "test":
        raise ValueError("explicit test process required")
    reader = asyncio.StreamReader()
    await asyncio.get_running_loop().connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader),
        sys.stdin,
    )
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
    # barrier 配置来自可信测试进程环境，绝不从 Graph/payload/card 读取。
    barriers = set(os.environ.get("P104_BARRIERS", "").split(","))

    async def hook(event: str, data: dict[str, Any]) -> None:
        emit(event, **data)
        if event in barriers:
            if os.environ.get("P104_ONCE_BARRIERS") == "1":
                barriers.remove(event)
            emit("barrier", point=event, task=data.get("task"))
            while True:
                try:
                    if (await reader.readline()).decode().strip() != "release":
                        raise ValueError("explicit barrier release required")
                    break
                except asyncio.CancelledError:
                    emit("barrier_cancelled", point=event)
                    if os.environ.get("P104_IGNORE_CANCEL") != "1":
                        raise

    try:
        await Worker(
            session,
            ProbeRunner(ProbeStore(session.settings, session, mode="test"), hook=hook),
            heartbeat_seconds=0.05,
            poll_seconds=0.02,
            cancel_seconds=1,
        ).run(stop)
    except UnsafeShutdown:
        emit("unsafe_shutdown")
        os._exit(75)
    emit("stopped")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("organization", type=UUID)
    args = parser.parse_args()
    try:
        asyncio.run(serve(args.organization))
    except Exception as error:
        emit("failed", code=type(error).__name__)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
