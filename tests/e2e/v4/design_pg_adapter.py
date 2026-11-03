"""Read-only SQL prepared from reviewed design c4c4840, not runtime-validated SQL.

No connect/DSN discovery, launch configuration or schema mutation. The final
backend commit must be checked against these identifiers before Root runs probes.
Only explicit synthetic business fields are selected; no bearer/CSRF/credentials.
"""

from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from .adapter import CapacityFacts, OperationFacts, Snapshot
from .pg_probe import read_snapshot
from .supervisor import Budget

SNAPSHOT_SQL = """
WITH target AS (SELECT id, organization_id, fixture_version, fixture_digest,
                      reset_epoch, expires_at, revoked_at
               FROM business.v4_demo_tenants WHERE id = %s),
view AS (
 SELECT t.id AS tenant_id, t.reset_epoch AS epoch, s.auth_generation AS generation,
        jsonb_build_object(
          'organization_id', t.organization_id, 'fixture_version', t.fixture_version,
          'fixture_digest', t.fixture_digest, 'epoch', t.reset_epoch,
          'expires_at', t.expires_at, 'revoked_at', t.revoked_at,
          'persona', s.persona_id, 'principal', s.principal_id,
          'generation', s.auth_generation, 'session_revoked_at', s.revoked_at,
          'shops', (SELECT jsonb_agg(jsonb_build_array(template_key, shop_id)
                                    ORDER BY template_key)
                    FROM business.v4_demo_shops WHERE tenant_id=t.id),
          'overlays', (SELECT COALESCE(jsonb_agg(jsonb_build_array(shop_id, reset_epoch,
                         object_kind, object_key, version, payload_digest)
                         ORDER BY shop_id, reset_epoch, object_kind, object_key), '[]'::jsonb)
                       FROM business.v4_demo_overlays WHERE tenant_id=t.id),
          'receipts', (SELECT COALESCE(jsonb_agg(jsonb_build_array(id, operation,
                         request_key, payload_digest, reset_epoch, auth_generation)
                         ORDER BY id), '[]'::jsonb)
                       FROM business.v4_demo_receipts WHERE tenant_id=t.id),
          'events', (SELECT COALESCE(jsonb_agg(jsonb_build_array(id, receipt_id, event_kind,
                         reset_epoch, auth_generation) ORDER BY id), '[]'::jsonb)
                     FROM business.v4_demo_events WHERE tenant_id=t.id)
        ) AS content
 FROM target t JOIN business.v4_demo_sessions s ON s.tenant_id=t.id
)
SELECT tenant_id, epoch, generation,
       encode(sha256(convert_to(content::text, 'UTF8')), 'hex') AS digest,
       (SELECT count(*) FROM business.v4_demo_receipts WHERE tenant_id=view.tenant_id) AS receipts,
       (SELECT count(*) FROM business.v4_demo_receipts
        WHERE tenant_id=view.tenant_id) AS tombstones,
       clock_timestamp() AS db_utc
FROM view
"""

CAPACITY_SQL = """
WITH moment AS MATERIALIZED (SELECT clock_timestamp() AS now),
active AS (
 SELECT t.id, s.id AS session_id
 FROM business.v4_demo_tenants t JOIN business.v4_demo_sessions s ON s.tenant_id=t.id
 CROSS JOIN moment
 WHERE t.revoked_at IS NULL AND s.revoked_at IS NULL
   AND t.expires_at > moment.now AND s.expires_at > moment.now
)
SELECT (SELECT count(DISTINCT id) FROM active) AS active_tenants,
       (SELECT count(DISTINCT session_id) FROM active) AS active_sessions,
       (SELECT count(*) FROM business.v4_demo_receipts
        WHERE operation='session_create') AS creation_receipts
"""

OPERATION_SQL = """
WITH original AS (
 SELECT id, tenant_id FROM business.v4_demo_receipts
 WHERE operation=%s AND request_key=%s
)
SELECT (SELECT count(*) FROM original) AS receipts,
       (SELECT count(*) FROM business.v4_demo_events e
        JOIN original r ON e.receipt_id=r.id AND e.tenant_id=r.tenant_id) AS events,
       (SELECT COALESCE(array_agg(e.event_kind ORDER BY e.event_kind, e.id), ARRAY[]::text[])
        FROM business.v4_demo_events e
        JOIN original r ON e.receipt_id=r.id AND e.tenant_id=r.tenant_id) AS event_kinds,
       (SELECT min(id::text) FROM original) AS receipt_id,
       (SELECT min(tenant_id::text) FROM original) AS tenant_id,
       (SELECT min(t.reset_epoch) FROM business.v4_demo_tenants t
        JOIN original r ON t.id=r.tenant_id) AS epoch
"""


class DesignPgFacts:
    """Used by the single future V4Adapter; connection is supplied explicitly."""

    def __init__(self, connection: psycopg.Connection[Any], budget: Budget) -> None:
        self.connection, self.budget = connection, budget

    def snapshot(self, tenant_id: str, *, final_collection: bool = False) -> Snapshot:
        # In this design retained control receipts are the deduplication tombstones;
        # there is no separate tombstone table. The digest excludes observation time.
        return read_snapshot(
            self.connection, SNAPSHOT_SQL, tenant_id, self.budget, final_collection=final_collection
        )

    def _row(self, sql: str, parameters: tuple[str, ...]) -> dict[str, Any]:
        milliseconds = int(self.budget.timeout(5) * 1000)
        if milliseconds < 1 or self.connection.info.transaction_status != (
            psycopg.pq.TransactionStatus.IDLE
        ):
            raise ValueError("bounded fresh read-only transaction required")
        with self.connection.transaction():
            with self.connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute("SET LOCAL TIME ZONE 'UTC'")
                cursor.execute(
                    "SELECT set_config('statement_timeout', %s, true)", (str(milliseconds),)
                )
                cursor.execute("SELECT set_config('lock_timeout', %s, true)", (str(milliseconds),))
                cursor.execute(sql, parameters, prepare=True)
                row = cursor.fetchone()
                if row is None or cursor.fetchone() is not None:
                    raise AssertionError("one complete PG fact row required")
        return dict(row)

    def capacity_facts(self) -> CapacityFacts:
        row = self._row(CAPACITY_SQL, ())
        if set(row) != {"active_tenants", "active_sessions", "creation_receipts"} or any(
            type(value) is not int or value < 0 for value in row.values()
        ):
            raise AssertionError("invalid capacity facts")
        return CapacityFacts(**row)

    def operation_facts(self, operation: str, key: str) -> OperationFacts:
        if operation not in {"session_create", "reset", "persona", "logout"}:
            raise ValueError("control operation required")
        UUID(key)
        row = self._row(OPERATION_SQL, (operation, key))
        if set(row) != {"receipts", "events", "event_kinds", "receipt_id", "tenant_id", "epoch"}:
            raise AssertionError("invalid operation facts")
        if any(type(row[name]) is not int or row[name] < 0 for name in ("receipts", "events")):
            raise AssertionError("invalid operation counts")
        kinds = row["event_kinds"]
        if not isinstance(kinds, list) or any(not isinstance(kind, str) for kind in kinds):
            raise AssertionError("complete event kind sequence required")
        if len(kinds) != row["events"]:
            raise AssertionError("event sequence/count mismatch")
        row["event_kinds"] = tuple(kinds)
        if row["epoch"] is not None and (type(row["epoch"]) is not int or row["epoch"] < 0):
            raise AssertionError("invalid observed epoch")
        for name in ("receipt_id", "tenant_id"):
            if row[name] is not None:
                UUID(row[name])
        return OperationFacts(**row)
