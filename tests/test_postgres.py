"""必须使用独立真实 PG；缺配置直接失败，不用 SQLite/skip 替代。"""

import asyncio
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from commerceops.entrypoints.database import migrate, setup_checkpointer
from commerceops.infrastructure.checkpoint import checkpointer
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.repository import PersistenceConflict, TaskRepository, TaskScope
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import sql
from sqlalchemy.exc import ProgrammingError

from tests.pg_support import inbox, seed

pytestmark = pytest.mark.integration


@pytest.fixture
def settings() -> DatabaseSettings:
    return DatabaseSettings()


@pytest.fixture
def db(settings: DatabaseSettings) -> Iterator[psycopg.Connection[dict[str, Any]]]:
    with connect(settings) as connection:
        yield connection
        # 每个约束 fixture 回滚；持久重启样例由单独脚本负责。
        connection.rollback()


def runtime(settings: DatabaseSettings) -> DatabaseSettings:
    assert settings.runtime_password_file is not None
    return settings.model_copy(
        update={
            "user": "commerceops_app",
            "password_file": settings.runtime_password_file,
        }
    )


def test_revision_and_schema(db: psycopg.Connection[dict[str, Any]]) -> None:
    row = db.execute("SELECT version_num FROM business.alembic_version").fetchone()
    assert row and row["version_num"] == "0003_inventory_explanations"
    assert db.execute("SHOW server_version").fetchone()["server_version"].startswith("17.11")  # type: ignore[index]
    tables = db.execute("""SELECT table_schema, table_name FROM information_schema.tables
        WHERE table_schema IN ('business','checkpoints','public')""").fetchall()
    assert not any(row["table_schema"] == "public" for row in tables)
    assert {row["table_name"] for row in tables if row["table_schema"] == "business"} == {
        "organizations",
        "shops",
        "principals",
        "identities",
        "conversations",
        "inbox_events",
        "business_tasks",
        "jobs",
        "audit_events",
        "alembic_version",
        "principal_shop_scopes",
        "commerce_snapshots",
        "snapshot_products",
        "snapshot_order_lines",
        "snapshot_refunds",
        "analysis_reports",
        "explanation_links",
        "model_stage_budgets",
        "model_calls",
        "model_call_observations",
        "model_explanations",
        "explanation_task_results",
        "inventory_intent_requests",
        "inventory_intent_results",
    }
    row = db.execute("SELECT max(v) AS version FROM checkpoints.checkpoint_migrations").fetchone()
    assert row and row["version"] == len(AsyncPostgresSaver.MIGRATIONS) - 1


def test_job_dedup_scope_and_rollback(db: psycopg.Connection[dict[str, Any]]) -> None:
    data = seed(db)
    repo = TaskRepository(db, TaskScope(data.organization, data.shop))
    task = repo.get(data.task)
    assert task and task["thread_id"] == str(data.task)
    dedupe = str(uuid4())
    job = repo.enqueue(data.task, "analyze", dedupe, "technical_fixture")
    assert repo.enqueue(data.task, "analyze", dedupe, "technical_fixture") == job
    with pytest.raises(PersistenceConflict):
        repo.enqueue(data.task, "recover", dedupe, "changed")
    assert TaskRepository(db, TaskScope(uuid4(), data.shop)).get(data.task) is None
    assert TaskRepository(db, TaskScope(data.organization, uuid4())).get(data.task) is None
    with pytest.raises(PersistenceConflict):
        TaskRepository(db, TaskScope(uuid4(), data.shop)).enqueue(data.task, "analyze", dedupe, "x")
    # DB 失败回滚后连接可继续使用；原任务/job 留在同一外层事务。
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
        db.execute("UPDATE business.jobs SET organization_id=%s WHERE id=%s", (uuid4(), job))
    assert repo.get(data.task)


