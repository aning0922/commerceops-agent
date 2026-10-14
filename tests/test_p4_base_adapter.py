"""实际 A d039 Protocol + B adapter 全操作离线契约；无 PG/真实平台。"""

import asyncio
from typing import Any

import pytest
from commerceops.adapters.feishu import business_base as base
from commerceops.adapters.feishu import projection_contract as contract
from commerceops.application.feishu_business import contracts as shared

from tests.test_p4_base_contract import request, sample, terminal
from tests.test_p4_base_reconciliation import page, row

pytestmark = pytest.mark.offline


class MemoryRecords:
    def __init__(
        self, rows: list[dict[str, Any]] | None = None, reply: contract.ApiReply | None = None
    ):
        self.rows = rows or []
        self.reply = reply
        self.calls: list[tuple[str, str | None, float | None]] = []

    async def list(
        self,
        app_token: str,
        table_id: str,
        page_token: str | None,
        *,
        deadline: float | None = None,
    ) -> contract.ApiReply:
        self.calls.append(("query", page_token, deadline))
        return page(self.rows)

    async def create(
        self,
        app_token: str,
        table_id: str,
        token: str,
        projection: contract.ItemProjection,
        *,
        deadline: float | None = None,
    ) -> contract.ApiReply:
        self.calls.append(("create", token, deadline))
        if self.reply is not None:
            if self.reply.http_status is None:
                self.rows.append(row(projection))  # Fake已成功，但ACK丢失。
            return self.reply
        self.rows.append(row(projection))
        return contract.ApiReply(200, 0, {"record": {"record_id": "synthetic-row"}})

    async def update(
        self,
        app_token: str,
        table_id: str,
        record_id: str,
        projection: contract.ItemProjection,
        *,
        deadline: float | None = None,
    ) -> contract.ApiReply:
        self.calls.append(("update", record_id, deadline))
        self.rows = [row(projection, record_id)]
        return self.reply or contract.ApiReply(200, 0, {"record": {"record_id": record_id}})


def execute(
    fake: contract.RecordTransport, value: contract.ProjectionRequest
) -> contract.ProjectionResult:
    adapter: contract.BaseProjectionAdapter = base.BusinessBaseAdapter(
        fake, {"test": ("test-base", "test-table")}
    )
    return asyncio.run(adapter.project(value))


def test_shared_protocol_create_once_full_readback_and_unique_binding_called(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[contract.ProjectionRequest, contract.ProjectionResult]] = []
    original = shared.bind_projection_result

    def bind(
        value: contract.ProjectionRequest, result: contract.ProjectionResult
    ) -> contract.ProjectionResult:
        calls.append((value, result))
        return original(value, result)

    monkeypatch.setattr(base, "bind_projection_result", bind)
    fake = MemoryRecords()
    value = request(operation="create")
    result = execute(fake, value)
    assert result.outcome == "verified" and result.observed_version == 1
    assert result.observed_fields == sample().fields()
    assert result.complete and result.matched_count == 1 and result.content_matches
    assert [call[0] for call in fake.calls] == ["query", "create", "query"]
    assert fake.calls[1][1] == str(value.client_token)
    assert len({call[2] for call in fake.calls}) == 1
    assert len(calls) == 1 and calls[0][0] == value
    assert original(value, result).outcome == "verified"


@pytest.mark.parametrize("state", ["completed", "closed"])
def test_update_current_terminal_snapshot_of_same_original_row_once(state: str) -> None:
    fake = MemoryRecords([row()])
    value = request(
        terminal(business_status=state), operation="update", external_id="synthetic-row"
    )
    result = execute(fake, value)
    assert result.outcome == "verified" and result.observed_version == 2
    assert result.observed_fields == value.projection.fields()
    assert [call[0] for call in fake.calls] == ["query", "update", "query"]
    assert len({call[2] for call in fake.calls}) == 1


@pytest.mark.parametrize("operation", ["create", "update", "reconcile"])
def test_same_version_already_verified_or_higher_version_is_readonly(operation: str) -> None:
    external = "synthetic-row" if operation != "create" else None
    fake = MemoryRecords([row()])
    value = request(operation=operation, external_id=external)
    assert execute(fake, value).outcome == "verified"
    assert [call[0] for call in fake.calls] == ["query"]
    fake = MemoryRecords([row(terminal())])
    result = execute(fake, value)
    assert result.outcome == "stale" and result.observed_version == 2
    assert [call[0] for call in fake.calls] == ["query"]


@pytest.mark.parametrize("operation", ["create", "update", "reconcile"])
def test_wrong_content_duplicate_missing_fields_or_record_never_writes(operation: str) -> None:
    external = "synthetic-row" if operation != "create" else None
    value = request(operation=operation, external_id=external)
    missing = row()
    del missing["fields"]["SKU"]
    for rows in ([row(sample(quantity=101))], [row(), row(identifier="duplicate")], [missing]):
        fake = MemoryRecords(rows)
        assert execute(fake, value).outcome in {"unknown", "conflict"}
        assert [call[0] for call in fake.calls] == ["query"]
    if external:
        fake = MemoryRecords([row(identifier="wrong-record")])
        assert execute(fake, value).outcome == "conflict"
        assert [call[0] for call in fake.calls] == ["query"]


