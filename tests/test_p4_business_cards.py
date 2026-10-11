"""正式20SKU卡片全披露/完整联合假设与版本hash，不发送技术probe卡。"""

import asyncio
import copy
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from commerceops.adapters.feishu.business_cards import build_business_card
from commerceops.application.commerce.analysis_task import InventoryTaskRequest
from commerceops.application.commerce.inventory_analysis import analyze_inventory
from commerceops.application.replenishment.planning import freeze_plan
from commerceops.domain.inventory_rules import RuleParameters

from tests.e2e.web.live_item_worker import twenty

pytestmark = pytest.mark.offline


def full_plan() -> tuple[dict[str, Any], dict[str, Any]]:
    collected = asyncio.run(twenty(InventoryTaskRequest()).collect())
    report = analyze_inventory(collected.data, RuleParameters())
    frozen = freeze_plan(
        organization_id=UUID(int=1),
        shop_id=UUID(int=2),
        task_id=UUID(int=3),
        plan_id=UUID(int=4),
        version=1,
        report=report,
        source={
            "source_task_id": str(UUID(int=5)),
            "report_id": str(UUID(int=6)),
            "snapshot_id": str(UUID(int=7)),
            "facts_hash": report.facts_hash,
            "collected_at": collected.collected_at,
        },
        expires_at=datetime(2026, 10, 12, tzinfo=UTC),
        parameters={
            "source_mode": "mock",
            "dataset_version": "inventory-v1",
            "fixture_case": "baseline",
            "L": 3,
            "R": 7,
            "S": 2,
        },
        config_version="p3-config-v1",
    )
    assert frozen
    return frozen.content, {
        "id": UUID(int=8),
        "plan_id": UUID(int=4),
        "plan_version": 1,
        "plan_hash": frozen.plan_hash,
    }


def test_real_frozen_report_twenty_card_includes_all_sku_quantity_and_unknown_keys() -> None:
    content, approval = full_plan()
    card = build_business_card(content, approval, "n" * 43)
    assert (
        card["schema"] == "2.0" and content["item_count"] == 20 and content["total_units"] == 2000
    )
    body = card["body"]["elements"][0]["content"]
    for item in content["items"]:
        assert item["sku_label"] in body and str(item["quantity"]) in body
    approve = card["body"]["elements"][1]["behaviors"][0]["value"]
    reject = card["body"]["elements"][2]["behaviors"][0]["value"]
    assert approve["action"] == "approve_with_assumptions"
    assert approve["acknowledged_assumption_keys"] == [
        r["key"] for r in content["required_assumptions"]
    ]
    assert reject["action"] == "reject_assumptions" and reject["acknowledged_assumption_keys"] == []
    assert "actor" not in approve and "quantity" not in approve and "probe_id" not in approve


@pytest.mark.parametrize("mutation", ["truncated", "quantity", "version", "hash"])
def test_card_refuses_partial_or_unbound_approval(mutation: str) -> None:
    content, approval = full_plan()
    content = copy.deepcopy(content)
    if mutation == "truncated":
        content["items"] = content["items"][:1]
    elif mutation == "quantity":
        content["items"][0]["quantity"] += 1
    elif mutation == "version":
        approval["plan_version"] = 2
    else:
        approval["plan_hash"] = "a" * 64
    with pytest.raises(ValueError):
        build_business_card(content, approval, "n" * 43)
