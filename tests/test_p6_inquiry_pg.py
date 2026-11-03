"""Real PG contract candidates. Collection is offline; execution needs owned PG."""

import asyncio
import hashlib
import json
import os
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from commerceops.application.commerce.readonly_inquiry_executor import NAMES, Outcome, Tool, execute
from commerceops.application.commerce.readonly_inquiry_service_contracts import (
    CreateInquiry,
    ResultPayload,
)
from commerceops.application.replenishment.contracts import WebFailure
from commerceops.entrypoints.database import grant_runtime, migrate, setup_checkpointer
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.queue import JobQueue
from commerceops.infrastructure.readonly_inquiry_runtime import db_call
from commerceops.infrastructure.readonly_inquiry_store import InquiryConfig, InquiryStore
from commerceops.infrastructure.worker_lock import (
    WorkerSession,
    confirm_termination,
    mark_attention,
    open_async,
)
from commerceops.workflows.readonly_inquiry import ReadonlyInquiryRunner, runtime_factory
from psycopg import sql
from psycopg.types.json import Jsonb

from tests.inventory_support import DIRECTORY
from tests.p3_support import P3Fixture, initialize_p3

pytestmark = pytest.mark.integration


@dataclass
class InquiryFixture:
    web: P3Fixture
    store: InquiryStore

    def request(self, **changes: Any) -> CreateInquiry:
        return CreateInquiry.model_validate_json(
            json.dumps(
                {
                    "schema_version": "p6-inquiry-web-v1",
                    "shop_id": str(self.web.inventory.data.shop),
                    "question": "库存 合成演示商品 100",
                    "context_report_id": None,
                    "request_key": str(uuid4()),
                    **changes,
                }
            )
        )

    def row(self, task: UUID) -> dict[str, Any]:
        with connect(self.web.config.database) as db:
            row = db.execute(
                """SELECT i.*,t.state AS task_state,j.status AS job_state,j.attempts
                FROM business.readonly_inquiries i
                JOIN business.business_tasks t ON t.id=i.task_id
                JOIN business.jobs j ON j.task_id=i.task_id WHERE i.task_id=%s""",
                (task,),
            ).fetchone()
            assert row is not None
            return row


@pytest.fixture
def inquiry(tmp_path: Path) -> Iterator[InquiryFixture]:
    # No module-level config/read/connect: --collect-only must never touch PG.
    settings = DatabaseSettings()
    assert settings.runtime_password_file
    owner = settings.model_copy(update={"name": "p6_inquiry_" + uuid4().hex})
    app = owner.model_copy(
        update={
            "user": "commerceops_app",
            "password_file": settings.runtime_password_file,
        }
    )
    with psycopg.connect(**settings.kwargs(), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(owner.name)))
        try:
            # Requires Root's frozen 0019 + exact 0020_p6_knowledge_copy parent chain.
            migrate(owner)
            asyncio.run(setup_checkpointer(owner))
            grant_runtime(owner)
            web = initialize_p3(owner, app, tmp_path)
            try:
                yield InquiryFixture(
                    web,
                    InquiryStore(
                        web.config, InquiryConfig(web.inventory.data.shop, DIRECTORY, enabled=True)
                    ),
                )
            finally:
                web.client.close()
        finally:
            admin.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(owner.name))
            )


async def execute_task(f: InquiryFixture, task: UUID, *, settle: bool = True) -> None:
    session = WorkerSession(f.web.config.database, f.web.actor.organization_id)
    await session.start()
    try:
        queue = JobQueue(session, task_ids=frozenset({task}))
        job = await queue.claim()
        assert job is not None and job.task_id == task
        runner = ReadonlyInquiryRunner(f.store, session, runtime_factory(f.store, session))
        await runner.run(job)
        if settle:
            await queue.done(job)
    finally:
        await session.close(clean=True)


