"""M3 S1 人工可复算金标；无 PG、HTTP、Worker、模型或发送。"""

from datetime import UTC, date, datetime, timedelta
from decimal import Inexact, Rounded, localcontext
from typing import Any
from uuid import UUID

import pytest
from commerceops.application.daily.aggregation import aggregate_daily
from commerceops.application.daily.contracts import DailyInput, DailyReport
from pydantic import ValidationError

pytestmark = pytest.mark.offline

SOURCE: dict[str, Any] = {
    "organization_id": UUID(int=1),
    "shop_id": UUID(int=2),
    "source_binding_id": UUID(int=3),
    "source_config_version": "daily-fixture-1",
    "config_digest": "a" * 64,
    "source_kind": "mock",
    "fixture_version": "daily-gold-1",
    "currency": "CNY",
    "timezone": "Asia/Taipei",
}
DAY = date(2026, 11, 2)
START = datetime(2026, 11, 1, 16, tzinfo=UTC)
END = datetime(2026, 11, 2, 16, tzinfo=UTC)


def order(ref: str, **updates: Any) -> dict[str, Any]:
    return {
        "source": SOURCE,
        "order_id": ref,
        "currency": "CNY",
        "status": "processing",
        "created_at": START,
        "paid_at": START,
        "shipping_net": "0",
        "shipping_tax": "0",
        "fee_net": "0",
        "fee_tax": "0",
        "order_total": "0",
        **updates,
    }


def line(ref: str, line_id: str = "1", **updates: Any) -> dict[str, Any]:
    return {
        "source": SOURCE,
        "order_id": ref,
        "line_id": line_id,
        "currency": "CNY",
        "quantity": 1,
        "net_amount": "0",
        "tax_amount": "0",
        **updates,
    }


def refund(ref: str, refund_id: str = "r1", **updates: Any) -> dict[str, Any]:
    return {
        "source": SOURCE,
        "order_id": ref,
        "refund_id": refund_id,
        "currency": "CNY",
        "occurred_at": START,
        "amount": "0",
        "lines": (),
        "quantity_reason": "AMOUNT_ONLY",
        "restocked": None,
        **updates,
    }


def raw(
    orders: tuple[dict[str, Any], ...] = (),
    lines: tuple[dict[str, Any], ...] = (),
    refunds: tuple[dict[str, Any], ...] = (),
    *,
    coverage: dict[str, Any] | None = None,
    **updates: Any,
) -> dict[str, Any]:
    return {
        "snapshot_id": UUID(int=4),
        "source": SOURCE,
        "business_day": DAY,
        "as_of": END + timedelta(hours=1),
        "orders": orders,
        "order_lines": lines,
        "refunds": refunds,
        "rules": {"currency": "CNY"},
        "coverage": {
            "strategy": "complete_fixture",
            "orders_complete": True,
            "order_lines_complete": True,
            "refunds_complete": True,
            "discovered_order_count": len(orders),
            "discovered_line_count": len(lines),
            "discovered_refund_count": len(refunds),
            "collection_started_at": END,
            "collected_at": END + timedelta(minutes=1),
            **(coverage or {}),
        },
        **updates,
    }


def report(body: dict[str, Any]) -> DailyReport:
    return aggregate_daily(DailyInput.model_validate(body))


def codes(value: DailyReport) -> set[str]:
    return {finding.code for finding in value.findings}


