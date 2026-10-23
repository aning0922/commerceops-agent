"""原terminal unknown的独立一次准入；复用PG/audit/SDK账本，不重置旧状态。"""

import json
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from commerceops.application.feishu_business.worker_window import ControlledWorkerWindow
from commerceops.domain.commerce_values import facts_hash
from commerceops.infrastructure.web_sessions import json_native


def recovery_once_id(window: ControlledWorkerWindow, *, dispatched: bool = False) -> UUID:
    terminal = window.terminal_update
    if terminal is None or terminal.recovery_of is None:
        raise PermissionError("P4_TERMINAL_RECOVERY_REQUIRED")
    stage = "dispatched" if dispatched else "authorized"
    return uuid5(
        NAMESPACE_URL,
        f"commerceops:p4:terminal-recovery:{terminal.projection.outbox_id}:"
        f"{terminal.recovery_of.failed_window_id}:1:{stage}",
    )


def state_hash(row: dict[str, Any]) -> str:
    return facts_hash(json_native({key: value for key, value in row.items() if key != "anchor"}))


async def failed_terminal_source(
    db: Any, window: ControlledWorkerWindow, delivery: dict[str, Any], before: Any
) -> None:
    """锁内重核已结束的原一次失败，完整ledger必须全成功且update/create/IM均0。"""
    from commerceops.infrastructure.feishu_outbox_recovery import (
        _terminal_closed,
        sdk_window_hash,
        terminal_authorization_id,
        terminal_denied,
    )

    terminal = window.terminal_update
    if terminal is None or terminal.recovery_of is None:
        terminal_denied()
    recovery = terminal.recovery_of
    cur = await db.execute(
        "SELECT after_state FROM business.audit_events WHERE id=%s AND organization_id=%s "
        "AND task_id=%s AND source='feishu_recovery' AND action='terminal_update_authorized' "
        "AND entity_type='outbox' AND entity_id=%s",
        (
            terminal_authorization_id(terminal.projection.outbox_id),
            window.organization_id,
            terminal.verified_recovery.task_id,
            str(terminal.projection.outbox_id),
        ),
    )
    authorization = await cur.fetchone()
    if not authorization or facts_hash(authorization["after_state"]) != recovery.failed_window_hash:
        terminal_denied()
    prior = ControlledWorkerWindow.model_validate_json(json.dumps(authorization["after_state"]))
    old = prior.terminal_update
    excluded = {"worker_window_id", "gateway_window_id", "expires_at", "recovery_of"}
    if (
        old is None
        or old.recovery_of is not None
        or old.model_dump(exclude=excluded) != terminal.model_dump(exclude=excluded)
        or prior.window_id != recovery.failed_window_id
        or prior.window_id == window.window_id
        or prior.gateway_window_id == window.gateway_window_id
        or prior.profile != "terminal_update"
        or not prior.enabled
        or prior.caps != window.caps
        or (prior.organization_id, prior.shop_id, prior.task_ids)
        != (window.organization_id, window.shop_id, window.task_ids)
    ):
        terminal_denied()
    cur = await db.execute(
        "SELECT after_state FROM business.audit_events WHERE id=%s AND organization_id=%s "
        "AND source='feishu_gateway' AND action='gateway_start_claimed'",
        (prior.gateway_window_id, window.organization_id),
    )
    gateway = await cur.fetchone()
    if not gateway or facts_hash(gateway["after_state"]) != recovery.failed_gateway_hash:
        terminal_denied()
    await _terminal_closed(
        db,
        window.organization_id,
        "feishu_gateway",
        "gateway_runtime",
        str(prior.gateway_window_id),
        recovery.failed_gateway_termination_id,
        before,
    )
    await _terminal_closed(
        db,
        window.organization_id,
        "worker",
        "worker_runtime",
        str(recovery.failed_worker_owner),
        recovery.failed_worker_termination_id,
        before,
    )
    cur = await db.execute(
        "SELECT * FROM business.p4_sdk_windows WHERE id=%s FOR SHARE",
        (prior.window_id,),
    )
    sdk = await cur.fetchone()
    if (
        not sdk
        or sdk_window_hash(sdk) != recovery.failed_sdk_window_hash
        or sdk["method_caps"] != prior.caps
        or not sdk["configured_enabled"]
        or sdk["verification_mode"] != "controlled_sdk"
        or (sdk["organization_id"], sdk["shop_id"], sdk["expires_at"])
        != (prior.organization_id, prior.shop_id, prior.expires_at)
    ):
        terminal_denied()
    cur = await db.execute(
        "SELECT * FROM business.p4_sdk_calls WHERE window_id=%s ORDER BY id FOR SHARE",
        (prior.window_id,),
    )
    calls = await cur.fetchall()
    preflight = {
        "auth.v3.tenant_access_token.internal",
        "bot.v3.info",
        "bitable.v1.app_table.list",
        "bitable.v1.app_table_field.list",
    }
    methods = preflight | {"bitable.v1.app_table_record.list"}
    if (
        facts_hash(json_native(calls)) != recovery.failed_ledger_hash
        or len(calls) != len(methods)
        or {row["method"] for row in calls} != methods
        or any(
            row["status"] != "returned"
            or row["http_status"] != 200
            or row["provider_code"] != 0
            or row["completed_at"] is None
            or not row["started_at"] <= row["completed_at"] < before
            or row["started_at"] >= prior.expires_at
            or row["scope_kind"]
            != ("preflight" if row["method"] in preflight else "base_projection")
            or row["subject_id"]
            != (prior.window_id if row["method"] in preflight else terminal.projection.outbox_id)
            or row["task_id"]
            != (None if row["method"] in preflight else terminal.verified_recovery.task_id)
            for row in calls
        )
    ):
        terminal_denied()
    expected = dict(
        outbox_id=terminal.projection.outbox_id,
        version=2,
        status="unknown",
        attempts=1,
        last_operation="update",
        last_error="INCOMPLETE_READBACK",
        external_id=None,
        observed_version=None,
        complete_unique_verified=False,
        claimed_by=str(recovery.failed_worker_owner),
        verification_mode="controlled_sdk",
    )
    if any(delivery.get(key) != value for key, value in expected.items()) or (
        state_hash(delivery) != recovery.failed_delivery_hash
    ):
        terminal_denied()


