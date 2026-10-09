"""技术持久层；scope 必须来自调用者已验证身份，不是权限/Worker实现。"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection


@dataclass(frozen=True)
class TaskScope:
    organization_id: UUID
    shop_id: UUID


class PersistenceConflict(Exception):
    """同一个持久键与原始语义不一致，不重试掩盖冲突。"""


class TaskRepository:
    def __init__(self, connection: Connection[dict[str, Any]], scope: TaskScope):
        self.connection = connection
        self.scope = scope

    def get(self, task_id: UUID) -> dict[str, Any] | None:
        return self.connection.execute(
            """SELECT * FROM business.business_tasks
            WHERE organization_id=%s AND shop_id=%s AND id=%s""",
            (self.scope.organization_id, self.scope.shop_id, task_id),
        ).fetchone()

    def enqueue(self, task_id: UUID, kind: str, dedupe_key: str, payload_ref: str) -> UUID:
        """在调用者事务内追加逻辑 job；不领取、不执行、不开新事务。"""
        if self.get(task_id) is None:
            raise PersistenceConflict("task outside scope")
        row = self.connection.execute(
            """INSERT INTO business.jobs
            (id,organization_id,shop_id,task_id,kind,dedupe_key,payload_ref)
            VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (dedupe_key) DO NOTHING RETURNING id""",
            (
                uuid4(),
                self.scope.organization_id,
                self.scope.shop_id,
                task_id,
                kind,
                dedupe_key,
                payload_ref,
            ),
        ).fetchone()
        if row is not None:
            return UUID(str(row["id"]))
        existing = self.connection.execute(
            """SELECT * FROM business.jobs WHERE dedupe_key=%s
            AND organization_id=%s AND shop_id=%s AND task_id=%s AND kind=%s AND payload_ref=%s""",
            (
                dedupe_key,
                self.scope.organization_id,
                self.scope.shop_id,
                task_id,
                kind,
                payload_ref,
            ),
        ).fetchone()
        if existing is None:
            raise PersistenceConflict("job key payload conflict")
        return UUID(str(existing["id"]))
