"""Manual goldens for the real MockCommerce facade and deterministic renderer."""

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from commerceops.adapters.commerce.mock import Behavior, Fixture, MockCommerce
from commerceops.application.commerce.contracts import OrderLine
from commerceops.application.commerce.readonly_inquiry_contracts import (
    Calls,
    Context,
    ReadResult,
    ToolCall,
    parse_choice,
)
from commerceops.application.commerce.readonly_inquiry_executor import NAMES, Outcome, Tool, execute
from commerceops.application.commerce.readonly_inquiry_render import render
from commerceops.application.commerce.readonly_inquiry_tools import MockReadFacade

pytestmark = pytest.mark.offline
DIRECTORY = Path(__file__).parent / "fixtures/commerce/inventory-v1"
SKU = "sku/demo/100/p"


def fixture(name: str = "baseline") -> Fixture:
    return Fixture.load(DIRECTORY, name)


def context(f: Fixture) -> Context:
    return Context(
        request_id="q",
        principal_id="p",
        organization_id="o",
        shop_id=f.source.shop_id,
        identity_id="i",
        auth_version=1,
        source_binding=f.source.provenance.raw_hash,
        question="查询合成演示商品",
    )


def call(name: str, args: dict[str, object], ident: str = "c1") -> ToolCall:
    value = parse_choice(
        json.dumps(
            {
                "kind": "call_tools",
                "intent": "readonly_inquiry",
                "calls": [{"tool_call_id": ident, "name": name, "args": args}],
            }
        )
    )
    if not isinstance(value, Calls):
        raise ValueError("EXPECTED_CALLS")
    return value.calls[0]


def window(start: str, end: str) -> dict[str, str]:
    return {"start": start, "end": end}


def choice(calls: list[dict[str, object]]) -> str:
    return json.dumps({"kind": "call_tools", "intent": "readonly_inquiry", "calls": calls})


class Identity:
    async def authorize(self, context: Context, call: ToolCall | None) -> bool:
        return True


class Route:
    async def choose(self, context: Context, results: tuple[ReadResult, ...]) -> str:
        if not results:
            return choice(
                [
                    {
                        "tool_call_id": "products",
                        "name": "commerce.read_products",
                        "args": {"query": "合成演示商品 100"},
                    }
                ]
            )
        if len(results) == 1:
            sku = results[0].products[0].sku_key
            return choice(
                [
                    {
                        "tool_call_id": "orders",
                        "name": "commerce.read_orders",
                        "args": {
                            "skus": [sku],
                            "windows": [
                                window("2026-09-20T00:00:00Z", "2026-09-27T00:00:00Z"),
                                window("2026-09-27T00:00:00Z", "2026-10-04T00:00:00Z"),
                            ],
                        },
                    },
                    {
                        "tool_call_id": "stock",
                        "name": "commerce.read_inventory",
                        "args": {"skus": [sku]},
                    },
                ]
            )
        sold = [fact.evidence_id for fact in results[1].facts if fact.metric == "sold_units"]
        stock = next(
            fact.evidence_id for fact in results[2].facts if fact.metric == "available_stock"
        )
        return json.dumps(
            {
                "kind": "final",
                "intent": "readonly_inquiry",
                "evidence_refs": [*sold, stock],
                "claims": [{"kind": "compare", "refs": sold}, {"kind": "fact", "refs": [stock]}],
            }
        )


def two_period_fixture() -> Fixture:
    base = fixture()
    old = base.orders[0]

    def order(order_id: str, line_id: str, at: str, qty: int, amount: str) -> OrderLine:
        return OrderLine.model_validate(
            {
                **old.model_dump(),
                "order_id": order_id,
                "line_id": line_id,
                "created_at": datetime.fromisoformat(at),
                "quantity": qty,
                "net_amount": Decimal(amount),
            }
        )

    orders = (
        order("old", "line-old", "2026-09-24T00:00:00+00:00", 3, "1.20"),
        order("new", "line-new", "2026-10-01T00:00:00+00:00", 5, "2.30"),
    )
    return replace(base, orders=orders)


