"""S3新owned PG候选；本owner仅collect，实际SQL/退出由Root窗口核收。"""

import asyncio
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from commerceops.application.daily.contracts import DailyRuleConfig
from commerceops.application.daily.questions import QuestionInput, QuestionSpec
from commerceops.application.daily.scheduling import ScheduleConfig, due_at
from commerceops.application.daily.source import MockMetadata
from commerceops.application.replenishment.contracts import WebFailure
from commerceops.domain.commerce_values import canonical_bytes, facts_hash
from commerceops.entrypoints.api import create_app
from commerceops.infrastructure.daily_delivery import DailyFakeDelivery
from commerceops.infrastructure.daily_operations import DailyOperations
from commerceops.infrastructure.daily_questions import DailyQuestionStore, create_question
from commerceops.infrastructure.daily_schedules import DailyScheduler
from commerceops.infrastructure.daily_sources import DailyDeployment
from commerceops.infrastructure.daily_store import DailyStore, create_daily_task
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.queue import JobQueue
from commerceops.infrastructure.worker_lock import WorkerSession, mark_attention
from commerceops.workflows.daily_report import DailyRunner
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from tests.p3_support import ORIGIN, P3Fixture
from tests.test_daily_pg import prepare
from tests.test_daily_report import DAY
from tests.test_p3_pg import fixture as fixture

pytestmark = pytest.mark.integration


async def work(f: P3Fixture, files: DailyDeployment) -> UUID:
    session = WorkerSession(f.config.database, f.inventory.data.organization)
    await session.start()
    try:
        jobs = JobQueue(session)
        await jobs.recover_confirmed()
        run = await jobs.claim()
        assert run is not None
        runner = DailyRunner(DailyStore(f.config.database, session, files))
        await runner.run(run)
        await runner.run(run)
        assert session.connection is not None
        await mark_attention(session.connection, session.owner)
        await jobs.done(run)
        return run.task_id
    finally:
        await session.close(clean=True)


def completed(
    f: P3Fixture, directory: Path
) -> tuple[DailyDeployment, MockMetadata, UUID, QuestionInput, DailyOperations]:
    files, meta = prepare(f, directory)
    task = create_daily_task(
        f.config.database, files, f.actor, f.inventory.data.shop, uuid4(), "source-1", DAY
    )
    assert asyncio.run(work(f, files)) == task
    operations = DailyOperations(f.config.database, files, f.config.csrf_secret)
    with connect(f.config.database) as db:
        row = db.execute(
            "SELECT * FROM business.p6_daily_reports WHERE task_id=%s", (task,)
        ).fetchone()
    assert row is not None
    body = QuestionInput(
        schema_version="p6-daily-question-v1",
        request_key=uuid4(),
        report_id=row["id"],
        snapshot_id=row["snapshot_id"],
        content_hash=row["report"]["content_hash"],
        facts_hash=row["facts_hash"],
        question=QuestionSpec(
            kind="metric_evidence", metric_key="paid_order_total", finding_id=None
        ),
    )
    return files, meta, task, body, operations


def test_question_transaction_replay_and_frozen_current_permission(
    fixture: P3Fixture, tmp_path: Path
) -> None:
    f = fixture
    files, _, task, body, operations = completed(f, tmp_path / "daily")
    question = create_question(f.config.database, f.actor, task, body)
    assert create_question(f.config.database, f.actor, task, body) == question
    assert asyncio.run(work(f, files)) == question
    result = operations.question(f.actor, task, question, None)
    assert result.question.state == "completed" and result.question.answer is not None
    assert result.question.answer.narrative_mode == "template"
    assert result.question.answer.total_evidence_count == len(result.question.citations)
    with connect(f.config.database) as db:
        assert db.execute("SELECT count(*) AS n FROM business.p6_daily_questions").fetchone() == {
            "n": 1
        }
    changed = body.model_copy(
        update={"question": QuestionSpec(kind="data_quality", metric_key=None, finding_id=None)}
    )
    with pytest.raises(WebFailure, match="IDEMPOTENCY_CONFLICT"):
        create_question(f.config.database, f.actor, task, changed)
    with connect(f.inventory.owner) as db:
        db.execute(
            """UPDATE business.principal_role_shop_grants SET enabled=false
            WHERE principal_id=%s AND role='operator'""",
            (f.actor.principal_id,),
        )
    with pytest.raises(WebFailure):
        operations.question(f.actor, task, question, None)


