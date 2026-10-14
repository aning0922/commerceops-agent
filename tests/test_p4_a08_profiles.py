"""A08有限profile准入，原known70/general边界保留；SDK/PG0。"""

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from commerceops.application.feishu_business.recovery import ApprovedOutboxRecovery
from commerceops.application.feishu_business.worker_window import (
    GROUP20_CAPS,
    READONLY_RECOVERY_CAPS,
    RECOVERY_CAPS,
    ControlledWorkerWindow,
)
from commerceops.infrastructure.worker import Worker

from tests.test_p4_controlled_worker import configured

pytestmark = pytest.mark.offline


def readonly_value() -> tuple[Any, dict[str, Any]]:
    settings, window, _ = configured()
    value = window.model_dump(mode="json")
    recovery = recovery_value()
    recovery.update(
        worker_window_id=str(window.window_id),
        gateway_window_id=str(window.gateway_window_id),
        expires_at=window.expires_at.isoformat(),
        task_id=str(next(iter(window.task_ids))),
        sender_gateway={
            "gateway_id": str(uuid4()),
            "gateway_hash": "b" * 64,
            "termination_id": str(uuid4()),
        },
    )
    value.update(profile="approved_outbox", caps=dict(READONLY_RECOVERY_CAPS), recovery=recovery)
    return settings, value


def test_sender_lineage_readonly_window_has_five_methods_total10() -> None:
    settings, value = readonly_value()
    checked = ControlledWorkerWindow.model_validate_json(json.dumps(value))
    assert dict(checked.window(settings).caps) == dict(READONLY_RECOVERY_CAPS)
    assert sum(checked.window(settings).caps.values()) == 10


@pytest.mark.parametrize(
    "method",
    [
        "bitable.v1.app_table_record.create",
        "bitable.v1.app_table_record.update",
        "im.v1.message.create",
    ],
)
def test_sender_lineage_rejects_every_remote_write_cap(method: str) -> None:
    settings, value = readonly_value()
    value["caps"][method] = 1
    with pytest.raises(PermissionError):
        ControlledWorkerWindow.model_validate_json(json.dumps(value)).window(settings)


@pytest.mark.parametrize("change", ["origin", "new", "two", "v2", "extra", "wrong_profile"])
def test_sender_lineage_closed_dto_binding(change: str) -> None:
    settings, value = readonly_value()
    recovery = value["recovery"]
    if change in ("origin", "new"):
        recovery["sender_gateway"]["gateway_id"] = recovery[
            "original_gateway_id" if change == "origin" else "gateway_window_id"
        ]
    elif change == "two":
        recovery["projections"].append(dict(recovery["projections"][0]))
    elif change == "v2":
        recovery["projections"][0]["version"] = 2
    elif change == "extra":
        recovery["sender_gateway"]["untrusted"] = True
    else:
        value["profile"] = "known70"
    with pytest.raises((ValueError, PermissionError)):
        ControlledWorkerWindow.model_validate_json(json.dumps(value)).window(settings)


def recovery_value() -> dict[str, Any]:
    settings, window, _ = configured()
    task = next(iter(window.task_ids))
    return {
        "schema_version": "p4-approved-outbox-v1",
        "worker_window_id": str(window.window_id),
        "gateway_window_id": str(window.gateway_window_id),
        "expires_at": window.expires_at.isoformat(),
        "original_gateway_id": str(uuid4()),
        "original_gateway_hash": "a" * 64,
        "gateway_termination_id": str(uuid4()),
        "worker_owner": str(uuid4()),
        "worker_termination_id": str(uuid4()),
        "original_sdk_window_id": str(uuid4()),
        "original_sdk_window_hash": "a" * 64,
        "task_id": str(task),
        "task_version": 4,
        "inbox_id": str(uuid4()),
        "receipt_hash": "a" * 64,
        "plan_id": str(uuid4()),
        "plan_version": 1,
        "plan_hash": "a" * 64,
        "approval_id": str(uuid4()),
        "decision_id": str(uuid4()),
        "execution_id": str(uuid4()),
        "operator_auth_version": 1,
        "approver_auth_version": 1,
        "target_key": settings.base_target_key,
        "projections": [
            {
                "outbox_id": str(uuid4()),
                "item_id": str(uuid4()),
                "client_token": str(uuid4()),
                "version": 1,
                "projection_hash": "a" * 64,
                "request_hash": "a" * 64,
            }
        ],
    }


