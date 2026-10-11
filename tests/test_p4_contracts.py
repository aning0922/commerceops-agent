"""P4共享接口负例与完整投影：离线，不调用平台或PG。"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid1, uuid4

import pytest
from commerceops.application.feishu_business.contracts import (
    BASE_FIELDS,
    ItemProjection,
    ProjectionRequest,
    ProjectionResult,
)
from pydantic import ValidationError

pytestmark = pytest.mark.offline


def item(**changes: Any) -> ItemProjection:
    body: dict[str, Any] = {
        "item_id": uuid4(),
        "task_id": uuid4(),
        "sku": "SKU-演示",
        "quantity": 100,
        "risk": "replenishment_risk",
        "window": "2026-10-01/2026-10-08",
        "source_mode": "mock",
        "approval_status": "approved",
        "approved_by": "审批人",
        "business_status": "open",
        "sync_version": 1,
        "updated_at": datetime(2026, 10, 11, tzinfo=UTC),
    }
    return ItemProjection(**(body | changes))


def test_all_fifteen_columns_and_blank_resolution_are_preserved() -> None:
    fields = item().fields()
    assert tuple(fields) == BASE_FIELDS
    assert len(fields) == 15
    assert fields["Quantity"] == 100
    assert fields["BusinessStatus"] == "open"
    assert fields["ResolutionReason"] is fields["ResolvedBy"] is fields["ResolvedAt"] is None


@pytest.mark.parametrize(
    "changes",
    [
        {"quantity": True},
        {"quantity": 1.5},
        {"quantity": "100"},
        {"quantity": 0},
        {"business_status": "completed"},
        {"business_status": "closed"},
        {"resolution_reason": "隐藏终态"},
        {"updated_at": datetime(2026, 10, 11)},
        {"sync_version": 0},
        {"source_mode": "live"},
        {"actor": "伪造"},
    ],
)
def test_projection_rejects_unsafe_values(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        item(**changes)


def test_terminal_all_three_fields_are_required_and_projected() -> None:
    instant = datetime(2026, 10, 11, tzinfo=UTC)
    fields = item(
        business_status="closed",
        resolution_reason="需求取消",
        resolved_by="审批人",
        resolved_at=instant,
        sync_version=2,
    ).fields()
    assert fields["BusinessStatus"] == "closed"
    assert fields["ResolutionReason"] == "需求取消"
    assert fields["ResolvedAt"] == instant.isoformat()
    assert fields["SyncVersion"] == 2


@pytest.mark.parametrize(
    "changes",
    [
        {"client_token": uuid1()},
        {"timeout_seconds": 11},
        {"max_pages": 101},
        {"operation": "update"},
        {"external_id": "record-already-exists"},
    ],
)
def test_request_requires_original_uuid4_and_bounded_transport(changes: dict[str, Any]) -> None:
    body: dict[str, Any] = {
        "outbox_id": uuid4(),
        "organization_id": uuid4(),
        "shop_id": uuid4(),
        "target_key": "m1-test",
        "operation": "create",
        "client_token": uuid4(),
        "projection": item(),
    }
    with pytest.raises(ValidationError):
        ProjectionRequest(**(body | changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"complete": False},
        {"matched_count": 0},
        {"matched_count": 2},
        {"content_matches": False},
        {"observed_version": None},
        {"external_id": None},
    ],
)
def test_verified_requires_unique_complete_full_content_readback(changes: dict[str, Any]) -> None:
    body: dict[str, Any] = {
        "outcome": "verified",
        "code": "READBACK_MATCH",
        "external_id": "record",
        "observed_version": 1,
        "complete": True,
        "matched_count": 1,
        "content_matches": True,
    }
    with pytest.raises(ValidationError):
        ProjectionResult(**(body | changes))


def test_unknown_cannot_claim_retry_policy() -> None:
    with pytest.raises(ValidationError):
        ProjectionResult(outcome="unknown", code="ACK_LOST", retry_after_seconds=1)


def test_retryable_requires_evidence_of_explicit_no_write() -> None:
    with pytest.raises(ValidationError):
        ProjectionResult(outcome="retryable", code="HTTP_500", retry_after_seconds=1)
    result = ProjectionResult(
        outcome="retryable",
        code="EXPLICIT_RATE_REJECTION",
        retry_after_seconds=1,
        write_rejected=True,
    )
    assert result.write_rejected
