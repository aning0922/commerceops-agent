"""跨实际 Gateway 子进程的原 workflow 恢复；账本 Fake、实际 SDK/secret0。"""

import asyncio
import json
from typing import Any
from uuid import UUID, uuid4

import pytest
from commerceops.application.feishu_business.worker_window import (
    GROUP20_CAPS,
    ControlledWorkerWindow,
)
from commerceops.application.replenishment.contracts import WebFailure
from commerceops.domain.commerce_values import facts_hash
from commerceops.entrypoints.feishu_worker_child import trusted_scope
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_gateway_window import guard_gateway
from commerceops.infrastructure.feishu_outbox_recovery import receipt_hash, sdk_window_hash
from commerceops.infrastructure.feishu_workflow_recovery import (
    approval_binding_hash,
    task_binding_hash,
)
from commerceops.infrastructure.worker_lock import confirm_termination
from psycopg import sql

from tests.p3_support import P3Fixture, P3Process
from tests.p4_recovery_support import gateway, settings, start_gateway, stop_gateway
from tests.test_p3_approval_pg import checkpoint_state, wait_ready, wait_state
from tests.test_p3_execution_recovery_pg import wait_jobs
from tests.test_p3_pg import fixture as fixture
from tests.test_p4_a08_identity_pg import frozen
from tests.test_p4_a08_workflow_pg import ready_card
from tests.test_p4_gateway_pg import message, service

pytestmark = pytest.mark.integration


def manifest(
    f: P3Fixture, old: Any, new: Any, task: UUID, owner: str, sdk_id: UUID
) -> ControlledWorkerWindow:
    with connect(f.config.database) as db:
        task_row = db.execute(
            """SELECT t.*,s.source_task_id,s.parameters,s.config_version
            FROM business.business_tasks t JOIN business.p3_task_sources s ON s.task_id=t.id
            WHERE t.id=%s""",
            (task,),
        ).fetchone()
        receipt = db.execute(
            """SELECT r.*,i.payload_hash FROM business.p4_inbox_receipts r
            JOIN business.inbox_events i ON i.id=r.inbox_id WHERE i.task_id=%s
            AND i.sanitized_payload->>'event_type'='im.message.receive_v1'""",
            (task,),
        ).fetchone()
        claim = db.execute(
            "SELECT after_state FROM business.audit_events WHERE id=%s", (old.window_id,)
        ).fetchone()
        gateway_end = db.execute(
            """SELECT id FROM business.audit_events WHERE source='feishu_gateway'
            AND entity_id=%s AND action='termination_confirmed'""",
            (str(old.window_id),),
        ).fetchone()
        worker_end = db.execute(
            """SELECT id FROM business.audit_events WHERE source='worker'
            AND entity_id=%s AND action='termination_confirmed'""",
            (owner,),
        ).fetchone()
        sdk = db.execute("SELECT * FROM business.p4_sdk_windows WHERE id=%s", (sdk_id,)).fetchone()
        approval = db.execute(
            "SELECT * FROM business.approvals WHERE task_id=%s", (task,)
        ).fetchone()
        execution = db.execute(
            "SELECT id FROM business.executions WHERE task_id=%s", (task,)
        ).fetchone()
        assert task_row and receipt and claim and gateway_end and worker_end and sdk
        operator = db.execute(
            "SELECT auth_version FROM business.principals WHERE id=%s", (task_row["requester_id"],)
        ).fetchone()
        assert operator
    window_id = uuid4()
    return ControlledWorkerWindow.model_validate_json(
        json.dumps(
            {
                "schema_version": "p4-worker-v1",
                "window_id": str(window_id),
                "gateway_window_id": str(new.window_id),
                "organization_id": str(f.actor.organization_id),
                "shop_id": str(f.inventory.data.shop),
                "task_ids": [str(task)],
                "expires_at": new.expires_at.isoformat(),
                "enabled": True,
                "profile": "approved_workflow",
                "caps": dict(GROUP20_CAPS),
                "workflow_recovery": {
                    "schema_version": "p4-approved-workflow-v1",
                    "worker_window_id": str(window_id),
                    "gateway_window_id": str(new.window_id),
                    "expires_at": new.expires_at.isoformat(),
                    "original_gateway_id": str(old.window_id),
                    "original_gateway_hash": facts_hash(claim["after_state"]),
                    "gateway_termination_id": str(gateway_end["id"]),
                    "worker_owner": owner,
                    "worker_termination_id": str(worker_end["id"]),
                    "original_sdk_window_id": str(sdk_id),
                    "original_sdk_window_hash": sdk_window_hash(sdk),
                    "task_id": str(task),
                    "task_version": task_row["version"],
                    "task_binding_hash": task_binding_hash(task_row),
                    "inbox_id": str(receipt["inbox_id"]),
                    "receipt_hash": receipt_hash(receipt),
                    "operator_auth_version": operator["auth_version"],
                    "approval_id": str(approval["id"]) if approval else None,
                    "approval_binding_hash": approval_binding_hash(approval) if approval else None,
                    "decision_id": str(approval["decision_id"])
                    if approval and approval["decision_id"]
                    else None,
                    "decision_payload_hash": approval["decision_payload_hash"]
                    if approval
                    else None,
                    "execution_id": str(execution["id"]) if execution else None,
                    "target_key": "test",
                },
            }
        )
    )


