"""A03待自有PG验证：正式P3/T4/T6与B adapter组合，transportFake/platform0。"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from commerceops.adapters.feishu.business_base import BusinessBaseAdapter
from commerceops.adapters.feishu.business_gateway import BusinessCard
from commerceops.adapters.feishu.projection_contract import ApiReply
from commerceops.application.feishu_business.delivery import DeliveryGate
from commerceops.application.replenishment.contracts import DecisionInput
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_base_delivery import BaseDeliveryStore
from commerceops.infrastructure.worker_lock import WorkerSession
from psycopg.errors import CheckViolation

from tests.p3_support import P3Fixture, P3Process
from tests.test_p3_approval_pg import payload, wait_state
from tests.test_p3_pg import fixture as fixture
from tests.test_p4_base_adapter import MemoryRecords
from tests.test_p4_base_reconciliation import row
from tests.test_p4_gateway_pg import message, service

pytestmark = pytest.mark.integration


def executed_feishu(f: P3Fixture, *, twenty: bool = False) -> tuple[UUID, UUID]:
    gateway = service(f)
    incoming = message(f)
    task = UUID(gateway.message(incoming)["task_id"])
    child = P3Process(f, "worker", {"task_id": str(task), "p4_demo": twenty}, "never")
    try:
        child.until("after_ready")
        request = DecisionInput.model_validate_json(
            json.dumps(payload(f, task, "approve_with_assumptions" if twenty else "approve"))
        )
        with connect(f.config.database) as db:
            card = db.execute(
                "SELECT id FROM business.outbox WHERE aggregate_id=%s", (request.approval_id,)
            ).fetchone()
            assert card
            db.execute(
                """INSERT INTO business.p4_card_bindings(approval_id,outbox_id,chat_id,
                message_id,source_mode) VALUES(%s,%s,%s,'synthetic-card','offline_fake')""",
                (request.approval_id, card["id"], incoming.chat_id),
            )
        gateway.card(
            BusinessCard(
                "synthetic-card-event",
                incoming.identity,
                incoming.chat_id,
                "synthetic-card",
                request,
            )
        )
        wait_state(f, task, "completed")
        with connect(f.config.database) as db:
            row = db.execute(
                "SELECT id FROM business.replenishment_items WHERE task_id=%s", (task,)
            ).fetchone()
            assert row
            return task, row["id"]
    finally:
        if child.process.poll() is None:
            child.stop_clean()  # 实际SIGTERM/wait/reap；不以session锁释放猜OS死亡。


def gate(f: P3Fixture, task: UUID, **changes: Any) -> DeliveryGate:
    return DeliveryGate(
        **dict(
            organization_id=f.actor.organization_id,
            shop_id=f.inventory.data.shop,
            task_ids=frozenset({task}),
            target_key="test",
            expires_at=datetime.now(UTC) + timedelta(minutes=3),
            enabled=True,
            **changes,
        )
    )


def resolve(f: P3Fixture, item: UUID) -> None:
    from uuid import uuid4

    result = f.client.post(
        f"/api/v1/items/{item}/resolve",
        headers=f.headers(),
        json={
            "schema_version": "p3-web-v1",
            "request_key": str(uuid4()),
            "expected_version": 1,
            "action": "complete",
            "reason": "内部跟进完成，不代表采购或入库",
        },
    )
    assert result.status_code == 200


def due(f: P3Fixture) -> None:
    with connect(f.config.database) as db:
        # 仅owned测试新delivery的可变排队时间；原key/snapshot/firstAttempt/unknown不改。
        db.execute(
            "UPDATE business.p4_base_deliveries SET next_attempt_at=clock_timestamp() "
            "WHERE status IN ('pending','unknown')"
        )


def test_unknown_v1_then_t6_v2_original_readback_anchor_and_same_row_update(
    fixture: P3Fixture,
) -> None:
    f = fixture
    task, item = executed_feishu(f)
    fake = MemoryRecords(reply=ApiReply(None, None))

    async def run() -> None:
        session = WorkerSession(f.config.database, f.actor.organization_id)
        await session.start()
        try:
            store = BaseDeliveryStore(
                session, BusinessBaseAdapter(fake, {"test": ("fake", "fake")}), gate(f, task)
            )
            assert await store.dispatch_one() == "unknown"
            resolve(f, item)
            due(f)
            assert await store.dispatch_one() == "verified"  # 只原v1完整读回，目标仍v2。
            with connect(f.config.database) as db:
                row = db.execute(
                    "SELECT version,status FROM business.p4_base_deliveries ORDER BY version"
                ).fetchall()
                assert row == [
                    {"version": 1, "status": "verified"},
                    {"version": 2, "status": "pending"},
                ]
            fake.reply = None
            assert await store.dispatch_one() == "verified"
            assert await store.dispatch_one() == "idle"
        finally:
            await session.close(clean=True)

    asyncio.run(run())
    assert [c[0] for c in fake.calls] == ["query", "create", "query", "query", "update", "query"]
    assert len(fake.rows) == 1 and fake.rows[0]["fields"]["SyncVersion"] == 2
    with connect(f.config.database) as db:
        rows = db.execute(
            "SELECT version,status,external_id,observed_version,complete_unique_verified "
            "FROM business.p4_base_deliveries ORDER BY version"
        ).fetchall()
        assert [r["observed_version"] for r in rows] == [1, 2]
        assert all(r["status"] == "verified" and r["complete_unique_verified"] for r in rows)
        original = db.execute(
            "SELECT provider_idempotency_key FROM business.outbox WHERE aggregate_id=%s "
            "AND aggregate_version=1",
            (item,),
        ).fetchone()
        assert original and fake.calls[1][1] == str(original["provider_idempotency_key"])
        assert db.execute("SELECT count(*) AS n FROM business.p4_base_links").fetchone() == {"n": 1}
        assert db.execute(
            "SELECT status,version FROM business.replenishment_items WHERE id=%s", (item,)
        ).fetchone() == {"status": "completed", "version": 2}
        assert db.execute(
            "SELECT count(*) AS n FROM business.outbox "
            "WHERE sender_enabled OR external_id IS NOT NULL"
        ).fetchone() == {"n": 0}


def test_terminal_before_first_projection_restores_v1_creation_fields_then_v2(
    fixture: P3Fixture,
) -> None:
    f = fixture
    task, item = executed_feishu(f)
    resolve(f, item)
    fake = MemoryRecords()

    async def run() -> None:
        session = WorkerSession(f.config.database, f.actor.organization_id)
        await session.start()
        try:
            store = BaseDeliveryStore(
                session, BusinessBaseAdapter(fake, {"test": ("fake", "fake")}), gate(f, task)
            )
            assert await store.dispatch_one() == "verified"
            assert fake.rows[0]["fields"]["BusinessStatus"] == "open"
            assert fake.rows[0]["fields"]["ResolutionReason"] is None
            assert await store.dispatch_one() == "verified"
            assert fake.rows[0]["fields"]["BusinessStatus"] == "completed"
        finally:
            await session.close(clean=True)

    asyncio.run(run())
    assert [c[0] for c in fake.calls].count("create") == 1
    assert [c[0] for c in fake.calls].count("update") == 1


def test_current_permission_revoked_prevents_base_transport_and_business_rollback(
    fixture: P3Fixture,
) -> None:
    f = fixture
    task, item = executed_feishu(f)
    with connect(f.inventory.owner) as db:
        db.execute(
            "UPDATE business.principal_role_shop_grants SET enabled=false "
            "WHERE principal_id=%s AND role='approver'",
            (f.actor.principal_id,),
        )
    fake = MemoryRecords()

    async def run() -> None:
        session = WorkerSession(f.config.database, f.actor.organization_id)
        await session.start()
        try:
            store = BaseDeliveryStore(
                session, BusinessBaseAdapter(fake, {"test": ("fake", "fake")}), gate(f, task)
            )
            assert await store.dispatch_one() == "idle"
        finally:
            await session.close(clean=True)

    asyncio.run(run())
    assert fake.calls == []
    with connect(f.config.database) as db:
        assert db.execute(
            "SELECT status FROM business.replenishment_items WHERE id=%s", (item,)
        ).fetchone() == {"status": "open"}
        assert db.execute(
            "SELECT status,last_error FROM business.p4_base_deliveries"
        ).fetchone() == {"status": "fatal", "last_error": "CURRENT_PERMISSION_DENIED"}


def test_unknown_reconcile_missing_three_attempts_never_second_create_and_v2_waits(
    fixture: P3Fixture,
) -> None:
    f = fixture
    task, item = executed_feishu(f)
    fake = MemoryRecords(reply=ApiReply(503, 9999999))

    async def run() -> None:
        session = WorkerSession(f.config.database, f.actor.organization_id)
        await session.start()
        try:
            store = BaseDeliveryStore(
                session, BusinessBaseAdapter(fake, {"test": ("fake", "fake")}), gate(f, task)
            )
            assert await store.dispatch_one() == "unknown"
            resolve(f, item)
            for _ in range(2):
                due(f)
                assert await store.dispatch_one() == "unknown"
            assert await store.dispatch_one() == "idle"
            with connect(f.config.database) as db:
                d = db.execute(
                    "SELECT * FROM business.p4_base_deliveries WHERE version=1"
                ).fetchone()
                assert d and d["status"] == "unknown" and d["attempts"] == 3 and d["unknown_since"]
                assert db.execute(
                    "SELECT count(*) AS n FROM business.p4_base_links"
                ).fetchone() == {"n": 0}
            for statement in (
                "UPDATE business.p4_base_deliveries SET status='pending' WHERE version=1",
                "UPDATE business.p4_base_deliveries SET client_token=gen_random_uuid() "
                "WHERE version=1",
                "UPDATE business.p4_base_deliveries SET unknown_since=NULL WHERE version=1",
            ):
                with connect(f.config.database) as db, pytest.raises(CheckViolation):
                    db.execute(statement)
        finally:
            await session.close(clean=True)

    asyncio.run(run())
    assert [c[0] for c in fake.calls] == ["query", "create", "query", "query"]


def test_same_twenty_factory_p2_t2_t4_and_full_base_fake_readback(fixture: P3Fixture) -> None:
    f = fixture
    task, _ = executed_feishu(f, twenty=True)

    class MultiRecords(MemoryRecords):
        async def create(
            self,
            app_token: str,
            table_id: str,
            token: str,
            projection: Any,
            *,
            deadline: float | None = None,
        ) -> ApiReply:
            identifier = "synthetic-" + projection.item_id.hex
            self.calls.append(("create", token, deadline))
            self.rows.append(row(projection, identifier))
            return ApiReply(200, 0, {"record": {"record_id": identifier}})

    fake = MultiRecords()

    async def run() -> None:
        session = WorkerSession(f.config.database, f.actor.organization_id)
        await session.start()
        try:
            store = BaseDeliveryStore(
                session, BusinessBaseAdapter(fake, {"test": ("fake", "fake")}), gate(f, task)
            )
            for _ in range(20):
                assert await store.dispatch_one() == "verified"
            assert await store.dispatch_one() == "idle"
        finally:
            await session.close(clean=True)

    asyncio.run(run())
    assert len(fake.rows) == 20
    assert sum(r["fields"]["Quantity"] for r in fake.rows) == 2000
    assert all(r["fields"]["SyncVersion"] == 1 for r in fake.rows)
    assert [c[0] for c in fake.calls].count("create") == 20
    assert [c[0] for c in fake.calls].count("query") == 40
    with connect(f.config.database) as db:
        plan = db.execute(
            "SELECT content FROM business.replenishment_plans WHERE task_id=%s", (task,)
        ).fetchone()
        assert (
            plan and plan["content"]["item_count"] == 20 and plan["content"]["total_units"] == 2000
        )
        assert len(plan["content"]["required_assumptions"]) == 1
        assert db.execute(
            "SELECT count(*) AS n FROM business.executions WHERE task_id=%s", (task,)
        ).fetchone() == {"n": 1}
        assert db.execute(
            "SELECT count(*) AS n FROM business.p4_base_links WHERE item_id IN "
            "(SELECT id FROM business.replenishment_items WHERE task_id=%s)",
            (task,),
        ).fetchone() == {"n": 20}
