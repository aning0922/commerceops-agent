"""真实 PG + OS 进程；故障窗口用 barrier/数据库锁，没有随机 sleep。"""

import asyncio
import json
import os
import queue
import signal
import subprocess
import sys
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from commerceops.application.intake import TestInbound as Inbound
from commerceops.application.intake import TestIntakeService as Intake
from commerceops.application.intake import TrustedTestContext
from commerceops.entrypoints.database import grant_runtime, migrate
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.intake import PgTestIntakeStore
from commerceops.infrastructure.queue import JobQueue, OwnershipLost
from commerceops.infrastructure.repository import PersistenceConflict, TaskRepository, TaskScope
from commerceops.infrastructure.worker_lock import (
    TerminationRequired,
    WorkerBusy,
    WorkerSession,
    confirm_termination,
)
from psycopg import sql

from tests.pg_support import Seed, seed

pytestmark = pytest.mark.integration


@dataclass
class Fixture:
    owner: DatabaseSettings
    app: DatabaseSettings
    data: Seed

    def intake(self, *, event: Inbound | None = None, hook: Any = None) -> Any:
        return Intake(PgTestIntakeStore(self.app)).accept(
            TrustedTestContext(
                self.data.organization,
                self.data.shop,
                self.data.principal,
                self.data.conversation,
                "test",
            ),
            event or inbound(self.data),
            hook=hook,
        )


def inbound(data: Seed) -> Inbound:
    return Inbound(
        data.app,
        data.tenant,
        str(uuid4()),
        str(uuid4()),
        {"schema_version": 1, "intent": "technical_test"},
        "p103-technical-v1",
    )


@pytest.fixture
def fixture() -> Iterator[Fixture]:
    settings = DatabaseSettings()
    assert settings.runtime_password_file is not None
    name = "p103_" + uuid4().hex
    owner = settings.model_copy(update={"name": name})
    app = owner.model_copy(
        update={"user": "commerceops_app", "password_file": settings.runtime_password_file}
    )
    with psycopg.connect(**settings.kwargs(), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            migrate(owner)
            with connect(owner) as db:
                db.execute("CREATE SCHEMA checkpoints")
            grant_runtime(owner)
            with connect(app) as db:
                data = seed(db)
            yield Fixture(owner, app, data)
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def counts(f: Fixture) -> tuple[int, int, int, int]:
    values: list[int] = []
    with connect(f.app) as db:
        for name in ("inbox_events", "business_tasks", "jobs", "audit_events"):
            row = db.execute(
                sql.SQL("SELECT count(*) AS n FROM business.{}").format(sql.Identifier(name))
            ).fetchone()
            assert row is not None
            values.append(row["n"])
    return values[0], values[1], values[2], values[3]


@pytest.mark.parametrize("point", ["after_inbox", "after_task", "after_job", "before_commit"])
def test_t1_rollback_never_returns_success(fixture: Fixture, point: str) -> None:
    def fail(name: str) -> None:
        if name == point:
            raise RuntimeError("injected before commit")

    with pytest.raises(RuntimeError):
        fixture.intake(hook=fail)
    assert counts(fixture) == (0, 1, 0, 0)


def test_t1_commit_ack_loss_duplicate_and_semantic_conflict(fixture: Fixture) -> None:
    event = inbound(fixture.data)

    def lose_ack(name: str) -> None:
        if name == "after_commit":
            raise RuntimeError("controlled ACK loss")

    with pytest.raises(RuntimeError):
        fixture.intake(event=event, hook=lose_ack)
    receipt = fixture.intake(event=event)
    assert fixture.intake(event=event) == receipt
    assert fixture.intake(event=replace(event, event_id=str(uuid4()))) == receipt
    assert counts(fixture) == (1, 2, 1, 1)
    with pytest.raises(PersistenceConflict):
        fixture.intake(
            event=replace(event, normalized_request={"schema_version": 1, "changed": True})
        )
    assert counts(fixture) == (1, 2, 1, 1)
    with connect(fixture.app) as db:
        row = TaskRepository(db, TaskScope(fixture.data.organization, fixture.data.shop)).get(
            receipt.task_id
        )
        assert row and row["thread_id"] == str(receipt.task_id)
        assert row["workflow_version"] == "p103-technical-v1"


def test_t1_duplicate_barrier_and_visibility(fixture: Fixture) -> None:
    event = inbound(fixture.data)
    before_commit, release, duplicate_started = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )

    def hold(name: str) -> None:
        if name == "before_commit":
            before_commit.set()
            assert release.wait(10)

    def duplicate() -> Any:
        duplicate_started.set()
        return fixture.intake(event=event)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(fixture.intake, event=event, hook=hold)
        assert before_commit.wait(10)
        second = pool.submit(duplicate)
        assert duplicate_started.wait(10)
        # 在 T1 确定的 pre-commit barrier，其他连接看不到任何部分交付。
        assert counts(fixture) == (0, 1, 0, 0)
        assert not first.done()
        assert not second.done()
        release.set()
        assert first.result(10) == second.result(10)
    assert counts(fixture) == (1, 2, 1, 1)


