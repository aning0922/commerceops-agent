"""下一次 Root 自有 PG 窗口候选：真实 SQL/锁，transport Fake；本源码批未执行。"""

import asyncio
import hashlib
import json
import re
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal
from uuid import uuid4

import psycopg
import pytest
from commerceops.application.feishu_business.sdk_window import SDKScope
from commerceops.application.feishu_business.worker_window import ControlledWorkerWindow
from commerceops.entrypoints.database import grant_runtime, migrate, setup_checkpointer
from commerceops.entrypoints.feishu_worker_child import trusted_scope
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_sdk_ledger import PersistentSDKLedger
from commerceops.infrastructure.worker_lock import WorkerSession
from psycopg import sql
from psycopg.errors import CheckViolation
from psycopg.types.json import Jsonb

from tests.diagnostic_plugin import emit
from tests.p3_support import P3Fixture, initialize_p3
from tests.p4_recovery_support import settings
from tests.test_p3_pg import fixture as fixture
from tests.test_p4_first_create_pg import original_c0

pytestmark = pytest.mark.integration
SEND = """UPDATE business.p4_base_deliveries SET status='sending',last_operation='create',
attempts=2,claimed_by=%s WHERE outbox_id=%s"""

MigrationStage = Literal[
    "prepare-migrations",
    "create-db",
    "migrate0012",
    "checkpointer",
    "grant-runtime",
    "initialize_p3",
    "original_c0",
    "snapshot-before",
    "migrate0013",
    "snapshot-after",
    "compare",
    "revision-check",
    "cleanup-client",
    "cleanup-db",
    "cleanup-admin",
]
MIGRATION_STAGES: tuple[MigrationStage, ...] = (
    "prepare-migrations",
    "create-db",
    "migrate0012",
    "checkpointer",
    "grant-runtime",
    "initialize_p3",
    "original_c0",
    "snapshot-before",
    "migrate0013",
    "snapshot-after",
    "compare",
    "revision-check",
    "cleanup-client",
    "cleanup-db",
    "cleanup-admin",
)


def migration_sqlstate(error: BaseException) -> str | None:
    """仅受限真实异常链与 psycopg 属性；不用 message/orig/SQL/fixture 标识。"""
    pending = [error]
    seen: set[int] = set()
    while pending and len(seen) < 8:
        current = pending.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, psycopg.Error):
            try:
                value = current.sqlstate
            except BaseException:
                value = None  # 分类读取失败不能替换/吞掉原测试异常。
            if type(value) is str and re.fullmatch(r"[0-9A-Z]{5}", value):
                return value
        links: tuple[BaseException | None, ...]
        try:
            links = (current.__cause__, current.__context__)
        except BaseException:
            links = ()
        for linked in links:
            if isinstance(linked, BaseException) and id(linked) not in seen:
                pending.append(linked)
    return None


def migration_diag(stage: MigrationStage, error: BaseException | None = None) -> None:
    if stage not in MIGRATION_STAGES:
        raise ValueError("INVALID_MIGRATION_DIAGNOSTIC_STAGE")
    name = type(error).__name__ if error is not None else None
    if name is not None and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", name) is None:
        name = "BaseException"
    emit(
        "c0_migration_stage",
        stage=stage,
        exception_class=name,
        sqlstate=migration_sqlstate(error) if error is not None else None,
    )


async def current_sender(f: P3Fixture, window: ControlledWorkerWindow) -> WorkerSession:
    await trusted_scope(f.config, settings(f), window)
    session = WorkerSession(f.config.database, window.organization_id)
    await session.start()
    try:
        ledger = PersistentSDKLedger(session, window.window(settings(f)))

        async def fake_auth() -> Any:
            return SimpleNamespace(raw=SimpleNamespace(status_code=200), code=0)

        with ledger.scope(SDKScope(window.window_id, None, "preflight")):
            await ledger.invoke("auth.v3.tenant_access_token.internal", fake_auth)
        assert session.connection
        with connect(f.config.database) as db:
            # 原 BaseDeliveryStore 同形 observer，绑定实际专用锁连接；不作 SDK 发送。
            db.execute(
                """INSERT INTO business.p4_sender_state
            (organization_id,shop_id,destination_alias,configured_enabled,expires_at,
            worker_owner,worker_backend_pid,verification_mode)
            VALUES(%s,%s,'Base',true,%s,%s,%s,'controlled_sdk')
            ON CONFLICT(organization_id,shop_id,destination_alias) DO UPDATE SET
            configured_enabled=EXCLUDED.configured_enabled,expires_at=EXCLUDED.expires_at,
            worker_owner=EXCLUDED.worker_owner,worker_backend_pid=EXCLUDED.worker_backend_pid,
            verification_mode=EXCLUDED.verification_mode,checked_at=clock_timestamp()""",
                (
                    window.organization_id,
                    window.shop_id,
                    window.expires_at,
                    session.owner,
                    session.connection.info.backend_pid,
                ),
            )
        return session
    except BaseException:
        await session.close(clean=True)
        raise


