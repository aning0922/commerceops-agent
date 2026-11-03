"""Explicit owner-only fixture bootstrap and additive V4 runtime grants."""

from typing import Any
from uuid import UUID

import psycopg
from psycopg import sql

from commerceops.application.v4_demo.seed_contract import SeedBundle, generate_seed

DB = psycopg.Connection[dict[str, Any]]
TABLES = (
    "fixture_versions",
    "tenants",
    "shops",
    "personas",
    "bootstraps",
    "sessions",
    "receipts",
    "events",
    "overlays",
    "rate_attempts",
)
PROVISION = "v4_demo_provision(uuid,uuid,text,text,text,uuid,uuid,text,uuid,text,text,text,text)"


def require_owner(db: DB) -> None:
    revision = db.execute("SELECT version_num FROM business.alembic_version").fetchone()
    if revision != {"version_num": "0024_v4_demo_foundation"}:
        raise ValueError("V4_SCHEMA_REVISION")
    environment = db.execute("""SELECT current_setting('server_version') AS version,
    (SELECT extversion FROM pg_extension WHERE extname='vector') AS vector""").fetchone()
    if (
        not environment
        or not environment["version"].startswith("17.11")
        or environment["vector"] != "0.8.7"
    ):
        raise ValueError("V4_DATABASE_ENVIRONMENT")
    for table in (
        *("v4_demo_" + suffix for suffix in TABLES),
        "organizations",
        "web_credentials",
        "web_sessions",
    ):
        row = db.execute(
            "SELECT current_user=pg_get_userbyid(relowner) AS allowed FROM pg_class "
            "WHERE oid=to_regclass(%s)",
            ("business." + table,),
        ).fetchone()
        if row is None or not row["allowed"]:
            raise ValueError("V4_OWNER_REQUIRED")


def initialize_fixture(db: DB) -> SeedBundle:
    require_owner(db)
    bundle = generate_seed()
    db.execute("SELECT pg_advisory_xact_lock(1446261842,1)")
    old = db.execute(
        "SELECT canonical_content,content_hash FROM "
        "business.v4_demo_fixture_versions WHERE version=%s",
        (bundle.content.fixture_version,),
    ).fetchone()
    text = bundle.canonical_content().decode()
    if old is not None:
        if old != dict(canonical_content=text, content_hash=bundle.manifest.content_digest):
            raise ValueError("V4_FIXTURE_CONFLICT")
        return bundle
    db.execute(
        """INSERT INTO business.v4_demo_fixture_versions
    (version,generator_version,canonical_content,content,content_hash,snapshot_at)
    VALUES(%s,%s,%s,%s::jsonb,%s,%s)""",
        (
            bundle.content.fixture_version,
            bundle.content.generator_version,
            text,
            text,
            bundle.manifest.content_digest,
            bundle.content.snapshot_at,
        ),
    )
    return bundle


def grant_v4_runtime(db: DB) -> None:
    require_owner(db)
    for suffix in TABLES:
        target = sql.Identifier("business", "v4_demo_" + suffix)
        db.execute(sql.SQL("REVOKE ALL ON {} FROM commerceops_app").format(target))
        db.execute(sql.SQL("GRANT SELECT ON {} TO commerceops_app").format(target))
    for suffix in ("bootstraps", "receipts", "events", "rate_attempts"):
        db.execute(
            sql.SQL("GRANT INSERT ON {} TO commerceops_app").format(
                sql.Identifier("business", "v4_demo_" + suffix)
            )
        )
    db.execute(
        "GRANT UPDATE(create_request_key,consumed_at) ON "
        "business.v4_demo_bootstraps TO commerceops_app"
    )
    db.execute(
        "GRANT UPDATE(reset_epoch,revoked_at) ON business.v4_demo_tenants TO commerceops_app"
    )
    db.execute("""GRANT UPDATE(persona_id,principal_id,identity_id,bound_web_session_id,
    auth_version,auth_generation,reset_epoch,csrf_nonce,csrf_digest,revoked_at,last_receipt_id)
    ON business.v4_demo_sessions TO commerceops_app""")
    db.execute("GRANT DELETE ON business.v4_demo_overlays TO commerceops_app")
    db.execute("""GRANT EXECUTE ON FUNCTION business.v4_demo_request_valid(
    jsonb,text,uuid,bigint,bigint,text,text) TO commerceops_app""")
    db.execute(
        sql.SQL("GRANT EXECUTE ON FUNCTION business.{} TO commerceops_app").format(
            sql.SQL(PROVISION)
        )
    )


def gc_tenant(db: DB, tenant_id: UUID) -> None:
    require_owner(db)
    t = db.execute(
        """SELECT t.*,o.name AS organization_name,clock_timestamp() AS db_now
    FROM business.v4_demo_tenants t JOIN business.organizations o ON o.id=t.organization_id
    WHERE t.id=%s FOR UPDATE OF t""",
        (tenant_id,),
    ).fetchone()
    if (
        t is None
        or t["organization_name"] != "V4 synthetic demo " + str(tenant_id)
        or t["db_now"] < t["retain_until"]
    ):
        raise ValueError("V4_GC_NOT_READY")
    s = db.execute(
        "SELECT * FROM business.v4_demo_sessions WHERE tenant_id=%s FOR UPDATE", (tenant_id,)
    ).fetchone()
    if s is None:
        raise ValueError("V4_GC_BINDING")
    if db.execute(
        "SELECT 1 FROM business.business_tasks WHERE organization_id=%s LIMIT 1",
        (t["organization_id"],),
    ).fetchone():
        raise ValueError("V4_GC_BUSINESS_DEPENDENCY")
    principals = db.execute(
        "SELECT principal_id FROM business.v4_demo_personas WHERE tenant_id=%s "
        "ORDER BY principal_id",
        (tenant_id,),
    ).fetchall()
    for principal in principals:
        db.execute(
            "SELECT id FROM business.principals WHERE id=%s FOR UPDATE",
            (principal["principal_id"],),
        )
    db.execute(
        "UPDATE business.web_sessions SET "
        "revoked_at=coalesce(revoked_at,clock_timestamp()) WHERE "
        "organization_id=%s",
        (t["organization_id"],),
    )
    db.execute(
        "UPDATE business.web_credentials SET enabled=false WHERE organization_id=%s AND enabled",
        (t["organization_id"],),
    )
    db.execute(
        "UPDATE business.principals SET "
        "enabled=false,auth_version=auth_version+1 WHERE organization_id=%s AND "
        "enabled",
        (t["organization_id"],),
    )
    for suffix in ("overlays", "events", "receipts", "sessions", "personas", "shops"):
        db.execute(
            sql.SQL("DELETE FROM {} WHERE tenant_id=%s").format(
                sql.Identifier("business", "v4_demo_" + suffix)
            ),
            (tenant_id,),
        )
    db.execute("DELETE FROM business.v4_demo_bootstraps WHERE id=%s", (s["bootstrap_id"],))
    db.execute("DELETE FROM business.v4_demo_tenants WHERE id=%s", (tenant_id,))
