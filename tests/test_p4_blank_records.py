"""完整扫描中的空白行仅表示无 item key；坏行与严格匹配规则保持。"""

import pytest
from commerceops.adapters.feishu.projection_rules import readback_rows

from tests.test_p4_base_contract import request, terminal
from tests.test_p4_base_reconciliation import CURSOR, FakeRecords, page, reconcile, row

pytestmark = pytest.mark.offline


def blank(identifier: str) -> dict[str, object]:
    return {"record_id": identifier, "fields": {}}


def test_complete_blank_multi_page_is_missing_without_anchor() -> None:
    value = request()
    fake = FakeRecords(
        [
            page([blank("blank-1")], has_more=True, total=2, page_token="next"),  # noqa: S106
            page([blank("blank-2")], total=2),
        ]
    )
    result = reconcile(fake, "fake", "fake", value.projection)
    assert result.code == "ITEM_MISSING" and result.complete
    assert result.external_id is None and result.matched_count == 0
    assert not fake.creates and not fake.updates


def test_blank_plus_one_complete_match_preserves_strict_binding() -> None:
    value = request()
    result = readback_rows(value, [blank("blank-1"), row(), blank("blank-2")])
    assert result.outcome == "verified" and result.complete and result.matched_count == 1
    assert result.external_id == "synthetic-row"


@pytest.mark.parametrize(
    "broken",
    [
        {"fields": {}},
        {"record_id": "", "fields": {}},
        {"record_id": None, "fields": {}},
        {"record_id": 1, "fields": {}},
        {"record_id": "bad"},
        {"record_id": "bad", "fields": None},
        {"record_id": "bad", "fields": []},
        {"record_id": "bad", "fields": {"SKU": "partial"}},
        {"record_id": "bad", "fields": {"CommerceOpsItemID": None}},
        {"record_id": "bad", "fields": {"CommerceOpsItemID": 1}},
    ],
)
def test_blank_exception_never_swallows_malformed_or_partial_row(broken: object) -> None:
    result = readback_rows(request(), [broken])  # type: ignore[list-item]
    assert result.outcome == "unknown" and result.code == "INCOMPLETE_READBACK"


def test_blank_duplicate_record_id_still_rejects_whole_scan() -> None:
    result = readback_rows(request(), [blank("same"), blank("same")])
    assert result.outcome == "unknown" and result.code == "INCOMPLETE_READBACK"


def test_blank_does_not_relax_matched_nullable_key_requirement() -> None:
    matched = row()
    del matched["fields"]["ResolvedAt"]
    result = readback_rows(request(), [blank("blank"), matched])
    assert result.outcome == "unknown" and result.code == "INCOMPLETE_READBACK"


def test_blank_keeps_double_match_anchor_conflict_and_newer_version() -> None:
    assert (
        readback_rows(request(), [blank("blank"), row(), row(identifier="second")]).outcome
        == "conflict"
    )
    assert (
        readback_rows(request(external_id="other"), [blank("blank"), row()]).outcome == "conflict"
    )
    assert readback_rows(request(), [blank("blank"), row(terminal())]).outcome == "stale"


@pytest.mark.parametrize(
    "pages",
    [
        [page([blank("blank")], has_more=True, total=1)],
        [page([blank("blank")], total=2)],
        [
            page([blank("blank")], has_more=True, total=2, page_token=CURSOR),
            page([blank("second")], total=3),
        ],
        [
            page([blank("same")], has_more=True, total=2, page_token=CURSOR),
            page([blank("same")], total=2),
        ],
    ],
)
def test_blank_requires_complete_consistent_pagination_before_missing(pages: list) -> None:
    result = reconcile(FakeRecords(pages), "fake", "fake", request().projection)
    assert result.outcome == "unknown" and result.external_id is None