def test_independent_multi_cohort_gold_and_order_level_amounts() -> None:
    # 旧单今天支付：商品90+税9+运费5+运费税0.5+费用2+费用税0.2=106.7。
    # 本日无行订单运费3；本日未记录支付的订单不计入支付额。
    # 昨日支付订单今天两笔退款7+1.2；今日支付旧单再退20 => 当日退款28.2。
    body = raw(
        (
            order(
                "old-paid-today",
                created_at=START - timedelta(days=10),
                shipping_net="5",
                shipping_tax="0.5",
                fee_net="2",
                fee_tax="0.2",
                order_total="106.7",
                status="refunded",
            ),
            order("zero-line", shipping_net="3", order_total="3"),
            order("no-paid-time", paid_at=None, order_total="8", status="pending"),
            order(
                "old-refund-today",
                created_at=START - timedelta(days=40),
                paid_at=START - timedelta(days=39),
                order_total="50",
                status="refunded",
            ),
            order("old-no-paid", created_at=START - timedelta(days=5), paid_at=None),
        ),
        (
            line("old-paid-today", "1", net_amount="60", tax_amount="6", quantity=3),
            line("old-paid-today", "2", net_amount="30", tax_amount="3"),
            line("no-paid-time", net_amount="8"),
            line("old-refund-today", net_amount="50"),
        ),
        (
            refund(
                "old-refund-today",
                "r1",
                amount="7",
                lines=({"line_id": "1", "quantity": 1, "quantity_reason": None},),
                quantity_reason=None,
                restocked=False,
            ),
            refund("old-refund-today", "r2", amount="1.2"),
            refund("old-paid-today", "r3", amount="20"),
            refund("old-refund-today", "r4", amount="100", occurred_at=END),
        ),
        rules={"currency": "CNY", "low_paid_total": "110", "high_refund_amount": "28"},
    )
    result = report(body)
    assert result.complete and result.metrics is not None
    actual = result.metrics.model_dump(mode="json")
    assert actual == {
        "created_order_count": 2,
        "paid_order_count": 2,
        "paid_product_net": "90",
        "paid_product_tax": "9",
        "paid_shipping_net": "8",
        "paid_shipping_tax": "0.5",
        "paid_fee_net": "2",
        "paid_fee_tax": "0.2",
        "paid_order_total": "109.7",
        "refund_count": 3,
        "refunded_order_count": 2,
        "refund_amount": "28.2",
        "orders_without_payment_timestamp": 1,
        "status_counts": [{"status": "pending", "count": 1}, {"status": "processing", "count": 1}],
        "average_paid_order_value": {"numerator": "1097", "denominator": "20"},
        "average_reason": None,
    }
    assert codes(result) == {"LOW_PAID_TOTAL", "HIGH_REFUND_AMOUNT", "PAYMENT_TIMESTAMP_MISSING"}
    shown = {item.metric_key: item.value for item in result.display}
    assert shown["average_paid_order_value"] == "54.85"
    assert shown["paid_order_total"] == "109.70"
    assert any('"quantity_reason":"AMOUNT_ONLY"' in (e.value or "") for e in result.evidence)
    assert all(f.evidence_ids for f in result.findings)
    assert {i for f in result.findings for i in f.evidence_ids} <= {
        e.evidence_id for e in result.evidence
    }
    assert DailyReport.model_validate_json(result.model_dump_json()) == result


def test_zero_denominator_and_no_payment_inference() -> None:
    result = report(
        raw(
            (
                order("pending", paid_at=None),
                order("old", created_at=START - timedelta(days=1), paid_at=None),
            )
        )
    )
    assert result.metrics is not None
    assert result.metrics.paid_order_count == 0
    assert result.metrics.orders_without_payment_timestamp == 1
    assert result.metrics.average_paid_order_value is None
    assert result.metrics.average_reason == "ZERO_DENOMINATOR"
    assert codes(result) == {
        "PAYMENT_TIMESTAMP_MISSING",
        "NO_RECORDED_PAYMENTS",
        "RULE_NOT_CONFIGURED",
    }
    assert (
        next(d.value for d in result.display if d.metric_key == "average_paid_order_value") is None
    )
    empty = report(raw())
    assert empty.complete and empty.metrics is not None
    assert empty.metrics.paid_order_total == 0 and empty.metrics.refund_amount == 0
    assert empty.metrics.created_order_count == 0 and empty.metrics.refund_count == 0


@pytest.mark.parametrize("status", ["cancelled", "refunded", "completed"])
def test_later_status_does_not_erase_recorded_payment(status: str) -> None:
    result = report(raw((order("1", status=status),)))
    assert result.metrics is not None and result.metrics.paid_order_count == 1


