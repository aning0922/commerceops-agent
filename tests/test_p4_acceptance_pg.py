"""新自有PG：双schema实际role/query与同outer/原Factory/真实once及cold replay。"""

import asyncio
import os
import time
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

from scripts.p4_acceptance import QUERIES, Deadline, schema_contract
from tests.p4_acceptance_support import (
    AcceptanceFixture,
    completed_origin,
    recheck_manifest,
    recovery_manifest,
    sender_manifest,
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
    sender_gateway = reader_gateway = current_gateway = None
    sender_process = reader_process = current_process = None
    try:
        origin_gateway, origin_window, origin_owner, delivery = completed_origin(a)
        # 原SDK自然过期和原退避；绝不缩短TTL/改账本或next_attempt_at。
        remaining = (origin_window.expires_at - datetime.now(UTC)).total_seconds()
        assert remaining < 61
        if remaining > 0:
            time.sleep(remaining + 0.02)
        a.wait_due(delivery["outbox_id"])
        sender_gateway, sender_process = a.gateway()
        sender = sender_manifest(
            a, origin_gateway, sender_gateway, origin_window, origin_owner, delivery
        )
        a.external_behavior("ack_drop")
        _, sent = a.worker(sender)
        assert sent["exit_code"] == 1
        assert sent["stages"]["CALL"]["state"] == "PASSED"
        a.stop_gateway(sender_gateway, sender_process)
        sender_process = None
        a.wait_due(delivery["outbox_id"])
        reader_gateway, reader_process = a.gateway()
        reader = recovery_manifest(a, sender, sent["pg_proof"]["worker_owner"], reader_gateway)
        a.external_behavior("missing_required")
        _, read = a.worker(reader)
        assert read["exit_code"] == 1
        a.stop_gateway(reader_gateway, reader_process)
        reader_process = None
        a.wait_due(delivery["outbox_id"])
        current_gateway, current_process = a.gateway()
        current = recheck_manifest(a, reader, read["pg_proof"]["worker_owner"], current_gateway)
        a.external_behavior("normal")
        _, verified = a.worker(current)
        assert verified["exit_code"] == 0, verified["stages"]
        result = verified["witnesses"][0]["result"]
        assert result["outcome"] == "verified"
        with connect(app) as db:
            before = QUERIES["SDK_COUNTS"].execute(
                db, (current.window_id,), revision="0016", role="app"
            )
            links = QUERIES["LINKS"].execute(
                db, (delivery["item_id"],), revision="0016", role="app"
            )
            rows = QUERIES["ITEMS"].execute(
                db, (next(iter(current.task_ids)),), revision="0016", role="app"
            )
        assert len(links) == 1 and len(rows) == 1 and all(r["status"] == "open" for r in rows)
        assert sum(r["n"] for r in before if r["method"] == "bitable.v1.app_table_record.list") == 1
        assert verified["counts"]["real_network_egress"] == 0
        # 同entry/hash、同window/key的新Python进程；没有新arm或新业务POST。
        _, replay = a.worker(current)
        assert replay["exit_code"] == 1
        assert replay["stages"]["AUTHORIZE"]["state"] == "FAILED"
        assert replay["stages"]["PREFLIGHT"]["state"] == "NOT_RUN"
        with connect(app) as db:
            after = QUERIES["SDK_COUNTS"].execute(
                db, (current.window_id,), revision="0016", role="app"
            )
            once = db.execute(
                "SELECT action,count(*) AS n FROM business.audit_events "
                "WHERE action IN ('explicit_ro_recheck_authorized',"
                "'explicit_ro_recheck_dispatched') "
                "AND entity_id=%s GROUP BY action ORDER BY action",
                (str(delivery["outbox_id"]),),
            ).fetchall()
        assert before == after
        assert len(once) == 2 and all(r["n"] == 1 for r in once)
    finally:
        for window, process in (
            (current_gateway, current_process),
            (reader_gateway, reader_process),
            (sender_gateway, sender_process),
        ):
            if window is not None and process is not None:
                a.stop_gateway(window, process)
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
