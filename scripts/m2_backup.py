"""M2 same-version backup primitives, called only by the owned scenario's bounded child.

No resource creation, scheduler, migration, checkpoint repair or business write.
The parent owns subprocess deadlines and validates the source/target container identities.
"""

import hashlib
import json
from typing import Any

from psycopg import Connection, sql

REVISION = "0018_p5_commerce_sources"
BUSINESS = frozenset(
    """organizations shops principals identities conversations inbox_events business_tasks jobs
    audit_events alembic_version principal_shop_scopes commerce_snapshots snapshot_products
    snapshot_order_lines snapshot_refunds analysis_reports explanation_links model_stage_budgets
    model_calls model_call_observations model_explanations explanation_task_results
    inventory_intent_requests inventory_intent_results principal_role_shop_grants web_credentials
    web_sessions web_login_attempts web_requests p3_task_sources replenishment_plans approvals
    outbox approval_resumes p3_observations p3_revalidation_transitions p3_revalidation_failures
    executions replenishment_items outbox_reconciliations p3_template_results p4_inbox_receipts
    p4_card_bindings p4_clarification_replies p4_base_deliveries p4_base_links p4_sender_state
    p4_sdk_windows p4_sdk_calls p4_im_deliveries p4_read_replies p4_clarification_requests
    p4_history_recoveries p4_history_messages p4_read_message_sources
    p5_commerce_source_bindings""".split()
)
CHECKPOINTS = frozenset(
    {"checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations"}
)
TABLES = frozenset(
    [("business", name) for name in BUSINESS] + [("checkpoints", name) for name in CHECKPOINTS]
)
MAX_ROWS = 10000
MAX_BYTES = 32 * 1024 * 1024


class BackupFailure(ValueError):
    """Fixed safe code only. Caller must never serialize a database exception."""


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def no_other_clients(db: Connection[dict[str, Any]]) -> None:
    row = db.execute(
        "SELECT count(*) AS n FROM pg_stat_activity WHERE datname=current_database() "
        "AND backend_type='client backend' AND pid<>pg_backend_pid()"
    ).fetchone()
    if row != {"n": 0}:
        raise BackupFailure("M2_DATABASE_CLIENTS_REMAIN")


def empty_target(db: Connection[dict[str, Any]]) -> None:
    """Call before restoring, without running migrate/seed/setup-checkpointer."""
    no_other_clients(db)
    row = db.execute(
        "SELECT count(*) AS n FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' "
        "AND nspname NOT IN ('information_schema','public')"
    ).fetchone()
    objects = db.execute(
        "SELECT (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public') + "
        "(SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "WHERE n.nspname='public') + "
        "(SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace "
        "WHERE n.nspname='public') AS n"
    ).fetchone()
    if row != {"n": 0} or objects != {"n": 0}:
        raise BackupFailure("M2_RESTORE_TARGET_NOT_EMPTY")


