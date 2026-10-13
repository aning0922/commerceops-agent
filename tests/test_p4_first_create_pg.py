"""新自有 PG/实际进程与账本；SDK transport Fake，Secret/平台/provider0。"""

import asyncio
import json
import subprocess
import sys
import time
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from commerceops.adapters.feishu.business_base import BusinessBaseAdapter
from commerceops.adapters.feishu.business_gateway import BusinessCard
from commerceops.adapters.feishu.projection_contract import ApiReply
from commerceops.application.feishu_business.delivery import DeliveryGate
from commerceops.application.feishu_business.sdk_window import SDKScope, SDKWindow
from commerceops.application.feishu_business.worker_window import (
    FIRST_CREATE_CAPS,
    KNOWN70_CAPS,
    ControlledWorkerWindow,
)
from commerceops.application.replenishment.contracts import DecisionInput
from commerceops.entrypoints.feishu_business import confirm_worker_child
from commerceops.entrypoints.feishu_worker_child import controlled_task_ids, trusted_scope
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_base_delivery import BaseDeliveryStore
from commerceops.infrastructure.feishu_gateway_window import guard_gateway
from commerceops.infrastructure.feishu_sdk_ledger import PersistentSDKLedger
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.worker_lock import WorkerSession, confirm_termination

from tests.p3_support import P3Fixture, P3Process
from tests.p4_recovery_support import (
    RecordedRecords,
    gateway,
    settings,
    start_gateway,
    stop_gateway,
    write_private,
)
from tests.test_p3_approval_pg import payload, wait_state
from tests.test_p3_execution_recovery_pg import wait_jobs
from tests.test_p3_pg import fixture as fixture
from tests.test_p4_a09_workflow_pg import manifest
from tests.test_p4_base_adapter import MemoryRecords
from tests.test_p4_blank_records import blank
from tests.test_p4_delivery_pg import due, resolve
from tests.test_p4_gateway_pg import message, service

pytestmark = pytest.mark.integration


async def c0_child(config_path: Path, spec_path: Path) -> None:
    config = WebConfig.from_file(config_path)
    spec = json.loads(spec_path.read_text())
    organization, shop, task = (UUID(spec[key]) for key in ("organization", "shop", "task"))
    session = WorkerSession(config.database, organization)
    await session.start()
    try:
        expiry = datetime.now(UTC) + timedelta(seconds=4)
        ledger = PersistentSDKLedger(
            session,
            SDKWindow(
                uuid4(),
                organization,
                shop,
                expiry,
                {"bitable.v1.app_table_record.list": 1},
                enabled=True,
                verification_mode="controlled_sdk",
            ),
        )
        fake = RecordedRecords(ledger, rows=[{"record_id": "partial", "fields": {"SKU": "bad"}}])
        store = BaseDeliveryStore(
            session,
            BusinessBaseAdapter(fake, {"test": ("fake", "fake")}),
            DeliveryGate(
                organization,
                shop,
                frozenset({task}),
                "test",
                expiry,
                enabled=True,
                verification_mode="controlled_sdk",
            ),
            ledger,
        )
        assert await store.dispatch_one() == "unknown"
        assert [call[0] for call in fake.calls] == ["query"]
    finally:
        await session.close(clean=True)


def c0_process(f: P3Fixture, task: UUID) -> None:
    spec = f.private / "c0-spec.private.json"
    write_private(
        spec, {"organization": f.actor.organization_id, "shop": f.inventory.data.shop, "task": task}
    )
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import asyncio,sys; from pathlib import Path; "
            "from tests.test_p4_first_create_pg import c0_child; "
            "asyncio.run(c0_child(Path(sys.argv[1]),Path(sys.argv[2])))",
            str(f.config_file),
            str(spec),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        _, errors = child.communicate(timeout=15)
        if child.returncode:
            destination = Path("/run/owned") if Path("/run/owned").is_dir() else f.private
            diagnostic = destination / ("c0-child-" + uuid4().hex + ".private.txt")
            diagnostic.write_bytes(errors)
            diagnostic.chmod(0o600)
            raise AssertionError("C0 child failed; private traceback retained")
        asyncio.run(confirm_worker_child(f.config, f.actor.organization_id, child.pid))
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


