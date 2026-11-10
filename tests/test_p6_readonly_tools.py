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
    OrdersCall,
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
    assert (
        result.results[1].scanned_rows == 3
    )  # One catalog row + two orders; empty refunds add zero.
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
    assert not result.complete and result.scanned_rows == 3 and not result.facts
    bounded = MockReadFacade(MockCommerce(f, page_size=2))
    result = asyncio.run(bounded.read(context(f), orders, 10**12, 2))
    assert not result.complete and result.scanned_rows == 1 and not result.facts


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
    assert result.scanned_rows == 5  # Catalog + two orders + two refunds, including outside dates.
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
    assert {f.currency: f.value for f in result.facts if f.metric == "sold_units"} == {
        "CNY": "140",
        "USD": "70",
    }


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
    assert result.complete and result.scanned_rows == 1
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


def test_cross_sku_period_comparison_is_rejected_by_executor_and_renderer() -> None:
    """Independent counterexample: A's 3 and B's 5 are not a growth comparison."""
    from commerceops.application.commerce.readonly_inquiry_contracts import Claim

    f = two_period_fixture()
    other_sku = "sku/demo/200/p"
    other = f.products[0].model_copy(
        update={
            "sku_key": other_sku,
            "product_id": "200",
            "stock_pool_key": "pool/demo/200",
        }
    )
    f = replace(
        f,
        products=(*f.products, other),
        orders=(
            f.orders[0],
            f.orders[1].model_copy(update={"sku_key": other_sku}),
        ),
    )
    facade = MockReadFacade(MockCommerce(f, page_size=1))

    class CrossSkuRoute:
        async def choose(self, current: Context, results: tuple[ReadResult, ...]) -> str:
            if len(results) < 2:
                index = len(results)
                return choice(
                    [
                        {
                            "tool_call_id": f"order-{index}",
                            "name": "commerce.read_orders",
                            "args": {
                                "skus": [SKU if index == 0 else other_sku],
                                "windows": [
                                    window("2026-09-20T00:00:00Z", "2026-09-27T00:00:00Z")
                                    if index == 0
                                    else window("2026-09-27T00:00:00Z", "2026-10-04T00:00:00Z")
                                ],
                            },
                        }
                    ]
                )
            refs = [
                next(x.evidence_id for x in result.facts if x.metric == "sold_units")
                for result in results
            ]
            return json.dumps(
                {
                    "kind": "final",
                    "intent": "readonly_inquiry",
                    "evidence_refs": refs,
                    "claims": [{"kind": "compare", "refs": refs}],
                }
            )

    outcome = asyncio.run(
        execute(
            context(f), CrossSkuRoute(), Identity(), {name: Tool("read", facade) for name in NAMES}
        )
    )
    assert outcome.status == "invalid_response" and not outcome.results
    assert "66.67" not in render(outcome).text
    first = asyncio.run(
        facade.read(
            context(f),
            call(
                "commerce.read_orders",
                {
                    "skus": [SKU],
                    "windows": [window("2026-09-20T00:00:00Z", "2026-09-27T00:00:00Z")],
                },
                "a",
            ),
            10**12,
            10000,
        )
    )
    second = asyncio.run(
        facade.read(
            context(f),
            call(
                "commerce.read_orders",
                {
                    "skus": [other_sku],
                    "windows": [window("2026-09-27T00:00:00Z", "2026-10-04T00:00:00Z")],
                },
                "b",
            ),
            10**12,
            10000,
        )
    )
    a = next(x for x in first.facts if x.metric == "sold_units")
    b = next(x for x in second.facts if x.metric == "sold_units")
    assert (a.sku_key, a.value, b.sku_key, b.value) == (SKU, "3", other_sku, "5")
    forged = Outcome(
        status="complete",
        model_calls=3,
        tool_calls=2,
        scanned_rows=6,
        traces=(),
        results=(first, second),
        evidence_refs=(a.evidence_id, b.evidence_id),
        claims=(Claim(kind="compare", refs=(a.evidence_id, b.evidence_id)),),
    )
    with pytest.raises(ValueError, match="INVALID_COMPARISON"):
        render(forged)


@pytest.mark.parametrize("name", ["commerce.read_orders", "commerce.read_inventory"])
def test_unknown_sku_cannot_return_a_complete_zero_or_inventory(name: str) -> None:
    f = fixture()
    source = MockCommerce(f, page_size=1)
    args: dict[str, object] = {"skus": ["sku/demo/unknown/p"]}
    if name == "commerce.read_orders":
        args["windows"] = [window("2026-10-01T00:00:00Z", "2026-10-08T00:00:00Z")]
    result = asyncio.run(MockReadFacade(source).read(context(f), call(name, args), 10**12, 10000))
    assert not result.complete and not result.facts
    assert result.quality_flags == ("SKU_NOT_FOUND",)
    assert source.call_counts == {"products": 1}


def test_statuses_with_unknown_or_unproven_refunds_are_incomplete_not_790_or_70() -> None:
    f = fixture("statuses")
    orders = call(
        "commerce.read_orders",
        {"skus": [SKU], "windows": [window("2026-10-01T00:00:00Z", "2026-10-08T00:00:00Z")]},
    )
    result = asyncio.run(
        MockReadFacade(MockCommerce(f, page_size=2)).read(context(f), orders, 10**12, 10000)
    )
    assert not result.complete and result.quality_flags == ("ORDER_STATUS_REVIEW",)
    assert not result.facts and result.scanned_rows == 12  # One catalog and all eleven order rows.
    # Manual fixture index oracle: first four qualify; rows 5..9 are explicitly excluded.
    known = replace(f, orders=f.orders[:4] + f.orders[5:10])
    result = asyncio.run(
        MockReadFacade(MockCommerce(known, page_size=2)).read(context(known), orders, 10**12, 10000)
    )
    assert result.complete
    expected = {"sold_units": "70", "order_net": "42.00", "order_average": "10.500000"}
    assert {fact.metric: fact.value for fact in result.facts} == expected
    assert isinstance(orders, OrdersCall)
    assert all(
        fact.sku_key == SKU and fact.currency == "CNY" and fact.window == orders.args.windows[0]
        for fact in result.facts
    )