def quiescent_snapshot(db: Connection[dict[str, Any]]) -> dict[str, Any]:
    """Hash all 60 tables, schema/ACL and checkpoint bytes in a read-only snapshot.

    No row contents, account hashes, nonce, session or checkpoint payload leave this function.
    Run in a separately owned child so a stalled transport cannot outlive the parent's deadline.
    """
    db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    db.execute("SET LOCAL statement_timeout=5000")
    no_other_clients(db)
    version = db.execute("SHOW server_version_num").fetchone()
    if version != {"server_version_num": "170011"}:
        raise BackupFailure("M2_DATABASE_VERSION")
    revision = db.execute("SELECT version_num FROM business.alembic_version").fetchall()
    if revision != [{"version_num": REVISION}]:
        raise BackupFailure("M2_SCHEMA_REVISION")
    tables = db.execute(
        "SELECT table_schema AS s,table_name AS t FROM information_schema.tables "
        "WHERE table_schema NOT LIKE 'pg_%' AND table_schema<>'information_schema' "
        "ORDER BY table_schema,table_name"
    ).fetchall()
    if {(row["s"], row["t"]) for row in tables} != TABLES or len(tables) != 60:
        raise BackupFailure("M2_SCHEMA_TABLES")
    role = db.execute(
        "SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,rolcanlogin "
        "FROM pg_roles WHERE rolname='commerceops_app'"
    ).fetchone()
    if role != dict(
        rolname="commerceops_app",
        rolsuper=False,
        rolcreatedb=False,
        rolcreaterole=False,
        rolreplication=False,
        rolbypassrls=False,
        rolcanlogin=True,
    ):
        raise BackupFailure("M2_RUNTIME_ROLE")
    schema: dict[str, Any] = {}
    queries = {
        "columns": "SELECT table_schema,table_name,column_name,ordinal_position,data_type,"
        "udt_name,is_nullable,column_default,is_identity,is_generated,generation_expression "
        "FROM information_schema.columns "
        "WHERE table_schema IN ('business','checkpoints') ORDER BY 1,2,4",
        "constraints": "SELECT n.nspname,c.relname,k.conname,"
        "pg_get_constraintdef(k.oid) AS definition "
        "FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname IN ('business','checkpoints') ORDER BY 1,2,3",
        "indexes": "SELECT schemaname,tablename,indexname,indexdef FROM pg_indexes "
        "WHERE schemaname IN ('business','checkpoints') ORDER BY 1,2,3",
        "functions": "SELECT n.nspname,p.proname,pg_get_function_identity_arguments(p.oid) AS args,"
        "pg_get_functiondef(p.oid) AS definition,p.proacl::text AS acl,"
        "p.proowner::regrole::text AS owner "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "WHERE n.nspname IN ('business','checkpoints') ORDER BY 1,2,3",
        "relations": "SELECT n.nspname,c.relname,c.relkind,c.relacl::text AS acl,"
        "c.relowner::regrole::text AS owner,c.relrowsecurity,c.relforcerowsecurity "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname IN ('business','checkpoints') ORDER BY 1,2",
        "triggers": "SELECT n.nspname,c.relname,t.tgname,t.tgenabled,"
        "pg_get_triggerdef(t.oid) AS definition FROM pg_trigger t "
        "JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname IN ('business','checkpoints') AND NOT t.tgisinternal ORDER BY 1,2,3",
        "namespaces": "SELECT nspname,nspacl::text AS acl FROM pg_namespace "
        "WHERE nspname IN ('business','checkpoints','public') ORDER BY 1",
    }
    for catalog_name, catalog_query in queries.items():
        schema[catalog_name] = db.execute(catalog_query).fetchall()
    rows: dict[str, dict[str, Any]] = {}
    total_bytes = 0
    for namespace, name in sorted(TABLES):
        query = sql.SQL(
            "SELECT CASE WHEN octet_length(to_jsonb(t)::text)<=%s THEN to_jsonb(t)::text "
            "ELSE NULL END AS body FROM {}.{} t ORDER BY to_jsonb(t)::text LIMIT %s"
        ).format(sql.Identifier(namespace), sql.Identifier(name))
        cursor = db.execute(query, (MAX_BYTES, MAX_ROWS + 1))
        hasher = hashlib.sha256()
        count = 0
        for row in cursor:
            count += 1
            if count > MAX_ROWS or not isinstance(row["body"], str):
                raise BackupFailure("M2_BACKUP_CAPACITY")
            raw = row["body"].encode()
            total_bytes += len(raw)
            if total_bytes > MAX_BYTES:
                raise BackupFailure("M2_BACKUP_CAPACITY")
            hasher.update(len(raw).to_bytes(8, "big"))
            hasher.update(raw)
        rows[namespace + "." + name] = {"count": count, "sha256": hasher.hexdigest()}
    checkpoint_revision = db.execute(
        "SELECT max(v) AS version FROM checkpoints.checkpoint_migrations"
    ).fetchone()
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    if checkpoint_revision != {"version": len(AsyncPostgresSaver.MIGRATIONS) - 1}:
        raise BackupFailure("M2_CHECKPOINT_VERSION")
    no_other_clients(db)
    return {
        "schema_version": "p5-m2-backup-snapshot-v1",
        "revision": REVISION,
        "server_version_num": "170011",
        "checkpoint_revision": checkpoint_revision,
        "schema_sha256": digest(schema),
        "runtime_role": role,
        "tables": rows,
    }


def same_snapshot(before: dict[str, Any], after: dict[str, Any]) -> None:
    if before != after:
        raise BackupFailure("M2_RESTORE_SNAPSHOT_MISMATCH")
