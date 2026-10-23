"""自有PG澄清1:1入站/原键/权限/unknown；不产生业务task/job或Base对象。"""

import asyncio
from dataclasses import replace

import pytest
from commerceops.adapters.feishu.contracts import ProbePolicy
from commerceops.application.feishu_business.clarification import ClarificationMessage, NoticeResult
from commerceops.application.replenishment.contracts import WebFailure
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_clarification import ClarificationDeliveryStore
from commerceops.infrastructure.worker_lock import WorkerSession
from psycopg import sql

from tests.p3_support import P3Fixture
from tests.test_p3_pg import fixture as fixture
from tests.test_p4_gateway_pg import message, service

pytestmark = pytest.mark.integration


def business_counts(f: P3Fixture) -> dict[str, int]:
    result: dict[str, int] = {}
    with connect(f.config.database) as db:
        for table in (
            "business_tasks",
            "jobs",
            "analysis_reports",
            "replenishment_plans",
            "approvals",
            "executions",
            "replenishment_items",
            "outbox",
        ):
            row = db.execute(
                sql.SQL("SELECT count(*) AS n FROM business.{}").format(sql.Identifier(table))
            ).fetchone()
            assert row
            result[table] = row["n"]
    return result


def policy(f: P3Fixture) -> ProbePolicy:
    return ProbePolicy(
        f.inventory.data.app,
        f.inventory.data.tenant,
        "synthetic-bot",
        frozenset({"p4-synthetic-user"}),
        frozenset({"p4-synthetic-chat"}),
    )


class Sender:
    def __init__(self, outcome: str = "sent"):
        self.outcome = outcome
        self.calls: list[ClarificationMessage] = []

    async def send_clarification(self, request: ClarificationMessage) -> NoticeResult:
        self.calls.append(request)
        return NoticeResult.model_validate(
            {
                "outcome": self.outcome,
                "code": "SYNTHETIC_RESULT",
                "message_id": "synthetic-reply" if self.outcome == "sent" else None,
            }
        )


@pytest.mark.parametrize("kind", ["p2p", "group"])
def test_ambiguous_has_one_inbox_reply_original_uuid_and_zero_business_delta(
    fixture: P3Fixture, kind: str
) -> None:
    f = fixture
    s = service(f)
    original = replace(message(f, kind=kind), text="分析一下")
    before = business_counts(f)
    result = s.message(original)
    assert result["state"] == "needs_clarification" and "task_id" not in result
    for _ in range(10):
        assert s.message(original)["reply_id"] == result["reply_id"]
        assert (
            s.message(replace(original, event_id="another-event"))["reply_id"] == result["reply_id"]
        )
    assert business_counts(f) == before
    with connect(f.config.database) as db:
        rows = db.execute("SELECT * FROM business.p4_clarification_replies").fetchall()
        inbox = db.execute(
            "SELECT count(*) AS n FROM business.inbox_events WHERE source='feishu_business'"
        ).fetchone()
        assert len(rows) == 1 and inbox and inbox["n"] == 1
        assert rows[0]["provider_uuid"].version == 4 and rows[0]["status"] == "pending"
    complete = s.message(
        replace(
            original,
            event_id="complete-event",
            message_id="new-complete-message",
            text="分析库存并生成补货建议",
        )
    )
    assert complete["state"] == "queued"
    after = business_counts(f)
    assert after["business_tasks"] - before["business_tasks"] == 2
    assert after["jobs"] - before["jobs"] == 2


@pytest.mark.parametrize("outcome", ["sent", "unknown"])
def test_unique_worker_send_or_unknown_never_blind_resends(
    fixture: P3Fixture, outcome: str
) -> None:
    f = fixture
    service(f).message(replace(message(f), text="分析一下"))
    sender = Sender(outcome)

    async def run() -> None:
        session = WorkerSession(f.config.database, f.inventory.data.organization)
        await session.start()
        try:
            store = ClarificationDeliveryStore(session, policy(f), sender, controlled_sender=True)
            assert await store.dispatch_one() == outcome
            assert await store.dispatch_one() == "idle"
            await store.reconcile()
        finally:
            await session.close(clean=True)

    asyncio.run(run())
    assert len(sender.calls) == 1
    with connect(f.config.database) as db:
        row = db.execute(
            "SELECT provider_uuid,status,attempts FROM business.p4_clarification_replies"
        ).fetchone()
        assert row and row["provider_uuid"] == sender.calls[0].provider_uuid
        assert row["status"] == outcome and row["attempts"] == 1


