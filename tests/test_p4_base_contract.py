"""仅本地十五文本字段快照；不假定 A 尚未冻结的 PG DTO。"""

from typing import Any

import pytest
from commerceops.adapters.feishu.projection_contract import (
    BASE_FIELDS,
    ProjectionContractError,
    ProjectionFields,
)
from commerceops.adapters.feishu.projection_rules import is_current

pytestmark = pytest.mark.offline


def sample(**changes: str) -> ProjectionFields:
    return ProjectionFields.from_fields(
        {
            "CommerceOpsItemID": "00000000-0000-4000-8000-000000000041",
            "TaskID": "00000000-0000-4000-8000-000000000040",
            "SKU": "示例商品-甲",
            "Quantity": "100",
            "Risk": "risk",
            "Window": "[2026-10-01T00:00:00+00:00,2026-10-08T00:00:00+00:00)",
            "SourceMode": "mock",
            "ApprovalStatus": "approved",
            "ApprovedBy": "示例审批人",
            "BusinessStatus": "open",
            "ResolutionReason": "",
            "ResolvedBy": "",
            "ResolvedAt": "",
            "SyncVersion": "1",
            "UpdatedAt": "2026-10-11T03:00:00+00:00",
            **changes,
        }
    )


def terminal(**changes: str) -> ProjectionFields:
    return sample(
        **{
            "BusinessStatus": "completed",
            "SyncVersion": "2",
            "ResolutionReason": "内部跟进完成；不代表入库",
            "ResolvedBy": "示例处理人",
            "ResolvedAt": "2026-10-11T04:00:00+00:00",
            "UpdatedAt": "2026-10-11T04:00:00+00:00",
            **changes,
        }
    )


def test_snapshot_freezes_exact_fifteen_fields_and_does_not_leak_values() -> None:
    original = sample().as_fields()
    snapshot = ProjectionFields.from_fields(original)
    original["Quantity"] = "999"
    exported = snapshot.as_fields()
    exported["Quantity"] = "666"
    assert tuple(snapshot.as_fields()) == BASE_FIELDS
    assert snapshot.as_fields()["Quantity"] == "100"
    assert snapshot.wire_fields()["ResolvedAt"] is None
    assert "示例" not in repr(snapshot)
    assert is_current(snapshot, 1)
    assert not is_current(snapshot, 2)
    assert not is_current(terminal(), 1)


@pytest.mark.parametrize("status", ["completed", "closed"])
def test_terminal_pg_columns_are_projected_without_reopening(status: str) -> None:
    snapshot = terminal(BusinessStatus=status)
    assert snapshot.version == 2
    assert snapshot.wire_fields()["BusinessStatus"] == status
    assert snapshot.wire_fields()["ResolutionReason"] == "内部跟进完成；不代表入库"


@pytest.mark.parametrize(
    "key,value",
    [
        ("Quantity", "0"),
        ("Quantity", "1.0"),
        ("Quantity", "01"),
        ("Quantity", "-1"),
        ("Quantity", True),
        ("SyncVersion", "0"),
        ("SyncVersion", "1.0"),
        ("SyncVersion", "２"),
        ("SyncVersion", True),
        ("CommerceOpsItemID", "not-an-item"),
        ("TaskID", "not-a-task"),
        ("BusinessStatus", "pending"),
        ("ApprovalStatus", "pending"),
        ("ApprovedBy", ""),
        ("SKU", ""),
        ("UpdatedAt", "2026-10-11T03:00:00"),
        ("UpdatedAt", "not-a-date"),
        ("UpdatedAt", "2026-10-11T11:00:00+08:00"),
        ("ResolutionReason", "unauthorized-terminal"),
    ],
)
def test_invalid_serialized_fields_fail_closed_without_echo(key: str, value: Any) -> None:
    fields = sample().as_fields()
    fields[key] = value
    with pytest.raises(ProjectionContractError, match="^BASE_PROJECTION_CONTRACT_INVALID$"):
        ProjectionFields.from_fields(fields)


@pytest.mark.parametrize("key", ["ResolutionReason", "ResolvedBy", "ResolvedAt"])
def test_terminal_needs_all_resolution_columns(key: str) -> None:
    fields = terminal().as_fields()
    fields[key] = ""
    with pytest.raises(ProjectionContractError):
        ProjectionFields.from_fields(fields)


@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate", "mutable"])
def test_schema_and_immutable_constructor_cannot_bypass_validation(mutation: str) -> None:
    fields = sample().as_fields()
    if mutation == "missing":
        del fields["Risk"]
    elif mutation == "extra":
        fields["ProbeID"] = "must-not-reuse-probe"
    else:
        pairs: Any = tuple(fields.items())
        pairs = pairs[:-1] + (pairs[0],) if mutation == "duplicate" else list(pairs)
        with pytest.raises(ProjectionContractError):
            ProjectionFields(pairs)
        return
    with pytest.raises(ProjectionContractError):
        ProjectionFields.from_fields(fields)


@pytest.mark.parametrize("version", [True, 0, -1, "2"])
def test_current_pg_version_is_strict(version: Any) -> None:
    with pytest.raises(ProjectionContractError):
        is_current(sample(), version)