@pytest.mark.parametrize("field", ["created_at", "paid_at", "occurred_at"])
def test_microsecond_half_open_day(field: str) -> None:
    instants = (START - timedelta(microseconds=1), START, END - timedelta(microseconds=1), END)
    orders = tuple(
        order(str(i), created_at=START - timedelta(days=1), paid_at=None) for i in range(4)
    )
    refunds: tuple[dict[str, Any], ...] = ()
    if field == "occurred_at":
        refunds = tuple(
            refund(str(i), str(i), occurred_at=t, amount="1") for i, t in enumerate(instants)
        )
    else:
        orders = tuple({**o, field: t} for o, t in zip(orders, instants, strict=True))
    result = report(raw(orders, refunds=refunds))
    assert result.metrics is not None
    key = {
        "created_at": "created_order_count",
        "paid_at": "paid_order_count",
        "occurred_at": "refund_count",
    }[field]
    assert getattr(result.metrics, key) == 2
    if field == "occurred_at":
        assert result.metrics.refund_amount == 2


@pytest.mark.parametrize(
    "day,start,end,hours",
    [
        (
            date(2026, 3, 8),
            datetime(2026, 3, 8, 5, tzinfo=UTC),
            datetime(2026, 3, 9, 4, tzinfo=UTC),
            23,
        ),
        (
            date(2026, 11, 1),
            datetime(2026, 11, 1, 4, tzinfo=UTC),
            datetime(2026, 11, 2, 5, tzinfo=UTC),
            25,
        ),
    ],
)
def test_dst_days_use_local_midnights(
    day: date, start: datetime, end: datetime, hours: int
) -> None:
    source = {**SOURCE, "timezone": "America/New_York"}
    result = report(
        raw(
            tuple(
                order(str(i), source=source, created_at=t, paid_at=t)
                for i, t in enumerate((start, end - timedelta(microseconds=1), end))
            ),
            source=source,
            business_day=day,
            as_of=end + timedelta(minutes=2),
            coverage={"collection_started_at": end, "collected_at": end + timedelta(minutes=1)},
        )
    )
    assert (result.window.start, result.window.end) == (start, end)
    assert (end - start).total_seconds() == hours * 3600
    assert result.metrics is not None and result.metrics.paid_order_count == 2


@pytest.mark.parametrize(
    "currency", ["CNY", "USD", "EUR", "JPY", "GBP", "AUD", "CAD", "HKD", "CHF", "SGD"]
)
@pytest.mark.parametrize(
    "price,expected_cents,expected_yen",
    [
        ("1.005", "1.00", "1"),
        ("1.015", "1.02", "1"),
        ("2.5", "2.50", "2"),
        ("3.5", "3.50", "4"),
    ],
)
def test_currency_allowlist_and_half_even(
    currency: str, price: str, expected_cents: str, expected_yen: str
) -> None:
    source = {**SOURCE, "currency": currency}
    result = report(
        raw(
            (order("1", source=source, currency=currency, order_total=price, shipping_net=price),),
            source=source,
            rules={"currency": currency},
        )
    )
    display = {item.metric_key: item.value for item in result.display}
    assert display["average_paid_order_value"] == (
        expected_yen if currency == "JPY" else expected_cents
    )


def test_exact_average_and_hash_ignore_decimal_context_and_entity_order() -> None:
    body = raw(
        (order("b", shipping_net="1.005", order_total="1.005"), order("a")),
        refunds=(refund("a", "z", amount="0.01"), refund("b", "y", amount="0.02")),
    )
    expected = report(body)
    assert expected.metrics is not None
    assert expected.metrics.average_paid_order_value is not None
    assert expected.metrics.average_paid_order_value.model_dump() == {
        "numerator": "201",
        "denominator": "400",
    }
    assert (
        next(d.value for d in expected.display if d.metric_key == "average_paid_order_value")
        == "0.50"
    )
    with localcontext() as context:
        context.prec = 1
        context.traps[Inexact] = True
        context.traps[Rounded] = True
        actual = report(
            {
                **body,
                "orders": tuple(reversed(body["orders"])),
                "refunds": tuple(reversed(body["refunds"])),
            }
        )
    assert expected == actual
    assert expected.content_hash == actual.content_hash and expected.facts_hash == actual.facts_hash


