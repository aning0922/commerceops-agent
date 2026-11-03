"""Owned PG test child; no provider and no server. Private config path only."""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

from commerceops.infrastructure.queue import JobQueue
from commerceops.infrastructure.readonly_inquiry_store import InquiryConfig, InquiryStore
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.worker_lock import WorkerSession
from commerceops.workflows.readonly_inquiry import ReadonlyInquiryRunner, runtime_factory

from tests.inventory_support import DIRECTORY


async def run(value: dict[str, Any]) -> None:
    config = WebConfig.from_file(Path(value["configuration"]))
    task = UUID(value["task"])
    session = WorkerSession(config.database, UUID(value["organization"]))
    directory = Path(value["missing_fixture"]) if value.get("missing_fixture") else DIRECTORY
    store = InquiryStore(config, InquiryConfig(UUID(value["shop"]), directory, enabled=True))
    await session.start()
    clean = False
    try:
        queue = JobQueue(session, task_ids=frozenset({task}))
        await queue.recover_confirmed()
        job = await queue.claim()
        assert job is not None and job.task_id == task

        async def forbidden(*args: Any) -> Any:
            raise AssertionError("completed replay must not construct a model/tool runtime")

        factory = forbidden if value["replay"] else runtime_factory(store, session)
        await ReadonlyInquiryRunner(store, session, factory).run(job)
        print(json.dumps({"event": "saved", "owner": session.owner}), flush=True)
        # Parent may SIGKILL here: durable result exists, running job is unsettled.
        if not value["replay"]:
            assert await asyncio.to_thread(sys.stdin.readline) == "settle\n"
        await queue.done(job)
        clean = True
        print(json.dumps({"event": "settled"}), flush=True)
    finally:
        await session.close(clean=clean)


if __name__ == "__main__":
    try:
        asyncio.run(run(json.loads(Path(sys.argv[1]).read_text())))
    except BaseException:
        # Never echo SQL DETAIL, private configuration, or credentials.
        print(json.dumps({"event": "failed"}), flush=True)
        raise SystemExit(1) from None
