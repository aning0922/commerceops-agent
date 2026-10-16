"""原已受理/未启动任务的窄一次接续；只写原immutable audit，不补旧历史。"""

import json
import os
import socket
from datetime import UTC, datetime
from typing import Any, NoReturn
from uuid import NAMESPACE_URL, UUID, uuid5

from psycopg import sql
from psycopg.types.json import Jsonb

from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.application.feishu_business.gateway_window import GatewayWindow
from commerceops.application.feishu_business.worker_window import ControlledWorkerWindow
from commerceops.domain.commerce_values import facts_hash
from commerceops.infrastructure.feishu_gateway_window import claimed_state
from commerceops.infrastructure.feishu_outbox_recovery import full_process_receipt, receipt_hash
from commerceops.infrastructure.feishu_workflow_recovery import task_binding_hash
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.web_sessions import json_native
from commerceops.infrastructure.worker_lock import (
    open_async,
    process_namespace,
    require_process_absent,
)


def denied() -> NoReturn:
    raise PermissionError("P4_QUEUED_START_DENIED")


def original_task_hash(row: dict[str, Any]) -> str:
    return facts_hash(
        json_native(
            {
                k: row[k]
                for k in (
                    "id",
                    "organization_id",
                    "shop_id",
                    "conversation_id",
                    "requester_id",
                    "kind",
                    "workflow_version",
                    "thread_id",
                    "normalized_request",
                )
            }
        )
    )


def original_jobs_hash(rows: list[dict[str, Any]]) -> str:
    return facts_hash(
        json_native(
            [
                {
                    k: row[k]
                    for k in (
                        "id",
                        "organization_id",
                        "shop_id",
                        "task_id",
                        "kind",
                        "dedupe_key",
                        "payload_ref",
                        "created_at",
                    )
                }
                for row in sorted(rows, key=lambda r: str(r["id"]))
            ]
        )
    )


def attempt_id(window: ControlledWorkerWindow) -> UUID:
    r = window.queued_start
    if r is None:
        denied()
    return uuid5(
        NAMESPACE_URL, f"p4-queued-start:{window.organization_id}:{r.task_id}:{r.inbox_id}"
    )


def admission_id(window: ControlledWorkerWindow) -> UUID:
    return uuid5(window.window_id, "queued-worker-admission")


def authorization_id(window: ControlledWorkerWindow) -> UUID:
    return uuid5(window.window_id, "queued-worker-authorized")


async def audit_claim(
    db: Any, window: ControlledWorkerWindow, identifier: UUID, action: str
) -> None:
    r = window.queued_start
    if r is None:
        denied()
    await db.execute(
        """INSERT INTO business.audit_events(id,organization_id,task_id,source,action,
        entity_type,entity_id,after_state,trace_id) VALUES(%s,%s,%s,'feishu_recovery',%s,
        'queued_workflow',%s,%s,%s)""",
        (
            identifier,
            window.organization_id,
            r.task_id,
            action,
            str(r.task_id),
            Jsonb(window.model_dump(mode="json")),
            window.window_id,
        ),
    )


async def require_claim(
    db: Any, window: ControlledWorkerWindow, identifier: UUID, action: str
) -> None:
    cur = await db.execute(
        """SELECT after_state FROM business.audit_events WHERE id=%s AND organization_id=%s
        AND source='feishu_recovery' AND action=%s AND entity_type='queued_workflow'""",
        (identifier, window.organization_id, action),
    )
    row = await cur.fetchone()
    if not row or row["after_state"] != window.model_dump(mode="json"):
        denied()


