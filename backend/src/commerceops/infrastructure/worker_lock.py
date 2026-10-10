"""专用 session 锁及持久启动闸门；不把 lease 当作进程死亡证明。"""

import os
import socket
import sys
from typing import Any
from uuid import UUID, uuid4

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from commerceops.infrastructure.database import DatabaseSettings

LOCK_KEY = 7412438461303


class WorkerBusy(Exception):
    pass


class TerminationRequired(Exception):
    pass


class LockLost(Exception):
    pass


def process_namespace() -> str:
    # Linux 容器必须核对实际 PID namespace；同 hostname 不足以证明进程相同。
    return os.readlink("/proc/self/ns/pid") if sys.platform == "linux" else "host"


async def open_async(settings: DatabaseSettings) -> AsyncConnection[dict[str, Any]]:
    return await AsyncConnection.connect(
        **settings.kwargs(),
        row_factory=dict_row,
        autocommit=True,
        options="-c statement_timeout=5000 -c lock_timeout=5000",
    )


async def lifecycle(
    db: AsyncConnection[dict[str, Any]],
    organization: UUID,
    owner: str,
    action: str,
    *,
    evidence: str | None = None,
) -> None:
    await db.execute(
        """INSERT INTO business.audit_events
        (id,organization_id,source,action,entity_type,entity_id,after_state,reason,trace_id,occurred_at)
        VALUES (%s,%s,'worker',%s,'worker_runtime',%s,%s,%s,%s,clock_timestamp())""",
        (
            uuid4(),
            organization,
            action,
            owner,
            Jsonb(
                {
                    "pid": os.getpid(),
                    "host": socket.gethostname(),
                    "pid_namespace": process_namespace(),
                }
            ),
            evidence,
            uuid4(),
        ),
    )


async def unresolved(db: AsyncConnection[dict[str, Any]]) -> list[dict[str, Any]]:
    cursor = await db.execute(
        """SELECT s.* FROM business.audit_events s
        WHERE s.source='worker' AND s.entity_type='worker_runtime' AND s.action='started'
        AND NOT EXISTS (SELECT 1 FROM business.audit_events e
        WHERE e.source='worker' AND e.entity_type='worker_runtime' AND e.entity_id=s.entity_id
        AND e.action='termination_confirmed')"""
    )
    return await cursor.fetchall()


def require_process_absent(process: Any) -> None:
    if (
        not isinstance(process, dict)
        or process.get("host") != socket.gethostname()
        or process.get("pid_namespace") != process_namespace()
    ):
        raise TerminationRequired("same process namespace proof required")
    pid = process.get("pid")
    if type(pid) is not int or pid <= 0:
        raise TerminationRequired("valid original process receipt required")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return
    except OSError:
        raise TerminationRequired("old process termination cannot be proved") from None
    else:
        raise TerminationRequired("old process still exists")


async def mark_attention(db: AsyncConnection[dict[str, Any]], owner: str) -> None:
    await db.execute(
        """UPDATE business.business_tasks t SET state='needs_attention',
        failure_code='WORKER_TERMINATION_UNCONFIRMED',version=version+1,updated_at=clock_timestamp()
        WHERE EXISTS (SELECT 1 FROM business.jobs j WHERE j.task_id=t.id
        AND j.status='running' AND j.lease_owner=%s)
        AND NOT (t.kind='inventory_analysis_only' AND t.state='completed'
        AND business.valid_inventory_result(t.id,t.organization_id,t.shop_id,t.workflow_version))
        AND t.failure_code IS DISTINCT FROM 'WORKER_TERMINATION_UNCONFIRMED'""",
        (owner,),
    )


