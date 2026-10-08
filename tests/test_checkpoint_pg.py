"""G2：真实 PG、官方 saver、真实 Graph 与 OS 死亡/barrier；模拟审批。"""

import asyncio
import json
import os
import signal
import threading
import time
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from commerceops.infrastructure.checkpoint import checkpointer
from commerceops.infrastructure.checkpoint_probe import ProbeStore
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.queue import JobQueue, OwnershipLost
from commerceops.infrastructure.repository import PersistenceConflict
from commerceops.infrastructure.worker_lock import (
    TerminationRequired,
    WorkerSession,
    confirm_termination,
)
from commerceops.workflows.checkpoint_probe import RETIRED_PROBE_VERSION
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import copy_checkpoint
from langgraph.checkpoint.base.id import uuid6
from psycopg import sql

from tests.checkpoint_support import Fixture, Process, initialize

pytestmark = pytest.mark.integration


def evidence(scenario: str, **values: Any) -> None:
    print(
        "G2 EVIDENCE: "
        + json.dumps(
            {
                "scenario": scenario,
                "source_mode": "postgres_technical",
                "model_mode": "not_used",
                "approval_mode": "simulated",
                **values,
            },
            sort_keys=True,
        )
    )


@pytest.fixture
def fixture() -> Iterator[Fixture]:
    settings = DatabaseSettings()
    name = "p104_" + uuid4().hex
    owner = settings.model_copy(update={"name": name})
    with psycopg.connect(**settings.kwargs(), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            yield initialize(owner)
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def saved(f: Fixture, task: UUID) -> Any:
    async def read() -> Any:
        async with checkpointer(f.app) as saver:
            config: RunnableConfig = {"configurable": {"thread_id": str(task)}}
            return await saver.aget_tuple(config)

    return asyncio.run(read())


def done(f: Fixture, job: UUID) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with connect(f.app) as db:
            row = db.execute("SELECT status FROM business.jobs WHERE id=%s", (job,)).fetchone()
            if row and row["status"] == "done":
                return
            assert row and row["status"] != "dead", row
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
        done(f, first_job)
        checkpoint = saved(f, f.data.task)
        assert checkpoint and checkpoint.pending_writes
        assert any(channel == "__interrupt__" for _, channel, _ in checkpoint.pending_writes)
        assert f.rows(f.data.task)["status"] == "waiting"
        other = f.new_task()
        other_job = f.enqueue(other)
        assert first.until("invoke")["task"] == str(other.task)
        first.until("interrupt_persisted")
        done(f, other_job)
        assert f.rows(other.task)["result_ref"] is None
        stop(first)  # supervisor OS wait，随后同 namespace 的旧 PID 已消失。
        ref = f.decide(f.data)
        resume_job = f.enqueue(f.data, "resume", ref)
        second = Process(f)
        second.until("started")
        invoke = second.until("invoke")
        assert invoke["action"] == "resume" and invoke["thread"] == str(f.data.task)
        second.until("graph_finished")
        done(f, resume_job)
        # wait 节点重跑；prepare 未重跑；另一个 thread 仍等待，没有错误重建。
        assert sum(e["event"] == "wait_entered" for e in first.history) == 2
        assert sum(e["event"] == "wait_entered" for e in second.history) == 1
        assert not any(e["event"] == "prepare_entered" for e in second.history)
        assert all(e["active"] <= 1 for e in first.history + second.history if "active" in e)
        assert f.rows(f.data.task)["result_ref"]
        assert f.rows(other.task)["status"] == "waiting"
        stop(second)
        evidence(
            "cross_process_resume",
            task=str(f.data.task),
            thread=str(f.data.task),
            old_pid=first.process.pid,
            old_exit=first.process.returncode,
            new_pid=second.process.pid,
            interrupt_checkpoint=checkpoint.config,
            result_ref=f.rows(f.data.task)["result_ref"],
            maximum_graph_active=1,
            wait_node_runs=2,
            prepare_node_runs=1,
            other_thread=str(other.task),
        )
    finally:
        first.close()
        if second:
            second.close()


def test_receipt_commit_before_checkpoint_sigkill_replays_one_receipt(fixture: Fixture) -> None:
    f = fixture
    initial = f.enqueue(f.data)
    first = Process(f, barriers="receipt_committed")
    blocked = restarted = None
    try:
        started = first.until("started")
        first.until("interrupt_persisted")
        done(f, initial)
        ref = f.decide(f.data)
        resume = f.enqueue(f.data, "resume", ref)
        committed = first.until("receipt_committed")
        first.until("barrier")
        assert f.rows(f.data.task)["result_ref"] == committed["result_ref"]
        before = saved(f, f.data.task)
        assert before and "result_ref" not in before.checkpoint["channel_values"]
        assert before.checkpoint["channel_values"]["decision_ref"] == ref
        first.process.kill()  # 本测试 PID；明确 receipt COMMIT 后、execute 输出前。
        assert first.wait() == -signal.SIGKILL
        blocked = Process(f)
        assert blocked.until("failed")["code"] == "TerminationRequired"
        assert blocked.wait() == 2
        asyncio.run(confirm_termination(f.app, started["owner"], "p104 SIGKILL supervisor wait"))
        restarted = Process(f)
        restarted.until("started")
        invoke = restarted.until("invoke")
        assert invoke["action"] == "continue" and invoke["thread"] == str(f.data.task)
        replayed = restarted.until("receipt_committed")
        assert replayed["result_ref"] == committed["result_ref"]
        restarted.until("graph_finished")
        done(f, resume)
        assert not any(e["event"] == "prepare_entered" for e in restarted.history)
        with connect(f.app) as db:
            row = db.execute("SELECT count(*) AS n FROM checkpoint_probe.receipts").fetchone()
            assert row and row["n"] == 1
            row = db.execute("SELECT attempts FROM business.jobs WHERE id=%s", (resume,)).fetchone()
            assert row and row["attempts"] == 2
        after = saved(f, f.data.task)
        assert after.checkpoint["channel_values"]["result_ref"] == committed["result_ref"]
        stop(restarted)
        evidence(
            "receipt_commit_checkpoint_gap",
            task=str(f.data.task),
            thread=str(f.data.task),
            job=str(resume),
            old_pid=first.process.pid,
            old_exit=first.process.returncode,
            new_pid=restarted.process.pid,
            before_checkpoint=before.config,
            after_checkpoint=after.config,
            result_ref=committed["result_ref"],
            receipt_count=1,
            attempts=2,
            recovery_action="continue",
            start_repeated=False,
        )
    finally:
        first.close()
        for p in (blocked, restarted):
            if p:
                p.close()


def test_real_graph_startup_mutex_lock_loss_cancels_no_escape(fixture: Fixture) -> None:
    f = fixture
    job = f.enqueue(f.data)
    first = Process(f, barriers="prepare_entered")
    second = blocked = recovered = None
    try:
        started = first.until("started")
        first.until("barrier")
        second = Process(f)
        assert second.until("failed")["code"] == "WorkerBusy"
        assert second.wait() == 2
        with connect(f.owner) as db:
            db.execute("SELECT pg_terminate_backend(%s)", (started["lock_pid"],))
        first.until("barrier_cancelled")
        first.until("runner_left")
        assert first.until("failed")["code"] == "LockLost"
        assert first.wait() == 2
        before = saved(f, f.data.task)
        with connect(f.owner) as db:
            db.execute("UPDATE business.jobs SET lease_until=clock_timestamp()-interval '1 hour'")
        blocked = Process(f)
        assert blocked.until("failed")["code"] == "TerminationRequired"
        assert blocked.wait() == 2
        assert saved(f, f.data.task).config == before.config
        with connect(f.app) as db:
            row = db.execute("SELECT count(*) AS n FROM checkpoint_probe.receipts").fetchone()
            assert row == {"n": 0}
        asyncio.run(confirm_termination(f.app, started["owner"], "p104 lock loss OS wait"))
        recovered = Process(f)
        recovered.until("started")
        assert recovered.until("invoke")["action"] == "continue"
        recovered.until("interrupt_persisted")
        done(f, job)
        stop(recovered)
        evidence(
            "graph_lock_loss_cancel",
            old_pid=first.process.pid,
            old_exit=first.process.returncode,
            receipt_count=0,
            checkpoint=before.config,
            cancellation_complete=True,
            unconfirmed_start_refused=True,
        )
    finally:
        first.close()
        for p in (second, blocked, recovered):
            if p:
                p.close()


def test_decision_before_interrupt_observed_is_not_dropped_and_finished_reconciles(
    fixture: Fixture,
) -> None:
    f = fixture
    initial = f.enqueue(f.data)
    p = Process(f, barriers="prepare_entered")
    try:
        p.until("started")
        p.until("barrier")
        ref = f.decide(f.data)  # 决定已持久存在，此刻真实中断尚未发生。
        resume = f.enqueue(f.data, "resume", ref)
        p.release()
        p.until("interrupt_persisted")
        p.until("graph_finished")
        done(f, resume)
        done(f, initial)
        recovery = f.enqueue(f.data, "recover")
        done(f, recovery)
        stop(p)
        assert f.rows(f.data.task)["status"] == "finished"
        assert {e["kind"] for e in p.history if e["event"] == "runner_entered"} == {
            "analyze",
            "resume",
            "recover",
        }
        assert sum(e["event"] == "execute_entered" for e in p.history) == 1
        assert all(e["active"] <= 1 for e in p.history if "active" in e)
    finally:
        p.close()


@pytest.mark.parametrize("approved", [True, False])
def test_waiting_recover_and_durable_decision_reject_or_receipt(
    fixture: Fixture, approved: bool
) -> None:
    f = fixture
    initial = f.enqueue(f.data)
    p = Process(f)
    try:
        p.until("started")
        p.until("interrupt_persisted")
        done(f, initial)
        before = saved(f, f.data.task)
        waiting = f.enqueue(f.data, "recover")
        done(f, waiting)
        assert saved(f, f.data.task).config == before.config
        ref = f.decide(f.data, approved=approved)
        resume = f.enqueue(f.data, "resume", ref)
        p.until("graph_finished")
        done(f, resume)
        reconcile = f.enqueue(f.data, "recover")
        done(f, reconcile)
        assert bool(f.rows(f.data.task)["result_ref"]) is approved
        stop(p)
        assert sum(e["event"] == "prepare_entered" for e in p.history) == 1
        assert sum(e["event"] == "execute_entered" for e in p.history) == 1
    finally:
        p.close()


@pytest.mark.parametrize(
    "fault", ["version", "task", "request_hash", "missing", "receipt_hash", "payload"]
)
def test_unknown_checkpoint_or_conflict_needs_attention_never_starts_again(
    fixture: Fixture,
    fault: str,
) -> None:
    f = fixture
    initial = f.enqueue(f.data)
    first = Process(f)
    second = None
    try:
        first.until("started")
        first.until("interrupt_persisted")
        done(f, initial)
        stop(first)
        original = saved(f, f.data.task)
        ref = f.decide(f.data)
        if fault == "receipt_hash":
            with connect(f.owner) as db:
                db.execute(
                    "INSERT INTO checkpoint_probe.receipts "
                    "VALUES (%s,%s,%s,%s,'different_hash',%s)",
                    (
                        f"p104:{f.data.task}",
                        f.data.task,
                        f.data.organization,
                        f.data.shop,
                        str(uuid4()),
                    ),
                )
        elif fault == "missing":
            # 官方 saver 删的是本测试独立库的技术 thread，用于未知状态故障注入。
            async def delete() -> None:
                async with checkpointer(f.owner) as saver:
                    await saver.adelete_thread(str(f.data.task))

            asyncio.run(delete())
        elif fault != "payload":

            async def corrupt() -> None:
                async with checkpointer(f.owner) as saver:
                    checkpoint = copy_checkpoint(original.checkpoint)
                    checkpoint["id"] = str(uuid6())
                    key = {
                        "version": "workflow_version",
                        "task": "task_id",
                        "request_hash": "request_hash",
                    }[fault]
                    checkpoint["channel_values"][key] = "unsupported"
                    versions = checkpoint["channel_versions"].copy()
                    previous = versions[key]
                    assert isinstance(previous, str)
                    versions[key] = saver.get_next_version(previous, None)
                    checkpoint["channel_versions"] = versions
                    await saver.aput(
                        original.config, checkpoint, original.metadata, {key: versions[key]}
                    )

            asyncio.run(corrupt())
        recovery = f.enqueue(f.data, "resume", '{"approved":true}' if fault == "payload" else ref)
        second = Process(f)
        second.until("started")
        done(f, recovery)
        stop(second)
        assert f.rows(f.data.task)["status"] == "needs_attention"
        assert not any(e["event"] == "invoke" for e in second.history)
        with connect(f.app) as db:
            row = db.execute(
                "SELECT state FROM business.business_tasks WHERE id=%s", (f.data.task,)
            ).fetchone()
            assert row and row["state"] == "needs_attention"
            row = db.execute("SELECT count(*) AS n FROM checkpoint_probe.receipts").fetchone()
            assert row == {"n": 1 if fault == "receipt_hash" else 0}
    finally:
        first.close()
        if second:
            second.close()


def test_same_operation_key_different_hash_explicit_conflict(fixture: Fixture) -> None:
    f = fixture
    f.enqueue(f.data)

    async def scenario() -> None:
        session = WorkerSession(f.app, f.data.organization)
        await session.start()
        try:
            job = await JobQueue(session).claim()
            assert job
            store = ProbeStore(f.app, session, mode="test")
            row = await store.load(job)
            ref = f.decide(f.data)
            receipt = await store.receipt(job, row["request_hash"], ref)
            assert await store.receipt(job, row["request_hash"], ref) == receipt
            with pytest.raises(PersistenceConflict):
                await store.existing_receipt(job, "different_hash")
            with connect(f.app) as db:
                assert db.execute(
                    "SELECT count(*) AS n FROM checkpoint_probe.receipts"
                ).fetchone() == {"n": 1}
        finally:
            await session.close(clean=True)

    asyncio.run(scenario())


def test_receipt_db_failure_rolls_back_then_resumes_unfinished_node(fixture: Fixture) -> None:
    f = fixture
    initial = f.enqueue(f.data)
    p = Process(f, barriers="execute_entered")
    try:
        p.until("started")
        p.until("interrupt_persisted")
        done(f, initial)
        ref = f.decide(f.data)
        resume = f.enqueue(f.data, "resume", ref)
        p.until("barrier")
        with connect(f.owner) as db:
            db.execute("REVOKE INSERT ON checkpoint_probe.receipts FROM commerceops_app")
        p.release()
        p.until("runner_left")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with connect(f.app) as db:
                row = db.execute(
                    "SELECT status FROM business.jobs WHERE id=%s", (resume,)
                ).fetchone()
                if row and row["status"] == "retry_wait":
                    assert db.execute(
                        "SELECT count(*) AS n FROM checkpoint_probe.receipts"
                    ).fetchone() == {"n": 0}
                    break
            threading.Event().wait(0.01)
        else:
            raise AssertionError("DB failure did not persist retry")
        before = saved(f, f.data.task)
        assert "result_ref" not in before.checkpoint["channel_values"]
        with connect(f.owner) as db:
            db.execute("GRANT INSERT ON checkpoint_probe.receipts TO commerceops_app")
            db.execute(
                "UPDATE business.jobs SET available_at=clock_timestamp() WHERE id=%s", (resume,)
            )
        invoke = p.until("invoke")
        assert invoke["action"] == "continue"
        p.until("barrier")
        p.release()
        p.until("graph_finished")
        done(f, resume)
        assert f.rows(f.data.task)["result_ref"]
        stop(p)
    finally:
        p.close()


def test_real_graph_noncooperative_cancel_exits_before_replacement(fixture: Fixture) -> None:
    f = fixture
    f.enqueue(f.data)
    p = Process(f, barriers="prepare_entered", ignore_cancel=True)
    blocked = None
    try:
        started = p.until("started")
        p.until("barrier")
        with connect(f.owner) as db:
            db.execute("SELECT pg_terminate_backend(%s)", (started["lock_pid"],))
        p.until("barrier_cancelled")
        p.until("unsafe_shutdown")
        assert p.wait() == 75
        assert not any(e["event"] == "runner_left" for e in p.history)
        blocked = Process(f)
        assert blocked.until("failed")["code"] == "TerminationRequired"
        assert blocked.wait() == 2
        asyncio.run(confirm_termination(f.app, started["owner"], "p104 noncooperative OS wait"))
        assert f.rows(f.data.task)["result_ref"] is None
        evidence(
            "graph_noncooperative_exit",
            old_pid=p.process.pid,
            old_exit=p.process.returncode,
            receipt_count=0,
            runner_returned=False,
            unconfirmed_start_refused=True,
        )
    finally:
        p.close()
        if blocked:
            blocked.close()


def test_checkpoint_write_db_failure_does_not_report_persisted_interrupt(fixture: Fixture) -> None:
    f = fixture
    initial = f.enqueue(f.data)
    p = Process(f, barriers="prepare_entered", once=True)
    try:
        p.until("started")
        p.until("barrier")
        with connect(f.owner) as db:
            db.execute("REVOKE INSERT,UPDATE ON checkpoints.checkpoint_writes FROM commerceops_app")
        p.release()
        assert p.until("runner_failed")["code"] == "InsufficientPrivilege"
        p.until("runner_left")
        assert f.rows(f.data.task)["status"] == "running"
        assert not any(e["event"] == "interrupt_persisted" for e in p.history)
        assert f.rows(f.data.task)["result_ref"] is None
        with connect(f.owner) as db:
            db.execute("GRANT INSERT,UPDATE ON checkpoints.checkpoint_writes TO commerceops_app")
        assert p.until("invoke")["action"] == "continue"
        p.until("interrupt_persisted")
        done(f, initial)
        assert f.rows(f.data.task)["status"] == "waiting"
        stop(p)
        evidence(
            "checkpoint_db_failure_recovered",
            task=str(f.data.task),
            false_interrupt_reported=False,
            receipt_count=0,
            checkpoint=saved(f, f.data.task).config,
        )
    finally:
        p.close()


def test_current_principal_revoked_before_resume_marks_attention(fixture: Fixture) -> None:
    f = fixture
    initial = f.enqueue(f.data)
    p = Process(f)
    try:
        p.until("started")
        p.until("interrupt_persisted")
        done(f, initial)
        ref = f.decide(f.data)
        with connect(f.owner) as db:
            db.execute(
                "UPDATE business.principals SET enabled=false,auth_version=auth_version+1 "
                "WHERE id=%s",
                (f.data.principal,),
            )
        resume = f.enqueue(f.data, "resume", ref)
        done(f, resume)
        assert f.rows(f.data.task)["status"] == "needs_attention"
        assert f.rows(f.data.task)["result_ref"] is None
        stop(p)
    finally:
        p.close()


def test_run_request_scope_and_owner_cannot_be_replaced(fixture: Fixture) -> None:
    from dataclasses import replace

    f = fixture
    f.enqueue(f.data)

    async def scenario() -> None:
        session = WorkerSession(f.app, f.data.organization)
        await session.start()
        try:
            job = await JobQueue(session).claim()
            assert job
            store = ProbeStore(f.app, session, mode="test")
            for altered in (
                replace(job, organization_id=uuid4()),
                replace(job, shop_id=uuid4()),
                replace(job, owner=str(uuid4())),
            ):
                with pytest.raises(OwnershipLost):
                    await store.load(altered)
            with connect(f.app) as db:
                assert db.execute("SELECT count(*) AS n FROM checkpoint_probe.runs").fetchone() == {
                    "n": 0
                }
        finally:
            await session.close(clean=True)

    asyncio.run(scenario())


def test_resume_before_first_checkpoint_defers_without_new_start(fixture: Fixture) -> None:
    f = fixture
    ref = str(uuid4())
    resume = f.enqueue(f.data, "resume", ref)
    p = Process(f)
    try:
        p.until("started")
        p.until("runner_left")
        assert f.rows(f.data.task)["started"] is False
        assert saved(f, f.data.task) is None
        assert f.decide(f.data, ref=ref) == ref
        initial = f.enqueue(f.data)
        p.until("interrupt_persisted")
        p.until("graph_finished")
        done(f, resume)
        done(f, initial)
        assert f.rows(f.data.task)["result_ref"]
        stop(p)
        assert sum(e["event"] == "prepare_entered" for e in p.history) == 1
        assert sum(e.get("action") == "start" for e in p.history) == 1
    finally:
        p.close()


def test_retired_probe_task_version_is_preserved_and_marked_attention(fixture: Fixture) -> None:
    f = fixture
    old = f.new_task(version=RETIRED_PROBE_VERSION)
    job = f.enqueue(old)
    p = Process(f)
    try:
        p.until("started")
        done(f, job)
        stop(p)
        assert f.rows(old.task)["status"] == "needs_attention"
        assert saved(f, old.task) is None
        assert not any(e["event"] == "invoke" for e in p.history)
        with connect(f.app) as db:
            row = db.execute(
                "SELECT state,workflow_version FROM business.business_tasks WHERE id=%s",
                (old.task,),
            ).fetchone()
            assert row == {"state": "needs_attention", "workflow_version": RETIRED_PROBE_VERSION}
        evidence(
            "retired_probe_version_refused",
            task=str(old.task),
            version=RETIRED_PROBE_VERSION,
            checkpoint_created=False,
            start_called=False,
        )
    finally:
        p.close()


def test_live_stopped_graph_cannot_confirm_or_take_over(fixture: Fixture) -> None:
    f = fixture
    f.enqueue(f.data)
    p = Process(f, barriers="prepare_entered")
    blocked = None
    try:
        started = p.until("started")
        p.until("barrier")
        os.kill(p.process.pid, signal.SIGSTOP)
        pid, status = os.waitpid(p.process.pid, os.WUNTRACED)
        assert pid == p.process.pid and os.WIFSTOPPED(status)
        with connect(f.owner) as db:
            db.execute("SELECT pg_terminate_backend(%s)", (started["lock_pid"],))
            db.execute("UPDATE business.jobs SET lease_until=clock_timestamp()-interval '1 hour'")
        with pytest.raises(TerminationRequired):
            asyncio.run(confirm_termination(f.app, started["owner"], "live graph cannot confirm"))
        blocked = Process(f)
        assert blocked.until("failed")["code"] == "TerminationRequired"
        assert blocked.wait() == 2
        assert p.process.poll() is None
        p.process.kill()
        assert p.wait() == -signal.SIGKILL
        asyncio.run(confirm_termination(f.app, started["owner"], "p104 stopped graph OS wait"))
    finally:
        p.close()
        if blocked:
            blocked.close()
