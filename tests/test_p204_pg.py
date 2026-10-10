"""P204同Worker/真实PG/离线HTTP替身，禁止actual网络与凭据。"""

import asyncio
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
import psycopg
import pytest
from commerceops.application.commerce.explanation_task import STAGE_BASE, Evidence
from commerceops.application.commerce.intent_task import ROUTE_SYSTEM
from commerceops.application.commerce.inventory_routing import RoutingInput
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.explanation_repository import (
    ExplanationStore,
    create_explanation_task,
)
from commerceops.infrastructure.intent_repository import (
    IntentStore,
    create_intent_task,
    read_intent,
)
from commerceops.infrastructure.inventory_repository import InventoryStore
from commerceops.infrastructure.worker import Worker
from commerceops.infrastructure.worker_lock import WorkerSession
from commerceops.workflows.inventory_analysis import InventoryRunner, MockCollectorFactory
from commerceops.workflows.inventory_routing import IntentRunner
from commerceops.workflows.report_explanation import (
    ExplanationRunner,
    InventoryCompositeRunner,
    ProviderFactory,
)

from tests.inventory_support import DIRECTORY, InventoryFixture
from tests.test_inventory_pg import fixture as fixture

pytestmark = pytest.mark.integration


async def done(f: InventoryFixture, job: UUID) -> None:
    for _ in range(2000):
        with connect(f.app) as db:
            row = db.execute(
                "SELECT status,last_error FROM business.jobs WHERE id=%s", (job,)
            ).fetchone()
        if row and row["status"] == "done":
            return
        if row and row["status"] == "dead":
            raise AssertionError("p204 controlled job dead")
        await asyncio.sleep(0.01)
    raise AssertionError("owned p204 job timeout")


@dataclass
class Harness:
    f: InventoryFixture
    parent: UUID
    calls: list[dict[str, Any]]
    store: ExplanationStore
    proposal: dict[str, Any]

    async def intent(
        self, text: str, context: UUID | None = None, mode: Evidence = "offline_stub"
    ) -> dict[str, Any]:
        task, job = create_intent_task(
            self.f.app, self.f.identity, RoutingInput(text=text, context_task_id=context), mode
        )
        await done(self.f, job)
        return await read_intent(self.f.app, self.f.identity, task)

    async def explain(self, mode: str = "offline_stub") -> UUID:
        child, job = create_explanation_task(self.f.app, self.f.identity, self.parent, mode)  # type: ignore[arg-type]
        await done(self.f, job)
        return child


async def run(f: InventoryFixture, scenario: Any, *, fault: str | None = None) -> None:
    calls: list[dict[str, Any]] = []
    proposal: dict[str, Any] = {"intent": "inventory_replenishment", "candidates": []}

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        if fault == "unknown":
            return httpx.Response(200, json={"model": "deepseek-flash", "choices": []})
        if fault == "over_budget":
            return httpx.Response(
                200,
                json={
                    "model": "deepseek-flash",
                    "usage": {"prompt_tokens": 100, "completion_tokens": 801, "total_tokens": 901},
                    "choices": [
                        {"finish_reason": "stop", "message": {"role": "assistant", "content": "{}"}}
                    ],
                },
            )
        if body["messages"][0]["content"] == ROUTE_SYSTEM:
            return httpx.Response(
                200,
                json={
                    "model": "deepseek-flash",
                    "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": json.dumps(proposal)},
                        }
                    ],
                },
            )
        items = json.loads(body["messages"][1]["content"])["items"]
        return httpx.Response(
            200,
            json={
                "model": "deepseek-flash",
                "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "highlights": [
                                        {
                                            "sku_key": item["sku_key"],
                                            "reason": item["allowed_reason"],
                                            "source": "facts",
                                        }
                                        for item in items
                                    ]
                                }
                            ),
                        },
                    }
                ],
            },
        )

    parent, job = f.create()
    session = WorkerSession(f.app, f.data.organization)
    await session.start()
    store = ExplanationStore(f.app, session)
    runner = InventoryCompositeRunner(
        InventoryRunner(InventoryStore(f.app, session), MockCollectorFactory(DIRECTORY)),
        ExplanationRunner(store, ProviderFactory(offline_transport=httpx.MockTransport(respond))),
        IntentRunner(
            IntentStore(f.app, session),
            ProviderFactory(offline_transport=httpx.MockTransport(respond)),
        ),
    )
    stop = asyncio.Event()
    worker = asyncio.create_task(
        Worker(session, runner, heartbeat_seconds=0.1, poll_seconds=0.01).run(stop)
    )
    try:
        await done(f, job)
        await scenario(Harness(f, parent, calls, store, proposal))
    finally:
        stop.set()
        await worker