def test_inbox_event_message_dedup_and_cross_scope(db: psycopg.Connection[dict[str, Any]]) -> None:
    data = seed(db)
    other = seed(db)
    event, message = str(uuid4()), str(uuid4())
    inbox(db, data, event=event, message=message)
    for duplicate_event, duplicate_message in ((event, str(uuid4())), (str(uuid4()), message)):
        with pytest.raises(psycopg.errors.UniqueViolation), db.transaction():
            inbox(db, data, event=duplicate_event, message=duplicate_message)
    # 相同平台标识在另一个 app/tenant 作用域可保存。
    inbox(db, other, event=event, message=message)
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
        db.execute(
            """UPDATE business.inbox_events SET task_id=%s
            WHERE organization_id=%s""",
            (other.task, data.organization),
        )
    row = db.execute(
        "SELECT count(*) AS n FROM business.inbox_events WHERE organization_id IN (%s,%s)",
        (data.organization, other.organization),
    ).fetchone()
    assert row and row["n"] == 2


@pytest.mark.parametrize("field", ["shop_id", "requester_id", "conversation_id"])
def test_task_cross_organization(db: psycopg.Connection[dict[str, Any]], field: str) -> None:
    data, other = seed(db), seed(db)
    value = {
        "shop_id": other.shop,
        "requester_id": other.principal,
        "conversation_id": other.conversation,
    }[field]
    # INSERT 验证复合 FK；UPDATE 另有不可变身份 trigger。
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
        db.execute(
            sql.SQL("""INSERT INTO business.business_tasks
            SELECT %s,organization_id,{shop}, {conversation}, {requester}, kind,
            normalized_request,state,version,active_plan_id,workflow_version,%s,failure_code,
            created_at,updated_at FROM business.business_tasks WHERE id=%s""").format(
                shop=sql.Placeholder() if field == "shop_id" else sql.Identifier("shop_id"),
                conversation=sql.Placeholder()
                if field == "conversation_id"
                else sql.Identifier("conversation_id"),
                requester=sql.Placeholder()
                if field == "requester_id"
                else sql.Identifier("requester_id"),
            ),
            (new_id := uuid4(), value, str(new_id), data.task),
        )


def test_same_organization_cross_shop(db: psycopg.Connection[dict[str, Any]]) -> None:
    data = seed(db)
    other_shop = uuid4()
    db.execute(
        """INSERT INTO business.shops
        SELECT %s, organization_id, adapter_kind,%s,timezone,currency,config_ref,
        environment,created_at,updated_at FROM business.shops WHERE id=%s""",
        (other_shop, str(uuid4()), data.shop),
    )
    inbox(db, data, event=str(uuid4()), message=str(uuid4()))
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
        db.execute(
            "UPDATE business.inbox_events SET shop_id=%s WHERE task_id=%s", (other_shop, data.task)
        )
    job = TaskRepository(db, TaskScope(data.organization, data.shop)).enqueue(
        data.task, "analyze", str(uuid4()), "technical_fixture"
    )
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
        db.execute("UPDATE business.jobs SET shop_id=%s WHERE id=%s", (other_shop, job))


def test_identity_audit_foreign_keys(db: psycopg.Connection[dict[str, Any]]) -> None:
    data, other = seed(db), seed(db)
    for statement, parameters in [
        (
            "UPDATE business.identities SET principal_id=%s WHERE organization_id=%s",
            (other.principal, data.organization),
        ),
        (
            "UPDATE business.identities SET tenant_key=%s WHERE organization_id=%s",
            (other.tenant, data.organization),
        ),
        (
            """INSERT INTO business.audit_events
        (id,organization_id,task_id,actor_id,source,action,entity_type,entity_id,trace_id)
        VALUES (%s,%s,%s,%s,'technical_fixture','probe','task','fixture',%s)""",
            (uuid4(), data.organization, other.task, data.principal, uuid4()),
        ),
    ]:
        with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
            db.execute(statement, parameters)
    with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
        db.execute(
            "UPDATE business.principals SET roles=ARRAY['unapproved_role'] WHERE id=%s",
            (data.principal,),
        )


def test_task_thread_immutable_and_reserved_plan(db: psycopg.Connection[dict[str, Any]]) -> None:
    data = seed(db)
    for statement, parameters in [
        ("UPDATE business.business_tasks SET thread_id=%s WHERE id=%s", (str(uuid4()), data.task)),
        ("UPDATE business.business_tasks SET workflow_version='changed' WHERE id=%s", (data.task,)),
        ("UPDATE business.business_tasks SET active_plan_id=%s WHERE id=%s", (uuid4(), data.task)),
    ]:
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(statement, parameters)


