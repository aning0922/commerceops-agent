"""只用于受控自有测试的T1提交/ACK屏障；无平台事件/生产身份后门。"""

import asyncio
import json
import os
import signal
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import psycopg
from commerceops.application.intake import TestInbound, TrustedTestContext
from commerceops.application.replenishment.contracts import (
    CreateInput,
    DecisionInput,
    ResolveInput,
    WebActor,
)
from commerceops.infrastructure.approval_decisions import DecisionStore
from commerceops.infrastructure.explanation_repository import ExplanationStore
from commerceops.infrastructure.intake import PgTestIntakeStore
from commerceops.infrastructure.inventory_repository import InventoryStore
from commerceops.infrastructure.replenishment_items import ItemStore
from commerceops.infrastructure.replenishment_projection import ProjectionStore
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

    payload = value["payload"]
    assert isinstance(payload, dict)
    factory = (
        ControlledP3Factory(payload["controlled"])
        if payload.get("controlled")
        else MockCollectorFactory(DIRECTORY)
    )
    revalidation_factory = (
        ControlledP3Factory(payload["revalidation_controlled"])
        if payload.get("revalidation_controlled")
        else factory
    )

    class ObservedApprovalRunner(ApprovalRunner):
        async def run(self, request: Any) -> Any:
            try:
                return await super().run(request)
            except psycopg.Error as error:
                emit(
                    "safe_pg_failure",
                    category=type(error).__name__,
                    sqlstate=error.sqlstate,
                    constraint=error.diag.constraint_name,
                )
                raise

    approval = ObservedApprovalRunner(
        ApprovalStore(config, session, hook=barrier),
        hook=barrier,
        collector_factory=revalidation_factory,
    )

    def offline_response(request: httpx.Request) -> httpx.Response:
        items = json.loads(json.loads(request.content)["messages"][1]["content"])["items"]
        return httpx.Response(
            200,
            json={
                "model": "deepseek-flash",
                "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "highlights": [
                                        {
                                            "sku_key": x["sku_key"],
                                            "reason": x["allowed_reason"],
                                            "source": "facts",
                                        }
                                        for x in items
                                    ]
                                }
                            ),
                        },
                    }
                ],
            },
        )

    provider = ProviderFactory(
        offline_transport=httpx.MockTransport(offline_response)
        if payload.get("offline_explanation")
        else None,
    )
    runner = InventoryCompositeRunner(
        InventoryRunner(InventoryStore(config.database, session), factory),
        ExplanationRunner(ExplanationStore(config.database, session), provider),
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

    if value["action"] == "projection":

        async def projection() -> None:
            organization = UUID(value["legacy"]["organization"])
            session = WorkerSession(config.database, organization)
            await session.start()
            try:
                store = ProjectionStore(session, controlled_stub=True)
                identifier = UUID(value["payload"]["outbox_id"])
                if value["payload"]["operation"] == "failure":
                    await store.record_failure(
                        identifier, unknown=value["payload"].get("unknown", False)
                    )
                    emit("ack")
                else:
                    emit("ack", outcome=await store.reconcile(identifier))
            finally:
                await session.close(clean=True)

        asyncio.run(projection())
        return

    def hook(point: str) -> None:
        emit(point)
        if point == value["barrier"] and sys.stdin.readline().strip() != "release":
            raise ValueError("controlled P3 release required")

    if value["action"] in ("create", "decide", "resolve"):
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
        elif value["action"] == "decide":
            decision = DecisionInput.model_validate_json(json.dumps(value["payload"]))
            DecisionStore(config).decide(actor, decision.approval_id, decision, hook=hook)
        else:
            ItemStore(ReplenishmentStore(config, DIRECTORY)).resolve(
                actor,
                UUID(value["payload"]["item_id"]),
                ResolveInput.model_validate_json(json.dumps(value["payload"]["request"])),
                hook=hook,
            )
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
