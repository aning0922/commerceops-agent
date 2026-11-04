"""Owned PG日报恢复的独立OS进程；仅测试显式deployment，未装配任何外部sender/model。"""

import argparse
import asyncio
from pathlib import Path
from uuid import UUID

from commerceops.infrastructure.daily_sources import DailyDeployment
from commerceops.infrastructure.daily_store import DailyStore
from commerceops.infrastructure.database import DatabaseSettings
from commerceops.infrastructure.queue import JobQueue
from commerceops.infrastructure.worker_lock import WorkerSession, mark_attention
from commerceops.workflows.daily_report import DailyRunner


async def run(
    deployment: Path,
    org: UUID,
    task: UUID,
    ack: bool,
    repeat: bool = False,
    mark_completed: bool = False,
) -> None:
    settings = DatabaseSettings()
    files = DailyDeployment.load(deployment)
    session = WorkerSession(settings, org)
    await session.start()
    try:
        queue = JobQueue(session, task_ids=frozenset({task}))
        await queue.recover_confirmed()
        claimed = await queue.claim()
        if claimed is None or claimed.task_id != task:
            raise ValueError("owned job missing")
        runner = DailyRunner(DailyStore(settings, session, files))
        await runner.run(claimed)
        if repeat:
            await runner.run(claimed)
        if mark_completed:
            assert session.connection is not None
            await mark_attention(session.connection, session.owner)
        if ack:
            await queue.done(claimed)
    finally:
        await session.close(clean=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deployment", type=Path, required=True)
    parser.add_argument("--organization", type=UUID, required=True)
    parser.add_argument("--task", type=UUID, required=True)
    parser.add_argument("--ack", action="store_true")
    parser.add_argument("--repeat", action="store_true")
    parser.add_argument("--mark-attention", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(
            run(
                args.deployment,
                args.organization,
                args.task,
                args.ack,
                args.repeat,
                args.mark_attention,
            )
        )
    except Exception as error:
        raise SystemExit(
            f"owned daily worker failed: {type(error).__name__}; original task retained"
        ) from None
    print("owned daily worker stopped")


if __name__ == "__main__":
    main()