def test_full_dynamic_mock_chain_and_manual_period_golden() -> None:
    f = two_period_fixture()
    facade = MockReadFacade(MockCommerce(f, page_size=1))
    result = asyncio.run(
        execute(context(f), Route(), Identity(), {name: Tool("read", facade) for name in NAMES})
    )
    assert result.status == "complete" and result.model_calls == 3 and result.tool_calls == 3
    sold = [fact for fact in result.results[1].facts if fact.metric == "sold_units"]
    assert [fact.value for fact in sold] == ["3", "5"]  # Independent source rows above.
    assert result.results[1].scanned_rows == 2  # 2 orders; empty refund pages scan zero rows.
    answer = render(result)
    assert "前期 3 件" in answer.text and "本期 5 件" in answer.text
    assert "变化 2 件" in answer.text and "66.67%" in answer.text
    assert "可用库存 20 件" in answer.text and len(answer.evidence_refs) == 3


def test_ambiguous_complete_catalog_returns_safe_options_without_model_selection() -> None:
    f = fixture()
    second = f.products[0].model_copy(update={"sku_key": "sku/demo/200/p", "product_id": "200"})
    f = replace(f, products=(f.products[0], second))
    source = MockCommerce(f, page_size=1)
    outcome = asyncio.run(
        execute(
            context(f),
            Route(),
            Identity(),
            {name: Tool("read", MockReadFacade(source)) for name in NAMES},
        )
    )
    assert outcome.status == "clarify" and not outcome.results
    assert {item.sku_key for item in outcome.clarification_options} == {SKU, "sku/demo/200/p"}
    assert all(item.label == "DEMO" for item in outcome.clarification_options)
    assert outcome.model_calls == 1 and outcome.tool_calls == 1


def test_no_match_and_partial_catalog_do_not_offer_exhaustive_choices() -> None:
    f = fixture()
    source = MockCommerce(f, page_size=1)
    # Explicit no-match is separate from a complete, ambiguous catalog.
    none = asyncio.run(
        MockReadFacade(source).read(
            context(f), call("commerce.read_products", {"query": "absent"}), 10**12, 10000
        )
    )
    assert none.complete and none.products == ()
    f2 = replace(
        f,
        products=(
            f.products[0],
            f.products[0].model_copy(update={"sku_key": "sku/demo/200/p", "product_id": "200"}),
        ),
    )
    partial = MockCommerce(f2, page_size=1, behavior=Behavior(endpoint="products", max_pages=1))
    outcome = asyncio.run(
        execute(
            context(f2),
            Route(),
            Identity(),
            {name: Tool("read", MockReadFacade(partial)) for name in NAMES},
        )
    )
    assert outcome.status == "source_incomplete" and not outcome.clarification_options


def test_unknown_stock_keeps_null_and_quality() -> None:
    f = fixture("unknown_stock")
    facade = MockReadFacade(MockCommerce(f, page_size=1))
    result = asyncio.run(
        facade.read(context(f), call("commerce.read_inventory", {"skus": [SKU]}), 10**12, 10000)
    )
    assert result.complete
    stock = next(fact for fact in result.facts if fact.metric == "available_stock")
    assert stock.value is None and "UNKNOWN_STOCK" in stock.quality_flags


def test_real_mock_page_failure_and_scan_budget_fail_closed() -> None:
    f = fixture("statuses")
    partial = MockReadFacade(
        MockCommerce(f, page_size=2, behavior=Behavior(endpoint="orders", max_pages=1))
    )
    orders = call(
        "commerce.read_orders",
        {"skus": [SKU], "windows": [window("2026-10-01T00:00:00Z", "2026-10-08T00:00:00Z")]},
    )
    result = asyncio.run(partial.read(context(f), orders, 10**12, 10000))
    assert not result.complete and result.scanned_rows == 2 and not result.facts
    bounded = MockReadFacade(MockCommerce(f, page_size=2))
    result = asyncio.run(bounded.read(context(f), orders, 10**12, 2))
    assert not result.complete and result.scanned_rows == 2 and not result.facts


