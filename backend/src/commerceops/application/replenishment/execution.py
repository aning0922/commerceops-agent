"""T4重观测实质事实与永久执行hash；不负责当前授权或副作用事务。"""

import copy
from typing import Any

from commerceops.application.commerce.analysis_task import CollectedInventory
from commerceops.application.commerce.inventory_analysis import (
    _native_input_value,
    analyze_inventory,
)
from commerceops.application.commerce.inventory_facts import InventoryInput, InventoryReport
from commerceops.application.replenishment.contracts import (
    ResolveInput,
    analysis_request_from_parameters,
)
from commerceops.domain.commerce_values import canonical_bytes, complete_days, facts_hash
from commerceops.domain.inventory_rules import RuleParameters


def verified_observation(
    collected: CollectedInventory, parameters: dict[str, Any]
) -> tuple[InventoryInput, InventoryReport, dict[str, Any]]:
    """重新严格验证原生输入并计算；不接受caller填充报告/数量/质量。"""
    request = analysis_request_from_parameters(parameters)
    data = InventoryInput.model_validate(_native_input_value(collected.data))
    report = analyze_inventory(data, RuleParameters(request.L, request.R, request.S))
    normalized = data.model_dump(mode="json")
    normalized["window"] = report.window.model_dump(mode="json")
    for refund in normalized["refunds"]:
        refund["lines"] = sorted(refund["lines"], key=canonical_bytes)
    for field in ("products", "order_lines", "refunds", "inventories", "open_items", "warnings"):
        normalized[field] = sorted(normalized[field], key=canonical_bytes)
    if report.input_hash != facts_hash(normalized):
        raise ValueError("REVALIDATION_INPUT_HASH_MISMATCH")
    return data, report, normalized


def material_hash(data: InventoryInput, parameters: dict[str, Any]) -> str:
    """仅忽略读取/捕获时间；所有订单、退款、质量、库存、在途与open项保留。"""
    value = copy.deepcopy(data.model_dump(mode="json"))
    if value["window"] is None:
        start, end = complete_days(data.now, data.source.timezone)
        value["window"] = {"start": start, "end": end}
    value.pop("now")
    value["source"]["provenance"].pop("captured_at", None)
    value["source"]["provenance"].pop("raw_hash", None)
    for collection in ("products", "order_lines", "refunds", "inventories"):
        for row in value[collection]:
            row["source"].pop("captured_at", None)
            row["source"].pop("raw_hash", None)
            if collection == "inventories":
                row.pop("observed_at", None)
            if collection == "refunds":
                row["lines"] = sorted(row["lines"], key=canonical_bytes)
            row["source"]["quality_flags"] = sorted(row["source"]["quality_flags"])
        value[collection] = sorted(value[collection], key=canonical_bytes)
    value["open_items"] = sorted(value["open_items"], key=canonical_bytes)
    value["warnings"] = sorted(value["warnings"])
    value["source"]["provenance"]["quality_flags"] = sorted(
        value["source"]["provenance"]["quality_flags"]
    )
    return facts_hash(
        {
            "material_version": "p3-revalidation-material-v1",
            "input": value,
            "parameters": parameters,
        }
    )


def operation_key(plan: dict[str, Any]) -> str:
    return f"restock:{plan['shop_id']}:{plan['id']}:{plan['version']}"


def execution_hash(plan: dict[str, Any], approval: dict[str, Any]) -> str:
    return facts_hash(
        {
            "execution_hash_version": "p3-execution-v1",
            "plan_id": str(plan["id"]),
            "plan_version": plan["version"],
            "plan_hash": plan["plan_hash"],
            "approval_id": str(approval["id"]),
            "decision_id": str(approval["decision_id"]),
            "decision_payload_hash": approval["decision_payload_hash"],
        }
    )


def resolution_hash(item: str, request: ResolveInput) -> str:
    return facts_hash(
        {
            "item_id": item,
            "action": request.action,
            "reason": request.reason.strip(),
            "expected_version": request.expected_version,
        }
    )
