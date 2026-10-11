"""新合成Feishu任务/真实PG+wait/reap/原ledger/Fake SDK，不是平台证据。"""

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from commerceops.adapters.feishu.business_base import BusinessBaseAdapter
from commerceops.adapters.feishu.business_gateway import BusinessCard
from commerceops.application.feishu_business.delivery import DeliveryGate
from commerceops.application.feishu_business.worker_window import (
    RECOVERY_CAPS,
    ControlledWorkerWindow,
)
from commerceops.application.replenishment.contracts import DecisionInput
from commerceops.domain.commerce_values import facts_hash
from commerceops.entrypoints.feishu_worker_child import trusted_scope
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_base_delivery import BaseDeliveryStore
from commerceops.infrastructure.feishu_gateway_window import guard_gateway
from commerceops.infrastructure.feishu_outbox_recovery import (
    receipt_hash,
    sdk_window_hash,
    trusted_recovery_scope,
)
from commerceops.infrastructure.feishu_sdk_ledger import PersistentSDKLedger
from commerceops.infrastructure.worker_lock import WorkerSession

from tests.p3_support import P3Fixture, P3Process
from tests.p4_recovery_support import (
    RecordedRecords,
    gateway,
    original_unknown,
    settings,
    start_gateway,
    stop_gateway,
)
from tests.test_p3_approval_pg import payload, wait_state
from tests.test_p3_pg import fixture as fixture
from tests.test_p4_delivery_pg import due, resolve
from tests.test_p4_gateway_pg import message, service

pytestmark = pytest.mark.integration


