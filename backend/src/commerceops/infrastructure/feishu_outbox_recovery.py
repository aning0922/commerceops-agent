"""在原PG/audit与单Worker锁下复核显式原键恢复；绝不重执行T4。"""

import json
from typing import Any, NoReturn

from psycopg.types.json import Jsonb

from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.application.feishu_business.gateway_window import GatewayWindow
from commerceops.application.feishu_business.worker_window import ControlledWorkerWindow
from commerceops.domain.commerce_values import facts_hash
from commerceops.infrastructure.feishu_base_delivery import item_snapshot
from commerceops.infrastructure.feishu_gateway_window import claimed_state
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.worker_lock import open_async


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
            ([recovery.original_gateway_id, window.gateway_window_id], window.organization_id),
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
        cur = await db.execute(
            """SELECT id,action,after_state,occurred_at FROM business.audit_events
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
            or not old["occurred_at"]
            <= starts[0]["occurred_at"]
            <= stops[0]["occurred_at"]
            <= confirmations[0]["occurred_at"]
            < new["occurred_at"]
        ):
            denied()
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
            or not old["occurred_at"]
            <= sdk["created_at"]
            < sdk["expires_at"]
            <= original.expires_at
        ):
            denied()
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
                    delivery["claimed_by"] != str(recovery.worker_owner)
                    or delivery["unknown_since"] is None
                )
                or claim
                and projection.version == 2
                and delivery["attempts"] != 0
                or delivery["attempts"] >= 3
                and delivery["status"] != "verified"
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
            if not bound or bound["after_state"] != window.model_dump(mode="json"):
                denied()