def test_t1_current_identity_and_scope_rejected(fixture: Fixture) -> None:
    with connect(fixture.owner) as db:
        db.execute(
            "UPDATE business.principals SET enabled=false,auth_version=auth_version+1 WHERE id=%s",
            (fixture.data.principal,),
        )
    with pytest.raises(PersistenceConflict):
        fixture.intake()
    assert counts(fixture) == (0, 1, 0, 0)


def test_owner_lease_short_transactions_and_delay(fixture: Fixture) -> None:
    receipt = fixture.intake()

    async def scenario() -> None:
        session = WorkerSession(fixture.app, fixture.data.organization)
        await session.start()
        jobs = JobQueue(session)
        try:
            job = await jobs.claim()
            assert job and job.job_id == receipt.job_id and job.attempt == 1
            with pytest.raises(OwnershipLost):
                await jobs.done(replace(job, owner=str(uuid4())))
            with connect(fixture.owner) as db:
                # 领取已提交，不持有长事务/行锁；另一连接能立即锁住该行。
                db.execute(
                    "SELECT id FROM business.jobs WHERE id=%s FOR UPDATE NOWAIT", (job.job_id,)
                )
                row = db.execute(
                    "SELECT extract(epoch FROM lease_until-clock_timestamp()) AS seconds "
                    "FROM business.jobs WHERE id=%s",
                    (job.job_id,),
                ).fetchone()
                assert row and 50 < row["seconds"] <= 60
            await jobs.renew(job)
            await jobs.defer(job, 3600)
            assert await jobs.claim() is None
            with pytest.raises(OwnershipLost):
                await jobs.done(job)
            with connect(fixture.owner) as db:
                db.execute(
                    "UPDATE business.jobs SET available_at=clock_timestamp() WHERE id=%s",
                    (job.job_id,),
                )
            retried = await jobs.claim()
            assert retried and retried.job_id == job.job_id and retried.attempt == 2
            # 真实 DB 中 owner 已被篡改时，同一个内存 request 也必须拒绝。
            with connect(fixture.owner) as db:
                db.execute(
                    "UPDATE business.jobs SET lease_owner=%s WHERE id=%s",
                    (str(uuid4()), job.job_id),
                )
            with pytest.raises(OwnershipLost):
                await jobs.renew(retried)
            with connect(fixture.owner) as db:
                db.execute(
                    "UPDATE business.jobs SET lease_owner=%s WHERE id=%s",
                    (session.owner, job.job_id),
                )
            await jobs.done(retried)
        finally:
            await session.close(clean=True)

    asyncio.run(scenario())