def assert_rollback_control(
    f: P3Fixture, window: ControlledWorkerWindow, session: WorkerSession
) -> None:
    assert window.first_create
    with connect(f.config.database) as db, db.transaction(force_rollback=True):
        assert db.execute(SEND, (session.owner, window.first_create.outbox_id)).rowcount == 1
    # SQL control已回滚；原 unknown/attempts1/history/SDK create0保持，非实际SDK create。
    with connect(f.config.database) as db:
        assert db.execute("SELECT status,attempts FROM business.p4_base_deliveries").fetchone() == {
            "status": "unknown",
            "attempts": 1,
        }


def denied_update(f: P3Fixture, statement: str | sql.Composed, params: tuple[Any, ...]) -> None:
    with connect(f.config.database) as db:
        with pytest.raises(CheckViolation):
            db.execute(statement, params)
        db.rollback()


@pytest.mark.parametrize("status", ["started", "raised", "returned", "not_called"])
def test_c0_trigger_rejects_any_exact_outbox_create_ledger_status(
    fixture: P3Fixture,
    status: str,
) -> None:
    f = fixture
    with original_c0(f) as window:

        async def run() -> None:
            session = await current_sender(f, window)
            try:
                assert_rollback_control(f, window, session)
                projection = window.first_create
                assert projection
                with connect(f.inventory.owner) as db:
                    prior = uuid4()
                    db.execute(
                        """INSERT INTO business.p4_sdk_windows
                    (id,organization_id,shop_id,expires_at,configured_enabled,method_caps,
                    verification_mode) VALUES(%s,%s,%s,clock_timestamp()-interval '1 second',
                    true,%s,'controlled_sdk')""",
                        (
                            prior,
                            window.organization_id,
                            window.shop_id,
                            Jsonb({"bitable.v1.app_table_record.create": 1}),
                        ),
                    )
                    # 明示人工构造的可能调用历史；没有调用SDK，也不篡改已有历史行。
                    db.execute(
                        """INSERT INTO business.p4_sdk_calls
                    (id,window_id,subject_id,task_id,scope_kind,method,status,completed_at)
                    VALUES(%s,%s,%s,%s,'base_projection','bitable.v1.app_table_record.create',
                    %s,CASE WHEN %s='started' THEN NULL ELSE clock_timestamp() END)""",
                        (
                            uuid4(),
                            prior,
                            projection.outbox_id,
                            next(iter(window.task_ids)),
                            status,
                            status,
                        ),
                    )
                denied_update(f, SEND, (session.owner, projection.outbox_id))
            finally:
                await session.close(clean=True)

        asyncio.run(run())


def test_c0_trigger_keeps_neighbor_bindings_unknown_history_and_revoked_permission_denied(
    fixture: P3Fixture,
) -> None:
    f = fixture
    with original_c0(f) as window:

        async def run() -> None:
            session = await current_sender(f, window)
            try:
                assert_rollback_control(f, window, session)
                projection = window.first_create
                assert projection
                statements: list[tuple[str, sql.Composable]] = [
                    ("client_token", sql.SQL("gen_random_uuid()")),
                    ("item_id", sql.SQL("gen_random_uuid()")),
                    ("projection_hash", sql.Literal("c" * 64)),
                    ("version", sql.Literal(2)),
                    ("attempts", sql.Literal(3)),
                    ("unknown_since", sql.Literal(None)),
                    ("first_attempt_at", sql.Literal(None)),
                    ("last_operation", sql.Literal("update")),
                    ("external_id", sql.Literal("synthetic-anchor")),
                    ("claimed_by", sql.Literal("wrong-current-owner")),
                ]
                for field, expression in statements:
                    # 固定测试语句集合，没有入站/外部输入；不改共享源码状态机。
                    assignments = {
                        "status": sql.Literal("sending"),
                        "last_operation": sql.Literal("create"),
                        "attempts": sql.Literal(2),
                        "claimed_by": sql.Literal(session.owner),
                        field: expression,
                    }
                    query = sql.SQL(
                        "UPDATE business.p4_base_deliveries SET {} WHERE outbox_id=%s"
                    ).format(
                        sql.SQL(",").join(
                            sql.SQL("{}={}").format(sql.Identifier(column), value)
                            for column, value in assignments.items()
                        )
                    )
                    denied_update(f, query, (projection.outbox_id,))
                with connect(f.inventory.owner) as db:
                    db.execute(
                        "UPDATE business.principals SET auth_version=auth_version+1 WHERE id=%s",
                        (f.actor.principal_id,),
                    )
                denied_update(f, SEND, (session.owner, projection.outbox_id))
            finally:
                await session.close(clean=True)

        asyncio.run(run())


