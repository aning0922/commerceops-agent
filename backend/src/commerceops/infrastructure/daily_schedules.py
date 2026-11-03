"""单Worker maintenance扫描；一期run/task/job/审计在同事务，不补重旧任务。"""

from uuid import UUID, uuid4, uuid5

from psycopg.types.json import Jsonb

from commerceops.application.daily.scheduling import ScheduleConfig, latest_due
from commerceops.application.daily.source import WORKFLOW, DailyTaskRequest, DailyUnsafe
from commerceops.application.replenishment.contracts import WebActor, WebFailure
from commerceops.domain.commerce_values import canonical_bytes, facts_hash
from commerceops.infrastructure.daily_sources import DailyDeployment
from commerceops.infrastructure.daily_store import SOURCE_SQL, bound_metadata
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.web_sessions import actor_guard, now, role_scope
from commerceops.infrastructure.worker_lock import WorkerSession, open_async


def configure_schedule(
    settings: DatabaseSettings,
    files: DailyDeployment,
    actor: WebActor,
    config: ScheduleConfig,
    *,
    enabled: bool,
) -> UUID:
    """仅表owner可用的受控CLI服务；显式当前session + admin/operator同owner。"""
    if type(enabled) is not bool:
        raise ValueError("DAILY_BOOLEAN_INVALID")
    with connect(settings) as db:
        owner = db.execute(
            r"""SELECT current_user=pg_get_userbyid(relowner) AS owner FROM pg_class WHERE
oid='business.p6_daily_schedules'::regclass"""
        ).fetchone()
        if not owner or not owner["owner"]:
            raise WebFailure("ACCESS_DENIED", 403)
        actor_guard(db, actor)
        if (config.organization_id, config.owner_id, config.owner_auth_version) != (
            actor.organization_id,
            actor.principal_id,
            actor.auth_version,
        ) or not all(role_scope(db, actor, config.shop_id, role) for role in ("operator", "admin")):
            raise WebFailure("ACCESS_DENIED", 403)
        active = files.active(config.organization_id, config.shop_id)
        row = db.execute(
            SOURCE_SQL, (active.binding_id, config.organization_id, config.shop_id)
        ).fetchone()
        metadata = bound_metadata(row, files, config.organization_id, config.shop_id)
        if (
            config.daily_source != metadata.source(active.binding_id)
            or config.first_business_day < metadata.earliest_business_day
        ):
            raise WebFailure("PLAN_CHANGED", 409)
        conversation = db.execute(
            r"""SELECT id FROM business.conversations WHERE id=%s AND organization_id=%s AND
actor_id=%s FOR SHARE""",
            (config.conversation_id, actor.organization_id, actor.principal_id),
        ).fetchone()
        if conversation is None or config.first_due_at <= now(db):
            raise WebFailure("INVALID_REQUEST", 422)
        if config.destination_binding_id is not None:
            dest = db.execute(
                r"""
SELECT id FROM business.p6_daily_destinations WHERE id=%s AND organization_id=%s AND
shop_id=%s AND owner_id=%s AND transport='fake' FOR SHARE""",
                (
                    config.destination_binding_id,
                    actor.organization_id,
                    config.shop_id,
                    actor.principal_id,
                ),
            ).fetchone()
            if dest is None:
                raise WebFailure("INVALID_REQUEST", 422)
        previous = db.execute(
            r"""SELECT * FROM business.p6_daily_schedules WHERE schedule_id=%s ORDER BY
schedule_version DESC FOR UPDATE""",
            (config.schedule_id,),
        ).fetchall()
        if previous and any(
            (p["organization_id"], p["shop_id"], p["owner_id"])
            != (config.organization_id, config.shop_id, config.owner_id)
            for p in previous
        ):
            raise WebFailure("RESOURCE_NOT_FOUND", 404)
        existing = next(
            (p for p in previous if p["schedule_version"] == config.schedule_version), None
        )
        body = config.model_dump(mode="json")
        if existing:
            if existing["config"] != body or existing["enabled"] != enabled:
                raise WebFailure("IDEMPOTENCY_CONFLICT", 409)
            return UUID(str(existing["id"]))
        expected = previous[0]["schedule_version"] + 1 if previous else 1
        if config.schedule_version != expected:
            raise WebFailure("PLAN_CHANGED", 409)
        db.execute(
            r"""UPDATE business.p6_daily_schedules SET
enabled=false,pause_reason='superseded',updated_at=clock_timestamp() WHERE
schedule_id=%s AND enabled""",
            (config.schedule_id,),
        )
        row_id = uuid4()
        db.execute(
            r"""
INSERT INTO
business.p6_daily_schedules(id,schedule_id,schedule_version,organization_id,shop_id,owner_id,
canonical_config,config,config_hash,enabled) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                row_id,
                config.schedule_id,
                config.schedule_version,
                config.organization_id,
                config.shop_id,
                config.owner_id,
                canonical_bytes(body).decode(),
                Jsonb(body),
                facts_hash(body),
                enabled,
            ),
        )
        db.execute(
            r"""
INSERT INTO
business.audit_events(id,organization_id,actor_id,source,action,entity_type,entity_id,after_state,trace_id)
VALUES(%s,%s,%s,'daily','schedule_configured','daily_schedule',%s,%s,%s)""",
            (
                uuid4(),
                actor.organization_id,
                actor.principal_id,
                row_id,
                Jsonb(
                    {
                        "schedule_id": str(config.schedule_id),
                        "version": config.schedule_version,
                        "enabled": enabled,
                    }
                ),
                uuid4(),
            ),
        )
        return row_id


def pause_schedule(
    settings: DatabaseSettings, actor: WebActor, schedule_id: UUID, version: int
) -> None:
    with connect(settings) as db:
        actor_guard(db, actor)
        row = db.execute(
            r"""SELECT * FROM business.p6_daily_schedules WHERE schedule_id=%s AND
schedule_version=%s FOR UPDATE""",
            (schedule_id, version),
        ).fetchone()
        if (
            row is None
            or (row["organization_id"], row["owner_id"])
            != (actor.organization_id, actor.principal_id)
            or not all(role_scope(db, actor, row["shop_id"], r) for r in ("admin", "operator"))
        ):
            raise WebFailure("RESOURCE_NOT_FOUND", 404)
        db.execute(
            r"""UPDATE business.p6_daily_schedules SET
enabled=false,pause_reason='owner_paused',updated_at=clock_timestamp() WHERE id=%s""",
            (row["id"],),
        )
        db.execute(
            r"""
INSERT INTO
business.audit_events(id,organization_id,actor_id,source,action,entity_type,entity_id,after_state,trace_id)
VALUES(%s,%s,%s,'daily','schedule_paused','daily_schedule',%s,%s,%s)""",
            (
                uuid4(),
                actor.organization_id,
                actor.principal_id,
                row["id"],
                Jsonb({"version": version}),
                uuid4(),
            ),
        )


class DailyScheduler:
    def __init__(self, settings: DatabaseSettings, session: WorkerSession, files: DailyDeployment):
        self.settings, self.session, self.files = settings, session, files

    async def reconcile(self) -> None:
        await self.session.check()
        # 一轮最多32个显式配置；没有新cron、第二Worker或并行Graph。
        async with await open_async(self.settings) as db:
            rows = await (
                await db.execute(
                    r"""
SELECT id FROM business.p6_daily_schedules WHERE organization_id=%s AND enabled
AND (config->>'first_due_at')::timestamptz<=clock_timestamp()
AND (last_created_day IS NULL OR (((last_created_day+2)::timestamp AT TIME ZONE
(config#>>'{daily_source,timezone}'))+make_interval(mins=>(config->>'delay_minutes')::int))
<=clock_timestamp()) ORDER BY updated_at,id LIMIT 32""",
                    (self.session.organization,),
                )
            ).fetchall()
        for row in rows:
            await self._one(row["id"])

    async def _one(self, row_id: UUID) -> None:
        async with await open_async(self.settings) as db, db.transaction():
            await db.execute("SET LOCAL statement_timeout='18000ms'")
            row = await (
                await db.execute(
                    r"""
SELECT * FROM business.p6_daily_schedules WHERE id=%s AND organization_id=%s AND
enabled FOR UPDATE""",
                    (row_id, self.session.organization),
                )
            ).fetchone()
            if row is None:
                return
            config = ScheduleConfig.model_validate_json(row["canonical_config"])
            if row["config"] != config.model_dump(mode="json") or row["config_hash"] != facts_hash(
                config.model_dump(mode="json")
            ):
                raise DailyUnsafe("DAILY_STORAGE_FAILURE")
            timestamp = await (await db.execute("SELECT clock_timestamp() AS time")).fetchone()
            if timestamp is None:
                raise DailyUnsafe("DAILY_STORAGE_FAILURE")
            due = latest_due(config, timestamp["time"], row["last_created_day"])
            if due is None:
                return
            pause = None
            permission = await (
                await db.execute(
                    "SELECT business.p6_current_permission(%s,%s,%s,%s) AS allowed",
                    (
                        config.owner_id,
                        config.organization_id,
                        config.shop_id,
                        config.owner_auth_version,
                    ),
                )
            ).fetchone()
            if not permission or not permission["allowed"]:
                pause = "DAILY_PERMISSION_INVALID"
            try:
                active = self.files.active(config.organization_id, config.shop_id)
                source = await (
                    await db.execute(
                        SOURCE_SQL, (active.binding_id, config.organization_id, config.shop_id)
                    )
                ).fetchone()
                metadata = bound_metadata(
                    source, self.files, config.organization_id, config.shop_id
                )
                if metadata.source(active.binding_id) != config.daily_source:
                    raise DailyUnsafe("DAILY_SOURCE_BINDING_CHANGED")
            except DailyUnsafe:
                pause = pause or "DAILY_SOURCE_BINDING_CHANGED"
            if pause:
                await db.execute(
                    r"""UPDATE business.p6_daily_schedules SET
enabled=false,pause_reason=%s,updated_at=clock_timestamp() WHERE id=%s""",
                    (pause, row_id),
                )
                await db.execute(
                    r"""
INSERT INTO
business.audit_events(id,organization_id,actor_id,source,action,entity_type,entity_id,after_state,trace_id)
VALUES(%s,%s,%s,'daily','schedule_auto_paused','daily_schedule',%s,%s,%s)""",
                    (
                        uuid4(),
                        config.organization_id,
                        config.owner_id,
                        row_id,
                        Jsonb({"code": pause}),
                        uuid4(),
                    ),
                )
                return
            old = await (
                await db.execute(
                    r"""
SELECT task_id FROM business.p6_daily_schedule_runs WHERE schedule_id=%s AND due_at=%s""",
                    (config.schedule_id, due.due_at),
                )
            ).fetchone()
            if old is None:
                task_id = uuid4()
                key = uuid5(config.schedule_id, due.due_at.isoformat())
                req = DailyTaskRequest(
                    schema_version="p6-daily-task-v1",
                    daily_source=config.daily_source,
                    business_day=due.business_day,
                    snapshot_id=uuid4(),
                    rules=config.rules,
                    request_key=key,
                    request_hash=facts_hash(
                        {"schedule_config": row["config_hash"], "due_at": due.due_at.isoformat()}
                    ),
                    conversation_id=config.conversation_id,
                    requester_auth_version=config.owner_auth_version,
                )
                await db.execute(
                    r"""
INSERT INTO
business.business_tasks(id,organization_id,shop_id,conversation_id,requester_id,kind,normalized_request,workflow_version,thread_id)
VALUES(%s,%s,%s,%s,%s,'daily_report',%s,%s,%s)""",
                    (
                        task_id,
                        config.organization_id,
                        config.shop_id,
                        config.conversation_id,
                        config.owner_id,
                        Jsonb(req.model_dump(mode="json")),
                        WORKFLOW,
                        str(task_id),
                    ),
                )
                run_id = uuid4()
                await db.execute(
                    r"""
INSERT INTO
business.p6_daily_schedule_runs(id,organization_id,shop_id,schedule_row_id,schedule_id,schedule_version,business_day,due_at,task_id,missed_periods,skipped_first_day,skipped_last_day)
VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        run_id,
                        config.organization_id,
                        config.shop_id,
                        row_id,
                        config.schedule_id,
                        config.schedule_version,
                        due.business_day,
                        due.due_at,
                        task_id,
                        due.missed_periods,
                        due.skipped_first_day,
                        due.skipped_last_day,
                    ),
                )
                await db.execute(
                    r"""INSERT INTO
business.jobs(id,organization_id,shop_id,task_id,kind,dedupe_key,payload_ref)
VALUES(%s,%s,%s,%s,'analyze',%s,%s)""",
                    (
                        uuid4(),
                        config.organization_id,
                        config.shop_id,
                        task_id,
                        f"p6-schedule:{config.schedule_id}:{due.due_at.isoformat()}",
                        f"task:{task_id}",
                    ),
                )
                await db.execute(
                    r"""
INSERT INTO
business.audit_events(id,organization_id,task_id,actor_id,source,action,entity_type,entity_id,after_state,trace_id)
VALUES(%s,%s,%s,%s,'daily','schedule_run_created','daily_schedule_run',%s,%s,%s)""",
                    (
                        uuid4(),
                        config.organization_id,
                        task_id,
                        config.owner_id,
                        run_id,
                        Jsonb(
                            {"due_at": due.due_at.isoformat(), "missed_periods": due.missed_periods}
                        ),
                        uuid4(),
                    ),
                )
            await db.execute(
                r"""UPDATE business.p6_daily_schedules SET
last_created_day=%s,updated_at=clock_timestamp() WHERE id=%s""",
                (due.business_day, row_id),
            )
            await self.session.check()
