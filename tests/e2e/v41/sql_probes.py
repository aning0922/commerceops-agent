"""Fixed real app-role attack/rollback probes, usable only in the future reviewed API container.

No deployment, owner grants, retries, arbitrary SQL or replacement HTTP responses.
"""

import argparse
import hashlib
import importlib
import json
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
from commerceops.application.v41 import contracts as dto
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.v4_demo_sessions import DemoConfig, bounded
from commerceops.infrastructure.web_config import private_bytes
from psycopg import sql
from psycopg.types.json import Jsonb

from .final_facts import IDENTITY
from .pg_observer import SCHEMA_TABLES, TABLES

ROOT = Path(__file__).resolve().parents[3]
INPUT = Path("/run/v4_api/v41-probe.private.json")


class ForcedRollback(Exception):
    """Raised only after the real apply function and deferred constraints completed."""


def admission(opened: bool) -> None:
    if not opened:
        raise ValueError("ROOT_EXACT_SQL_PROBE_WINDOW_REQUIRED")
    # Actual Root authorization and a successful standalone owner ACL verification replace
    # the old historical HOLD metadata. No READY field or incompatible checkout CLI is used.
    auth_path = Path("/run/v4_api/runtime-authorization.json")
    verified_path = Path("/run/v4_api/owner-setup-verification.json")
    if not auth_path.is_file() or not verified_path.is_file():
        raise ValueError("V41_SQL_PROBE_RUNTIME_HOLD")
    from .owner_setup import authorization

    auth = json.loads(private_bytes(auth_path))
    authorization(auth)
    verified = json.loads(private_bytes(verified_path))
    if (
        verified.get("action") != "verify-runtime"
        or verified.get("status") != "VERIFIED"
        or verified.get("image_id") != auth["test_image"]
        or any(
            verified.get(n) != auth[n]
            for n in ("source_sha", "source_tree", "database", "project", "authorization_id")
        )
        or verified["result"].get("fingerprint_matches") is not True
        or verified["result"].get("private_verifier_app_read") is not False
    ):
        raise ValueError("V41_SQL_PROBE_OWNER_VERIFICATION_REQUIRED")


def load_input() -> tuple[DemoConfig, dict[str, Any]]:
    value = json.loads(private_bytes(INPUT))
    fields = {
        "schema",
        "owner_catalog",
        "source_sha",
        "source_tree",
        "scope",
        "resource_id",
        "body",
        "preview_body",
        "bearer",
        "csrf",
        "deadline",
    }
    if set(value) != fields or value["schema"] != "v41-sql-probe-1":
        raise ValueError("FIXED_SQL_PROBE_INPUT_REQUIRED")
    end = datetime.fromisoformat(value["deadline"])
    if end.utcoffset() != UTC.utcoffset(end) or (end - datetime.now(UTC)).total_seconds() <= 180:
        raise ValueError("SQL_PROBE_WINDOW_EXPIRED")
    scope = value["scope"]
    if set(scope) != set(IDENTITY) - {"owner_session_id"}:
        raise ValueError("SQL_PROBE_SCOPE_REQUIRED")
    for name in ("tenant_id", "organization_id", "principal_id", "shop_id"):
        UUID(scope[name])
    UUID(value["resource_id"])
    for name in ("reset_epoch", "auth_generation"):
        if type(scope[name]) is not int or scope[name] < 0:
            raise ValueError("SQL_PROBE_SCOPE_REQUIRED")
    command = value["body"]
    for name, expected in (
        ("shop_id", scope["shop_id"]),
        ("expected_epoch", scope["reset_epoch"]),
        ("expected_generation", scope["auth_generation"]),
    ):
        if command[name] != expected or value["preview_body"][name] != expected:
            raise ValueError("SQL_PROBE_COMMAND_SCOPE_MISMATCH")
    UUID(command["request_key"])
    UUID(value["preview_body"]["request_key"])
    value["body"] = dto.SetProductTags.model_validate_json(json.dumps(value["body"])).model_dump(
        mode="json"
    )
    value["preview_body"] = dto.ImportPreviewInput.model_validate_json(
        json.dumps(value["preview_body"])
    ).model_dump(mode="json")
    config = DemoConfig.load(Path("/run/v4_api/demo.json"))
    if config.web.database.user != "commerceops_app" or not config.web.database.name.startswith(
        "v4_demo_v41_"
    ):
        raise ValueError("NEW_V41_APP_ROLE_REQUIRED")
    validate_owner_catalog(
        value["owner_catalog"], config.web.database.name, value["source_sha"], value["source_tree"]
    )
    return config, dict(value)