def test_older_row_immutable_content_mismatch_does_not_authorize_update() -> None:
    fake = MemoryRecords([row(sample(quantity=101))])
    value = request(terminal(), operation="update", external_id="synthetic-row")
    assert execute(fake, value).outcome == "unknown"
    assert [call[0] for call in fake.calls] == ["query"]


def test_ack_loss_then_new_adapter_reconciles_same_item_and_token_without_recreate() -> None:
    fake = MemoryRecords(reply=contract.ApiReply(None, None))
    value = request(operation="create")
    first = execute(fake, value)
    assert first.outcome == "unknown" and not first.write_rejected
    recovered = execute(fake, request())
    assert recovered.outcome == "verified"
    assert [call[0] for call in fake.calls] == ["query", "create", "query"]
    assert fake.calls[1][1] == str(value.client_token) and len(fake.rows) == 1


@pytest.mark.parametrize(
    "status,code,outcome,rejected",
    [
        (200, 1254290, "retryable", True),
        (200, 1254291, "retryable", True),
        (429, 1254290, "retryable", True),
        (429, 9999999, "unknown", False),
        (429, None, "unknown", False),
        (503, 1254291, "unknown", False),
        (200, 1255001, "unknown", False),
        (200, 9999999, "unknown", False),
        (200, 1254045, "fatal", False),
        (400, 1255006, "conflict", False),
        (403, 1254608, "unknown", False),
        (400, 1254607, "unknown", False),
    ],
)
def test_write_fault_is_one_attempt_specific_rejection_or_unknown_no_automatic_retry(
    status: int,
    code: int | None,
    outcome: str,
    rejected: bool,
) -> None:
    fake = MemoryRecords(reply=contract.ApiReply(status, code))
    result = execute(fake, request(operation="create"))
    assert result.outcome == outcome and result.write_rejected is rejected
    assert [call[0] for call in fake.calls] == ["query", "create"]
    if outcome == "retryable":
        assert result.retry_after_seconds == 1
    else:
        assert result.retry_after_seconds is None


def test_reconcile_zero_rows_and_update_missing_row_never_blind_create() -> None:
    for value in (request(), request(terminal(), operation="update", external_id="synthetic-row")):
        fake = MemoryRecords()
        result = execute(fake, value)
        assert result.outcome == "unknown" and result.code == "ITEM_MISSING"
        assert [call[0] for call in fake.calls] == ["query"]


def test_total_query_budget_is_shared_by_preflight_and_postwrite() -> None:
    fake = MemoryRecords()
    result = execute(fake, request(operation="create", max_pages=1))
    assert result.outcome == "unknown" and result.code == "READBACK_BUDGET_EXHAUSTED"
    assert [call[0] for call in fake.calls] == ["query"]
    fake = MemoryRecords()
    assert execute(fake, request(operation="create", max_pages=2)).outcome == "verified"
    assert [call[0] for call in fake.calls] == ["query", "create", "query"]


def test_invalid_model_copy_and_target_do_not_reach_transport() -> None:
    fake = MemoryRecords()
    bad = request(operation="create").model_copy(update={"timeout_seconds": 11})
    assert execute(fake, bad).outcome == "fatal"
    assert execute(fake, request(target_key="absent")).code == "TARGET_NOT_CONFIGURED"
    assert fake.calls == []


@pytest.mark.parametrize("boundary", ["preflight", "write", "readback"])
def test_one_operation_deadline_cancels_at_each_boundary_without_reset_or_retry(
    boundary: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class WaitingRecords(MemoryRecords):
        cancelled = False

        async def list(
            self,
            app_token: str,
            table_id: str,
            page_token: str | None,
            *,
            deadline: float | None = None,
        ) -> contract.ApiReply:
            result = await super().list(app_token, table_id, page_token, deadline=deadline)
            if boundary == "preflight" or (boundary == "readback" and len(self.calls) == 3):
                try:
                    await asyncio.Event().wait()
                finally:
                    self.cancelled = True
            return result

        async def create(
            self,
            app_token: str,
            table_id: str,
            token: str,
            projection: contract.ItemProjection,
            *,
            deadline: float | None = None,
        ) -> contract.ApiReply:
            result = await super().create(app_token, table_id, token, projection, deadline=deadline)
            if boundary == "write":
                try:
                    await asyncio.Event().wait()
                finally:
                    self.cancelled = True
            return result

    fake = WaitingRecords()
    original = base.operation_deadline

    def short_deadline(deadline: float | None = None) -> float:
        proposed = original(deadline)
        return min(proposed, asyncio.get_running_loop().time() + 0.03)

    monkeypatch.setattr(base, "operation_deadline", short_deadline)
    result = execute(fake, request(operation="create"))
    assert result.outcome == "unknown" and not result.write_rejected and fake.cancelled
    expected_calls = {"preflight": 1, "write": 2, "readback": 3}
    assert len(fake.calls) == expected_calls[boundary]
    assert len({call[2] for call in fake.calls}) == 1