def test_same_worker_explanation_cache_and_budget(fixture: InventoryFixture) -> None:
    async def scenario(h: Harness) -> None:
        first = await h.explain()
        second = await h.explain()
        assert (
            len(h.calls) == 1 and h.f.row(first)["state"] == h.f.row(second)["state"] == "completed"
        )
        assert h.f.row(h.parent)["state"] == "completed"
        with connect(h.f.app) as db:
            budget = db.execute(
                "SELECT * FROM business.model_stage_budgets WHERE stage_key=%s",
                (STAGE_BASE + ":offline",),
            ).fetchone()
            assert budget and budget["reserved_count"] == 1 and budget["reserved_nanos"] == 3360000
            assert not budget["halted"]
            rows = db.execute("SELECT * FROM business.model_explanations").fetchall()
            assert len(rows) == 1 and rows[0]["result"]["narrative_mode"] == "model_selected"
            links = db.execute("SELECT * FROM business.explanation_task_results").fetchall()
            assert len(links) == 2 and links[0]["result_id"] == links[1]["result_id"]

    asyncio.run(run(fixture, scenario))


def test_unknown_usage_halts_does_not_retry(fixture: InventoryFixture) -> None:
    async def scenario(h: Harness) -> None:
        child = await h.explain()
        assert len(h.calls) == 1 and h.f.row(child)["state"] == "completed"
        with connect(h.f.app) as db:
            budget = db.execute("SELECT * FROM business.model_stage_budgets").fetchone()
            assert budget and budget["halted"] and budget["reserved_count"] == 1
            observation = db.execute("SELECT * FROM business.model_call_observations").fetchone()
            assert observation and observation["outcome"] == "uncertain"
            assert observation["actual_cost_usd"] is None and observation["input_tokens"] is None
            result = db.execute("SELECT result FROM business.model_explanations").fetchone()
            assert result and result["result"]["narrative_mode"] == "template"
        await h.explain()
        assert len(h.calls) == 1

    asyncio.run(run(fixture, scenario, fault="unknown"))


def test_template_and_local_fault_actual_zero(fixture: InventoryFixture) -> None:
    async def scenario(h: Harness) -> None:
        await h.explain("template")
        assert h.calls == []
        await h.explain("local_fault")
        assert h.calls == []  # 本地失败transport为独立替身，不是实际provider。
        with connect(h.f.app) as db:
            modes = db.execute("SELECT evidence_mode FROM business.model_calls").fetchall()
            assert modes and all(row["evidence_mode"] == "offline_stub" for row in modes)
            assert not db.execute(
                "SELECT 1 FROM business.model_stage_budgets WHERE stage_key=%s",
                (STAGE_BASE + ":actual",),
            ).fetchone()

    asyncio.run(run(fixture, scenario))


def test_stage_ten_requests_across_distinct_reports(fixture: InventoryFixture) -> None:
    async def scenario(h: Harness) -> None:
        await h.explain()
        for _ in range(10):
            parent, job = h.f.create()
            await done(h.f, job)
            h.parent = parent
            await h.explain()
        assert len(h.calls) == 10
        with connect(h.f.app) as db:
            stage = db.execute("SELECT * FROM business.model_stage_budgets").fetchone()
            assert stage and stage["reserved_count"] == 10 and stage["reserved_nanos"] == 33600000
            count = db.execute("SELECT count(*) AS n FROM business.model_calls").fetchone()
            assert count and count["n"] == 10
            with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
                db.execute("UPDATE business.model_stage_budgets SET reserved_count=0")

    asyncio.run(run(fixture, scenario))