async def recovery_authorized(db: Any, window: ControlledWorkerWindow) -> None:
    from commerceops.infrastructure.feishu_outbox_recovery import terminal_denied

    cur = await db.execute(
        "SELECT after_state FROM business.audit_events WHERE id=%s AND organization_id=%s "
        "AND source='feishu_recovery' AND action='terminal_recovery_authorized'",
        (recovery_once_id(window), window.organization_id),
    )
    row = await cur.fetchone()
    if not row or row["after_state"] != window.model_dump(mode="json"):
        terminal_denied()


async def dispatch_recovery(
    db: Any, window: ControlledWorkerWindow, row: dict[str, Any], owner: str
) -> None:
    from psycopg.types.json import Jsonb

    from commerceops.infrastructure.feishu_outbox_recovery import terminal_denied

    await recovery_authorized(db, window)
    if window.terminal_update is None or window.terminal_update.recovery_of is None:
        terminal_denied()
    if state_hash(row) != window.terminal_update.recovery_of.failed_delivery_hash:
        terminal_denied()
    cur = await db.execute(
        "INSERT INTO business.audit_events(id,organization_id,task_id,source,action,entity_type,"
        "entity_id,after_state,trace_id) VALUES(%s,%s,%s,'feishu_recovery',"
        "'terminal_recovery_dispatched','outbox',%s,%s,%s) ON CONFLICT(id) DO NOTHING RETURNING id",
        (
            recovery_once_id(window, dispatched=True),
            window.organization_id,
            row["task_id"],
            str(row["outbox_id"]),
            Jsonb(
                dict(
                    window=window.model_dump(mode="json"),
                    prior_delivery=json_native(
                        {key: value for key, value in row.items() if key != "anchor"}
                    ),
                    worker_owner=owner,
                    operation="read_first_conditional_update",
                )
            ),
            window.window_id,
        ),
    )
    if not await cur.fetchone():
        terminal_denied()