def test_low_privilege_and_sql_null_round_trip(inquiry: InquiryFixture) -> None:
    f = inquiry
    receipt = f.store.create(f.web.actor, f.request())
    with connect(f.web.config.database) as db:
        role = db.execute("SELECT current_user AS name").fetchone()
        acl = db.execute("""SELECT
            has_table_privilege(current_user,'business.readonly_inquiries','DELETE') AS delete,
            has_table_privilege(current_user,'business.readonly_inquiries','TRUNCATE') AS truncate,
            has_column_privilege(current_user,'business.readonly_inquiries','request','UPDATE')
            AS request_update""").fetchone()
        assert role == {"name": "commerceops_app"}
        assert acl == {"delete": False, "truncate": False, "request_update": False}
        row = db.execute(
            """SELECT result IS NULL AS sql_null,request->'context_report_id'
            = 'null'::jsonb AS json_null FROM business.readonly_inquiries WHERE task_id=%s""",
            (receipt.task_id,),
        ).fetchone()
        assert row == {"sql_null": True, "json_null": True}
    assert f.store.read(f.web.actor, task_id=receipt.task_id).result is None
    asyncio.run(execute_task(f, receipt.task_id))
    result = f.store.read(f.web.actor, request_key=receipt.request_key)
    assert result.state == "completed" and result.result is not None
    assert result.answer and "20" in result.answer
    assert f.row(receipt.task_id)["job_state"] == "done"


def test_json_null_is_not_a_valid_terminal_result(inquiry: InquiryFixture) -> None:
    f = inquiry
    task = f.store.create(f.web.actor, f.request()).task_id
    with pytest.raises(psycopg.Error), connect(f.web.config.database) as db:
        db.execute(
            """UPDATE business.readonly_inquiries SET state='failed',result=%s,
            result_canonical='null',result_hash=repeat('0',64),version=version+1
            WHERE task_id=%s""",
            (Jsonb(None), task),
        )
    assert f.row(task)["state"] == "queued" and f.row(task)["result"] is None


def test_same_key_concurrency_and_changed_payload(inquiry: InquiryFixture) -> None:
    f = inquiry
    request = f.request()
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = [pool.submit(f.store.create, f.web.actor, request) for _ in range(4)]
        receipts = [p.result(timeout=15) for p in pending]
    assert len({r.task_id for r in receipts}) == 1
    assert sum(not r.duplicate for r in receipts) == 1
    changed = f.request(request_key=str(request.request_key), question="销量 DEMO")
    with pytest.raises(WebFailure) as caught:
        f.store.create(f.web.actor, changed)
    assert caught.value.code == "IDEMPOTENCY_CONFLICT"
    with connect(f.web.config.database) as db:
        row = db.execute(
            "SELECT count(*) AS n FROM business.jobs WHERE task_id=%s", (receipts[0].task_id,)
        ).fetchone()
        assert row == {"n": 1}


def test_commit_receipt_loss_reads_original_key(inquiry: InquiryFixture) -> None:
    f = inquiry
    request = f.request()

    def fail(point: str) -> None:
        if point == "after_commit":
            raise OSError("controlled receipt loss")

    with pytest.raises(OSError):
        f.store.create(f.web.actor, request, hook=fail)
    read = f.store.read(f.web.actor, request_key=request.request_key)
    repeat = f.store.create(f.web.actor, request)
    assert read.task_id == repeat.task_id and repeat.duplicate


def test_before_commit_fault_rolls_back_task_job_and_receipt(inquiry: InquiryFixture) -> None:
    f = inquiry
    request = f.request()

    def fail(point: str) -> None:
        if point == "before_commit":
            raise OSError("controlled rollback")

    with pytest.raises(OSError):
        f.store.create(f.web.actor, request, hook=fail)
    with pytest.raises(WebFailure) as caught:
        f.store.read(f.web.actor, request_key=request.request_key)
    assert caught.value.code == "RESOURCE_NOT_FOUND"
    with connect(f.web.config.database) as db:
        row = db.execute("""SELECT count(*) AS n FROM business.business_tasks
            WHERE kind='readonly_inquiry'""").fetchone()
        assert row == {"n": 0}


