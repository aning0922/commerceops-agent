"""inventory-rule-v1：纯整数/Fraction库存规则，无框架、存储或授权副作用。"""

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from typing import Literal

from commerceops.domain.commerce_values import identifier, integer

RULE_VERSION = "inventory-rule-v1"
DISPLAY_VERSION = "inventory-display-v1"
MAX_CANDIDATES = 20


class Risk(StrEnum):
    RISK = "risk"
    STOCKOUT = "stockout"
    NORMAL = "normal"
    NO_RECENT_DEMAND = "no_recent_demand"
    MANUAL_CHECK = "manual_check"
    QUALITY_BLOCKED = "quality_blocked"


@dataclass(frozen=True)
class RuleParameters:
    L: int = 3
    R: int = 7
    S: int = 2
    rule_version: Literal["inventory-rule-v1"] = "inventory-rule-v1"
    parameter_mode: Literal["demo_assumption"] = "demo_assumption"

    def __post_init__(self) -> None:
        if any(integer(value) < 0 for value in (self.L, self.R, self.S)):
            raise ValueError("INVALID_PARAMETERS")
        if self.rule_version != RULE_VERSION or self.parameter_mode != "demo_assumption":
            raise ValueError("UNSUPPORTED_PARAMETERS")


@dataclass(frozen=True)
class Evaluation:
    D: Fraction | None
    A: int | None
    inbound_units: int | None
    effective_inbound_units: int
    T: int | None
    trigger: Fraction | None
    risk: Risk
    suggested_units: int | None
    coverage: Fraction | None
    coverage_reason: str | None
    required_assumptions: tuple[str, ...]
    hard_blocks: tuple[str, ...]
    can_form_suggestion: bool


def evaluate_inventory(
    *,
    sku_key: str,
    gross_units: int | None,
    available_stock: int | None,
    inbound_units: int | None,
    parameters: RuleParameters,
    hard_blocks: tuple[str, ...] = (),
) -> Evaluation:
    if type(parameters) is not RuleParameters:
        raise ValueError("INVALID_PARAMETERS")
    parameters.__post_init__()
    identifier(sku_key)
    if gross_units is not None and integer(gross_units) < 0:
        raise ValueError("INVALID_DEMAND")
    if available_stock is not None:
        integer(available_stock)
    if inbound_units is not None and integer(inbound_units) < 0:
        raise ValueError("INVALID_INBOUND")
    blocks = {identifier(block) for block in hard_blocks}
    demand = Fraction(gross_units, 7) if gross_units is not None else None
    if demand is None:
        blocks.add("SOURCE_INCOMPLETE")
    if available_stock is None:
        blocks.add("UNKNOWN_STOCK")
    effective = 0 if inbound_units is None else inbound_units
    target = None
    trigger = None
    if demand is not None:
        exact_target = demand * (parameters.L + parameters.R + parameters.S)
        target = -(-exact_target.numerator // exact_target.denominator)
        trigger = demand * (parameters.L + parameters.S)

    coverage = None
    if demand is None:
        coverage_reason = "INCOMPLETE_DEMAND"
    elif demand == 0:
        coverage_reason = "NO_RECENT_DEMAND"
    elif available_stock is None:
        coverage_reason = "UNKNOWN_STOCK"
    elif available_stock < 0:
        coverage_reason = "BACKLOG_STOCK"
    else:
        coverage = Fraction(available_stock, 1) / demand
        coverage_reason = None

    quantity = None
    if blocks:
        risk = (
            Risk.MANUAL_CHECK
            if blocks & {"SHARED_POOL_UNRESOLVED", "OPEN_WORK_ITEM"}
            else Risk.QUALITY_BLOCKED
        )
    else:
        if demand is None or available_stock is None or trigger is None:
            raise ValueError("INVALID_RULE_INPUT")
        if demand == 0:
            risk = Risk.NO_RECENT_DEMAND if available_stock > 0 else Risk.MANUAL_CHECK
        elif available_stock <= 0:
            risk = Risk.STOCKOUT
        elif available_stock <= trigger:
            risk = Risk.RISK
        else:
            risk = Risk.NORMAL
        if risk in {Risk.RISK, Risk.STOCKOUT}:
            if target is None:
                raise ValueError("INVALID_RULE_INPUT")
            quantity = max(0, target - available_stock - effective)
    can_form = quantity is not None and quantity > 0
    assumptions = (f"inbound_unknown_zero:{sku_key}",) if can_form and inbound_units is None else ()
    return Evaluation(
        demand,
        available_stock,
        inbound_units,
        effective,
        target,
        trigger,
        risk,
        quantity,
        coverage,
        coverage_reason,
        assumptions,
        tuple(sorted(blocks)),
        can_form,
    )


def display_fraction(value: Fraction | None) -> str | None:
    """精确整数舍入到六位 HALF_EVEN，展示值不参与规则或canonical事实。"""
    if value is None:
        return None
    scaled, remainder = divmod(abs(value.numerator) * 1_000_000, value.denominator)
    if remainder * 2 > value.denominator or (remainder * 2 == value.denominator and scaled % 2):
        scaled += 1
    sign = "-" if value < 0 and scaled else ""
    return f"{sign}{scaled // 1_000_000}.{scaled % 1_000_000:06d}"