def test_report_reader_requires_injected_authorized_port() -> None:
    f = fixture()
    facade = MockReadFacade(MockCommerce(f))
    with pytest.raises(ValueError, match="REPORT_READ_UNAVAILABLE"):
        asyncio.run(
            facade.read(context(f), call("reports.read", {"report_id": "r"}), 10**12, 10000)
        )


def test_zero_denominator_and_currency_are_explicit_in_renderer() -> None:
    from commerceops.application.commerce.readonly_inquiry_contracts import Claim, Fact, Window

    w1 = Window(start=datetime(2026, 10, 1, tzinfo=UTC), end=datetime(2026, 10, 2, tzinfo=UTC))
    w2 = Window(start=w1.end, end=datetime(2026, 10, 3, tzinfo=UTC))
    f = fixture()
    common = dict(
        tool_call_id="c",
        shop_id="demo",
        source_binding=f.source.provenance.raw_hash,
        snapshot_id="s",
        as_of=f.now,
        complete=True,
        scanned_rows=0,
        sku_keys=(SKU,),
    )
    facts = (
        Fact(
            evidence_id="a",
            metric="order_net",
            sku_key=SKU,
            window=w1,
            as_of=f.now,
            value="0",
            unit="金额",
            currency="CNY",
        ),
        Fact(
            evidence_id="b",
            metric="order_net",
            sku_key=SKU,
            window=w2,
            as_of=f.now,
            value="2.35",
            unit="金额",
            currency="CNY",
        ),
    )
    result = ReadResult.model_validate({**common, "facts": facts, "windows": (w1, w2)})
    outcome = Outcome(
        status="complete",
        model_calls=1,
        tool_calls=1,
        scanned_rows=0,
        traces=(),
        results=(result,),
        evidence_refs=("a", "b"),
        claims=(Claim(kind="compare", refs=("a", "b")),),
    )
    text = render(outcome).text
    assert "前期 0 CNY" in text and "本期 2.35 CNY" in text
    assert "比例不可计算（前期为 0）" in text
    mixed = result.model_copy(
        update={"facts": (facts[0], facts[1].model_copy(update={"currency": "USD"}))}
    )
    with pytest.raises(ValueError, match="INVALID_COMPARISON"):
        render(replace(outcome, results=(mixed,)))


def test_refunds_follow_order_cohort_even_when_created_outside_window() -> None:
    f = fixture("cross_period")
    facade = MockReadFacade(MockCommerce(f, page_size=1))
    result = asyncio.run(
        facade.read(
            context(f),
            call(
                "commerce.read_orders",
                {
                    "skus": [SKU],
                    "windows": [
                        window("2026-09-20T00:00:00Z", "2026-09-27T00:00:00Z"),
                        window("2026-10-01T00:00:00Z", "2026-10-08T00:00:00Z"),
                    ],
                },
            ),
            10**12,
            10000,
        )
    )
    assert result.complete
    assert [fact.value for fact in result.facts if fact.metric == "sold_units"] == ["13", "70"]
    assert [fact.value for fact in result.facts if fact.metric == "refund_cohort"] == [
        "5.00",
        "5.00",
    ]
    assert result.scanned_rows == 4  # Two order rows and two refund rows, including outside dates.
    from commerceops.application.commerce.readonly_inquiry_contracts import Claim

    outcome = Outcome(
        status="complete",
        model_calls=2,
        tool_calls=1,
        scanned_rows=4,
        traces=(),
        results=(result,),
        evidence_refs=(next(x.evidence_id for x in result.facts if x.metric == "refund_cohort"),),
        claims=(
            Claim(
                kind="fact",
                refs=(next(x.evidence_id for x in result.facts if x.metric == "refund_cohort"),),
            ),
        ),
    )
    assert "非本窗口现金流" in render(outcome).text


