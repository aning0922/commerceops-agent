"""New-owned PG checks of M2 read/empty-target guards, not the actual Woo restore gate."""

from pathlib import Path

import psycopg
import pytest
from commerceops.infrastructure.database import DatabaseSettings, connect

from scripts.m2_backup import (
    BackupFailure,
    empty_target,
    no_other_clients,
    quiescent_snapshot,
    same_snapshot,
)
from scripts.m2_state import seed
from tests.test_p4_acceptance_pg import database as database
from tests.test_p4_acceptance_pg import initialize_schema

pytestmark = pytest.mark.integration


def test_exact_0018_snapshot_reads_every_table_and_preserves_read_only(
    database: tuple[DatabaseSettings, DatabaseSettings],
    tmp_path: Path,
) -> None:
    owner, _ = database
    initialize_schema(owner, "0018")
    seed(owner, tmp_path, "owned-m2-snapshot")
    with connect(owner) as db:
        before = quiescent_snapshot(db)
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            db.execute("UPDATE business.organizations SET name='forbidden-test-write'")
    with connect(owner) as db:
        after = quiescent_snapshot(db)
    same_snapshot(before, after)
    assert len(before["tables"]) == 60
    assert before["tables"]["business.business_tasks"]["count"] == 0
    assert before["tables"]["business.web_credentials"]["count"] == 2
    assert before["runtime_role"]["rolsuper"] is False


def test_snapshot_detects_change_and_seed_cannot_replace_existing_org(
    database: tuple[DatabaseSettings, DatabaseSettings],
    tmp_path: Path,
) -> None:
    owner, _ = database
    initialize_schema(owner, "0018")
    seed(owner, tmp_path, "owned-m2-change")
    with connect(owner) as db:
        before = quiescent_snapshot(db)
    with pytest.raises(BackupFailure, match="M2_SEED_NOT_EMPTY"):
        seed(owner, tmp_path, "owned-m2-change")
    with connect(owner) as db:
        db.execute("UPDATE business.organizations SET name='owned-mutated-label'")
    with connect(owner) as db:
        after = quiescent_snapshot(db)
    with pytest.raises(BackupFailure, match="M2_RESTORE_SNAPSHOT_MISMATCH"):
        same_snapshot(before, after)


def test_empty_target_rejects_existing_schema_or_public_function(
    database: tuple[DatabaseSettings, DatabaseSettings],
) -> None:
    owner, _ = database
    with connect(owner) as db:
        empty_target(db)
        db.execute(
            "CREATE FUNCTION public.owned_m2_probe() RETURNS integer LANGUAGE sql AS 'SELECT 1'"
        )
    with connect(owner) as db:
        with pytest.raises(BackupFailure, match="M2_RESTORE_TARGET_NOT_EMPTY"):
            empty_target(db)
    initialize_schema(owner, "0018")
    with connect(owner) as db:
        with pytest.raises(BackupFailure, match="M2_RESTORE_TARGET_NOT_EMPTY"):
            empty_target(db)


def test_source_active_client_is_not_treated_as_stopped(
    database: tuple[DatabaseSettings, DatabaseSettings],
) -> None:
    owner, app = database
    initialize_schema(owner, "0018")
    with connect(app), connect(owner) as db:
        with pytest.raises(BackupFailure, match="M2_DATABASE_CLIENTS_REMAIN"):
            no_other_clients(db)
    with connect(owner) as db:
        no_other_clients(db)