@pytest.mark.parametrize(
    "barrier",
    ["before_t2_commit", "after_t2_commit", "after_ready", "before_t4_commit", "after_t4_commit"],
)
def test_cross_gateway_original_five_boundaries_keep_plan_nonce_ttl_and_unique_execution(
    fixture: P3Fixture,
    barrier: str,
) -> None:
    f = fixture
    old = gateway(f, case="baseline", seconds=240, max_workflows=2)
    gateway_child = start_gateway(f, old)
    child = restored = replacement = None
    new = None
    try:
        store = service(
            f,
            allow_live_bindings=True,
            gateway_guard=lambda db, create: guard_gateway(db, old, create),
        )
        incoming = message(f, kind="group")
        task = UUID(store.message(incoming)["task_id"])
        old_window = ControlledWorkerWindow.model_validate_json(
            json.dumps(
                {
                    "schema_version": "p4-worker-v1",
                    "window_id": str(uuid4()),
                    "gateway_window_id": str(old.window_id),
                    "organization_id": str(f.actor.organization_id),
                    "shop_id": str(f.inventory.data.shop),
                    "task_ids": [str(task)],
                    "expires_at": old.expires_at.isoformat(),
                    "enabled": True,
                    "profile": "group20",
                    "caps": dict(GROUP20_CAPS),
                }
            )
        )
        scoped: dict[str, Any] = {
            "task_id": str(task),
            "p4_demo": True,
            "p4_ledger_stub": True,
            "p4_scope": {
                "window": old_window.model_dump(mode="json"),
                "settings": settings(f).model_dump(mode="json"),
            },
        }
        child = P3Process(f, "worker", scoped, barrier)
        owner = child.until("started")["owner"]
        before = None
        if barrier in ("before_t4_commit", "after_t4_commit"):
            child.until("after_ready")
            card, before = ready_card(f, task, incoming)
            store.card(card)
        child.until(barrier)
        if barrier in ("after_t2_commit", "after_ready"):
            card, before = ready_card(f, task, incoming)
            if barrier == "after_t2_commit":
                with pytest.raises(WebFailure, match="CARD_CONTEXT_MISMATCH"):
                    store.card(card)
        child.kill_reap()
        asyncio.run(
            confirm_termination(f.config.database, owner, "A09 owned original SIGKILL and wait=-9")
        )
        stop_gateway(f, old, gateway_child)
        with connect(f.config.database) as db:
            with pytest.raises(WebFailure, match="GATEWAY_WINDOW_CLOSED"):
                guard_gateway(db, old, False)
        new = gateway(f, case="baseline", max_workflows=0)
        replacement = start_gateway(f, new)
        recovered = manifest(f, old, new, task, owner, old_window.window_id)
        # 新 Gateway 不能借恢复入口接新 T1；拒绝本身零业务写入。
        resumed_store = service(
            f,
            allow_live_bindings=True,
            gateway_guard=lambda db, create: guard_gateway(db, new, create),
        )
        unchanged = frozen(f)
        with pytest.raises(WebFailure, match="GATEWAY_WORKFLOW_CAP_EXHAUSTED"):
            resumed_store.message(message(f, kind="group"))
        assert frozen(f) == unchanged
        scoped.pop("p4_ledger_stub")
        scoped["p4_scope"]["window"] = recovered.model_dump(mode="json")
        restored = P3Process(f, "worker", scoped, "never")
        restored.until("started")
        restored.until("workflow_scope_validated")
        if barrier not in ("before_t4_commit", "after_t4_commit"):
            wait_ready(f, task)
            card, current = ready_card(f, task, incoming)
            if before:
                assert current == before
            assert resumed_store.card(card)["decision_source"] == "feishu"
        wait_state(f, task, "completed", restoring=True)
        wait_jobs(f, task)
        snapshot = asyncio.run(checkpoint_state(f, task))
        assert not snapshot.next and not snapshot.interrupts
        with connect(f.config.database) as db:
            for table in ("replenishment_plans", "approvals", "executions"):
                assert db.execute(
                    sql.SQL("SELECT count(*) AS n FROM business.{} WHERE task_id=%s").format(
                        sql.Identifier(table)
                    ),
                    (task,),
                ).fetchone() == {"n": 1}
            items = db.execute(
                "SELECT quantity FROM business.replenishment_items WHERE task_id=%s", (task,)
            ).fetchall()
            assert len(items) == 20 and all(int(i["quantity"]) == 100 for i in items)
            assert db.execute(
                "SELECT count(*) AS n FROM business.outbox WHERE task_id=%s "
                "AND operation='item_projection'",
                (task,),
            ).fetchone() == {"n": 20}
            # 仅原窗口一个 Fake ledger auth 回执；没有实际 SDK 或新窗口调用。
            assert db.execute("SELECT count(*) AS n FROM business.p4_sdk_calls").fetchone() == {
                "n": 1
            }
    finally:
        if child and child.process.poll() is None:
            child.kill_reap()
        if restored and restored.process.poll() is None:
            restored.stop_clean()
        if replacement and new:
            stop_gateway(f, new, replacement)
        elif gateway_child.poll() is None:
            stop_gateway(f, old, gateway_child)


