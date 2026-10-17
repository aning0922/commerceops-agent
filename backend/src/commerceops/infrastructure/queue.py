"""真实 PG 短事务队列；启动锁与持久终止闸门由 WorkerSession 提供。"""

from typing import Literal, cast
from uuid import UUID

from psycopg import sql

from commerceops.application.runner import JobKind, RunRequest
from commerceops.infrastructure.worker_lock import WorkerSession, open_async


class OwnershipLost(Exception):
    pass


class JobQueue:
    def __init__(
        self,
        session: WorkerSession,
        *,
        lease_seconds: int = 60,
        task_ids: frozenset[UUID] | None = None,
    ):
        if lease_seconds < 1 or task_ids is not None and (not task_ids or len(task_ids) > 10):
            raise ValueError("lease must be positive")
        self.session = session
        self.lease_seconds = lease_seconds
        self.task_ids = None if task_ids is None else list(task_ids)

    async def recover_confirmed(self) -> None:
        """仅重排有持久停止/终止确认的 running；无任何按超时接管路径。"""
        await self.session.check()
        async with await open_async(self.session.settings) as db, db.transaction():
            await db.execute(
                """UPDATE business.jobs j SET status='ready',lease_owner=NULL,
                lease_until=NULL,available_at=clock_timestamp(),updated_at=clock_timestamp(),
                last_error='CONFIRMED_WORKER_TERMINATION'
                WHERE j.status='running'
                AND (%s::uuid[] IS NULL OR (j.organization_id=%s AND j.task_id=ANY(%s)))
                AND EXISTS
                (SELECT 1 FROM business.audit_events e WHERE e.source='worker'
                AND e.entity_type='worker_runtime' AND e.entity_id=j.lease_owner
                AND e.action='termination_confirmed')""",
                (self.task_ids, self.session.organization, self.task_ids),
            )

    async def claim(self) -> RunRequest | None:
        await self.session.check()
        async with await open_async(self.session.settings) as db, db.transaction():
            cursor = await db.execute(
                """WITH candidate AS (SELECT id FROM business.jobs
                WHERE status IN ('ready','retry_wait') AND available_at<=clock_timestamp()
                AND (%s::uuid[] IS NULL OR (organization_id=%s AND task_id=ANY(%s)))
                ORDER BY available_at,id FOR UPDATE SKIP LOCKED LIMIT 1)
                UPDATE business.jobs j SET status='running',attempts=attempts+1,
                lease_owner=%s,lease_until=clock_timestamp() + %s * interval '1 second',
                updated_at=clock_timestamp() FROM candidate
                WHERE j.id=candidate.id RETURNING j.*""",
                (
                    self.task_ids,
                    self.session.organization,
                    self.task_ids,
                    self.session.owner,
                    self.lease_seconds,
                ),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            cursor = await db.execute(
                """SELECT thread_id,workflow_version
                FROM business.business_tasks WHERE id=%s""",
                (row["task_id"],),
            )
            task = await cursor.fetchone()
            if task is None:
                raise OwnershipLost("job task missing")
            return RunRequest(
                UUID(str(row["id"])),
                UUID(str(row["task_id"])),
                UUID(str(row["organization_id"])),
                UUID(str(row["shop_id"])),
                task["thread_id"],
                task["workflow_version"],
                cast(JobKind, row["kind"]),
                row["payload_ref"],
                self.session.owner,
                row["attempts"],
            )

    async def renew(self, job: RunRequest) -> None:
        await self._update(
            job,
            """lease_until=clock_timestamp()+%s * interval '1 second',
            updated_at=clock_timestamp()""",
            (self.lease_seconds,),
        )

    async def done(self, job: RunRequest) -> None:
        await self._update(
            job,
            """status='done',lease_owner=NULL,lease_until=NULL,
            last_error=NULL,updated_at=clock_timestamp()""",
        )

    async def defer(self, job: RunRequest, seconds: int, *, failed: bool = False) -> None:
        if seconds < 0 or seconds > 86400:
            raise ValueError("invalid persistent delay")
        await self._update(
            job,
            """status='retry_wait',lease_owner=NULL,lease_until=NULL,
            available_at=clock_timestamp()+%s * interval '1 second',last_error=%s,
            updated_at=clock_timestamp()""",
            (seconds, "RUNNER_RETRY" if failed else "RUNNER_DEFER"),
        )

    async def dead(
        self,
        job: RunRequest,
        code: Literal[
            "RUNNER_FAILED",
            "WORKFLOW_VERSION_UNSUPPORTED",
            "JOB_KIND_UNSUPPORTED",
            "RUNNER_RESULT_INVALID",
        ] = "RUNNER_FAILED",
    ) -> None:
        await self._update(
            job,
            """status='dead',lease_owner=NULL,lease_until=NULL,
            last_error=%s,updated_at=clock_timestamp()""",
            (code,),
            unknown_workflow=code == "WORKFLOW_VERSION_UNSUPPORTED",
        )

    async def _update(
        self,
        job: RunRequest,
        assignments: str,
        args: tuple[object, ...] = (),
        *,
        unknown_workflow: bool = False,
    ) -> None:
        # assignments 为本文件固定 SQL；不接受外部字段/片段。
        await self.session.check()
        if job.owner != self.session.owner:
            raise OwnershipLost("job owner mismatch")
        async with await open_async(self.session.settings) as db, db.transaction():
            cursor = await db.execute(
                sql.SQL(
                    "UPDATE business.jobs SET {} WHERE id=%s AND task_id=%s "
                    "AND organization_id=%s AND shop_id=%s AND status='running' AND lease_owner=%s"
                ).format(sql.SQL(assignments)),
                (*args, job.job_id, job.task_id, job.organization_id, job.shop_id, job.owner),
            )
            if cursor.rowcount != 1:
                raise OwnershipLost("job ownership changed")
            if unknown_workflow:
                await db.execute(
                    """UPDATE business.business_tasks SET state='needs_attention',
                 failure_code='WORKFLOW_VERSION_UNSUPPORTED',version=version+1,
                 updated_at=clock_timestamp() WHERE id=%s AND organization_id=%s AND shop_id=%s
                 AND state NOT IN ('completed','rejected','expired')""",
                    (job.task_id, job.organization_id, job.shop_id),
                )