def prepared(f: P3Fixture) -> tuple[ControlledWorkerWindow, Any, Any, Path]:
    old = gateway(f, seconds=180)
    original = start_gateway(f, old)
    try:
        store = service(
            f,
            "known_inbound",
            allow_live_bindings=True,
            gateway_guard=lambda db, create: guard_gateway(db, old, create),
        )
        incoming = message(f)
        task = UUID(store.message(incoming)["task_id"])
        child = P3Process(f, "worker", {"task_id": str(task)}, "never")
        try:
            child.until("after_ready")
            request = DecisionInput.model_validate_json(json.dumps(payload(f, task)))
            with connect(f.config.database) as db:
                outbox = db.execute(
                    "SELECT id FROM business.outbox WHERE aggregate_id=%s", (request.approval_id,)
                ).fetchone()
                assert outbox
                db.execute(
                    """INSERT INTO business.p4_card_bindings
                (approval_id,outbox_id,chat_id,message_id,source_mode)
                VALUES(%s,%s,%s,'synthetic-live-card','feishu')""",
                    (request.approval_id, outbox["id"], incoming.chat_id),
                )
            store.card(
                BusinessCard(
                    "synthetic-card-event",
                    incoming.identity,
                    incoming.chat_id,
                    "synthetic-live-card",
                    request,
                )
            )
            wait_state(f, task, "completed")
        finally:
            if child.process.poll() is None:
                child.stop_clean()
        with connect(f.config.database) as db:
            item = db.execute(
                "SELECT id FROM business.replenishment_items WHERE task_id=%s", (task,)
            ).fetchone()
            assert item
        resolve(f, item["id"])
        output, sdk_id = original_unknown(f, task, old)
    finally:
        stop_gateway(f, old, original)
    new = gateway(f, max_workflows=0)
    replacement = start_gateway(f, new)
    try:
        with connect(f.config.database) as db:
            task_row = db.execute(
                "SELECT version FROM business.business_tasks WHERE id=%s", (task,)
            ).fetchone()
            approval = db.execute(
                "SELECT * FROM business.approvals WHERE task_id=%s", (task,)
            ).fetchone()
            receipt = db.execute(
                """SELECT r.*,i.payload_hash FROM business.p4_inbox_receipts r
            JOIN business.inbox_events i ON i.id=r.inbox_id WHERE i.task_id=%s
            AND i.sanitized_payload->>'event_type'='im.message.receive_v1'""",
                (task,),
            ).fetchone()
            execution = db.execute(
                "SELECT id FROM business.executions WHERE task_id=%s", (task,)
            ).fetchone()
            claim = db.execute(
                "SELECT after_state FROM business.audit_events WHERE id=%s", (old.window_id,)
            ).fetchone()
            termination = db.execute(
                """SELECT id FROM business.audit_events WHERE entity_id=%s
            AND source='feishu_gateway' AND action='termination_confirmed'""",
                (str(old.window_id),),
            ).fetchone()
            sdk = db.execute(
                "SELECT * FROM business.p4_sdk_windows WHERE id=%s", (sdk_id,)
            ).fetchone()
            owner = UUID(json.loads(output.read_text())["owner"])
            worker_end = db.execute(
                """SELECT id FROM business.audit_events WHERE entity_id=%s
            AND source='worker' AND action='termination_confirmed'""",
                (str(owner),),
            ).fetchone()
            deliveries = db.execute(
                """SELECT d.*,o.request_hash FROM business.p4_base_deliveries d
            JOIN business.outbox o ON o.id=d.outbox_id WHERE d.task_id=%s ORDER BY d.version""",
                (task,),
            ).fetchall()
            assert (
                task_row
                and approval
                and receipt
                and execution
                and claim
                and termination
                and sdk
                and worker_end
            )
        value = {
            "schema_version": "p4-worker-v1",
            "window_id": str(uuid4()),
            "gateway_window_id": str(new.window_id),
            "organization_id": str(f.actor.organization_id),
            "shop_id": str(f.inventory.data.shop),
            "task_ids": [str(task)],
            "expires_at": new.expires_at.isoformat(),
            "caps": dict(RECOVERY_CAPS),
            "enabled": True,
            "profile": "approved_outbox",
        }
        value["recovery"] = {
            "schema_version": "p4-approved-outbox-v1",
            "worker_window_id": value["window_id"],
            "gateway_window_id": value["gateway_window_id"],
            "expires_at": value["expires_at"],
            "original_gateway_id": str(old.window_id),
            "original_gateway_hash": facts_hash(claim["after_state"]),
            "gateway_termination_id": str(termination["id"]),
            "worker_owner": str(owner),
            "worker_termination_id": str(worker_end["id"]),
            "original_sdk_window_id": str(sdk_id),
            "original_sdk_window_hash": sdk_window_hash(sdk),
            "task_id": str(task),
            "task_version": task_row["version"],
            "inbox_id": str(receipt["inbox_id"]),
            "receipt_hash": receipt_hash(receipt),
            "plan_id": str(approval["plan_id"]),
            "plan_version": approval["plan_version"],
            "plan_hash": approval["plan_hash"],
            "approval_id": str(approval["id"]),
            "decision_id": str(approval["decision_id"]),
            "execution_id": str(execution["id"]),
            "operator_auth_version": f.actor.auth_version,
            "approver_auth_version": approval["decided_auth_version"],
            "target_key": "test",
            "projections": [
                {
                    k: str(d[k]) if isinstance(d[k], UUID) else d[k]
                    for k in (
                        "outbox_id",
                        "item_id",
                        "client_token",
                        "version",
                        "projection_hash",
                        "request_hash",
                    )
                }
                for d in deliveries
            ],
        }
        return (
            ControlledWorkerWindow.model_validate_json(json.dumps(value)),
            new,
            replacement,
            output,
        )
    except BaseException:
        stop_gateway(f, new, replacement)
        raise


def preserved(f: P3Fixture) -> dict[str, Any]:
    from psycopg import sql

    with connect(f.config.database) as db:
        return {
            table: db.execute(
                sql.SQL("SELECT * FROM business.{} ORDER BY id").format(sql.Identifier(table))
            ).fetchall()
            for table in (
                "business_tasks",
                "replenishment_plans",
                "approvals",
                "executions",
                "replenishment_items",
                "outbox",
                "jobs",
            )
        }