@pytest.mark.parametrize("evidence", ["missing", "before_creation", "after_capture"])
def test_refunded_order_requires_valid_paid_or_completed_evidence(evidence: str) -> None:
    from datetime import timedelta

    f = fixture()
    row = f.orders[0]
    paid = (
        None
        if evidence == "missing"
        else (
            row.created_at - timedelta(seconds=1)
            if evidence == "before_creation"
            else row.source.captured_at + timedelta(seconds=1)
        )
    )
    f = replace(
        f,
        orders=(
            row.model_copy(update={"status": "refunded", "paid_at": paid, "completed_at": None}),
        ),
    )
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
    assert not result.complete and result.quality_flags == ("ORDER_STATUS_REVIEW",)
    assert not result.facts


def test_unresolved_pool_is_unknown_and_pool_identity_is_checked() -> None:
    from commerceops.application.commerce.readonly_inquiry_contracts import Claim

    f = fixture()
    unresolved = f.inventories[0].model_copy(update={"pool_allocation": "unresolved"})
    f = replace(f, inventories=(unresolved,))
    result = asyncio.run(
        MockReadFacade(MockCommerce(f, page_size=1)).read(
            context(f), call("commerce.read_inventory", {"skus": [SKU]}), 10**12, 10000
        )
    )
    stock = next(x for x in result.facts if x.metric == "available_stock")
    assert result.complete and stock.value is None
    assert stock.sku_key == SKU and "SHARED_POOL_UNRESOLVED" in stock.quality_flags
    outcome = Outcome(
        status="complete",
        model_calls=2,
        tool_calls=1,
        scanned_rows=2,
        traces=(),
        results=(result,),
        evidence_refs=(stock.evidence_id,),
        claims=(Claim(kind="fact", refs=(stock.evidence_id,)),),
    )
    assert "可用库存 未知" in render(outcome).text and "可用库存 20" not in render(outcome).text
    mismatch = replace(
        f, inventories=(unresolved.model_copy(update={"stock_pool_key": "pool/demo/wrong"}),)
    )
    result = asyncio.run(
        MockReadFacade(MockCommerce(mismatch, page_size=1)).read(
            context(mismatch), call("commerce.read_inventory", {"skus": [SKU]}), 10**12, 10000
        )
    )
    assert not result.complete and result.quality_flags == ("STOCK_POOL_MISMATCH",)
    assert not result.facts


def test_shared_catalog_pool_does_not_duplicate_exact_tagged_stock() -> None:
    f = fixture()
    # The v1 model has no proven per-variant shares even when individual rows say exact.
    other = f.products[0].model_copy(update={"sku_key": "sku/demo/200/p", "product_id": "200"})
    f = replace(f, products=(f.products[0], other))
    result = asyncio.run(
        MockReadFacade(MockCommerce(f, page_size=1)).read(
            context(f), call("commerce.read_inventory", {"skus": [SKU]}), 10**12, 10000
        )
    )
    assert result.complete and all(x.value is None for x in result.facts)
    assert all("SHARED_POOL_UNRESOLVED" in x.quality_flags for x in result.facts)


def test_refund_fact_retains_refund_page_observation_time(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import timedelta

    from commerceops.application.commerce.contracts import Page, Refund

    f = fixture("cross_period")
    source = MockCommerce(f, page_size=1)
    original = source.list_refunds
    refund_time = f.now + timedelta(minutes=5)

    def observed_refunds(order_ids: tuple[str, ...], *, cursor: str | None = None) -> Page[Refund]:
        return original(order_ids, cursor=cursor).model_copy(update={"observed_at": refund_time})

    monkeypatch.setattr(source, "list_refunds", observed_refunds)
    result = asyncio.run(
        MockReadFacade(source).read(
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
    assert result.complete
    assert next(x.as_of for x in result.facts if x.metric == "refund_cohort") == refund_time
    assert next(x.as_of for x in result.facts if x.metric == "sold_units") == f.now


def test_multi_sku_order_refund_without_amount_allocation_is_incomplete() -> None:
    f = fixture("cross_period")
    other_sku = "sku/demo/200/p"
    other = f.products[0].model_copy(
        update={
            "sku_key": other_sku,
            "product_id": "200",
            "stock_pool_key": "pool/demo/200",
        }
    )
    first = f.orders[0]
    second = first.model_copy(update={"sku_key": other_sku, "line_id": "other-line"})
    f = replace(f, products=(*f.products, other), orders=(first, second))
    result = asyncio.run(
        MockReadFacade(MockCommerce(f, page_size=1)).read(
            context(f),
            call(
                "commerce.read_orders",
                {
                    "skus": [SKU, other_sku],
                    "windows": [window("2026-10-01T00:00:00Z", "2026-10-08T00:00:00Z")],
                },
            ),
            10**12,
            10000,
        )
    )
    assert not result.complete and result.quality_flags == ("REFUND_SCOPE_REVIEW",)
    assert not result.facts
