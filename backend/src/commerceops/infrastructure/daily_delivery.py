"""仅PG Fake接收器：先持久sending，再独立提交接收回执；unknown不自动重发。"""

import json
from typing import Any, Literal
from uuid import UUID, uuid4

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from commerceops.application.daily.contracts import DailyDTO, MetricDisplay
from commerceops.application.daily.scheduling import ScheduleConfig
from commerceops.application.daily.source import DailyTaskRequest, DailyUnsafe
from commerceops.domain.commerce_values import canonical_bytes, facts_hash
from commerceops.infrastructure.daily_sources import DailyDeployment
from commerceops.infrastructure.daily_store import (
    RESULT_SQL,
    SOURCE_SQL,
    StoredDaily,
    bound_metadata,
    verified_row,
)
from commerceops.infrastructure.worker_lock import WorkerSession, open_async


class FakePayload(DailyDTO):
    schema_version: Literal["p6-daily-delivery-v1"]
    transport: Literal["fake"]
    report_id: UUID
    task_id: UUID
    snapshot_id: UUID
    content_hash: str
    facts_hash: str
    business_day: str
    timezone: str
    currency: str
    source_kind: Literal["mock", "woocommerce_test"]
    coverage_scope: Literal["controlled_test_dataset"]
    complete: Literal[True]
    display: tuple[MetricDisplay, ...]
    narrative_mode: Literal["template"]
    evidence_mode: Literal["not_used"]


def payload_for(task_id: UUID, stored: StoredDaily) -> FakePayload:
    if not stored.report.complete:
        raise DailyUnsafe("DAILY_SOURCE_INCOMPLETE")
    return FakePayload(
        schema_version="p6-daily-delivery-v1",
        transport="fake",
        report_id=stored.report_id,
        task_id=task_id,
        snapshot_id=stored.report.snapshot_id,
        content_hash=stored.report.content_hash,
        facts_hash=stored.report.facts_hash,
        business_day=stored.report.business_day.isoformat(),
        timezone=stored.report.source.timezone,
        currency=stored.report.source.currency,
        source_kind=stored.report.source.source_kind,
        coverage_scope="controlled_test_dataset",
        complete=True,
        display=stored.report.display,
        narrative_mode="template",
        evidence_mode="not_used",
    )