def test_refs_scope_revoke_and_parent_immutable(fixture: InventoryFixture) -> None:
    async def scenario(h: Harness) -> None:
        from dataclasses import replace
        from uuid import uuid4

        from commerceops.entrypoints.api import create_app
        from commerceops.entrypoints.explanation_http import ExplanationEndpoints
        from fastapi.testclient import TestClient

        before = h.f.row(h.parent)
        child = await h.explain()
        assert h.f.row(h.parent) == before
        current = TestClient(
            create_app(
                explanation_service=ExplanationEndpoints(h.f.app),
                identity_resolver=lambda _: h.f.identity,
            )
        )
        r = current.get(f"/tasks/{h.parent}/explanation")
        assert r.status_code == 200 and r.json()["result"]["facts_hash"]
        assert len(h.calls) == 1
        for _ in range(3):
            assert current.get(f"/tasks/{h.parent}/explanation").status_code == 200
        assert len(h.calls) == 1
        wrong = replace(h.f.identity, shop_id=uuid4())
        denied = TestClient(
            create_app(
                explanation_service=ExplanationEndpoints(h.f.app), identity_resolver=lambda _: wrong
            )
        )
        assert denied.get(f"/tasks/{h.parent}/explanation").status_code == 403
        with connect(h.f.owner) as db:
            db.execute(
                """UPDATE business.principal_shop_scopes SET enabled=false
                        WHERE principal_id=%s""",
                (h.f.data.principal,),
            )
        assert current.get(f"/tasks/{h.parent}/explanation").status_code == 403
        assert h.f.row(child)["state"] == "completed"

    asyncio.run(run(fixture, scenario))


@pytest.mark.parametrize(
    "kind,barrier",
    [
        ("explanation", "provider_returned"),
        ("explanation", "explanation_committed"),
        ("routing", "provider_returned"),
        ("routing", "intent_committed"),
    ],
)
def test_process_crash_no_second_http(fixture: InventoryFixture, kind: str, barrier: str) -> None:
    import signal

    from commerceops.infrastructure.worker_lock import TerminationRequired, confirm_termination

    from tests.p204_support import ExplanationProcess

    f = fixture
    parent, parent_job = f.create()
    first = ExplanationProcess(f, barrier)
    second = None
    try:
        started = first.until("started")
        first.until("report_committed")
        asyncio.run(done(f, parent_job))
        if kind == "explanation":
            child, job = create_explanation_task(f.app, f.identity, parent, "offline_stub")
        else:
            child, job = create_intent_task(
                f.app,
                f.identity,
                RoutingInput(text="受控原句", context_task_id=parent),
                "offline_stub",
            )
        first.until("offline_http")
        first.until(barrier)
        first.process.kill()
        assert first.process.wait(timeout=15) == -signal.SIGKILL

        async def blocked() -> None:
            s = WorkerSession(f.app, f.data.organization)
            with pytest.raises(TerminationRequired):
                await s.start()

        asyncio.run(blocked())
        assert f.row(child)["state"] == (
            "completed" if barrier != "provider_returned" else "needs_attention"
        )
        asyncio.run(
            confirm_termination(f.app, started["owner"], "P204 owned SIGKILL parent wait proof")
        )
        second = ExplanationProcess(f)
        second.until("started")
        second.until(
            "persistent_replay"
            if barrier != "provider_returned"
            else "prior_request_recovered_without_http"
        )
        asyncio.run(done(f, job))
        assert f.row(child)["state"] == "completed" and f.counts(parent) == (1, 1)
        with connect(f.app) as db:
            budget = db.execute("SELECT * FROM business.model_stage_budgets").fetchone()
            assert budget and budget["reserved_count"] == 1 and budget["reserved_nanos"] == 3360000
            assert budget["halted"] == (barrier == "provider_returned")
            count = db.execute("SELECT count(*) AS n FROM business.model_calls").fetchone()
            assert count and count["n"] == 1
            row = db.execute("SELECT * FROM business.model_call_observations").fetchone()
            assert row and row["actual_cost_usd"] is None
            assert row["outcome"] == ("uncertain" if barrier == "provider_returned" else "observed")
        second.process.send_signal(signal.SIGTERM)
        second.until("stopped")
        assert second.process.wait(timeout=15) == 0
        assert not any(row["event"] == "offline_http" for row in second.seen)
    finally:
        first.close()
        if second:
            second.close()