async def claim_queued_attempt(
    config: WebConfig,
    settings: BusinessSettings,
    window: ControlledWorkerWindow,
    gateway: GatewayWindow,
) -> None:
    """父arm后先burn固定once；后续校验/WS/Worker失败仍SPENT。"""
    window.window(settings)
    r = window.queued_start
    if r is None or config.database.user != "commerceops_app" or gateway.max_workflows != 0:
        denied()
    async with await open_async(config.database) as db:
        cur = await db.execute(
            """SELECT 1 FROM business.inbox_events i JOIN business.p4_inbox_receipts r
            ON r.inbox_id=i.id JOIN business.business_tasks t ON t.id=i.task_id
            WHERE i.id=%s AND i.task_id=%s AND t.organization_id=%s AND t.shop_id=%s
            AND i.organization_id=t.organization_id AND i.shop_id=t.shop_id
            AND i.source='feishu_business'""",
            (r.inbox_id, r.task_id, window.organization_id, window.shop_id),
        )
        if not await cur.fetchone():
            denied()
        # Commit this transaction BEFORE validation/Gateway; no later rollback can reclaim it.
        async with db.transaction():
            await audit_claim(db, window, attempt_id(window), "queued_start_attempted")
        async with db.transaction():
            await validate(
                db,
                config,
                settings,
                window,
                gateway,
                first=True,
                worker_owner=None,
                require_new=False,
            )


async def trusted_queued_start(
    config: WebConfig,
    settings: BusinessSettings,
    window: ControlledWorkerWindow,
    gateway: GatewayWindow,
    *,
    worker_owner: str,
    claim: bool = True,
) -> None:
    window.window(settings)
    if config.database.user != "commerceops_app" or window.queued_start is None:
        denied()
    if claim and (window.expires_at - datetime.now(UTC)).total_seconds() < 180:
        denied()
    async with await open_async(config.database) as db:
        await require_claim(db, window, attempt_id(window), "queued_start_attempted")
        if claim:
            # A second process/window cannot turn an earlier failed admission into success.
            async with db.transaction():
                await audit_claim(db, window, admission_id(window), "queued_start_admitted")
        else:
            await require_claim(db, window, admission_id(window), "queued_start_admitted")
            await require_claim(db, window, authorization_id(window), "queued_start_authorized")
        async with db.transaction():
            await validate(
                db,
                config,
                settings,
                window,
                gateway,
                first=claim,
                worker_owner=worker_owner,
                require_new=True,
            )
            if claim:
                await audit_claim(db, window, authorization_id(window), "queued_start_authorized")


