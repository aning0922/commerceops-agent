"""显式原键 C0 首次 create；任何已预占 create 仍只对账，不改排队或旧键。"""

import json
import os
import socket
from typing import Any, NoReturn

from commerceops.application.feishu_business.delivery import DeliveryGate
from commerceops.application.feishu_business.worker_window import ControlledWorkerWindow
from commerceops.domain.commerce_values import facts_hash
from commerceops.infrastructure.feishu_base_delivery import item_snapshot
from commerceops.infrastructure.feishu_outbox_recovery import full_process_receipt
from commerceops.infrastructure.feishu_sdk_ledger import PersistentSDKLedger
from commerceops.infrastructure.worker_lock import process_namespace, require_process_absent


def denied() -> NoReturn:
    raise PermissionError("P4_FIRST_CREATE_RECOVERY_DENIED")


async def old_senders_closed(db: Any, window: ControlledWorkerWindow, claimed_at: Any) -> None:
    expected = {
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "pid_namespace": process_namespace(),
    }
    for source, kind in (("worker", "worker_runtime"), ("feishu_gateway", "gateway_runtime")):
        cur = await db.execute(
            """SELECT entity_id,after_state,occurred_at FROM business.audit_events
            WHERE organization_id=%s AND source=%s AND entity_type=%s AND action='started'""",
            (window.organization_id, source, kind),
        )
        current_workers = 0
        seen = set()
        for start in await cur.fetchall():
            if start["entity_id"] in seen:
                denied()
            seen.add(start["entity_id"])
            if source == "feishu_gateway" and start["entity_id"] == str(window.gateway_window_id):
                continue  # 当前新 Gateway 已由共同入口核原唯一 App lease/active claim。
            if (
                source == "worker"
                and start["after_state"] == expected
                and start["occurred_at"] >= claimed_at
            ):
                current_workers += 1
                if current_workers > 1:
                    denied()
                continue
            cur = await db.execute(
                """SELECT after_state,reason,occurred_at FROM business.audit_events
                WHERE organization_id=%s AND source=%s AND entity_type=%s
                AND entity_id=%s AND action='termination_confirmed'""",
                (window.organization_id, source, kind, start["entity_id"]),
            )
            ends = await cur.fetchall()
            process = start["after_state"]
            if (
                len(ends) != 1
                or not full_process_receipt(process)
                or not start["occurred_at"] <= ends[0]["occurred_at"] < claimed_at
            ):
                denied()
            end = ends[0]["after_state"]
            if source == "feishu_gateway":
                if (
                    type(end) is not dict
                    or end.get("process") != process
                    or end.get("child_reaped") is not True
                    or type(end.get("child_exit")) is not int
                ):
                    denied()
            elif (
                not full_process_receipt(end)
                or any(end[key] != process[key] for key in ("host", "pid_namespace"))
                or not ends[0]["reason"]
            ):
                denied()
            if source == "worker":
                cur = await db.execute(
                    """SELECT after_state,occurred_at FROM business.audit_events
                    WHERE organization_id=%s AND source=%s AND entity_type=%s
                    AND entity_id=%s AND action='stopped'""",
                    (window.organization_id, source, kind, start["entity_id"]),
                )
                stops = await cur.fetchall()
                if (
                    len(stops) > 1
                    or stops
                    and (
                        stops[0]["after_state"] != process
                        or not start["occurred_at"]
                        <= stops[0]["occurred_at"]
                        <= ends[0]["occurred_at"]
                    )
                ):
                    denied()
            require_process_absent(process)


