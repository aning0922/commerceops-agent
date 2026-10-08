"""G2：真实 PG、官方 saver、真实 Graph 与 OS 死亡/barrier；模拟审批。"""

import asyncio
import signal
import threading
import time
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from langchain_core.runnables import RunnableConfig
from psycopg import sql

from commerceops.infrastructure.checkpoint import checkpointer
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.worker_lock import confirm_termination
from tests.checkpoint_support import Fixture, Process, initialize

pytestmark = pytest.mark.integration


@pytest.fixture
def fixture() -> Iterator[Fixture]:
    settings = DatabaseSettings()
    name = "p104_" + uuid4().hex
    owner = settings.model_copy(update={"name": name})
    with psycopg.connect(**settings.kwargs(),autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            yield initialize(owner)
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def saved(f: Fixture, task: UUID) -> Any:
    async def read() -> Any:
        async with checkpointer(f.app) as saver:
            config: RunnableConfig = {"configurable":{"thread_id":str(task)}}
            return await saver.aget_tuple(config)
    return asyncio.run(read())


def done(f: Fixture, job: UUID) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with connect(f.app) as db:
            row = db.execute("SELECT status FROM business.jobs WHERE id=%s",(job,)).fetchone()
            if row and row["status"] == "done":
                return
            assert row and row["status"] != "dead",row
        threading.Event().wait(0.01)
    raise AssertionError("job commit barrier timed out")


def stop(p: Process) -> None:
    p.process.send_signal(signal.SIGTERM)
    p.until("stopped")
    assert p.wait() == 0


def test_interrupt_slot_other_thread_and_cross_process_resume(fixture: Fixture) -> None:
    f = fixture
    first_job = f.enqueue(f.data)
    first = Process(f)
    second = None
    try:
        first.until("started")
        first.until("interrupt_persisted")
        done(f,first_job)
        checkpoint = saved(f,f.data.task)
        assert checkpoint and checkpoint.pending_writes
        assert any(channel == "__interrupt__" for _,channel,_ in checkpoint.pending_writes)
        assert f.rows(f.data.task)["status"] == "waiting"
        other = f.new_task()
        other_job = f.enqueue(other)
        assert first.until("invoke")["task"] == str(other.task)
        first.until("interrupt_persisted")
        done(f,other_job)
        assert f.rows(other.task)["result_ref"] is None
        stop(first)  # supervisor OS wait，随后同 namespace 的旧 PID 已消失。
        ref = f.decide(f.data)
        resume_job = f.enqueue(f.data,"resume",ref)
        second = Process(f)
        second.until("started")
        invoke = second.until("invoke")
        assert invoke["action"] == "resume" and invoke["thread"] == str(f.data.task)
        second.until("graph_finished")
        done(f,resume_job)
        # wait 节点重跑；prepare 未重跑；另一个 thread 仍等待，没有错误重建。
        assert sum(e["event"] == "wait_entered" for e in first.history) == 2
        assert sum(e["event"] == "wait_entered" for e in second.history) == 1
        assert not any(e["event"] == "prepare_entered" for e in second.history)
        assert all(e["active"] <= 1 for e in first.history+second.history if "active" in e)
        assert f.rows(f.data.task)["result_ref"]
        assert f.rows(other.task)["status"] == "waiting"
        stop(second)
    finally:
        first.close()
        if second:
            second.close()


def test_receipt_commit_before_checkpoint_sigkill_replays_one_receipt(fixture: Fixture) -> None:
    f = fixture
    initial = f.enqueue(f.data)
    first = Process(f,barriers="receipt_committed")
    blocked = restarted = None
    try:
        started = first.until("started")
        first.until("interrupt_persisted")
        done(f,initial)
        ref = f.decide(f.data)
        resume = f.enqueue(f.data,"resume",ref)
        committed = first.until("receipt_committed")
        first.until("barrier")
        assert f.rows(f.data.task)["result_ref"] == committed["result_ref"]
        before = saved(f,f.data.task)
        assert before and "result_ref" not in before.checkpoint["channel_values"]
        assert before.checkpoint["channel_values"]["decision_ref"] == ref
        first.process.kill()  # 本测试 PID；明确 receipt COMMIT 后、execute 输出前。
        assert first.wait() == -signal.SIGKILL
        blocked = Process(f)
        assert blocked.until("failed")["code"] == "TerminationRequired"
        assert blocked.wait() == 2
        asyncio.run(confirm_termination(f.app,started["owner"],"p104 SIGKILL supervisor wait"))
        restarted = Process(f)
        restarted.until("started")
        invoke = restarted.until("invoke")
        assert invoke["action"] == "continue" and invoke["thread"] == str(f.data.task)
        replayed = restarted.until("receipt_committed")
        assert replayed["result_ref"] == committed["result_ref"]
        restarted.until("graph_finished")
        done(f,resume)
        assert not any(e["event"] == "prepare_entered" for e in restarted.history)
        with connect(f.app) as db:
            row = db.execute("SELECT count(*) AS n FROM checkpoint_probe.receipts").fetchone()
            assert row and row["n"] == 1
            row = db.execute("SELECT attempts FROM business.jobs WHERE id=%s",(resume,)).fetchone()
            assert row and row["attempts"] == 2
        after = saved(f,f.data.task)
        assert after.checkpoint["channel_values"]["result_ref"] == committed["result_ref"]
        stop(restarted)
    finally:
        first.close()
        for p in (blocked,restarted):
            if p:
                p.close()


def test_real_graph_startup_mutex_lock_loss_cancels_no_escape(fixture: Fixture) -> None:
    f = fixture
    f.enqueue(f.data)
    first = Process(f,barriers="prepare_entered")
    second = blocked = None
    try:
        started = first.until("started")
        first.until("barrier")
        second = Process(f)
        assert second.until("failed")["code"] == "WorkerBusy"
        assert second.wait() == 2
        with connect(f.owner) as db:
            db.execute("SELECT pg_terminate_backend(%s)",(started["lock_pid"],))
        first.until("barrier_cancelled")
        first.until("runner_left")
        assert first.until("failed")["code"] == "LockLost"
        assert first.wait() == 2
        before = saved(f,f.data.task)
        with connect(f.owner) as db:
            db.execute("UPDATE business.jobs SET lease_until=clock_timestamp()-interval '1 hour'")
        blocked = Process(f)
        assert blocked.until("failed")["code"] == "TerminationRequired"
        assert blocked.wait() == 2
        assert saved(f,f.data.task).config == before.config
        with connect(f.app) as db:
            assert db.execute("SELECT count(*) AS n FROM checkpoint_probe.receipts").fetchone() == {"n":0}
        asyncio.run(confirm_termination(f.app,started["owner"],"p104 lock loss OS wait"))
    finally:
        first.close()
        for p in (second,blocked):
            if p:
                p.close()
