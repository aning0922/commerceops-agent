"""纯规则独立边界，不依赖待测实现动态生成金标。"""

from fractions import Fraction
from typing import Any

import pytest
from commerceops.domain.inventory_rules import (
    Evaluation,
    Risk,
    RuleParameters,
    display_fraction,
    evaluate_inventory,
)

pytestmark = pytest.mark.offline


def rule(
    stock: int | None,
    gross: int | None = 70,
    inbound: int | None = 0,
    params: RuleParameters | None = None,
    blocks: tuple[str, ...] = (),
) -> Evaluation:
    return evaluate_inventory(
        sku_key="sku/demo/100/p",
        gross_units=gross,
        available_stock=stock,
        inbound_units=inbound,
        parameters=params or RuleParameters(),
        hard_blocks=blocks,
    )


@pytest.mark.parametrize(
    "stock,inbound,risk,quantity,coverage,reason",
    [
        (20, 0, Risk.RISK, 100, Fraction(2), None),
        (50, 0, Risk.RISK, 70, Fraction(5), None),
        (51, 0, Risk.NORMAL, None, Fraction(51, 10), None),
        (-5, 0, Risk.STOCKOUT, 125, None, "BACKLOG_STOCK"),
        (0, 0, Risk.STOCKOUT, 120, Fraction(0), None),
        (20, 30, Risk.RISK, 70, Fraction(2), None),
        (20, None, Risk.RISK, 100, Fraction(2), None),
        (None, 0, Risk.QUALITY_BLOCKED, None, None, "UNKNOWN_STOCK"),
    ],
)
def test_paper_stock_and_inbound(
    stock: int | None,
    inbound: int | None,
    risk: Risk,
    quantity: int | None,
    coverage: Fraction | None,
    reason: str | None,
) -> None:
    actual = rule(stock, inbound=inbound)
    assert (actual.D, actual.T, actual.trigger) == (Fraction(10), 120, Fraction(50))
    assert (actual.risk, actual.suggested_units, actual.coverage, actual.coverage_reason) == (
        risk,
        quantity,
        coverage,
        reason,
    )
    if inbound is None:
        assert actual.inbound_units is None and actual.effective_inbound_units == 0
        assert actual.required_assumptions == ("inbound_unknown_zero:sku/demo/100/p",)


@pytest.mark.parametrize(
    "stock,risk,quantity,coverage",
    [
        (5, Risk.RISK, 3, Fraction(35, 8)),
        (6, Risk.NORMAL, None, Fraction(21, 4)),
    ],
)
def test_fractional_boundary_never_rounds_demand(
    stock: int, risk: Risk, quantity: int | None, coverage: Fraction
) -> None:
    value = rule(stock, gross=8, params=RuleParameters(L=3, R=2, S=2))
    assert (value.D, value.T, value.trigger) == (Fraction(8, 7), 8, Fraction(40, 7))
    assert (value.risk, value.suggested_units, value.coverage) == (risk, quantity, coverage)
    assert display_fraction(value.D) == "1.142857"
    assert display_fraction(value.trigger) == "5.714286"


@pytest.mark.parametrize(
    "stock,risk", [(20, Risk.NO_RECENT_DEMAND), (0, Risk.MANUAL_CHECK), (-5, Risk.MANUAL_CHECK)]
)
def test_zero_demand_reason_precedence(stock: int, risk: Risk) -> None:
    value = rule(stock, gross=0)
    assert value.risk == risk and value.suggested_units is None
    assert value.coverage is None and value.coverage_reason == "NO_RECENT_DEMAND"


@pytest.mark.parametrize(
    "bad", [True, False, 1.0, 1.5, float("nan"), float("inf"), "3", Fraction(1, 2), -1]
)
@pytest.mark.parametrize("field", ["L", "R", "S"])
def test_parameters_reject_non_integer_and_negative(field: str, bad: object) -> None:
    fields: dict[str, Any] = {field: bad}
    with pytest.raises(ValueError):
        RuleParameters(**fields)


@pytest.mark.parametrize("field", ["gross_units", "available_stock", "inbound_units"])
@pytest.mark.parametrize("bad", [True, 1.5, float("nan"), "1"])
def test_rule_cannot_coerce_quantity(field: str, bad: object) -> None:
    fields: dict[str, Any] = {
        "sku_key": "sku/demo/100/p",
        "gross_units": 70,
        "available_stock": 20,
        "inbound_units": 0,
        "parameters": RuleParameters(),
        field: bad,
    }
    with pytest.raises(ValueError):
        evaluate_inventory(**fields)


@pytest.mark.parametrize(
    "flag", ["SOURCE_CHANGED", "OPEN_WORK_ITEM", "SHARED_POOL_UNRESOLVED", "UNKNOWN_STOCK"]
)
def test_inbound_assumption_never_waives_hard_block(flag: str) -> None:
    value = rule(20, inbound=None, blocks=(flag,))
    assert value.suggested_units is None and not value.can_form_suggestion
    assert value.inbound_units is None and value.effective_inbound_units == 0
    assert value.required_assumptions == () and flag in value.hard_blocks


def test_unknown_demand_is_not_zero_and_no_invented_quantity_ceiling() -> None:
    unknown = rule(20, gross=None)
    assert unknown.D is None and unknown.T is None and unknown.suggested_units is None
    assert unknown.coverage_reason == "INCOMPLETE_DEMAND"
    large = rule(-(10**30), gross=70)
    assert large.suggested_units == 120 + 10**30
    assert rule(20, inbound=200).suggested_units == 0
    assert not rule(20, inbound=200).can_form_suggestion
    assert RuleParameters(L=0, R=0, S=0).L == 0


@pytest.mark.parametrize(
    "value,expected",
    [
        (Fraction(1, 2_000_000), "0.000000"),
        (Fraction(3, 2_000_000), "0.000002"),
        (Fraction(-3, 2_000_000), "-0.000002"),
        (Fraction(8, 7), "1.142857"),
    ],
)
def test_exact_half_even_display(value: Fraction, expected: str) -> None:
    assert display_fraction(value) == expected
