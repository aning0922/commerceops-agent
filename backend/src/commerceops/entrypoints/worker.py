"""部署启动层；本任务仅提供显式技术 test runner，正式图由 P1-04 注入。"""

import argparse
import asyncio
import os
import signal
from pathlib import Path
from uuid import UUID

from commerceops.application.runner import RunRequest, RunResult
from commerceops.infrastructure.database import DatabaseSettings
from commerceops.infrastructure.inventory_repository import InventoryStore
from commerceops.infrastructure.worker import UnsafeShutdown, Worker
from commerceops.infrastructure.worker_lock import WorkerSession, confirm_termination
from commerceops.workflows.inventory_analysis import InventoryRunner, MockCollectorFactory


class TechnicalRunner:
    workflow_versions = frozenset({"p103-technical-v1"})

    async def run(self, request: RunRequest) -> RunResult:
        # 无库存/模型/审批/checkpoint，只证明串行调度；不写业务 completed。
        return RunResult()


async def serve(
    settings: DatabaseSettings, organization: UUID, fixture: Path | None = None
) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    session = WorkerSession(settings, organization)
    await session.start()
    print(f"technical test worker started: owner={session.owner}", flush=True)
    try:
        runner = (
            InventoryRunner(InventoryStore(settings, session), MockCollectorFactory(fixture))
            if fixture is not None
            else TechnicalRunner()
        )
        await Worker(session, runner).run(stop)
    except UnsafeShutdown:
        # 在 asyncio.run 清理 pending tasks 之前退出；非合作调用不能拖住退出。
        print("worker cancellation unconfirmed; termination confirmation required", flush=True)
        os._exit(75)


def main() -> None:
    parser = argparse.ArgumentParser(description="Single Worker technical test / recovery")
    parser.add_argument("action", choices=["test-run", "inventory-test-run", "confirm-termination"])
    parser.add_argument("--organization", type=UUID)
    parser.add_argument("--fixture-directory", type=Path)
    parser.add_argument("--owner")
    parser.add_argument("--evidence-reference")
    parser.add_argument("--confirm-old-process-terminated", action="store_true")
    args = parser.parse_args()
    try:
        settings = DatabaseSettings()
        if args.action in ("test-run", "inventory-test-run"):
            if os.environ.get("COMMERCEOPS_MODE") != "test" or args.organization is None:
                raise ValueError("explicit test mode and organization required")
            if args.action == "inventory-test-run" and args.fixture_directory is None:
                raise ValueError("owned fixture directory required")
            asyncio.run(
                serve(
                    settings,
                    args.organization,
                    args.fixture_directory if args.action == "inventory-test-run" else None,
                )
            )
        else:
            if (
                not args.confirm_old_process_terminated
                or not args.owner
                or not args.evidence_reference
            ):
                raise ValueError("operator termination confirmation required")
            asyncio.run(confirm_termination(settings, args.owner, args.evidence_reference))
    except UnsafeShutdown:
        print(
            "worker unsafe cancellation: process exiting; termination confirmation required",
            flush=True,
        )
        os._exit(75)
    except Exception as error:
        # 仅固定异常类别；不打印数据库/runner 原始错误、参数或 DSN。
        raise SystemExit(f"worker failed: {type(error).__name__}") from None


if __name__ == "__main__":
    main()