@pytest.mark.parametrize(
    "change",
    [
        {"owner": "unowned-worker"},
        {"job_id": uuid4()},
        {"workflow_version": "other-workflow"},
        {"payload_ref": "task:unowned"},
        {"thread_id": "unowned-thread"},
    ],
)
def test_rejected_question_run_never_marks_original_task(
    fixture: P3Fixture, tmp_path: Path, change: dict[str, Any]
) -> None:
    f = fixture
    files, _, task, body, _ = completed(f, tmp_path / "daily")
    question = create_question(f.config.database, f.actor, task, body)

    async def execute() -> None:
        session = WorkerSession(f.config.database, f.actor.organization_id)
        await session.start()
        try:
            jobs = JobQueue(session)
            run = await jobs.claim()
            assert run is not None and run.task_id == question
            store = DailyQuestionStore(f.config.database, session)
            await store.run(replace(run, **change))
            with connect(f.config.database) as db:
                row = db.execute(
                    "SELECT state,failure_code FROM business.business_tasks WHERE id=%s",
                    (question,),
                ).fetchone()
                assert row == {"state": "queued", "failure_code": None}
            await store.run(run)
            await jobs.done(run)
        finally:
            await session.close(clean=True)

    asyncio.run(execute())


def test_real_session_post_csrf_and_uuid_wire(fixture: P3Fixture, tmp_path: Path) -> None:
    f = fixture
    files, _ = prepare(f, tmp_path / "daily")
    app = create_app(
        web_config=f.config, replenishment_store=f.store, daily_enabled=True, daily_files=files
    )
    with TestClient(app, base_url=ORIGIN) as client:
        client.cookies.update(f.client.cookies)
        body = {
            "schema_version": "p6-m3-web-v1",
            "shop_id": str(f.inventory.data.shop),
            "source_config_version": "source-1",
            "request_key": str(uuid4()),
            "business_day": DAY.isoformat(),
        }
        assert (
            client.post("/api/v1/daily-reports", json=body, headers={"Origin": ORIGIN}).status_code
            == 403
        )
        response = client.post("/api/v1/daily-reports", json=body, headers=f.headers())
        assert response.status_code == 202
        task = response.json()["accepted"]["task_id"]
        assert (
            client.post("/api/v1/daily-reports", json=body, headers=f.headers()).json()["accepted"][
                "task_id"
            ]
            == task
        )
        cap = client.get(
            "/api/v1/daily-capabilities", params={"shop_id": str(f.inventory.data.shop)}
        )
        assert cap.status_code == 200 and cap.json()["capabilities"]["enabled"] is True
        assert cap.json()["capabilities"]["external_sender_enabled"] is False
        assert client.get("/api/v1/daily-reports/" + task).json()["daily"]["state"] == "queued"


def schedule_row(
    f: P3Fixture, files: DailyDeployment, meta: MockMetadata, *, destination: bool = False
) -> tuple[UUID, ScheduleConfig]:
    """只有新owned测试owner可直登过去配置，以验证恢复；产品CLI仍拒绝过去first_due。"""
    with connect(f.inventory.owner) as db:
        conversation = db.execute(
            """SELECT id FROM business.conversations WHERE actor_id=%s AND channel='web'
            ORDER BY id LIMIT 1""",
            (f.actor.principal_id,),
        ).fetchone()
        assert conversation is not None
        destination_id = uuid4() if destination else None
        if destination:
            db.execute(
                """INSERT INTO business.p6_daily_destinations
                (id,organization_id,shop_id,owner_id,binding_version,transport,enabled)
                VALUES(%s,%s,%s,%s,1,'fake',true)""",
                (
                    destination_id,
                    f.actor.organization_id,
                    f.inventory.data.shop,
                    f.actor.principal_id,
                ),
            )
        config = ScheduleConfig(
            schema_version="p6-daily-schedule-v1",
            schedule_id=uuid4(),
            schedule_version=1,
            organization_id=f.actor.organization_id,
            shop_id=f.inventory.data.shop,
            owner_id=f.actor.principal_id,
            owner_auth_version=f.actor.auth_version,
            conversation_id=conversation["id"],
            daily_source=meta.source(files.bindings[0].binding_id),
            rules=DailyRuleConfig(currency=meta.currency),
            delay_minutes=0,
            first_business_day=meta.earliest_business_day - timedelta(days=5),
            first_due_at=due_at(meta.earliest_business_day - timedelta(days=5), meta.timezone, 0),
            destination_binding_id=destination_id,
        )
        row_id = uuid4()
        body = config.model_dump(mode="json")
        db.execute(
            """INSERT INTO business.p6_daily_schedules
            (id,schedule_id,schedule_version,organization_id,shop_id,owner_id,config,
            canonical_config,config_hash,enabled) VALUES(%s,%s,1,%s,%s,%s,%s,%s,%s,true)""",
            (
                row_id,
                config.schedule_id,
                config.organization_id,
                config.shop_id,
                config.owner_id,
                Jsonb(body),
                canonical_bytes(body).decode(),
                facts_hash(body),
            ),
        )
    return row_id, config


