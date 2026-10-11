"""B 实际采用 A d039 的共享输入/输出/唯一字段规范，不保留临时 DTO。"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from commerceops.adapters.feishu import projection_contract as contract
from commerceops.application.feishu_business import contracts as shared

pytestmark = pytest.mark.offline


def sample(**changes: Any) -> contract.ItemProjection:
    return contract.ItemProjection(
        **{
            "item_id": UUID("00000000-0000-4000-8000-000000000041"),
            "task_id": UUID("00000000-0000-4000-8000-000000000040"),
            "sku": "示例商品-甲",
            "quantity": 100,
            "risk": "risk",
            "window": "[2026-10-01T00:00:00+00:00,2026-10-08T00:00:00+00:00)",
            "source_mode": "mock",
            "approval_status": "approved",
            "approved_by": "示例审批人",
            "business_status": "open",
            "sync_version": 1,
            "updated_at": datetime(2026, 10, 11, 3, tzinfo=UTC),
            **changes,
        }
    )


def terminal(**changes: Any) -> contract.ItemProjection:
    return sample(
        **{
            "business_status": "completed",
            "sync_version": 2,
            "resolution_reason": "内部跟进完成；不代表入库",
            "resolved_by": "示例处理人",
            "resolved_at": datetime(2026, 10, 11, 4, tzinfo=UTC),
            "updated_at": datetime(2026, 10, 11, 4, tzinfo=UTC),
            **changes,
        }
    )


def request(
    projection: contract.ItemProjection | None = None, **changes: Any
) -> contract.ProjectionRequest:
    return contract.ProjectionRequest(
        **{
            "outbox_id": UUID("00000000-0000-4000-8000-000000000043"),
            "organization_id": UUID("00000000-0000-4000-8000-000000000044"),
            "shop_id": UUID("00000000-0000-4000-8000-000000000045"),
            "target_key": "test",
            "operation": "reconcile",
            "client_token": UUID("00000000-0000-4000-8000-000000000042"),
            "projection": projection or sample(),
            **changes,
        }
    )


def test_reexports_are_identical_shared_classes_and_functions() -> None:
    for name in (
        "ItemProjection",
        "ProjectionRequest",
        "ProjectionResult",
        "BaseProjectionAdapter",
        "bind_projection_result",
        "normalize_projection_fields",
        "BASE_FIELDS",
    ):
        assert getattr(contract, name) is getattr(shared, name)
    assert not hasattr(contract, "ProjectionFields")


def test_exact_shared_fifteen_fields_numeric_types_and_explicit_null() -> None:
    projection = sample()
    fields = projection.fields()
    assert tuple(fields) == contract.BASE_FIELDS
    assert type(fields["Quantity"]) is int and type(fields["SyncVersion"]) is int
    assert fields["ResolvedAt"] is None
    fields["Quantity"] = 999
    assert projection.fields()["Quantity"] == 100
    assert contract.normalize_projection_fields(projection.fields()) == projection.fields()


@pytest.mark.parametrize("status", ["completed", "closed"])
def test_terminal_mapping_is_exact_pg_state_reason_actor_time(status: str) -> None:
    fields = terminal(business_status=status).fields()
    assert fields["BusinessStatus"] == status and fields["SyncVersion"] == 2
    assert fields["ResolutionReason"] == "内部跟进完成；不代表入库"
    assert fields["ResolvedAt"] == "2026-10-11T04:00:00+00:00"


@pytest.mark.parametrize(
    "key,value",
    [
        ("Quantity", True),
        ("Quantity", 1.0),
        ("Quantity", "100"),
        ("Quantity", 0),
        ("SyncVersion", True),
        ("SyncVersion", 1.0),
        ("SyncVersion", "2"),
        ("SyncVersion", 0),
        ("CommerceOpsItemID", None),
        ("TaskID", ""),
        ("Risk", None),
        ("SKU", ""),
        ("ApprovalStatus", None),
        ("UpdatedAt", None),
    ],
)
def test_remote_wrong_shapes_are_rejected_by_unique_shared_normalizer(key: str, value: Any) -> None:
    fields = sample().fields()
    fields[key] = value
    with pytest.raises(ValueError):
        contract.normalize_projection_fields(fields)


@pytest.mark.parametrize("key", contract.BASE_FIELDS)
def test_unique_normalizer_never_fills_missing_keys(key: str) -> None:
    fields = sample().fields()
    del fields[key]
    with pytest.raises(ValueError, match="INCOMPLETE_PROJECTION_READBACK"):
        contract.normalize_projection_fields(fields)
