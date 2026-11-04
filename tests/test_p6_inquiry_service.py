"""Offline DTO, explicit demo-source runtime and completed runner replay tests; no PG."""

import asyncio
import json
import threading
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from commerceops.adapters.commerce.mock import Fixture, MockCommerce
from commerceops.application.commerce.analysis_task import InventoryTaskRequest
from commerceops.application.commerce.inventory_analysis import analyze_inventory
from commerceops.application.commerce.inventory_facts import InventoryInput
from commerceops.application.commerce.readonly_inquiry_contracts import (
    Context,
    OrdersCall,
    ReportsCall,
    ToolCall,
)
from commerceops.application.commerce.readonly_inquiry_executor import Outcome
from commerceops.application.commerce.readonly_inquiry_service_contracts import (
    WORKFLOW,
    CreateInquiry,
    ResultPayload,
)
from commerceops.application.commerce.readonly_inquiry_service_demo import (
    DemoChoice,
    DomainReadPort,
    fixture_domain,
)
from commerceops.application.commerce.readonly_inquiry_tools import MockReadFacade
from commerceops.application.replenishment.contracts import WebActor
from commerceops.application.runner import RunRequest
from commerceops.infrastructure import readonly_inquiry_runtime
from commerceops.infrastructure import readonly_inquiry_store as inquiry_storage
from commerceops.infrastructure.readonly_inquiry_runtime import ServiceReadPort, db_call
from commerceops.infrastructure.readonly_inquiry_store import InquiryConfig, InquiryStore
from commerceops.workflows.readonly_inquiry import ReadonlyInquiryRunner, Runtime
from pydantic import ValidationError

pytestmark = pytest.mark.offline
DIRECTORY = Path(__file__).parent / "fixtures/commerce/inventory-v1"


def request_body() -> dict[str, object]:
    return {
        "schema_version": "p6-inquiry-web-v1",
        "shop_id": str(uuid4()),
        "question": "库存 合成演示商品 100",
        "context_report_id": None,
        "request_key": str(uuid4()),
    }


@pytest.mark.parametrize("key", ["identity", "role", "source_url", "model", "model_key", "budget"])
def test_create_does_not_accept_authority_or_provider_fields(key: str) -> None:
    body = request_body()
    body[key] = "untrusted"
    with pytest.raises(ValidationError):
        CreateInquiry.model_validate_json(json.dumps(body))


def test_strict_question_and_invalid_uuid() -> None:
    body = request_body()
    body["question"] = "  "
    with pytest.raises(ValueError):
        CreateInquiry.model_validate_json(json.dumps(body))
    body["question"] = "库存 DEMO"
    body["shop_id"] = True
    with pytest.raises(ValueError):
        CreateInquiry.model_validate_json(json.dumps(body))


class Identity:
    async def authorize(self, context: Context, call: ToolCall | None) -> bool:
        return True


class Session:
    async def check(self) -> None:
        pass


class MemoryRunnerStore:
    """Only runner control flow; does not stand in for SQL/role/transaction evidence."""

    def __init__(self) -> None:
        self.saved: ResultPayload | None = None
        self.marks = self.writes = 0

    def load(self, run: RunRequest) -> tuple[dict[str, Any], ResultPayload | None]:
        return {}, self.saved

    def mark(self, run: RunRequest) -> None:
        self.marks += 1

    def finish(self, run: RunRequest, result: ResultPayload) -> None:
        self.saved = result
        self.writes += 1

    def fail_safe(self, run: RunRequest, known: ResultPayload | None = None) -> None:
        raise AssertionError("unexpected failure settlement")


def run_request() -> RunRequest:
    task = uuid4()
    return RunRequest(
        uuid4(),
        task,
        uuid4(),
        uuid4(),
        str(task),
        WORKFLOW,
        "analyze",
        f"inquiry:{task}",
        str(uuid4()),
        1,
    )


