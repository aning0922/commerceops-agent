"""endpoint特定无损转换；PG expectation/完整分页/严格DTO仍是必要门禁。"""

from typing import Any

import pytest
from commerceops.adapters.feishu.projection_rules import MAX_WIRE_INTEGER, wire_integer

from tests.test_p4_base_contract import sample, terminal
from tests.test_p4_base_reconciliation import FakeRecords, page, reconcile, row

pytestmark = pytest.mark.offline


@pytest.mark.parametrize(
    "value", [1, 100, MAX_WIRE_INTEGER, 1.0, 100.0, "1", "100", str(MAX_WIRE_INTEGER)]
)
def test_supported_lossless_positive_integer_forms(value: Any) -> None:
    assert wire_integer(value) == int(value)


@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        None,
        0,
        -1,
        0.0,
        -1.0,
        0.5,
        float("inf"),
        float("-inf"),
        float("nan"),
        MAX_WIRE_INTEGER + 1,
        float(MAX_WIRE_INTEGER + 1),
        str(MAX_WIRE_INTEGER + 1),
        "",
        "0",
        "-1",
        "+1",
        "01",
        "1.0",
        "1e2",
        "100tail",
        " 100",
        "100 ",
        "１",
        {},
        [],
        "9" * 100,
    ],
)
def test_unknown_fractional_nonfinite_overflow_bool_and_suffix_rejected(value: Any) -> None:
    with pytest.raises(ValueError, match="INVALID_BASE_WIRE_INTEGER"):
        wire_integer(value)


def test_list_numeric_strings_and_three_expected_empty_omissions_are_strictly_bound() -> None:
    item = row()
    item["fields"]["Quantity"] = str(sample().quantity)
    item["fields"]["SyncVersion"] = "1"
    for key in ("ResolutionReason", "ResolvedBy", "ResolvedAt"):
        del item["fields"][key]
    result = reconcile(FakeRecords([page([item])]), "test-base", "test-table", sample())
    assert result.outcome == "verified" and result.observed_fields == sample().fields()
    assert type(sample().fields()["Quantity"]) is int
    assert type(sample().fields()["SyncVersion"]) is int


@pytest.mark.parametrize("key", ["Quantity", "SyncVersion", "SKU", "UpdatedAt"])
def test_wire_compatibility_does_not_make_different_values_equal(key: str) -> None:
    item = row()
    item["fields"][key] = "999" if key in ("Quantity", "SyncVersion") else "different"
    assert (
        reconcile(FakeRecords([page([item])]), "test-base", "test-table", sample()).outcome
        != "verified"
    )


@pytest.mark.parametrize("key", ["ResolutionReason", "ResolvedBy", "ResolvedAt"])
def test_omission_of_expected_nonempty_terminal_field_is_incomplete(key: str) -> None:
    item = row(terminal())
    del item["fields"][key]
    assert (
        reconcile(FakeRecords([page([item])]), "test-base", "test-table", terminal()).code
        == "INCOMPLETE_READBACK"
    )


def test_wire_conversion_does_not_relax_global_unique_or_complete_pages() -> None:
    item = row()
    item["fields"]["Quantity"] = str(sample().quantity)
    assert (
        reconcile(
            FakeRecords([page([item, row(identifier="second")])]),
            "test-base",
            "test-table",
            sample(),
        ).outcome
        == "conflict"
    )
    assert (
        reconcile(
            FakeRecords([page([item], has_more=True)]), "test-base", "test-table", sample()
        ).outcome
        == "unknown"
    )
