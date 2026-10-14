"""在原PG/audit与单Worker锁下复核显式原键恢复；绝不重执行T4。"""

import json
from enum import StrEnum
from typing import Any, NoReturn
from uuid import NAMESPACE_URL, UUID, uuid5

from psycopg.types.json import Jsonb

from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.application.feishu_business.gateway_window import GatewayWindow
from commerceops.application.feishu_business.worker_window import (
    FIRST_CREATE_CAPS,
    READONLY_RECOVERY_CAPS,
    ControlledWorkerWindow,
)
from commerceops.domain.commerce_values import facts_hash
from commerceops.infrastructure.feishu_base_delivery import item_snapshot
from commerceops.infrastructure.feishu_gateway_window import claimed_state
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.worker_lock import open_async, require_process_absent


def receipt_hash(row: dict[str, Any]) -> str:
    return facts_hash(
        {
            "inbox_id": str(row["inbox_id"]),
            "identity_id": str(row["identity_id"]),
            "payload_hash": row["payload_hash"],
            "result": row["result"],
        }
    )


def sdk_window_hash(row: dict[str, Any]) -> str:
    return facts_hash(
        {
            "id": str(row["id"]),
            "organization_id": str(row["organization_id"]),
            "shop_id": str(row["shop_id"]),
            "expires_at": row["expires_at"].isoformat(),
            "configured_enabled": row["configured_enabled"],
            "method_caps": row["method_caps"],
            "verification_mode": row["verification_mode"],
        }
    )


def denied() -> NoReturn:
    raise PermissionError("P4_APPROVED_OUTBOX_RECOVERY_DENIED")


def full_process_receipt(value: Any) -> bool:
    return (
        type(value) is dict
        and set(value) == {"pid", "host", "pid_namespace"}
        and type(value["pid"]) is int
        and value["pid"] > 0
        and type(value["host"]) is str
        and bool(value["host"])
        and type(value["pid_namespace"]) is str
        and bool(value["pid_namespace"])
    )


def recheck_audit_id(outbox_id: UUID, *, dispatched: bool = False) -> UUID:
    suffix = "dispatched" if dispatched else "authorized"
    return uuid5(NAMESPACE_URL, f"commerceops:p4:explicit-ro:{outbox_id}:{suffix}")


class ReaderStage(StrEnum):
    INPUT = "P4_RO_READER_INPUT"
    CLAIM = "P4_RO_READER_CLAIM"
    PRIOR = "P4_RO_READER_PRIOR"
    BINDING = "P4_RO_READER_BINDING"
    GATEWAY_CLAIM = "P4_RO_READER_GATEWAY_CLAIM"
    GATEWAY_SCOPE = "P4_RO_READER_GATEWAY_SCOPE"
    SENDER_END = "P4_RO_READER_SENDER_END"
    WORKER_END = "P4_RO_READER_WORKER_END"
    GATEWAY_END = "P4_RO_READER_GATEWAY_END"
    SDK_WINDOW = "P4_RO_READER_SDK_WINDOW"
    SDK_CALL = "P4_RO_READER_SDK_CALL"
    SDK_REQUIRED = "P4_RO_READER_SDK_REQUIRED"
    READBACK_RECEIPT = "P4_RO_READER_READBACK_RECEIPT"


def reader_denied(stage: ReaderStage) -> NoReturn:
    raise PermissionError(stage.value)