def test_demo_same_executor_result_is_persistable_and_replay_does_not_rechoose() -> None:
    f = Fixture.load(DIRECTORY)
    store = MemoryRunnerStore()
    factories = 0

    async def factory(run: RunRequest, row: dict[str, Any]) -> Runtime:
        nonlocal factories
        factories += 1
        ctx = Context(
            request_id=str(run.task_id),
            principal_id="p",
            organization_id="o",
            shop_id=f.source.shop_id,
            identity_id="i",
            auth_version=1,
            source_binding=f.source.provenance.raw_hash,
            question="库存 合成演示商品 100",
        )
        domain = fixture_domain(f)
        return (
            ctx,
            DemoChoice(domain),
            Identity(),
            DomainReadPort(MockReadFacade(MockCommerce(f)), domain),
        )

    runner = ReadonlyInquiryRunner(store, Session(), factory)
    request = run_request()

    async def both() -> None:
        await runner.run(request)
        await runner.run(request)

    asyncio.run(both())
    assert factories == store.marks == store.writes == 1
    assert store.saved is not None and store.saved.status == "complete"
    assert store.saved.evidence_mode == "offline_stub" and store.saved.model_calls == 3
    assert ResultPayload.model_validate_json(store.saved.model_dump_json()) == store.saved
    assert (
        next(
            fact.value
            for result in store.saved.results
            for fact in result.facts
            if fact.metric == "available_stock"
        )
        == "20"
    )


def test_source_domain_stops_before_any_source_read() -> None:
    f = Fixture.load(DIRECTORY)
    source = MockCommerce(f)
    domain = fixture_domain(f)
    ctx = Context(
        request_id="q",
        principal_id="p",
        organization_id="o",
        shop_id=f.source.shop_id,
        identity_id="i",
        auth_version=1,
        source_binding=f.source.provenance.raw_hash,
        question="销量 DEMO",
    )
    call = OrdersCall.model_validate_json(
        json.dumps(
            {
                "tool_call_id": "c",
                "name": "commerce.read_orders",
                "args": {
                    "skus": [f.products[0].sku_key],
                    "windows": [
                        {
                            "start": (domain.start - timedelta(days=1)).isoformat(),
                            "end": domain.end.isoformat(),
                        }
                    ],
                },
            }
        )
    )
    result = asyncio.run(
        DomainReadPort(MockReadFacade(source), domain).read(ctx, call, 10**12, 10000)
    )
    assert not result.complete and result.quality_flags == ("SOURCE_DOMAIN_UNAVAILABLE",)
    assert source.call_counts == {}


def test_failure_payload_cannot_publish_results() -> None:
    payload = ResultPayload.from_outcome(Outcome("access_denied", 0, 0, 0, ()))
    data = json.loads(payload.model_dump_json())
    data["evidence_mode"] = "actual_provider"
    with pytest.raises(ValueError):
        ResultPayload.model_validate_json(json.dumps(data))


def test_cancelled_database_call_waits_for_thread_termination() -> None:
    started, release, stopped = threading.Event(), threading.Event(), threading.Event()

    def work() -> int:
        started.set()
        release.wait(1)
        stopped.set()
        return 1

    async def scenario() -> None:
        task = asyncio.create_task(db_call(work))
        await asyncio.to_thread(started.wait, 1)
        task.cancel()
        await asyncio.sleep(0.01)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert stopped.is_set()

    asyncio.run(scenario())


