"""Explicit owner-only V41 runtime grants and exact retained-tenant cleanup hooks."""

from uuid import UUID

from psycopg import sql

from commerceops.infrastructure.v4_demo_sessions import DB, DemoConfig, bounded
from commerceops.infrastructure.v41_security import _owner, assert_policy

TABLES = (
    "product_tags",
    "order_fulfillments",
    "import_products",
    "action_events",
    "action_receipts",
    "import_jobs",
)
RUNTIME = (
    "v41_read_guard(text,text,uuid,bigint,bigint)",
    "v41_apply_action(text,text,text,text,text,uuid)",
    "v41_reserve_preview(text,text,text,text,text,uuid)",
    "v41_bind_parser(uuid,text,uuid,integer)",
    "v41_stop_parser(uuid,text,uuid,jsonb)",
    "v41_publish_preview(text,text,text,uuid,text,text,text)",
)


def _tables_owned(db: DB) -> None:
    _owner(db)
    for suffix in TABLES:
        row = db.execute(
            "SELECT current_user=pg_get_userbyid(relowner) AS allowed FROM pg_class "
            "WHERE oid=to_regclass(%s)",
            ("business.v41_" + suffix,),
        ).fetchone()
        if not row or not row["allowed"]:
            raise ValueError("V41_OWNER_REQUIRED")


def grant_runtime(db: DB, config: DemoConfig) -> None:
    """Explicit operator step after exact SQL review; never called by migration/API/import."""
    _tables_owned(db)
    bounded(db)
    assert_policy(db, config)
    for suffix in (*TABLES, "security_policy"):
        table = sql.Identifier("business", "v41_" + suffix)
        db.execute(sql.SQL("REVOKE ALL ON {} FROM PUBLIC,commerceops_app").format(table))
        db.execute(sql.SQL("GRANT SELECT ON {} TO commerceops_app").format(table))
    for signature in RUNTIME:
        # Every signature above is a checked-in constant, never an input or broad schema grant.
        db.execute(
            sql.SQL("GRANT EXECUTE ON FUNCTION business.{} TO commerceops_app").format(
                sql.SQL(signature)
            )
        )


def gc_effects(db: DB, tenant_id: UUID) -> None:
    """Caller already holds the retained owned tenant/session locks; never clears policy."""
    _tables_owned(db)
    row = db.execute(
        """SELECT t.retain_until,clock_timestamp() AS db_now,o.name
        FROM business.v4_demo_tenants t JOIN business.organizations o ON o.id=t.organization_id
        WHERE t.id=%s FOR UPDATE OF t""",
        (tenant_id,),
    ).fetchone()
    if (
        not row
        or row["name"] != "V4 synthetic demo " + str(tenant_id)
        or row["db_now"] < row["retain_until"]
    ):
        raise ValueError("V41_GC_NOT_READY")
    if db.execute(
        "SELECT 1 FROM business.v41_import_jobs WHERE tenant_id=%s "
        "AND parse_state<>'STOPPED' LIMIT 1",
        (tenant_id,),
    ).fetchone():
        raise ValueError("V41_PROCESS_HOLD")
    for suffix in TABLES:
        db.execute(
            sql.SQL("DELETE FROM {} WHERE tenant_id=%s").format(
                sql.Identifier("business", "v41_" + suffix)
            ),
            (tenant_id,),
        )
