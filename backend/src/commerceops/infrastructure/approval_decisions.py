"""锁后T3决定/持久原键/语义重复；没有checkpoint或外部副作用事务。"""

import hmac
import json
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from commerceops.application.replenishment.contracts import (
    Actor,
    DecisionInput,
    FeishuActor,
    WebFailure,
)
from commerceops.application.replenishment.decisions import (
    confirm_set,
    decision_hash,
    decision_request_hash,
)
from commerceops.application.replenishment.security import approval_nonce, digest
from commerceops.domain.commerce_values import canonical_bytes
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.replenishment_repository import visible_task
from commerceops.infrastructure.repository import TaskRepository, TaskScope
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.web_sessions import DB, actor_guard, envelope, now, role_scope


def decision_fields(db: DB, approval: dict[str, Any]) -> dict[str, Any] | None:
    if approval["decision_id"] is None:
        return None
    resume = db.execute(
        "SELECT delivery_state FROM business.approval_resumes WHERE decision_id=%s",
        (approval["decision_id"],),
    ).fetchone()
    if not resume:
        raise WebFailure("NOT_READY")
    return {
        "decision_id": approval["decision_id"],
        "task_id": approval["task_id"],
        "approval_id": approval["id"],
        "plan_id": approval["plan_id"],
        "plan_version": approval["plan_version"],
        "plan_hash": approval["plan_hash"],
        "decision_payload_hash": approval["decision_payload_hash"],
        "action": approval["decision_action"],
        "acknowledged_assumption_keys": approval["acknowledged_assumption_keys"],
        "approval_status": approval["status"],
        "decided_by": approval["decided_by"],
        "decided_at": approval["decided_at"],
        "decision_source": approval["decision_source"],
        "reason_code": approval["reason_code"],
        "resume_state": resume["delivery_state"],
    }


def may_decide(
    db: DB,
    config: WebConfig,
    actor: Actor,
    task: dict[str, Any],
    approval: dict[str, Any],
    plan: dict[str, Any],
) -> bool:
    return bool(
        approval["status"] == "pending"
        and task["state"] in ("awaiting_approval", "needs_reapproval")
        and task["active_plan_id"] == plan["id"]
        and plan["status"] == "current"
        and approval["expires_at"] > now(db)
        and approval["nonce_key_version"] == config.key_version
        and actor.principal_id in approval["eligible_principal_ids"]
        and role_scope(db, actor, task["shop_id"], "approver")
        and plan["content"]["disclosure_complete"]
        and not plan["content"]["hard_blocks"]
    )


def nonce_for(config: WebConfig, approval: dict[str, Any]) -> str:
    if approval["nonce_key_version"] != config.key_version:
        raise WebFailure("SERVICE_UNAVAILABLE", 503)
    value = approval_nonce(
        config.nonce_secret,
        approval["id"],
        approval["plan_id"],
        approval["plan_version"],
        approval["plan_hash"],
        approval["expires_at"],
    )
    if not hmac.compare_digest(digest(value), approval["nonce_hash"]):
        raise WebFailure("SERVICE_UNAVAILABLE", 503)
    return value


