"""S2候选真实PG节点；须Root提供新owned服务/UTC窗口后运行，collect不连接PG。"""

import asyncio
import hashlib
import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from commerceops.application.daily.source import MockMetadata
from commerceops.application.replenishment.contracts import WebFailure
from commerceops.domain.commerce_values import canonical_bytes, utc_time
from commerceops.entrypoints.api import create_app
from commerceops.entrypoints.daily_source import register_source
from commerceops.infrastructure.daily_read import DailyReadStore
from commerceops.infrastructure.daily_sources import ActiveBinding, DailyDeployment
from commerceops.infrastructure.daily_store import DailyStore, create_daily_task
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.queue import JobQueue
from commerceops.infrastructure.worker_lock import WorkerSession, mark_attention
from commerceops.workflows.daily_report import DailyRunner
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from tests.p3_support import ORIGIN, P3Fixture
from tests.test_daily_report import DAY
from tests.test_daily_source import manifest, metadata, source_data
from tests.test_p3_pg import fixture as fixture

pytestmark = pytest.mark.integration


def prepare(
    f: P3Fixture, directory: Path, business_day: date = DAY
) -> tuple[DailyDeployment, MockMetadata]:
    directory.mkdir(mode=0o700)
    data = f.inventory.data
    meta = metadata(directory).model_copy(
        update={
            "organization_id": data.organization,
            "shop_id": data.shop,
            "earliest_business_day": business_day,
        }
    )
    gold = manifest(meta).model_copy(
        update={"earliest_business_day": business_day, "latest_business_day": business_day}
    )
    orders, refunds = source_data()
    offset = timedelta(days=(business_day - DAY).days)
    for row in [*orders, *(item for rows in refunds.values() for item in rows)]:
        for field in ("date_created_gmt", "date_paid_gmt"):
            if row.get(field) is not None:
                row[field] = (utc_time(row[field]) + offset).isoformat()
    for filename, body in (
        (meta.manifest_ref, gold.model_dump(mode="json")),
        (meta.fixture_ref, {"orders": orders, "refunds": refunds}),
    ):
        path = Path(filename)
        path.write_text(json.dumps(body))
        path.chmod(0o600)
    meta = meta.model_copy(
        update={
            "manifest_digest": hashlib.sha256(Path(meta.manifest_ref).read_bytes()).hexdigest(),
            "fixture_digest": hashlib.sha256(Path(meta.fixture_ref).read_bytes()).hexdigest(),
        }
    )
    binding = ActiveBinding(
        organization_id=data.organization,
        shop_id=data.shop,
        binding_id=uuid4(),
        config_digest=meta.config_digest,
        private_pin_digest=None,
    )
    files = DailyDeployment(
        schema_version="p6-daily-deployment-v1",
        directory=directory,
        bindings=(binding,),
        model_requests_enabled=False,
        external_sender_enabled=False,
    )
    path = directory / f"{binding.binding_id}.json"
    path.write_text(meta.model_dump_json())
    path.chmod(0o600)
    with connect(f.inventory.owner) as db:
        db.execute(
            """UPDATE business.shops SET config_ref=%s,external_shop_key=%s,
        timezone=%s,currency=%s WHERE id=%s""",
            (meta.config_ref, meta.external_shop_key, meta.timezone, meta.currency, data.shop),
        )
    register_source(f.inventory.owner, files, data.organization, data.shop)
    return files, meta


async def execute(
    f: P3Fixture, files: DailyDeployment, *, hook: Any = None
) -> tuple[UUID, dict[str, Any]]:
    task = create_daily_task(
        f.config.database, files, f.actor, f.inventory.data.shop, uuid4(), "source-1", DAY
    )
    session = WorkerSession(f.config.database, f.inventory.data.organization)
    await session.start()
    try:
        jobs = JobQueue(session)
        run = await jobs.claim()
        assert run and run.task_id == task
        store = DailyStore(f.config.database, session, files)
        runner = DailyRunner(store, **({"hook": hook} if hook else {}))
        await runner.run(run)
        result = DailyReadStore(f.config.database).read(f.actor, task)
        # 封存后拿掉当前metadata文件仍只能复用原回执，不能重新采集/读秘密。
        file = files.directory / f"{files.bindings[0].binding_id}.json"
        file.rename(file.with_suffix(".held"))
        await DailyRunner(DailyStore(f.config.database, session, files)).run(run)
        assert session.connection is not None
        await mark_attention(session.connection, session.owner)
        assert (
            DailyReadStore(f.config.database).read(f.actor, task)["daily"]["state"] == "completed"
        )
        await jobs.done(run)
        return task, result
    finally:
        await session.close(clean=True)