def test_valid_same_shop_operator_is_not_original_receipt_owner(inquiry: InquiryFixture) -> None:
    f = inquiry
    request = f.request()
    original = f.store.create(f.web.actor, request)
    principal, identity, session = uuid4(), uuid4(), uuid4()
    org, shop = f.web.actor.organization_id, f.web.inventory.data.shop
    with connect(f.web.inventory.owner) as db:
        db.execute(
            """INSERT INTO business.principals(id,organization_id,display_name,roles)
            VALUES(%s,%s,'owned second inquiry reader',ARRAY['operator'])""",
            (principal, org),
        )
        db.execute(
            """INSERT INTO business.identities
            (id,organization_id,principal_id,provider,app_id,tenant_key,external_subject)
            VALUES(%s,%s,%s,'web',%s,%s,%s)""",
            (
                identity,
                org,
                principal,
                f.web.inventory.data.app,
                f.web.inventory.data.tenant,
                str(uuid4()),
            ),
        )
        db.execute(
            "INSERT INTO business.principal_shop_scopes VALUES(%s,%s,%s,true)",
            (org, shop, principal),
        )
        db.execute(
            "INSERT INTO business.principal_role_shop_grants VALUES(%s,%s,%s,'operator',true)",
            (org, shop, principal),
        )
        db.execute(
            """INSERT INTO business.web_credentials
            SELECT %s,%s,%s,%s,password_hash,true FROM business.web_credentials WHERE login=%s""",
            ("u-" + uuid4().hex, org, principal, identity, f.web.login),
        )
        row = db.execute(
            "SELECT auth_version FROM business.principals WHERE id=%s", (principal,)
        ).fetchone()
        assert row is not None
        version = row["auth_version"]
        db.execute(
            """INSERT INTO business.web_sessions
            SELECT %s,encode(sha256(convert_to(%s,'UTF8')),'hex'),kind,%s,%s,%s,%s,
            csrf_digest,key_version,created_at,last_seen_at,absolute_expires_at,
            idle_expires_at,NULL FROM business.web_sessions WHERE id=%s""",
            (session, str(uuid4()), org, principal, identity, version, f.web.actor.session_id),
        )
    other = replace(
        f.web.actor,
        principal_id=principal,
        identity_id=identity,
        session_id=session,
        auth_version=version,
    )
    # Current valid same-shop operator, not merely a forged/missing session.
    f.store.authorize_entry(other)
    for locator in ({"task_id": original.task_id}, {"request_key": original.request_key}):
        with pytest.raises(WebFailure) as caught:
            f.store.read(other, **locator)
        assert caught.value.code == "RESOURCE_NOT_FOUND"
    separate = f.store.create(other, request)
    assert separate.task_id != original.task_id and not separate.duplicate
    assert f.store.read(other, request_key=request.request_key).task_id == separate.task_id


@pytest.mark.parametrize("field", ["organization_id", "principal_id", "identity_id", "session_id"])
def test_cross_identity_and_scope_cannot_read_or_repost(
    inquiry: InquiryFixture, field: str
) -> None:
    f = inquiry
    request = f.request()
    receipt = f.store.create(f.web.actor, request)
    changes: dict[str, Any] = {field: uuid4()}
    actor = replace(f.web.actor, **changes)
    with pytest.raises(WebFailure):
        f.store.read(actor, task_id=receipt.task_id)
    with pytest.raises(WebFailure):
        f.store.create(actor, request)
    with pytest.raises(WebFailure):
        f.store.create(f.web.actor, f.request(shop_id=str(uuid4())))


@pytest.mark.parametrize("change", ["role", "scope", "identity", "session"])
def test_current_revocation_denies_saved_evidence(inquiry: InquiryFixture, change: str) -> None:
    f = inquiry
    receipt = f.store.create(f.web.actor, f.request())
    asyncio.run(execute_task(f, receipt.task_id))
    with connect(f.web.inventory.owner) as db:
        if change == "role":
            db.execute(
                "UPDATE business.principals SET roles=ARRAY['approver'],"
                "auth_version=auth_version+1 WHERE id=%s",
                (f.web.actor.principal_id,),
            )
        elif change == "scope":
            db.execute(
                "UPDATE business.principal_role_shop_grants SET enabled=false "
                "WHERE principal_id=%s AND role='operator'",
                (f.web.actor.principal_id,),
            )
        elif change == "identity":
            db.execute(
                "UPDATE business.web_credentials SET enabled=false WHERE identity_id=%s",
                (f.web.actor.identity_id,),
            )
        else:
            db.execute(
                "UPDATE business.web_sessions SET revoked_at=clock_timestamp() WHERE id=%s",
                (f.web.actor.session_id,),
            )
    with pytest.raises(WebFailure):
        f.store.read(f.web.actor, task_id=receipt.task_id)


