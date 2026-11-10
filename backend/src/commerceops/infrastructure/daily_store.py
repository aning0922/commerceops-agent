"""日报权威三表事务；历史回执先于采集，受理/提交锁当前权限和来源。"""

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from commerceops.adapters.commerce.daily import CollectionReceipt
from commerceops.application.daily.aggregation import aggregate_daily
from commerceops.application.daily.contracts import DailyInput, DailyReport, DailyRuleConfig
from commerceops.application.daily.source import (
    WORKFLOW,
    DailyMetadata,
    DailyTaskRequest,
    DailyUnsafe,
)
from commerceops.application.replenishment.contracts import WebActor, WebFailure
from commerceops.application.runner import RunRequest
from commerceops.domain.commerce_values import canonical_bytes, facts_hash
from commerceops.infrastructure.daily_sources import DailyDeployment, manifest_for
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.repository import TaskRepository, TaskScope
from commerceops.infrastructure.web_sessions import actor_guard, now, role_scope
from commerceops.infrastructure.worker_lock import WorkerSession, open_async

SOURCE_SQL = """SELECT b.*,s.adapter_kind,s.environment,s.external_shop_key,s.currency,s.timezone,
s.config_ref AS current_ref FROM business.p6_daily_source_bindings b JOIN business.shops s
ON s.organization_id=b.organization_id AND s.id=b.shop_id
WHERE b.id=%s AND b.organization_id=%s AND b.shop_id=%s FOR SHARE OF s"""


def bound_metadata(
    row: dict[str, Any] | None, files: DailyDeployment, org: UUID, shop: UUID
) -> DailyMetadata:
    active = files.active(org, shop)
    actual = files.metadata(active)
    if (
        row is None
        or row["id"] != active.binding_id
        or (
            row["config_digest"] != active.config_digest
            or row["config_ref"] != row["current_ref"]
            or row["config_ref"] != actual.config_ref
            or row["source_config_version"] != actual.source_config_version
            or row["projection"] != actual.model_dump(mode="json")
            or row["canonical_projection"].encode()
            != canonical_bytes(actual.model_dump(mode="json"))
            or any(
                row[k] != getattr(actual, k)
                for k in ("environment", "external_shop_key", "currency", "timezone")
            )
            or row["adapter_kind"] != actual.adapter_kind
        )
    ):
        raise DailyUnsafe("DAILY_SOURCE_BINDING_CHANGED")
    return actual


@dataclass(frozen=True)
class StoredDaily:
    report_id: UUID
    snapshot: DailyInput
    report: DailyReport
    receipt: CollectionReceipt


def verified_row(row: dict[str, Any], request: DailyTaskRequest) -> StoredDaily:
    """读路径重算同S1，不以hash存在或JSON shape代替业务复算。"""
    try:
        snapshot = DailyInput.model_validate_json(row["canonical_content"])
        report = DailyReport.model_validate_json(row["canonical_report"])
        receipt = CollectionReceipt.model_validate_json(row["canonical_receipt"])
        if (
            snapshot.snapshot_id != request.snapshot_id
            or snapshot.source != request.daily_source
            or snapshot.business_day != request.business_day
            or snapshot.rules != request.rules
            or snapshot.content_hash != row["content_hash"]
            or snapshot.canonical_content() != row["content"]
            or canonical_bytes(snapshot.canonical_content()).decode() != row["canonical_content"]
            or report != aggregate_daily(snapshot)
            or report.facts_hash != row["facts_hash"]
            or canonical_bytes(report.model_dump(mode="json")).decode() != row["canonical_report"]
            or facts_hash(report.model_dump(mode="json")) != row["report_hash"]
            or receipt.snapshot_content_hash != snapshot.content_hash
            or receipt.source_binding_id != str(request.daily_source.source_binding_id)
            or receipt.config_digest != request.daily_source.config_digest
            or receipt.config_digest != row["registered_config_digest"]
            or receipt.manifest_digest != row["registered_manifest_digest"]
            or not receipt.all_queries_revalidated
            or report.complete
            and receipt.expected_set_hash != receipt.observed_set_hash
            or row["request_content"] != canonical_bytes(request.model_dump(mode="json")).decode()
            or row["request_hash"] != facts_hash(request.model_dump(mode="json"))
            or facts_hash(receipt.model_dump(mode="json")) != row["receipt_hash"]
            or canonical_bytes(receipt.model_dump(mode="json")).decode() != row["canonical_receipt"]
        ):
            raise ValueError
        return StoredDaily(row["report_id"], snapshot, report, receipt)
    except (ValueError, TypeError, KeyError):
        raise DailyUnsafe("DAILY_STORAGE_FAILURE") from None