def test_daily_real_transactions_report_read_and_receipt_replay(
    fixture: P3Fixture, tmp_path: Path
) -> None:
    files, _ = prepare(fixture, tmp_path / "daily-owned")
    task, result = asyncio.run(execute(fixture, files))
    assert result["daily"]["state"] == "completed"
    assert result["daily"]["report"]["metrics"]["paid_order_total"] == "109.7"
    assert result["daily"]["report"]["metrics"]["refund_amount"] == "7.5"
    with connect(fixture.config.database) as db:
        assert db.execute("SELECT count(*) AS n FROM business.p6_daily_snapshots").fetchone() == {
            "n": 1
        }
        assert db.execute("SELECT count(*) AS n FROM business.p6_daily_reports").fetchone() == {
            "n": 1
        }
        assert db.execute(
            "SELECT count(*) AS n FROM business.jobs WHERE task_id=%s", (task,)
        ).fetchone() == {"n": 1}


def test_daily_commit_then_runner_exception_uses_same_receipt(
    fixture: P3Fixture, tmp_path: Path
) -> None:
    files, _ = prepare(fixture, tmp_path / "daily-owned")

    async def failure(point: str) -> None:
        if point == "report_committed":
            raise RuntimeError("controlled postcommit crash")

    _, result = asyncio.run(execute(fixture, files, hook=failure))
    assert result["daily"]["report"]["complete"] is True


def test_daily_request_key_replay_conflict_and_scope(fixture: P3Fixture, tmp_path: Path) -> None:
    files, _ = prepare(fixture, tmp_path / "daily-owned")
    key = uuid4()
    data = fixture.inventory.data
    task = create_daily_task(
        fixture.config.database, files, fixture.actor, data.shop, key, "source-1", DAY
    )
    assert (
        create_daily_task(
            fixture.config.database, files, fixture.actor, data.shop, key, "source-1", DAY
        )
        == task
    )
    with pytest.raises(WebFailure) as conflict:
        create_daily_task(
            fixture.config.database, files, fixture.actor, data.shop, key, "other", DAY
        )
    assert conflict.value.status == 409
    with pytest.raises(WebFailure):
        DailyReadStore(fixture.config.database).read(
            replace(fixture.actor, organization_id=uuid4()), task
        )
    with connect(fixture.config.database) as db:
        assert db.execute(
            "SELECT count(*) AS n FROM business.jobs WHERE task_id=%s", (task,)
        ).fetchone() == {"n": 1}


@pytest.mark.parametrize(
    "table", ["p6_daily_source_bindings", "p6_daily_snapshots", "p6_daily_reports"]
)
def test_daily_runtime_acl_and_owner_evidence_immutability(
    fixture: P3Fixture, tmp_path: Path, table: str
) -> None:
    files, _ = prepare(fixture, tmp_path / "daily-owned")
    asyncio.run(execute(fixture, files))
    from psycopg import sql

    with connect(fixture.config.database) as db:
        for privilege in ("UPDATE", "DELETE", "TRUNCATE"):
            assert db.execute(
                "SELECT has_table_privilege(current_user,%s,%s) AS ok",
                ("business." + table, privilege),
            ).fetchone() == {"ok": False}
        if table == "p6_daily_source_bindings":
            assert db.execute(
                "SELECT has_table_privilege(current_user,%s,'INSERT') AS ok", ("business." + table,)
            ).fetchone() == {"ok": False}
    with connect(fixture.inventory.owner) as db:
        for command in (
            sql.SQL("DELETE FROM business.{}").format(sql.Identifier(table)),
            sql.SQL("TRUNCATE business.{} CASCADE").format(sql.Identifier(table)),
        ):
            with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
                db.execute(command)