def test_decimal_context_and_mixed_currencies_do_not_merge() -> None:
    from decimal import getcontext

    f = fixture()
    old = f.orders[0]
    rows = (
        old.model_copy(update={"order_id": "x", "line_id": "x", "net_amount": Decimal("1.234567")}),
        old.model_copy(update={"order_id": "y", "line_id": "y", "net_amount": Decimal("2.345678")}),
        old.model_copy(
            update={
                "order_id": "z",
                "line_id": "z",
                "net_amount": Decimal("4.500001"),
                "currency": "USD",
            }
        ),
    )
    f = replace(f, orders=rows)
    context_precision = getcontext().prec
    try:
        getcontext().prec = 4
        result = asyncio.run(
            MockReadFacade(MockCommerce(f, page_size=1)).read(
                context(f),
                call(
                    "commerce.read_orders",
                    {
                        "skus": [SKU],
                        "windows": [window("2026-10-01T00:00:00Z", "2026-10-08T00:00:00Z")],
                    },
                ),
                10**12,
                10000,
            )
        )
    finally:
        getcontext().prec = context_precision
    assert result.complete
    amounts = {fact.currency: fact.value for fact in result.facts if fact.metric == "order_net"}
    assert amounts == {"CNY": "3.580245", "USD": "4.500001"}
    assert next(f.value for f in result.facts if f.metric == "sold_units") == "210"


def test_unknown_stock_renders_unknown_without_inventing_zero() -> None:
    from commerceops.application.commerce.readonly_inquiry_contracts import Claim

    f = fixture("unknown_stock")
    result = asyncio.run(
        MockReadFacade(MockCommerce(f, page_size=1)).read(
            context(f), call("commerce.read_inventory", {"skus": [SKU]}), 10**12, 10000
        )
    )
    stock = next(item for item in result.facts if item.metric == "available_stock")
    outcome = Outcome(
        status="complete",
        model_calls=2,
        tool_calls=1,
        scanned_rows=1,
        traces=(),
        results=(result,),
        evidence_refs=(stock.evidence_id,),
        claims=(Claim(kind="fact", refs=(stock.evidence_id,)),),
    )
    assert "未知" in render(outcome).text and "UNKNOWN_STOCK" in render(outcome).text
    assert " 0 件" not in render(outcome).text


def test_empty_complete_window_average_has_zero_denominator_not_zero_amount() -> None:
    f = fixture()
    result = asyncio.run(
        MockReadFacade(MockCommerce(f, page_size=1)).read(
            context(f),
            call(
                "commerce.read_orders",
                {
                    "skus": [SKU],
                    "windows": [window("2026-09-20T00:00:00Z", "2026-09-21T00:00:00Z")],
                },
            ),
            10**12,
            10000,
        )
    )
    assert result.complete and result.scanned_rows == 0
    average = next(item for item in result.facts if item.metric == "order_average")
    assert average.value is None and average.quality_flags == ("ZERO_DENOMINATOR",)
    from commerceops.application.commerce.readonly_inquiry_contracts import Claim

    outcome = Outcome(
        status="complete",
        model_calls=1,
        tool_calls=1,
        scanned_rows=0,
        traces=(),
        results=(result,),
        evidence_refs=(average.evidence_id,),
        claims=(Claim(kind="fact", refs=(average.evidence_id,)),),
    )
    assert "不可计算（分母为 0）" in render(outcome).text


def test_injected_report_reader_is_bound_to_current_context_and_report() -> None:
    f = fixture()
    seen: list[tuple[str, str]] = []

    class AuthorizedReport:
        async def read(self, current: Context, report_id: str, deadline: float) -> ReadResult:
            seen.append((current.principal_id, report_id))
            return ReadResult(
                tool_call_id="c1",
                shop_id=current.shop_id,
                source_binding=current.source_binding,
                snapshot_id="snap-r",
                report_id=report_id,
                as_of=f.now,
                complete=True,
                scanned_rows=0,
                sku_keys=(),
            )

    facade = MockReadFacade(MockCommerce(f), report_reader=AuthorizedReport())
    result = asyncio.run(
        facade.read(context(f), call("reports.read", {"report_id": "r"}), 10**12, 10000)
    )
    assert seen == [("p", "r")]
    assert result.complete and result.report_id == "r"