@pytest.mark.parametrize("fault", [None, "hash_invalid", "report_tampered", "not_completed"])
def test_report_read_uses_one_owned_transaction_and_validates_frozen_report(
    monkeypatch: pytest.MonkeyPatch, fault: str | None
) -> None:
    # Connection/authority doubles exercise the boundary, not actual PG authorization.
    f = Fixture.load(DIRECTORY)
    report = analyze_inventory(
        InventoryInput(
            source=f.source,
            now=f.now,
            products=f.products,
            order_lines=f.orders,
            refunds=f.refunds,
            inventories=f.inventories,
            complete=True,
        )
    )
    run = run_request()
    report_id, snapshot_id = uuid4(), uuid4()
    evidence: dict[str, Any] = {
        "id": report_id,
        "snapshot_id": snapshot_id,
        "source_state": "queued" if fault == "not_completed" else "completed",
        "report": report.model_dump(mode="json"),
        "snapshot_content": InventoryInput(
            source=f.source,
            now=f.now,
            products=f.products,
            order_lines=f.orders,
            refunds=f.refunds,
            inventories=f.inventories,
            complete=True,
        ).model_dump(mode="json"),
        "normalized_request": InventoryTaskRequest().model_dump(mode="json"),
        "window_start": report.window.start,
        "window_end": report.window.end,
        "content_hash": "a" * 64,
        "outcome": "report_ready",
    }
    if fault == "report_tampered":
        evidence["report"]["items"][0]["gross_units"] = 999
    actor = WebActor(uuid4(), uuid4(), uuid4(), run.organization_id, 1)
    connections: list[Any] = []

    class Database:
        current: dict[str, Any]
        closed = False

        def __enter__(self) -> "Database":
            return self

        def __exit__(self, *_: Any) -> None:
            self.closed = True

        def execute(self, sql: str, args: object) -> "Database":
            self.current = (
                {"valid": fault != "hash_invalid"} if "valid_inventory_result" in sql else evidence
            )
            return self

        def fetchone(self) -> dict[str, Any]:
            return self.current

    class Store:
        settings: Any = None
        inquiry: Any

        def __init__(self) -> None:
            self.inquiry = self

        def fixture(self) -> Fixture:
            return f

        def run_row(self, db: Database, request: RunRequest) -> dict[str, Any]:
            assert not db.closed and request == run
            return {"shop_id": run.shop_id}

        def actor(self, row: dict[str, Any]) -> WebActor:
            return actor

        def report_task(self, db: Database, subject: WebActor, shop: object, rid: object) -> object:
            assert subject == actor and shop == run.shop_id and rid == report_id
            return uuid4()

    def connect(settings: Any) -> Database:
        db = Database()
        connections.append(db)
        return db

    monkeypatch.setattr(readonly_inquiry_runtime, "connect", connect)
    port = ServiceReadPort(Store(), run, fixture_domain(f))  # type: ignore[arg-type]
    context = Context(
        request_id=str(run.task_id),
        principal_id=str(actor.principal_id),
        organization_id=str(actor.organization_id),
        shop_id=f.source.shop_id,
        identity_id=str(actor.identity_id),
        auth_version=1,
        source_binding=f.source.provenance.raw_hash,
        question="解释报告",
    )
    call = ReportsCall.model_validate_json(
        json.dumps(
            {
                "tool_call_id": "report",
                "name": "reports.read",
                "args": {"report_id": str(report_id)},
            }
        )
    )
    if fault is None:
        result = port.read_report(context, call)
        assert result.complete and result.snapshot_id == str(snapshot_id)
        assert result.facts[0].value == "70"
    else:
        with pytest.raises(ValueError):
            port.read_report(context, call)
    assert len(connections) == 1 and connections[0].closed


def test_database_call_propagates_inner_cancellation_without_spinning() -> None:
    def work() -> int:
        raise asyncio.CancelledError

    async def scenario() -> None:
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(db_call(work), 1)

    asyncio.run(scenario())


def test_runner_denied_load_settles_only_safe_failure() -> None:
    from commerceops.application.replenishment.contracts import WebFailure

    class Denied(MemoryRunnerStore):
        def load(self, run: RunRequest) -> tuple[dict[str, Any], ResultPayload | None]:
            raise WebFailure("SESSION_INVALID", 401)

        def fail_safe(self, run: RunRequest, known: ResultPayload | None = None) -> None:
            assert known is None
            self.saved = ResultPayload.safe_failure(known)

    async def forbidden(*args: Any) -> Any:
        raise AssertionError("no model/source runtime after denied load")

    store = Denied()
    asyncio.run(ReadonlyInquiryRunner(store, Session(), forbidden).run(run_request()))
    assert (
        store.saved is not None
        and store.saved.results == ()
        and store.saved.status == "access_denied"
    )


