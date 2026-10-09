"""只供独立 G1 测试容器：样例跨进程/容器重建断言。"""

import argparse
import asyncio
from uuid import UUID, uuid4

from commerceops.infrastructure.checkpoint import checkpointer
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.repository import TaskRepository, TaskScope
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import empty_checkpoint

from tests.pg_support import inbox, seed
from tests.test_postgres import runtime

MARKER = "g1_persistence_fixture"


def write(settings: DatabaseSettings) -> None:
    with connect(settings) as connection:
        data = seed(connection)
        connection.execute(
            "UPDATE business.business_tasks SET kind=%s WHERE id=%s", (MARKER, data.task)
        )
        inbox(connection, data, event="persistence-event", message="persistence-message")
        TaskRepository(connection, TaskScope(data.organization, data.shop)).enqueue(
            data.task, "technical_fixture", f"{MARKER}:{data.task}", MARKER
        )
        connection.execute(
            """INSERT INTO business.audit_events
            (id,organization_id,task_id,actor_id,source,action,entity_type,entity_id,trace_id)
            VALUES (%s,%s,%s,%s,'postgres_technical','persist','task',%s,%s)""",
            (uuid4(), data.organization, data.task, data.principal, str(data.task), uuid4()),
        )

    async def save() -> None:
        checkpoint = empty_checkpoint()
        checkpoint["channel_values"] = {"technical_marker": MARKER}
        checkpoint["channel_versions"] = {"technical_marker": 1}
        config: RunnableConfig = {
            "configurable": {
                "thread_id": str(data.task),
                "checkpoint_ns": "",
            }
        }
        async with checkpointer(settings) as saver:
            await saver.aput(
                config, checkpoint, {"source": "input", "step": -1}, {"technical_marker": 1}
            )

    asyncio.run(save())
    print(f"persistence fixture committed: task={data.task}, thread={data.task}")


def verify(settings: DatabaseSettings) -> None:
    with connect(settings) as connection:
        tasks = connection.execute(
            "SELECT * FROM business.business_tasks WHERE kind=%s", (MARKER,)
        ).fetchall()
        if len(tasks) != 1:
            raise RuntimeError("persistence fixture cardinality mismatch")
        task = tasks[0]
        if task["thread_id"] != str(task["id"]):
            raise RuntimeError("thread mismatch")
        for table in ("inbox_events", "jobs", "audit_events"):
            # 表名为固定代码集合，不接受用户输入。
            from psycopg import sql

            row = connection.execute(
                sql.SQL("SELECT count(*) AS n FROM business.{} WHERE task_id=%s").format(
                    sql.Identifier(table)
                ),
                (task["id"],),
            ).fetchone()
            if row is None or row["n"] != 1:
                raise RuntimeError("persistence cardinality mismatch")
        repo = TaskRepository(connection, TaskScope(task["organization_id"], task["shop_id"]))
        repo.enqueue(UUID(str(task["id"])), "technical_fixture", f"{MARKER}:{task['id']}", MARKER)

    async def read() -> None:
        async with checkpointer(settings) as saver:
            config: RunnableConfig = {
                "configurable": {
                    "thread_id": task["thread_id"],
                    "checkpoint_ns": "",
                }
            }
            result = await saver.aget_tuple(config)
            if (
                result is None
                or result.checkpoint["channel_values"].get("technical_marker") != MARKER
            ):
                raise RuntimeError("checkpoint persistence mismatch")

    asyncio.run(read())
    print(
        f"persistence verified: task={task['id']}, thread={task['thread_id']}, inbox/jobs/audit=1"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["seed", "verify"])
    action = parser.parse_args().action
    settings = runtime(DatabaseSettings())
    if action == "seed":
        write(settings)
    else:
        verify(settings)


if __name__ == "__main__":
    main()
