"""Explicit long group operation admission; no database, SDK, network or secret."""

import json
import os
import socket
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.application.feishu_business.gateway_window import GatewayWindow
from commerceops.application.feishu_business.worker_window import ControlledWorkerWindow
from commerceops.entrypoints.feishu_business import require_group_ready_scope
from commerceops.infrastructure.worker_lock import process_namespace
from pydantic import ValidationError
from pytest import MonkeyPatch

from tests.test_p4_controlled_worker import configured

pytestmark = pytest.mark.offline


def operation(seconds: int = 540) -> tuple[BusinessSettings, ControlledWorkerWindow, GatewayWindow]:
    settings, original, _ = configured()
    settings = settings.model_copy(
        update={
            "allowed_group_chat_ids": frozenset({"owned-group"}),
            "allowed_open_ids": frozenset({"owned-A", "owned-B"}),
        }
    )
    expiry = datetime.now(UTC) + timedelta(seconds=seconds)
    value = original.model_dump(mode="json")
    value.update(
        expires_at=expiry.isoformat(),
        profile="approved_workflow",
        group_operation_chat_id="owned-group",
    )
    value["caps"].pop("bitable.v1.app_table_record.update")
    task = value["task_ids"][0]
    recovery = dict(
        schema_version="p4-approved-workflow-v1",
        worker_window_id=value["window_id"],
        gateway_window_id=value["gateway_window_id"],
        expires_at=expiry.isoformat(),
        original_gateway_id=str(uuid4()),
        original_gateway_hash="a" * 64,
        gateway_termination_id=str(uuid4()),
        worker_owner=str(uuid4()),
        worker_termination_id=str(uuid4()),
        original_sdk_window_id=str(uuid4()),
        original_sdk_window_hash="b" * 64,
        task_id=task,
        task_version=1,
        task_binding_hash="c" * 64,
        inbox_id=str(uuid4()),
        receipt_hash="d" * 64,
        operator_auth_version=1,
        approval_id=str(uuid4()),
        approval_binding_hash="e" * 64,
        decision_id=None,
        decision_payload_hash=None,
        execution_id=None,
        target_key=settings.base_target_key,
    )
    value["workflow_recovery"] = recovery
    worker = ControlledWorkerWindow.model_validate_json(json.dumps(value))
    gateway = GatewayWindow.model_validate_json(
        json.dumps(
            dict(
                schema_version="p4-gateway-v1",
                window_id=value["gateway_window_id"],
                organization_id=value["organization_id"],
                shop_id=value["shop_id"],
                expires_at=expiry.isoformat(),
                max_workflows=0,
                max_callbacks=14,
                enabled=True,
                group_operation_chat_id="owned-group",
                parameters=dict(
                    source_mode="mock",
                    dataset_version="inventory-v1",
                    fixture_case="baseline",
                    L=3,
                    R=7,
                    S=2,
                ),
            )
        )
    )
    return settings, worker, gateway


def test_only_explicit_bound_group_operation_accepts_540_seconds() -> None:
    settings, worker, gateway = operation()
    assert not gateway.active()
    assert gateway.active(group_operation=True)
    require_group_ready_scope(settings, gateway)
    assert worker.window(settings).expires_at == gateway.expires_at
    assert "bitable.v1.app_table_record.update" not in worker.caps


@pytest.mark.parametrize("seconds", [601, 0, -1])
def test_long_operation_still_rejects_outside_absolute_bound(seconds: int) -> None:
    settings, worker, gateway = operation(seconds)
    assert not gateway.active(group_operation=True)
    with pytest.raises(PermissionError):
        worker.window(settings)


@pytest.mark.parametrize(
    "change", ["default", "other_chat", "no_group", "one_actor", "f02", "update"]
)
def test_long_worker_rejects_default_or_wrong_scope_before_factory(change: str) -> None:
    settings, worker, _ = operation()
    if change == "default":
        worker = worker.model_copy(update={"group_operation_chat_id": None})
    elif change == "other_chat":
        worker = worker.model_copy(update={"group_operation_chat_id": "other-group"})
    elif change == "no_group":
        settings = settings.model_copy(update={"allowed_group_chat_ids": frozenset()})
    elif change == "one_actor":
        settings = settings.model_copy(update={"allowed_open_ids": frozenset({"owned-A"})})
    elif change == "f02":
        settings = settings.model_copy(update={"f02_enabled": True})
    else:
        worker = worker.model_copy(
            update={"caps": {**worker.caps, "bitable.v1.app_table_record.update": 1}}
        )
    with pytest.raises(PermissionError):
        worker.window(settings)


@pytest.mark.parametrize(
    "profile",
    [
        "known70",
        "group20",
        "approved_outbox",
        "approved_first_create",
        "terminal_update",
        "approved_queued_start",
    ],
)
def test_no_other_profile_inherits_long_admission(profile: str) -> None:
    settings, worker, _ = operation()
    with pytest.raises(PermissionError):
        worker.model_copy(update={"profile": profile}).window(settings)


def test_long_gateway_cannot_create_workflows_or_accept_other_group() -> None:
    settings, _, gateway = operation()
    with pytest.raises(ValidationError):
        GatewayWindow.model_validate(gateway.model_copy(update={"max_workflows": 1}).model_dump())
    with pytest.raises(ValidationError):
        GatewayWindow.model_validate(gateway.model_copy(update={"max_callbacks": 15}).model_dump())
    with pytest.raises(PermissionError):
        require_group_ready_scope(
            settings.model_copy(update={"allowed_group_chat_ids": frozenset({"other"})}), gateway
        )


def test_old_default_claims_remain_byte_shape_compatible() -> None:
    _, worker, gateway = operation(120)
    for original in (worker, gateway):
        old = original.model_copy(update={"group_operation_chat_id": None}).model_dump(mode="json")
        assert "group_operation_chat_id" not in old
        decoded = type(original).model_validate_json(json.dumps(old))
        assert decoded.model_dump(mode="json") == old


def test_native_ready_receipt_uses_the_explicit_long_scope(monkeypatch: MonkeyPatch) -> None:
    from commerceops.infrastructure import feishu_gateway_ready as ready

    _, _, gateway = operation()
    _, _, config = configured()
    process = dict(pid=os.getpid(), host=socket.gethostname(), pid_namespace=process_namespace())
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.return_value.fetchall.return_value = [{"after_state": process}]
    monkeypatch.setattr(ready, "connect", lambda settings: connection)
    ready.gateway_transport_event(config, gateway, lost=False)
    assert connection.execute.call_args.args[1][2] == "ready"
    with pytest.raises(PermissionError, match="P4_QUEUED_GATEWAY_PROCESS_REQUIRED"):
        ready.gateway_transport_event(
            config, gateway.model_copy(update={"group_operation_chat_id": None}), lost=False
        )