class DecisionStore:
    def __init__(self, config: WebConfig):
        self.config, self.settings = config, config.database

    def authorize(self, actor: Actor, approval_id: UUID) -> dict[str, Any]:
        # 预检独立短事务，不持principal锁进入下面task→plan→approval→principal锁序。
        with connect(self.settings) as db:
            actor_guard(db, actor)
            approval = db.execute(
                "SELECT * FROM business.approvals WHERE id=%s AND organization_id=%s",
                (approval_id, actor.organization_id),
            ).fetchone()
            if not approval:
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            task = visible_task(db, actor, approval["task_id"])
            if not (approval["decision_id"] and approval["decided_by"] == actor.principal_id):
                if not role_scope(db, actor, task["shop_id"], "approver"):
                    raise WebFailure("ACCESS_DENIED", 403)
                if actor.principal_id not in approval["eligible_principal_ids"]:
                    raise WebFailure("RESOURCE_NOT_FOUND", 404)
            return approval

    def decide(
        self,
        actor: Actor,
        path: UUID,
        request: DecisionInput,
        *,
        hook: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        initial = self.authorize(actor, path)
        with connect(self.settings) as db:
            receipt = self.decide_in_transaction(
                db, actor, path, request, initial=initial, hook=hook
            )
        if hook:
            hook("after_t3_commit")
        return receipt

    def decide_in_transaction(
        self,
        db: DB,
        actor: Actor,
        path: UUID,
        request: DecisionInput,
        *,
        initial: dict[str, Any] | None = None,
        binding_check: Callable[[DB, dict[str, Any]], None] | None = None,
        hook: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        if initial is None:
            initial = db.execute(
                "SELECT * FROM business.approvals WHERE id=%s AND organization_id=%s",
                (path, actor.organization_id),
            ).fetchone()
        if not initial:
            raise WebFailure("RESOURCE_NOT_FOUND", 404)
        if path != request.approval_id:
            raise WebFailure("INVALID_REQUEST", 422)
        semantic = decision_hash(request)
        request_hash = decision_request_hash(request, str(path))
        db.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
            (f"web:decision:{actor.principal_id}:{request.request_key}",),
        )
        task = db.execute(
            "SELECT * FROM business.business_tasks WHERE id=%s FOR UPDATE",
            (initial["task_id"],),
        ).fetchone()
        plan = db.execute(
            "SELECT * FROM business.replenishment_plans WHERE id=%s FOR UPDATE",
            (initial["plan_id"],),
        ).fetchone()
        approval = db.execute(
            "SELECT * FROM business.approvals WHERE id=%s FOR UPDATE", (path,)
        ).fetchone()
        if not task or not plan or not approval:
            raise WebFailure("RESOURCE_NOT_FOUND", 404)
        actor_guard(db, actor)
        visible_task(db, actor, task["id"])
        if binding_check:
            binding_check(db, approval)
        previous = db.execute(
            """SELECT * FROM business.web_requests WHERE principal_id=%s
         AND operation='decision' AND request_key=%s""",
            (actor.principal_id, request.request_key),
        ).fetchone()
        if previous and previous["request_hash"] != request_hash:
            raise WebFailure("IDEMPOTENCY_CONFLICT")
        valid_nonce = hmac.compare_digest(digest(request.nonce), approval["nonce_hash"])
        if (request.plan_id, request.plan_version, request.plan_hash) != (
            approval["plan_id"],
            approval["plan_version"],
            approval["plan_hash"],
        ):
            raise WebFailure("APPROVAL_SUPERSEDED")
        if not valid_nonce:
            raise WebFailure("INVALID_REQUEST", 422)
        duplicate = approval["decision_id"] is not None
        if duplicate:
            if (approval["decided_by"], approval["decision_payload_hash"]) != (
                actor.principal_id,
                semantic,
            ):
                raise WebFailure("DECISION_CONFLICT")
        else:
            nonce_for(self.config, approval)  # 新决定必须当前专用key可验证；旧决定只读不重批。
            if not role_scope(db, actor, task["shop_id"], "approver"):
                raise WebFailure("ACCESS_DENIED", 403)
            if actor.principal_id not in approval["eligible_principal_ids"]:
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            timestamp = now(db)  # 全部身份/业务锁取得之后的DB时钟。
            if approval["expires_at"] <= timestamp or approval["status"] == "expired":
                raise WebFailure("APPROVAL_EXPIRED", 410)
            if (
                approval["status"] != "pending"
                or plan["status"] != "current"
                or task["active_plan_id"] != plan["id"]
            ):
                raise WebFailure("APPROVAL_SUPERSEDED")
            if task["state"] not in ("awaiting_approval", "needs_reapproval"):
                raise WebFailure("NOT_READY")
            confirm_set(request, plan["content"])
            decision_id = uuid4()
            rejected = request.action in ("reject", "reject_assumptions")
            row = db.execute(
                """UPDATE business.approvals SET status=%s,decision_id=%s,
             decision_action=%s,decision_payload_hash=%s,acknowledged_assumption_keys=%s,
             decided_by=%s,decided_at=%s,decision_source=%s,decision_request_key=%s,
             reason_code=%s,decided_auth_version=%s,decided_identity_id=%s
             WHERE id=%s AND status='pending' RETURNING *""",
                (
                    "rejected" if rejected else "approved",
                    decision_id,
                    request.action,
                    semantic,
                    list(request.acknowledged_assumption_keys),
                    actor.principal_id,
                    timestamp,
                    "feishu" if isinstance(actor, FeishuActor) else "web",
                    request.request_key,
                    "INBOUND_ASSUMPTION_DECLINED"
                    if request.action == "reject_assumptions"
                    else None,
                    actor.auth_version,
                    actor.identity_id,
                    path,
                ),
            ).fetchone()
            if not row:
                raise WebFailure("DECISION_CONFLICT")
            approval = row
            job = TaskRepository(db, TaskScope(actor.organization_id, task["shop_id"])).enqueue(
                task["id"], "resume", f"p3-decision:{decision_id}", f"decision:{decision_id}"
            )
            db.execute(
                """INSERT INTO business.approval_resumes
             (decision_id,approval_id,organization_id,shop_id,task_id,job_id,delivery_state)
             VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (
                    decision_id,
                    path,
                    actor.organization_id,
                    task["shop_id"],
                    task["id"],
                    job,
                    "queued" if approval["ready_at"] else "waiting_checkpoint",
                ),
            )
            db.execute(
                """INSERT INTO business.audit_events
             (id,organization_id,task_id,actor_id,source,action,entity_type,entity_id,trace_id)
             VALUES (%s,%s,%s,%s,'replenishment','approval_decided','approval',%s,%s)""",
                (
                    uuid4(),
                    actor.organization_id,
                    task["id"],
                    actor.principal_id,
                    str(path),
                    uuid4(),
                ),
            )
        fields = decision_fields(db, approval)
        if not fields:
            raise WebFailure("NOT_READY")
        receipt = envelope(db, **fields, request_key=request.request_key, duplicate=duplicate)
        if not previous:
            db.execute(
                """INSERT INTO business.web_requests
             (organization_id,principal_id,operation,request_key,request_hash,task_id,result)
             VALUES (%s,%s,'decision',%s,%s,%s,%s)""",
                (
                    actor.organization_id,
                    actor.principal_id,
                    request.request_key,
                    request_hash,
                    task["id"],
                    Jsonb(json.loads(canonical_bytes(receipt))),
                ),
            )
        if hook:
            hook("before_t3_commit")
        return receipt