async def validate(
    db: Any,
    config: WebConfig,
    settings: BusinessSettings,
    window: ControlledWorkerWindow,
    gateway: GatewayWindow,
    *,
    first: bool,
    worker_owner: str | None,
    require_new: bool,
) -> None:
    r = window.queued_start
    if (
        r is None
        or window.profile != "approved_queued_start"
        or not gateway.active()
        or gateway.max_workflows != 0
        or gateway.window_id != window.gateway_window_id
        or gateway.expires_at != window.expires_at
        or (gateway.organization_id, gateway.shop_id) != (window.organization_id, window.shop_id)
    ):
        denied()
    cur = await db.execute(
        """SELECT id,after_state,occurred_at FROM business.audit_events
        WHERE id=ANY(%s) AND organization_id=%s AND source='feishu_gateway'
        AND action='gateway_start_claimed' AND entity_type='gateway_window'""",
        ([r.original_gateway_id, window.gateway_window_id], window.organization_id),
    )
    claims = {row["id"]: row for row in await cur.fetchall()}
    old, new = claims.get(r.original_gateway_id), claims.get(window.gateway_window_id)
    if not old or facts_hash(old["after_state"]) != r.original_gateway_hash:
        denied()
    original = GatewayWindow.model_validate_json(
        json.dumps({key: old["after_state"].get(key) for key in GatewayWindow.model_fields})
    )
    if (
        old["after_state"] != claimed_state(original)
        or original.parameters != gateway.parameters
        or (original.organization_id, original.shop_id) != (window.organization_id, window.shop_id)
    ):
        denied()
    if original.max_workflows != 1 or original.parameters.fixture_case != "known_inbound":
        denied()
    if (original.parameters.L, original.parameters.R, original.parameters.S) != (3, 7, 2):
        denied()
    cur = await db.execute(
        """SELECT id,action,after_state,occurred_at FROM business.audit_events
        WHERE organization_id=%s AND source='feishu_gateway' AND entity_type='gateway_runtime'
        AND entity_id=%s AND action IN ('started','termination_confirmed')""",
        (window.organization_id, str(original.window_id)),
    )
    events = await cur.fetchall()
    starts = [e for e in events if e["action"] == "started"]
    ends = [e for e in events if e["action"] == "termination_confirmed"]
    if (
        len(starts) != 1
        or len(ends) != 1
        or ends[0]["id"] != r.gateway_termination_id
        or not full_process_receipt(starts[0]["after_state"])
        or ends[0]["after_state"].get("process") != starts[0]["after_state"]
        or ends[0]["after_state"].get("child_reaped") is not True
        or type(ends[0]["after_state"].get("child_exit")) is not int
        or not old["occurred_at"] <= starts[0]["occurred_at"] <= ends[0]["occurred_at"]
    ):
        denied()
    require_process_absent(starts[0]["after_state"])
    if require_new:
        if (
            not new
            or new["after_state"] != claimed_state(gateway)
            or not ends[0]["occurred_at"] < new["occurred_at"]
        ):
            denied()
        cur = await db.execute(
            """SELECT action,after_state FROM business.audit_events WHERE organization_id=%s
            AND source='feishu_gateway' AND entity_type='gateway_runtime' AND entity_id=%s
            AND action IN ('started','ready','transport_lost','termination_confirmed')""",
            (window.organization_id, str(gateway.window_id)),
        )
        runtime = await cur.fetchall()
        ready = [e for e in runtime if e["action"] == "ready"]
        running = [e for e in runtime if e["action"] == "started"]
        if (
            len(ready) != 1
            or len(running) != 1
            or any(e["action"] in ("transport_lost", "termination_confirmed") for e in runtime)
        ):
            denied()
        from commerceops.infrastructure.feishu_gateway_ready import ready_state

        if ready[0]["after_state"] != ready_state(running[0]["after_state"]):
            denied()
    cur = await db.execute(
        """SELECT 1 FROM business.audit_events WHERE organization_id=%s AND source='worker'
        AND action='started' AND occurred_at>=%s AND (%s::text IS NULL OR entity_id<>%s)
        LIMIT 1""",
        (window.organization_id, old["occurred_at"], worker_owner, worker_owner),
    )
    if await cur.fetchone():
        denied()
    if worker_owner is not None:
        cur = await db.execute(
            """SELECT after_state,occurred_at FROM business.audit_events WHERE organization_id=%s
            AND source='worker' AND action='started'
            AND entity_type='worker_runtime' AND entity_id=%s""",
            (window.organization_id, worker_owner),
        )
        own = await cur.fetchall()
        process = dict(
            pid=os.getpid(), host=socket.gethostname(), pid_namespace=process_namespace()
        )
        if (
            len(own) != 1
            or own[0]["after_state"] != process
            or not new
            or own[0]["occurred_at"] < new["occurred_at"]
        ):
            denied()
    cur = await db.execute(
        """SELECT 1 FROM business.p4_sdk_windows WHERE organization_id=%s AND created_at>=%s
        AND id<>%s LIMIT 1""",
        (window.organization_id, old["occurred_at"], window.window_id),
    )
    if await cur.fetchone():
        denied()
    # Original common validator keeps current identity/role and original receipt time.
    from commerceops.entrypoints.feishu_worker_child import trusted_tasks

    await trusted_tasks(db, settings, window, original, old["occurred_at"])
    cur = await db.execute(
        """SELECT t.*,s.source_task_id,s.parameters,s.config_version,s.source_report_id,
        s.snapshot_id AS source_snapshot_id,s.facts_hash AS source_facts_hash,
        s.mode AS source_mode,r.inbox_id,r.identity_id,
        r.result,r.created_at AS receipt_at,i.payload_hash,i.sanitized_payload,
        p.auth_version AS operator_auth_version FROM business.business_tasks t
        JOIN business.p3_task_sources s ON s.task_id=t.id AND s.organization_id=t.organization_id
        AND s.shop_id=t.shop_id JOIN business.inbox_events i ON i.task_id=t.id
        AND i.organization_id=t.organization_id AND i.shop_id=t.shop_id
        JOIN business.p4_inbox_receipts r ON r.inbox_id=i.id
        JOIN business.principals p ON p.id=t.requester_id AND p.organization_id=t.organization_id
        WHERE t.id=%s AND r.inbox_id=%s FOR SHARE OF t,s,i,p""",
        (r.task_id, r.inbox_id),
    )
    task = await cur.fetchone()
    if (
        not task
        or task["source_task_id"] != r.source_task_id
        or task_binding_hash(task) != r.task_binding_hash
        or receipt_hash(task) != r.receipt_hash
        or task["operator_auth_version"] != r.operator_auth_version
        or task["config_version"] != config.config_version
        or task["result"].get("task_id") != str(r.task_id)
        or task["sanitized_payload"].get("chat_type") != "p2p"
        or not old["occurred_at"] <= task["receipt_at"] < original.expires_at
        or not task["receipt_at"] < ends[0]["occurred_at"]
    ):
        denied()
    cur = await db.execute(
        "SELECT * FROM business.business_tasks WHERE id=%s FOR SHARE", (r.source_task_id,)
    )
    source = await cur.fetchone()
    if (
        not source
        or original_task_hash(source) != r.source_binding_hash
        or (source["organization_id"], source["shop_id"], source["requester_id"])
        != (task["organization_id"], task["shop_id"], task["requester_id"])
    ):
        denied()
    cur = await db.execute(
        "SELECT * FROM business.jobs WHERE task_id=ANY(%s) "
        "AND (%s OR id=ANY(%s)) ORDER BY id FOR SHARE",
        ([r.task_id, r.source_task_id], first, list(r.job_ids)),
    )
    jobs = await cur.fetchall()
    if (
        len(jobs) != 2
        or {j["id"] for j in jobs} != set(r.job_ids)
        or original_jobs_hash(jobs) != r.jobs_binding_hash
    ):
        denied()
    if (
        source["kind"] != "inventory_analysis_only"
        or source["workflow_version"] != "p203-inventory-analysis-v1"
    ):
        denied()
    expected_jobs = {
        r.source_task_id: ("analyze", f"analysis:{r.source_task_id}", f"task:{r.source_task_id}"),
        r.task_id: ("analyze", f"p3:{r.task_id}", f"task:{r.task_id}"),
    }
    if any(
        (j["kind"], j["dedupe_key"], j["payload_ref"]) != expected_jobs.get(j["task_id"])
        for j in jobs
    ):
        denied()
    if first:
        if task["source_mode"] != "new_cycle" or any(
            task[k] is not None
            for k in ("source_report_id", "source_snapshot_id", "source_facts_hash")
        ):
            denied()
        if any(
            t["state"] != "queued"
            or t["version"] != 1
            or t["active_plan_id"] is not None
            or t["failure_code"] is not None
            for t in (task, source)
        ):
            denied()
        if any(
            j["status"] != "ready"
            or j["attempts"] != 0
            or j["lease_owner"] is not None
            or j["lease_until"] is not None
            or j["last_error"] is not None
            for j in jobs
        ):
            denied()
        for name in (
            "analysis_reports",
            "replenishment_plans",
            "approvals",
            "executions",
            "replenishment_items",
            "outbox",
            "p4_base_deliveries",
            "p4_im_deliveries",
            "p3_observations",
        ):
            cur = await db.execute(
                sql.SQL("SELECT 1 FROM business.{} WHERE task_id=ANY(%s) LIMIT 1").format(
                    sql.Identifier(name)
                ),
                ([r.task_id, r.source_task_id],),
            )
            if await cur.fetchone():
                denied()
        for name in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            cur = await db.execute(
                sql.SQL("SELECT 1 FROM checkpoints.{} WHERE thread_id=ANY(%s) LIMIT 1").format(
                    sql.Identifier(name)
                ),
                ([str(r.task_id), str(r.source_task_id)],),
            )
            if await cur.fetchone():
                denied()
    elif any(
        t["state"] in ("failed", "needs_attention", "needs_reapproval") for t in (task, source)
    ):
        denied()