def test_c0_trigger_rejects_actual_current_window_expiry_without_reset(fixture: P3Fixture) -> None:
    f = fixture
    with original_c0(f) as original:
        value = original.model_dump(mode="json")
        expiry = datetime.now(UTC) + timedelta(seconds=18)
        value["expires_at"] = expiry.isoformat()
        value["workflow_recovery"]["expires_at"] = expiry.isoformat()
        window = ControlledWorkerWindow.model_validate_json(json.dumps(value))

        async def run() -> None:
            session = await current_sender(f, window)
            try:
                assert_rollback_control(f, window, session)
                await asyncio.sleep(max(0, (expiry - datetime.now(UTC)).total_seconds()) + 0.02)
                assert window.first_create
                denied_update(f, SEND, (session.owner, window.first_create.outbox_id))
            finally:
                await session.close(clean=True)

        asyncio.run(run())


def test_forward_0012_upgrade_preserves_original_c0_rows_and_checkpoint_bytes(
    fixture: P3Fixture,
    tmp_path: Path,
) -> None:
    # 同本次新PG namespace另一个随机测试DB；不是原known70库或旧卷。
    stage: MigrationStage = "prepare-migrations"
    reported = False
    try:
        migration_diag(stage)
        old_migrations = tmp_path / "schema-0012"
        shutil.copytree("backend/migrations", old_migrations)
        (old_migrations / "versions/0013_p4_first_create.py").unlink()
        name = "p4_c0_preserve_" + uuid4().hex
        owner = fixture.inventory.owner.model_copy(update={"name": name})
        app = fixture.config.database.model_copy(update={"name": name})
        stage = "create-db"
        migration_diag(stage)
        with psycopg.connect(**fixture.inventory.owner.kwargs(), autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
            try:
                stage = "migrate0012"
                migration_diag(stage)
                migrate(owner, migrations=old_migrations)
                stage = "checkpointer"
                migration_diag(stage)
                asyncio.run(setup_checkpointer(owner))
                stage = "grant-runtime"
                migration_diag(stage)
                grant_runtime(owner)
                stage = "initialize_p3"
                migration_diag(stage)
                f = initialize_p3(owner, app, tmp_path / "legacy-private")
                try:
                    stage = "original_c0"
                    migration_diag(stage)
                    with original_c0(f):

                        def snapshot() -> dict[str, tuple[int, str]]:
                            with connect(owner) as db:
                                names = db.execute("""SELECT schemaname,tablename FROM pg_tables
                                WHERE schemaname IN ('business','checkpoints')
                                AND tablename<>'alembic_version'
                                ORDER BY schemaname,tablename""").fetchall()
                                result = {}
                                for row in names:
                                    rows = db.execute(
                                        sql.SQL(
                                            "SELECT row_to_json(t)::text AS body FROM {} t"
                                        ).format(
                                            sql.Identifier(row["schemaname"], row["tablename"])
                                        )
                                    ).fetchall()
                                    encoded = "\n".join(sorted(r["body"] for r in rows)).encode()
                                    result[row["schemaname"] + "." + row["tablename"]] = (
                                        len(rows),
                                        hashlib.sha256(encoded).hexdigest(),
                                    )
                                return result

                        stage = "snapshot-before"
                        migration_diag(stage)
                        before = snapshot()
                        stage = "migrate0013"
                        migration_diag(stage)
                        migrate(owner)
                        stage = "snapshot-after"
                        migration_diag(stage)
                        after = snapshot()
                        stage = "compare"
                        migration_diag(stage)
                        assert after == before
                        stage = "revision-check"
                        migration_diag(stage)
                        with connect(owner) as db:
                            assert db.execute(
                                "SELECT version_num FROM business.alembic_version"
                            ).fetchone() == {
                                "version_num": "0013_p4_first_create",
                            }
                except BaseException as error:
                    migration_diag(stage, error)
                    reported = True
                    raise
                finally:
                    migration_diag("cleanup-client")
                    try:
                        f.client.close()
                    except BaseException as error:
                        migration_diag("cleanup-client", error)
                        reported = True
                        raise
            except BaseException as error:
                if not reported:
                    migration_diag(stage, error)
                    reported = True
                raise
            finally:
                migration_diag("cleanup-db")
                try:
                    admin.execute(
                        sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
                    )
                except BaseException as error:
                    migration_diag("cleanup-db", error)
                    reported = True
                    raise
            stage = "cleanup-admin"
            migration_diag(stage)
    except BaseException as error:
        if not reported:
            migration_diag(stage, error)
        raise
