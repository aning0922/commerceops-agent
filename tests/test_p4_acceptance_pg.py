"""新自有PG：双schema实际role/query与同outer/原Factory/真实once及cold replay。"""

import asyncio
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from commerceops.entrypoints.database import grant_runtime, migrate, setup_checkpointer
from commerceops.infrastructure.database import DatabaseSettings, connect, migration_engine
from psycopg import sql

from scripts.p4_acceptance import Deadline, schema_contract
from tests.p4_acceptance_support import (
    AcceptanceFixture,
    prepare_batch_ro,
    prepare_single_ro,
)

pytestmark = pytest.mark.integration


def initialize_schema(owner: DatabaseSettings, revision: str) -> None:
    if revision == "0016":
        migrate(owner)
    else:
        config = Config()
        config.set_main_option("script_location", "backend/migrations")
        engine = migration_engine(owner)
        try:
            with engine.begin() as db:
                config.attributes["connection"] = db
                command.upgrade(config, "0015")
        finally:
            engine.dispose()
    asyncio.run(setup_checkpointer(owner))
    grant_runtime(owner, **({"legacy_revision": "0015"} if revision == "0015" else {}))  # type: ignore[arg-type]


@pytest.fixture
def database() -> Iterator[tuple[DatabaseSettings, DatabaseSettings]]:
    settings = DatabaseSettings()
    assert settings.runtime_password_file is not None
    name = "p4_acceptance_" + uuid4().hex
    owner = settings.model_copy(update={"name": name})
    app = owner.model_copy(
        update={
            "user": "commerceops_app",
            "password_file": settings.runtime_password_file,
            "runtime_password_file": None,
        }
    )
    with psycopg.connect(**settings.kwargs(), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            yield owner, app
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.mark.parametrize("revision", ["0015", "0016"])
def test_exact_schema_app_queries_and_expected_metadata_denial(
    database: tuple[DatabaseSettings, DatabaseSettings],
    revision: str,
) -> None:
    owner, app = database
    initialize_schema(owner, revision)
    result = schema_contract(owner, app, revision)
    assert result["exact_table_count"] == (55 if revision == "0015" else 56)
    assert result["alembic_read_denied_sqlstate"] == "42501"
    if revision == "0016":
        with pytest.raises(ValueError, match="revision mismatch"):
            grant_runtime(owner, legacy_revision="0015")


def test_same_outer_native_full_RO_once_and_fresh_process_original_key_replay(
    database: tuple[DatabaseSettings, DatabaseSettings],
    tmp_path: Path,
) -> None:
    owner, app = database
    initialize_schema(owner, "0016")
    schema_contract(owner, app, "0016")
    expiry = datetime.now(UTC) + timedelta(minutes=12)
    registered = os.environ.get("COMMERCEOPS_ACCEPTANCE_DEADLINE")
    if registered:
        expiry = min(expiry, datetime.fromisoformat(registered))
    lease = Deadline.register(expiry)
    a = AcceptanceFixture.prepare(owner, app, tmp_path, lease, case_kind="recover_single_item")
    try:
        result = prepare_single_ro(a)
        assert result["verified"]["exit_code"] == 0
        assert result["verified"]["counts"]["real_network_egress"] == 0
        assert result["replay"]["exit_code"] == 1
    finally:
        assert a.cleanup()


def test_twenty_items_ordinary_ro_is_separate_from_explicit_single_recovery(
    database: tuple[DatabaseSettings, DatabaseSettings], tmp_path: Path
) -> None:
    owner, app = database
    initialize_schema(owner, "0016")
    expiry = datetime.now(UTC) + timedelta(minutes=8)
    registered = os.environ.get("COMMERCEOPS_ACCEPTANCE_DEADLINE")
    if registered:
        expiry = min(expiry, datetime.fromisoformat(registered))
    a = AcceptanceFixture.prepare(
        owner, app, tmp_path, Deadline.register(expiry), case_kind="batch_twenty_items"
    )
    try:
        result = prepare_batch_ro(a)
        assert len(result["items"]) == 20
        assert sum(int(r["quantity"]) for r in result["items"]) == 2000
        assert result["explicit_recheck"] is False
        assert result["window"].recovery.explicit_ro_recheck is None
        assert result["window"].recovery.sender_gateway is None
    finally:
        assert a.cleanup()


def test_gateway_session_lock_held_until_actual_child_reap(
    database: tuple[DatabaseSettings, DatabaseSettings],
    tmp_path: Path,
) -> None:
    owner, app = database
    initialize_schema(owner, "0016")
    a = AcceptanceFixture.prepare(
        owner,
        app,
        tmp_path,
        Deadline.register(datetime.now(UTC) + timedelta(minutes=5)),
        case_kind="recover_single_item",
    )
    window = child = None
    try:
        window, child = a.gateway()
        with connect(app) as db:
            row = db.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS acquired",
                ("p4-gateway:" + a.business.app_id,),
            ).fetchone()
            assert row == {"acquired": False}
        a.stop_gateway(window, child)
        with connect(app) as db:
            assert db.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS acquired",
                ("p4-gateway:" + a.business.app_id,),
            ).fetchone() == {"acquired": True}
            assert db.execute(
                "SELECT pg_advisory_unlock(hashtextextended(%s,0)) AS released",
                ("p4-gateway:" + a.business.app_id,),
            ).fetchone() == {"released": True}
    finally:
        if window is not None and child is not None and not child.confirmed:
            a.stop_gateway(window, child)
        assert a.cleanup()
