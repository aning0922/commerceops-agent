"""Actual read-only per-subject/key facts for the exact 772ecc6 seven-table layout.

Called only after writers stop. Missing/unknown observations remain explicit; no action is replayed.
"""

import hashlib
import json
from typing import Any
from uuid import UUID

from commerceops.application.v4_demo.seed_contract import FixtureContent, generate_seed
from commerceops.domain.commerce_values import facts_hash
from psycopg import sql

from .subjects import OPERATIONS

IDENTITY = (
    "tenant_id",
    "organization_id",
    "shop_id",
    "owner_session_id",
    "principal_id",
    "reset_epoch",
    "auth_generation",
)
EFFECTS = {
    "product_tags": ("v41_product_tags", "product_id"),
    "order_fulfillment": ("v41_order_fulfillments", "order_id"),
    "import_confirm": ("v41_import_products", "product_id"),
}


def decode_subjects(raw: bytes) -> dict[str, Any]:
    if len(raw) > 512_000:
        raise ValueError("SUBJECTS_BOUND_EXCEEDED")
    value = json.loads(raw)
    if set(value) != {"schema", "scopes"} or value["schema"] != "v41-subjects-1":
        raise ValueError("SUBJECTS_SCHEMA_MISMATCH")
    scopes = value["scopes"]
    if not isinstance(scopes, dict) or not 1 <= len(scopes) <= 20:
        raise ValueError("SUBJECTS_SCOPES_REQUIRED")
    for identity, entry in scopes.items():
        if set(entry) != {"scope", "operations"}:
            raise ValueError("SUBJECT_ENTRY_MISMATCH")
        scope = entry["scope"]
        expected = {
            "tenant_id",
            "organization_id",
            "principal_id",
            "shop_id",
            "reset_epoch",
            "auth_generation",
        }
        if set(scope) != expected:
            raise ValueError("SUBJECT_SCOPE_MISMATCH")
        for field in expected - {"reset_epoch", "auth_generation"}:
            if str(UUID(scope[field])) != scope[field]:
                raise ValueError("SUBJECT_UUID_MISMATCH")
        for field in ("reset_epoch", "auth_generation"):
            if type(scope[field]) is not int or scope[field] < 0:
                raise ValueError("SUBJECT_COUNTER_MISMATCH")
        if hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest() != identity:
            raise ValueError("SUBJECT_IDENTITY_MISMATCH")
        operations = entry["operations"]
        if not isinstance(operations, dict) or len(operations) > 100:
            raise ValueError("SUBJECT_OPERATIONS_BOUND")
        for name, attempt in operations.items():
            if set(attempt) != {"operation", "request_key", "state", "observations"}:
                raise ValueError("SUBJECT_OPERATION_MISMATCH")
            operation, key = attempt["operation"], str(UUID(attempt["request_key"]))
            if operation not in OPERATIONS or name != operation + ":" + key:
                raise ValueError("SUBJECT_ORIGINAL_OPERATION_KEY_REQUIRED")
            history = attempt["observations"]
            states = {
                "ATTEMPT_STARTED",
                "ACK_OK",
                "ACK_COMMITTED",
                "ACK_REJECTED",
                "ACK_UNKNOWN",
                "COMMITTED_READBACK",
                "UNKNOWN_READBACK",
                "SQL_ROLLBACK_VERIFIED",
            }
            if (
                not isinstance(history, list)
                or not 1 <= len(history) <= 100
                or any(x not in states for x in history)
            ):
                raise ValueError("SUBJECT_OBSERVATIONS_INVALID")
            if attempt["state"] != history[-1]:
                raise ValueError("SUBJECT_LATEST_OBSERVATION_MISMATCH")
    return dict(value)


