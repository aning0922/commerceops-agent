"""Real PG read-only final facts; exact owned connection/query come from adapter."""

import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from .adapter import Snapshot
from .supervisor import Budget


def read_snapshot(
    connection: psycopg.Connection[Any],
    sql: str,
    tenant_id: str,
    budget: Budget,
    *,
    final_collection: bool = False,
) -> Snapshot:
    """SQL must be the independently reviewed single SELECT for the frozen schema.

    One tenant parameter, exact columns, real DB UTC. No guessed tables/DSN or
    automatic connect/reconnect; the adapter attests this is the new owned PG.
    final_collection occurs after all writers stop and before owned PG shutdown.
    """
    UUID(tenant_id)
    milliseconds = int(budget.timeout(5, cleanup=final_collection) * 1000)
    if milliseconds < 1 or connection.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
        raise ValueError("bounded fresh read-only transaction required")
    with connection.transaction():
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("SET LOCAL TIME ZONE 'UTC'")
            cursor.execute("SELECT set_config('statement_timeout', %s, true)", (str(milliseconds),))
            cursor.execute("SELECT set_config('lock_timeout', %s, true)", (str(milliseconds),))
            cursor.execute(sql, (tenant_id,), prepare=True)
            row = cursor.fetchone()
            if row is None or cursor.fetchone() is not None:
                raise AssertionError("one complete tenant snapshot required")
    fields = {"tenant_id", "epoch", "generation", "digest", "receipts", "tombstones", "db_utc"}
    if set(row) != fields or str(row["tenant_id"]) != tenant_id:
        raise AssertionError("wrong tenant snapshot shape")
    if any(
        type(row[key]) is not int or row[key] < 0
        for key in ("epoch", "generation", "receipts", "tombstones")
    ):
        raise AssertionError("snapshot counters must be nonnegative integers")
    if not isinstance(row["db_utc"], datetime) or row["db_utc"].utcoffset() != UTC.utcoffset(
        row["db_utc"]
    ):
        raise AssertionError("actual aware DB UTC required")
    if not isinstance(row["digest"], str) or not re.fullmatch(r"[a-f0-9]{64}", row["digest"]):
        raise AssertionError("actual SHA256 tenant digest required")
    return Snapshot(
        tenant_id,
        row["epoch"],
        row["generation"],
        str(row["digest"]),
        row["receipts"],
        row["tombstones"],
        row["db_utc"].isoformat(),
    )
