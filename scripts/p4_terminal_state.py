"""原queued item的停写后只读结算；不提供业务提交或观察服务。"""

import json
import time
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import UUID

from commerceops.application.replenishment.contracts import ResolveInput
from commerceops.application.replenishment.execution import resolution_hash
from commerceops.domain.commerce_values import facts_hash
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.replenishment_items import ItemStore
from commerceops.infrastructure.web_sessions import json_native
from commerceops.infrastructure.worker_lock import require_process_absent

from scripts.p4_acceptance import write_private


def classify_t6(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """只给持久快照分类；未知绝不授权另一个close或update。"""
    unknown = dict(state="UNKNOWN", permit_human_close=False, request_key=None)
    try:
        items = snapshot["items"]
        if (
            len(items) != 1
            or isinstance(items[0]["quantity"], (bool, float))
            or Decimal(str(items[0]["quantity"])) != 70
        ):
            return unknown
        item = items[0]
        tasks, approvals = snapshot["tasks"], snapshot["approvals"]
        if (
            len(tasks) != 1
            or len(approvals) != 1
            or tasks[0]["id"] != item["task_id"]
            or tasks[0]["state"] != "completed"
            or approvals[0]["task_id"] != item["task_id"]
            or approvals[0]["status"] != "approved"
            or approvals[0]["decision_source"] != "feishu"
            or tasks[0]["requester_id"] != approvals[0]["decided_by"]
        ):
            return unknown
        deliveries = snapshot["deliveries"]
        v1 = [d for d in deliveries if d["version"] == 1]
        links = snapshot["links"]
        if (
            len(v1) != 1
            or len(links) != 1
            or v1[0]["item_id"] != item["id"]
            or v1[0]["status"] != "verified"
            or v1[0]["verification_mode"] != "controlled_sdk"
            or v1[0]["attempts"] != 1
            or v1[0]["observed_version"] != 1
            or v1[0]["complete_unique_verified"] is not True
            or not v1[0]["external_id"]
            or links[0]["external_id"] != v1[0]["external_id"]
            or links[0]["original_outbox_id"] != v1[0]["outbox_id"]
        ):
            return unknown
        requests, audits = snapshot["requests"], snapshot["item_audit"]
        v2 = [o for o in snapshot["outboxes"] if o["aggregate_version"] == 2]
        resolution_fields = (
            "resolution_id",
            "resolved_by",
            "resolved_at",
            "resolved_identity_id",
            "resolved_auth_version",
            "resolution_reason",
            "resolution_request_key",
            "resolution_payload_hash",
        )
        if (
            item["status"] == "open"
            and item["version"] == 1
            and all(item[k] is None for k in resolution_fields)
            and not requests
            and not audits
            and not v2
            and not any(d["version"] != 1 for d in deliveries)
        ):
            return dict(state="UNCOMMITTED", permit_human_close=True, request_key=None)
        if (
            item["status"] != "closed"
            or item["version"] != 2
            or len(requests) != 1
            or len(audits) != 1
            or len(v2) != 1
            or any(item[k] is None for k in resolution_fields)
        ):
            return unknown
        task, approval = snapshot["tasks"], snapshot["approvals"]
        if len(task) != 1 or len(approval) != 1:
            return unknown
        task, approval = task[0], approval[0]
        if (
            task["requester_id"] != approval["decided_by"]
            or item["resolved_by"] != task["requester_id"]
            or approval["status"] != "approved"
            or approval["decision_source"] != "feishu"
        ):
            return unknown
        semantic = ResolveInput.model_validate_json(
            json.dumps(
                dict(
                    schema_version="p3-web-v1",
                    request_key=str(item["resolution_request_key"]),
                    action="close",
                    reason=item["resolution_reason"],
                    expected_version=1,
                )
            )
        )
        semantic_hash = resolution_hash(str(item["id"]), semantic)
        receipt = requests[0]
        result = receipt["result"]
        expected_payload = dict(
            schema_version="p3-web-v1", item_id=str(item["id"]), version=2, state="closed"
        )
        outbox = v2[0]
        if (
            receipt["request_key"] != item["resolution_request_key"]
            or receipt["principal_id"] != item["resolved_by"]
            or receipt["task_id"] != item["task_id"]
            or receipt["request_hash"] != semantic_hash
            or item["resolution_payload_hash"] != semantic_hash
            or result["request_key"] != str(item["resolution_request_key"])
            or result["identity_mode"] != "session"
            or result["duplicate"] is not False
            or result["resolution"] != json_native(ItemStore.resolution(item))
            or result["item"]["item_id"] != str(item["id"])
            or result["item"]["state"] != "closed"
            or result["item"]["version"] != 2
            or (audits[0]["source"], audits[0]["action"], audits[0]["actor_id"])
            != ("replenishment", "item_closed", item["resolved_by"])
            or outbox["aggregate_id"] != item["id"]
            or outbox["operation"] != "item_projection"
            or outbox["payload"] != expected_payload
            or outbox["request_hash"] != facts_hash(expected_payload)
            or outbox["dedupe_key"] != f"item:{item['id']}:2"
        ):
            return unknown
        return dict(
            state="COMMITTED",
            permit_human_close=False,
            request_key=str(item["resolution_request_key"]),
        )
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return unknown


def collect_final_t6(
    settings: DatabaseSettings,
    organization: UUID,
    shop: UUID,
    task: UUID,
    *,
    writers: Sequence[Mapping[str, Any]],
    output: Path,
) -> dict[str, Any]:
    """所有已绑定API/Worker/Gateway writers退出后，PG仍活时先持久facts再分类。"""
    if not writers or settings.user != "commerceops_app":
        raise PermissionError("P4_T6_WRITER_STOP_REQUIRED")
    for process in writers:
        require_process_absent(dict(process))
    with connect(settings) as db:
        db.execute("SET TRANSACTION READ ONLY")
        db.execute("SET LOCAL statement_timeout='1s'")
        # API OS退出后还需让原数据库连接/在途COMMIT完成或回滚，不能只看API PID。
        drain_end = time.monotonic() + 5
        while True:
            peers = db.execute(
                "SELECT count(*) AS n FROM pg_stat_activity WHERE datname=current_database() "
                "AND usename=current_user AND pid<>pg_backend_pid()"
            ).fetchone()
            if peers is not None and peers["n"] == 0:
                break
            if time.monotonic() >= drain_end:
                write_private(
                    output,
                    dict(
                        stage="DATABASE_WRITER_DRAIN",
                        state="UNKNOWN",
                        peer_count=None if peers is None else peers["n"],
                    ),
                )
                raise PermissionError("P4_T6_DATABASE_WRITER_DRAIN_REQUIRED")
            db.execute("SELECT pg_stat_clear_snapshot()")
            time.sleep(0.02)
        db.commit()
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        db.execute("SET LOCAL statement_timeout='5s'")
        stamp = db.execute("SELECT clock_timestamp() AS at_utc").fetchone()
        if stamp is None:
            raise RuntimeError("P4_T6_DATABASE_UTC_MISSING")
        facts: dict[str, Any] = dict(database_UTC=stamp["at_utc"], writers=json_native(writers))
        for key, query in (
            (
                "tasks",
                "SELECT * FROM business.business_tasks WHERE organization_id=%s "
                "AND shop_id=%s AND id=%s",
            ),
            (
                "approvals",
                "SELECT * FROM business.approvals WHERE organization_id=%s "
                "AND shop_id=%s AND task_id=%s",
            ),
            (
                "items",
                "SELECT * FROM business.replenishment_items WHERE organization_id=%s "
                "AND shop_id=%s AND task_id=%s ORDER BY id",
            ),
            (
                "requests",
                "SELECT * FROM business.web_requests WHERE organization_id=%s "
                "AND task_id=%s AND operation='resolve' AND principal_id IN "
                "(SELECT requester_id FROM business.business_tasks WHERE shop_id=%s AND id=%s)",
            ),
            (
                "item_audit",
                "SELECT * FROM business.audit_events WHERE organization_id=%s "
                "AND task_id=%s AND entity_type='replenishment_item'",
            ),
            (
                "outboxes",
                "SELECT * FROM business.outbox WHERE organization_id=%s "
                "AND shop_id=%s AND task_id=%s AND operation='item_projection' ORDER BY id",
            ),
            (
                "deliveries",
                "SELECT * FROM business.p4_base_deliveries WHERE organization_id=%s "
                "AND shop_id=%s AND task_id=%s ORDER BY version",
            ),
            (
                "links",
                "SELECT l.* FROM business.p4_base_links l JOIN "
                "business.replenishment_items i ON i.id=l.item_id WHERE l.organization_id=%s "
                "AND l.shop_id=%s AND i.task_id=%s",
            ),
        ):
            params: tuple[Any, ...] = (
                (organization, task, shop, task)
                if key == "requests"
                else (organization, task)
                if key == "item_audit"
                else (organization, shop, task)
            )
            facts[key] = db.execute(query, params).fetchall()
        # 原/当前窗口均从同task的不可变授权审计取得；不扫描其他任务或采集wire值。
        terminal_actions = [
            "terminal_update_authorized",
            "terminal_recovery_authorized",
            "terminal_recovery_dispatched",
        ]
        facts["terminal_audit"] = db.execute(
            "SELECT * FROM business.audit_events WHERE organization_id=%s AND task_id=%s "
            "AND ((source='feishu_recovery' AND action=ANY(%s)) "
            "OR (source='feishu_delivery' AND action='base_projection_checked')) ORDER BY id",
            (organization, task, terminal_actions),
        ).fetchall()
        window_ids = {
            UUID(str(event["after_state"]["window_id"]))
            for event in facts["terminal_audit"]
            if event["action"] in terminal_actions[:2]
        }
        facts["sdk_windows"] = db.execute(
            "SELECT * FROM business.p4_sdk_windows WHERE organization_id=%s AND shop_id=%s "
            "AND id=ANY(%s) ORDER BY id",
            (organization, shop, list(window_ids)),
        ).fetchall()
        facts["sdk_calls"] = db.execute(
            "SELECT c.* FROM business.p4_sdk_calls c JOIN business.p4_sdk_windows w "
            "ON w.id=c.window_id WHERE w.organization_id=%s AND w.shop_id=%s "
            "AND w.id=ANY(%s) ORDER BY c.id",
            (organization, shop, list(window_ids)),
        ).fetchall()
        end = db.execute("SELECT clock_timestamp() AS at_utc").fetchone()
        if end is None:
            raise RuntimeError("P4_T6_DATABASE_UTC_MISSING")
        facts["database_UTC_end"] = end["at_utc"]
    # Any unknown or failed semantic assertion must leave the final native facts intact.
    write_private(output, json_native(facts))
    classification = classify_t6(facts)
    write_private(output.with_suffix(".classification.json"), classification)
    return classification


def terminal_recovery_from_native(db: Any, context: Mapping[str, Any], *, expires_at: Any) -> Any:
    """只读当前PG原失败态派生disabled模板；真正准入仍由原生Worker锁内复核。"""
    from uuid import uuid5

    from commerceops.application.feishu_business.worker_window import ControlledWorkerWindow
    from commerceops.infrastructure.feishu_outbox_recovery import (
        sdk_window_hash,
        terminal_authorization_id,
    )
    from commerceops.infrastructure.feishu_terminal_recovery import state_hash

    from scripts.p4_acceptance import require, terminal_window_from_native

    template = terminal_window_from_native(db, context, expires_at=expires_at, queued=True)
    terminal = template.terminal_update
    require(terminal is not None, "P4A_TERMINAL_RECOVERY_TEMPLATE")
    if terminal is None:
        raise PermissionError("P4A_TERMINAL_RECOVERY_TEMPLATE")
    delivery = db.execute(
        "SELECT * FROM business.p4_base_deliveries WHERE outbox_id=%s AND organization_id=%s "
        "AND shop_id=%s AND task_id=%s",
        (
            terminal.projection.outbox_id,
            template.organization_id,
            template.shop_id,
            terminal.verified_recovery.task_id,
        ),
    ).fetchone()
    require(
        delivery is not None and delivery["status"] == "unknown" and delivery["attempts"] == 1,
        "P4A_TERMINAL_RECOVERY_FAILED_STATE",
    )
    if delivery is None:
        raise PermissionError("P4A_TERMINAL_RECOVERY_FAILED_STATE")
    authorization = db.execute(
        "SELECT after_state FROM business.audit_events WHERE id=%s AND organization_id=%s "
        "AND task_id=%s AND source='feishu_recovery' AND action='terminal_update_authorized'",
        (
            terminal_authorization_id(terminal.projection.outbox_id),
            template.organization_id,
            terminal.verified_recovery.task_id,
        ),
    ).fetchone()
    require(authorization is not None, "P4A_TERMINAL_RECOVERY_FAILED_WINDOW")
    if authorization is None:
        raise PermissionError("P4A_TERMINAL_RECOVERY_FAILED_WINDOW")
    prior = ControlledWorkerWindow.model_validate_json(json.dumps(authorization["after_state"]))
    sdk = db.execute(
        "SELECT * FROM business.p4_sdk_windows WHERE id=%s", (prior.window_id,)
    ).fetchone()
    calls = db.execute(
        "SELECT * FROM business.p4_sdk_calls WHERE window_id=%s ORDER BY id",
        (prior.window_id,),
    ).fetchall()
    gateway = db.execute(
        "SELECT after_state FROM business.audit_events WHERE id=%s AND organization_id=%s "
        "AND source='feishu_gateway' AND action='gateway_start_claimed'",
        (prior.gateway_window_id, template.organization_id),
    ).fetchone()

    def termination(source: str, entity: str) -> UUID:
        rows = db.execute(
            "SELECT id FROM business.audit_events WHERE organization_id=%s AND source=%s "
            "AND entity_id=%s AND action='termination_confirmed'",
            (template.organization_id, source, entity),
        ).fetchall()
        require(len(rows) == 1, "P4A_TERMINAL_RECOVERY_FAILED_LIFECYCLE")
        return rows[0]["id"]  # type: ignore[no-any-return]

    require(sdk is not None and gateway is not None, "P4A_TERMINAL_RECOVERY_FAILED_LEDGER")
    if sdk is None or gateway is None:
        raise PermissionError("P4A_TERMINAL_RECOVERY_FAILED_LEDGER")
    value = template.model_dump(mode="json")
    wid, gid = (
        uuid5(prior.window_id, "terminal-recovery-disabled-worker"),
        uuid5(prior.window_id, "terminal-recovery-disabled-gateway"),
    )
    value.update(window_id=str(wid), gateway_window_id=str(gid))
    value["terminal_update"].update(
        worker_window_id=str(wid),
        gateway_window_id=str(gid),
        recovery_of=dict(
            recovery_count=1,
            failed_window_id=str(prior.window_id),
            failed_window_hash=facts_hash(authorization["after_state"]),
            failed_sdk_window_hash=sdk_window_hash(sdk),
            failed_ledger_hash=facts_hash(json_native(calls)),
            failed_delivery_hash=state_hash(delivery),
            failed_gateway_hash=facts_hash(gateway["after_state"]),
            failed_gateway_termination_id=str(
                termination("feishu_gateway", str(prior.gateway_window_id))
            ),
            failed_worker_owner=delivery["claimed_by"],
            failed_worker_termination_id=str(termination("worker", delivery["claimed_by"])),
        ),
    )
    return ControlledWorkerWindow.model_validate_json(json.dumps(value))
