"""Fixed read-only facts in a new V41 pg-test container; no arbitrary SQL/action."""

import argparse
import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from commerceops.infrastructure.database import DatabaseSettings, connect
from psycopg import sql

TABLES = (
    "v41_product_tags",
    "v41_order_fulfillments",
    "v41_import_jobs",
    "v41_import_products",
    "v41_action_receipts",
    "v41_action_events",
)


def row(value: dict[str, Any] | None) -> dict[str, Any]:
    if value is None:
        raise ValueError("OBSERVER_ROW_MISSING")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("schema", "tenant"))
    parser.add_argument("--tenant")
    parser.add_argument("--shop")
    parser.add_argument("--deadline", required=True)
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args()
    try:
        end = datetime.fromisoformat(args.deadline)
        if end.utcoffset() != UTC.utcoffset(end) or (end - datetime.now(UTC)).total_seconds() <= (
            0 if args.final else 180
        ):
            raise ValueError("OBSERVER_WINDOW_EXPIRED")
        settings = DatabaseSettings()
        if not re.fullmatch(r"v4_demo_v41_[a-z0-9_]{1,40}", settings.name):
            raise ValueError("NEW_V41_DATABASE_REQUIRED")
        with connect(settings) as db:
            db.execute("BEGIN READ ONLY")
            db.execute("SET LOCAL statement_timeout='5s'")
            db.execute("SET LOCAL lock_timeout='1s'")
            revision = row(
                db.execute("SELECT version_num FROM business.alembic_version").fetchone()
            )["version_num"]
            if revision != "0025_v41_catalog_operations":
                raise ValueError("V41_SCHEMA_REVISION_MISMATCH")
            rows = db.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='business' AND table_name LIKE 'v41_%'"
            ).fetchall()
            if {r["table_name"] for r in rows} != set(TABLES):
                raise ValueError("V41_TABLE_SET_MISMATCH")
            value: dict[str, object] = {"revision": revision, "tables": sorted(TABLES)}
            if args.action == "tenant":
                tenant = str(UUID(args.tenant))
                shop = str(UUID(args.shop))
                # Identifiers are the fixed contract set, tenant always parameterized.
                value["counts"] = {
                    t: row(
                        db.execute(
                            sql.SQL(
                                "SELECT count(*) AS count FROM {} WHERE tenant_id=%s AND shop_id=%s"
                            ).format(sql.Identifier("business", t)),
                            (tenant, shop),
                        ).fetchone()
                    )["count"]
                    for t in TABLES
                }
            value["db_utc"] = row(db.execute("SELECT clock_timestamp() AS utc").fetchone())[
                "utc"
            ].isoformat()
            db.rollback()
        print(json.dumps(value))
    except Exception as error:
        print(json.dumps({"status": "FAILED", "error_type": type(error).__name__}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
