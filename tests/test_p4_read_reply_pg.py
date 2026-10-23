"""自有新 PG 的两种持久回复/单 lease/Fake SDK；平台与 provider 调用 0。"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from commerceops.adapters.feishu.contracts import ProbePolicy
from commerceops.application.feishu_business.clarification import NoticeResult
from commerceops.application.feishu_business.im_delivery import BusinessMessage
from commerceops.application.feishu_business.read_reply import READ_REPLY_CAPS
from commerceops.application.feishu_business.sdk_window import SDKScope, SDKWindow
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_read_reply import ReadReplyDeliveryStore
from commerceops.infrastructure.feishu_sdk_ledger import PersistentSDKLedger
from commerceops.infrastructure.worker_lock import WorkerSession
from psycopg.errors import CheckViolation, FeatureNotSupported, InsufficientPrivilege

from tests.p3_support import P3Fixture, P3Process, run_graphs
from tests.test_p3_pg import fixture as fixture
from tests.test_p4_gateway_pg import message, service
from tests.test_p4_template_results_pg import cached, counts

pytestmark = pytest.mark.integration


def prepared(f: P3Fixture, kind: str = "explain_report") -> dict[str, Any]:
    s = service(f)
    incoming = message(f)
    task = UUID(s.message(incoming)["task_id"])
    child = P3Process(f, "worker", {"task_id": str(task)}, "never")
    try:
        child.until("after_ready")
        child.stop_clean()
    finally:
        if child.process.poll() is None:
            child.kill_reap()
    original = cached(f, task)
    text = (
        f"查询任务{task}进度"
        if kind == "task_status"
        else f"解释任务{task}的报告{original['report_id']}"
    )
    receipt = s.message(
        replace(
            incoming, event_id="read-" + uuid4().hex, message_id="read-" + uuid4().hex, text=text
        )
    )
    with connect(f.config.database) as db:
        row = db.execute(
            "SELECT * FROM business.p4_read_replies WHERE id=%s", (UUID(receipt["reply_id"]),)
        ).fetchone()
    assert row and row["status"] == "pending" and row["attempts"] == 0
    assert receipt["as_of"] == row["payload"]["as_of"]
    return row


class FakeSender:
    def __init__(self, f: P3Fixture, ledger: PersistentSDKLedger, outcome: str = "sent"):
        self.f, self.ledger, self.outcome = f, ledger, outcome
        self.calls: list[UUID] = []

    async def send_message(self, request: BusinessMessage) -> NoticeResult:
        async def wire() -> Any:
            with connect(self.f.config.database) as db:
                carrier = db.execute(
                    "SELECT status,attempts FROM business.p4_read_replies WHERE id=%s",
                    (request.outbox_id,),
                ).fetchone()
                call = db.execute(
                    "SELECT status FROM business.p4_sdk_calls WHERE subject_id=%s",
                    (request.outbox_id,),
                ).fetchone()
            assert carrier == {"status": "sending", "attempts": 1} and call == {"status": "started"}
            self.calls.append(request.provider_uuid)
            if self.outcome == "unknown":
                raise RuntimeError("controlled_after_send_unknown")
            if self.outcome == "cancel":
                raise asyncio.CancelledError()
            return SimpleNamespace(raw=SimpleNamespace(status_code=200), code=0)

        await self.ledger.invoke("im.v1.message.create", wire)
        return NoticeResult(outcome="sent", code="IM_ACK", message_id="synthetic-actual-ack")


def policy(f: P3Fixture) -> ProbePolicy:
    return ProbePolicy(
        f.inventory.data.app,
        f.inventory.data.tenant,
        "synthetic-bot",
        frozenset({"p4-synthetic-user"}),
        frozenset(),
    )


async def delivery(
    f: P3Fixture, row: dict[str, Any], outcome: str = "sent", enabled: bool = True
) -> tuple[WorkerSession, ReadReplyDeliveryStore, FakeSender]:
    session = WorkerSession(f.config.database, f.actor.organization_id)
    await session.start()
    window = SDKWindow(
        uuid4(),
        session.organization,
        f.inventory.data.shop,
        datetime.now(UTC) + timedelta(minutes=2),
        READ_REPLY_CAPS,
        enabled=enabled,
    )
    ledger = PersistentSDKLedger(session, window)
    sender = FakeSender(f, ledger, outcome)
    store = ReadReplyDeliveryStore(
        session, f.store, policy(f), sender, ledger, row["id"], row["task_id"]
    )
    return session, store, sender


@pytest.mark.parametrize("kind", ["task_status", "explain_report"])
def test_two_kind_sender_started_precommit_one_uuid_ten_replay_zero_business(
    fixture: P3Fixture,
    kind: str,
) -> None:
    f = fixture
    row = prepared(f, kind)
    before = counts(f)

    async def run() -> None:
        session, store, sender = await delivery(f, row)
        try:
            assert await store.dispatch_one() == "sent"
            for _ in range(10):
                assert await store.dispatch_one() == "idle"
            assert sender.calls == [row["provider_uuid"]]
        finally:
            await session.close(clean=True)

    asyncio.run(run())
    assert counts(f) == before
    with connect(f.config.database) as db:
        saved = db.execute(
            "SELECT * FROM business.p4_read_replies WHERE id=%s", (row["id"],)
        ).fetchone()
        assert saved and saved["status"] == "sent" and saved["payload"] == row["payload"]
        assert saved["as_of"] == row["as_of"] and saved["attempts"] == 1


def test_unknown_original_uuid_terminal_no_new_window_retry(fixture: P3Fixture) -> None:
    f = fixture
    row = prepared(f)
    before = counts(f)

    async def run() -> None:
        session, store, sender = await delivery(f, row, "unknown")
        try:
            assert await store.dispatch_one() == "unknown"
            assert await store.dispatch_one() == "idle" and sender.calls == [row["provider_uuid"]]
            # 即使换一个允许新 window 的 ledger，原 carrier unknown 仍不能 claim。
            store.ledger = PersistentSDKLedger(
                session, replace(store.ledger.window, window_id=uuid4())
            )
            assert await store.dispatch_one() == "idle"
        finally:
            await session.close(clean=True)

    asyncio.run(run())
    assert counts(f) == before
    with connect(f.config.database) as db:
        assert db.execute(
            "SELECT status FROM business.p4_read_replies WHERE id=%s", (row["id"],)
        ).fetchone() == {"status": "unknown"}


@pytest.mark.parametrize("change", ["role", "identity", "shop", "group", "version"])
def test_current_revoke_cross_policy_and_stale_zero_sdk(fixture: P3Fixture, change: str) -> None:
    f = fixture
    row = prepared(f)
    before = counts(f)

    async def run() -> None:
        session, store, sender = await delivery(f, row)
        try:
            with connect(f.inventory.owner) as db:
                if change == "role":
                    db.execute(
                        "UPDATE business.principal_role_shop_grants SET enabled=false "
                        "WHERE principal_id=%s",
                        (f.inventory.data.principal,),
                    )
                elif change == "identity":
                    db.execute(
                        "UPDATE business.identities SET external_subject='remapped' WHERE id=%s",
                        (row["identity_id"],),
                    )
                elif change == "version":
                    db.execute(
                        "UPDATE business.business_tasks SET version=version+1 WHERE id=%s",
                        (row["task_id"],),
                    )
            if change == "shop":
                store.ledger = PersistentSDKLedger(
                    session, replace(store.ledger.window, shop_id=uuid4())
                )
            if change == "group":
                store.policy = replace(store.policy, app_id="untrusted-app")
            assert await store.dispatch_one() == "denied" and sender.calls == []
            with connect(f.config.database) as db:
                assert db.execute("SELECT count(*) AS n FROM business.p4_sdk_calls").fetchone() == {
                    "n": 0
                }
        finally:
            await session.close(clean=True)

    asyncio.run(run())
    assert counts(f) == before


def test_concurrent_claim_only_one_send_and_disabled_window_zero(fixture: P3Fixture) -> None:
    f = fixture
    row = prepared(f)
    before = counts(f)

    async def run() -> None:
        session, store, sender = await delivery(f, row, enabled=False)
        try:
            assert await store.dispatch_one() == "disabled" and sender.calls == []
            store.ledger.window = replace(store.ledger.window, enabled=True)
            result = await asyncio.gather(store.dispatch_one(), store.dispatch_one())
            assert sorted(result) == ["idle", "sent"] and sender.calls == [row["provider_uuid"]]
        finally:
            await session.close(clean=True)

    asyncio.run(run())
    assert counts(f) == before


def test_read_inbox_concurrent_same_event_fixed_asof_uuid_and_single_carrier(
    fixture: P3Fixture,
) -> None:
    f = fixture
    s = service(f)
    incoming = message(f)
    task = UUID(s.message(incoming)["task_id"])
    asyncio.run(run_graphs(f, task))
    before = counts(f)
    request = replace(
        incoming,
        event_id="read-" + uuid4().hex,
        message_id="read-" + uuid4().hex,
        text=f"查询任务{task}进度",
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(s.message, [request, request]))
    assert (
        replies[0]["reply_id"] == replies[1]["reply_id"]
        and replies[0]["as_of"] == replies[1]["as_of"]
    )
    assert counts(f) == before
    with connect(f.config.database) as db:
        assert db.execute("SELECT count(*) AS n FROM business.p4_read_replies").fetchone() == {
            "n": 1
        }


def test_carrier_identity_no_mutation_delete_truncate_and_scope_no_forgery(
    fixture: P3Fixture,
) -> None:
    f = fixture
    row = prepared(f)
    with connect(f.inventory.owner) as db:
        for query in (
            "UPDATE business.p4_read_replies SET as_of=clock_timestamp()",
            "UPDATE business.p4_read_replies SET provider_uuid=gen_random_uuid()",
            "UPDATE business.p4_read_replies SET payload_hash=repeat('0',64)",
            "DELETE FROM business.p4_read_replies",
            "TRUNCATE business.p4_read_replies CASCADE",
        ):
            with pytest.raises(CheckViolation), db.transaction():
                db.execute(query)
        revision = db.execute("SELECT version_num FROM business.alembic_version").fetchone()
        related = db.execute("SELECT to_regclass('business.p4_history_messages') AS t").fetchone()
        if revision == {"version_num": "0017_p4_verified_history"}:
            assert related and related["t"] is not None
            before = db.execute(
                """SELECT row_to_json(r)::text AS body
                    FROM business.p4_read_replies r ORDER BY id"""
            ).fetchall()
            history_before = db.execute(
                """SELECT row_to_json(m)::text AS body
                    FROM business.p4_history_messages m ORDER BY id"""
            ).fetchall()
            with pytest.raises(FeatureNotSupported) as refused, db.transaction():
                db.execute("TRUNCATE business.p4_read_replies")
            assert refused.value.sqlstate == "0A000"
            assert (
                db.execute(
                    """SELECT row_to_json(r)::text AS body
                    FROM business.p4_read_replies r ORDER BY id"""
                ).fetchall()
                == before
            )
            assert (
                db.execute(
                    """SELECT row_to_json(m)::text AS body
                    FROM business.p4_history_messages m ORDER BY id"""
                ).fetchall()
                == history_before
            )
        else:
            assert revision in (
                {"version_num": "0015_p4_read_replies"},
                {"version_num": "0016_p4_clarification_requests"},
            )
            with pytest.raises(CheckViolation), db.transaction():
                db.execute("TRUNCATE business.p4_read_replies")
    with connect(f.config.database) as db:
        for query in (
            "UPDATE business.p4_read_replies SET payload=payload",
            "DELETE FROM business.p4_read_replies",
            "TRUNCATE business.p4_read_replies",
        ):
            with pytest.raises(InsufficientPrivilege), db.transaction():
                db.execute(query)

    async def run() -> None:
        session, store, sender = await delivery(f, row)

        async def forbidden() -> Any:
            raise AssertionError("unauthorized SDK")

        try:
            for subject, task in (
                (row["id"], row["task_id"]),
                (uuid4(), row["task_id"]),
                (row["id"], uuid4()),
            ):
                with store.ledger.scope(SDKScope(subject, task, "read_reply")):
                    with pytest.raises(PermissionError):
                        await store.ledger.invoke("im.v1.message.create", forbidden)
            assert sender.calls == []
        finally:
            await session.close(clean=True)

    asyncio.run(run())


@pytest.mark.parametrize(
    "point,calls", [("after_read_claim", 0), ("after_read_started", 1), ("after_read_sdk", 1)]
)
def test_actual_process_crash_original_carrier_unknown_no_retry(
    fixture: P3Fixture,
    point: str,
    calls: int,
) -> None:
    from commerceops.infrastructure.worker_lock import confirm_termination

    f = fixture
    row = prepared(f)
    before = counts(f)
    child = P3Process(
        f,
        "worker",
        {"read_reply_stub": True, "reply_id": str(row["id"]), "task_id": str(row["task_id"])},
        point,
    )
    try:
        owner = child.until("started")["owner"]
        child.until(point)
        with connect(f.config.database) as db:
            assert db.execute(
                "SELECT status,attempts FROM business.p4_read_replies WHERE id=%s", (row["id"],)
            ).fetchone() == {"status": "sending", "attempts": 1}
            assert db.execute(
                "SELECT count(*) AS n FROM business.p4_sdk_calls WHERE subject_id=%s", (row["id"],)
            ).fetchone() == {"n": calls}
        child.kill_reap()
        asyncio.run(
            confirm_termination(f.config.database, owner, "owned read reply child SIGKILL/reaped")
        )

        async def recover() -> None:
            session, store, sender = await delivery(f, row)
            try:
                await store.recover_unknown()
                assert await store.dispatch_one() == "idle" and sender.calls == []
            finally:
                await session.close(clean=True)

        asyncio.run(recover())
        with connect(f.config.database) as db:
            saved = db.execute(
                "SELECT * FROM business.p4_read_replies WHERE id=%s", (row["id"],)
            ).fetchone()
            assert (
                saved
                and saved["status"] == "unknown"
                and saved["provider_uuid"] == row["provider_uuid"]
            )
            assert saved["payload"] == row["payload"] and saved["as_of"] == row["as_of"]
        assert counts(f) == before
    finally:
        if child.process.poll() is None:
            child.kill_reap()


def test_caps_cross_window_second_method_and_expired_or_lost_lease_zero(
    fixture: P3Fixture,
) -> None:
    from commerceops.infrastructure.worker_lock import LockLost

    f = fixture
    row = prepared(f)
    before = counts(f)

    async def run() -> None:
        session, store, sender = await delivery(f, row)
        try:
            original_send = sender.send_message

            async def one(request: BusinessMessage) -> NoticeResult:
                result = await original_send(request)
                replacement = PersistentSDKLedger(
                    session, replace(store.ledger.window, window_id=uuid4())
                )
                with replacement.scope(SDKScope(row["id"], row["task_id"], "read_reply")):
                    with pytest.raises(PermissionError):
                        await replacement.invoke(
                            "im.v1.message.create", lambda: pytest.fail("second method forbidden")
                        )
                return result

            sender.send_message = one  # type: ignore[method-assign]
            invalid = PersistentSDKLedger(
                session,
                replace(
                    store.ledger.window,
                    window_id=uuid4(),
                    caps={**READ_REPLY_CAPS, "im.v1.message.create": 2},
                ),
            )
            with invalid.scope(SDKScope(row["id"], row["task_id"], "read_reply")):
                with pytest.raises(PermissionError):
                    await invalid.invoke(
                        "im.v1.message.create", lambda: pytest.fail("cap mismatch")
                    )
            store.ledger.window = replace(
                store.ledger.window, expires_at=datetime.now(UTC) - timedelta(seconds=1)
            )
            assert await store.dispatch_one() == "disabled" and sender.calls == []
            store.ledger.window = replace(
                store.ledger.window, expires_at=datetime.now(UTC) + timedelta(minutes=2)
            )
            assert await store.dispatch_one() == "sent" and len(sender.calls) == 1
            await session.close(clean=True)
            with pytest.raises(LockLost):
                await store.dispatch_one()
            assert len(sender.calls) == 1
        finally:
            if session.active:
                await session.close(clean=True)

    asyncio.run(run())
    assert counts(f) == before


@pytest.mark.parametrize("unavailable", [False, True])
def test_historical_completed_missing_or_unavailable_fixed_not_ready_no_backfill(
    fixture: P3Fixture,
    monkeypatch: pytest.MonkeyPatch,
    unavailable: bool,
) -> None:
    from commerceops.application.replenishment.template_result import TemplateRenderError
    from commerceops.infrastructure import p3_template_results as templates

    f = fixture
    s = service(f, case="normal")
    incoming = message(f)
    if unavailable:

        async def fail(*args: Any, **kwargs: Any) -> Any:
            raise TemplateRenderError()

        monkeypatch.setattr(templates, "render", fail)
    else:
        # 模拟旧部署已完成任务没有模板：不修改/删除实际历史表或触发器。
        async def absent(*args: Any, **kwargs: Any) -> UUID:
            return uuid4()

        monkeypatch.setattr(templates, "freeze", absent)
    task = UUID(s.message(incoming)["task_id"])
    asyncio.run(run_graphs(f, task))
    before = counts(f)
    with connect(f.config.database) as db:
        source = db.execute(
            "SELECT source_report_id FROM business.p3_task_sources WHERE task_id=%s", (task,)
        ).fetchone()
    assert source
    request = replace(
        incoming,
        event_id="read-" + uuid4().hex,
        message_id="read-" + uuid4().hex,
        text=f"解释任务{task}的报告{source['source_report_id']}",
    )
    receipt = s.message(request)
    assert (
        receipt["facts"]["error"]["code"] == "NOT_READY" and receipt["reply_delivery"] == "pending"
    )
    for _ in range(10):
        assert s.message(request) == {**receipt, "duplicate": True}
    assert counts(f) == before
    with connect(f.config.database) as db:
        row = db.execute(
            "SELECT payload FROM business.p4_read_replies WHERE id=%s", (UUID(receipt["reply_id"]),)
        ).fetchone()
    assert (
        row and row["payload"]["read_code"] == "NOT_READY" and row["payload"]["explanation"] is None
    )


def test_late_fake_sender_deadline_never_marks_sent_or_retries(fixture: P3Fixture) -> None:
    f = fixture
    row = prepared(f)
    before = counts(f)

    async def run() -> None:
        session, store, sender = await delivery(f, row)

        async def late(request: BusinessMessage) -> NoticeResult:
            async def wire() -> Any:
                sender.calls.append(request.provider_uuid)
                await asyncio.sleep(1)
                return SimpleNamespace(raw=SimpleNamespace(status_code=200), code=0)

            await store.ledger.invoke("im.v1.message.create", wire)
            return NoticeResult(outcome="sent", code="IM_ACK", message_id="too-late-ack")

        store.sender = SimpleNamespace(send_message=late)
        store.ledger.window = replace(
            store.ledger.window, expires_at=datetime.now(UTC) + timedelta(milliseconds=150)
        )
        try:
            assert await store.dispatch_one() == "unknown" and len(sender.calls) == 1
            assert await store.dispatch_one() == "disabled" and len(sender.calls) == 1
            with connect(f.config.database) as db:
                saved = db.execute(
                    "SELECT status,message_id FROM business.p4_read_replies WHERE id=%s",
                    (row["id"],),
                ).fetchone()
                assert saved == {"status": "unknown", "message_id": None}
        finally:
            await session.close(clean=True)

    asyncio.run(run())
    assert counts(f) == before