async def trusted_reader(db: Any, window: ControlledWorkerWindow, new_claim_at: Any) -> None:
    """最近失败RO的独立可信链；不将reader owner绑定成原C sender。"""
    recovery = window.recovery
    if recovery is None or recovery.explicit_ro_recheck is None:
        reader_denied(ReaderStage.INPUT)
    reader = recovery.explicit_ro_recheck
    cur = await db.execute(
        """SELECT after_state,occurred_at FROM business.audit_events WHERE id=%s
        AND organization_id=%s AND source='feishu_recovery'
        AND action='approved_outbox_claimed' AND entity_type='sdk_window'""",
        (reader.reader_window_id, window.organization_id),
    )
    authorization = await cur.fetchone()
    if not authorization or facts_hash(authorization["after_state"]) != reader.reader_claim_hash:
        reader_denied(ReaderStage.CLAIM)
    prior = ControlledWorkerWindow.model_validate_json(json.dumps(authorization["after_state"]))
    if prior.recovery is None:
        reader_denied(ReaderStage.PRIOR)
    expected = recovery.model_dump(mode="json")
    expected.update(
        worker_window_id=str(prior.window_id),
        gateway_window_id=str(prior.gateway_window_id),
        expires_at=prior.model_dump(mode="json")["expires_at"],
        explicit_ro_recheck=None,
    )
    if (
        prior.profile != "approved_outbox"
        or prior.recovery.model_dump(mode="json") != expected
        or prior.window_id != reader.reader_window_id
        or prior.gateway_window_id != reader.reader_gateway.gateway_id
        or (prior.organization_id, prior.shop_id) != (window.organization_id, window.shop_id)
        or prior.task_ids != window.task_ids
        or not prior.enabled
        or prior.first_create is not None
        or prior.workflow_recovery is not None
        or set(prior.caps) - set(READONLY_RECOVERY_CAPS)
        or any(not 1 <= cap <= READONLY_RECOVERY_CAPS[m] for m, cap in prior.caps.items())
        or prior.caps.get("auth.v3.tenant_access_token.internal") != 1
        or prior.caps.get("bot.v3.info") != 1
    ):
        reader_denied(ReaderStage.BINDING)
    cur = await db.execute(
        """SELECT after_state,occurred_at FROM business.audit_events WHERE id=%s
        AND organization_id=%s AND source='feishu_gateway'
        AND action='gateway_start_claimed' AND entity_type='gateway_window'""",
        (reader.reader_gateway.gateway_id, window.organization_id),
    )
    gw_claim = await cur.fetchone()
    if not gw_claim or facts_hash(gw_claim["after_state"]) != reader.reader_gateway.gateway_hash:
        reader_denied(ReaderStage.GATEWAY_CLAIM)
    gw = GatewayWindow.model_validate_json(
        json.dumps({k: gw_claim["after_state"].get(k) for k in GatewayWindow.model_fields})
    )
    cur = await db.execute(
        "SELECT after_state FROM business.audit_events WHERE id=%s",
        (recovery.original_gateway_id,),
    )
    origin = await cur.fetchone()
    if (
        not origin
        or gw_claim["after_state"] != claimed_state(gw)
        or (gw.organization_id, gw.shop_id) != (window.organization_id, window.shop_id)
        or gw.max_workflows != 0
        or gw.parameters.model_dump(mode="json") != origin["after_state"]["parameters"]
        or prior.expires_at > gw.expires_at
    ):
        reader_denied(ReaderStage.GATEWAY_SCOPE)
    cur = await db.execute(
        "SELECT occurred_at FROM business.audit_events WHERE id=%s",
        (recovery.sender_gateway.termination_id if recovery.sender_gateway else None,),
    )
    sender_end = await cur.fetchone()
    if not sender_end or sender_end["occurred_at"] >= gw_claim["occurred_at"]:
        reader_denied(ReaderStage.SENDER_END)
    cur = await db.execute(
        """SELECT id,action,after_state,reason,occurred_at FROM business.audit_events
        WHERE organization_id=%s AND source='worker' AND entity_type='worker_runtime'
        AND entity_id=%s AND action IN ('started','stopped','termination_confirmed')""",
        (window.organization_id, str(reader.reader_owner)),
    )
    runs = await cur.fetchall()
    starts = [r for r in runs if r["action"] == "started"]
    stops = [r for r in runs if r["action"] == "stopped"]
    ends = [
        r
        for r in runs
        if r["action"] == "termination_confirmed" and r["id"] == reader.reader_termination_id
    ]
    if (
        len(starts) != 1
        or len(stops) != 1
        or len(ends) != 1
        or not full_process_receipt(starts[0]["after_state"])
        or starts[0]["after_state"] != stops[0]["after_state"]
        or not full_process_receipt(ends[0]["after_state"])
        or not ends[0]["reason"]
        or any(
            ends[0]["after_state"][k] != starts[0]["after_state"][k]
            for k in ("host", "pid_namespace")
        )
        or not gw_claim["occurred_at"]
        <= starts[0]["occurred_at"]
        <= authorization["occurred_at"]
        <= stops[0]["occurred_at"]
        <= ends[0]["occurred_at"]
        < new_claim_at
    ):
        reader_denied(ReaderStage.WORKER_END)
    require_process_absent(starts[0]["after_state"])
    cur = await db.execute(
        """SELECT id,action,after_state,occurred_at FROM business.audit_events
        WHERE organization_id=%s AND source='feishu_gateway' AND entity_type='gateway_runtime'
        AND entity_id=%s AND (action='started' OR id=%s)""",
        (window.organization_id, str(gw.window_id), reader.reader_gateway.termination_id),
    )
    runs = await cur.fetchall()
    gw_starts = [r for r in runs if r["action"] == "started"]
    gw_ends = [
        r
        for r in runs
        if r["action"] == "termination_confirmed"
        and r["id"] == reader.reader_gateway.termination_id
    ]
    if (
        len(gw_starts) != 1
        or len(gw_ends) != 1
        or not full_process_receipt(gw_starts[0]["after_state"])
        or gw_ends[0]["after_state"].get("process") != gw_starts[0]["after_state"]
        or gw_ends[0]["after_state"].get("child_reaped") is not True
        or type(gw_ends[0]["after_state"].get("child_exit")) is not int
        or not gw_claim["occurred_at"]
        <= gw_starts[0]["occurred_at"]
        <= starts[0]["occurred_at"]
        <= stops[0]["occurred_at"]
        <= gw_ends[0]["occurred_at"]
        < new_claim_at
    ):
        reader_denied(ReaderStage.GATEWAY_END)
    require_process_absent(gw_starts[0]["after_state"])
    cur = await db.execute(
        "SELECT * FROM business.p4_sdk_windows WHERE id=%s", (reader.reader_window_id,)
    )
    sdk = await cur.fetchone()
    if (
        not sdk
        or sdk_window_hash(sdk) != reader.reader_window_hash
        or (sdk["organization_id"], sdk["shop_id"]) != (window.organization_id, window.shop_id)
        or sdk["verification_mode"] != "controlled_sdk"
        or not sdk["configured_enabled"]
        or sdk["method_caps"] != prior.caps
        or sdk["expires_at"] != prior.expires_at
        or not authorization["occurred_at"] <= sdk["created_at"] <= stops[0]["occurred_at"]
        or sdk["created_at"] >= gw_ends[0]["occurred_at"]
    ):
        reader_denied(ReaderStage.SDK_WINDOW)
    cur = await db.execute(
        "SELECT * FROM business.p4_sdk_calls WHERE window_id=%s", (reader.reader_window_id,)
    )
    calls = await cur.fetchall()
    projection = recovery.projections[0]
    counts: dict[str, int] = {}
    for call in calls:
        method = call["method"]
        counts[method] = counts.get(method, 0) + 1
        base = method == "bitable.v1.app_table_record.list"
        if (
            method not in prior.caps
            or counts[method] > prior.caps[method]
            or (call["status"], call["http_status"], call["provider_code"]) != ("returned", 200, 0)
            or not sdk["created_at"] <= call["started_at"] < sdk["expires_at"]
            or call["started_at"] > stops[0]["occurred_at"]
            or (call["subject_id"], call["task_id"], call["scope_kind"])
            != (
                (projection.outbox_id, recovery.task_id, "base_projection")
                if base
                else (reader.reader_window_id, None, "preflight")
            )
        ):
            reader_denied(ReaderStage.SDK_CALL)
    if counts.get("auth.v3.tenant_access_token.internal") != 1 or not counts.get(
        "bitable.v1.app_table_record.list"
    ):
        reader_denied(ReaderStage.SDK_REQUIRED)
    cur = await db.execute(
        """SELECT after_state FROM business.audit_events WHERE organization_id=%s
        AND task_id=%s AND source='feishu_delivery' AND action='base_projection_checked'
        AND entity_id=%s AND occurred_at>=%s AND occurred_at<=%s""",
        (
            window.organization_id,
            recovery.task_id,
            str(projection.outbox_id),
            sdk["created_at"],
            stops[0]["occurred_at"],
        ),
    )
    checked = await cur.fetchall()
    if len(checked) != 1 or any(
        checked[0]["after_state"].get(k) != v
        for k, v in {
            "operation": "reconcile",
            "status": "unknown",
            "version": 1,
            "observed_version": None,
            "complete_unique_verified": False,
            "verification_mode": "controlled_sdk",
            "safe_code": "INCOMPLETE_READBACK",
        }.items()
    ):
        reader_denied(ReaderStage.READBACK_RECEIPT)


