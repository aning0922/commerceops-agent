"""单原键 C0 profile；Fake 持久授权准入，不证明真实平台。"""

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from commerceops.application.feishu_business.delivery import DeliveryGate
from commerceops.application.feishu_business.worker_window import (
    FIRST_CREATE_CAPS,
    ControlledWorkerWindow,
)
from commerceops.infrastructure import feishu_first_create_recovery as recovery_module
from commerceops.infrastructure.feishu_first_create_recovery import admitted_first_create

from tests.test_p4_a09_workflow import value
from tests.test_p4_controlled_worker import configured

pytestmark = pytest.mark.offline


def candidate() -> dict[str, Any]:
    result = value()
    result.update(profile="approved_first_create", caps=dict(FIRST_CREATE_CAPS))
    result["first_create"] = {
        "outbox_id": str(uuid4()),
        "item_id": str(uuid4()),
        "client_token": str(uuid4()),
        "version": 1,
        "projection_hash": "a" * 64,
        "request_hash": "b" * 64,
    }
    recovery = result["workflow_recovery"]
    recovery.update(
        approval_id=str(uuid4()),
        approval_binding_hash="a" * 64,
        decision_id=str(uuid4()),
        decision_payload_hash="b" * 64,
        execution_id=str(uuid4()),
    )
    return result


@pytest.mark.parametrize(
    "change",
    [
        "none",
        "missing_projection",
        "v2",
        "create2",
        "im",
        "wrong_profile",
        "approval",
        "decision",
        "execution",
        "many",
        "wrong_task",
        "wrong_expiry",
    ],
)
def test_first_create_profile_is_single_original_completed_workflow(change: str) -> None:
    settings, _, _ = configured()
    spec = candidate()
    if change == "none":
        window = ControlledWorkerWindow.model_validate_json(json.dumps(spec)).window(settings)
        assert sum(window.caps.values()) == 12 and "im.v1.message.create" not in window.caps
        return
    if change == "missing_projection":
        spec["first_create"] = None
    elif change == "v2":
        spec["first_create"]["version"] = 2
    elif change == "create2":
        spec["caps"]["bitable.v1.app_table_record.create"] = 2
    elif change == "im":
        spec["caps"]["im.v1.message.create"] = 1
    elif change == "wrong_profile":
        spec["profile"] = "approved_workflow"
    elif change in ("approval", "decision", "execution"):
        spec["workflow_recovery"][change + "_id"] = None
    elif change == "many":
        spec["task_ids"].append(str(uuid4()))
    elif change == "wrong_task":
        spec["workflow_recovery"]["task_id"] = str(uuid4())
    else:
        spec["workflow_recovery"]["expires_at"] = "2020-01-01T00:00:00Z"
    with pytest.raises((ValueError, PermissionError)):
        ControlledWorkerWindow.model_validate_json(json.dumps(spec)).window(settings)


class DB:
    def __init__(self, state: Any, create: Any):
        self.results = [
            {"after_state": state} if state else None,
            create,
            {"occurred_at": "fixed-new-gateway-claim"},
        ]

    async def execute(self, *_: Any) -> "DB":
        return self

    async def fetchone(self) -> Any:
        return self.results.pop(0)


@pytest.mark.parametrize(
    "change",
    [
        "none",
        "no_claim",
        "bad_claim",
        "wrong_window",
        "wrong_key",
        "wrong_hash",
        "wrong_request",
        "v2",
        "attempt2",
        "different_error",
        "anchor",
        "pending",
        "last_reconcile",
        "started",
        "raised",
        "returned",
        "not_called",
        "ledger_caps",
        "ledger_org",
        "ledger_shop",
        "ledger_expiry",
        "ledger_off",
        "ledger_fake",
        "target",
        "old_sender_live",
    ],
)
def test_explicit_claim_original_row_and_all_create_statuses_gate_dispatch(
    change: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = candidate()
    window = ControlledWorkerWindow.model_validate_json(json.dumps(spec))
    projection = window.first_create
    assert projection and window.workflow_recovery
    gate = DeliveryGate(
        window.organization_id,
        window.shop_id,
        window.task_ids,
        window.workflow_recovery.target_key,
        window.expires_at,
        enabled=True,
        verification_mode="controlled_sdk",
        first_create=projection,
        first_create_window_id=window.window_id,
    )
    row: dict[str, Any] = {
        "outbox_id": projection.outbox_id,
        "item_id": projection.item_id,
        "client_token": projection.client_token,
        "projection_hash": projection.projection_hash,
        "version": 1,
        "status": "unknown",
        "attempts": 1,
        "anchor": None,
        "last_operation": "create",
        "last_error": "INCOMPLETE_READBACK",
        "task_id": next(iter(window.task_ids)),
    }
    state: Any = spec
    create = None
    if change == "no_claim":
        state = None
    elif change == "bad_claim":
        state = {"profile": "approved_first_create"}
    elif change == "wrong_window":
        gate = replace(gate, first_create_window_id=uuid4())
    elif change == "wrong_key":
        row["client_token"] = uuid4()
    elif change == "wrong_hash":
        row["projection_hash"] = "c" * 64
    elif change == "wrong_request":
        state["first_create"]["request_hash"] = "c" * 64
    elif change == "v2":
        row["version"] = 2
    elif change == "attempt2":
        row["attempts"] = 2
    elif change == "different_error":
        row["last_error"] = "BASE_WRITE_UNKNOWN"
    elif change == "anchor":
        row["anchor"] = "synthetic-anchor"
    elif change == "pending":
        row["status"] = "pending"
    elif change == "last_reconcile":
        row["last_operation"] = "reconcile"
    elif change in ("started", "raised", "returned", "not_called"):
        create = {"status": change}
    current_sdk = SimpleNamespace(
        window_id=UUID(spec["window_id"]),
        organization_id=window.organization_id,
        shop_id=window.shop_id,
        expires_at=window.expires_at,
        enabled=True,
        verification_mode="controlled_sdk",
        caps=dict(window.caps),
    )
    if change == "ledger_caps":
        current_sdk.caps["bitable.v1.app_table_record.create"] = 2
    elif change == "ledger_org":
        current_sdk.organization_id = uuid4()
    elif change == "ledger_shop":
        current_sdk.shop_id = uuid4()
    elif change == "ledger_expiry":
        from datetime import timedelta

        current_sdk.expires_at += timedelta(seconds=1)
    elif change == "ledger_off":
        current_sdk.enabled = False
    elif change == "ledger_fake":
        current_sdk.verification_mode = "offline_fake"
    elif change == "target":
        gate = replace(gate, target_key="other")
    checked = []

    async def closed(_: Any, selected: Any, claimed_at: Any) -> None:
        assert selected == window and claimed_at == "fixed-new-gateway-claim"
        checked.append(True)
        if change == "old_sender_live":
            raise PermissionError("P4_FIRST_CREATE_RECOVERY_DENIED")

    monkeypatch.setattr(recovery_module, "old_senders_closed", closed)
    ledger = SimpleNamespace(window=current_sdk)
    if change == "old_sender_live":
        with pytest.raises(PermissionError, match="P4_FIRST_CREATE_RECOVERY_DENIED"):
            asyncio.run(admitted_first_create(DB(state, create), gate, ledger, row))  # type: ignore[arg-type]
        assert checked == [True]
        return
    allowed = asyncio.run(admitted_first_create(DB(state, create), gate, ledger, row))  # type: ignore[arg-type]
    assert allowed is (change == "none")
    assert checked == ([True] if change == "none" else [])