def test_routing_five_intents_same_budget_and_cache(fixture: InventoryFixture) -> None:
    async def scenario(h: Harness) -> None:
        await h.explain()
        for i, intent in enumerate(
            ("inventory_replenishment", "task_status", "explain_report", "clarify", "unsupported")
        ):
            h.proposal["intent"] = intent
            result = await h.intent(f"受控原句{i}", h.parent)
            assert (
                result["state"] == "completed" and result["result"]["decision"]["intent"] == intent
            )
            assert result["result"]["metadata"]["prompt_version"] == "inventory-routing-v1"
            assert result["result"]["decision"]["evidence_mode"] == "offline_stub"
        assert len(h.calls) == 6
        h.proposal["intent"] = "unsupported"
        cached = await h.intent("受控原句0", h.parent)
        assert (
            cached["result"]["decision"]["intent"] == "inventory_replenishment"
            and len(h.calls) == 6
        )
        with connect(h.f.app) as db:
            stage = db.execute("SELECT * FROM business.model_stage_budgets").fetchone()
            assert stage and stage["reserved_count"] == 6 and stage["reserved_nanos"] == 6 * 3360000
            assert not stage["halted"]
            counts = db.execute(
                """SELECT count(*) AS n FROM business.business_tasks
                WHERE kind='inventory_analysis_only'"""
            ).fetchone()
            assert counts and counts["n"] == 1  # 仅routing证据，不自动创建业务任务。

    asyncio.run(run(fixture, scenario))


def test_routing_permission_confirmation_and_read_only_http(fixture: InventoryFixture) -> None:
    async def scenario(h: Harness) -> None:
        from dataclasses import replace
        from uuid import uuid4

        from commerceops.entrypoints.api import create_app
        from commerceops.entrypoints.explanation_http import ExplanationEndpoints
        from fastapi.testclient import TestClient

        h.proposal.update(
            intent="inventory_replenishment",
            candidates=[{"name": "L", "value": 4, "start": 2, "end": 3, "source": "explicit_text"}],
        )
        result = await h.intent("L=4")
        assert result["result"]["decision"]["parameters"] == {"L": 4, "R": 7, "S": 2}
        task = result["task_id"]
        client = TestClient(
            create_app(
                explanation_service=ExplanationEndpoints(h.f.app),
                identity_resolver=lambda _: h.f.identity,
            )
        )
        for _ in range(3):
            response = client.get(f"/test/routes/{task}")
            assert response.status_code == 200
        assert len(h.calls) == 1
        forged = client.post(
            "/test/route", json={"text": "库存", "tenant": "other", "approved": True}
        )
        assert forged.status_code == 400 and forged.json()["schema_version"] == "p204-read-v1"
        unknown = replace(h.f.identity, principal_id=uuid4())
        denied = TestClient(
            create_app(
                explanation_service=ExplanationEndpoints(h.f.app),
                identity_resolver=lambda _: unknown,
            )
        )
        assert denied.get(f"/test/routes/{task}").status_code == 403
        with connect(h.f.owner) as db:
            db.execute(
                """UPDATE business.principal_shop_scopes SET enabled=false
                        WHERE principal_id=%s""",
                (h.f.data.principal,),
            )
        assert client.get(f"/test/routes/{task}").status_code == 403 and len(h.calls) == 1
        with connect(h.f.app) as db:
            rows = db.execute(
                "SELECT * FROM business.audit_events WHERE source='routing'"
            ).fetchall()
            assert rows and all(
                row["after_state"]["business_task_created"] is False for row in rows
            )

    asyncio.run(run(fixture, scenario))


