"""原queued单次成功v1来源；不消耗或构造旧explicit RO历史。"""

import json
from typing import Any

from commerceops.application.feishu_business.recovery import VerifiedQueuedV1
from commerceops.application.feishu_business.worker_window import (
    KNOWN70_CAPS,
    ControlledWorkerWindow,
)
from commerceops.infrastructure.feishu_outbox_recovery import (
    _terminal_closed,
    sdk_window_hash,
    terminal_denied,
)


async def trusted_queued_v1_source(
    db: Any, window: ControlledWorkerWindow, verified_at: Any
) -> None:
    from commerceops.infrastructure.feishu_queued_start import (
        admission_id,
        attempt_id,
        authorization_id,
        original_jobs_hash,
        original_task_hash,
        require_claim,
    )
    from commerceops.infrastructure.feishu_workflow_recovery import task_binding_hash

    terminal = window.terminal_update
    if terminal is None or not isinstance(terminal.verified_recovery, VerifiedQueuedV1):
        terminal_denied()
    source = terminal.verified_recovery
    queued = source.queued_start
    from uuid import uuid5

    cur = await db.execute(
        "SELECT after_state FROM business.audit_events WHERE id=%s AND organization_id=%s "
        "AND task_id=%s AND source='feishu_recovery' AND action='queued_start_authorized' "
        "AND entity_type='queued_workflow'",
        (
            uuid5(source.worker_window_id, "queued-worker-authorized"),
            window.organization_id,
            source.task_id,
        ),
    )
    row = await cur.fetchone()
    if not row:
        terminal_denied()
    prior = ControlledWorkerWindow.model_validate_json(json.dumps(row["after_state"]))
    if (
        prior.profile != "approved_queued_start"
        or prior.queued_start != queued
        or not prior.enabled
        or prior.caps != dict(KNOWN70_CAPS)
        or (prior.organization_id, prior.shop_id) != (window.organization_id, window.shop_id)
        or prior.task_ids != window.task_ids
    ):
        terminal_denied()
    for identifier, action in (
        (attempt_id(prior), "queued_start_attempted"),
        (admission_id(prior), "queued_start_admitted"),
        (authorization_id(prior), "queued_start_authorized"),
    ):
        await require_claim(db, prior, identifier, action)
    await _terminal_closed(
        db,
        window.organization_id,
        "feishu_gateway",
        "gateway_runtime",
        str(queued.original_gateway_id),
        queued.gateway_termination_id,
        verified_at,
    )
    cur = await db.execute(
        "SELECT t.*,s.source_task_id,s.parameters,s.config_version FROM business.business_tasks t "
        "JOIN business.p3_task_sources s ON s.task_id=t.id WHERE t.id=%s "
        "AND t.organization_id=%s AND t.shop_id=%s",
        (source.task_id, window.organization_id, window.shop_id),
    )
    task = await cur.fetchone()
    if not task or task_binding_hash(task) != queued.task_binding_hash:
        terminal_denied()
    cur = await db.execute(
        "SELECT * FROM business.business_tasks WHERE id=%s AND organization_id=%s AND shop_id=%s",
        (queued.source_task_id, window.organization_id, window.shop_id),
    )
    original_source = await cur.fetchone()
    if not original_source or original_task_hash(original_source) != queued.source_binding_hash:
        terminal_denied()
    cur = await db.execute(
        "SELECT * FROM business.jobs WHERE id=ANY(%s) AND organization_id=%s AND shop_id=%s",
        (list(queued.job_ids), window.organization_id, window.shop_id),
    )
    jobs = await cur.fetchall()
    if len(jobs) != 2 or original_jobs_hash(jobs) != queued.jobs_binding_hash:
        terminal_denied()
    cur = await db.execute(
        "SELECT * FROM business.p4_sdk_windows WHERE id=%s", (source.worker_window_id,)
    )
    sdk = await cur.fetchone()
    if (
        not sdk
        or sdk_window_hash(sdk) != terminal.verified_sdk_window_hash
        or sdk["method_caps"] != prior.caps
        or not sdk["configured_enabled"]
        or sdk["verification_mode"] != "controlled_sdk"
        or sdk["expires_at"] != prior.expires_at
        or (sdk["organization_id"], sdk["shop_id"]) != (window.organization_id, window.shop_id)
    ):
        terminal_denied()
    cur = await db.execute(
        "SELECT method,status,http_status,provider_code,scope_kind,task_id,subject_id "
        "FROM business.p4_sdk_calls WHERE window_id=%s",
        (prior.window_id,),
    )
    calls = await cur.fetchall()
    counts = {method: sum(c["method"] == method for c in calls) for method in KNOWN70_CAPS}
    if (
        any(
            c["method"] not in KNOWN70_CAPS
            or c["status"] != "returned"
            or c["http_status"] != 200
            or c["provider_code"] != 0
            for c in calls
        )
        or any(counts[m] > KNOWN70_CAPS[m] for m in counts)
        or counts["auth.v3.tenant_access_token.internal"] != 1
        or counts["bot.v3.info"] != 1
        or counts["bitable.v1.app_table.list"] < 1
        or counts["bitable.v1.app_table_field.list"] < 1
        or counts["bitable.v1.app_table_record.create"] != 1
        or counts["bitable.v1.app_table_record.update"] != 0
        or counts["bitable.v1.app_table_record.list"] < 2
        or counts["im.v1.message.create"] < 1
    ):
        terminal_denied()
    cur = await db.execute(
        "SELECT o.id,o.operation FROM business.outbox o JOIN business.p4_im_deliveries d "
        "ON d.outbox_id=o.id WHERE o.organization_id=%s AND o.shop_id=%s AND o.task_id=%s "
        "AND o.operation IN ('approval_card','task_result') AND d.status='sent' "
        "AND d.claimed_by=%s",
        (
            window.organization_id,
            window.shop_id,
            source.task_id,
            str(terminal.verified_worker_owner),
        ),
    )
    notices = {r["id"]: r["operation"] for r in await cur.fetchall()}
    for call in calls:
        method = call["method"]
        if method in (
            "auth.v3.tenant_access_token.internal",
            "bot.v3.info",
            "bitable.v1.app_table.list",
            "bitable.v1.app_table_field.list",
        ):
            valid = (call["scope_kind"], call["task_id"], call["subject_id"]) == (
                "preflight",
                None,
                prior.window_id,
            )
        elif method == "im.v1.message.create":
            valid = (
                call["task_id"] == source.task_id
                and notices.get(call["subject_id"]) == call["scope_kind"]
            )
        else:
            valid = (call["scope_kind"], call["task_id"], call["subject_id"]) == (
                "base_projection",
                source.task_id,
                source.projections[0].outbox_id,
            )
        if not valid:
            terminal_denied()
    cur = await db.execute(
        "SELECT count(*) AS n FROM business.p4_base_deliveries WHERE task_id=%s "
        "AND organization_id=%s AND shop_id=%s AND version=1",
        (source.task_id, window.organization_id, window.shop_id),
    )
    if await cur.fetchone() != {"n": 1}:
        terminal_denied()