@pytest.mark.parametrize(
    "bad", [True, 1, 1.0, float("nan"), "NaN", "1e2", "0.0000001", "100000000000000"]
)
def test_reject_invalid_money_and_input_overflow(bad: object) -> None:
    with pytest.raises(ValidationError):
        report(raw((order("1", order_total=bad),)))


@pytest.mark.parametrize("metric", ["paid", "refund"])
def test_aggregate_overflow_blocks_metrics_and_business_findings(metric: str) -> None:
    big = "99999999999999.999999"
    orders: tuple[dict[str, Any], ...] = (
        order("a", shipping_net=big, order_total=big),
        order("b", shipping_net="0.000001", order_total="0.000001"),
    )
    refunds = (refund("a", "1", amount=big), refund("b", "2", amount="0.000001"))
    if metric == "refund":
        orders = tuple({**o, "paid_at": None} for o in orders)
    result = report(
        raw(
            orders,
            refunds=refunds if metric == "refund" else (),
            rules={"currency": "CNY", "low_paid_total": "10", "high_refund_amount": "0"},
        )
    )
    assert not result.complete and result.metrics is None and result.display == ()
    assert codes(result) == {"AGGREGATE_OUT_OF_RANGE"}


@pytest.mark.parametrize(
    "coverage",
    [
        {"orders_complete": False},
        {"order_lines_complete": False},
        {"refunds_complete": False},
        {"quality_flags": ("MISSING_PAGE",)},
        {"quality_flags": ("CAPACITY_LIMIT",)},
        {"quality_flags": ("PAYMENT_STATUS_CONFLICT",)},
    ],
)
def test_incomplete_never_runs_metric_rules(coverage: dict[str, Any]) -> None:
    result = report(
        raw(
            coverage=coverage,
            rules={"currency": "CNY", "low_paid_total": "1", "high_refund_amount": "0"},
        )
    )
    assert not result.complete and result.metrics is None and result.display == ()
    assert codes(result) == {"SOURCE_INCOMPLETE"}


def test_amount_mismatch_even_outside_day_blocks_report() -> None:
    result = report(
        raw(
            (
                order(
                    "bad-old",
                    order_total="1",
                    created_at=START - timedelta(days=5),
                    paid_at=START - timedelta(days=4),
                ),
            )
        )
    )
    assert not result.complete and result.metrics is None
    assert codes(result) == {"ORDER_AMOUNT_MISMATCH"}


def test_threshold_equality_and_disabled_rules() -> None:
    body = raw(
        (order("1", shipping_net="10", order_total="10"),),
        refunds=(refund("1", amount="2"),),
        rules={"currency": "CNY", "low_paid_total": "10", "high_refund_amount": "2"},
    )
    assert codes(report(body)) == set()
    body["rules"] = {
        "currency": "CNY",
        "low_paid_total": "10.000001",
        "high_refund_amount": "1.999999",
    }
    assert codes(report(body)) == {"LOW_PAID_TOTAL", "HIGH_REFUND_AMOUNT"}
    body["rules"] = {"currency": "CNY"}
    assert codes(report(body)) == {"RULE_NOT_CONFIGURED"}


@pytest.mark.parametrize("kind", ["order", "line", "refund"])
@pytest.mark.parametrize("conflict", [False, True])
def test_duplicate_entities_rejected(kind: str, conflict: bool) -> None:
    first = {"order": order("1"), "line": line("1"), "refund": refund("1")}[kind]
    second = {**first}
    if conflict:
        second[{"order": "order_total", "line": "net_amount", "refund": "amount"}[kind]] = "1"
    body = raw(
        (first, second) if kind == "order" else (order("1"),),
        (first, second) if kind == "line" else (),
        (first, second) if kind == "refund" else (),
    )
    with pytest.raises(ValidationError, match="DUPLICATE_DAILY_ENTITY"):
        report(body)