def test_p204_evidence_immutable_and_budget_not_reset(fixture: InventoryFixture) -> None:
    async def scenario(h: Harness) -> None:
        await h.explain()
        await h.intent("只记录routing")
        tables = (
            "explanation_links",
            "model_calls",
            "model_call_observations",
            "model_explanations",
            "explanation_task_results",
            "inventory_intent_requests",
            "inventory_intent_results",
            "model_stage_budgets",
        )
        with connect(h.f.owner) as db:
            for table in tables:
                for verb in ("DELETE FROM", "TRUNCATE"):
                    from psycopg import sql

                    with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
                        db.execute(
                            sql.SQL("{} business.{}{}").format(
                                sql.SQL(verb),
                                sql.Identifier(table),
                                sql.SQL(" CASCADE" if verb == "TRUNCATE" else ""),
                            )
                        )
            for statement in ("UPDATE business.model_stage_budgets SET reserved_nanos=0",):
                with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
                    db.execute(statement)
        with connect(h.f.app) as db:
            for table in tables:
                from psycopg import sql

                with pytest.raises(psycopg.errors.InsufficientPrivilege), db.transaction():
                    db.execute(sql.SQL("DELETE FROM business.{}").format(sql.Identifier(table)))

    asyncio.run(run(fixture, scenario))


@pytest.mark.parametrize("duplicate", [False, True])
def test_atomic_admission_concurrency_no_http(fixture: InventoryFixture, duplicate: bool) -> None:
    from uuid import uuid4

    from commerceops.application.model_explanation.contracts import BudgetRequest
    from commerceops.infrastructure.model_budget_repository import PRICING, PersistentAdmission
    from commerceops.infrastructure.p204_token_counter import COUNT_VERSION
    from commerceops.infrastructure.queue import JobQueue

    async def scenario() -> None:
        f = fixture
        parent, _ = f.create()
        session = WorkerSession(f.app, f.data.organization)
        await session.start()
        queue = JobQueue(session)
        analysis = InventoryRunner(InventoryStore(f.app, session), MockCollectorFactory(DIRECTORY))
        store = ExplanationStore(f.app, session)
        try:
            first = await queue.claim()
            assert first
            await analysis.run(first)
            await queue.done(first)
            parents = [parent]
            if not duplicate:
                for _ in range(11):
                    p, _ = f.create()
                    parents.append(p)
                    r = await queue.claim()
                    assert r
                    await analysis.run(r)
                    await queue.done(r)
            admissions = []
            for p in parents if not duplicate else [parent, parent]:
                create_explanation_task(f.app, f.identity, p, "offline_stub")
                r = await queue.claim()
                assert r
                await store.mark(r, "analyzing")
                _, req, _ = await store.load(r)
                request = BudgetRequest(
                    str(uuid4()),
                    req.body_hash,
                    req.facts_hash,
                    "deepseek",
                    "deepseek-flash",
                    req.prompt_version,
                    5000,
                    800,
                    COUNT_VERSION,
                    PRICING.version,
                    PRICING.cost(5000, 800),
                    "offline_stub",
                )
                admissions.append((PersistentAdmission(store, r), request))
            reservations = await asyncio.gather(*(a.reserve(q) for a, q in admissions))
            assert sum(r is not None for r in reservations) == (1 if duplicate else 10)
            with connect(f.app) as db:
                stage = db.execute("SELECT * FROM business.model_stage_budgets").fetchone()
                assert stage and stage["reserved_count"] == (1 if duplicate else 10)
                assert stage["reserved_nanos"] == (1 if duplicate else 10) * 3360000
                assert stage["halted"] == duplicate
                calls = db.execute("SELECT count(*) AS n FROM business.model_calls").fetchone()
                assert calls and calls["n"] == stage["reserved_count"]
        finally:
            await session.close(clean=True)

    asyncio.run(scenario())


def test_invalid_usage_readable_template_not_trusted_metadata(fixture: InventoryFixture) -> None:
    async def scenario(h: Harness) -> None:
        from commerceops.entrypoints.api import create_app
        from commerceops.entrypoints.explanation_http import ExplanationEndpoints
        from fastapi.testclient import TestClient

        child = await h.explain()
        assert h.f.row(child)["state"] == "completed" and len(h.calls) == 1
        client = TestClient(
            create_app(
                explanation_service=ExplanationEndpoints(h.f.app),
                identity_resolver=lambda _: h.f.identity,
            )
        )
        result = client.get(f"/tasks/{h.parent}/explanation")
        assert result.status_code == 200
        metadata = result.json()["result"]["metadata"]
        assert (
            metadata["usage"] is None
            and metadata["cost_estimate"] is None
            and metadata["stop_required"] is True
        )
        with connect(h.f.app) as db:
            row = db.execute("SELECT * FROM business.model_stage_budgets").fetchone()
            assert row and row["halted"] and row["reserved_count"] == 1

    asyncio.run(run(fixture, scenario, fault="over_budget"))