async def enqueue_delivery(
    db: AsyncConnection[dict[str, Any]], task_id: UUID, stored: StoredDaily, *, fake_enabled: bool
) -> None:
    if not stored.report.complete:
        return
    row = await (
        await db.execute(
            r"""SELECT r.id AS run_id,s.config,d.id AS destination_id,d.enabled
FROM business.p6_daily_schedule_runs r JOIN business.p6_daily_schedules s ON
s.id=r.schedule_row_id
JOIN business.p6_daily_destinations d ON
d.id=(s.config->>'destination_binding_id')::uuid
AND d.organization_id=r.organization_id AND d.shop_id=r.shop_id AND
d.owner_id=s.owner_id
WHERE r.task_id=%s AND s.enabled AND d.transport='fake' FOR SHARE OF s,d""",
            (task_id,),
        )
    ).fetchone()
    if row is None:
        return
    body = payload_for(task_id, stored).model_dump(mode="json")
    outbox_id, delivery_id, provider_key = uuid4(), uuid4(), uuid4()
    # 原outbox的禁止sender/sent/sending约束完全保留；Fake状态只在新日报表。
    await db.execute(
        r"""
INSERT INTO business.outbox(id,organization_id,shop_id,task_id,destination,
aggregate_id,aggregate_version,operation,dedupe_key,request_hash,payload,provider_idempotency_key,status)
VALUES(%s,%s,%s,%s,'daily_fake',%s,1,'daily_report_fake',%s,%s,%s,%s,'blocked')""",
        (
            outbox_id,
            stored.report.source.organization_id,
            stored.report.source.shop_id,
            task_id,
            stored.report_id,
            f"p6-daily-delivery:{stored.report_id}:{row['destination_id']}",
            facts_hash(body),
            Jsonb(body),
            provider_key,
        ),
    )
    await db.execute(
        r"""
INSERT INTO business.p6_daily_deliveries(id,organization_id,shop_id,task_id,report_id,
destination_binding_id,outbox_id,schedule_run_id,payload,canonical_payload,payload_hash,provider_key,status)
VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            delivery_id,
            stored.report.source.organization_id,
            stored.report.source.shop_id,
            task_id,
            stored.report_id,
            row["destination_id"],
            outbox_id,
            row["run_id"],
            Jsonb(body),
            canonical_bytes(body).decode(),
            facts_hash(body),
            provider_key,
            "pending" if fake_enabled and row["enabled"] else "disabled",
        ),
    )


class DailyFakeDelivery:
    def __init__(self, session: WorkerSession, files: DailyDeployment | None = None):
        self.session, self.files = session, files

    async def reconcile(self) -> None:
        await self.session.check()
        async with await open_async(self.session.settings) as db:
            await db.execute(
                r"""UPDATE business.p6_daily_deliveries d SET status='unknown',
failure_code='FAKE_RESULT_UNKNOWN',updated_at=clock_timestamp()
WHERE organization_id=%s AND status='sending' AND claimed_by<>%s
AND EXISTS(SELECT 1 FROM business.audit_events a WHERE a.source='worker'
AND a.entity_type='worker_runtime' AND a.entity_id=d.claimed_by AND
a.action='termination_confirmed')""",
                (self.session.organization, self.session.owner),
            )
            rows = await (
                await db.execute(
                    r"""SELECT id FROM business.p6_daily_deliveries WHERE organization_id=%s AND
status='pending' ORDER BY created_at,id LIMIT 32""",
                    (self.session.organization,),
                )
            ).fetchall()
        for row in rows:
            await self.send(row["id"])

    async def _validated(
        self, db: AsyncConnection[dict[str, Any]], delivery_id: UUID, *, status: str
    ) -> dict[str, Any] | None:
        row = await (
            await db.execute(
                r"""
SELECT d.*,o.payload AS outbox_payload,o.request_hash,
o.provider_idempotency_key,o.destination,o.operation,s.config,s.enabled AS
schedule_enabled,
dest.enabled AS destination_enabled,dest.owner_id AS destination_owner,dest.transport,
t.requester_id,t.normalized_request,r.schedule_id,r.schedule_version,s.schedule_id AS
current_schedule_id,
s.schedule_version AS current_schedule_version
FROM business.p6_daily_deliveries d JOIN business.outbox o ON o.id=d.outbox_id
JOIN business.business_tasks t ON t.id=d.task_id AND
t.organization_id=d.organization_id AND t.shop_id=d.shop_id
JOIN business.p6_daily_schedule_runs r ON r.id=d.schedule_run_id AND
r.task_id=d.task_id
JOIN business.p6_daily_schedules s ON s.id=r.schedule_row_id
JOIN business.p6_daily_destinations dest ON dest.id=d.destination_binding_id
AND dest.organization_id=d.organization_id AND dest.shop_id=d.shop_id
WHERE d.id=%s AND d.organization_id=%s AND d.status=%s FOR UPDATE OF d FOR SHARE OF
s,dest,t,o""",
                (delivery_id, self.session.organization, status),
            )
        ).fetchone()
        if row is None:
            return None
        config = ScheduleConfig.model_validate_json(json.dumps(row["config"]))
        if self.files is not None:
            active = self.files.active(config.organization_id, config.shop_id)
            source = await (
                await db.execute(
                    SOURCE_SQL, (active.binding_id, config.organization_id, config.shop_id)
                )
            ).fetchone()
            metadata = bound_metadata(source, self.files, config.organization_id, config.shop_id)
            if metadata.source(active.binding_id) != config.daily_source:
                raise DailyUnsafe("DAILY_SOURCE_BINDING_CHANGED")
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
        current = await (
            await db.execute(
                "SELECT business.p6_schedule_current(%s) AS allowed", (row["task_id"],)
            )
        ).fetchone()
        if (
            not permission
            or not permission["allowed"]
            or not current
            or not current["allowed"]
            or not (
                row["schedule_enabled"]
                and row["destination_enabled"]
                and row["transport"] == "fake"
                and row["destination_owner"] == row["requester_id"] == config.owner_id
                and row["destination_binding_id"] == config.destination_binding_id
                and row["schedule_id"] == row["current_schedule_id"] == config.schedule_id
                and row["schedule_version"]
                == row["current_schedule_version"]
                == config.schedule_version
            )
        ):
            raise DailyUnsafe("DAILY_PERMISSION_INVALID")
        request = DailyTaskRequest.model_validate_json(json.dumps(row["normalized_request"]))
        report_row = await (
            await db.execute(RESULT_SQL, (row["task_id"], row["organization_id"], row["shop_id"]))
        ).fetchone()
        if report_row is None:
            raise DailyUnsafe("DAILY_STORAGE_FAILURE")
        stored = verified_row(report_row, request)
        body = payload_for(row["task_id"], stored).model_dump(mode="json")
        if (
            row["payload"] != body
            or row["outbox_payload"] != body
            or row["canonical_payload"] != canonical_bytes(body).decode()
            or (
                row["request_hash"] != row["payload_hash"]
                or row["payload_hash"] != facts_hash(body)
                or row["provider_idempotency_key"] != row["provider_key"]
                or row["destination"] != "daily_fake"
                or row["operation"] != "daily_report_fake"
                or row["report_id"] != stored.report_id
            )
        ):
            raise DailyUnsafe("DAILY_STORAGE_FAILURE")
        return row

    async def send(self, delivery_id: UUID, *, after_receiver_commit: Any = None) -> None:
        await self.session.check()
        try:
            async with await open_async(self.session.settings) as db, db.transaction():
                await db.execute("SET LOCAL statement_timeout='18000ms'")
                row = await self._validated(db, delivery_id, status="pending")
                if row is None:
                    return
                await db.execute(
                    r"""
UPDATE business.p6_daily_deliveries SET
status='sending',attempts=1,claimed_by=%s,updated_at=clock_timestamp() WHERE id=%s""",
                    (self.session.owner, delivery_id),
                )
        except DailyUnsafe as error:
            async with await open_async(self.session.settings) as db:
                await db.execute(
                    r"""UPDATE business.p6_daily_deliveries SET
status='disabled',failure_code=%s,updated_at=clock_timestamp() WHERE id=%s AND
organization_id=%s AND status='pending'""",
                    (error.code, delivery_id, self.session.organization),
                )
            return
        try:
            # 接收副作用与sending分开提交。接收器本身用原provider_key永久去重，非checkpoint。
            async with await open_async(self.session.settings) as db, db.transaction():
                await db.execute("SET LOCAL statement_timeout='18000ms'")
                row = await self._validated(db, delivery_id, status="sending")
                if row is None or row["claimed_by"] != self.session.owner:
                    raise DailyUnsafe()
                await db.execute(
                    r"""
INSERT INTO
business.p6_daily_fake_receipts(provider_key,destination_binding_id,payload_hash,external_id)
VALUES(%s,%s,%s,%s) ON CONFLICT(provider_key) DO NOTHING""",
                    (
                        row["provider_key"],
                        row["destination_binding_id"],
                        row["payload_hash"],
                        "fake:" + str(row["provider_key"]),
                    ),
                )
                receipt = await (
                    await db.execute(
                        "SELECT * FROM business.p6_daily_fake_receipts WHERE provider_key=%s",
                        (row["provider_key"],),
                    )
                ).fetchone()
                if receipt is None or (
                    receipt["destination_binding_id"],
                    receipt["payload_hash"],
                ) != (row["destination_binding_id"], row["payload_hash"]):
                    raise DailyUnsafe()
            if after_receiver_commit is not None:
                await after_receiver_commit()
            async with await open_async(self.session.settings) as db:
                # sending期间配置改变不能撤回已提交Fake接收；保留真实Fake回执，不改投新目标。
                await db.execute(
                    r"""UPDATE business.p6_daily_deliveries SET
status='sent',external_id=%s,updated_at=clock_timestamp() WHERE id=%s AND
status='sending' AND claimed_by=%s""",
                    (receipt["external_id"], delivery_id, self.session.owner),
                )
        except Exception:
            async with await open_async(self.session.settings) as db:
                await db.execute(
                    r"""UPDATE business.p6_daily_deliveries SET
status='unknown',failure_code='FAKE_RESULT_UNKNOWN',updated_at=clock_timestamp()
WHERE id=%s AND status='sending' AND claimed_by=%s""",
                    (delivery_id, self.session.owner),
                )
