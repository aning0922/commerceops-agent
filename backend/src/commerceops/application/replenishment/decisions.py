"""T3纯语义hash与精确确认集合；身份/期限/nonce由锁后PG用例负责。"""

from typing import Any

from commerceops.application.replenishment.contracts import DecisionInput, WebFailure
from commerceops.domain.commerce_values import facts_hash


def decision_hash(request: DecisionInput) -> str:
    return facts_hash(
        {
            "approval_id": str(request.approval_id),
            "plan_id": str(request.plan_id),
            "plan_version": request.plan_version,
            "plan_hash": request.plan_hash,
            "action": request.action,
            "acknowledged_assumption_keys": sorted(request.acknowledged_assumption_keys),
        }
    )


def decision_request_hash(request: DecisionInput, path: str) -> str:
    body = request.model_dump(mode="json", exclude={"request_key"})
    body["acknowledged_assumption_keys"] = sorted(request.acknowledged_assumption_keys)
    return facts_hash({"path": path, "body": body})


def confirm_set(request: DecisionInput, plan: dict[str, Any]) -> None:
    if not plan.get("disclosure_complete") or plan.get("hard_blocks"):
        raise WebFailure("DATA_INCOMPLETE")
    expected = sorted(item["key"] for item in plan["required_assumptions"])
    actual = sorted(request.acknowledged_assumption_keys)
    if request.action == "approve" and expected:
        raise WebFailure("ASSUMPTION_ACK_REQUIRED")
    if request.action == "approve_with_assumptions" and (not expected or actual != expected):
        raise WebFailure("ASSUMPTION_SET_MISMATCH")
    if request.action == "reject_assumptions" and not expected:
        raise WebFailure("ASSUMPTION_SET_MISMATCH")