@contextmanager
def original_c0(f: P3Fixture) -> Iterator[ControlledWorkerWindow]:
    old = gateway(f, case="known_inbound", seconds=180)
    original_gateway = start_gateway(f, old)
    graph = replacement = None
    new = None
    try:
        intake = service(
            f,
            "known_inbound",
            allow_live_bindings=True,
            gateway_guard=lambda db, create: guard_gateway(db, old, create),
        )
        incoming = message(f)
        task = UUID(intake.message(incoming)["task_id"])
        spec: dict[str, Any] = {
            "schema_version": "p4-worker-v1",
            "window_id": str(uuid4()),
            "gateway_window_id": str(old.window_id),
            "organization_id": str(f.actor.organization_id),
            "shop_id": str(f.inventory.data.shop),
            "task_ids": [str(task)],
            "expires_at": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
            "enabled": True,
            "profile": "known70",
            "caps": dict(KNOWN70_CAPS),
        }
        graph = P3Process(
            f,
            "worker",
            {
                "task_id": str(task),
                "p4_ledger_stub": True,
                "p4_scope": {"window": spec, "settings": settings(f).model_dump(mode="json")},
            },
            "never",
        )
        owner = graph.until("started")["owner"]
        graph.until("after_ready")
        request = DecisionInput.model_validate_json(json.dumps(payload(f, task, "approve")))
        with connect(f.config.database) as db:
            approval_outbox = db.execute(
                "SELECT id FROM business.outbox WHERE aggregate_id=%s", (request.approval_id,)
            ).fetchone()
            assert approval_outbox
            db.execute(
                """INSERT INTO business.p4_card_bindings
                (approval_id,outbox_id,chat_id,message_id,source_mode)
                VALUES(%s,%s,%s,'synthetic-c0-card','feishu')""",
                (request.approval_id, approval_outbox["id"], incoming.chat_id),
            )
        card = BusinessCard(
            "synthetic-c0-event", incoming.identity, incoming.chat_id, "synthetic-c0-card", request
        )
        intake.card(card)
        wait_state(f, task, "completed")
        wait_jobs(f, task)
        graph.stop_clean()
        asyncio.run(
            confirm_termination(f.config.database, owner, "owned graph clean exit0 and reap")
        )
        c0_process(f, task)
        stop_gateway(f, old, original_gateway)
        new = gateway(f, case="known_inbound", max_workflows=0)
        replacement = start_gateway(f, new)
        recovered = manifest(f, old, new, task, owner, UUID(spec["window_id"]))
        value = recovered.model_dump(mode="json")
        with connect(f.config.database) as db:
            delivery = db.execute(
                """SELECT d.*,o.request_hash FROM business.p4_base_deliveries d
                JOIN business.outbox o ON o.id=d.outbox_id WHERE d.task_id=%s""",
                (task,),
            ).fetchone()
            assert delivery and delivery["last_error"] == "INCOMPLETE_READBACK"
            assert db.execute(
                "SELECT count(*) AS n FROM business.p4_sdk_calls WHERE "
                "method='bitable.v1.app_table_record.create'"
            ).fetchone() == {"n": 0}
        value.update(
            profile="approved_first_create",
            caps=dict(FIRST_CREATE_CAPS),
            first_create={
                key: str(delivery[key])
                if key in ("outbox_id", "item_id", "client_token")
                else delivery[key]
                for key in (
                    "outbox_id",
                    "item_id",
                    "client_token",
                    "version",
                    "projection_hash",
                    "request_hash",
                )
            },
        )
        window = ControlledWorkerWindow.model_validate_json(json.dumps(value))
        # SDK0/new claim0：旧 SDK 仍有效的入口必须拒绝；等待原固定 expiry，绝不改旧窗口。
        with pytest.raises(PermissionError, match="P4_FIRST_CREATE_RECOVERY_DENIED"):
            asyncio.run(trusted_scope(f.config, settings(f), window))
        with connect(f.config.database) as db:
            expiry = db.execute(
                "SELECT max(expires_at) AS expiry FROM business.p4_sdk_windows"
            ).fetchone()
            assert expiry
            remaining = (expiry["expiry"] - datetime.now(UTC)).total_seconds()
        assert remaining < 31
        if remaining > 0:
            time.sleep(remaining + 0.02)
        yield window
    except BaseException as error:
        from tests.diagnostic_plugin import emit

        emit(
            "first_create_safe_failure",
            category=type(error).__name__,
            frames=[
                {"file": Path(frame.filename).name, "function": frame.name, "line": frame.lineno}
                for frame in traceback.extract_tb(error.__traceback__)
            ],
        )
        raise
    finally:
        if graph and graph.process.poll() is None:
            graph.kill_reap()
        if replacement and new:
            stop_gateway(f, new, replacement)
        if original_gateway.poll() is None:
            stop_gateway(f, old, original_gateway)


class AckDropRecords(RecordedRecords):
    """Fake 低层成功已持久returned200/code0，唯一上层ACK丢失。"""

    async def create(self, *args: Any, **kwargs: Any) -> ApiReply:
        async def call() -> Any:
            reply = await MemoryRecords.create(self, *args, **kwargs)
            return SimpleNamespace(raw=SimpleNamespace(status_code=200), code=0, reply=reply)

        await self.ledger.invoke("bitable.v1.app_table_record.create", call)
        return ApiReply(None, None)