def test_real_executor_finish_revocation_preserves_usage_in_safe_sql_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full runner/executor/store flow; transport/authorization doubles, no PG proof."""
    from commerceops.application.replenishment.contracts import WebFailure

    fixture = Fixture.load(DIRECTORY)
    request = run_request()
    row: dict[str, Any] = {
        "task_id": request.task_id,
        "organization_id": request.organization_id,
        "principal_id": uuid4(),
        "state": "queued",
        "task_state": "queued",
        "result": None,
        "result_canonical": None,
        "result_hash": None,
    }
    writes: list[dict[str, Any]] = []

    class Transport:
        def __enter__(self) -> "Transport":
            return self

        def __exit__(self, *_: Any) -> None:
            pass

        def execute(self, statement: str, args: Any = None) -> "Transport":
            if "UPDATE business.readonly_inquiries SET state='analyzing'" in statement:
                row["state"] = "analyzing"
            elif "UPDATE business.readonly_inquiries SET state='failed'" in statement:
                stored = json.loads(args[1])
                assert stored == args[0].obj
                row.update(
                    state="failed",
                    result=stored,
                    result_canonical=args[1],
                    result_hash=args[2],
                )
                writes.append(stored)
            elif "UPDATE business.business_tasks SET state='analyzing'" in statement:
                row["task_state"] = "analyzing"
            elif "UPDATE business.business_tasks SET state='failed'" in statement:
                row["task_state"] = "failed"
            return self

        def fetchone(self) -> dict[str, bool]:
            return {"valid": True}

    class Store(InquiryStore):
        revoked = False
        attempted: ResultPayload | None = None

        def owned_row(self, db: Any, run: RunRequest) -> dict[str, Any]:
            assert run == request
            return dict(row)

        def run_row(self, db: Any, run: RunRequest) -> dict[str, Any]:
            if self.revoked:
                raise WebFailure("ACCESS_DENIED", 403)
            return self.owned_row(db, run)

        def finish(self, run: RunRequest, result: ResultPayload) -> None:
            self.attempted = result
            self.revoked = True
            super().finish(run, result)

    monkeypatch.setattr(inquiry_storage, "connect", lambda _: Transport())
    # All persistence calls still use the actual InquiryStore methods above.
    config: Any = SimpleNamespace(database=None)
    store = Store(config, InquiryConfig(request.shop_id, DIRECTORY, enabled=True))

    async def factory(run: RunRequest, state: dict[str, Any]) -> Runtime:
        context = Context(
            request_id=str(run.task_id),
            principal_id=str(row["principal_id"]),
            organization_id=str(run.organization_id),
            shop_id=fixture.source.shop_id,
            identity_id="current-test-identity",
            auth_version=1,
            source_binding=fixture.source.provenance.raw_hash,
            question="库存 合成演示商品 100",
        )
        domain = fixture_domain(fixture)
        return (
            context,
            DemoChoice(domain),
            Identity(),
            DomainReadPort(MockReadFacade(MockCommerce(fixture)), domain),
        )

    runner = ReadonlyInquiryRunner(store, Session(), factory)
    asyncio.run(runner.run(request))
    attempted = store.attempted
    assert attempted is not None and attempted.status == "complete" and attempted.results
    assert (attempted.model_calls, attempted.tool_calls, attempted.scanned_rows) == (3, 2, 3)
    assert len(writes) == 1 and row["state"] == row["task_state"] == "failed"
    saved = ResultPayload.model_validate_json(row["result_canonical"])
    assert (saved.model_calls, saved.tool_calls, saved.scanned_rows) == (3, 2, 3)
    assert saved.traces == attempted.traces and len(saved.traces) == 2
    assert saved.status == "access_denied"
    assert saved.results == ()
    assert saved.claims == ()
    assert saved.evidence_refs == ()
    assert saved.clarification_options == ()
    assert "sku/demo" not in saved.model_dump_json()
    # Same durable failed receipt is reused; no additional model, tool or result write.
    asyncio.run(runner.run(request))
    assert len(writes) == 1 and ResultPayload.model_validate_json(row["result_canonical"]) == saved
