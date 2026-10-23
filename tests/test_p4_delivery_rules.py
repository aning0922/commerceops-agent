"""A/B原键v1未知→T6v2组合边界；实际B adapter+Fake transport，平台0。"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from commerceops.adapters.feishu.business_base import BusinessBaseAdapter
from commerceops.adapters.feishu.projection_contract import ApiReply
from commerceops.application.feishu_business.contracts import ProjectionResult
from commerceops.application.feishu_business.delivery import (
    DeliveryGate,
    disposition,
    next_operation,
)
from commerceops.infrastructure.feishu_base_delivery import item_snapshot

from tests.test_p4_base_adapter import MemoryRecords
from tests.test_p4_base_contract import request, sample, terminal

pytestmark = pytest.mark.offline


def test_unknown_create_then_t6_anchors_only_original_v1_before_controlled_v2_update() -> None:
    async def case() -> None:
        fake = MemoryRecords(reply=ApiReply(None, None))
        adapter = BusinessBaseAdapter(fake, {"test": ("synthetic-base", "synthetic-table")})
        original = request(operation="create")
        unknown = disposition(
            original, await adapter.project(original), current_version=2, attempts=1
        )
        assert unknown.status == "unknown" and unknown.anchor is None and not unknown.current_synced
        assert next_operation(status="pending", version=2, anchor=None, attempts=0) is None
        reconcile = original.model_copy(update={"operation": "reconcile"})
        verified = disposition(
            reconcile, await adapter.project(reconcile), current_version=2, attempts=2
        )
        assert verified.status == "verified" and verified.anchor == "synthetic-row"
        assert verified.observed_version == 1 and not verified.current_synced
        assert (
            next_operation(status="pending", version=2, anchor=verified.anchor, attempts=0)
            == "update"
        )
        fake.reply = None
        current = request(
            terminal(), operation="update", external_id=verified.anchor, client_token=uuid4()
        )
        done = disposition(current, await adapter.project(current), current_version=2, attempts=1)
        assert done.current_synced and done.observed_version == 2 and done.anchor == verified.anchor
        assert [c[0] for c in fake.calls] == [
            "query",
            "create",
            "query",
            "query",
            "update",
            "query",
        ]
        assert fake.calls[1][1] == str(original.client_token) and len(fake.rows) == 1

    asyncio.run(case())


@pytest.mark.parametrize("attempts", [0, 1, 2])
def test_unknown_any_age_never_selects_a_second_write(attempts: int) -> None:
    assert (
        next_operation(status="unknown", version=1, anchor=None, attempts=attempts) == "reconcile"
    )
    assert (
        next_operation(status="unknown", version=2, anchor="original", attempts=attempts)
        == "reconcile"
    )


def test_full_original_readback_is_required_even_after_t6_or_fake_verified_claim() -> None:
    original = request(operation="reconcile")
    fake = ProjectionResult(
        outcome="verified",
        code="CLAIM",
        external_id="synthetic-row",
        observed_version=1,
        complete=True,
        matched_count=1,
        content_matches=True,
    )
    missing = disposition(original, fake, current_version=2, attempts=1)
    assert missing.status == "unknown" and missing.anchor is None and not missing.current_synced
    newer = fake.model_copy(update={"observed_version": 2, "observed_fields": terminal().fields()})
    held = disposition(original, newer, current_version=2, attempts=2)
    assert held.status == "stale" and held.anchor is None and not held.current_synced


def test_retryable_readback_cannot_revive_unknown_create_or_exceed_write_budget() -> None:
    result = ProjectionResult(outcome="retryable", code="KNOWN_REJECTION", write_rejected=True)
    assert disposition(request(), result, current_version=1, attempts=1).status == "unknown"
    assert (
        disposition(request(operation="create"), result, current_version=1, attempts=1).status
        == "pending"
    )
    assert (
        disposition(request(operation="create"), result, current_version=1, attempts=3).status
        == "fatal"
    )
    assert next_operation(status="unknown", version=1, anchor=None, attempts=3) is None


def test_v1_snapshot_after_t6_does_not_copy_terminal_v2_fields_or_update_time() -> None:
    created, resolved = datetime(2026, 10, 11, 3, tzinfo=UTC), datetime(2026, 10, 11, 4, tzinfo=UTC)
    row: dict[str, Any] = dict(
        id=sample().item_id,
        task_id=sample().task_id,
        version=2,
        sku_key="one",
        quantity=100,
        approved_by=uuid4(),
        status="completed",
        resolution_reason="完成",
        resolved_by=uuid4(),
        resolved_at=resolved,
        created_at=created,
        updated_at=resolved,
    )
    plan = {
        "items": [{"sku_key": "one", "quantity": 100, "fact": {"risk": "risk"}}],
        "window": {"start": "start", "end": "end"},
    }
    original, current = item_snapshot(row, plan, 1), item_snapshot(row, plan, 2)
    assert original.business_status == "open" and original.updated_at == created
    assert original.resolution_reason is None
    assert original.resolved_at is None and original.resolved_by is None
    assert current.business_status == "completed" and current.updated_at == resolved
    assert current.resolution_reason == "完成"
    with pytest.raises(ValueError):
        item_snapshot({**row, "quantity": 99}, plan, 1)


def test_delivery_gate_defaults_off_and_old_window_never_reopens() -> None:
    settings: dict[str, Any] = dict(
        organization_id=uuid4(),
        shop_id=uuid4(),
        task_ids=frozenset({uuid4()}),
        target_key="synthetic",
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
    )
    assert not DeliveryGate(**settings).active()
    assert DeliveryGate(**settings, enabled=True).active()
    assert not DeliveryGate(
        **{**settings, "expires_at": datetime.now(UTC) - timedelta(seconds=1)}, enabled=True
    ).active()