@pytest.mark.parametrize("change", ["grant", "identity", "auth_version"])
def test_route_revoked_before_provider_zero_requests(
    fixture: InventoryFixture, change: str
) -> None:
    from commerceops.infrastructure.queue import JobQueue

    async def scenario() -> None:
        f = fixture
        task, _ = create_intent_task(f.app, f.identity, RoutingInput(text="库存"), "offline_stub")
        with connect(f.owner) as db:
            if change == "grant":
                db.execute(
                    """UPDATE business.principal_shop_scopes SET enabled=false
                        WHERE principal_id=%s""",
                    (f.data.principal,),
                )
            elif change == "identity":
                db.execute("DELETE FROM business.identities WHERE id=%s", (f.identity.identity_id,))
            else:
                db.execute(
                    """UPDATE business.principals SET roles=ARRAY['approver'],
                    auth_version=auth_version+1 WHERE id=%s""",
                    (f.data.principal,),
                )
        calls = []

        def reject(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            raise AssertionError("revoked request reached transport")

        session = WorkerSession(f.app, f.data.organization)
        await session.start()
        try:
            queue = JobQueue(session)
            r = await queue.claim()
            assert r
            await IntentRunner(
                IntentStore(f.app, session),
                ProviderFactory(offline_transport=httpx.MockTransport(reject)),
            ).run(r)
            await queue.done(r)
            assert calls == [] and f.row(task)["state"] == "needs_attention"
            with connect(f.app) as db:
                count = db.execute("SELECT count(*) AS n FROM business.model_calls").fetchone()
                assert count and count["n"] == 0
        finally:
            await session.close(clean=True)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "barrier,revoked",
    [
        ("provider_returned", None),
        ("provider_returned", "identity"),
        ("provider_returned", "grant"),
        ("call_observation_committed", None),
    ],
)
def test_old_unknown_fences_earlier_queued_different_key(
    fixture: InventoryFixture, barrier: str, revoked: str | None
) -> None:
    import signal
    from dataclasses import replace
    from uuid import uuid4

    from commerceops.infrastructure.worker_lock import TerminationRequired, confirm_termination

    from tests.p204_support import ExplanationProcess

    f = fixture
    parent, parent_job = f.create()
    first = ExplanationProcess(f, barrier)
    second = None
    try:
        started = first.until("started")
        first.until("report_committed")
        asyncio.run(done(f, parent_job))
        original, job = create_explanation_task(f.app, f.identity, parent, "offline_stub")
        first.until("offline_http")
        first.until(barrier)
        principal, identity, conversation = uuid4(), uuid4(), uuid4()
        with connect(f.owner) as db:
            db.execute(
                """INSERT INTO business.principals(id,organization_id,display_name,roles)
                VALUES (%s,%s,'owned second actor',ARRAY['operator'])""",
                (principal, f.data.organization),
            )
            db.execute(
                """INSERT INTO business.identities
                (id,organization_id,principal_id,provider,app_id,tenant_key,external_subject)
                VALUES (%s,%s,%s,'technical_fixture',%s,%s,%s)""",
                (identity, f.data.organization, principal, f.data.app, f.data.tenant, str(uuid4())),
            )
            db.execute(
                "INSERT INTO business.principal_shop_scopes VALUES (%s,%s,%s,true)",
                (f.data.organization, f.data.shop, principal),
            )
            db.execute(
                """INSERT INTO business.conversations
                (id,organization_id,channel,chat_id,actor_id,topic_key)
                VALUES (%s,%s,'test',%s,%s,'owned intent')""",
                (conversation, f.data.organization, str(uuid4()), principal),
            )
        other_actor = replace(f.identity, principal_id=principal, identity_id=identity)
        other, other_job = create_intent_task(
            f.app, other_actor, RoutingInput(text="独立另一scope排队请求"), "offline_stub"
        )
        if revoked:
            with connect(f.owner) as db:
                if revoked == "identity":
                    db.execute(
                        "DELETE FROM business.identities WHERE id=%s", (f.identity.identity_id,)
                    )
                else:
                    db.execute(
                        """UPDATE business.principal_shop_scopes SET enabled=false
                        WHERE principal_id=%s""",
                        (f.data.principal,),
                    )
        first.process.kill()
        assert first.process.wait(timeout=15) == -signal.SIGKILL

        async def blocked() -> None:
            with pytest.raises(TerminationRequired):
                await WorkerSession(f.app, f.data.organization).start()

        asyncio.run(blocked())
        asyncio.run(
            confirm_termination(f.app, started["owner"], "P204 stage-wide owned SIGKILL wait proof")
        )
        second = ExplanationProcess(f)
        second.until("started")
        asyncio.run(done(f, other_job))
        asyncio.run(done(f, job))
        assert not any(row["event"] == "offline_http" for row in second.seen)
        assert f.row(other)["state"] == "completed"
        assert f.row(original)["state"] == ("needs_attention" if revoked else "completed")
        with connect(f.app) as db:
            stage = db.execute("SELECT * FROM business.model_stage_budgets").fetchone()
            assert (
                stage
                and stage["halted"]
                and stage["reserved_count"] == 1
                and stage["reserved_nanos"] == 3360000
            )
            calls = db.execute("SELECT * FROM business.model_calls").fetchall()
            assert len(calls) == 1 and str(calls[0]["worker_owner"]) == started["owner"]
            observation = db.execute("SELECT * FROM business.model_call_observations").fetchone()
            assert observation and observation["outcome"] == (
                "observed" if barrier == "call_observation_committed" else "uncertain"
            )
            assert observation["stop_required"] == (barrier != "call_observation_committed")
        second.process.send_signal(signal.SIGTERM)
        second.until("stopped")
        assert second.process.wait(timeout=15) == 0
    finally:
        first.close()
        if second:
            second.close()