def validate_owner_catalog(catalog: dict[str, Any], database: str, source: str, tree: str) -> None:
    if (
        type(catalog.get("native_exit")) is not int
        or catalog["native_exit"] != 0
        or catalog.get("source_sha") != source
        or catalog.get("source_tree") != tree
        or re.fullmatch(r"[a-f0-9]{40}", source) is None
        or re.fullmatch(r"[a-f0-9]{40}", tree) is None
        or re.fullmatch(r"[a-f0-9]{64}", catalog.get("stdout_sha256", "")) is None
    ):
        raise ValueError("ROOT_OWNER_CATALOG_RECEIPT_REQUIRED")
    result = catalog["result"]
    if (
        result.get("execution_identity") != {"role": "commerceops_owner", "database": database}
        or result.get("revision") != "0025_v41_catalog_operations"
        or result.get("tables") != sorted(SCHEMA_TABLES)
        or type(result.get("global_policy_rows")) is not int
        or result["global_policy_rows"] != 1
    ):
        raise ValueError("ROOT_OWNER_CATALOG_SCHEMA_BINDING_MISMATCH")


def identity(db: Any, value: dict[str, Any]) -> dict[str, Any]:
    bounded(db)
    environment = db.execute("SELECT current_user AS role,current_database() AS name").fetchone()
    if environment["role"] != "commerceops_app" or not environment["name"].startswith(
        "v4_demo_v41_"
    ):
        raise ValueError("ACTUAL_APP_ROLE_REQUIRED")
    scope = value["scope"]
    rows = db.execute(
        "SELECT s.id,s.bound_web_session_id,s.principal_id,s.reset_epoch,s.auth_generation,"
        "s.token_hash FROM business.v4_demo_sessions s JOIN business.v4_demo_tenants t "
        "ON t.id=s.tenant_id WHERE t.id=%s AND t.organization_id=%s",
        (scope["tenant_id"], scope["organization_id"]),
    ).fetchall()
    if (
        len(rows) != 1
        or any(rows[0][n] != scope[n] for n in ("reset_epoch", "auth_generation"))
        or str(rows[0]["principal_id"]) != scope["principal_id"]
    ):
        raise ValueError("ACTUAL_NEW_SESSION_SCOPE_MISMATCH")
    if rows[0]["token_hash"] != hashlib.sha256(value["bearer"].encode()).hexdigest():
        raise ValueError("ACTUAL_NEW_SESSION_BEARER_MISMATCH")
    return dict(rows[0])