def test_revoked_actor_never_receives_pending_reply(fixture: P3Fixture) -> None:
    f = fixture
    service(f).message(replace(message(f), text="分析一下"))
    with connect(f.inventory.owner) as db:
        db.execute(
            "UPDATE business.principals SET enabled=false,auth_version=auth_version+1 WHERE id=%s",
            (f.actor.principal_id,),
        )
    sender = Sender()

    async def run() -> None:
        session = WorkerSession(f.config.database, f.inventory.data.organization)
        await session.start()
        try:
            store = ClarificationDeliveryStore(session, policy(f), sender, controlled_sender=True)
            assert await store.dispatch_one() == "denied"
        finally:
            await session.close(clean=True)

    asyncio.run(run())
    assert sender.calls == []


def test_unauthorized_ambiguous_input_creates_neither_inbox_nor_reply(fixture: P3Fixture) -> None:
    f = fixture
    s = service(f)
    with connect(f.inventory.owner) as db:
        db.execute(
            "UPDATE business.principals SET roles='{}',auth_version=auth_version+1 WHERE id=%s",
            (f.actor.principal_id,),
        )
    with pytest.raises(WebFailure):
        s.message(replace(message(f), text="分析一下"))
    with connect(f.config.database) as db:
        row = db.execute("SELECT count(*) AS n FROM business.p4_clarification_replies").fetchone()
        assert row and row["n"] == 0


def test_unknown_older_than_one_hour_is_held_and_original_uuid_never_changes(
    fixture: P3Fixture,
) -> None:
    f = fixture
    service(f).message(replace(message(f), text="分析一下"))
    with connect(f.inventory.owner) as db:
        row = db.execute("SELECT provider_uuid FROM business.p4_clarification_replies").fetchone()
        assert row
        original_uuid = row["provider_uuid"]
        db.execute("""UPDATE business.p4_clarification_replies SET status='unknown',attempts=1,
            first_attempt_at=clock_timestamp()-interval '2 hours',claimed_by='old-owned-sender',
            last_error='ACK_UNPROVEN'""")
    sender = Sender()

    async def run() -> None:
        session = WorkerSession(f.config.database, f.inventory.data.organization)
        await session.start()
        try:
            store = ClarificationDeliveryStore(session, policy(f), sender, controlled_sender=True)
            assert await store.dispatch_one() == "idle"
        finally:
            await session.close(clean=True)

    asyncio.run(run())
    assert sender.calls == []
    with connect(f.config.database) as db:
        row = db.execute(
            "SELECT provider_uuid,status FROM business.p4_clarification_replies"
        ).fetchone()
        assert row and row["provider_uuid"] == original_uuid and row["status"] == "unknown"


def test_removed_group_scope_denies_fixed_reply_before_transport(fixture: P3Fixture) -> None:
    f = fixture
    service(f).message(replace(message(f, kind="group"), text="分析一下"))
    sender = Sender()
    closed_policy = replace(policy(f), allowed_group_chat_ids=frozenset())

    async def run() -> None:
        session = WorkerSession(f.config.database, f.inventory.data.organization)
        await session.start()
        try:
            store = ClarificationDeliveryStore(
                session, closed_policy, sender, controlled_sender=True
            )
            assert await store.dispatch_one() == "denied"
        finally:
            await session.close(clean=True)

    asyncio.run(run())
    assert sender.calls == []


def test_existing_single_worker_maintenance_sends_reply_without_business_jobs(
    fixture: P3Fixture,
) -> None:
    from commerceops.application.runner import RunRequest, RunResult
    from commerceops.infrastructure.worker import Worker

    f = fixture
    service(f).message(replace(message(f), text="分析一下"))
    before = business_counts(f)
    sender = Sender()

    class EmptyRunner:
        workflow_versions = frozenset({"g1-fixture-v1"})

        async def run(self, request: RunRequest) -> RunResult:
            raise AssertionError("clarification must not enqueue a graph job")

    async def run() -> None:
        session = WorkerSession(f.config.database, f.inventory.data.organization)
        await session.start()
        store = ClarificationDeliveryStore(session, policy(f), sender, controlled_sender=True)
        stop = asyncio.Event()

        async def maintenance() -> None:
            await store.reconcile()
            if sender.calls:
                stop.set()

        await Worker(
            session, EmptyRunner(), reconcile=maintenance, heartbeat_seconds=0.1, poll_seconds=0.02
        ).run(stop)

    asyncio.run(run())
    assert len(sender.calls) == 1 and business_counts(f) == before