@pytest.mark.parametrize("kind", ["order", "line", "refund"])
@pytest.mark.parametrize(
    "field,bad",
    [
        ("organization_id", UUID(int=8)),
        ("shop_id", UUID(int=8)),
        ("source_binding_id", UUID(int=8)),
        ("source_config_version", "other"),
        ("config_digest", "b" * 64),
    ],
)
def test_wrong_entity_source_rejected(kind: str, field: str, bad: object) -> None:
    bad_source = {**SOURCE, field: bad}
    body = raw(
        (order("1", source=bad_source if kind == "order" else SOURCE),),
        (line("1", source=bad_source),) if kind == "line" else (),
        (refund("1", source=bad_source),) if kind == "refund" else (),
    )
    with pytest.raises(ValidationError, match="DAILY_ENTITY_SOURCE_MISMATCH"):
        report(body)


@pytest.mark.parametrize("kind", ["line", "refund"])
def test_orphan_entities_rejected(kind: str) -> None:
    with pytest.raises(ValidationError, match="ORPHAN_DAILY_ENTITY"):
        report(
            raw(
                (order("1"),),
                (line("other"),) if kind == "line" else (),
                (refund("other"),) if kind == "refund" else (),
            )
        )


def test_refund_line_must_belong_to_same_order() -> None:
    with pytest.raises(ValidationError, match="ORPHAN_DAILY_REFUND_LINE"):
        report(
            raw(
                (order("1"), order("2")),
                (line("2"),),
                (
                    refund(
                        "1",
                        lines=({"line_id": "1", "quantity": 1, "quantity_reason": None},),
                        quantity_reason=None,
                    ),
                ),
            )
        )


@pytest.mark.parametrize("kind", ["order", "line", "refund", "rules"])
def test_currency_mismatch_rejected(kind: str) -> None:
    body = raw(
        (order("1", currency="USD" if kind == "order" else "CNY"),),
        (line("1", currency="USD"),) if kind == "line" else (),
        (refund("1", currency="USD"),) if kind == "refund" else (),
        rules={"currency": "USD" if kind == "rules" else "CNY"},
    )
    with pytest.raises(ValidationError, match="CURRENCY_MISMATCH|SOURCE_MISMATCH"):
        report(body)