class Process:
    def __init__(self, fixture: Fixture, *, hold_after_stop: bool = False):
        environment = os.environ.copy()
        s = fixture.app
        environment.update(
            COMMERCEOPS_DB_HOST=s.host,
            COMMERCEOPS_DB_PORT=str(s.port),
            COMMERCEOPS_DB_NAME=s.name,
            COMMERCEOPS_DB_USER=s.user,
            COMMERCEOPS_DB_PASSWORD_FILE=str(s.password_file),
        )
        if hold_after_stop:
            environment["TEST_HOLD_AFTER_STOP"] = "1"
        self.process = subprocess.Popen(
            [sys.executable, "-m", "tests.worker_process", str(fixture.data.organization)],
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self.events: queue.Queue[dict[str, Any]] = queue.Queue()
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self.events.put(json.loads(line))

    def event_any(self) -> dict[str, Any]:
        return self.events.get(timeout=15)

    def event(self, name: str) -> dict[str, Any]:
        event = self.event_any()
        assert event["event"] == name, event
        return event

    def send(self, command: str) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(command + "\n")
        self.process.stdin.flush()

    def wait(self) -> int:
        result = self.process.wait(timeout=15)
        self.thread.join(timeout=5)
        return result

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
            self.wait()
        for stream in (self.process.stdin, self.process.stdout):
            if stream is not None:
                stream.close()


def test_s01_two_os_process_startup_mutex(fixture: Fixture) -> None:
    fixture.intake()
    first, second = Process(fixture), None
    try:
        first.event("started")
        first.event("entered")
        second = Process(fixture)
        assert second.event("failed")["code"] == "WorkerBusy"
        assert second.wait() == 2
        with connect(fixture.app) as db:
            row = db.execute("SELECT attempts,status FROM business.jobs").fetchone()
            assert row == {"attempts": 1, "status": "running"}
        first.process.send_signal(signal.SIGTERM)
        first.event("cancelled")
        first.event("left")
        first.event("stopped")
        assert first.wait() == 0
    finally:
        first.close()
        if second is not None:
            second.close()


def test_s02_serial_kinds_interrupt_and_queue_restart(fixture: Fixture) -> None:
    receipts = [fixture.intake() for _ in range(3)]
    with connect(fixture.app) as db:
        for receipt, kind in zip(receipts, ("analyze", "resume", "recover"), strict=True):
            db.execute("UPDATE business.jobs SET kind=%s WHERE id=%s", (kind, receipt.job_id))
    first, restarted = Process(fixture), None
    try:
        first.event("started")
        seen = []
        kinds = []
        for command in ("interrupt", "release"):
            run = first.event("entered")
            seen.append(run["job"])
            kinds.append(run["kind"])
            assert run["active"] == run["maximum"] == 1
            assert run["thread"] == run["task"]
            first.send(command)
            assert first.event("left")["active"] == 0
        held = first.event("entered")
        assert set(kinds + [held["kind"]]) == {"analyze", "resume", "recover"}
        first.process.send_signal(signal.SIGTERM)
        first.event("cancelled")
        first.event("left")
        first.event("stopped")
        assert first.wait() == 0  # 明确 OS wait，之后才能启动恢复。
        restarted = Process(fixture)
        restarted.event("started")
        recovered = restarted.event("entered")
        assert recovered["job"] == held["job"] and recovered["attempt"] == 2
        assert recovered["maximum"] == 1
        restarted.send("release")
        restarted.event("left")
        # 不等随机 sleep：等待 DB 行 done 的确定事务 barrier 再停止。
        wait_done(fixture, len(receipts))
        restarted.process.send_signal(signal.SIGTERM)
        restarted.event("stopped")
        assert restarted.wait() == 0
        assert len(set(seen + [held["job"]])) == 3
    finally:
        first.close()
        if restarted is not None:
            restarted.close()


def wait_done(fixture: Fixture, count: int) -> None:
    # 有界条件轮询，只等待具体持久事务提交，不用于猜测故障竞态。
    import time

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with connect(fixture.app) as db:
            row = db.execute(
                "SELECT count(*) AS n FROM business.jobs WHERE status='done'"
            ).fetchone()
            if row and row["n"] == count:
                return
        threading.Event().wait(0.01)
    raise AssertionError("job completion commit barrier timed out")


@pytest.mark.parametrize("noncooperative", [False, True])
def test_s03_lock_loss_unconfirmed_blocks_then_confirmed_recovers(
    fixture: Fixture,
    noncooperative: bool,
) -> None:
    receipt = fixture.intake()
    first, blocked, recovered = Process(fixture), None, None
    try:
        started = first.event("started")
        first.event("entered")
        if noncooperative:
            first.send("hang-cancel")
            first.event("hanging")
        with connect(fixture.owner) as db:
            # 故障只注入本测试 Worker 专用连接，不终止未知 DB 会话。
            db.execute("SELECT pg_terminate_backend(%s)", (started["lock_pid"],))
        if noncooperative:
            first.event("cancel_ignored")
            # finally 可能再次 cancel；等最终硬退出事件。
            while first.event_any()["event"] != "unsafe_shutdown":
                pass
            assert first.wait() == 75
        else:
            first.event("cancelled")
            first.event("left")
            assert first.event("failed")["code"] == "LockLost"
            assert first.wait() == 2
        # 即使OS已wait，但持久确认未登记，且lease人为设为过期，仍禁止自动接管。
        with connect(fixture.owner) as db:
            db.execute("UPDATE business.jobs SET lease_until=clock_timestamp()-interval '1 hour'")
        blocked = Process(fixture)
        assert blocked.event("failed")["code"] == "TerminationRequired"
        assert blocked.wait() == 2
        with connect(fixture.app) as db:
            task = TaskRepository(db, TaskScope(fixture.data.organization, fixture.data.shop)).get(
                receipt.task_id
            )
            assert task and task["state"] == "needs_attention"
            row = db.execute("SELECT attempts,status FROM business.jobs").fetchone()
            assert row == {"attempts": 1, "status": "running"}
        asyncio.run(
            confirm_termination(fixture.app, started["owner"], "test supervisor OS wait completed")
        )
        # 确认提交后响应丢失重试也不追加重复审计。
        asyncio.run(
            confirm_termination(fixture.app, started["owner"], "test supervisor OS wait completed")
        )
        recovered = Process(fixture)
        recovered.event("started")
        run = recovered.event("entered")
        assert run["job"] == str(receipt.job_id) and run["attempt"] == 2
        recovered.send("release")
        recovered.event("left")
        wait_done(fixture, 1)
        recovered.process.send_signal(signal.SIGTERM)
        recovered.event("stopped")
        assert recovered.wait() == 0
    finally:
        first.close()
        if blocked is not None:
            blocked.close()
        if recovered is not None:
            recovered.close()


def test_confirm_termination_refuses_held_lock_and_unrecognized_owner(fixture: Fixture) -> None:
    async def scenario() -> None:
        session = WorkerSession(fixture.app, fixture.data.organization)
        await session.start()
        try:
            with pytest.raises(WorkerBusy):
                await confirm_termination(fixture.app, session.owner, "invalid while running")
        finally:
            await session.close(clean=True)
        with pytest.raises(TerminationRequired):
            await confirm_termination(fixture.app, str(uuid4()), "not a known process")

    asyncio.run(scenario())


def test_s03_old_os_process_alive_blocks_without_lease_takeover(fixture: Fixture) -> None:
    receipt = fixture.intake()
    old, blocked = Process(fixture), None
    try:
        started = old.event("started")
        old.event("entered")
        os.kill(old.process.pid, signal.SIGSTOP)
        # OS 停止状态的同步 barrier：旧进程确定仍活着，无法响应取消。
        pid, status = os.waitpid(old.process.pid, os.WUNTRACED)
        assert pid == old.process.pid and os.WIFSTOPPED(status)
        with connect(fixture.owner) as db:
            db.execute("SELECT pg_terminate_backend(%s)", (started["lock_pid"],))
            db.execute("UPDATE business.jobs SET lease_until=clock_timestamp()-interval '1 hour'")
        with pytest.raises(TerminationRequired):
            asyncio.run(
                confirm_termination(fixture.app, started["owner"], "cannot confirm live PID")
            )
        blocked = Process(fixture)
        assert blocked.event("failed")["code"] == "TerminationRequired"
        assert blocked.wait() == 2
        assert old.process.poll() is None
        with connect(fixture.app) as db:
            row = db.execute(
                "SELECT status,attempts FROM business.jobs WHERE id=%s", (receipt.job_id,)
            ).fetchone()
            assert row == {"status": "running", "attempts": 1}
        os.kill(old.process.pid, signal.SIGCONT)
        old.event("cancelled")
        old.event("left")
        assert old.event("failed")["code"] == "LockLost"
        assert old.wait() == 2
        asyncio.run(
            confirm_termination(
                fixture.app, started["owner"], "test wait after stopped live process"
            )
        )
    finally:
        old.close()
        if blocked is not None:
            blocked.close()


def test_runner_retry_is_finite_and_releases_slot(fixture: Fixture) -> None:
    first = fixture.intake()
    process = Process(fixture)
    try:
        process.event("started")
        for attempt in range(1, 4):
            run = process.event("entered")
            assert run["job"] == str(first.job_id) and run["attempt"] == attempt
            process.send("retry")
            process.event("left")
        # 新入站还可排队，证明 dead/retry 不占执行槽。
        second = fixture.intake()
        run = process.event("entered")
        assert run["job"] == str(second.job_id)
        process.send("release")
        process.event("left")
        wait_done(fixture, 1)
        process.process.send_signal(signal.SIGTERM)
        process.event("stopped")
        assert process.wait() == 0
        with connect(fixture.app) as db:
            row = db.execute(
                "SELECT status,attempts,last_error FROM business.jobs WHERE id=%s", (first.job_id,)
            ).fetchone()
            assert row == {"status": "dead", "attempts": 3, "last_error": "RUNNER_FAILED"}
    finally:
        process.close()


def test_unsupported_workflow_never_runs_as_new_graph(fixture: Fixture) -> None:
    bad = fixture.intake(
        event=replace(inbound(fixture.data), workflow_version="old-unsupported-v0")
    )
    good = fixture.intake()
    process = Process(fixture)
    try:
        process.event("started")
        run = process.event("entered")
        assert run["job"] == str(good.job_id)
        process.send("release")
        process.event("left")
        wait_done(fixture, 1)
        process.process.send_signal(signal.SIGTERM)
        process.event("stopped")
        assert process.wait() == 0
        with connect(fixture.app) as db:
            row = db.execute(
                "SELECT status,last_error FROM business.jobs WHERE id=%s", (bad.job_id,)
            ).fetchone()
            assert row == {"status": "dead", "last_error": "WORKFLOW_VERSION_UNSUPPORTED"}
            row = db.execute(
                "SELECT workflow_version FROM business.business_tasks WHERE id=%s", (bad.task_id,)
            ).fetchone()
            assert row and row["workflow_version"] == "old-unsupported-v0"
    finally:
        process.close()


def test_t1_two_existing_delivery_keys_cannot_be_spliced(fixture: Fixture) -> None:
    a, b = inbound(fixture.data), inbound(fixture.data)
    fixture.intake(event=a)
    fixture.intake(event=b)
    with pytest.raises(PersistenceConflict):
        fixture.intake(event=replace(a, message_id=b.message_id))
    assert counts(fixture) == (2, 3, 2, 2)


def test_running_job_without_process_receipt_never_auto_recovers(fixture: Fixture) -> None:
    receipt = fixture.intake()
    with connect(fixture.owner) as db:
        db.execute(
            """UPDATE business.jobs SET status='running',lease_owner=%s,
            lease_until=clock_timestamp()-interval '1 hour' WHERE id=%s""",
            (str(uuid4()), receipt.job_id),
        )

    async def scenario() -> None:
        session = WorkerSession(fixture.app, fixture.data.organization)
        with pytest.raises(TerminationRequired):
            await session.start()

    asyncio.run(scenario())
    with connect(fixture.app) as db:
        row = db.execute(
            "SELECT state FROM business.business_tasks WHERE id=%s", (receipt.task_id,)
        ).fetchone()
        assert row and row["state"] == "needs_attention"
        row = db.execute(
            "SELECT attempts,status FROM business.jobs WHERE id=%s", (receipt.job_id,)
        ).fetchone()
        assert row == {"attempts": 0, "status": "running"}


def test_clean_stop_receipt_alone_does_not_prove_os_exit(fixture: Fixture) -> None:
    receipt = fixture.intake()
    old, blocked, restarted = Process(fixture, hold_after_stop=True), None, None
    try:
        old.event("started")
        old.event("entered")
        old.process.send_signal(signal.SIGTERM)
        old.event("cancelled")
        old.event("left")
        old.event("stopped")
        old.event("awaiting_exit")
        assert old.process.poll() is None
        blocked = Process(fixture)
        assert blocked.event("failed")["code"] == "TerminationRequired"
        assert blocked.wait() == 2
        old.send("exit")
        assert old.wait() == 0
        restarted = Process(fixture)
        restarted.event("started")
        run = restarted.event("entered")
        assert run["job"] == str(receipt.job_id) and run["attempt"] == 2
        restarted.send("release")
        restarted.event("left")
        wait_done(fixture, 1)
        restarted.process.send_signal(signal.SIGTERM)
        restarted.event("stopped")
        assert restarted.wait() == 0
    finally:
        old.close()
        if blocked is not None:
            blocked.close()
        if restarted is not None:
            restarted.close()
