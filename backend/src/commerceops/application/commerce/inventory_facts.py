"""analysis-only输入/精确事实DTO；不创建snapshot、plan或业务实体。"""

from fractions import Fraction
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from commerceops.application.commerce.contracts import (
    Digest,
    Identifier,
    Inventory,
    NonnegativeUnits,
    OrderLine,
    PositiveUnits,
    Product,
    Quality,
    Refund,
    Source,
    Timestamp,
    Units,
    Window,
)
from commerceops.domain.commerce_values import canonical_bytes, facts_hash
from commerceops.domain.inventory_rules import Evaluation, RuleParameters, display_fraction


class AnalysisDTO(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    schema_version: Literal["inventory-analysis-v1"] = "inventory-analysis-v1"


class OpenWorkItemInput(AnalysisDTO):
    """已有fixture只读观测，非补货实体/创建入口，无审批或执行状态。"""

    item_id: Identifier
    sku_key: Identifier
    stock_pool_key: Identifier
    status: Literal["open"]
    quantity: PositiveUnits
    source_kind: Literal["mock"]


class InventoryInput(AnalysisDTO):
    source: Source
    now: Timestamp
    window: Window | None = None
    products: tuple[Product, ...]
    order_lines: tuple[OrderLine, ...]
    refunds: tuple[Refund, ...]
    inventories: tuple[Inventory, ...]
    complete: bool
    warnings: tuple[Quality, ...] = ()
    open_items: tuple[OpenWorkItemInput, ...] = ()


class ExactRatio(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    numerator: str
    denominator: str

    @model_validator(mode="after")
    def reduced(self) -> Self:
        try:
            value = Fraction(int(self.numerator), int(self.denominator))
        except (ValueError, ZeroDivisionError):
            raise ValueError("NON_CANONICAL_RATIO") from None
        if str(value.numerator) != self.numerator or str(value.denominator) != self.denominator:
            raise ValueError("NON_CANONICAL_RATIO")
        return self

    @classmethod
    def from_fraction(cls, value: Fraction | None) -> "ExactRatio | None":
        return (
            None
            if value is None
            else cls(numerator=str(value.numerator), denominator=str(value.denominator))
        )


class Display(AnalysisDTO):
    display_version: Literal["inventory-display-v1"] = "inventory-display-v1"
    D: str | None
    trigger: str | None
    coverage: str | None


class InventoryFact(AnalysisDTO):
    sku_key: Identifier
    stock_pool_key: Identifier | None
    sku_label: str | None
    active: bool | None
    gross_units: NonnegativeUnits | None
    known_gross_units: NonnegativeUnits
    demand_complete: bool
    known_refunded_units: NonnegativeUnits
    quantity_complete: bool
    refunded_units: NonnegativeUnits | None
    net_units: Units | None
    quantity_reason: str | None
    currency: str
    D: ExactRatio | None
    A: Units | None
    stock_reason: str | None
    inventory_observed_at: Timestamp | None
    source_version: Identifier | None
    inbound_units: NonnegativeUnits | None
    inbound_reason: str | None
    effective_inbound_units: NonnegativeUnits
    L: NonnegativeUnits
    R: NonnegativeUnits
    S: NonnegativeUnits
    T: NonnegativeUnits | None
    trigger: ExactRatio | None
    risk: Literal[
        "risk", "stockout", "normal", "no_recent_demand", "manual_check", "quality_blocked"
    ]
    suggested_units: NonnegativeUnits | None
    coverage: ExactRatio | None
    coverage_reason: str | None
    required_assumptions: tuple[str, ...]
    hard_blocks: tuple[str, ...]
    quality_flags: tuple[str, ...]
    included_order_ids: tuple[str, ...]
    excluded_order_ids: tuple[str, ...]
    review_order_ids: tuple[str, ...]
    open_item_ids: tuple[str, ...]
    can_form_suggestion: bool
    suggestion_mode: Literal["estimate", "assumption_draft", "blocked", "not_needed"]
    analysis_only: Literal[True] = True
    execution_available: Literal[False] = False
    eligible_for_execution: Literal[False] = False
    display: Display


def evaluation_fields(value: Evaluation, parameters: RuleParameters) -> dict[str, object]:
    return {
        "D": ExactRatio.from_fraction(value.D),
        "A": value.A,
        "inbound_units": value.inbound_units,
        "effective_inbound_units": value.effective_inbound_units,
        "L": parameters.L,
        "R": parameters.R,
        "S": parameters.S,
        "T": value.T,
        "trigger": ExactRatio.from_fraction(value.trigger),
        "risk": value.risk.value,
        "suggested_units": value.suggested_units,
        "coverage": ExactRatio.from_fraction(value.coverage),
        "coverage_reason": value.coverage_reason,
        "required_assumptions": value.required_assumptions,
        "hard_blocks": value.hard_blocks,
        "can_form_suggestion": value.can_form_suggestion,
        "suggestion_mode": (
            "blocked"
            if value.hard_blocks
            else "assumption_draft"
            if value.required_assumptions
            else "estimate"
            if value.can_form_suggestion
            else "not_needed"
        ),
        "display": Display(
            D=display_fraction(value.D),
            trigger=display_fraction(value.trigger),
            coverage=display_fraction(value.coverage),
        ),
    }


class InventoryReport(AnalysisDTO):
    rule_version: Literal["inventory-rule-v1"] = "inventory-rule-v1"
    parameter_mode: Literal["demo_assumption"] = "demo_assumption"
    canonical_version: Literal["canonical-facts-v1"] = "canonical-facts-v1"
    source: Source
    now: Timestamp
    window: Window
    source_complete: bool
    complete: bool
    requires_review: bool
    L: NonnegativeUnits
    R: NonnegativeUnits
    S: NonnegativeUnits
    warnings: tuple[str, ...]
    items: tuple[InventoryFact, ...]
    candidate_count: NonnegativeUnits
    scope_required: bool
    input_hash: Digest
    analysis_only: Literal[True] = True
    execution_available: Literal[False] = False
    facts_hash: Digest

    def canonical_facts(self) -> dict[str, object]:
        return self.model_dump(
            mode="json", exclude={"facts_hash": True, "items": {"__all__": {"display"}}}
        )

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.canonical_facts())

    @model_validator(mode="after")
    def verify_hash(self) -> Self:
        if self.facts_hash != facts_hash(self.canonical_facts()):
            raise ValueError("FACTS_HASH_MISMATCH")
        return self
