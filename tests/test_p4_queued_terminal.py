"""新queued-v1来源显式区分旧RO，保留原terminal精确权限。"""

import json
from typing import Any
from uuid import uuid4

import pytest
from commerceops.application.feishu_business.worker_window import ControlledWorkerWindow

from tests.test_p4_queued_start import queued_manifest
from tests.test_p4_terminal_update import terminal_value

pytestmark = pytest.mark.offline


def queued_terminal_value() -> tuple[Any, dict[str, Any]]:
    settings, queued = queued_manifest()
    _, value = terminal_value()
    terminal = value["terminal_update"]
    old = terminal["verified_recovery"]
    source = {
        key: old[key]
        for key in (
            "task_version",
            "plan_id",
            "plan_version",
            "plan_hash",
            "approval_id",
            "decision_id",
            "execution_id",
            "approver_auth_version",
            "projections",
        )
    }
    source.update(
        schema_version="p4-verified-queued-v1",
        queued_start=queued["queued_start"],
        operator_auth_version=queued["queued_start"]["operator_auth_version"],
    )
    terminal["verified_recovery"] = source
    value["task_ids"] = queued["task_ids"]
    value["expires_at"] = terminal["expires_at"] = queued["expires_at"]
    return settings, value


def test_explicit_queued_v1_source_is_distinct_and_keeps_terminal_caps() -> None:
    settings, value = queued_terminal_value()
    window = ControlledWorkerWindow.model_validate_json(json.dumps(value))
    assert sum(window.window(settings).caps.values()) == 11
    assert window.requires_sealed_source
    source = window.terminal_update
    assert source is not None
    assert str(source.verified_recovery.task_id) == value["task_ids"][0]
    assert source.verified_recovery.projections[0].version == 1
    assert ControlledWorkerWindow.model_validate_json(window.model_dump_json()) == window
    legacy_settings, legacy = terminal_value()
    old = ControlledWorkerWindow.model_validate_json(json.dumps(legacy))
    old.window(legacy_settings)
    assert not old.requires_sealed_source


@pytest.mark.parametrize(
    "change",
    [
        "legacy_tag",
        "sender",
        "explicit_ro",
        "missing_queued",
        "auth",
        "bool_auth",
        "v2_anchor",
        "two_anchors",
        "same_gateway",
        "same_original_gateway",
        "same_worker",
        "same_outbox",
        "same_token",
        "different_item",
        "different_target",
        "other_profile",
    ],
)
def test_queued_terminal_cannot_fabricate_ro_or_rebind_original(change: str) -> None:
    settings, value = queued_terminal_value()
    terminal = value["terminal_update"]
    source = terminal["verified_recovery"]
    if change == "legacy_tag":
        source["schema_version"] = "p4-approved-outbox-v1"
    elif change in ("sender", "explicit_ro"):
        source["sender_gateway" if change == "sender" else "explicit_ro_recheck"] = None
    elif change == "missing_queued":
        source.pop("queued_start")
    elif change in ("auth", "bool_auth"):
        source["operator_auth_version"] = 999 if change == "auth" else True
    elif change == "v2_anchor":
        source["projections"][0]["version"] = 2
    elif change == "two_anchors":
        source["projections"].append(dict(source["projections"][0]))
    elif change in ("same_gateway", "same_original_gateway", "same_worker"):
        key = "worker_window_id" if change == "same_worker" else "gateway_window_id"
        original_field = "original_gateway_id" if change == "same_original_gateway" else key
        terminal[key] = source["queued_start"][original_field]
        value["window_id" if key == "worker_window_id" else key] = terminal[key]
    elif change in ("same_outbox", "same_token"):
        key = "outbox_id" if change == "same_outbox" else "client_token"
        terminal["projection"][key] = source["projections"][0][key]
    elif change == "different_item":
        terminal["projection"]["item_id"] = str(uuid4())
    elif change == "different_target":
        source["queued_start"]["target_key"] = "synthetic-other-target"
    else:
        value["profile"] = "approved_queued_start"
    with pytest.raises((ValueError, PermissionError)):
        ControlledWorkerWindow.model_validate_json(json.dumps(value)).window(settings)