@pytest.mark.parametrize(
    "scalar",
    ["4.5", "4/5", "4-5", "4~5", "4到5", "4 5", "4，5", "4５", "4天到5天", "4", "4天", "4，"],
)
def test_complete_parameter_token_controls_business_insert(
    fixture: InventoryFixture, scalar: str
) -> None:
    from commerceops.application.commerce.inventory_routing import (
        GuardedRouter,
        ModelRoute,
        ParameterCandidate,
    )
    from commerceops.entrypoints.api import create_app
    from commerceops.entrypoints.explanation_http import ExplanationEndpoints
    from fastapi.testclient import TestClient

    text = f"L={scalar} R=7 S=2"
    proposed = ModelRoute(
        intent="inventory_replenishment",
        evidence_mode="offline_stub",
        candidates=tuple(
            ParameterCandidate.model_validate(
                {
                    "name": name,
                    "value": value,
                    "start": start,
                    "end": start + 1,
                    "source": "explicit_text",
                }
            )
            for name, value, start in [
                ("L", 4, 2),
                ("R", 7, text.index("R=") + 2),
                ("S", 2, text.index("S=") + 2),
            ]
        ),
    )

    class Model:
        async def route(self, text: str) -> ModelRoute:
            return proposed

    client = TestClient(
        create_app(
            explanation_service=ExplanationEndpoints(fixture.app, GuardedRouter(Model())),
            identity_resolver=lambda _: fixture.identity,
        )
    )
    with connect(fixture.app) as db:
        before = db.execute(
            "SELECT count(*) AS n FROM business.business_tasks WHERE kind='inventory_analysis_only'"
        ).fetchone()
        assert before
    response = client.post("/test/route", json={"text": text})
    assert response.status_code == 200
    valid = scalar in ("4", "4天", "4，")
    assert response.json()["decision"]["intent"] == (
        "inventory_replenishment" if valid else "clarify"
    )
    with connect(fixture.app) as db:
        after = db.execute(
            "SELECT count(*) AS n FROM business.business_tasks WHERE kind='inventory_analysis_only'"
        ).fetchone()
        assert after
        assert after["n"] - before["n"] == int(valid)