def test_runtime_audit_append_only(settings: DatabaseSettings) -> None:
    with connect(runtime(settings)) as connection:
        data = seed(connection)
        audit_id = uuid4()
        connection.execute(
            """INSERT INTO business.audit_events
            (id,organization_id,task_id,actor_id,source,action,entity_type,entity_id,trace_id)
            VALUES (%s,%s,%s,%s,'technical_fixture','probe','task',%s,%s)""",
            (audit_id, data.organization, data.task, data.principal, str(data.task), uuid4()),
        )
        for query in [
            "UPDATE business.audit_events SET action='changed' WHERE id=%s",
            "DELETE FROM business.audit_events WHERE id=%s",
        ]:
            with pytest.raises(psycopg.errors.InsufficientPrivilege), connection.transaction():
                connection.execute(query, (audit_id,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege), connection.transaction():
            connection.execute("TRUNCATE business.audit_events")
        with pytest.raises(psycopg.errors.InsufficientPrivilege), connection.transaction():
            connection.execute("CREATE TABLE business.unauthorized (id integer)")
        connection.rollback()


def test_checkpointer_repeat_and_runtime_roundtrip(settings: DatabaseSettings) -> None:
    asyncio.run(setup_checkpointer(settings))
    asyncio.run(setup_checkpointer(settings))

    async def roundtrip() -> None:
        checkpoint = empty_checkpoint()
        checkpoint["channel_values"] = {"technical_marker": "G1"}
        checkpoint["channel_versions"] = {"technical_marker": 1}
        config: RunnableConfig = {"configurable": {"thread_id": str(uuid4()), "checkpoint_ns": ""}}
        async with checkpointer(runtime(settings)) as saver:
            saved = await saver.aput(
                config, checkpoint, {"source": "input", "step": -1}, {"technical_marker": 1}
            )
        async with checkpointer(runtime(settings)) as saver:
            result = await saver.aget_tuple(saved)
            assert result and result.checkpoint["channel_values"]["technical_marker"] == "G1"

    asyncio.run(roundtrip())


def test_failed_migration_atomic_and_recover(settings: DatabaseSettings) -> None:
    """使用同实例独立随机库注入 DDL 冲突；只删除本测试创建的库。"""
    name = "p102_failure_" + uuid4().hex
    isolated = settings.model_copy(update={"name": name})
    with psycopg.connect(**settings.kwargs(), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            with connect(isolated) as connection:
                connection.execute("CREATE SCHEMA business")
                connection.execute("CREATE TABLE business.jobs (sentinel integer)")
            with pytest.raises(ProgrammingError):
                migrate(isolated)
            with connect(isolated) as connection:
                row = connection.execute("""SELECT to_regclass('business.organizations') AS org,
                    to_regclass('business.alembic_version') AS revision""").fetchone()
                assert row and row == {"org": None, "revision": None}
                connection.execute("DROP TABLE business.jobs")
            migrate(isolated)
            migrate(isolated)
            with connect(isolated) as connection:
                assert connection.execute(
                    "SELECT version_num FROM business.alembic_version"
                ).fetchone()
            # 官方 autocommit setup 的部分提交故障，恢复仍由原官方迁移执行。
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(
                    AsyncPostgresSaver,
                    "MIGRATIONS",
                    [
                        AsyncPostgresSaver.MIGRATIONS[0],
                        "SELECT 1/0",
                    ],
                )
                with pytest.raises(psycopg.errors.DivisionByZero):
                    asyncio.run(setup_checkpointer(isolated))
            asyncio.run(setup_checkpointer(isolated))
            asyncio.run(setup_checkpointer(isolated))
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def test_permission_version_required(db: psycopg.Connection[dict[str, Any]]) -> None:
    data = seed(db)
    for statement in [
        "UPDATE business.principals SET roles=ARRAY['approver'] WHERE id=%s",
        "UPDATE business.principals SET enabled=false WHERE id=%s",
    ]:
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(statement, (data.principal,))
    db.execute(
        "UPDATE business.principals SET enabled=false,auth_version=auth_version+1 WHERE id=%s",
        (data.principal,),
    )
    with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
        db.execute("UPDATE business.principals SET auth_version=1 WHERE id=%s", (data.principal,))