def effect_digest(effects: list[dict[str, Any]], operation: str, object_field: str) -> str:
    summary = [
        {
            "kind": operation,
            "object_id": str(e[object_field]),
            "payload_digest": e["payload_digest"],
        }
        for e in sorted(effects, key=lambda item: str(item[object_field]))
    ]
    raw = json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def verify_receipt(db: Any, receipt: dict[str, Any], template_key: str) -> dict[str, Any]:
    operation = receipt["operation"]
    body = json.loads(receipt["canonical_request"])["body"]
    if (
        hashlib.sha256(receipt["canonical_request"].encode()).hexdigest()
        != receipt["payload_digest"]
        or body["request_key"] != str(receipt["request_id"])
        or body["shop_id"] != str(receipt["shop_id"])
        or body["expected_epoch"] != receipt["reset_epoch"]
        or body["expected_generation"] != receipt["auth_generation"]
        or body["expected_data_revision"] != receipt["before_revision"]
        or receipt["before_revision"] == receipt["after_revision"]
    ):
        raise ValueError("FINAL_ORIGINAL_RECEIPT_REQUEST_BINDING_MISMATCH")
    table, object_field = EFFECTS[operation]
    events = db.execute(
        "SELECT * FROM business.v41_action_events WHERE receipt_id=%s ORDER BY id", (receipt["id"],)
    ).fetchall()
    if len(events) != 1:
        raise ValueError("FINAL_RECEIPT_EVENT_NOT_ONCE")
    event = events[0]
    if (
        any(
            event[n] != receipt[n]
            for n in (*IDENTITY, "resource_id", "resource_version", "effect_count")
        )
        or event["event_kind"] != operation
    ):
        raise ValueError("FINAL_EVENT_RECEIPT_BINDING_MISMATCH")
    effects = db.execute(
        sql.SQL("SELECT * FROM {} WHERE receipt_id=%s ORDER BY {}").format(
            sql.Identifier("business", table), sql.Identifier(object_field)
        ),
        (receipt["id"],),
    ).fetchall()
    state = "CURRENT_EFFECT"
    if operation == "product_tags" and not effects:
        # Tag updates replace the previous row, while all original receipts/events remain.
        latest = db.execute(
            "SELECT version,receipt_id FROM business.v41_product_tags WHERE tenant_id=%s "
            "AND shop_id=%s AND reset_epoch=%s AND product_id=%s",
            (
                receipt["tenant_id"],
                receipt["shop_id"],
                receipt["reset_epoch"],
                receipt["resource_id"],
            ),
        ).fetchone()
        if not latest or latest["version"] <= receipt["resource_version"]:
            raise ValueError("FINAL_TAG_HISTORICAL_EFFECT_UNEXPLAINED")
        body = json.loads(receipt["canonical_request"])["body"]
        payload = dict(
            scope={
                n: str(receipt[n]) if n != "reset_epoch" else receipt[n]
                for n in ("tenant_id", "shop_id", "reset_epoch")
            },
            product_id=str(receipt["resource_id"]),
            version=receipt["resource_version"],
            tags=body["tags"],
        )
        payload["scope"]["template_key"] = template_key
        payload_digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        historical = [{"product_id": receipt["resource_id"], "payload_digest": payload_digest}]
        if (
            receipt["effect_count"] != 1
            or effect_digest(historical, operation, object_field) != event["effect_digest"]
        ):
            raise ValueError("FINAL_HISTORICAL_TAG_EVENT_DIGEST_MISMATCH")
        state = "REPLACED_BY_LATER_TAG_VERSION"
    else:
        if (
            len(effects) != receipt["effect_count"]
            or effect_digest(effects, operation, object_field) != event["effect_digest"]
        ):
            raise ValueError("FINAL_RECEIPT_EFFECT_NOT_ONCE")
        for effect in effects:
            if operation == "import_confirm":
                job = db.execute(
                    "SELECT chain_version,data_revision FROM business.v41_import_jobs WHERE id=%s",
                    (effect["job_id"],),
                ).fetchone()
                if (
                    effect["job_id"] != receipt["resource_id"]
                    or job is None
                    or job["chain_version"] != receipt["resource_version"]
                    or job["data_revision"] != receipt["before_revision"]
                ):
                    raise ValueError("FINAL_IMPORT_JOB_RECEIPT_VERSION_MISMATCH")
            elif (
                effect[object_field] != receipt["resource_id"]
                or effect["version"] != receipt["resource_version"]
            ):
                raise ValueError("FINAL_RESOURCE_RECEIPT_VERSION_MISMATCH")
            if any(effect[n] != receipt[n] for n in IDENTITY):
                raise ValueError("FINAL_EFFECT_IDENTITY_MISMATCH")
            if (
                hashlib.sha256(effect["canonical_payload"].encode()).hexdigest()
                != effect["payload_digest"]
            ):
                raise ValueError("FINAL_EFFECT_BYTES_MISMATCH")
    return {"receipt": receipt, "event": event, "effects": effects, "effect_state": state}