@pytest.mark.parametrize("ack_drop", [False, True])
def test_original_c0_first_create_ack_loss_readonly_anchor_and_t6_same_record(
    fixture: P3Fixture,
    ack_drop: bool,
) -> None:
    f = fixture
    with original_c0(f) as window:
        asyncio.run(trusted_scope(f.config, settings(f), window))
        projection = window.first_create
        assert projection

        async def run() -> None:
            session = WorkerSession(f.config.database, window.organization_id)
            await session.start()
            try:
                ledger = PersistentSDKLedger(session, window.window(settings(f)))

                # 与正式 Factory 顺序一致：持久当前window/preflight后才进入delivery。
                async def fake_auth() -> Any:
                    return SimpleNamespace(raw=SimpleNamespace(status_code=200), code=0)

                with ledger.scope(SDKScope(window.window_id, None, "preflight")):
                    await ledger.invoke("auth.v3.tenant_access_token.internal", fake_auth)
                fake = (AckDropRecords if ack_drop else RecordedRecords)(
                    ledger,
                    rows=[blank("blank-" + str(n)) for n in range(5)],
                )
                store = BaseDeliveryStore(
                    session,
                    BusinessBaseAdapter(fake, {"test": ("fake", "fake")}),
                    DeliveryGate(
                        window.organization_id,
                        window.shop_id,
                        window.task_ids,
                        "test",
                        window.expires_at,
                        enabled=True,
                        verification_mode="controlled_sdk",
                        first_create=projection,
                        first_create_window_id=window.window_id,
                    ),
                    ledger,
                )
                assert await controlled_task_ids(f.config, window) == window.task_ids
                with connect(f.config.database) as db:
                    queued = db.execute(
                        "SELECT next_attempt_at<=clock_timestamp() AS due FROM "
                        "business.p4_base_deliveries WHERE outbox_id=%s",
                        (projection.outbox_id,),
                    ).fetchone()
                    assert queued
                from tests.diagnostic_plugin import emit

                emit("first_create_original_schedule", due_before_adjustment=queued["due"])
                due(f)  # 仅新owned fixture调度时间；原键/快照/unknown/attempt不改。
                outcome = await store.dispatch_one()
                emit(
                    "first_create_dispatch_outcome",
                    outcome=outcome,
                    transport_operations=[call[0] for call in fake.calls],
                )
                assert outcome == ("unknown" if ack_drop else "verified")
                if ack_drop:
                    # 新claim不能再授C0；原当前窗口下一步只能reconcile。
                    with pytest.raises(PermissionError):
                        await trusted_scope(f.config, settings(f), window)
                    due(f)
                    assert await store.dispatch_one() == "verified"
                resolve(f, projection.item_id)
                due(f)
                assert await store.dispatch_one() == "verified"
                assert len([c for c in fake.calls if c[0] == "create"]) == 1
                assert [c[1] for c in fake.calls if c[0] == "create"] == [
                    str(projection.client_token)
                ]
                assert [c[1] for c in fake.calls if c[0] == "update"] == ["synthetic-row"]
                with connect(f.config.database) as db:
                    rows = db.execute(
                        "SELECT version,status FROM business.p4_base_deliveries ORDER BY version"
                    ).fetchall()
                    assert rows == [
                        {"version": 1, "status": "verified"},
                        {"version": 2, "status": "verified"},
                    ]
                    assert db.execute(
                        "SELECT count(*) AS n FROM business.executions"
                    ).fetchone() == {"n": 1}
                    assert db.execute(
                        "SELECT count(*) AS n FROM business.replenishment_items"
                    ).fetchone() == {"n": 1}
                    assert db.execute(
                        "SELECT count(*) AS n FROM business.p4_sdk_calls WHERE "
                        "method='bitable.v1.app_table_record.create'"
                    ).fetchone() == {"n": 1}
                    if ack_drop:
                        assert db.execute(
                            "SELECT status,http_status,provider_code FROM business.p4_sdk_calls "
                            "WHERE "
                            "method='bitable.v1.app_table_record.create'"
                        ).fetchone() == {
                            "status": "returned",
                            "http_status": 200,
                            "provider_code": 0,
                        }
            finally:
                await session.close(clean=True)

        asyncio.run(run())


def test_c0_claim_denies_tampered_original_bindings_and_current_revocation(
    fixture: P3Fixture,
) -> None:
    f = fixture
    with original_c0(f) as window:
        for field in (
            "outbox_id",
            "item_id",
            "client_token",
            "projection_hash",
            "request_hash",
        ):
            spec = window.model_dump(mode="json")
            spec["first_create"][field] = "c" * 64 if field.endswith("hash") else str(uuid4())
            wrong = ControlledWorkerWindow.model_validate_json(json.dumps(spec))
            with pytest.raises(PermissionError):
                asyncio.run(trusted_scope(f.config, settings(f), wrong))
        with connect(f.inventory.owner) as db:
            db.execute(
                "UPDATE business.principals SET auth_version=auth_version+1 WHERE id=%s",
                (f.actor.principal_id,),
            )
        with pytest.raises(PermissionError):
            asyncio.run(trusted_scope(f.config, settings(f), window))
        with connect(f.config.database) as db:
            assert db.execute(
                "SELECT count(*) AS n FROM business.audit_events WHERE source='feishu_recovery'"
            ).fetchone() == {"n": 0}
            assert db.execute(
                "SELECT count(*) AS n FROM business.p4_sdk_calls "
                "WHERE method='bitable.v1.app_table_record.create'"
            ).fetchone() == {"n": 0}
