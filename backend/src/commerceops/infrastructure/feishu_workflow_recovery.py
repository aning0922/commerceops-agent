"""原 T1/OS 终止/SDK/不可变审批绑定下接续单个 workflow；不刷新旧凭据。"""

import json
from typing import Any, NoReturn

from psycopg.types.json import Jsonb

from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.application.feishu_business.gateway_window import GatewayWindow
from commerceops.application.feishu_business.worker_window import ControlledWorkerWindow
from commerceops.domain.commerce_values import facts_hash
from commerceops.infrastructure.feishu_gateway_window import claimed_state
from commerceops.infrastructure.feishu_outbox_recovery import (
    full_process_receipt,
    receipt_hash,
    sdk_window_hash,
)
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.web_sessions import json_native
from commerceops.infrastructure.worker_lock import open_async


def task_binding_hash(task: dict[str, Any]) -> str:
    return facts_hash(
        json_native(
            {
                key: task[key]
                for key in (
                    "id",
                    "organization_id",
                    "shop_id",
                    "requester_id",
                    "thread_id",
                    "kind",
                    "workflow_version",
                    "normalized_request",
                    "source_task_id",
                    "parameters",
                    "config_version",
                )
            }
        )
    )


def approval_binding_hash(approval: dict[str, Any]) -> str:
    return facts_hash(
        json_native(
            {
                key: approval[key]
                for key in (
                    "id",
                    "organization_id",
                    "shop_id",
                    "task_id",
                    "plan_id",
                    "plan_version",
                    "plan_hash",
                    "eligible_principal_ids",
                    "nonce_hash",
                    "nonce_key_version",
                    "expires_at",
                    "created_at",
                )
            }
        )
    )


def denied() -> NoReturn:
    raise PermissionError("P4_APPROVED_WORKFLOW_RECOVERY_DENIED")