def test_cross_gateway_missing_original_proofs_identity_and_never_started_t1_are_denied(
    fixture: P3Fixture,
) -> None:
    f = fixture
    old = gateway(f, case="baseline", seconds=240, max_workflows=2)
    original = start_gateway(f, old)
    child = replacement = None
    new = None
    try:
        store = service(
            f,
            allow_live_bindings=True,
            gateway_guard=lambda db, create: guard_gateway(db, old, create),
        )
        task = UUID(store.message(message(f, kind="group"))["task_id"])
        old_window = ControlledWorkerWindow.model_validate_json(
            json.dumps(
                {
                    "schema_version": "p4-worker-v1",
                    "window_id": str(uuid4()),
                    "gateway_window_id": str(old.window_id),
                    "organization_id": str(f.actor.organization_id),
                    "shop_id": str(f.inventory.data.shop),
                    "task_ids": [str(task)],
                    "expires_at": old.expires_at.isoformat(),
                    "enabled": True,
                    "profile": "group20",
                    "caps": dict(GROUP20_CAPS),
                }
            )
        )
        child = P3Process(
            f,
            "worker",
            {
                "task_id": str(task),
                "p4_demo": True,
                "p4_ledger_stub": True,
                "p4_scope": {
                    "window": old_window.model_dump(mode="json"),
                    "settings": settings(f).model_dump(mode="json"),
                },
            },
            "after_ready",
        )
        owner = child.until("started")["owner"]
        child.until("after_ready")
        queued = UUID(store.message(message(f, kind="group"))["task_id"])
        child.kill_reap()
        asyncio.run(
            confirm_termination(f.config.database, owner, "A09 negative owned SIGKILL/wait=-9")
        )
        stop_gateway(f, old, original)
        new = gateway(f, case="baseline", max_workflows=0)
        replacement = start_gateway(f, new)
        valid = manifest(f, old, new, task, owner, old_window.window_id)
        assert valid.workflow_recovery is not None
        baseline = frozen(f)
        for field in (
            "original_gateway_hash",
            "gateway_termination_id",
            "worker_termination_id",
            "original_sdk_window_hash",
            "task_binding_hash",
            "receipt_hash",
            "approval_binding_hash",
            "approval_id",
            "task_version",
        ):
            value = valid.model_dump(mode="json")
            value["workflow_recovery"][field] = (
                "0" * 64
                if field.endswith("hash")
                else valid.workflow_recovery.task_version + 1
                if field == "task_version"
                else str(uuid4())
            )
            with pytest.raises(PermissionError):
                asyncio.run(
                    trusted_scope(
                        f.config,
                        settings(f),
                        ControlledWorkerWindow.model_validate_json(json.dumps(value)),
                    )
                )
            assert frozen(f) == baseline
        for field, field_value in (
            ("app_id", "other-app"),
            ("tenant_key", "other-tenant"),
            ("allowed_open_ids", ["other-user"]),
        ):
            config = settings(f).model_dump(mode="json")
            config[field] = field_value
            with pytest.raises(PermissionError):
                asyncio.run(
                    trusted_scope(
                        f.config, type(settings(f)).model_validate_json(json.dumps(config)), valid
                    )
                )
            assert frozen(f) == baseline
        never_started = manifest(f, old, new, queued, owner, old_window.window_id)
        with pytest.raises(PermissionError):
            asyncio.run(trusted_scope(f.config, settings(f), never_started))
        assert frozen(f) == baseline
        with connect(f.inventory.owner) as db:
            db.execute(
                "UPDATE business.principal_role_shop_grants SET enabled=false "
                "WHERE principal_id=%s AND role='operator'",
                (f.actor.principal_id,),
            )
        baseline = frozen(f)
        with pytest.raises(PermissionError):
            asyncio.run(trusted_scope(f.config, settings(f), valid))
        assert frozen(f) == baseline
        with connect(f.config.database) as db:
            assert db.execute(
                "SELECT count(*) AS n FROM business.audit_events WHERE source='feishu_recovery'"
            ).fetchone() == {"n": 0}
    finally:
        if child and child.process.poll() is None:
            child.kill_reap()
        if replacement and new:
            stop_gateway(f, new, replacement)
        elif original.poll() is None:
            stop_gateway(f, old, original)
