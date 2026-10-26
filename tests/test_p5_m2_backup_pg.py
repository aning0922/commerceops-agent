"""New-owned PG checks of M2 read/empty-target guards, not the actual Woo restore gate."""

import asyncio
from copy import deepcopy
from pathlib import Path
from uuid import UUID, uuid4

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
from scripts.m2_state import (
    pending_checkpoint,
    seed,
    stopped_business_facts,
    validate_waiting_checkpoint,
)
from tests.p3_support import P3Fixture, P3Process
from tests.test_p3_approval_pg import checkpoint_state, payload
from tests.test_p3_pg import fixture as fixture
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


def test_official_stopped_pending_checkpoint_binding_and_initial_wrong_thread_plan_rejected(
    fixture: P3Fixture,
) -> None:
    f = fixture
    task_id = UUID(f.create(f.new_cycle())["task_id"])
    child = P3Process(f, "worker", {"task_id": str(task_id)}, "never")
    try:
        child.until("after_ready")
        original = payload(f, task_id)
    finally:
        if child.process.poll() is None:
            child.stop_clean()
    with connect(f.inventory.owner) as db:
        task = db.execute(
            "SELECT * FROM business.business_tasks WHERE id=%s", (task_id,)
        ).fetchone()
        approval = db.execute(
            "SELECT * FROM business.approvals WHERE id=%s", (UUID(original["approval_id"]),)
        ).fetchone()
    assert task and approval
    observed = {
        **original,
        "organization_id": str(task["organization_id"]),
        "shop_id": str(task["shop_id"]),
        "task_id": str(task_id),
        "expires_at": approval["expires_at"].isoformat(),
    }
    with connect(f.inventory.owner) as db:
        before = quiescent_snapshot(db)
    receipt = asyncio.run(pending_checkpoint(f.config, observed))
    with connect(f.inventory.app) as db:
        facts = stopped_business_facts(db, observed)
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            db.execute("UPDATE business.business_tasks SET state=state")
    assert facts["tasks"] == [{"state": "awaiting_approval", "original_scope": True}]
    assert facts["resumes"] == [] and facts["executions"] == [] and facts["items"] == []
    assert facts["decision_receipts"] == {"count": 0}
    assert receipt["official_wait_approval"] is True
    state = asyncio.run(checkpoint_state(f, task_id))
    assert validate_waiting_checkpoint(state, task, approval, observed) == receipt
    initial = state._replace(
        next=("prepare_approval",),
        interrupts=(),
        values={k: state.values[k] for k in ("workflow_version", "task_id", "request_hash")},
    )
    config = deepcopy(state.config)
    config["configurable"]["thread_id"] = str(uuid4())
    changed_plan = state._replace(values={**state.values, "plan_id": str(uuid4())})
    for invalid in (
        initial,
        state._replace(config=config),
        changed_plan,
        state._replace(interrupts=()),
    ):
        with pytest.raises(BackupFailure, match="M2_PENDING_CHECKPOINT_SEMANTICS"):
            validate_waiting_checkpoint(invalid, task, approval, observed)
    with pytest.raises(BackupFailure, match="M2_PENDING_CHECKPOINT_BUSINESS_BINDING"):
        asyncio.run(pending_checkpoint(f.config, {**observed, "task_id": str(uuid4())}))
    with pytest.raises(BackupFailure, match="M2_PENDING_CHECKPOINT_BUSINESS_BINDING"):
        validate_waiting_checkpoint(
            state, task, approval, {**observed, "expires_at": "2000-01-01T00:00:00+00:00"}
        )
    with connect(f.inventory.owner) as db:
        after = quiescent_snapshot(db)
    same_snapshot(before, after)
