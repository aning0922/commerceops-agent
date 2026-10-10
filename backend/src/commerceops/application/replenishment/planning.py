"""p3-plan-hash-v1纯事实冻结；无金额猜测、客户端数量或LLM决策。"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from commerceops.application.commerce.inventory_facts import InventoryReport
from commerceops.domain.commerce_values import canonical_bytes, facts_hash, integer


class PlanRejected(ValueError):
    pass


@dataclass(frozen=True)
class FrozenPlan:
    content: dict[str, Any]
    canonical_content: str
    plan_hash: str


def freeze_plan(
    *,
    organization_id: UUID,
    shop_id: UUID,
    task_id: UUID,
    plan_id: UUID,
    version: int,
    source: dict[str, Any],
    report: InventoryReport,
    expires_at: datetime,
    parameters: dict[str, Any],
    config_version: str,
    max_items: int = 20,
) -> FrozenPlan | None:
    if type(max_items) is not int or type(version) is not int:
        raise PlanRejected("INVALID_REQUEST")
    if not 1 <= integer(max_items) <= 20 or integer(version) < 1:
        raise PlanRejected("INVALID_REQUEST")
    if report.scope_required or report.candidate_count > max_items:
        raise PlanRejected("SCOPE_REQUIRED")
    if (
        not report.complete
        or not report.source_complete
        or any(i.hard_blocks for i in report.items)
    ):
        raise PlanRejected("DATA_INCOMPLETE")
    candidates = sorted(
        (i for i in report.items if i.can_form_suggestion and i.suggested_units),
        key=lambda i: i.sku_key,
    )
    if not candidates:
        if report.requires_review:
            raise PlanRejected("DATA_INCOMPLETE")
        return None
    if len(candidates) > max_items:
        raise PlanRejected("SCOPE_REQUIRED")
    items: list[dict[str, Any]] = []
    assumptions: list[dict[str, Any]] = []
    pools: set[str] = set()
    for fact in candidates:
        if fact.stock_pool_key is None or fact.open_item_ids or fact.stock_pool_key in pools:
            raise PlanRejected("DATA_INCOMPLETE")
        pools.add(fact.stock_pool_key)
        expected = (f"inbound_unknown_zero:{fact.sku_key}",) if fact.inbound_units is None else ()
        if fact.required_assumptions != expected:
            raise PlanRejected("DATA_INCOMPLETE")
        for key in expected:
            assumptions.append(
                {
                    "key": key,
                    "type": "inbound_unknown_zero",
                    "sku_key": fact.sku_key,
                    "estimated_units": 0,
                    "disclosure_version": "inbound-unknown-zero-v1",
                }
            )
        items.append(
            {
                "sku_key": fact.sku_key,
                "sku_label": fact.sku_label,
                "stock_pool_key": fact.stock_pool_key,
                "quantity": fact.suggested_units,
                "raw_inbound_units": fact.inbound_units,
                "effective_inbound_units": fact.effective_inbound_units,
                "fact": fact.model_dump(mode="json"),
            }
        )
    content = {
        "schema_version": "p3-web-v1",
        "hash_version": "p3-plan-hash-v1",
        "organization_id": str(organization_id),
        "shop_id": str(shop_id),
        "task_id": str(task_id),
        "plan_id": str(plan_id),
        "plan_version": version,
        "source": source,
        "currency": report.source.currency,
        "rule_version": report.rule_version,
        "parameters": parameters,
        "config_version": config_version,
        "window": report.window.model_dump(mode="json"),
        "expires_at": expires_at,
        "items": items,
        "item_count": len(items),
        "total_units": sum(i["quantity"] for i in items),
        "required_assumptions": sorted(assumptions, key=lambda a: a["key"]),
        "hard_blocks": [],
        "quality_flags": sorted(set(report.warnings)),
        "disclosure_complete": True,
    }
    encoded = canonical_bytes(content).decode()
    # 返回经过同一canonical编码的JSON-native内容，时间统一UTC Z，raw null不变。
    return FrozenPlan(json.loads(encoded), encoded, facts_hash(content))