@pytest.mark.parametrize("field", ["request_key", "snapshot_id", "daily_source", "rules"])
def test_daily_task_json_null_is_not_admitted(
    fixture: P3Fixture, tmp_path: Path, field: str
) -> None:
    files, _ = prepare(fixture, tmp_path / "daily-owned")
    data = fixture.inventory.data
    task = create_daily_task(
        fixture.config.database, files, fixture.actor, data.shop, uuid4(), "source-1", DAY
    )
    with connect(fixture.config.database) as db:
        row = db.execute("SELECT * FROM business.business_tasks WHERE id=%s", (task,)).fetchone()
        assert row
        body = {**row["normalized_request"], "request_key": str(uuid4()), field: None}
        new = uuid4()
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(
                """INSERT INTO business.business_tasks(id,organization_id,shop_id,conversation_id,
            requester_id,kind,normalized_request,workflow_version,thread_id)
            VALUES(%s,%s,%s,%s,%s,'daily_report',%s,'p6-daily-report-v1',%s)""",
                (
                    new,
                    row["organization_id"],
                    row["shop_id"],
                    row["conversation_id"],
                    row["requester_id"],
                    Jsonb(body),
                    str(new),
                ),
            )


def test_daily_revoked_before_collection_never_writes_snapshot(
    fixture: P3Fixture, tmp_path: Path
) -> None:
    files, _ = prepare(fixture, tmp_path / "daily-owned")
    data = fixture.inventory.data
    task = create_daily_task(
        fixture.config.database, files, fixture.actor, data.shop, uuid4(), "source-1", DAY
    )
    with connect(fixture.inventory.owner) as db:
        db.execute(
            "UPDATE business.principal_role_shop_grants SET enabled=false "
            "WHERE principal_id=%s AND role='operator'",
            (data.principal,),
        )

    async def run() -> None:
        session = WorkerSession(fixture.config.database, data.organization)
        await session.start()
        try:
            job = await JobQueue(session).claim()
            assert job and job.task_id == task
            await DailyRunner(DailyStore(fixture.config.database, session, files)).run(job)
        finally:
            await session.close(clean=True)

    asyncio.run(run())
    with connect(fixture.config.database) as db:
        assert db.execute(
            "SELECT failure_code FROM business.business_tasks WHERE id=%s", (task,)
        ).fetchone() == {"failure_code": "DAILY_PERMISSION_INVALID"}
        assert db.execute("SELECT count(*) AS n FROM business.p6_daily_snapshots").fetchone() == {
            "n": 0
        }


def test_daily_api_keeps_legacy_openapi_and_owner_only(fixture: P3Fixture, tmp_path: Path) -> None:
    files, _ = prepare(fixture, tmp_path / "daily-owned")
    task, _ = asyncio.run(execute(fixture, files))
    legacy = create_app(web_config=fixture.config, replenishment_store=fixture.store).openapi()
    app = create_app(
        web_config=fixture.config, replenishment_store=fixture.store, daily_enabled=True
    )
    assert app.openapi() == legacy
    from commerceops.entrypoints.daily_http import DAILY_PATHS

    assert set(app.state.daily_openapi["paths"]) == DAILY_PATHS
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get(f"/api/v1/daily-reports/{task}").status_code == 401
        client.cookies.update(fixture.client.cookies)
        result = client.get(f"/api/v1/daily-reports/{task}")
        assert result.status_code == 200 and result.json()["daily"]["state"] == "completed"
        assert result.headers["cache-control"] == "no-store"


