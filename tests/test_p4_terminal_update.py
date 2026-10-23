"""terminal update 的严格边界；旧RO序列化和写权限不扩大。"""

import json
from typing import Any
from uuid import uuid4

import pytest
from commerceops.application.feishu_business.worker_window import (
    RECOVERY_CAPS,
    ControlledWorkerWindow,
)

from tests.test_p4_a08_profiles import readonly_value

pytestmark = pytest.mark.offline


def terminal_value() -> tuple[Any, dict[str, Any]]:
    settings, prior = readonly_value()
    recovery = prior["recovery"]
    recovery["explicit_ro_recheck"] = dict(
        recheck_count=1,
        reader_gateway=dict(
            gateway_id=str(uuid4()), gateway_hash="a" * 64, termination_id=str(uuid4())
        ),
        reader_window_id=str(uuid4()),
        reader_window_hash="b" * 64,
        reader_claim_hash="c" * 64,
        reader_owner=str(uuid4()),
        reader_termination_id=str(uuid4()),
    )
    value = dict(prior)
    value.update(
        window_id=str(uuid4()),
        gateway_window_id=str(uuid4()),
        profile="terminal_update",
        caps=dict(RECOVERY_CAPS),
        recovery=None,
    )
    projection = dict(recovery["projections"][0])
    projection.update(outbox_id=str(uuid4()), client_token=str(uuid4()), version=2)
    value["terminal_update"] = dict(
        schema_version="p4-terminal-update-v1",
        worker_window_id=value["window_id"],
        gateway_window_id=value["gateway_window_id"],
        expires_at=value["expires_at"],
        verified_recovery=recovery,
        verified_sdk_window_hash="a" * 64,
        verified_gateway_hash="b" * 64,
        verified_gateway_termination_id=str(uuid4()),
        verified_worker_owner=str(uuid4()),
        verified_worker_termination_id=str(uuid4()),
        external_id="synthetic-original-record",
        projection=projection,
        request_key=str(uuid4()),
        semantic_hash="c" * 64,
        resolution_id=str(uuid4()),
        resolver_id=str(uuid4()),
        resolver_identity_id=str(uuid4()),
        resolver_auth_version=1,
    )
    return settings, value


def test_terminal_update_has_exact_six_methods11_and_no_legacy_field_changes() -> None:
    settings, value = terminal_value()
    checked = ControlledWorkerWindow.model_validate_json(json.dumps(value))
    assert checked.window(settings).caps == RECOVERY_CAPS
    assert sum(checked.caps.values()) == 11
    settings, legacy = readonly_value()
    checked = ControlledWorkerWindow.model_validate_json(json.dumps(legacy))
    assert "terminal_update" not in checked.model_dump(mode="json")
    from commerceops.application.feishu_business.recovery import ApprovedOutboxRecovery

    legacy["recovery"] = ApprovedOutboxRecovery.model_validate_json(
        json.dumps(legacy["recovery"])
    ).model_dump(mode="json")
    assert checked.model_dump(mode="json") == legacy


@pytest.mark.parametrize(
    "change",
    [
        "create",
        "im",
        "update2",
        "bool",
        "partialcaps",
        "wrong_task",
        "wrong_target",
        "wrong_window",
        "wrong_gateway",
        "wrong_expiry",
        "same_outbox",
        "same_token",
        "wrong_item",
        "v1",
        "no_sender",
        "no_explicit",
        "extra",
        "as_workflow",
        "off",
        "wrong_schema",
        "resolver_bool",
    ],
)
def test_terminal_write_is_not_admitted_by_partial_or_rebound_authority(change: str) -> None:
    settings, value = terminal_value()
    terminal = value["terminal_update"]
    if change in ("create", "im"):
        value["caps"][
            "bitable.v1.app_table_record.create" if change == "create" else "im.v1.message.create"
        ] = 1
    elif change in ("update2", "bool"):
        value["caps"]["bitable.v1.app_table_record.update"] = 2 if change == "update2" else True
    elif change == "partialcaps":
        value["caps"].pop("bitable.v1.app_table.list")
    elif change == "wrong_task":
        value["task_ids"] = [str(uuid4())]
    elif change == "wrong_target":
        terminal["verified_recovery"]["target_key"] = "synthetic-rebound"
    elif change in ("wrong_window", "wrong_gateway"):
        terminal["worker_window_id" if change == "wrong_window" else "gateway_window_id"] = str(
            uuid4()
        )
    elif change == "wrong_expiry":
        terminal["expires_at"] = "2020-01-01T00:00:00Z"
    elif change in ("same_outbox", "same_token"):
        key = "outbox_id" if change == "same_outbox" else "client_token"
        terminal["projection"][key] = terminal["verified_recovery"]["projections"][0][key]
    elif change == "wrong_item":
        terminal["projection"]["item_id"] = str(uuid4())
    elif change == "v1":
        terminal["projection"]["version"] = 1
    elif change in ("no_sender", "no_explicit"):
        terminal["verified_recovery"][
            "sender_gateway" if change == "no_sender" else "explicit_ro_recheck"
        ] = None
    elif change == "extra":
        terminal["privileged"] = True
    elif change == "as_workflow":
        value["profile"] = "approved_workflow"
    elif change == "off":
        value["enabled"] = False
    elif change == "wrong_schema":
        terminal["schema_version"] = "p4-approved-outbox-v1"
    else:
        terminal["resolver_auth_version"] = True
    with pytest.raises((ValueError, PermissionError)):
        ControlledWorkerWindow.model_validate_json(json.dumps(value)).window(settings)
