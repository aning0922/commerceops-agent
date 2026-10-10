"""只用于受控自有测试的T1提交/ACK屏障；无平台事件/生产身份后门。"""

import asyncio
import json
import os
import signal
import sys
from pathlib import Path
from uuid import UUID

from commerceops.application.intake import TestInbound, TrustedTestContext
from commerceops.application.replenishment.contracts import CreateInput, DecisionInput, WebActor
from commerceops.infrastructure.approval_decisions import DecisionStore
from commerceops.infrastructure.explanation_repository import ExplanationStore
from commerceops.infrastructure.intake import PgTestIntakeStore
from commerceops.infrastructure.inventory_repository import InventoryStore
from commerceops.infrastructure.replenishment_repository import ApprovalStore, ReplenishmentStore
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.worker import UnsafeShutdown, Worker
from commerceops.infrastructure.worker_lock import TerminationRequired, WorkerBusy, WorkerSession
from commerceops.workflows.inventory_analysis import InventoryRunner, MockCollectorFactory
from commerceops.workflows.replenishment import ApprovalRunner
from commerceops.workflows.report_explanation import (
    ExplanationRunner,
    InventoryCompositeRunner,
    ProviderFactory,
)
from pydantic import TypeAdapter

from tests.inventory_support import DIRECTORY
from tests.p3_support import ControlledP3Factory


def emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, "pid": os.getpid(), **fields}), flush=True)


async def worker_main(config: WebConfig, value: dict[str, object]) -> None:
    legacy = value["legacy"]
    assert isinstance(legacy, dict)
    session = WorkerSession(config.database, UUID(legacy["organization"]))
    try:
        await session.start()
    except (WorkerBusy, TerminationRequired) as error:
        emit("blocked", category=type(error).__name__)
        raise
    assert session.connection
    cursor = await session.connection.execute("SELECT pg_backend_pid() AS pid")
    row = await cursor.fetchone()
    assert row
    emit("started", owner=session.owner, lock_pid=row["pid"])
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)

    async def barrier(point: str) -> None:
        emit(point)
        if point == value["barrier"]:
            command = await asyncio.to_thread(sys.stdin.readline)
            if command.strip() != "release":
                raise ValueError("controlled P3 release required")

    approval = ApprovalRunner(ApprovalStore(config, session, hook=barrier), hook=barrier)
    payload = value["payload"]
    assert isinstance(payload, dict)
    factory = (
        ControlledP3Factory(payload["controlled"])
        if payload.get("controlled")
        else MockCollectorFactory(DIRECTORY)
    )
    runner = InventoryCompositeRunner(
        InventoryRunner(InventoryStore(config.database, session), factory),
        ExplanationRunner(ExplanationStore(config.database, session), ProviderFactory()),
        approval=approval,
    )
    try:
        await Worker(
            session,
            runner,
            heartbeat_seconds=0.1,
            poll_seconds=0.02,
            reconcile=approval.reconcile,
            recovery_scan_seconds=1,
        ).run(stop)
    except UnsafeShutdown:
        os._exit(75)
    emit("stopped")


def main() -> None:
    value = json.loads(Path(sys.argv[1]).read_text())
    config = WebConfig.from_file(Path(value["configuration"]))
    if value["action"] == "worker":
        asyncio.run(worker_main(config, value))
        return

    def hook(point: str) -> None:
        emit(point)
        if point == value["barrier"] and sys.stdin.readline().strip() != "release":
            raise ValueError("controlled P3 release required")

    if value["action"] in ("create", "decide"):
        a = value["actor"]
        actor = WebActor(
            UUID(a["session_id"]),
            UUID(a["principal_id"]),
            UUID(a["identity_id"]),
            UUID(a["organization_id"]),
            a["auth_version"],
        )
        if value["action"] == "create":
            request: CreateInput = TypeAdapter(CreateInput).validate_json(
                json.dumps(value["payload"])
            )
            ReplenishmentStore(config, DIRECTORY).create(actor, request, hook)
        else:
            decision = DecisionInput.model_validate_json(json.dumps(value["payload"]))
            DecisionStore(config).decide(actor, decision.approval_id, decision, hook=hook)
    else:
        data = value["legacy"]
        context = TrustedTestContext(
            UUID(data["organization"]),
            UUID(data["shop"]),
            UUID(data["principal"]),
            UUID(data["conversation"]),
            "test",
        )
        event = TestInbound(
            app_id=data["app"],
            tenant_key=data["tenant"],
            event_id=value["payload"]["event_id"],
            message_id=value["payload"]["message_id"],
            workflow_version="p103-technical-v1",
            normalized_request={"schema_version": 1},
        )
        PgTestIntakeStore(config.database).accept(context, event, hook)
    emit("ack")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"event": "failed", "category": type(error).__name__}), flush=True)
        raise SystemExit(2) from None