@pytest.mark.parametrize("operation", ["row_lock", "advisory_lock"])
def test_sql_block_deadline_joins_thread_before_return(
    inquiry: InquiryFixture, operation: str
) -> None:
    f = inquiry
    request = f.request()
    receipt = f.store.create(f.web.actor, request)
    stopped = threading.Event()
    with connect(f.web.inventory.owner) as blocker:
        if operation == "row_lock":
            blocker.execute(
                "SELECT 1 FROM business.readonly_inquiries WHERE task_id=%s FOR UPDATE",
                (receipt.task_id,),
            )
        else:
            blocker.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (f"p6-inquiry:{f.web.actor.principal_id}:{request.request_key}",),
            )

        def work() -> None:
            try:
                if operation == "row_lock":
                    with connect(f.web.config.database) as db:
                        f.store.bound_transaction(db)
                        db.execute(
                            "SELECT 1 FROM business.readonly_inquiries WHERE task_id=%s FOR UPDATE",
                            (receipt.task_id,),
                        )
                else:
                    f.store.create(f.web.actor, request)
            finally:
                stopped.set()

        async def scenario() -> None:
            start = time.monotonic()
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(db_call(work), 0.05)
            assert stopped.is_set() and time.monotonic() - start < 8

        asyncio.run(scenario())
    assert f.row(receipt.task_id)["state"] == "queued"


@pytest.mark.parametrize("change", ["none", "expired", "missing_fixture", "revoked"])
def test_result_commit_gap_and_new_process_replay(inquiry: InquiryFixture, change: str) -> None:
    f = inquiry
    receipt = f.store.create(f.web.actor, f.request())
    first = child(f, receipt.task_id, replay=False)
    try:
        event = next_event(first)
        assert event["event"] == "saved"
        owner = event["owner"]
        before = f.row(receipt.task_id)
        assert before["state"] == "completed" and before["job_state"] == "running"
        assert f.store.read(f.web.actor, request_key=receipt.request_key).task_id == receipt.task_id
        first.kill()
        first.wait(timeout=5)
        if change in ("expired", "revoked"):
            with connect(f.web.inventory.owner) as db:
                if change == "expired":
                    db.execute(
                        """UPDATE business.web_sessions
                        SET created_at=clock_timestamp()-interval '2 hours',
                        idle_expires_at=
                        clock_timestamp()-interval '1 second' WHERE id=%s""",
                        (f.web.actor.session_id,),
                    )
                else:
                    db.execute(
                        "UPDATE business.principals SET enabled=false WHERE id=%s",
                        (f.web.actor.principal_id,),
                    )
            with pytest.raises(WebFailure):
                f.store.read(f.web.actor, request_key=receipt.request_key)

        # Root's shared exclusion must preserve a valid terminal inquiry result.
        # Current pre-integration worker_lock lacks it: do not weaken this assertion.
        async def scan_termination() -> None:
            async with await open_async(f.web.config.database) as db:
                await mark_attention(db, owner)

        asyncio.run(scan_termination())
        assert f.row(receipt.task_id)["task_state"] == "completed"
        # Confirm only after actual OS process exit; never infer from a lease.
        asyncio.run(confirm_termination(f.web.config.database, owner, "owned P6 child reaped"))
        second = child(f, receipt.task_id, replay=True, missing_fixture=change == "missing_fixture")
        try:
            assert next_event(second)["event"] == "saved"
            assert next_event(second)["event"] == "settled"
            assert second.wait(timeout=5) == 0
        finally:
            reap(second)
        after = f.row(receipt.task_id)
        assert after["job_state"] == "done" and after["attempts"] == 2
        assert before["result_canonical"] == after["result_canonical"]
        assert before["result_hash"] == after["result_hash"]
        assert before["version"] == after["version"]
    finally:
        reap(first)


def child(
    f: InquiryFixture, task: UUID, *, replay: bool, missing_fixture: bool = False
) -> subprocess.Popen[str]:
    path = f.web.private / ("p6-child-" + uuid4().hex + ".json")
    path.write_text(
        json.dumps(
            {
                "configuration": str(f.web.config_file),
                "task": str(task),
                "organization": str(f.web.actor.organization_id),
                "shop": str(f.web.inventory.data.shop),
                "replay": replay,
                "missing_fixture": str(f.web.private / "absent-fixture")
                if missing_fixture
                else None,
            }
        )
    )
    path.chmod(0o600)
    env = os.environ.copy()
    root = Path(__file__).resolve().parents[1]
    env["PYTHONPATH"] = os.pathsep.join((str(root / "backend/src"), str(root)))
    return subprocess.Popen(
        [sys.executable, "-m", "tests.p6_inquiry_process", str(path)],
        cwd=root,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )


def next_event(process: subprocess.Popen[str]) -> dict[str, Any]:
    events: queue.Queue[str] = queue.Queue()
    assert process.stdout is not None
    stream = process.stdout
    reader = threading.Thread(target=lambda: events.put(stream.readline()), daemon=True)
    reader.start()
    try:
        line = events.get(timeout=20)
    except queue.Empty:
        reap(process)
        reader.join(timeout=2)
        raise AssertionError("owned inquiry child event deadline") from None
    reader.join(timeout=2)
    assert line and not reader.is_alive()
    value: dict[str, Any] = json.loads(line)
    return value


def reap(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.kill()
    process.wait(timeout=5)
    for stream in (process.stdin, process.stdout):
        if stream is not None:
            stream.close()


@pytest.mark.parametrize(
    "mutation",
    ["empty", "schema_missing", "schema_null", "status_null", "results_null", "counter_null"],
)
def test_correct_hash_does_not_make_malformed_result_valid(
    inquiry: InquiryFixture, mutation: str
) -> None:
    f = inquiry
    task = f.store.create(f.web.actor, f.request()).task_id
    payload = ResultPayload.from_outcome(Outcome("unsupported", 0, 0, 0, ())).model_dump(
        mode="json"
    )
    if mutation == "empty":
        payload = {}
    elif mutation == "schema_missing":
        payload.pop("schema_version")
    elif mutation == "schema_null":
        payload["schema_version"] = None
    elif mutation == "status_null":
        payload["status"] = None
    elif mutation == "results_null":
        payload["results"] = None
    else:
        payload["tool_calls"] = None
    canonical = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    with connect(f.web.config.database) as db:
        db.execute(
            "UPDATE business.readonly_inquiries SET state='analyzing',version=version+1 "
            "WHERE task_id=%s",
            (task,),
        )
        db.execute(
            "UPDATE business.business_tasks SET state='analyzing',version=version+1 WHERE id=%s",
            (task,),
        )
    with pytest.raises(psycopg.Error), connect(f.web.config.database) as db:
        db.execute(
            """UPDATE business.readonly_inquiries SET state='completed',result=%s,
            result_canonical=%s,result_hash=%s,version=version+1 WHERE task_id=%s""",
            (Jsonb(payload), canonical, digest, task),
        )
    assert f.row(task)["state"] == "analyzing" and f.row(task)["result"] is None


@pytest.mark.parametrize("field", ["schema_version", "shop_id", "request_key", "question"])
@pytest.mark.parametrize("mode", ["missing", "null"])
def test_sql_request_schema_fails_closed(inquiry: InquiryFixture, field: str, mode: str) -> None:
    f = inquiry
    request = f.request()
    raw = request.model_dump(mode="json")
    if mode == "missing":
        raw.pop(field)
    else:
        raw[field] = None
    with connect(f.web.config.database) as db:
        row = db.execute(
            "SELECT business.valid_inquiry_request(%s,%s,%s,NULL) AS valid",
            (Jsonb(raw), request.shop_id, request.request_key),
        ).fetchone()
        assert row == {"valid": False}


def test_revoke_after_mark_can_settle_fact_free_failure(inquiry: InquiryFixture) -> None:
    f = inquiry
    task = f.store.create(f.web.actor, f.request()).task_id

    async def scenario() -> None:
        session = WorkerSession(f.web.config.database, f.web.actor.organization_id)
        await session.start()
        try:
            queue = JobQueue(session, task_ids=frozenset({task}))
            job = await queue.claim()
            assert job is not None
            f.store.mark(job)
            with connect(f.web.inventory.owner) as db:
                db.execute(
                    "UPDATE business.principals SET enabled=false WHERE id=%s",
                    (f.web.actor.principal_id,),
                )
            with pytest.raises(WebFailure):
                f.store.finish(job, ResultPayload.from_outcome(Outcome("unsupported", 0, 0, 0, ())))
            f.store.fail_safe(job)
            # Repeat acknowledgement recovery preserves the same terminal receipt.
            f.store.fail_safe(job)
            await queue.done(job)
        finally:
            await session.close(clean=True)

    asyncio.run(scenario())
    row = f.row(task)
    assert row["state"] == row["task_state"] == "failed" and row["job_state"] == "done"
    assert row["result"]["status"] == "access_denied" and row["result"]["results"] == []
    with pytest.raises(WebFailure):
        f.store.read(f.web.actor, task_id=task)


def test_commit_ack_unknown_rechecks_terminal_before_same_job_settlement(
    inquiry: InquiryFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = inquiry
    task = f.store.create(f.web.actor, f.request()).task_id
    original = f.store.finish

    def lost_ack(*args: Any) -> None:
        original(*args)
        raise OSError("controlled result commit acknowledgement loss")

    monkeypatch.setattr(f.store, "finish", lost_ack)
    asyncio.run(execute_task(f, task))
    row = f.row(task)
    assert row["state"] == row["task_state"] == "completed" and row["job_state"] == "done"
    assert row["result"]["status"] == "complete" and row["attempts"] == 1
    with connect(f.web.config.database) as db:
        saved = db.execute(
            "SELECT count(*) AS n FROM business.audit_events WHERE task_id=%s "
            "AND action='inquiry_result_saved'",
            (task,),
        ).fetchone()
        assert saved == {"n": 1}


@pytest.mark.parametrize("question", ["库存 合成演示商品 100", "销量 合成演示商品 100"])
def test_sql_terminal_validator_accepts_real_executor_evidence(
    inquiry: InquiryFixture, question: str
) -> None:
    """Real SQL positive and bad-reference negative; no bypass of the store or authority."""
    f = inquiry
    task = f.store.create(f.web.actor, f.request(question=question)).task_id

    async def scenario() -> None:
        session = WorkerSession(f.web.config.database, f.web.actor.organization_id)
        await session.start()
        try:
            queue = JobQueue(session, task_ids=frozenset({task}))
            job = await queue.claim()
            assert job is not None
            row, previous = f.store.load(job)
            assert previous is None
            f.store.mark(job)
            context, choice, authority, reader = await runtime_factory(f.store, session)(job, row)
            outcome = await execute(
                context, choice, authority, {name: Tool("read", reader) for name in NAMES}
            )
            payload = ResultPayload.from_outcome(outcome)
            assert payload.status == "complete" and payload.evidence_refs and payload.claims
            schema = ResultPayload.model_json_schema()
            canonical = payload.model_dump_json()
            digest = hashlib.sha256(canonical.encode()).hexdigest()
            with connect(f.web.config.database) as db:
                f.store.bound_transaction(db)
                checked = db.execute(
                    """SELECT
                    business.inquiry_json_valid(%s,%s,%s) AS shape_valid,
                    business.valid_inquiry_payload(%s,%s,%s,'completed',%s,%s) AS terminal_valid""",
                    (
                        Jsonb(payload.model_dump(mode="json")),
                        Jsonb(schema),
                        Jsonb(schema),
                        Jsonb(payload.model_dump(mode="json")),
                        canonical,
                        digest,
                        job.workflow_version,
                        context.source_binding,
                    ),
                ).fetchone()
                assert checked == {"shape_valid": True, "terminal_valid": True}
                invalid = payload.model_dump(mode="json")
                invalid["evidence_refs"] = ["no-such-evidence"]
                invalid["claims"] = [{"kind": "fact", "refs": ["no-such-evidence"]}]
                bad = ResultPayload.model_validate_json(json.dumps(invalid))
                bad_canonical = bad.model_dump_json()
                rejected = db.execute(
                    """SELECT business.valid_inquiry_payload(
                    %s,%s,%s,'completed',%s,%s) AS valid""",
                    (
                        Jsonb(invalid),
                        bad_canonical,
                        hashlib.sha256(bad_canonical.encode()).hexdigest(),
                        job.workflow_version,
                        context.source_binding,
                    ),
                ).fetchone()
                assert rejected == {"valid": False}
            f.store.finish(job, payload)
            await queue.done(job)
            assert f.row(task)["result_canonical"] == canonical
        finally:
            await session.close(clean=True)

    asyncio.run(scenario())