def test_schedule_latest_dedupe_pause_and_queued_task_retained(
    fixture: P3Fixture, tmp_path: Path
) -> None:
    f = fixture
    files, meta = prepare(f, tmp_path / "daily")
    row_id, config = schedule_row(f, files, meta)

    async def scan() -> None:
        session = WorkerSession(f.config.database, f.actor.organization_id)
        await session.start()
        try:
            scheduler = DailyScheduler(f.config.database, session, files)
            await scheduler.reconcile()
            await scheduler.reconcile()
        finally:
            await session.close(clean=True)

    asyncio.run(scan())
    with connect(f.inventory.owner) as db:
        runs = db.execute(
            "SELECT * FROM business.p6_daily_schedule_runs WHERE schedule_id=%s",
            (config.schedule_id,),
        ).fetchall()
        assert len(runs) == 1 and runs[0]["missed_periods"] >= 5
        task = runs[0]["task_id"]
        db.execute("UPDATE business.p6_daily_schedules SET enabled=false WHERE id=%s", (row_id,))
    assert asyncio.run(work(f, files)) == task
    with connect(f.config.database) as db:
        task_row = db.execute(
            "SELECT state,failure_code FROM business.business_tasks WHERE id=%s", (task,)
        ).fetchone()
        assert task_row == {"state": "needs_attention", "failure_code": "DAILY_SCHEDULE_CHANGED"}
        assert db.execute("SELECT count(*) AS n FROM business.p6_daily_snapshots").fetchone() == {
            "n": 0
        }


@pytest.mark.parametrize("lose_reply", [False, True])
def test_fake_delivery_durable_receiver_and_unknown_no_retry(
    fixture: P3Fixture, tmp_path: Path, lose_reply: bool
) -> None:
    f = fixture
    with connect(f.config.database) as db:
        clock = db.execute("SELECT clock_timestamp() AS time").fetchone()
        assert clock is not None
        timestamp = clock["time"]
    day = timestamp.astimezone(ZoneInfo("Asia/Taipei")).date() - timedelta(days=1)
    files, meta = prepare(f, tmp_path / "daily", day)
    files = files.model_copy(update={"fake_delivery_enabled": True})
    _, config = schedule_row(f, files, meta, destination=True)

    # 本例强绑定固定DAY报告，避免把当前日期的空数据误称旧fixture完整。
    async def perform() -> None:
        session = WorkerSession(f.config.database, f.actor.organization_id)
        await session.start()
        try:
            await DailyScheduler(f.config.database, session, files).reconcile()
            jobs = JobQueue(session)
            run = await jobs.claim()
            assert run is not None
            with connect(f.config.database) as db:
                request = db.execute(
                    "SELECT normalized_request FROM business.business_tasks WHERE id=%s",
                    (run.task_id,),
                ).fetchone()
            assert request is not None
            assert request["normalized_request"]["business_day"] == day.isoformat()
            await DailyRunner(DailyStore(f.config.database, session, files)).run(run)
            await jobs.done(run)
            with connect(f.config.database) as db:
                delivery = db.execute(
                    "SELECT * FROM business.p6_daily_deliveries WHERE task_id=%s", (run.task_id,)
                ).fetchone()
            assert delivery is not None

            async def lost() -> None:
                raise RuntimeError("controlled lost Fake reply")

            sender = DailyFakeDelivery(session)
            await sender.send(delivery["id"], after_receiver_commit=lost if lose_reply else None)
            await sender.reconcile()
            await sender.send(delivery["id"])
            with connect(f.config.database) as db:
                after = db.execute(
                    "SELECT * FROM business.p6_daily_deliveries WHERE id=%s", (delivery["id"],)
                ).fetchone()
                assert after is not None
                assert (
                    after["status"] == ("unknown" if lose_reply else "sent")
                    and after["attempts"] == 1
                )
                assert db.execute(
                    "SELECT count(*) AS n FROM business.p6_daily_fake_receipts"
                ).fetchone() == {"n": 1}
                original = db.execute(
                    "SELECT status,sender_enabled,external_id FROM business.outbox WHERE id=%s",
                    (delivery["outbox_id"],),
                ).fetchone()
                assert original == {
                    "status": "blocked",
                    "sender_enabled": False,
                    "external_id": None,
                }
        finally:
            await session.close(clean=True)

    asyncio.run(perform())