@pytest.mark.parametrize(
    "update",
    [
        {"source": {**SOURCE, "currency": "BTC"}},
        {"business_day": "2026-11-02"},
        {"business_day": date(2026, 11, 3)},
        {"as_of": END - timedelta(microseconds=1)},
        {"unknown_field": True},
        {"source": {**SOURCE, "timezone": "Fake/Zone"}},
        {"orders": [order("1")]},
    ],
)
def test_strict_input_and_time_boundaries(update: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        report(raw(**update))


def test_report_facts_and_evidence_tampering_rejected() -> None:
    result = report(raw())
    body = result.model_dump(mode="python")
    body["content_hash"] = "b" * 64
    with pytest.raises(ValidationError, match="DAILY_FACTS_HASH_MISMATCH"):
        DailyReport.model_validate(body)
    body = result.model_dump(mode="python")
    body["evidence"][0]["value"] = "invented"
    with pytest.raises(ValidationError, match="DAILY_EVIDENCE_HASH_INVALID"):
        DailyReport.model_validate(body)


def test_nested_entity_order_and_quality_flag_order_are_canonical() -> None:
    body = raw(
        (order("a", order_total="3"), order("b")),
        (line("a", "2", net_amount="2"), line("a", "1", net_amount="1")),
        (
            refund(
                "a",
                lines=(
                    {"line_id": "2", "quantity": None, "quantity_reason": "UNKNOWN"},
                    {"line_id": "1", "quantity": 1, "quantity_reason": None},
                ),
                quantity_reason=None,
            ),
        ),
        coverage={"quality_flags": ("MISSING_PAGE", "SOURCE_CHANGED")},
    )
    first = report(body)
    other = {
        **body,
        "orders": tuple(reversed(body["orders"])),
        "order_lines": tuple(reversed(body["order_lines"])),
        "refunds": ({**body["refunds"][0], "lines": tuple(reversed(body["refunds"][0]["lines"]))},),
        "coverage": {**body["coverage"], "quality_flags": ("SOURCE_CHANGED", "MISSING_PAGE")},
    }
    assert report(other) == first
    assert first.metrics is None and codes(first) == {"SOURCE_INCOMPLETE"}


def test_line_and_refund_line_permutations_preserve_complete_report() -> None:
    body = raw(
        (order("a", order_total="3"),),
        (line("a", "2", net_amount="2"), line("a", "1", net_amount="1")),
        (
            refund(
                "a",
                lines=(
                    {"line_id": "2", "quantity": None, "quantity_reason": "UNKNOWN"},
                    {"line_id": "1", "quantity": 1, "quantity_reason": None},
                ),
                quantity_reason=None,
            ),
        ),
    )
    first = report(body)
    assert first.complete
    assert (
        report(
            {
                **body,
                "order_lines": tuple(reversed(body["order_lines"])),
                "refunds": (
                    {**body["refunds"][0], "lines": tuple(reversed(body["refunds"][0]["lines"]))},
                ),
            }
        )
        == first
    )


def test_negative_explicit_fee_and_large_components_are_exact() -> None:
    body = raw((order("a", order_total="1", shipping_net="2.005", fee_net="-1.005"),))
    baseline = report(body)
    assert baseline.metrics is not None and baseline.metrics.paid_order_total == 1
    assert next(d.value for d in baseline.display if d.metric_key == "paid_fee_net") == "-1.00"
    with localcontext() as context:
        context.prec = 1
        context.traps[Inexact] = True
        context.traps[Rounded] = True
        assert report(body) == baseline
    # paid total 只有 0.000003；仍须拒绝超界的 shipping 累计，不能只检查最终订单总额。
    result = report(
        raw(
            tuple(
                order(
                    str(i),
                    shipping_net="49999999999999.999999",
                    fee_net="-49999999999999.999998",
                    order_total="0.000001",
                )
                for i in range(3)
            )
        )
    )
    assert result.metrics is None and codes(result) == {"AGGREGATE_OUT_OF_RANGE"}


def test_repeating_average_is_exact_rational() -> None:
    result = report(raw((order("1", shipping_net="1", order_total="1"), order("2"), order("3"))))
    assert result.metrics is not None and result.metrics.average_paid_order_value is not None
    assert result.metrics.average_paid_order_value.model_dump() == {
        "numerator": "1",
        "denominator": "3",
    }
    assert (
        next(d.value for d in result.display if d.metric_key == "average_paid_order_value")
        == "0.33"
    )


@pytest.mark.parametrize("bad", [True, 1.1, "1", -1])
def test_quantities_reject_coercion(bad: object) -> None:
    with pytest.raises(ValidationError):
        report(raw((order("1"),), (line("1", quantity=bad),)))


@pytest.mark.parametrize(
    "update",
    [
        {"discovered_order_count": 1},
        {"discovered_line_count": 1},
        {"discovered_refund_count": 1},
        {"orders_complete": 1},
        {"refunds_complete": "true"},
        {"quality_flags": ("MISSING_PAGE", "MISSING_PAGE")},
        {"collection_started_at": END - timedelta(microseconds=1)},
        {"collected_at": END - timedelta(microseconds=1)},
        {"collected_at": END + timedelta(hours=2)},
        {"strategy": "full_store"},
    ],
)
def test_coverage_declaration_boundaries(update: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        report(raw(coverage=update))


@pytest.mark.parametrize(
    "change",
    [
        {"status": "custom-plugin-status"},
        {"paid_at": START - timedelta(microseconds=1)},
        {"created_at": datetime(2026, 11, 2)},
        {"paid_at": END + timedelta(minutes=2)},
    ],
)
def test_order_timestamp_and_status_rejected(change: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        report(raw((order("1", **change),)))


@pytest.mark.parametrize(
    "change",
    [
        {"amount": "-1"},
        {"amount": True},
        {"occurred_at": START - timedelta(microseconds=1)},
        {"occurred_at": END + timedelta(minutes=2)},
        {"quantity_reason": None},
        {
            "lines": ({"line_id": "1", "quantity": None, "quantity_reason": None},),
            "quantity_reason": None,
        },
        {
            "lines": ({"line_id": "1", "quantity": 1, "quantity_reason": None},) * 2,
            "quantity_reason": None,
        },
    ],
)
def test_refund_data_rejected(change: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        report(raw((order("1"),), (line("1"),), (refund("1", **change),)))


def test_snapshot_json_roundtrip_and_binding_changes_affect_facts() -> None:
    snapshot = DailyInput.model_validate(raw((order("1"),)))
    assert DailyInput.model_validate_json(snapshot.model_dump_json()) == snapshot
    baseline = aggregate_daily(snapshot)
    other = report(raw((order("1"),), snapshot_id=UUID(int=88)))
    assert baseline.content_hash != other.content_hash and baseline.facts_hash != other.facts_hash
    changed_rules = report(raw((order("1"),), rules={"currency": "CNY", "low_paid_total": "0"}))
    assert changed_rules.facts_hash != baseline.facts_hash


@pytest.mark.parametrize(
    "tamper", ["wrong_value", "missing", "empty", "duplicate", "extra", "reorder"]
)
@pytest.mark.parametrize("rehash", [False, True])
def test_display_must_be_exact_derivation_even_with_recomputed_hash(
    tamper: str, rehash: bool
) -> None:
    from commerceops.domain.commerce_values import facts_hash

    result = report(raw((order("1", shipping_net="12.34", order_total="12.34"),)))
    body = result.model_dump(mode="python")
    display = body["display"]
    if tamper == "wrong_value":
        display = tuple(
            {**item, "value": "999999.00"} if item["metric_key"] == "paid_order_total" else item
            for item in display
        )
    elif tamper == "missing":
        display = display[1:]
    elif tamper == "empty":
        display = ()
    elif tamper == "duplicate":
        display = (*display, display[0])
    elif tamper == "extra":
        display = (*display, {"metric_key": "paid_order_total", "value": "12.34"})
    else:
        display = tuple(reversed(display))
    body["display"] = display
    if rehash:
        body["facts_hash"] = facts_hash(result.canonical_facts())
    with pytest.raises(ValidationError, match="DAILY_DISPLAY_MISMATCH"):
        DailyReport.model_validate(body)


def test_legitimate_report_rebuild_json_and_low_context_validate() -> None:
    result = report(raw((order("1", shipping_net="1.015", order_total="1.015"), order("2"))))
    with localcontext() as context:
        context.prec = 1
        context.traps[Inexact] = True
        context.traps[Rounded] = True
        assert DailyReport.model_validate(result.model_dump(mode="python")) == result
        assert DailyReport.model_validate_json(result.model_dump_json()) == result
        assert (
            aggregate_daily(
                DailyInput.model_validate(
                    raw((order("1", shipping_net="1.015", order_total="1.015"), order("2")))
                )
            )
            == result
        )


def test_ratio_and_citation_binding_are_validated_beyond_report_hash() -> None:
    import json

    from commerceops.domain.commerce_values import facts_hash

    result = report(raw((order("1", shipping_net="1", order_total="1"),)))
    body = result.model_dump(mode="json")
    body["metrics"]["average_paid_order_value"] = {"numerator": "2", "denominator": "1"}
    body["facts_hash"] = facts_hash(
        {k: v for k, v in body.items() if k not in {"facts_hash", "display"}}
    )
    with pytest.raises(ValidationError, match="DAILY_AVERAGE_INVALID"):
        DailyReport.model_validate_json(json.dumps(body))
    body = result.model_dump(mode="json")
    finding = body["findings"][0]
    finding["evidence_ids"] = ("b" * 64,)
    finding["finding_id"] = facts_hash({k: v for k, v in finding.items() if k != "finding_id"})
    body["facts_hash"] = facts_hash(
        {k: v for k, v in body.items() if k not in {"facts_hash", "display"}}
    )
    with pytest.raises(ValidationError, match="DAILY_EVIDENCE_BINDING_INVALID"):
        DailyReport.model_validate_json(json.dumps(body))
