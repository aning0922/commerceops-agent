"""R13/R14/R16 离线 Fake；不证明 PG 事务/锁或真实 Base 完整性。"""

import asyncio
from typing import Any
from uuid import UUID

import pytest
from commerceops.adapters.feishu import projection_contract as contract
from commerceops.adapters.feishu.business_base import reconcile as scan
from commerceops.adapters.feishu.projection_rules import (
    WriteOutcome,
    write_outcome,
)

from tests.test_p4_base_contract import request, sample, terminal


def reconcile(
    transport: contract.RecordTransport,
    app_token: str,
    table_id: str,
    projection: contract.ItemProjection,
    *,
    expected_record_id: str | None = None,
    max_pages: int = 100,
) -> contract.ProjectionResult:
    return asyncio.run(
        scan(
            transport,
            app_token,
            table_id,
            request(projection, external_id=expected_record_id),
            max_pages=max_pages,
        )
    )


pytestmark = pytest.mark.offline
CURSOR = "page-2"


def row(
    fields: contract.ItemProjection | None = None, identifier: str = "synthetic-row"
) -> dict[str, Any]:
    return {"record_id": identifier, "fields": (fields or sample()).fields()}


def page(items: list[dict[str, Any]], **changes: Any) -> contract.ApiReply:
    return contract.ApiReply(
        200, 0, {"items": items, "has_more": False, "total": len(items), **changes}
    )


class FakeRecords:
    def __init__(self, pages: list[contract.ApiReply | Exception]):
        self.pages = pages
        self.cursors: list[str | None] = []
        self.creates: list[str] = []
        self.updates: list[str] = []
        self.persisted: list[dict[str, Any]] = []

    async def create(
        self,
        app_token: str,
        table_id: str,
        token: str,
        fields: contract.ItemProjection,
        *,
        deadline: float | None = None,
    ) -> contract.ApiReply:
        self.creates.append(token)
        self.persisted.append(row(fields))
        # 远端 Fake 已写，ACK 丢失；未暗中重试。
        return contract.ApiReply(None, None)

    async def list(
        self,
        app_token: str,
        table_id: str,
        page_token: str | None,
        *,
        deadline: float | None = None,
    ) -> contract.ApiReply:
        self.cursors.append(page_token)
        reply = self.pages[len(self.cursors) - 1]
        if isinstance(reply, Exception):
            raise reply
        return reply

    async def update(
        self,
        app_token: str,
        table_id: str,
        record_id: str,
        fields: contract.ItemProjection,
        *,
        deadline: float | None = None,
    ) -> contract.ApiReply:
        self.updates.append(record_id)
        self.persisted = [row(fields, record_id)]
        return contract.ApiReply(None, None)


def test_ack_loss_recovery_uses_full_original_key_and_only_reads() -> None:
    fake = FakeRecords([])
    token = "00000000-0000-4000-8000-000000000042"  # noqa: S105 - synthetic stable UUIDv4
    assert write_outcome(asyncio.run(fake.create("test-base", "test-table", token, sample()))) == (
        WriteOutcome.UNKNOWN
    )
    other = row(sample(item_id=UUID("00000000-0000-4000-8000-000000000099")), "other-row")
    fake.pages = [
        page([other], has_more=True, page_token=CURSOR, total=2),
        page(fake.persisted, total=2),
    ]
    result = reconcile(fake, "test-base", "test-table", sample())
    assert result.outcome == "verified"
    assert result.external_id == "synthetic-row"
    assert fake.cursors == [None, "page-2"]
    assert fake.creates == [token] and fake.updates == []


def test_update_ack_loss_restores_only_same_record_and_exact_terminal_version() -> None:
    fake = FakeRecords([])
    assert write_outcome(
        asyncio.run(fake.update("test-base", "test-table", "synthetic-row", terminal()))
    ) == (WriteOutcome.UNKNOWN)
    fake.pages = [page(fake.persisted)]
    result = reconcile(
        fake, "test-base", "test-table", terminal(), expected_record_id="synthetic-row"
    )
    assert result.outcome == "verified"
    assert result.external_id == "synthetic-row"
    assert fake.creates == [] and fake.updates == ["synthetic-row"]


@pytest.mark.parametrize(
    "items,expected",
    [
        ([], "unknown"),
        ([row(), row(identifier="duplicate-row")], "conflict"),
        ([row(), row()], "unknown"),
        ([row(sample(quantity=101))], "unknown"),
        ([row(terminal())], "stale"),
    ],
)
def test_zero_duplicate_mismatched_or_newer_rows_do_not_restore_external_link(
    items: list[dict[str, Any]],
    expected: str,
) -> None:
    fake = FakeRecords([page(items)])
    result = reconcile(fake, "test-base", "test-table", sample())
    assert result.outcome == expected
    assert result.outcome != "verified"
    assert fake.creates == [] and fake.updates == []