RESULT_SQL = """SELECT s.*,r.id AS report_id,r.canonical_report,r.report_hash,r.facts_hash,
b.projection->>'manifest_digest' AS registered_manifest_digest,
b.config_digest AS registered_config_digest
FROM business.p6_daily_snapshots s JOIN business.p6_daily_reports r
ON r.snapshot_id=s.id AND r.task_id=s.task_id AND r.organization_id=s.organization_id
AND r.shop_id=s.shop_id AND r.source_binding_id=s.source_binding_id
JOIN business.p6_daily_source_bindings b ON b.id=s.source_binding_id
AND b.organization_id=s.organization_id AND b.shop_id=s.shop_id
WHERE s.task_id=%s AND s.organization_id=%s AND s.shop_id=%s"""


class DailyStore:
    def __init__(self, settings: DatabaseSettings, session: WorkerSession, files: DailyDeployment):
        self.settings, self.session, self.files = settings, session, files

    async def _task(
        self, db: AsyncConnection[dict[str, Any]], run: RunRequest
    ) -> tuple[dict[str, Any], DailyTaskRequest]:
        if run.owner != self.session.owner or run.organization_id != self.session.organization:
            raise DailyUnsafe()
        cursor = await db.execute(
            """SELECT t.* FROM business.business_tasks t JOIN business.jobs j ON j.task_id=t.id
            AND j.organization_id=t.organization_id AND j.shop_id=t.shop_id
            WHERE t.id=%s AND t.organization_id=%s AND t.shop_id=%s AND j.id=%s
            AND j.lease_owner=%s AND j.status='running' AND j.kind=%s AND j.payload_ref=%s
            AND t.thread_id=%s AND t.workflow_version=%s AND t.kind='daily_report'
            FOR UPDATE OF t""",
            (
                run.task_id,
                run.organization_id,
                run.shop_id,
                run.job_id,
                run.owner,
                run.kind,
                run.payload_ref,
                run.thread_id,
                WORKFLOW,
            ),
        )
        row = await cursor.fetchone()
        if (
            row is None
            or run.workflow_version != WORKFLOW
            or run.payload_ref != f"task:{run.task_id}"
        ):
            raise DailyUnsafe()
        req = DailyTaskRequest.model_validate_json(json.dumps(row["normalized_request"]))
        if (
            req.daily_source.organization_id != run.organization_id
            or req.daily_source.shop_id != run.shop_id
        ):
            raise DailyUnsafe()
        return row, req

    async def _authorized(
        self, db: AsyncConnection[dict[str, Any]], task: dict[str, Any], request: DailyTaskRequest
    ) -> DailyMetadata:
        decision = await db.execute(
            "SELECT business.p6_current_permission(%s,%s,%s,%s) AS allowed",
            (
                task["requester_id"],
                task["organization_id"],
                task["shop_id"],
                request.requester_auth_version,
            ),
        )
        permitted = await decision.fetchone()
        if not permitted or not permitted["allowed"]:
            raise DailyUnsafe("DAILY_PERMISSION_INVALID")
        source = await db.execute(
            SOURCE_SQL,
            (request.daily_source.source_binding_id, task["organization_id"], task["shop_id"]),
        )
        metadata = bound_metadata(
            await source.fetchone(), self.files, task["organization_id"], task["shop_id"]
        )
        if metadata.source(request.daily_source.source_binding_id) != request.daily_source:
            raise DailyUnsafe("DAILY_SOURCE_BINDING_CHANGED")
        present = await (
            await db.execute("SELECT to_regclass('business.p6_daily_schedule_runs') AS name")
        ).fetchone()
        if present and present["name"] is not None:
            current = await (
                await db.execute(
                    "SELECT business.p6_schedule_current(%s) AS allowed", (task["id"],)
                )
            ).fetchone()
            if not current or not current["allowed"]:
                raise DailyUnsafe("DAILY_SCHEDULE_CHANGED")
        return metadata

    async def existing(self, run: RunRequest) -> StoredDaily | None:
        await self.session.check()
        async with await open_async(self.settings) as db, db.transaction():
            _, request = await self._task(db, run)
            cursor = await db.execute(RESULT_SQL, (run.task_id, run.organization_id, run.shop_id))
            row = await cursor.fetchone()
            return verified_row(row, request) if row is not None else None

    async def load(
        self, run: RunRequest, absolute_deadline: float
    ) -> tuple[DailyTaskRequest, DailyMetadata]:
        db: AsyncConnection[dict[str, Any]] | None = None

        async def operation() -> tuple[DailyTaskRequest, DailyMetadata]:
            nonlocal db
            await self.session.check()
            db = await open_async(self.settings)
            async with db, db.transaction():
                task, request = await self._task(db, run)
                if task["state"] not in ("queued", "analyzing"):
                    raise DailyUnsafe()
                metadata = await self._authorized(db, task, request)
                await db.execute(
                    """UPDATE business.business_tasks SET state='analyzing',version=version+1,
                updated_at=clock_timestamp() WHERE id=%s""",
                    (run.task_id,),
                )
                # 独立持久实际开始回执；queued/due/collection三种时间不混记。
                scheduled = await (
                    await db.execute(
                        "SELECT to_regclass('business.p6_daily_schedule_runs') AS name"
                    )
                ).fetchone()
                if scheduled and scheduled["name"] is not None:
                    await db.execute(
                        r"""
INSERT INTO business.audit_events(id,organization_id,task_id,actor_id,source,action,
entity_type,entity_id,after_state,trace_id) SELECT
%s,t.organization_id,t.id,t.requester_id,'daily',
'schedule_run_started','daily_schedule_run',r.id::text,jsonb_build_object('due_at',r.due_at),%s
FROM business.business_tasks t JOIN business.p6_daily_schedule_runs r ON
r.task_id=t.id
WHERE t.id=%s AND NOT EXISTS(SELECT 1 FROM business.audit_events a
WHERE a.task_id=t.id AND a.source='daily' AND a.action='schedule_run_started')""",
                        (uuid4(), uuid4(), run.task_id),
                    )
                return request, metadata

        task = asyncio.create_task(operation())
        try:
            done, _ = await asyncio.wait(
                (task,), timeout=max(0, absolute_deadline - time.monotonic())
            )
            if not done:
                raise DailyUnsafe("DAILY_SOURCE_UNAVAILABLE")
            return task.result()
        finally:
            if db is not None:
                await db.close()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def save(
        self, run: RunRequest, snapshot: DailyInput, report: DailyReport, receipt: CollectionReceipt
    ) -> StoredDaily:
        await self.session.check()
        async with await open_async(self.settings) as db, db.transaction():
            task, request = await self._task(db, run)
            cursor = await db.execute(RESULT_SQL, (run.task_id, run.organization_id, run.shop_id))
            old = await cursor.fetchone()
            if old is not None:
                return verified_row(old, request)
            metadata = await self._authorized(db, task, request)
            snapshot = DailyInput.model_validate_json(snapshot.model_dump_json())
            report = DailyReport.model_validate_json(report.model_dump_json())
            receipt = CollectionReceipt.model_validate_json(receipt.model_dump_json())
            if (
                snapshot.source != request.daily_source
                or snapshot.rules != request.rules
                or snapshot.snapshot_id != request.snapshot_id
                or snapshot.business_day != request.business_day
                or report != aggregate_daily(snapshot)
                or receipt.snapshot_content_hash != snapshot.content_hash
                or receipt.manifest_digest != metadata.manifest_digest
                or receipt.config_digest != metadata.config_digest
                or receipt.source_binding_id != str(request.daily_source.source_binding_id)
                or not receipt.all_queries_revalidated
                or report.complete
                and receipt.expected_set_hash != receipt.observed_set_hash
            ):
                raise DailyUnsafe()
            manifest = manifest_for(metadata)
            expected = {
                entry.order_id: {
                    "line_ids": sorted(entry.line_ids),
                    "refund_ids": sorted(entry.refund_ids),
                }
                for entry in manifest.orders
            }
            observed = {
                order.order_id: {
                    "line_ids": sorted(
                        line.line_id
                        for line in snapshot.order_lines
                        if line.order_id == order.order_id
                    ),
                    "refund_ids": sorted(
                        refund.refund_id
                        for refund in snapshot.refunds
                        if refund.order_id == order.order_id
                    ),
                }
                for order in snapshot.orders
            }
            if receipt.expected_set_hash != facts_hash(
                expected
            ) or receipt.observed_set_hash != facts_hash(observed):
                raise DailyUnsafe()
            report_id = uuid4()
            content = snapshot.canonical_content()
            canonical = canonical_bytes(content).decode()
            rbody = report.model_dump(mode="json")
            receipt_body = receipt.model_dump(mode="json")
            req_body = request.model_dump(mode="json")
            await db.execute(
                """INSERT INTO business.p6_daily_snapshots
            (id,organization_id,shop_id,task_id,source_binding_id,request_content,request_hash,
            schema_version,business_day,timezone,currency,window_start,window_end,collection_started_at,
            collected_at,complete,content,canonical_content,content_hash,receipt,canonical_receipt,receipt_hash)
            VALUES(%s,%s,%s,%s,%s,%s,%s,'p6-daily-snapshot-v1',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    snapshot.snapshot_id,
                    run.organization_id,
                    run.shop_id,
                    run.task_id,
                    request.daily_source.source_binding_id,
                    canonical_bytes(req_body).decode(),
                    facts_hash(req_body),
                    snapshot.business_day,
                    snapshot.source.timezone,
                    snapshot.source.currency,
                    snapshot.window.start,
                    snapshot.window.end,
                    snapshot.coverage.collection_started_at,
                    snapshot.coverage.collected_at,
                    report.complete,
                    Jsonb(content),
                    canonical,
                    snapshot.content_hash,
                    Jsonb(receipt_body),
                    canonical_bytes(receipt_body).decode(),
                    facts_hash(receipt_body),
                ),
            )
            await db.execute(
                """INSERT INTO business.p6_daily_reports
            (id,organization_id,shop_id,task_id,snapshot_id,source_binding_id,schema_version,metric_version,
            report,canonical_report,report_hash,canonical_facts,facts_hash,complete)
            VALUES(%s,%s,%s,%s,%s,%s,'p6-daily-report-v1','daily-metrics-v1',%s,%s,%s,%s,%s,%s)""",
                (
                    report_id,
                    run.organization_id,
                    run.shop_id,
                    run.task_id,
                    snapshot.snapshot_id,
                    request.daily_source.source_binding_id,
                    Jsonb(rbody),
                    canonical_bytes(rbody).decode(),
                    facts_hash(rbody),
                    report.canonical_bytes().decode(),
                    report.facts_hash,
                    report.complete,
                ),
            )
            await db.execute(
                """UPDATE business.business_tasks SET state=%s,failure_code=%s,
            version=version+1,updated_at=clock_timestamp() WHERE id=%s""",
                (
                    "completed" if report.complete else "needs_attention",
                    None if report.complete else "DAILY_SOURCE_INCOMPLETE",
                    run.task_id,
                ),
            )
            operations = await (
                await db.execute("SELECT to_regclass('business.p6_daily_deliveries') AS name")
            ).fetchone()
            saved = StoredDaily(report_id, snapshot, report, receipt)
            if operations and operations["name"] is not None:
                from commerceops.infrastructure.daily_delivery import enqueue_delivery

                await enqueue_delivery(
                    db, run.task_id, saved, fake_enabled=self.files.fake_delivery_enabled
                )
            await db.execute(
                """INSERT INTO business.audit_events(id,organization_id,task_id,actor_id,
            source,action,entity_type,entity_id,after_state,trace_id)
            VALUES(%s,%s,%s,%s,'daily','daily_report_saved','daily_report',%s,%s,%s)""",
                (
                    uuid4(),
                    run.organization_id,
                    run.task_id,
                    task["requester_id"],
                    report_id,
                    Jsonb(
                        {
                            "report_id": str(report_id),
                            "facts_hash": report.facts_hash,
                            "complete": report.complete,
                        }
                    ),
                    uuid4(),
                ),
            )
            await self.session.check()
            return saved

    async def fail(self, run: RunRequest, code: str) -> None:
        if code not in {
            "DAILY_SOURCE_UNAVAILABLE",
            "DAILY_SOURCE_INCOMPLETE",
            "DAILY_PERMISSION_INVALID",
            "DAILY_SOURCE_BINDING_CHANGED",
            "DAILY_STORAGE_FAILURE",
            "DAILY_SCHEDULE_CHANGED",
            "DAILY_WORKFLOW_UNSAFE",
        }:
            raise DailyUnsafe()
        await self.session.check()
        async with await open_async(self.settings) as db, db.transaction():
            task, _ = await self._task(db, run)
            cursor = await db.execute(RESULT_SQL, (run.task_id, run.organization_id, run.shop_id))
            if await cursor.fetchone() is not None:
                return
            state = (
                "needs_attention"
                if code
                in {
                    "DAILY_PERMISSION_INVALID",
                    "DAILY_SOURCE_BINDING_CHANGED",
                    "DAILY_WORKFLOW_UNSAFE",
                    "DAILY_STORAGE_FAILURE",
                    "DAILY_SCHEDULE_CHANGED",
                }
                else "failed"
            )
            await db.execute(
                """UPDATE business.business_tasks SET state=%s,failure_code=%s,
            version=version+1,updated_at=clock_timestamp() WHERE id=%s""",
                (state, code, run.task_id),
            )
            await db.execute(
                """INSERT INTO business.audit_events(id,organization_id,task_id,actor_id,
            source,action,entity_type,entity_id,after_state,trace_id)
            VALUES(%s,%s,%s,%s,'daily','daily_failed','business_task',%s,%s,%s)""",
                (
                    uuid4(),
                    run.organization_id,
                    run.task_id,
                    task["requester_id"],
                    run.task_id,
                    Jsonb({"code": code}),
                    uuid4(),
                ),
            )


def create_daily_task(
    settings: DatabaseSettings,
    files: DailyDeployment,
    actor: WebActor,
    shop: UUID,
    request_key: UUID,
    source_version: str,
    business_day: date | None = None,
) -> UUID:
    """同一受理事务写task/job；供受控服务调用，本片没有创建HTTP入口。"""
    with connect(settings) as db:
        actor_guard(db, actor)
        if not role_scope(db, actor, shop, "operator"):
            raise WebFailure("ACCESS_DENIED", 403)
        digest = facts_hash(
            {
                "shop": str(shop),
                "day": business_day.isoformat() if business_day else None,
                "source_version": source_version,
                "rule_version": "daily-rules-v1",
            }
        )
        old = db.execute(
            """SELECT * FROM business.business_tasks WHERE organization_id=%s
        AND requester_id=%s AND kind='daily_report' AND normalized_request->>'request_key'=%s
        FOR UPDATE""",
            (actor.organization_id, actor.principal_id, str(request_key)),
        ).fetchone()
        if old is not None:
            if old["normalized_request"]["request_hash"] != digest:
                raise WebFailure("IDEMPOTENCY_CONFLICT", 409)
            return UUID(str(old["id"]))
        active = files.active(actor.organization_id, shop)
        row = db.execute(SOURCE_SQL, (active.binding_id, actor.organization_id, shop)).fetchone()
        metadata = bound_metadata(row, files, actor.organization_id, shop)
        if metadata.source_config_version != source_version:
            raise WebFailure("PLAN_CHANGED", 409)
        timestamp = now(db)
        local_day = timestamp.astimezone(ZoneInfo(metadata.timezone)).date()
        day = business_day or local_day - timedelta(days=1)
        if day < metadata.earliest_business_day or day >= local_day:
            raise WebFailure("INVALID_REQUEST", 422)
        conversation = db.execute(
            """SELECT id FROM business.conversations WHERE organization_id=%s
        AND actor_id=%s AND channel='web' ORDER BY id LIMIT 1 FOR SHARE""",
            (actor.organization_id, actor.principal_id),
        ).fetchone()
        if conversation is None:
            conversation_id = uuid4()
            db.execute(
                """INSERT INTO business.conversations(id,organization_id,channel,chat_id,
            actor_id,topic_key) VALUES(%s,%s,'web',%s,%s,'daily') ON CONFLICT DO NOTHING""",
                (
                    conversation_id,
                    actor.organization_id,
                    str(actor.principal_id),
                    actor.principal_id,
                ),
            )
            conversation = db.execute(
                """SELECT id FROM business.conversations WHERE organization_id=%s
            AND actor_id=%s AND channel='web' AND chat_id=%s AND topic_key='daily' FOR SHARE""",
                (actor.organization_id, actor.principal_id, str(actor.principal_id)),
            ).fetchone()
            if conversation is None:
                raise WebFailure("NOT_READY", 409)
        req = DailyTaskRequest(
            schema_version="p6-daily-task-v1",
            daily_source=metadata.source(active.binding_id),
            business_day=day,
            snapshot_id=uuid4(),
            rules=DailyRuleConfig(currency=metadata.currency),
            request_key=request_key,
            request_hash=digest,
            conversation_id=conversation["id"],
            requester_auth_version=actor.auth_version,
        )
        task_id = uuid4()
        inserted = db.execute(
            """INSERT INTO business.business_tasks(id,organization_id,shop_id,
        conversation_id,requester_id,kind,normalized_request,workflow_version,thread_id)
        VALUES(%s,%s,%s,%s,%s,'daily_report',%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id""",
            (
                task_id,
                actor.organization_id,
                shop,
                conversation["id"],
                actor.principal_id,
                Jsonb(req.model_dump(mode="json")),
                WORKFLOW,
                str(task_id),
            ),
        ).fetchone()
        if inserted is None:
            # 并发相同键，在同SQL快照之后重新查已提交原任务。
            old = db.execute(
                """SELECT id,normalized_request FROM business.business_tasks
            WHERE organization_id=%s AND requester_id=%s AND kind='daily_report'
            AND normalized_request->>'request_key'=%s""",
                (actor.organization_id, actor.principal_id, str(request_key)),
            ).fetchone()
            if old is None or old["normalized_request"]["request_hash"] != digest:
                raise WebFailure("IDEMPOTENCY_CONFLICT", 409)
            return UUID(str(old["id"]))
        TaskRepository(db, TaskScope(actor.organization_id, shop)).enqueue(
            task_id, "analyze", f"p6-daily:{task_id}:analyze", f"task:{task_id}"
        )
        db.execute(
            """INSERT INTO business.audit_events(id,organization_id,task_id,actor_id,source,
        action,entity_type,entity_id,after_state,trace_id)
        VALUES(%s,%s,%s,%s,'daily','daily_task_accepted','business_task',%s,%s,%s)""",
            (
                uuid4(),
                actor.organization_id,
                task_id,
                actor.principal_id,
                task_id,
                Jsonb({"source_config_version": source_version, "business_day": day.isoformat()}),
                uuid4(),
            ),
        )
        return task_id
