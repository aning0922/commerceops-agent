"""Fixed M1 acceptance reads; no bootstrap, grants, transport calls or business writes.

The shared acceptance entry owns source verification and connections. Runtime reads
must use a real app connection; owner diagnostics never satisfy that requirement.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

REVISIONS = ("0015_p4_read_replies", "0016_p4_clarification_requests")
CASE_COUNTS = {"recover_single_item": 1, "batch_twenty_items": 20}
UUID_OID, TEXT_OID, INT_OID, BIGINT_OID = 2950, 25, 23, 20
BOOL_OID, NUMERIC_OID, TIME_OID, JSON_OID, UUID_ARRAY_OID = 16, 1700, 1184, 3802, 2951


class CaptureFailure(Exception):
    def __init__(self, code: str, query_id: str, sqlstate: str | None = None) -> None:
        super().__init__(code)
        self.code, self.query_id = code, query_id
        self.sqlstate = sqlstate if sqlstate and re.fullmatch(r"[0-9A-Z]{5}", sqlstate) else None

    def safe(self) -> dict[str, Any]:
        return {"code": self.code, "query_id": self.query_id, "sqlstate": self.sqlstate}


@dataclass(frozen=True)
class CaptureContext:
    revision: str
    organization_id: str
    shop_id: str
    task_id: str
    item_id: str
    principal_id: str
    identity_id: str
    auth_version: int
    checkpoint_threads: tuple[str, ...]
    request_key: str | None = None
    sdk_window_id: str | None = None
    sdk_subject_ids: tuple[str, ...] = ()
    case_kind: str = field(kw_only=True)
    expected_item_count: int = field(kw_only=True)
    expected_quantity_total: str = field(kw_only=True)

    def __post_init__(self) -> None:
        if self.revision not in REVISIONS or type(self.auth_version) is not int:
            raise CaptureFailure("CONTEXT_INVALID", "CONTEXT")
        if (
            self.case_kind not in CASE_COUNTS
            or type(self.expected_item_count) is not int
            or self.expected_item_count != CASE_COUNTS[self.case_kind]
            or not isinstance(self.expected_quantity_total, str)
            or not re.fullmatch(r"[1-9][0-9]{0,17}(?:\.[0-9]{1,6})?", self.expected_quantity_total)
            or (self.case_kind == "batch_twenty_items" and self.expected_quantity_total != "2000")
        ):
            raise CaptureFailure("CASE_CONTEXT_INVALID", "CONTEXT")
        if self.auth_version < 1 or not 1 <= len(self.checkpoint_threads) <= 6:
            raise CaptureFailure("CONTEXT_INVALID", "CONTEXT")
        try:
            for value in (
                self.organization_id,
                self.shop_id,
                self.task_id,
                self.item_id,
                self.principal_id,
                self.identity_id,
                *self.sdk_subject_ids,
            ):
                UUID(value)
            if self.request_key is not None:
                UUID(self.request_key)
            if self.sdk_window_id is not None:
                UUID(self.sdk_window_id)
        except (ValueError, TypeError, AttributeError):
            raise CaptureFailure("CONTEXT_INVALID", "CONTEXT") from None
        if any(not re.fullmatch(r"[A-Za-z0-9_:./-]{1,256}", t) for t in self.checkpoint_threads):
            raise CaptureFailure("CONTEXT_INVALID", "CONTEXT")
        if len(set(self.checkpoint_threads)) != len(self.checkpoint_threads):
            raise CaptureFailure("CONTEXT_INVALID", "CONTEXT")

    def parameters(self) -> dict[str, Any]:
        return {
            "org": UUID(self.organization_id),
            "shop": UUID(self.shop_id),
            "task": UUID(self.task_id),
            "item": UUID(self.item_id),
            "item_text": self.item_id,
            "principal": UUID(self.principal_id),
            "identity": UUID(self.identity_id),
            "key": UUID(self.request_key) if self.request_key else None,
            "threads": list(self.checkpoint_threads),
            "sdk_window": UUID(self.sdk_window_id) if self.sdk_window_id else None,
            "subjects": [UUID(v) for v in self.sdk_subject_ids],
        }

    def scope(self) -> dict[str, Any]:
        return {
            "organization_id": self.organization_id,
            "shop_id": self.shop_id,
            "task_id": self.task_id,
            "item_id": self.item_id,
            "checkpoint_threads": list(self.checkpoint_threads),
            "case_kind": self.case_kind,
            "expected_item_count": self.expected_item_count,
            "expected_quantity_total": self.expected_quantity_total,
        }


@dataclass(frozen=True)
class Query:
    query_id: str
    sql: str
    parameters: tuple[str, ...]
    fields: tuple[tuple[str, int], ...]
    minimum_revision: str = REVISIONS[0]


def fields(**values: int) -> tuple[tuple[str, int], ...]:
    return tuple(values.items())


QUERIES = (
    Query(
        "TASK",
        "SELECT id,organization_id,shop_id,kind,state,version,active_plan_id,"
        "workflow_version,thread_id,failure_code FROM business.business_tasks "
        "WHERE id=%s AND organization_id=%s AND shop_id=%s",
        ("task", "org", "shop"),
        fields(
            id=UUID_OID,
            organization_id=UUID_OID,
            shop_id=UUID_OID,
            kind=TEXT_OID,
            state=TEXT_OID,
            version=INT_OID,
            active_plan_id=UUID_OID,
            workflow_version=TEXT_OID,
            thread_id=TEXT_OID,
            failure_code=TEXT_OID,
        ),
    ),
    Query(
        "PLANS",
        "SELECT id,task_id,version,status,source_task_id,report_id,snapshot_id,"
        "facts_hash,plan_hash,plan_hash=encode(sha256(convert_to(canonical_content,'UTF8')),"
        "'hex') AS canonical_hash_matches FROM business.replenishment_plans "
        "WHERE task_id=%s AND organization_id=%s AND shop_id=%s ORDER BY version",
        ("task", "org", "shop"),
        fields(
            id=UUID_OID,
            task_id=UUID_OID,
            version=INT_OID,
            status=TEXT_OID,
            source_task_id=UUID_OID,
            report_id=UUID_OID,
            snapshot_id=UUID_OID,
            facts_hash=TEXT_OID,
            plan_hash=TEXT_OID,
            canonical_hash_matches=BOOL_OID,
        ),
    ),
    Query(
        "APPROVALS",
        "SELECT id,plan_id,plan_version,plan_hash,status,decision_id,"
        "decision_action,decided_by,decision_request_key,consumed_at FROM business.approvals "
        "WHERE task_id=%s AND organization_id=%s AND shop_id=%s ORDER BY id",
        ("task", "org", "shop"),
        fields(
            id=UUID_OID,
            plan_id=UUID_OID,
            plan_version=INT_OID,
            plan_hash=TEXT_OID,
            status=TEXT_OID,
            decision_id=UUID_OID,
            decision_action=TEXT_OID,
            decided_by=UUID_OID,
            decision_request_key=UUID_OID,
            consumed_at=TIME_OID,
        ),
    ),
    Query(
        "EXECUTIONS",
        "SELECT id,task_id,plan_id,approval_id,operation_key,status,item_ids,"
        "revalidation_snapshot_id,completed_at FROM business.executions "
        "WHERE task_id=%s AND organization_id=%s AND shop_id=%s ORDER BY id",
        ("task", "org", "shop"),
        fields(
            id=UUID_OID,
            task_id=UUID_OID,
            plan_id=UUID_OID,
            approval_id=UUID_OID,
            operation_key=TEXT_OID,
            status=TEXT_OID,
            item_ids=UUID_ARRAY_OID,
            revalidation_snapshot_id=UUID_OID,
            completed_at=TIME_OID,
        ),
    ),
    Query(
        "ITEMS",
        "SELECT id,task_id,execution_id,sku_key,quantity,status,version,"
        "approved_plan_id,source_snapshot_id,resolution_id,resolution_reason,resolved_by,"
        "resolved_identity_id,resolved_auth_version,resolution_request_key,"
        "resolution_payload_hash,resolved_at FROM business.replenishment_items "
        "WHERE task_id=%s AND organization_id=%s AND shop_id=%s ORDER BY id",
        ("task", "org", "shop"),
        fields(
            id=UUID_OID,
            task_id=UUID_OID,
            execution_id=UUID_OID,
            sku_key=TEXT_OID,
            quantity=NUMERIC_OID,
            status=TEXT_OID,
            version=INT_OID,
            approved_plan_id=UUID_OID,
            source_snapshot_id=UUID_OID,
            resolution_id=UUID_OID,
            resolution_reason=TEXT_OID,
            resolved_by=UUID_OID,
            resolved_identity_id=UUID_OID,
            resolved_auth_version=BIGINT_OID,
            resolution_request_key=UUID_OID,
            resolution_payload_hash=TEXT_OID,
            resolved_at=TIME_OID,
        ),
    ),
    Query(
        "ITEM_AUDIT",
        "SELECT id,task_id,actor_id,source,action,entity_type,entity_id,"
        "occurred_at FROM business.audit_events WHERE organization_id=%s AND task_id=%s "
        "AND entity_type='replenishment_item' AND entity_id=%s ORDER BY occurred_at,id",
        ("org", "task", "item_text"),
        fields(
            id=UUID_OID,
            task_id=UUID_OID,
            actor_id=UUID_OID,
            source=TEXT_OID,
            action=TEXT_OID,
            entity_type=TEXT_OID,
            entity_id=TEXT_OID,
            occurred_at=TIME_OID,
        ),
    ),
    Query(
        "JOBS",
        "SELECT id,kind,status,attempts,lease_owner FROM business.jobs "
        "WHERE task_id=%s AND organization_id=%s AND shop_id=%s ORDER BY id",
        ("task", "org", "shop"),
        fields(id=UUID_OID, kind=TEXT_OID, status=TEXT_OID, attempts=INT_OID, lease_owner=TEXT_OID),
    ),
    Query(
        "REQUEST",
        "SELECT organization_id,principal_id,operation,request_key,request_hash,"
        "task_id,result FROM business.web_requests WHERE organization_id=%s AND "
        "principal_id=%s AND operation='resolve' AND request_key=%s",
        ("org", "principal", "key"),
        fields(
            organization_id=UUID_OID,
            principal_id=UUID_OID,
            operation=TEXT_OID,
            request_key=UUID_OID,
            request_hash=TEXT_OID,
            task_id=UUID_OID,
            result=JSON_OID,
        ),
    ),
    Query(
        "OUTBOX",
        "SELECT id,organization_id,shop_id,task_id,destination,aggregate_id,aggregate_version,"
        "operation,dedupe_key,request_hash,payload,provider_idempotency_key,status,attempts "
        "FROM business.outbox WHERE organization_id=%s AND shop_id=%s AND task_id=%s ORDER BY id",
        ("org", "shop", "task"),
        fields(
            id=UUID_OID,
            organization_id=UUID_OID,
            shop_id=UUID_OID,
            task_id=UUID_OID,
            destination=TEXT_OID,
            aggregate_id=UUID_OID,
            aggregate_version=INT_OID,
            operation=TEXT_OID,
            dedupe_key=TEXT_OID,
            request_hash=TEXT_OID,
            payload=JSON_OID,
            provider_idempotency_key=UUID_OID,
            status=TEXT_OID,
            attempts=INT_OID,
        ),
    ),
    Query(
        "PROJECTIONS",
        "SELECT outbox_id,item_id,target_key,version,verification_mode,status,"
        "projection,projection_hash,external_id,observed_version,complete_unique_verified "
        "FROM business.p4_base_deliveries WHERE organization_id=%s AND shop_id=%s "
        "AND task_id=%s ORDER BY item_id,version,outbox_id",
        ("org", "shop", "task"),
        fields(
            outbox_id=UUID_OID,
            item_id=UUID_OID,
            target_key=TEXT_OID,
            version=INT_OID,
            verification_mode=TEXT_OID,
            status=TEXT_OID,
            projection=JSON_OID,
            projection_hash=TEXT_OID,
            external_id=TEXT_OID,
            observed_version=INT_OID,
            complete_unique_verified=BOOL_OID,
        ),
    ),
    Query(
        "ANCHOR",
        "SELECT item_id,target_key,original_outbox_id,external_id "
        "FROM business.p4_base_links WHERE organization_id=%s AND shop_id=%s AND item_id=%s "
        "ORDER BY target_key",
        ("org", "shop", "item"),
        fields(
            item_id=UUID_OID, target_key=TEXT_OID, original_outbox_id=UUID_OID, external_id=TEXT_OID
        ),
    ),
    Query(
        "READ_REPLIES",
        "SELECT id,task_id,source_kind,source_task_id,report_id,snapshot_id,"
        "facts_hash,payload_hash,status,attempts FROM business.p4_read_replies "
        "WHERE organization_id=%s AND shop_id=%s AND task_id=%s ORDER BY id",
        ("org", "shop", "task"),
        fields(
            id=UUID_OID,
            task_id=UUID_OID,
            source_kind=TEXT_OID,
            source_task_id=UUID_OID,
            report_id=UUID_OID,
            snapshot_id=UUID_OID,
            facts_hash=TEXT_OID,
            payload_hash=TEXT_OID,
            status=TEXT_OID,
            attempts=INT_OID,
        ),
    ),
    Query(
        "CLARIFICATIONS",
        "SELECT id,principal_id,identity_id,auth_version,request_key,round,"
        "state,task_id,source_hash,candidate_hash FROM business.p4_clarification_requests "
        "WHERE organization_id=%s AND shop_id=%s AND task_id=%s ORDER BY id",
        ("org", "shop", "task"),
        fields(
            id=UUID_OID,
            principal_id=UUID_OID,
            identity_id=UUID_OID,
            auth_version=BIGINT_OID,
            request_key=UUID_OID,
            round=BIGINT_OID,
            state=TEXT_OID,
            task_id=UUID_OID,
            source_hash=TEXT_OID,
            candidate_hash=TEXT_OID,
        ),
        minimum_revision=REVISIONS[1],
    ),
    Query(
        "MODEL_CALLS",
        "SELECT count(*) AS n,count(*) FILTER (WHERE evidence_mode='actual_provider') "
        "AS provider_calls FROM business.model_calls WHERE organization_id=%s AND shop_id=%s",
        ("org", "shop"),
        fields(n=BIGINT_OID, provider_calls=BIGINT_OID),
    ),
    Query(
        "IDENTITY",
        "SELECT p.id AS principal_id,p.enabled,p.auth_version,i.id AS identity_id,"
        "i.provider FROM business.principals p JOIN business.identities i ON "
        "i.principal_id=p.id AND i.organization_id=p.organization_id "
        "WHERE p.organization_id=%s AND p.id=%s AND i.id=%s",
        ("org", "principal", "identity"),
        fields(
            principal_id=UUID_OID,
            enabled=BOOL_OID,
            auth_version=INT_OID,
            identity_id=UUID_OID,
            provider=TEXT_OID,
        ),
    ),
    Query(
        "SDK_WINDOW",
        "SELECT id,organization_id,shop_id,expires_at,configured_enabled,"
        "method_caps,verification_mode FROM business.p4_sdk_windows WHERE id=%s "
        "AND organization_id=%s AND shop_id=%s",
        ("sdk_window", "org", "shop"),
        fields(
            id=UUID_OID,
            organization_id=UUID_OID,
            shop_id=UUID_OID,
            expires_at=TIME_OID,
            configured_enabled=BOOL_OID,
            method_caps=JSON_OID,
            verification_mode=TEXT_OID,
        ),
    ),
    Query(
        "SDK_LEDGER",
        "SELECT id,window_id,subject_id,task_id,scope_kind,method,status,"
        "http_status,provider_code FROM business.p4_sdk_calls WHERE window_id=%s "
        "AND subject_id=ANY(%s::uuid[]) ORDER BY id",
        ("sdk_window", "subjects"),
        fields(
            id=UUID_OID,
            window_id=UUID_OID,
            subject_id=UUID_OID,
            task_id=UUID_OID,
            scope_kind=TEXT_OID,
            method=TEXT_OID,
            status=TEXT_OID,
            http_status=INT_OID,
            provider_code=INT_OID,
        ),
    ),
) + tuple(
    Query(
        "CP_" + name.upper(),
        "SELECT count(*) AS n,encode(sha256(convert_to(COALESCE("  # noqa: S608 - three literal table identifiers
        "string_agg(to_jsonb(t)::text,'|' ORDER BY to_jsonb(t)::text),''),'UTF8')),'hex') "
        "AS sha256 FROM checkpoints." + name + " t WHERE thread_id=ANY(%s::text[])",
        ("threads",),
        fields(n=BIGINT_OID, sha256=TEXT_OID),
    )
    for name in ("checkpoints", "checkpoint_blobs", "checkpoint_writes")
)


def normalized(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, dict):
        return {k: normalized(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalized(v) for v in value]
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise CaptureFailure("RETURN_TYPE_INVALID", "NORMALIZE")


def execute_query(db: Any, query: Query, context: CaptureContext) -> dict[str, Any]:
    values = context.parameters()
    try:
        with db.transaction():
            cur = db.execute(query.sql, tuple(values[k] for k in query.parameters))
            observed = tuple((c.name, c.type_code) for c in cur.description)
            if observed != query.fields:
                raise CaptureFailure("RETURN_FIELDS_INVALID", query.query_id)
            result = cur.fetchall()
            if any(not isinstance(r, dict) or set(r) != dict(query.fields).keys() for r in result):
                raise CaptureFailure("RETURN_SHAPE_INVALID", query.query_id)
            return {
                "status": "PASSED",
                "rows": normalized(result),
                "fields": [{"name": n, "oid": t} for n, t in observed],
            }
    except CaptureFailure:
        raise
    except Exception as error:
        state = getattr(error, "sqlstate", None)
        if (
            context.revision == REVISIONS[0]
            and query.minimum_revision == REVISIONS[1]
            and state == "42P01"
        ):
            return {"status": "EXPECTED_ABSENT", "rows": None, "sqlstate": state}
        raise CaptureFailure("SQL_FAILED", query.query_id, state) from None


def require_app_role(db: Any) -> dict[str, Any]:
    try:
        row = db.execute(
            "SELECT current_user::text AS current_role,session_user::text AS session_role"
        ).fetchone()
        flags = db.execute(
            "SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user"
        ).fetchone()
    except Exception as error:
        raise CaptureFailure(
            "ROLE_QUERY_FAILED", "APP_ROLE", getattr(error, "sqlstate", None)
        ) from None
    if row != {"current_role": "commerceops_app", "session_role": "commerceops_app"} or flags != {
        "rolsuper": False,
        "rolcreatedb": False,
        "rolcreaterole": False,
    }:
        raise CaptureFailure("APP_ROLE_REQUIRED", "APP_ROLE")
    return {"identity": row, "flags": flags}


def capture_snapshot(db: Any, context: CaptureContext) -> dict[str, Any]:
    """Caller opens one fresh transaction/connection; no owner fallback or role switch."""
    try:
        db.execute("SET TRANSACTION READ ONLY")
        db.execute("SET LOCAL statement_timeout='5000ms'")
        db.execute("SET LOCAL lock_timeout='3000ms'")
    except Exception as error:
        raise CaptureFailure(
            "READONLY_SETUP_FAILED", "READONLY", getattr(error, "sqlstate", None)
        ) from None
    role = require_app_role(db)
    result = {q.query_id: execute_query(db, q, context) for q in QUERIES}
    return {
        "schema_revision": context.revision,
        "role": role,
        "queries": result,
        "scope": context.scope(),
        "business_validated": False,
    }


def rows(snapshot: dict[str, Any], query_id: str) -> list[dict[str, Any]]:
    query = snapshot["queries"][query_id]
    if query["status"] != "PASSED" or not isinstance(query["rows"], list):
        raise CaptureFailure("REQUIRED_QUERY_NOT_PASSED", query_id)
    return query["rows"]


def validate_business(snapshot: dict[str, Any], context: CaptureContext, *, closed: bool) -> None:
    tasks, plans, approvals, executions, items = (
        rows(snapshot, q) for q in ("TASK", "PLANS", "APPROVALS", "EXECUTIONS", "ITEMS")
    )
    if len(tasks) != 1 or tasks[0]["id"] != context.task_id or tasks[0]["state"] != "completed":
        raise CaptureFailure("TASK_BINDING_INVALID", "TASK")
    identity = rows(snapshot, "IDENTITY")
    if identity != [
        {
            "principal_id": context.principal_id,
            "enabled": True,
            "auth_version": context.auth_version,
            "identity_id": context.identity_id,
            "provider": "web",
        }
    ]:
        raise CaptureFailure("IDENTITY_BINDING_INVALID", "IDENTITY")
    if len(executions) != 1 or executions[0]["status"] != "completed":
        raise CaptureFailure("EXECUTION_BINDING_INVALID", "EXECUTIONS")
    execution = executions[0]
    if (
        len(items) != context.expected_item_count
        or len({x["sku_key"] for x in items}) != context.expected_item_count
        or sum(Decimal(x["quantity"]) for x in items) != Decimal(context.expected_quantity_total)
        or set(execution["item_ids"]) != {x["id"] for x in items}
        or any(
            x["task_id"] != context.task_id or x["execution_id"] != execution["id"] for x in items
        )
    ):
        raise CaptureFailure("ITEM_SET_INVALID", "ITEMS")
    selected = [p for p in plans if p["id"] == execution["plan_id"]]
    decisions = [a for a in approvals if a["id"] == execution["approval_id"]]
    if (
        len(selected) != 1
        or not selected[0]["canonical_hash_matches"]
        or len(decisions) != 1
        or decisions[0]["plan_id"] != selected[0]["id"]
        or decisions[0]["status"] != "approved"
        or decisions[0]["plan_hash"] != selected[0]["plan_hash"]
    ):
        raise CaptureFailure("PLAN_APPROVAL_BINDING_INVALID", "PLANS")
    target = [x for x in items if x["id"] == context.item_id]
    if len(target) != 1:
        raise CaptureFailure("TARGET_MISSING", "ITEMS")
    for item in items:
        wanted = ("closed", 2) if closed and item["id"] == context.item_id else ("open", 1)
        if (item["status"], item["version"]) != wanted:
            raise CaptureFailure("ITEM_STATE_INVALID", "ITEMS")
    if closed and (
        target[0]["resolved_by"] != context.principal_id
        or target[0]["resolved_identity_id"] != context.identity_id
        or target[0]["resolved_auth_version"] != context.auth_version
        or target[0]["resolution_request_key"] != context.request_key
    ):
        raise CaptureFailure("RESOLUTION_IDENTITY_INVALID", "ITEMS")


def validate_base_readback(
    snapshot: dict[str, Any],
    context: CaptureContext,
    *,
    version: int,
    target_key: str,
    external_id: str,
    verification_mode: str,
    native_projection_hash: str,
) -> dict[str, Any]:
    """Bind the shared entry's native DTO/transport proof to actual persisted state.

    A controlled_sdk-shaped native path can use a Fake transport. Its persisted
    enum must not be relabelled offline_fake; real transport counts are separate.
    """
    if version not in (1, 2) or verification_mode not in ("offline_fake", "controlled_sdk"):
        raise CaptureFailure("BASE_CONTEXT_INVALID", "PROJECTIONS")
    candidates = [
        r
        for r in rows(snapshot, "PROJECTIONS")
        if r["item_id"] == context.item_id
        and r["target_key"] == target_key
        and r["version"] == version
    ]
    anchors = [r for r in rows(snapshot, "ANCHOR") if r["target_key"] == target_key]
    if (
        len(candidates) != 1
        or len(anchors) != 1
        or candidates[0]["status"] != "verified"
        or candidates[0]["complete_unique_verified"] is not True
        or candidates[0]["observed_version"] != version
        or candidates[0]["verification_mode"] != verification_mode
        or candidates[0]["external_id"] != external_id
        or anchors[0]["external_id"] != external_id
        or candidates[0]["projection_hash"] != native_projection_hash
    ):
        raise CaptureFailure("BASE_READBACK_BINDING_INVALID", "PROJECTIONS")
    if version == 1 and anchors[0]["original_outbox_id"] != candidates[0]["outbox_id"]:
        raise CaptureFailure("BASE_ANCHOR_INVALID", "ANCHOR")
    return candidates[0]


def immutable_business(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {q: rows(snapshot, q) for q in ("TASK", "PLANS", "APPROVALS", "EXECUTIONS", "JOBS")}


def checkpoint_fingerprint(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {q.query_id: rows(snapshot, q.query_id) for q in QUERIES if q.query_id.startswith("CP_")}


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def verify_t6_outbox(
    before: dict[str, Any],
    after: dict[str, Any],
    context: CaptureContext,
    native_payload_hash: str,
) -> dict[str, Any]:
    old, new = rows(before, "OUTBOX"), rows(after, "OUTBOX")
    prior = {r["id"]: r for r in old}
    added = [r for r in new if r["id"] not in prior]
    if (
        len(added) != 1
        or len(new) != len(old) + 1
        or any(r != prior[r["id"]] for r in new if r["id"] in prior)
    ):
        raise CaptureFailure("OUTBOX_DELTA_INVALID", "OUTBOX")
    value = added[0]
    payload = {
        "schema_version": "p3-web-v1",
        "item_id": context.item_id,
        "version": 2,
        "state": "closed",
    }
    expected = {
        "organization_id": context.organization_id,
        "shop_id": context.shop_id,
        "task_id": context.task_id,
        "destination": "bitable",
        "aggregate_id": context.item_id,
        "aggregate_version": 2,
        "operation": "item_projection",
        "dedupe_key": f"item:{context.item_id}:2",
        "request_hash": native_payload_hash,
        "payload": payload,
        "status": "pending",
        "attempts": 0,
    }
    if any(value.get(k) != v for k, v in expected.items()):
        raise CaptureFailure("OUTBOX_BINDING_INVALID", "OUTBOX")
    try:
        if UUID(value["provider_idempotency_key"]).version != 4:
            raise ValueError
    except (ValueError, KeyError, TypeError, AttributeError):
        raise CaptureFailure("OUTBOX_TOKEN_INVALID", "OUTBOX") from None
    return value


def verify_t6_association(
    snapshot: dict[str, Any],
    context: CaptureContext,
    receipt: dict[str, Any],
    reason: str,
    native_semantic_hash: str,
) -> None:
    """The shared entry validates native ResolveInput/receipt and supplies its native hash."""
    validate_business(snapshot, context, closed=True)
    request_rows, audit = rows(snapshot, "REQUEST"), rows(snapshot, "ITEM_AUDIT")
    item = next(x for x in rows(snapshot, "ITEMS") if x["id"] == context.item_id)
    resolution = receipt.get("resolution", {})
    if (
        not re.fullmatch(r"[a-f0-9]{64}", native_semantic_hash)
        or reason != reason.strip()
        or receipt.get("request_key") != context.request_key
        or receipt.get("duplicate") is not False
        or receipt.get("item", {}).get("item_id") != context.item_id
        or receipt.get("item", {}).get("state") != "closed"
        or receipt.get("item", {}).get("version") != 2
    ):
        raise CaptureFailure("RECEIPT_BINDING_INVALID", "REQUEST")
    shared = {
        "request_key": context.request_key,
        "action": "close",
        "reason": reason,
        "resolved_by": context.principal_id,
        "before_version": 1,
        "after_version": 2,
        "resolution_payload_hash": native_semantic_hash,
        "resolution_id": item["resolution_id"],
    }
    if any(resolution.get(k) != v for k, v in shared.items()):
        raise CaptureFailure("RECEIPT_RESOLUTION_INVALID", "REQUEST")
    stored_resolution = (
        request_rows[0]["result"].get("resolution") if len(request_rows) == 1 else None
    )
    resolution_fields_equal = isinstance(stored_resolution, dict) and (
        {k: v for k, v in stored_resolution.items() if k != "resolved_at"}
        == {k: v for k, v in resolution.items() if k != "resolved_at"}
    )
    if (
        item["resolution_reason"] != reason
        or item["resolution_payload_hash"] != native_semantic_hash
        or len(request_rows) != 1
        or request_rows[0]["request_hash"] != native_semantic_hash
        or request_rows[0]["task_id"] != context.task_id
        or not resolution_fields_equal
    ):
        raise CaptureFailure("PERSISTED_RECEIPT_INVALID", "REQUEST")
    if not isinstance(stored_resolution, dict):
        raise CaptureFailure("PERSISTED_RECEIPT_INVALID", "REQUEST")
    try:
        receipt_time = datetime.fromisoformat(resolution["resolved_at"].replace("Z", "+00:00"))
        item_time = datetime.fromisoformat(item["resolved_at"].replace("Z", "+00:00"))
        stored_time = datetime.fromisoformat(
            stored_resolution["resolved_at"].replace("Z", "+00:00")
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        raise CaptureFailure("RESOLUTION_TIME_INVALID", "REQUEST") from None
    if receipt_time.utcoffset() is None or receipt_time != item_time or stored_time != item_time:
        raise CaptureFailure("RESOLUTION_TIME_INVALID", "REQUEST")
    if (
        len(audit) != 1
        or audit[0]["actor_id"] != context.principal_id
        or audit[0]["source"] != "replenishment"
        or audit[0]["action"] != "item_closed"
        or audit[0]["task_id"] != context.task_id
        or audit[0]["entity_id"] != context.item_id
    ):
        raise CaptureFailure("RESOLUTION_AUDIT_INVALID", "ITEM_AUDIT")


def capture_worker(db: Any, organization_id: str, owner: str) -> dict[str, Any]:
    """Cleanup-only query: independent of every task, DTO, CP and business projection."""
    try:
        org, worker = UUID(organization_id), str(UUID(owner))
    except (ValueError, TypeError, AttributeError):
        raise CaptureFailure("WORKER_SCOPE_INVALID", "WORKER_LIFECYCLE") from None
    try:
        db.execute("SET TRANSACTION READ ONLY")
        db.execute("SET LOCAL statement_timeout='3000ms'")
        require_app_role(db)
        cur = db.execute(
            "SELECT action,entity_id,after_state,reason,occurred_at FROM "
            "business.audit_events WHERE organization_id=%s AND source='worker' "
            "AND entity_type='worker_runtime' AND entity_id=%s ORDER BY occurred_at,id",
            (org, worker),
        )
        if tuple((c.name, c.type_code) for c in cur.description) != fields(
            action=TEXT_OID,
            entity_id=TEXT_OID,
            after_state=JSON_OID,
            reason=TEXT_OID,
            occurred_at=TIME_OID,
        ):
            raise CaptureFailure("RETURN_FIELDS_INVALID", "WORKER_LIFECYCLE")
        result = normalized(cur.fetchall())
    except CaptureFailure:
        raise
    except Exception as error:
        raise CaptureFailure(
            "WORKER_QUERY_FAILED", "WORKER_LIFECYCLE", getattr(error, "sqlstate", None)
        ) from None
    return {"owner": worker, "organization_id": str(org), "events": result}


def validate_worker(value: dict[str, Any], receipt: dict[str, Any], *, stopped: bool) -> None:
    expected = ["started", "stopped", "termination_confirmed"] if stopped else ["started"]
    events = value["events"]
    if (
        value["owner"] != receipt.get("owner")
        or value["organization_id"] != receipt.get("organization")
        or [r["action"] for r in events] != expected
    ):
        raise CaptureFailure("WORKER_LIFECYCLE_INVALID", "WORKER_LIFECYCLE")
    identity = {k: receipt[k] for k in ("pid", "host", "pid_namespace")}
    if events[0]["after_state"] != identity or (stopped and events[1]["after_state"] != identity):
        raise CaptureFailure("WORKER_PROCESS_BINDING_INVALID", "WORKER_LIFECYCLE")