def test_old_version_and_wrong_record_id_do_not_restore_update() -> None:
    result = reconcile(FakeRecords([page([row()])]), "test-base", "test-table", terminal())
    assert result.outcome == "unknown" and not result.content_matches
    result = reconcile(
        FakeRecords([page([row()])]),
        "test-base",
        "test-table",
        sample(),
        expected_record_id="different-row",
    )
    assert result.outcome == "conflict" and result.external_id is None


@pytest.mark.parametrize(
    "key",
    [
        "TaskID",
        "SKU",
        "Quantity",
        "Risk",
        "Window",
        "SourceMode",
        "ApprovalStatus",
        "ApprovedBy",
        "BusinessStatus",
        "SyncVersion",
        "UpdatedAt",
    ],
)
def test_each_required_missing_field_fails_readback(key: str) -> None:
    item = row()
    del item["fields"][key]
    result = reconcile(FakeRecords([page([item])]), "test-base", "test-table", sample())
    assert result.outcome == "unknown"
    assert result.external_id is None


def test_missing_resolution_fields_are_incomplete_while_explicit_null_is_empty() -> None:
    item = row()
    for key in ("ResolvedBy", "ResolvedAt", "ResolutionReason"):
        del item["fields"][key]
    fake = FakeRecords([page([item])])
    assert reconcile(fake, "test-base", "test-table", sample()).outcome == "unknown"
    item = row()
    for key in ("ResolvedBy", "ResolvedAt", "ResolutionReason"):
        item["fields"][key] = None
    assert reconcile(FakeRecords([page([item])]), "test-base", "test-table", sample()).outcome == (
        "verified"
    )
    item = row(terminal())
    del item["fields"]["ResolutionReason"]
    assert reconcile(
        FakeRecords([page([item])]), "test-base", "test-table", terminal()
    ).outcome == ("unknown")


@pytest.mark.parametrize(
    "reply",
    [
        contract.ApiReply(200, 1254291),
        contract.ApiReply(503, 0),
        TimeoutError("private"),
        contract.ApiReply(200, 0, {"items": [], "has_more": False}),
        page([row()], has_more=True),
        page([row()], has_more="false"),
        page([row()], total=2),
        page([row()], total=True),
        page([row()], has_more=True, page_token="", total=2),
        page([], has_more=True, page_token=CURSOR, total=2),
        page([{"record_id": "broken", "fields": {}}]),
    ],
)
def test_pagination_or_http_failure_does_not_use_partial_match(
    reply: contract.ApiReply | Exception,
) -> None:
    fake = FakeRecords([reply])
    result = reconcile(fake, "test-base", "test-table", sample())
    assert result.outcome == "unknown" and result.external_id is None
    assert fake.creates == [] and fake.updates == []


@pytest.mark.parametrize(
    "second",
    [
        contract.ApiReply(500, 1255040),
        TimeoutError("private-second-page"),
        page([row(identifier="second")], has_more=True, page_token=CURSOR, total=2),
        page([], total=1),
        page([], total=2),
    ],
)
def test_match_on_page_one_cannot_mask_later_failure_or_cursor_loop(
    second: contract.ApiReply | Exception,
) -> None:
    fake = FakeRecords(
        [
            page([row()], has_more=True, page_token=CURSOR, total=2),
            second,
        ]
    )
    result = reconcile(fake, "test-base", "test-table", sample())
    assert result.outcome == "unknown" and result.external_id is None
    assert len(fake.cursors) == 2


def test_limit_exhaustion_is_incomplete_and_stale_snapshot_never_selected_for_write() -> None:
    fake = FakeRecords([page([row()], has_more=True, page_token=CURSOR, total=2)])
    assert reconcile(fake, "test-base", "test-table", sample(), max_pages=1).outcome == ("unknown")
    assert fake.creates == [] and fake.updates == []


def test_all_pages_share_one_absolute_deadline_and_query_cancellation_does_not_write() -> None:
    class WaitingRecords(FakeRecords):
        def __init__(self) -> None:
            super().__init__([])
            self.deadlines: list[float | None] = []
            self.cancelled = False

        async def list(
            self,
            app_token: str,
            table_id: str,
            page_token: str | None,
            *,
            deadline: float | None = None,
        ) -> contract.ApiReply:
            self.cursors.append(page_token)
            self.deadlines.append(deadline)
            if page_token is None:
                return page([row()], has_more=True, page_token=CURSOR, total=2)
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled = True
            raise AssertionError("unreachable")

    fake = WaitingRecords()

    async def run() -> contract.ProjectionResult:
        deadline = asyncio.get_running_loop().time() + 0.02
        return await scan(fake, "test-base", "test-table", request(), deadline=deadline)

    result = asyncio.run(run())
    assert result.outcome == "unknown" and result.external_id is None
    assert len(fake.deadlines) == 2 and fake.deadlines[0] == fake.deadlines[1]
    assert fake.cancelled and fake.creates == [] and fake.updates == []