@pytest.mark.parametrize(
    "profile,ceilings,total",
    [
        ("group20", GROUP20_CAPS, 73),
        ("approved_outbox", RECOVERY_CAPS, 11),
    ],
)
def test_named_profile_finite_ceiling_and_no_method_expansion(
    profile: str,
    ceilings: Any,
    total: int,
) -> None:
    settings, window, _ = configured()
    value = window.model_dump(mode="json")
    value.update(profile=profile, caps=dict(ceilings))
    if profile == "approved_outbox":
        recovery = recovery_value()
        recovery.update(
            worker_window_id=str(window.window_id),
            gateway_window_id=str(window.gateway_window_id),
            expires_at=window.expires_at.isoformat(),
            task_id=str(next(iter(window.task_ids))),
        )
        value["recovery"] = recovery
    checked = ControlledWorkerWindow.model_validate_json(json.dumps(value))
    assert sum(checked.window(settings).caps.values()) == total
    for method, ceiling in ceilings.items():
        amended = checked.model_dump(mode="json")
        amended["caps"][method] = ceiling + 1
        with pytest.raises(PermissionError):
            ControlledWorkerWindow.model_validate_json(json.dumps(amended)).window(settings)
    if profile == "approved_outbox":
        for method in ("im.v1.message.create", "bitable.v1.app_table_record.create"):
            amended = checked.model_dump(mode="json")
            amended["caps"][method] = 1
            with pytest.raises(PermissionError):
                ControlledWorkerWindow.model_validate_json(json.dumps(amended)).window(settings)


@pytest.mark.parametrize(
    "change",
    [
        "new_gateway_same",
        "version2_only",
        "two_items",
        "same_token",
        "same_outbox",
        "naive",
        "extra",
    ],
)
def test_recovery_manifest_forbids_rebound_window_keys_and_unordered_pair(change: str) -> None:
    value = recovery_value()
    if change == "new_gateway_same":
        value["original_gateway_id"] = value["gateway_window_id"]
    elif change == "version2_only":
        value["projections"][0]["version"] = 2
    elif change == "naive":
        value["expires_at"] = "2026-10-12T04:00:00"
    elif change == "extra":
        value["new_execution"] = True
    else:
        first = value["projections"][0]
        second = {**first, "outbox_id": str(uuid4()), "client_token": str(uuid4()), "version": 2}
        second[
            {"two_items": "item_id", "same_token": "client_token", "same_outbox": "outbox_id"}[
                change
            ]
        ] = (
            str(uuid4())
            if change == "two_items"
            else first["client_token" if change == "same_token" else "outbox_id"]
        )
        value["projections"].append(second)
    with pytest.raises(ValueError):
        ApprovedOutboxRecovery.model_validate_json(json.dumps(value))


def test_outbox_only_worker_never_recovers_or_claims_any_graph_job() -> None:
    async def run() -> None:
        session = type("Session", (), {"close": AsyncMock()})()
        runner = type("Runner", (), {"workflow_versions": frozenset(), "run": AsyncMock()})()
        stop = asyncio.Event()
        scans = []

        async def maintain() -> None:
            scans.append(1)
            if len(scans) == 2:
                stop.set()

        worker = Worker(
            session,
            runner,
            reconcile=maintain,
            dispatch_jobs=False,
            recovery_scan_seconds=1,
            poll_seconds=0.01,
        )
        queue = type("Queue", (), {"recover_confirmed": AsyncMock(), "claim": AsyncMock()})()
        worker.queue = queue
        await worker.run(stop)
        assert len(scans) == 2
        queue.recover_confirmed.assert_not_called()
        queue.claim.assert_not_called()
        runner.run.assert_not_called()
        session.close.assert_awaited_once_with(clean=True)

    asyncio.run(run())