def preview_state(attempt: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    if len(rows) > 1:
        raise ValueError("FINAL_PREVIEW_KEY_NOT_UNIQUE")
    if "SQL_ROLLBACK_VERIFIED" in attempt["observations"] and rows:
        raise ValueError("FINAL_ROLLED_BACK_PREVIEW_PERSISTED")
    if "COMMITTED_READBACK" in attempt["observations"] and (not rows or not rows[0]["published"]):
        raise ValueError("FINAL_PUBLISHED_PREVIEW_READBACK_MISSING")
    return "PUBLISHED" if rows and rows[0]["published"] else "UNKNOWN"


def collect(db: Any, subjects: dict[str, Any]) -> dict[str, Any]:
    results = []
    for entry in subjects["scopes"].values():
        scope = entry["scope"]
        session = db.execute(
            "SELECT s.id,m.template_key FROM business.v4_demo_sessions s "
            "JOIN business.v4_demo_tenants t ON t.id=s.tenant_id "
            "JOIN business.v4_demo_shops m ON m.tenant_id=t.id "
            "WHERE t.id=%s AND t.organization_id=%s AND m.shop_id=%s",
            (scope["tenant_id"], scope["organization_id"], scope["shop_id"]),
        ).fetchall()
        if len(session) != 1:
            raise ValueError("FINAL_OWNED_SUBJECT_SESSION_MISSING_OR_AMBIGUOUS")
        bound = {**scope, "owner_session_id": session[0]["id"]}
        where = sql.SQL(" AND ").join(sql.SQL("{}=%s").format(sql.Identifier(n)) for n in IDENTITY)
        params = tuple(bound[n] for n in IDENTITY)
        actions = []
        for attempt in entry["operations"].values():
            if attempt["operation"] == "preview":
                rows = db.execute(
                    sql.SQL(
                        "SELECT id,preview_key,chain_version,parent_job_id,parse_state,parse_slot,"
                        "data_revision,parser_version,import_schema_version,job_digest,normalized_digest,"
                        "parse_pid,process_ref,stop_proof,preview_data IS NOT NULL AS published,"
                        "created_at,expires_at FROM business.v41_import_jobs "
                        "WHERE {} AND preview_key=%s"
                    ).format(where),
                    (*params, attempt["request_key"]),
                ).fetchall()
                state = preview_state(attempt, rows)
                actions.append(
                    {
                        "attempt": attempt,
                        "jobs": rows,
                        "db_state": state,
                    }
                )
            else:
                rows = db.execute(
                    sql.SQL(
                        "SELECT * FROM business.v41_action_receipts WHERE {} "
                        "AND operation=%s AND request_id=%s"
                    ).format(where),
                    (*params, attempt["operation"], attempt["request_key"]),
                ).fetchall()
                if len(rows) > 1:
                    raise ValueError("FINAL_ACTION_KEY_NOT_UNIQUE")
                if "SQL_ROLLBACK_VERIFIED" in attempt["observations"] and rows:
                    raise ValueError("FINAL_ROLLED_BACK_ACTION_PERSISTED")
                if "COMMITTED_READBACK" in attempt["observations"] and not rows:
                    raise ValueError("FINAL_COMMITTED_READBACK_RECEIPT_MISSING")
                actions.append(
                    {
                        "attempt": attempt,
                        "db_state": "COMMITTED" if rows else "UNKNOWN",
                        "facts": verify_receipt(db, rows[0], session[0]["template_key"])
                        if rows
                        else None,
                    }
                )
        source = db.execute(
            "SELECT t.fixture_digest,f.content,m.template_key FROM business.v4_demo_tenants t "
            "JOIN business.v4_demo_shops m ON m.tenant_id=t.id "
            "JOIN business.v4_demo_fixture_versions f ON f.version=t.fixture_version "
            "AND f.content_hash=t.fixture_digest WHERE t.id=%s AND m.shop_id=%s",
            (scope["tenant_id"], scope["shop_id"]),
        ).fetchone()
        if source is None:
            raise ValueError("FINAL_FIXTURE_SOURCE_MISSING")
        fixture = FixtureContent.model_validate_json(json.dumps(source["content"]))
        if (
            facts_hash(fixture.model_dump(mode="json")) != source["fixture_digest"]
            or source["fixture_digest"] != generate_seed().manifest.content_digest
        ):
            raise ValueError("FINAL_FIXTURE_STOCK_MONEY_SOURCE_CHANGED")
        shop = next(s for s in fixture.shops if s.shop_key == source["template_key"])
        financial = shop.model_dump(
            mode="json", include={"skus", "inventory", "orders", "order_lines", "refunds"}
        )
        results.append(
            {
                "scope": bound,
                "operations": actions,
                "fixture_digest": source["fixture_digest"],
                "synthetic_stock_money": financial,
            }
        )
    return {"schema": "v41-final-subject-facts-1", "subjects": results}