def snapshot(db: Any, value: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    scope = value["scope"]
    content: dict[str, Any] = {}
    for table in TABLES:
        rows = db.execute(
            sql.SQL(
                "SELECT * FROM {} WHERE tenant_id=%s AND shop_id=%s ORDER BY to_jsonb({})::text"
            ).format(sql.Identifier("business", table), sql.Identifier(table)),
            (scope["tenant_id"], scope["shop_id"]),
        ).fetchall()
        content[table] = {
            "count": len(rows),
            "sha256": hashlib.sha256(
                json.dumps(rows, sort_keys=True, default=str, ensure_ascii=False).encode()
            ).hexdigest(),
        }
    anchor = db.execute(
        "SELECT csrf_digest FROM business.web_sessions WHERE id=%s",
        (session["bound_web_session_id"],),
    ).fetchone()
    source = db.execute(
        "SELECT f.content FROM business.v4_demo_tenants t "
        "JOIN business.v4_demo_fixture_versions f ON f.version=t.fixture_version "
        "AND f.content_hash=t.fixture_digest WHERE t.id=%s",
        (scope["tenant_id"],),
    ).fetchone()
    if source is None or anchor is None:
        raise ValueError("SQL_PROBE_FIXTURE_OR_BOUND_SESSION_MISSING")
    content["fixture_money_stock_sha256"] = hashlib.sha256(
        json.dumps(source, sort_keys=True, default=str, ensure_ascii=False).encode()
    ).hexdigest()
    content["bound_anchor_sha256"] = hashlib.sha256(
        json.dumps(anchor, sort_keys=True).encode()
    ).hexdigest()
    return content


def count(db: Any, query: str, parameters: tuple[Any, ...]) -> int:
    row = db.execute(query, parameters).fetchone()
    if row is None or type(row["n"]) is not int or row["n"] < 0:
        raise ValueError("SQL_PROBE_COUNT_MISSING_OR_INVALID")
    return int(row["n"])


def forced_rollback(config: DemoConfig, value: dict[str, Any]) -> dict[str, Any]:
    # The fixture harness uses its new API private config to exercise the actual app DB role.
    security = importlib.import_module("commerceops.infrastructure.v41_security")
    with connect(config.web.database) as db:
        session = identity(db, value)
        before = snapshot(db, value, session)
        scope = value["scope"]
        if count(
            db,
            "SELECT count(*) AS n FROM business.v41_action_receipts "
            "WHERE owner_session_id=%s AND operation='product_tags' AND request_id=%s",
            (session["id"], value["body"]["request_key"]),
        ):
            raise ValueError("FRESH_ROLLBACK_KEY_REQUIRED")
        canonical = json.dumps(
            {
                "method": "POST",
                "path": "/api/v4/products/" + value["resource_id"] + "/tags",
                "body": value["body"],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        try:
            result = db.execute(
                "SELECT * FROM business.v41_apply_action(%s,%s,%s,%s,%s,%s)",
                (
                    value["bearer"],
                    value["csrf"],
                    security.binding_proof(config, session["bound_web_session_id"]),
                    canonical,
                    "product_tags",
                    value["resource_id"],
                ),
            ).fetchone()
            if result is None:
                raise ValueError("APPLY_DID_NOT_RETURN_RECEIPT")
            db.execute("SET CONSTRAINTS ALL IMMEDIATE")
            receipt_id = result["id"]
            events = count(
                db,
                "SELECT count(*) AS n FROM business.v41_action_events WHERE receipt_id=%s",
                (receipt_id,),
            )
            effects = count(
                db,
                "SELECT count(*) AS n FROM business.v41_product_tags WHERE receipt_id=%s",
                (receipt_id,),
            )
            if events != 1 or effects != 1:
                raise ValueError("APPLY_EFFECT_EVENT_STAGE_NOT_REACHED")
            raise ForcedRollback()
        except ForcedRollback:
            db.rollback()
        # A new transaction observes durable state; no COMMIT of the action was attempted.
        identity(db, value)
        after = snapshot(db, value, session)
        if after != before:
            raise ValueError("FORCED_ROLLBACK_LEFT_DURABLE_EFFECT")
        db.rollback()
    return {
        "scope": scope,
        "operation": "product_tags",
        "request_key": value["body"]["request_key"],
        "stage": "AFTER_APPLY_AND_CONSTRAINTS_BEFORE_COMMIT",
        "before": before,
        "after": after,
        "rolled_back": True,
    }


def binding_stop_attack(config: DemoConfig, value: dict[str, Any]) -> dict[str, Any]:
    findings: list[str] = []
    observations: list[dict[str, Any]] = []
    with connect(config.web.database) as db:
        session = identity(db, value)
        before = snapshot(db, value, session)
        security = importlib.import_module("commerceops.infrastructure.v41_security")
        scope = value["scope"]
        db.execute(
            "SELECT business.v41_read_guard(%s,%s,%s,%s,%s)",
            (
                value["bearer"],
                security.binding_proof(config, session["bound_web_session_id"]),
                scope["shop_id"],
                scope["reset_epoch"],
                scope["auth_generation"],
            ),
        ).fetchone()
        if count(
            db,
            "SELECT count(*) AS n FROM business.v41_import_jobs WHERE parse_state<>'STOPPED'",
            (),
        ):
            raise ValueError("EMPTY_NEW_OWNED_PARSER_CAPACITY_REQUIRED")
        chosen = secrets.token_urlsafe(32)
        forged = chosen + "." + secrets.token_urlsafe(32)
        lease, process_ref = uuid4().hex, uuid4()
        try:
            db.execute("SAVEPOINT anchor_attack")
            try:
                changed = db.execute(
                    "UPDATE business.web_sessions SET csrf_digest=%s WHERE id=%s RETURNING id",
                    (hashlib.sha256(chosen.encode()).hexdigest(), session["bound_web_session_id"]),
                ).fetchall()
                if len(changed) != 1:
                    raise ValueError("ATTACK_TARGET_NOT_PRESENT")
                # The accepted S04 design retains this legacy permission; the second MAC
                # must independently block a well-shaped forged invocation.
                observations.append({"stage": "legacy_anchor", "writable": True})
            except psycopg.Error as error:
                db.execute("ROLLBACK TO SAVEPOINT anchor_attack")
                if error.sqlstate not in {"42501", "23514"}:
                    raise ValueError("ATTACK_DENIAL_UNCLASSIFIED") from None
                observations.append(
                    {"stage": "legacy_anchor", "writable": False, "sqlstate": error.sqlstate}
                )
            db.execute("SAVEPOINT forged_reserve")
            try:
                body = value["preview_body"]
                from commerceops.application.v41.imports import decode_file

                canonical = json.dumps(
                    {
                        "command": {k: v for k, v in body.items() if k != "file_base64"},
                        "file_digest": hashlib.sha256(decode_file(body["file_base64"])).hexdigest(),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                job = db.execute(
                    "SELECT * FROM business.v41_reserve_preview(%s,%s,%s,%s,%s,%s)",
                    (
                        value["bearer"],
                        value["csrf"],
                        forged,
                        canonical,
                        hashlib.sha256(lease.encode()).hexdigest(),
                        process_ref,
                    ),
                ).fetchone()
                if job is None:
                    raise ValueError("ATTACK_RESERVE_RETURN_MISSING")
                findings.append("FORGED_BINDING_RESERVED_JOB")
                # Only reached after an unauthorized reserve: preserving the original
                # exploit chain, not expecting SQL to detect a trusted lease holder lying.
                fake = {
                    "process_ref": str(process_ref),
                    "pid": 2147480000,
                    "native_exit": 0,
                    "timed_out": False,
                    "reaped": True,
                    "output_digest": "0" * 64,
                }
                db.execute("SAVEPOINT forged_stop")
                try:
                    db.execute(
                        "SELECT business.v41_stop_parser(%s,%s,%s,%s)",
                        (job["id"], lease, process_ref, Jsonb(fake)),
                    )
                    state = db.execute(
                        "SELECT parse_state,parse_slot FROM business.v41_import_jobs WHERE id=%s",
                        (job["id"],),
                    ).fetchone()
                    findings.append("FORGED_STOP_ACCEPTED_WITHOUT_SPAWN_OR_REAP")
                    observations.append(
                        {"stage": "forged_stop", "denied": False, "db_state": state}
                    )
                except psycopg.Error as error:
                    db.execute("ROLLBACK TO SAVEPOINT forged_stop")
                    observations.append(
                        {"stage": "forged_stop", "denied": True, "sqlstate": error.sqlstate}
                    )
            except psycopg.Error as error:
                db.execute("ROLLBACK TO SAVEPOINT forged_reserve")
                if error.sqlstate != "23514" or error.diag.message_primary != "SESSION_INVALID":
                    raise ValueError("ATTACK_RESERVE_DENIAL_UNCLASSIFIED") from None
                observations.append(
                    {"stage": "forged_reserve", "denied": True, "sqlstate": error.sqlstate}
                )
        finally:
            db.rollback()  # Never persist the attack's anchor/job/slot changes, even if accepted.
        identity(db, value)
        after = snapshot(db, value, session)
        if after != before:
            raise ValueError("ATTACK_ROLLBACK_DID_NOT_RESTORE_STATE")
        db.rollback()
    return {
        "scope": value["scope"],
        "gate": "PARTIAL_S04_COMBINATION_ONLY",
        "findings": findings,
        "observations": observations,
        "before": before,
        "after": after,
        "status": "FORGED_RESERVE_REJECTED" if not findings else "FAILED_ATTACK_ACCEPTED",
        "live_child_stop": "NOT_RUN_SEPARATE_FIXTURE_REQUIRED",
        "parent_death": "NOT_RUN_SEPARATE_FIXTURE_REQUIRED",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("binding-stop-attack", "forced-action-rollback"))
    parser.add_argument("--root-opened-window", action="store_true")
    args = parser.parse_args()
    try:
        admission(args.root_opened_window)
        config, value = load_input()
        result = (
            binding_stop_attack(config, value)
            if args.action == "binding-stop-attack"
            else forced_rollback(config, value)
        )
        print(json.dumps(result, default=str))
        if result.get("findings"):
            raise SystemExit(1)
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "FAILED_OR_UNKNOWN",
                    "error_type": type(error).__name__,
                    "code": str(error)
                    if str(error)
                    in {"ROOT_EXACT_SQL_PROBE_WINDOW_REQUIRED", "V41_SQL_PROBE_RUNTIME_HOLD"}
                    else None,
                    "sqlstate": getattr(error, "sqlstate", None),
                }
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