async def trusted_recovery_scope(
    config: WebConfig,
    settings: BusinessSettings,
    window: ControlledWorkerWindow,
    gateway: GatewayWindow,
    *,
    claim: bool = True,
) -> None:
    recovery = window.recovery
    window.window(settings)
    if recovery is None or gateway.max_workflows != 0 or not gateway.active():
        denied()
    async with await open_async(config.database) as db, db.transaction():
        cur = await db.execute(
            """SELECT id,after_state,occurred_at FROM business.audit_events
            WHERE id=ANY(%s) AND organization_id=%s AND source='feishu_gateway'
            AND action='gateway_start_claimed' AND entity_type='gateway_window'""",
            (
                [recovery.original_gateway_id, window.gateway_window_id]
                + ([] if recovery.sender_gateway is None else [recovery.sender_gateway.gateway_id]),
                window.organization_id,
            ),
        )
        claims = {row["id"]: row for row in await cur.fetchall()}
        old = claims.get(recovery.original_gateway_id)
        new = claims.get(window.gateway_window_id)
        if (
            not old
            or not new
            or new["after_state"] != claimed_state(gateway)
            or facts_hash(old["after_state"]) != recovery.original_gateway_hash
        ):
            denied()
        original = GatewayWindow.model_validate_json(
            json.dumps({key: old["after_state"].get(key) for key in GatewayWindow.model_fields})
        )
        if (
            old["after_state"] != claimed_state(original)
            or (original.organization_id, original.shop_id)
            != (window.organization_id, window.shop_id)
            or original.parameters != gateway.parameters
        ):
            denied()
        cur = await db.execute(
            """SELECT id,entity_id,action,after_state,occurred_at FROM business.audit_events
            WHERE organization_id=%s AND source='feishu_gateway' AND entity_type='gateway_runtime'
            AND entity_id=%s AND (action='started' OR id=%s)""",
            (window.organization_id, str(original.window_id), recovery.gateway_termination_id),
        )
        rows = await cur.fetchall()
        started = [row for row in rows if row["action"] == "started"]
        ended = [
            row
            for row in rows
            if row["id"] == recovery.gateway_termination_id
            and row["action"] == "termination_confirmed"
        ]
        if (
            len(started) != 1
            or len(ended) != 1
            or not full_process_receipt(started[0]["after_state"])
            or ended[0]["after_state"].get("process") != started[0]["after_state"]
            or ended[0]["after_state"].get("child_reaped") is not True
            or type(ended[0]["after_state"].get("child_exit")) is not int
            or not old["occurred_at"]
            <= started[0]["occurred_at"]
            <= ended[0]["occurred_at"]
            < new["occurred_at"]
        ):
            denied()
        sender_claim, sender_gateway = old, original
        if recovery.sender_gateway is not None:
            lineage = recovery.sender_gateway
            candidate = claims.get(lineage.gateway_id)
            if not candidate or facts_hash(candidate["after_state"]) != lineage.gateway_hash:
                denied()
            sender_claim = candidate
            sender_gateway = GatewayWindow.model_validate_json(
                json.dumps(
                    {
                        key: sender_claim["after_state"].get(key)
                        for key in GatewayWindow.model_fields
                    }
                )
            )
            if (
                sender_claim["after_state"] != claimed_state(sender_gateway)
                or (sender_gateway.organization_id, sender_gateway.shop_id)
                != (window.organization_id, window.shop_id)
                or sender_gateway.parameters != original.parameters
                or sender_gateway.max_workflows != 0
                or not ended[0]["occurred_at"] < sender_claim["occurred_at"]
            ):
                denied()
            cur = await db.execute(
                """SELECT id,action,after_state,occurred_at FROM business.audit_events
                WHERE organization_id=%s AND source='feishu_gateway'
                AND entity_type='gateway_runtime' AND entity_id=%s
                AND (action='started' OR id=%s)""",
                (window.organization_id, str(lineage.gateway_id), lineage.termination_id),
            )
            sender_runs = await cur.fetchall()
            sender_starts = [row for row in sender_runs if row["action"] == "started"]
            sender_ends = [
                row
                for row in sender_runs
                if row["action"] == "termination_confirmed" and row["id"] == lineage.termination_id
            ]
            if (
                len(sender_starts) != 1
                or len(sender_ends) != 1
                or not full_process_receipt(sender_starts[0]["after_state"])
                or sender_ends[0]["after_state"].get("process") != sender_starts[0]["after_state"]
                or sender_ends[0]["after_state"].get("child_reaped") is not True
                or type(sender_ends[0]["after_state"].get("child_exit")) is not int
                or not sender_claim["occurred_at"]
                <= sender_starts[0]["occurred_at"]
                <= sender_ends[0]["occurred_at"]
                < new["occurred_at"]
            ):
                denied()
            require_process_absent(sender_starts[0]["after_state"])
        cur = await db.execute(
            """SELECT id,action,after_state,reason,occurred_at FROM business.audit_events
            WHERE organization_id=%s AND source='worker' AND entity_type='worker_runtime'
            AND entity_id=%s AND action IN ('started','stopped','termination_confirmed')""",
            (window.organization_id, str(recovery.worker_owner)),
        )
        runs = await cur.fetchall()
        starts = [row for row in runs if row["action"] == "started"]
        stops = [row for row in runs if row["action"] == "stopped"]
        confirmations = [
            row
            for row in runs
            if row["action"] == "termination_confirmed"
            and row["id"] == recovery.worker_termination_id
        ]
        if (
            len(starts) != 1
            or len(stops) != 1
            or len(confirmations) != 1
            or not full_process_receipt(starts[0]["after_state"])
            or starts[0]["after_state"] != stops[0]["after_state"]
            or not sender_claim["occurred_at"]
            <= starts[0]["occurred_at"]
            <= stops[0]["occurred_at"]
            <= confirmations[0]["occurred_at"]
            < new["occurred_at"]
        ):
            denied()
        if recovery.sender_gateway is not None:
            if (
                not full_process_receipt(confirmations[0]["after_state"])
                or not confirmations[0]["reason"]
                or any(
                    confirmations[0]["after_state"][key] != starts[0]["after_state"][key]
                    for key in ("host", "pid_namespace")
                )
            ):
                denied()
            require_process_absent(starts[0]["after_state"])
        cur = await db.execute(
            """SELECT t.version,t.state,t.active_plan_id,t.normalized_request,t.requester_id,
            s.parameters,p.content,p.plan_hash AS content_hash,p.version AS stored_plan_version,
            p.status AS plan_status,a.*,e.id AS execution_id,
            e.status AS execution_status,e.plan_hash AS execution_hash,e.item_ids,
            r.inbox_id,r.identity_id,r.result,r.created_at AS receipt_at,i.payload_hash,
            i.sanitized_payload,i.app_id,i.tenant_key,
            pr.auth_version AS operator_auth_version,
            ip.external_subject AS operator_open_id,c.chat_id
            FROM business.business_tasks t JOIN business.p3_task_sources s ON s.task_id=t.id
            JOIN business.replenishment_plans p ON p.id=t.active_plan_id
            JOIN business.approvals a ON a.plan_id=p.id
            JOIN business.executions e ON e.task_id=t.id AND e.plan_id=p.id AND e.approval_id=a.id
            JOIN business.inbox_events i ON i.task_id=t.id AND i.source='feishu_business'
            JOIN business.p4_inbox_receipts r ON r.inbox_id=i.id
            JOIN business.principals pr ON pr.id=t.requester_id
            JOIN business.identities ip ON ip.id=r.identity_id AND ip.principal_id=t.requester_id
            JOIN business.conversations c ON c.id=t.conversation_id AND c.channel='feishu'
            WHERE t.id=%s AND t.organization_id=%s AND t.shop_id=%s
            AND t.kind='inventory_replenishment'
            AND t.workflow_version='p3-inventory-replenishment-v1'
            AND i.sanitized_payload->>'event_type'='im.message.receive_v1'
            AND r.inbox_id=%s FOR SHARE OF t,p,a,e,pr,ip""",
            (recovery.task_id, window.organization_id, window.shop_id, recovery.inbox_id),
        )
        task = await cur.fetchone()
        # a.* includes task/plan bindings; select t aliases separately to avoid same-name ambiguity.
        if (
            not task
            or task["state"] != "completed"
            or task["version"] != recovery.task_version
            or task["active_plan_id"] != recovery.plan_id
            or task["plan_id"] != recovery.plan_id
            or task["plan_version"] != recovery.plan_version
            or task["plan_hash"] != recovery.plan_hash
            or task["id"] != recovery.approval_id
            or task["decision_id"] != recovery.decision_id
            or task["status"] != "approved"
            or task["consumed_at"] is None
            or task["plan_status"] != "executed"
            or task["content_hash"] != recovery.plan_hash
            or task["stored_plan_version"] != recovery.plan_version
            or task["decision_action"] not in ("approve", "approve_with_assumptions")
            or task["execution_id"] != recovery.execution_id
            or task["execution_status"] != "completed"
            or task["execution_hash"] != recovery.plan_hash
            or task["parameters"] != original.parameters.model_dump(mode="json")
            or not old["occurred_at"] <= task["receipt_at"] < original.expires_at
            or receipt_hash(task) != recovery.receipt_hash
            or task["operator_auth_version"] != recovery.operator_auth_version
            or task["decided_auth_version"] != recovery.approver_auth_version
            or (task["app_id"], task["tenant_key"]) != (settings.app_id, settings.tenant_key)
            or task["operator_open_id"] not in settings.allowed_open_ids
            or task["normalized_request"].get("identity_id") != str(task["identity_id"])
            or task["result"].get("task_id") != str(recovery.task_id)
            or task["sanitized_payload"].get("chat_type") not in ("p2p", "group")
            or task["sanitized_payload"].get("chat_type") == "group"
            and task["chat_id"] not in settings.allowed_group_chat_ids
        ):
            denied()
        cur = await db.execute(
            """SELECT business.lock_p3_permission(%s,%s,%s,%s,%s,'operator') AS creator_ok,
            business.lock_p3_permission(%s,%s,%s,%s,%s,'approver') AS approver_ok""",
            (
                task["requester_id"],
                window.organization_id,
                window.shop_id,
                task["identity_id"],
                recovery.operator_auth_version,
                task["decided_by"],
                window.organization_id,
                window.shop_id,
                task["decided_identity_id"],
                recovery.approver_auth_version,
            ),
        )
        permissions = await cur.fetchone()
        if not permissions or not permissions["creator_ok"] or not permissions["approver_ok"]:
            denied()
        cur = await db.execute(
            "SELECT * FROM business.p4_sdk_windows WHERE id=%s", (recovery.original_sdk_window_id,)
        )
        sdk = await cur.fetchone()
        if (
            not sdk
            or not sdk["configured_enabled"]
            or sdk["verification_mode"] != "controlled_sdk"
            or sdk["organization_id"] != window.organization_id
            or sdk["shop_id"] != window.shop_id
            or sdk_window_hash(sdk) != recovery.original_sdk_window_hash
            or not sender_claim["occurred_at"]
            <= sdk["created_at"]
            < sdk["expires_at"]
            <= sender_gateway.expires_at
        ):
            denied()
        if recovery.sender_gateway is not None:
            cur = await db.execute(
                """SELECT after_state,occurred_at FROM business.audit_events
                WHERE id=%s AND organization_id=%s AND source='feishu_recovery'
                AND action='approved_workflow_claimed' AND entity_type='sdk_window'""",
                (recovery.original_sdk_window_id, window.organization_id),
            )
            sender_authorization = await cur.fetchone()
            if not sender_authorization:
                denied()
            sender = ControlledWorkerWindow.model_validate_json(
                json.dumps(sender_authorization["after_state"])
            )
            workflow = sender.workflow_recovery
            if (
                sender.profile != "approved_first_create"
                or workflow is None
                or sender.first_create != recovery.projections[0]
                or sender.window_id != sdk["id"]
                or sender.gateway_window_id != sender_gateway.window_id
                or (sender.organization_id, sender.shop_id)
                != (window.organization_id, window.shop_id)
                or sender.task_ids != window.task_ids
                or not sender.enabled
                or sender.expires_at != sdk["expires_at"]
                or sender.caps != sdk["method_caps"]
                or set(sender.caps) - set(FIRST_CREATE_CAPS)
                or any(
                    not 1 <= cap <= FIRST_CREATE_CAPS[method] for method, cap in sender.caps.items()
                )
                or sender.caps.get("auth.v3.tenant_access_token.internal") != 1
                or sender.caps.get("bot.v3.info") != 1
                or sender.caps.get("bitable.v1.app_table_record.create") != 1
                or workflow.original_gateway_id != recovery.original_gateway_id
                or workflow.original_gateway_hash != recovery.original_gateway_hash
                or workflow.gateway_termination_id != recovery.gateway_termination_id
                or workflow.task_id != recovery.task_id
                or workflow.task_version != recovery.task_version
                or workflow.inbox_id != recovery.inbox_id
                or workflow.receipt_hash != recovery.receipt_hash
                or workflow.approval_id != recovery.approval_id
                or workflow.decision_id != recovery.decision_id
                or workflow.decision_payload_hash != task["decision_payload_hash"]
                or workflow.execution_id != recovery.execution_id
                or workflow.operator_auth_version != recovery.operator_auth_version
                or workflow.target_key != recovery.target_key
                or workflow.worker_window_id != sender.window_id
                or workflow.gateway_window_id != sender.gateway_window_id
                or workflow.expires_at != sender.expires_at
                or not sender_starts[0]["occurred_at"]
                <= starts[0]["occurred_at"]
                <= sender_authorization["occurred_at"]
                <= sdk["created_at"]
                or sdk["created_at"] > stops[0]["occurred_at"]
                or sdk["created_at"] >= sender_ends[0]["occurred_at"]
            ):
                denied()
            cur = await db.execute(
                """SELECT status,http_status,provider_code,started_at FROM business.p4_sdk_calls
                WHERE window_id=%s AND subject_id=%s AND task_id IS NULL AND scope_kind='preflight'
                AND method='auth.v3.tenant_access_token.internal'""",
                (sdk["id"], sdk["id"]),
            )
            authentication = await cur.fetchall()
            if (
                len(authentication) != 1
                or authentication[0]["status"] != "returned"
                or authentication[0]["http_status"] != 200
                or authentication[0]["provider_code"] != 0
                or not sdk["created_at"]
                <= authentication[0]["started_at"]
                <= stops[0]["occurred_at"]
            ):
                denied()
            from commerceops.infrastructure.feishu_workflow_recovery import (
                approval_binding_hash,
                task_binding_hash,
            )

            cur = await db.execute(
                """SELECT t.*,s.source_task_id,s.parameters,s.config_version
                FROM business.business_tasks t JOIN business.p3_task_sources s ON s.task_id=t.id
                WHERE t.id=%s""",
                (recovery.task_id,),
            )
            bound_task = await cur.fetchone()
            if (
                not bound_task
                or task_binding_hash(bound_task) != workflow.task_binding_hash
                or approval_binding_hash(task) != workflow.approval_binding_hash
            ):
                denied()
        if recovery.explicit_ro_recheck is not None:
            await trusted_reader(db, window, new["occurred_at"])
        for projection in recovery.projections:
            cur = await db.execute(
                """SELECT d.*,o.request_hash,o.payload AS original_payload,
                o.provider_idempotency_key,o.aggregate_version,o.destination,o.operation,
                o.sender_enabled,o.source_mode FROM business.p4_base_deliveries d
                JOIN business.outbox o ON o.id=d.outbox_id WHERE d.outbox_id=%s
                AND d.organization_id=%s AND d.shop_id=%s AND d.task_id=%s FOR SHARE OF d,o""",
                (projection.outbox_id, window.organization_id, window.shop_id, recovery.task_id),
            )
            delivery = await cur.fetchone()
            if (
                not delivery
                or delivery["verification_mode"] != "controlled_sdk"
                or delivery["target_key"] != recovery.target_key
                or delivery["item_id"] != projection.item_id
                or projection.item_id not in task["item_ids"]
                or delivery["version"] != projection.version
                or delivery["aggregate_version"] != projection.version
                or delivery["client_token"] != projection.client_token
                or delivery["provider_idempotency_key"] != projection.client_token
                or delivery["projection_hash"] != projection.projection_hash
                or facts_hash(delivery["projection"]) != projection.projection_hash
                or delivery["request_hash"] != projection.request_hash
                or facts_hash(delivery["original_payload"]) != projection.request_hash
                or (
                    delivery["destination"],
                    delivery["operation"],
                    delivery["source_mode"],
                    delivery["sender_enabled"],
                )
                != ("bitable", "item_projection", "mock", False)
                or delivery["status"]
                not in (
                    {"unknown"}
                    if projection.version == 1 and claim
                    else {"pending"}
                    if claim
                    else {"unknown", "pending", "verified"}
                )
                or claim
                and projection.version == 1
                and (
                    delivery["claimed_by"]
                    != str(
                        recovery.worker_owner
                        if recovery.explicit_ro_recheck is None
                        else recovery.explicit_ro_recheck.reader_owner
                    )
                    or delivery["unknown_since"] is None
                )
                or claim
                and projection.version == 2
                and delivery["attempts"] != 0
                or delivery["attempts"] >= 3
                and delivery["status"] != "verified"
                and recovery.explicit_ro_recheck is None
            ):
                denied()
            cur = await db.execute(
                "SELECT * FROM business.replenishment_items WHERE id=%s FOR SHARE",
                (projection.item_id,),
            )
            item = await cur.fetchone()
            if (
                not item
                or item["execution_id"] != recovery.execution_id
                or item_snapshot(item, task["content"], projection.version).model_dump(mode="json")
                != delivery["projection"]
            ):
                denied()
            if projection.version == 1:
                cur = await db.execute(
                    """SELECT 1 FROM business.p4_sdk_calls WHERE window_id=%s AND subject_id=%s
                    AND task_id=%s AND scope_kind='base_projection'
                    AND method='bitable.v1.app_table_record.create'
                    AND started_at>=%s AND started_at<=%s""",
                    (
                        recovery.original_sdk_window_id,
                        projection.outbox_id,
                        recovery.task_id,
                        starts[0]["occurred_at"],
                        stops[0]["occurred_at"],
                    ),
                )
                if not await cur.fetchone():
                    denied()
            if recovery.sender_gateway is not None:
                cur = await db.execute(
                    """SELECT window_id,status,http_status,provider_code,started_at
                    FROM business.p4_sdk_calls WHERE subject_id=%s
                    AND method='bitable.v1.app_table_record.create'""",
                    (projection.outbox_id,),
                )
                history = await cur.fetchall()
                cur = await db.execute(
                    "SELECT count(*) AS n FROM business.p4_base_links WHERE item_id=%s",
                    (projection.item_id,),
                )
                anchor = await cur.fetchone()
                if (
                    len(history) != 1
                    or history[0]["window_id"] != sdk["id"]
                    or history[0]["status"] != "returned"
                    or history[0]["http_status"] != 200
                    or history[0]["provider_code"] != 0
                    or not sdk["created_at"] <= history[0]["started_at"] < sdk["expires_at"]
                    or history[0]["started_at"] > sender_ends[0]["occurred_at"]
                    or item["status"] != "open"
                    or item["version"] != 1
                    or delivery["status"] not in {"unknown", "verified"}
                    or claim
                    and (
                        delivery["attempts"] != (2 if recovery.explicit_ro_recheck is None else 3)
                        or delivery["last_operation"]
                        != ("create" if recovery.explicit_ro_recheck is None else "reconcile")
                        or recovery.explicit_ro_recheck is not None
                        and delivery["last_error"] != "INCOMPLETE_READBACK"
                        or delivery["external_id"] is not None
                        or not anchor
                        or anchor["n"] != 0
                    )
                ):
                    denied()
        if recovery.explicit_ro_recheck is not None:
            projection = recovery.projections[0]
            authorization_id = recheck_audit_id(projection.outbox_id)
            state = {"recheck_count": 1, "window": window.model_dump(mode="json")}
            if claim:
                cur = await db.execute(
                    """INSERT INTO business.audit_events(id,organization_id,task_id,source,action,
                    entity_type,entity_id,after_state,trace_id) VALUES(%s,%s,%s,'feishu_recovery',
                    'explicit_ro_recheck_authorized','outbox',%s,%s,%s)
                    ON CONFLICT(id) DO NOTHING RETURNING id""",
                    (
                        authorization_id,
                        window.organization_id,
                        recovery.task_id,
                        str(projection.outbox_id),
                        Jsonb(state),
                        window.window_id,
                    ),
                )
                if not await cur.fetchone():
                    denied()
            else:
                cur = await db.execute(
                    """SELECT after_state FROM business.audit_events WHERE id=%s
                    AND organization_id=%s AND task_id=%s AND source='feishu_recovery'
                    AND action='explicit_ro_recheck_authorized' AND entity_id=%s
                    AND NOT EXISTS(SELECT 1 FROM business.audit_events WHERE id=%s)""",
                    (
                        authorization_id,
                        window.organization_id,
                        recovery.task_id,
                        str(projection.outbox_id),
                        recheck_audit_id(projection.outbox_id, dispatched=True),
                    ),
                )
                authorized = await cur.fetchone()
                if not authorized or authorized["after_state"] != state:
                    denied()
        if claim:
            await db.execute(
                """INSERT INTO business.audit_events(id,organization_id,task_id,source,action,
                entity_type,entity_id,after_state,trace_id) VALUES(%s,%s,%s,'feishu_recovery',
                'approved_outbox_claimed','sdk_window',%s,%s,%s)""",
                (
                    window.window_id,
                    window.organization_id,
                    recovery.task_id,
                    str(window.window_id),
                    Jsonb(window.model_dump(mode="json")),
                    window.window_id,
                ),
            )
        else:
            cur = await db.execute(
                """SELECT after_state FROM business.audit_events WHERE id=%s
                AND organization_id=%s AND source='feishu_recovery'
                AND action='approved_outbox_claimed'""",
                (window.window_id, window.organization_id),
            )
            bound = await cur.fetchone()
            expected = window.model_dump(mode="json")
            legacy = json.loads(json.dumps(expected))
            if recovery.explicit_ro_recheck is None:
                legacy["recovery"].pop("explicit_ro_recheck", None)
            if recovery.sender_gateway is None:
                legacy["recovery"].pop("sender_gateway", None)
            if not bound or bound["after_state"] not in (expected, legacy):
                denied()