def test_cross_window_original_unknown_v1_then_existing_v2_same_anchor_no_execution_or_key(
    fixture: P3Fixture,
) -> None:
    f = fixture
    window, new, replacement, output = prepared(f)
    recovery = window.recovery
    assert recovery
    before = preserved(f)
    try:
        asyncio.run(trusted_scope(f.config, settings(f), window))
        due(f)

        async def run() -> None:
            session = WorkerSession(f.config.database, f.actor.organization_id)
            await session.start()
            try:
                ledger = PersistentSDKLedger(session, window.window(settings(f)))
                fake = RecordedRecords(ledger, rows=json.loads(output.read_text())["rows"])
                gate = DeliveryGate(
                    window.organization_id,
                    window.shop_id,
                    window.task_ids,
                    "test",
                    window.expires_at,
                    enabled=True,
                    verification_mode="controlled_sdk",
                    outbox_ids=frozenset(p.outbox_id for p in recovery.projections),
                )
                store = BaseDeliveryStore(
                    session, BusinessBaseAdapter(fake, {"test": ("fake", "fake")}), gate, ledger
                )
                for _ in range(2):
                    await trusted_recovery_scope(f.config, settings(f), window, new, claim=False)
                    assert await store.dispatch_one() == "verified"
                assert await store.dispatch_one() == "idle"
                assert [c[0] for c in fake.calls] == ["query", "query", "update", "query"]
                assert len(fake.rows) == 1 and fake.rows[0]["fields"]["SyncVersion"] == 2
            finally:
                await session.close(clean=True)

        asyncio.run(run())
        assert preserved(f) == before
        with connect(f.config.database) as db:
            assert db.execute(
                "SELECT version,status FROM business.p4_base_deliveries ORDER BY version"
            ).fetchall() == [
                {"version": 1, "status": "verified"},
                {"version": 2, "status": "verified"},
            ]
            assert db.execute("SELECT count(*) AS n FROM business.p4_im_deliveries").fetchone() == {
                "n": 0
            }
        with pytest.raises(PermissionError):
            asyncio.run(trusted_scope(f.config, settings(f), window))
    finally:
        stop_gateway(f, new, replacement)


@pytest.mark.parametrize(
    "change",
    [
        "receipt",
        "plan_hash",
        "execution",
        "old_gateway",
        "gateway_end",
        "worker_end",
        "original_sdk",
        "token",
        "role",
    ],
)
def test_rebound_or_unterminated_original_and_current_permission_fail_before_new_sdk(
    fixture: P3Fixture,
    change: str,
) -> None:
    f = fixture
    window, new, replacement, _ = prepared(f)
    try:
        assert window.recovery
        recovery = window.recovery
        key = {
            "receipt": "receipt_hash",
            "plan_hash": "plan_hash",
            "execution": "execution_id",
            "old_gateway": "original_gateway_hash",
            "gateway_end": "gateway_termination_id",
            "worker_end": "worker_termination_id",
            "original_sdk": "original_sdk_window_hash",
        }.get(change)
        if key:
            recovery = recovery.model_copy(update={key: "0" * 64 if "hash" in key else uuid4()})
        elif change == "token":
            projection = recovery.projections[0].model_copy(update={"client_token": uuid4()})
            recovery = recovery.model_copy(
                update={"projections": (projection, *recovery.projections[1:])}
            )
        else:
            with connect(f.inventory.owner) as db:
                db.execute(
                    "UPDATE business.principal_role_shop_grants SET enabled=false "
                    "WHERE role='approver'"
                )
        amended = window.model_copy(update={"recovery": recovery})
        before = preserved(f)
        with pytest.raises(PermissionError):
            asyncio.run(trusted_scope(f.config, settings(f), amended))
        assert preserved(f) == before
        with connect(f.config.database) as db:
            assert db.execute(
                "SELECT count(*) AS n FROM business.p4_sdk_calls WHERE window_id=%s",
                (window.window_id,),
            ).fetchone() == {"n": 0}
            assert db.execute(
                "SELECT count(*) AS n FROM business.audit_events WHERE id=%s", (window.window_id,)
            ).fetchone() == {"n": 0}
    finally:
        stop_gateway(f, new, replacement)
