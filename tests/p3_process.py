"""只用于受控自有测试的T1提交/ACK屏障；无平台事件/生产身份后门。"""

import asyncio
import hashlib
import json
import os
import signal
import sys
import traceback
from datetime import UTC, datetime
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
from commerceops.workflows.inventory_analysis import (
    CollectorFactory,
    InventoryRunner,
    MockCollectorFactory,
)
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
    # 原固定checkout源码，不让owned旧依赖镜像中的wheel取代当前bound backend。
    modules = (Worker, ApprovalRunner, InventoryRunner, WorkerSession)
    hashes = {}
    for kind in modules:
        filename = sys.modules[kind.__module__].__file__
        if filename is None:
            raise ValueError("SOURCE_MODULE_FILE_REQUIRED")
        hashes[kind.__name__] = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
    emit("source_checked", hashes=hashes)
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)

    async def barrier(point: str) -> None:
        emit(point)
        if point == value["barrier"]:
            try:
                command = await asyncio.to_thread(sys.stdin.readline)
            except asyncio.CancelledError:
                emit("barrier_cancelled", point=point)
                raise
            if command.strip() != "release":
                raise ValueError("controlled P3 release required")

    payload = value["payload"]
    assert isinstance(payload, dict)
    scoped_tasks = None
    controlled_window = None
    if payload.get("p4_scope"):
        from commerceops.adapters.feishu.business_config import BusinessSettings
        from commerceops.application.feishu_business.worker_window import ControlledWorkerWindow
        from commerceops.entrypoints.feishu_worker_child import controlled_task_ids, trusted_scope

        scope = payload["p4_scope"]
        controlled_window = ControlledWorkerWindow.model_validate_json(json.dumps(scope["window"]))
        settings = BusinessSettings.model_validate_json(json.dumps(scope["settings"]))
        await trusted_scope(config, settings, controlled_window)
        scoped_tasks = await controlled_task_ids(config, controlled_window)
        if controlled_window.workflow_recovery:
            emit("workflow_scope_validated")
        if payload.get("p4_ledger_stub") is True:
            # 实际 PG 账本/Fake 返回，不构造 SDK Client/Factory 或读取秘密。
            from commerceops.application.feishu_business.sdk_window import SDKScope
            from commerceops.infrastructure.feishu_sdk_ledger import PersistentSDKLedger

            ledger = PersistentSDKLedger(session, controlled_window.window(settings))

            class StubReply:
                raw = type("Raw", (), {"status_code": 200})()
                code = 0

            async def local_reply() -> StubReply:
                return StubReply()

            with ledger.scope(SDKScope(controlled_window.window_id, None, "preflight")):
                await ledger.invoke("auth.v3.tenant_access_token.internal", local_reply)
    factory: CollectorFactory = (
        ControlledP3Factory(payload["controlled"])
        if payload.get("controlled")
        else MockCollectorFactory(DIRECTORY)
    )
    if payload.get("p4_demo") is True:
        from tests.p4_demo_factory import M1DemoFactory

        factory = M1DemoFactory()
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
    expiry_timer = None
    if controlled_window:
        expiry_timer = asyncio.get_running_loop().call_later(
            max(0, (controlled_window.expires_at - datetime.now(UTC)).total_seconds() - 15),
            stop.set,
        )
    try:

        async def maintenance() -> None:
            if controlled_window and controlled_window.workflow_recovery:
                from commerceops.application.feishu_business.gateway_window import GatewayWindow
                from commerceops.infrastructure.feishu_workflow_recovery import (
                    trusted_workflow_scope,
                )
                from commerceops.infrastructure.worker_lock import open_async

                async with await open_async(config.database) as db:
                    cur = await db.execute(
                        "SELECT after_state FROM business.audit_events WHERE id=%s",
                        (controlled_window.gateway_window_id,),
                    )
                    row = await cur.fetchone()
                assert row
                gateway = GatewayWindow.model_validate_json(
                    json.dumps({k: row["after_state"].get(k) for k in GatewayWindow.model_fields})
                )
                await trusted_workflow_scope(
                    config, settings, controlled_window, gateway, claim=False
                )
            await approval.reconcile(
                task_ids=None if controlled_window is None else controlled_window.task_ids
            )

        await Worker(
            session,
            runner,
            heartbeat_seconds=0.1,
            poll_seconds=0.02,
            reconcile=maintenance,
            recovery_scan_seconds=1,
            task_ids=scoped_tasks,
        ).run(stop)
    except UnsafeShutdown:
        os._exit(75)
    finally:
        if expiry_timer:
            expiry_timer.cancel()
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
        print(
            json.dumps(
                {
                    "event": "failed",
                    "category": type(error).__name__,
                    "trace": [
                        {
                            "file": Path(frame.filename).name,
                            "function": frame.name,
                            "line": frame.lineno,
                        }
                        for frame in traceback.extract_tb(error.__traceback__)
                    ],
                }
            ),
            flush=True,
        )
        raise SystemExit(2) from None