async def trusted_workflow_scope(
    config: WebConfig,
    settings: BusinessSettings,
    window: ControlledWorkerWindow,
    gateway: GatewayWindow,
    *,
    claim: bool = True,
) -> None:
    recovery = window.workflow_recovery
    window.window(settings)
    if recovery is None or gateway.max_workflows != 0 or not gateway.active():
        denied()
    async with await open_async(config.database) as db, db.transaction():
        cur = await db.execute(
            """SELECT id,after_state,occurred_at FROM business.audit_events
            WHERE id=ANY(%s) AND organization_id=%s AND source='feishu_gateway'
            AND action='gateway_start_claimed' AND entity_type='gateway_window'""",
            ([recovery.original_gateway_id, window.gateway_window_id], window.organization_id),
        )
        claims = {row["id"]: row for row in await cur.fetchall()}
        old, new = claims.get(recovery.original_gateway_id), claims.get(window.gateway_window_id)
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
            """SELECT id,action,after_state,occurred_at FROM business.audit_events
            WHERE organization_id=%s AND source='feishu_gateway' AND entity_type='gateway_runtime'
            AND entity_id=%s AND (action='started' OR id=%s)""",
            (window.organization_id, str(original.window_id), recovery.gateway_termination_id),
        )
        events = await cur.fetchall()
        starts = [r for r in events if r["action"] == "started"]
        ends = [
            r
            for r in events
            if r["id"] == recovery.gateway_termination_id and r["action"] == "termination_confirmed"
        ]
        if (
            len(starts) != 1
            or len(ends) != 1
            or not full_process_receipt(starts[0]["after_state"])
            or ends[0]["after_state"].get("process") != starts[0]["after_state"]
            or ends[0]["after_state"].get("child_reaped") is not True
            or type(ends[0]["after_state"].get("child_exit")) is not int
            or not old["occurred_at"]
            <= starts[0]["occurred_at"]
            <= ends[0]["occurred_at"]
            < new["occurred_at"]
        ):
            denied()
        gateway_end = ends[0]["occurred_at"]
        cur = await db.execute(
            """SELECT id,action,after_state,reason,occurred_at FROM business.audit_events
            WHERE organization_id=%s AND source='worker' AND entity_type='worker_runtime'
            AND entity_id=%s AND action IN ('started','stopped','termination_confirmed')""",
            (window.organization_id, str(recovery.worker_owner)),
        )
        events = await cur.fetchall()
        starts = [r for r in events if r["action"] == "started"]
        stops = [r for r in events if r["action"] == "stopped"]
        ends = [
            r
            for r in events
            if r["id"] == recovery.worker_termination_id and r["action"] == "termination_confirmed"
        ]
        if (
            len(starts) != 1
            or len(ends) != 1
            or len(stops) > 1
            or not full_process_receipt(starts[0]["after_state"])
            or not ends[0]["reason"]
            or not full_process_receipt(ends[0]["after_state"])
            or any(
                ends[0]["after_state"][key] != starts[0]["after_state"][key]
                for key in ("host", "pid_namespace")
            )
            or not old["occurred_at"]
            <= starts[0]["occurred_at"]
            <= ends[0]["occurred_at"]
            < new["occurred_at"]
            or stops
            and (
                stops[0]["after_state"] != starts[0]["after_state"]
                or not starts[0]["occurred_at"] <= stops[0]["occurred_at"] <= ends[0]["occurred_at"]
            )
        ):
            denied()
        worker_start, worker_end = starts[0]["occurred_at"], ends[0]["occurred_at"]
        # 同一个共同 T1 validator；替换 Gateway 不改变原 receipt 时间范围/平台身份。
        from commerceops.entrypoints.feishu_worker_child import trusted_tasks

        await trusted_tasks(db, settings, window, original, old["occurred_at"])
        cur = await db.execute(
            """SELECT t.*,s.source_task_id,s.parameters,s.config_version,
            r.inbox_id,r.identity_id,r.result,r.created_at AS receipt_at,i.payload_hash,
            i.sanitized_payload,c.chat_id,pr.auth_version AS operator_auth_version
            FROM business.business_tasks t JOIN business.p3_task_sources s ON s.task_id=t.id
            JOIN business.inbox_events i ON i.task_id=t.id AND i.source='feishu_business'
            AND i.sanitized_payload->>'event_type'='im.message.receive_v1'
            JOIN business.p4_inbox_receipts r ON r.inbox_id=i.id
            JOIN business.conversations c ON c.id=t.conversation_id
            JOIN business.principals pr ON pr.id=t.requester_id WHERE t.id=%s AND r.inbox_id=%s
            FOR SHARE OF t,s,i,c,pr""",
            (recovery.task_id, recovery.inbox_id),
        )
        task = await cur.fetchone()
        if (
            not task
            or task["state"] in ("failed", "needs_attention", "needs_reapproval")
            or task_binding_hash(task) != recovery.task_binding_hash
            or task["operator_auth_version"] != recovery.operator_auth_version
            or not old["occurred_at"] <= task["receipt_at"] < original.expires_at
            or task["receipt_at"] >= gateway_end
            or receipt_hash(task) != recovery.receipt_hash
            or task["result"].get("task_id") != str(task["id"])
            or task["sanitized_payload"].get("chat_type") not in ("p2p", "group")
            or task["sanitized_payload"].get("chat_type") == "group"
            and task["chat_id"] not in settings.allowed_group_chat_ids
            or claim
            and (
                task["version"] != recovery.task_version
                or task["state"]
                not in ("queued", "analyzing", "awaiting_approval", "executing", "completed")
            )
        ):
            denied()
        cur = await db.execute(
            "SELECT * FROM business.p4_sdk_windows WHERE id=%s", (recovery.original_sdk_window_id,)
        )
        sdk = await cur.fetchone()
        if (
            not sdk
            or not sdk["configured_enabled"]
            or sdk["verification_mode"] != "controlled_sdk"
            or (sdk["organization_id"], sdk["shop_id"]) != (window.organization_id, window.shop_id)
            or sdk_window_hash(sdk) != recovery.original_sdk_window_hash
            or set(window.caps) - set(sdk["method_caps"])
            or any(value > sdk["method_caps"][method] for method, value in window.caps.items())
            or not worker_start <= sdk["created_at"] <= worker_end
            or not sdk["created_at"] < sdk["expires_at"] <= original.expires_at
        ):
            denied()
        cur = await db.execute(
            """SELECT 1 FROM business.p4_sdk_calls WHERE window_id=%s AND subject_id=%s
            AND scope_kind='preflight' AND method='auth.v3.tenant_access_token.internal'
            AND status='returned' AND http_status=200 AND provider_code=0
            AND started_at>=%s AND started_at<=%s""",
            (sdk["id"], sdk["id"], worker_start, worker_end),
        )
        if not await cur.fetchone():
            denied()
        if claim:
            cur = await db.execute(
                """SELECT 1 FROM business.jobs WHERE task_id=%s AND attempts>0
                AND ((status='running' AND lease_owner=%s) OR
                (status IN ('done','retry_wait') AND updated_at BETWEEN %s AND %s))""",
                (task["id"], str(recovery.worker_owner), worker_start, worker_end),
            )
            if not await cur.fetchone():
                denied()  # 旧 queued/Worker0 不因新窗口复活。
            cur = await db.execute(
                "SELECT 1 FROM checkpoints.checkpoints WHERE thread_id=%s LIMIT 1",
                (task["thread_id"],),
            )
            if not await cur.fetchone():
                denied()
        cur = await db.execute(
            "SELECT * FROM business.approvals WHERE task_id=%s ORDER BY created_at", (task["id"],)
        )
        approvals = await cur.fetchall()
        if len(approvals) > 1 or recovery.approval_id is None and claim and approvals:
            denied()
        if recovery.approval_id is not None:
            if len(approvals) != 1 or approvals[0]["id"] != recovery.approval_id:
                denied()
            approval = approvals[0]
            if (
                approval_binding_hash(approval) != recovery.approval_binding_hash
                or task["active_plan_id"] != approval["plan_id"]
                or recovery.decision_id is not None
                and (
                    approval["decision_id"] != recovery.decision_id
                    or approval["decision_payload_hash"] != recovery.decision_payload_hash
                )
                or claim
                and approval["decision_id"] != recovery.decision_id
            ):
                denied()
        elif claim and task["active_plan_id"] is not None:
            denied()
        if approvals and approvals[0]["decision_id"] is not None:
            a = approvals[0]
            cur = await db.execute(
                "SELECT business.lock_p3_permission(%s,%s,%s,%s,%s,'approver') AS ok",
                (
                    a["decided_by"],
                    window.organization_id,
                    window.shop_id,
                    a["decided_identity_id"],
                    a["decided_auth_version"],
                ),
            )
            permission = await cur.fetchone()
            if not permission or not permission["ok"]:
                denied()
        cur = await db.execute("SELECT id FROM business.executions WHERE task_id=%s", (task["id"],))
        executions = [r["id"] for r in await cur.fetchall()]
        if (
            len(executions) > 1
            or (
                claim
                and executions != ([] if recovery.execution_id is None else [recovery.execution_id])
            )
            or (recovery.execution_id is not None and executions != [recovery.execution_id])
        ):
            denied()
        cur = await db.execute(
            """SELECT 1 FROM business.p4_base_deliveries WHERE task_id=%s
            AND verification_mode<>'controlled_sdk'
            UNION ALL SELECT 1 FROM business.p4_im_deliveries WHERE task_id=%s
            AND (verification_mode<>'controlled_sdk' OR status IN ('sending','unknown')) LIMIT 1""",
            (task["id"], task["id"]),
        )
        if await cur.fetchone():
            denied()  # 不能借 workflow 恢复重发未知卡片或混用 Fake 历史。
        if claim:
            await db.execute(
                """INSERT INTO business.audit_events(id,organization_id,task_id,source,action,
                entity_type,entity_id,after_state,trace_id) VALUES(%s,%s,%s,'feishu_recovery',
                'approved_workflow_claimed','sdk_window',%s,%s,%s)""",
                (
                    window.window_id,
                    window.organization_id,
                    task["id"],
                    str(window.window_id),
                    Jsonb(window.model_dump(mode="json")),
                    window.window_id,
                ),
            )
        else:
            cur = await db.execute(
                """SELECT after_state FROM business.audit_events WHERE id=%s
                AND organization_id=%s AND source='feishu_recovery'
                AND action='approved_workflow_claimed'""",
                (window.window_id, window.organization_id),
            )
            receipt = await cur.fetchone()
            if not receipt or receipt["after_state"] != window.model_dump(mode="json"):
                denied()