class WorkerSession:
    def __init__(self, settings: DatabaseSettings, organization: UUID):
        self.settings = settings
        self.organization = organization
        self.owner = str(uuid4())
        self.connection: AsyncConnection[dict[str, Any]] | None = None
        self.active = False

    async def start(self) -> None:
        db = await open_async(self.settings)
        self.connection = db
        try:
            cursor = await db.execute("SELECT pg_try_advisory_lock(%s) AS acquired", (LOCK_KEY,))
            row = await cursor.fetchone()
            if not row or not row["acquired"]:
                raise WorkerBusy("another worker holds startup lock")
            blocked = False
            async with db.transaction():
                old = await unresolved(db)
                if old:
                    for run in old:
                        cursor = await db.execute(
                            """SELECT 1 FROM business.audit_events WHERE source='worker'
                            AND entity_type='worker_runtime' AND entity_id=%s
                            AND action='stopped'""",
                            (run["entity_id"],),
                        )
                        stopped = await cursor.fetchone()
                        try:
                            if stopped is None:
                                raise TerminationRequired(
                                    "unclean stop needs explicit confirmation"
                                )
                            require_process_absent(run["after_state"])
                        except TerminationRequired:
                            await mark_attention(db, run["entity_id"])
                            blocked = True
                        else:
                            await lifecycle(
                                db,
                                UUID(str(run["organization_id"])),
                                run["entity_id"],
                                "termination_confirmed",
                                evidence="clean stop OS absence",
                            )
                if not blocked:
                    # 孤立 running 行缺少生命周期证据也不能恢复。
                    cursor = await db.execute("""SELECT DISTINCT j.lease_owner FROM business.jobs j
                        WHERE j.status='running' AND NOT EXISTS
                        (SELECT 1 FROM business.audit_events e WHERE e.source='worker'
                        AND e.entity_type='worker_runtime' AND e.entity_id=j.lease_owner
                        AND e.action='termination_confirmed')""")
                    orphaned = await cursor.fetchall()
                    for job in orphaned:
                        await mark_attention(db, job["lease_owner"])
                    if orphaned:
                        blocked = True
                    else:
                        await lifecycle(db, self.organization, self.owner, "started")
            if blocked:
                raise TerminationRequired("old process termination must be confirmed")
            self.active = True
        except BaseException:
            await db.close()
            self.connection = None
            raise

    async def check(self) -> None:
        if not self.active or self.connection is None:
            raise LockLost("worker session inactive")
        try:
            # 不重复 pg_try_advisory_lock：session advisory 锁是可重入计数的。
            await self.connection.execute("SELECT 1")
        except Exception:
            self.active = False
            raise LockLost("startup lock connection lost") from None

    async def close(self, *, clean: bool = False) -> None:
        db = self.connection
        try:
            if db is not None and self.active and clean:
                await lifecycle(db, self.organization, self.owner, "stopped")
        finally:
            self.active = False
            if db is not None:
                await db.close()
            self.connection = None


async def confirm_termination(settings: DatabaseSettings, owner: str, evidence: str) -> None:
    """同 host/PID namespace 的部署操作员确认；还需核对旧 PID 已不存在。

    无 HTTP/业务 API；不能从 lease 过期、锁可获取或自动超时产生此确认。
    """
    if not evidence.strip() or len(evidence) > 200:
        raise ValueError("termination evidence reference required")
    UUID(owner)
    db = await open_async(settings)
    try:
        cursor = await db.execute("SELECT pg_try_advisory_lock(%s) AS acquired", (LOCK_KEY,))
        row = await cursor.fetchone()
        if not row or not row["acquired"]:
            raise WorkerBusy("stop old worker before confirming termination")
        async with db.transaction():
            old = [run for run in await unresolved(db) if run["entity_id"] == owner]
            if len(old) != 1:
                cursor = await db.execute(
                    """SELECT reason FROM business.audit_events WHERE source='worker'
                    AND entity_type='worker_runtime' AND entity_id=%s
                    AND action='termination_confirmed'""",
                    (owner,),
                )
                confirmations = await cursor.fetchall()
                if len(confirmations) == 1 and confirmations[0]["reason"] == evidence:
                    return
                raise TerminationRequired("no unique unresolved worker receipt")
            require_process_absent(old[0]["after_state"])
            await lifecycle(
                db,
                UUID(str(old[0]["organization_id"])),
                owner,
                "termination_confirmed",
                evidence=evidence,
            )
    finally:
        await db.close()
