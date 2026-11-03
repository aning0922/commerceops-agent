"""One bounded read-only observer in the new project's pg-test container."""

import argparse
import json
import re
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from .design_pg_adapter import DesignPgFacts
from .migration_diagnostic import FALLBACK, suppress_raw_output
from .supervisor import Budget


def main() -> None:
    code = 1
    encoded = FALLBACK
    try:
        with suppress_raw_output():
            parser = argparse.ArgumentParser()
            parser.add_argument(
                "action",
                choices=(
                    "snapshot",
                    "capacity",
                    "operation",
                    "tenants",
                    "bootstrap",
                    "credential-revoke",
                    "grant-revoke",
                ),
            )
            parser.add_argument("--tenant")
            parser.add_argument("--principal")
            parser.add_argument("--shop")
            parser.add_argument("--operation")
            parser.add_argument("--key")
            parser.add_argument("--deadline", required=True)
            parser.add_argument("--final", action="store_true")
            args = parser.parse_args()
            from commerceops.infrastructure.database import DatabaseSettings, connect

            settings = DatabaseSettings()
            if not re.fullmatch(r"v4_demo_[a-z0-9_]{1,48}", settings.name):
                raise ValueError("new V4 database required")
            end = datetime.fromisoformat(args.deadline)
            # Final collection uses the reserved interval, and may only be called
            # by the parent after writers have stopped.
            reserve = 180 if not args.final else 0
            if end.utcoffset() != UTC.utcoffset(end):
                raise ValueError("UTC required")
            now = datetime.now(UTC)
            if (end - now).total_seconds() <= reserve:
                raise TimeoutError("window expired")
            import time

            budget = Budget(now, end, reserve, time.monotonic() + (end - now).total_seconds())
            with connect(settings) as db:
                facts = DesignPgFacts(db, budget)
                value: Any
                if args.action == "tenants":
                    value = facts._row(
                        "SELECT COALESCE(jsonb_agg(id ORDER BY id), '[]'::jsonb) "
                        "AS tenants FROM business.v4_demo_tenants",
                        (),
                    )
                elif args.action == "bootstrap":
                    UUID(args.key)
                    value = facts._row(
                        "SELECT id::text AS id,create_request_key::text AS key,"
                        "consumed_at IS NOT NULL AS consumed FROM business.v4_demo_bootstraps "
                        "WHERE create_request_key=%s",
                        (args.key,),
                    )
                elif args.action == "credential-revoke":
                    UUID(args.tenant)
                    UUID(args.principal)
                    if args.final:
                        raise ValueError("no final-stage writes")
                    with db.transaction():
                        db.execute("SELECT set_config('statement_timeout', '5000', true)")
                        db.execute("SELECT set_config('lock_timeout', '5000', true)")
                        rows = db.execute(
                            "UPDATE business.web_credentials c SET enabled=false "
                            "FROM business.v4_demo_personas p WHERE p.tenant_id=%s AND "
                            "p.principal_id=%s AND c.organization_id=p.organization_id AND "
                            "c.principal_id=p.principal_id AND c.identity_id=p.identity_id "
                            "RETURNING c.identity_id",
                            (args.tenant, args.principal),
                        ).fetchall()
                        if len(rows) != 1:
                            raise AssertionError("one owned credential required")
                    value = {"revoked": 1}
                elif args.action == "grant-revoke":
                    UUID(args.tenant)
                    UUID(args.principal)
                    UUID(args.shop)
                    if args.final:
                        raise ValueError("no final-stage writes")
                    with db.transaction():
                        db.execute("SELECT set_config('statement_timeout','5000',true)")
                        db.execute("SELECT set_config('lock_timeout','5000',true)")
                        rows = db.execute(
                            "UPDATE business.principal_role_shop_grants g "
                            "SET enabled=false FROM business.v4_demo_personas p "
                            "JOIN business.v4_demo_shops s ON s.tenant_id=p.tenant_id "
                            "WHERE p.tenant_id=%s AND p.principal_id=%s AND s.shop_id=%s "
                            "AND g.organization_id=p.organization_id AND "
                            "g.principal_id=p.principal_id AND g.shop_id=s.shop_id "
                            "AND g.role='operator' AND g.enabled RETURNING g.shop_id",
                            (args.tenant, args.principal, args.shop),
                        ).fetchall()
                        if len(rows) != 1:
                            raise AssertionError("one mapped owned grant required")
                        row = db.execute(
                            "SELECT count(*) AS count FROM "
                            "business.principal_role_shop_grants g JOIN "
                            "business.v4_demo_shops s ON s.shop_id=g.shop_id AND "
                            "s.organization_id=g.organization_id WHERE s.tenant_id=%s "
                            "AND g.principal_id=%s AND g.role='operator' AND g.enabled",
                            (args.tenant, args.principal),
                        ).fetchone()
                        if row is None or row["count"] != 1:
                            raise AssertionError("unrelated mapped grant changed")
                    value = {"revoked": 1, "remaining": 1}
                elif args.action == "snapshot":
                    value = facts.snapshot(args.tenant, final_collection=args.final)
                elif args.action == "capacity":
                    value = facts.capacity_facts()
                else:
                    value = facts.operation_facts(args.operation, args.key)
                encoded = json.dumps(value if isinstance(value, dict) else asdict(value))
            code = 0
    except BaseException:
        code, encoded = 1, FALLBACK
    print(encoded)
    raise SystemExit(code) from None


if __name__ == "__main__":
    main()