def test_daily_source_composite_fk_rejects_cross_organization(
    fixture: P3Fixture, tmp_path: Path
) -> None:
    _, meta = prepare(fixture, tmp_path / "daily-owned")
    other = meta.model_copy(update={"organization_id": uuid4()})
    body = other.model_dump(mode="json")
    with connect(fixture.inventory.owner) as db:
        with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
            db.execute(
                """INSERT INTO business.p6_daily_source_bindings(id,organization_id,shop_id,
            config_ref,source_config_version,canonical_projection,projection,config_digest)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    uuid4(),
                    other.organization_id,
                    other.shop_id,
                    other.config_ref,
                    other.source_config_version,
                    canonical_bytes(body).decode(),
                    Jsonb(body),
                    other.config_digest,
                ),
            )


def test_daily_report_insert_failure_rolls_back_snapshot(
    fixture: P3Fixture, tmp_path: Path
) -> None:
    files, _ = prepare(fixture, tmp_path / "daily-owned")
    task = create_daily_task(
        fixture.config.database,
        files,
        fixture.actor,
        fixture.inventory.data.shop,
        uuid4(),
        "source-1",
        DAY,
    )
    with connect(fixture.inventory.owner) as db:
        db.execute("""CREATE FUNCTION business.daily_test_fail() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'controlled report insert failure'; END $$""")
        db.execute("""CREATE TRIGGER daily_test_fail BEFORE INSERT ON business.p6_daily_reports
        FOR EACH ROW EXECUTE FUNCTION business.daily_test_fail()""")

    async def run() -> None:
        session = WorkerSession(fixture.config.database, fixture.inventory.data.organization)
        await session.start()
        try:
            job = await JobQueue(session).claim()
            assert job and job.task_id == task
            with pytest.raises(psycopg.Error):
                await DailyRunner(DailyStore(fixture.config.database, session, files)).run(job)
        finally:
            await session.close(clean=True)

    asyncio.run(run())
    with connect(fixture.config.database) as db:
        assert db.execute("SELECT count(*) AS n FROM business.p6_daily_snapshots").fetchone() == {
            "n": 0
        }
        assert db.execute("SELECT count(*) AS n FROM business.p6_daily_reports").fetchone() == {
            "n": 0
        }


def test_daily_load_deadline_closes_blocked_owned_pg_connection(
    fixture: P3Fixture, tmp_path: Path
) -> None:
    import time

    files, meta = prepare(fixture, tmp_path / "daily-owned")
    task = create_daily_task(
        fixture.config.database,
        files,
        fixture.actor,
        fixture.inventory.data.shop,
        uuid4(),
        "source-1",
        DAY,
    )

    async def run() -> None:
        session = WorkerSession(fixture.config.database, fixture.inventory.data.organization)
        await session.start()
        try:
            claimed = await JobQueue(session).claim()
            assert claimed and claimed.task_id == task
            store = DailyStore(fixture.config.database, session, files)
            # owner事务确定持有actor行锁，权限读取会真实阻塞；不靠随机sleep制造竞态。
            with connect(fixture.inventory.owner) as owner:
                owner.execute(
                    "SELECT id FROM business.principals WHERE id=%s FOR UPDATE",
                    (fixture.actor.principal_id,),
                )
                tick = time.monotonic()
                with pytest.raises(ValueError, match="DAILY_SOURCE_UNAVAILABLE"):
                    await store.load(claimed, tick + 1)
                assert time.monotonic() - tick < 3
            await DailyRunner(store).run(claimed)
            assert await store.existing(claimed) is not None
        finally:
            await session.close(clean=True)

    asyncio.run(run())


def test_daily_native_new_process_replay_without_source_files(
    fixture: P3Fixture, tmp_path: Path
) -> None:
    import os
    import subprocess
    import sys

    files, _ = prepare(fixture, tmp_path / "daily-owned")
    task = create_daily_task(
        fixture.config.database,
        files,
        fixture.actor,
        fixture.inventory.data.shop,
        uuid4(),
        "source-1",
        DAY,
    )
    config = files.directory / "deployment.json"
    config.write_text(files.model_dump_json())
    config.chmod(0o600)
    db = fixture.config.database
    env = os.environ.copy()
    env.update(
        COMMERCEOPS_DB_HOST=db.host,
        COMMERCEOPS_DB_PORT=str(db.port),
        COMMERCEOPS_DB_NAME=db.name,
        COMMERCEOPS_DB_USER=db.user,
        COMMERCEOPS_DB_PASSWORD_FILE=str(db.password_file),
    )
    args = [
        sys.executable,
        "-m",
        "tests.daily_worker_process",
        "--deployment",
        str(config),
        "--organization",
        str(fixture.inventory.data.organization),
        "--task",
        str(task),
    ]
    first = subprocess.run(args, env=env, capture_output=True, text=True, timeout=60)
    assert first.returncode == 0, first.stdout + first.stderr
    (files.directory / f"{files.bindings[0].binding_id}.json").unlink()
    second = subprocess.run([*args, "--ack"], env=env, capture_output=True, text=True, timeout=60)
    assert second.returncode == 0, second.stdout + second.stderr
    with connect(fixture.config.database) as connection:
        assert connection.execute(
            "SELECT count(*) AS n FROM business.p6_daily_reports"
        ).fetchone() == {"n": 1}
        assert connection.execute(
            "SELECT status,attempts FROM business.jobs WHERE task_id=%s", (task,)
        ).fetchone() == {"status": "done", "attempts": 2}
