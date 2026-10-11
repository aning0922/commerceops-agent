"""跨 Gateway 单原任务 manifest/profile 的闭合与有限预算。"""

import json
from typing import Any
from uuid import uuid4

import pytest
from commerceops.application.feishu_business.worker_window import (
    GROUP20_CAPS,
    ControlledWorkerWindow,
)

from tests.test_p4_controlled_worker import configured

pytestmark = pytest.mark.offline


def value() -> dict[str, Any]:
    settings, window, _ = configured()
    task = next(iter(window.task_ids))
    result = window.model_dump(mode="json")
    result.update(profile="approved_workflow", caps=dict(GROUP20_CAPS))
    result["workflow_recovery"] = {
        "schema_version": "p4-approved-workflow-v1",
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
        "task_version": 1,
        "task_binding_hash": "a" * 64,
        "inbox_id": str(uuid4()),
        "receipt_hash": "a" * 64,
        "operator_auth_version": 1,
        "approval_id": None,
        "approval_binding_hash": None,
        "decision_id": None,
        "decision_payload_hash": None,
        "execution_id": None,
        "target_key": settings.base_target_key,
    }
    return result


@pytest.mark.parametrize(
    "change",
    [
        "none",
        "missing",
        "many",
        "same_gateway",
        "same_sdk",
        "approval_pair",
        "decision_pair",
        "execution",
        "cap",
        "extra",
        "wrong_profile",
    ],
)
def test_workflow_recovery_requires_original_single_scope_and_finite_profile(change: str) -> None:
    settings, _, _ = configured()
    amended = value()
    recovery = amended["workflow_recovery"]
    if change == "none":
        checked = ControlledWorkerWindow.model_validate_json(json.dumps(amended)).window(settings)
        assert sum(checked.caps.values()) == 73
        return
    if change == "missing":
        amended["workflow_recovery"] = None
    elif change == "many":
        amended["task_ids"].append(str(uuid4()))
    elif change == "same_gateway":
        recovery["original_gateway_id"] = recovery["gateway_window_id"]
    elif change == "same_sdk":
        recovery["original_sdk_window_id"] = recovery["worker_window_id"]
    elif change == "approval_pair":
        recovery["approval_binding_hash"] = "a" * 64
    elif change == "decision_pair":
        recovery["decision_id"] = str(uuid4())
    elif change == "execution":
        recovery["execution_id"] = str(uuid4())
    elif change == "cap":
        amended["caps"]["bitable.v1.app_table_record.create"] = 21
    elif change == "extra":
        recovery["new_task"] = True
    else:
        amended["profile"] = "group20"
    with pytest.raises((ValueError, PermissionError)):
        ControlledWorkerWindow.model_validate_json(json.dumps(amended)).window(settings)