async def validate_first_create(
    db: Any, window: ControlledWorkerWindow, task: dict[str, Any], claimed_at: Any, *, claim: bool
) -> None:
    """复用共同 workflow 验证事务；必须先于新恢复claim/Factory/Secret。"""
    projection, recovery = window.first_create, window.workflow_recovery
    if (
        window.profile != "approved_first_create"
        or projection is None
        or recovery is None
        or recovery.execution_id is None
        or task["state"] != "completed"
    ):
        denied()
    cur = await db.execute(
        "SELECT *,business.valid_p3_execution(id) AS valid FROM business.executions WHERE id=%s",
        (recovery.execution_id,),
    )
    execution = await cur.fetchone()
    if (
        not execution
        or execution["valid"] is not True
        or execution["status"] != "completed"
        or execution["task_id"] != recovery.task_id
        or execution["item_ids"] != [projection.item_id]
    ):
        denied()
    cur = await db.execute(
        """SELECT d.*,o.request_hash,o.payload AS original_payload,o.provider_idempotency_key,
        o.aggregate_version,o.destination,o.operation,o.sender_enabled,o.source_mode
        FROM business.p4_base_deliveries d JOIN business.outbox o ON o.id=d.outbox_id
        WHERE d.outbox_id=%s AND d.organization_id=%s AND d.shop_id=%s AND d.task_id=%s
        FOR SHARE OF d,o""",
        (projection.outbox_id, window.organization_id, window.shop_id, recovery.task_id),
    )
    delivery = await cur.fetchone()
    if (
        not delivery
        or delivery["verification_mode"] != "controlled_sdk"
        or delivery["target_key"] != recovery.target_key
        or delivery["item_id"] != projection.item_id
        or delivery["version"] != 1
        or delivery["aggregate_version"] != 1
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
    ):
        denied()
    cur = await db.execute(
        "SELECT * FROM business.replenishment_items WHERE id=%s FOR SHARE", (projection.item_id,)
    )
    item = await cur.fetchone()
    cur = await db.execute(
        "SELECT content FROM business.replenishment_plans WHERE id=%s", (execution["plan_id"],)
    )
    plan = await cur.fetchone()
    if (
        not item
        or not plan
        or item["execution_id"] != recovery.execution_id
        or item_snapshot(item, plan["content"], 1).model_dump(mode="json") != delivery["projection"]
    ):
        denied()
    await old_senders_closed(db, window, claimed_at)
    if claim:
        if (
            item["status"] != "open"
            or item["version"] != 1
            or delivery["status"] != "unknown"
            or delivery["attempts"] != 1
            or delivery["last_operation"] != "create"
            or delivery["last_error"] != "INCOMPLETE_READBACK"
            or delivery["external_id"] is not None
        ):
            denied()
        cur = await db.execute(
            """SELECT 1 FROM business.p4_sdk_calls WHERE subject_id=%s
            AND method='bitable.v1.app_table_record.create' LIMIT 1""",
            (projection.outbox_id,),
        )
        if await cur.fetchone():
            denied()  # 包括started/raised/returned/not_called；C0入口不复用任何create预占。
        cur = await db.execute(
            """SELECT 1 FROM business.p4_sdk_windows WHERE organization_id=%s AND shop_id=%s
            AND id<>%s AND configured_enabled AND expires_at>clock_timestamp() LIMIT 1""",
            (window.organization_id, window.shop_id, window.window_id),
        )
        if await cur.fetchone():
            denied()


async def admitted_first_create(
    db: Any, gate: DeliveryGate, ledger: PersistentSDKLedger | None, row: dict[str, Any]
) -> bool:
    """同原delivery行锁内核持久授权和全账本C0；随后原adapter必须完整零匹配预扫。"""
    projection = gate.first_create
    if (
        projection is None
        or ledger is None
        or gate.first_create_window_id != ledger.window.window_id
        or row["outbox_id"] != projection.outbox_id
        or row["item_id"] != projection.item_id
        or row["client_token"] != projection.client_token
        or row["projection_hash"] != projection.projection_hash
        or row["version"] != 1
        or row["status"] != "unknown"
        or row["attempts"] != 1
        or row["last_operation"] != "create"
        or row["last_error"] != "INCOMPLETE_READBACK"
        or row["anchor"] is not None
    ):
        return False
    cur = await db.execute(
        """SELECT after_state FROM business.audit_events WHERE id=%s AND organization_id=%s
        AND source='feishu_recovery' AND action='approved_workflow_claimed'""",
        (gate.first_create_window_id, gate.organization_id),
    )
    claimed = await cur.fetchone()
    if not claimed:
        return False
    try:
        state = ControlledWorkerWindow.model_validate_json(json.dumps(claimed["after_state"]))
    except ValueError:
        return False
    if (
        state.profile != "approved_first_create"
        or state.first_create != projection
        or state.organization_id != gate.organization_id
        or state.shop_id != gate.shop_id
        or state.window_id != ledger.window.window_id
        or state.task_ids != frozenset({row["task_id"]})
        or state.expires_at != gate.expires_at
        or state.caps.get("bitable.v1.app_table_record.create") != 1
    ):
        return False
    cur = await db.execute(
        """SELECT 1 FROM business.p4_sdk_calls WHERE subject_id=%s
        AND method='bitable.v1.app_table_record.create' LIMIT 1""",
        (projection.outbox_id,),
    )
    return await cur.fetchone() is None
