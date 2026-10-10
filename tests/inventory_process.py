"""P203 实际 Worker/Graph 子进程；stdin 屏障只用作测试，不是业务入口。"""

import argparse
import asyncio
import json
import os
import signal
import sys
from uuid import UUID

from commerceops.infrastructure.database import DatabaseSettings
from commerceops.infrastructure.inventory_repository import InventoryStore
from commerceops.infrastructure.worker import Worker
from commerceops.infrastructure.worker_lock import WorkerSession
from commerceops.workflows.inventory_analysis import InventoryRunner, MockCollectorFactory

from tests.inventory_support import DIRECTORY


def emit(event: str, **values: object) -> None:
    print(json.dumps({"event": event, **values}), flush=True)


async def run(organization: UUID) -> None:
    reader = asyncio.StreamReader()
    await asyncio.get_running_loop().connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader), sys.stdin
    )
    stop = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    session = WorkerSession(DatabaseSettings(), organization)
    await session.start()
    emit("started", owner=session.owner, pid=os.getpid())

    async def hook(point: str) -> None:
        emit(point)
        if point == os.environ.get("P203_BARRIER"):
            if (await reader.readline()).decode().strip() != "release":
                raise ValueError("owned barrier command required")

    runner = InventoryRunner(
        InventoryStore(session.settings, session), MockCollectorFactory(DIRECTORY), hook=hook
    )
    await Worker(session, runner, heartbeat_seconds=0.05, poll_seconds=0.01).run(stop)
    emit("stopped")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("organization", type=UUID)
    args = parser.parse_args()
    try:
        asyncio.run(run(args.organization))
    except Exception as error:
        emit("failed", code=type(error).__name__)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
