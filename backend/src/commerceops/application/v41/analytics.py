"""Decimal record/event metrics on the effective source; no settlement or profit inference."""

from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Any
from zoneinfo import ZoneInfo

from commerceops.application.v41 import contracts as dto
from commerceops.application.v41.effective import EffectiveView
from commerceops.domain.commerce_values import facts_hash

LOW_STOCK_UNITS = 3


def amount_text(value: Decimal) -> str:
    if not value.is_finite() or value < 0:
        raise ValueError("INVALID_AMOUNT")
    rendered = format(value, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def period_for(view: EffectiveView, query: dto.PeriodQuery) -> dto.Period:
    if query.shop_id != view.scope.shop_id:
        raise ValueError("RESOURCE_NOT_FOUND")
    end = query.to_date or view.latest_business_day + timedelta(days=1)
    start = query.from_date or end - timedelta(days=query.days)
    timezone = ZoneInfo(view.timezone)
    return dto.Period(
        from_date=start,
        to_date=end,
        timezone=view.timezone,
        from_utc=datetime.combine(start, time.min, timezone),
        to_utc=datetime.combine(end, time.min, timezone),
    )


def snapshot_for(view: EffectiveView, material: dict[str, Any], read_at: datetime) -> dto.Snapshot:
    revision = view.revision()
    return dto.Snapshot(
        data_revision=revision,
        snapshot_id=facts_hash(dict(data_revision=revision, query=material, rules="v41-rules-1")),
        read_at=read_at,
        source=view.source,
    )


def _metric(
    view: EffectiveView,
    identifier: dto.MetricId,
    known: Decimal,
    included: int,
    *,
    money: bool = False,
    reasons: tuple[dto.Reason, ...] = (),
    excluded: int = 0,
    unavailable: bool = False,
    settlement: bool = False,
) -> dto.Metric:
    partial = unavailable or bool(excluded) or "OUTSIDE_SOURCE_WINDOW" in reasons
    text = amount_text(known)
    return dto.Metric(
        metric=identifier,
        value=None if partial else text,
        known_value=text,
        unit="money" if money else "count",
        currency=view.currency if money else None,
        completeness="UNAVAILABLE" if unavailable else "PARTIAL" if partial else "COMPLETE",
        reason_codes=reasons,
        included_count=included,
        excluded_count=excluded,
        settlement_status="UNKNOWN" if settlement else "NOT_APPLICABLE",
    )


def period_metrics(view: EffectiveView, period: dto.Period) -> tuple[dto.Metric, ...]:
    if period.timezone != view.timezone or any(
        order.currency != view.currency
        or any(refund.currency != view.currency for refund in order.refunds)
        for order in view.orders
    ):
        raise ValueError("METRIC_SOURCE_MISMATCH")
    start, end = period.from_utc, period.to_utc
    created = [row for row in view.orders if start <= row.created_at < end]
    paid = [row for row in view.orders if row.paid_at is not None and start <= row.paid_at < end]
    # An unknown pay timestamp may fall in any later period. Never silently place it at creation.
    unknown = [row for row in view.orders if row.paid_at is None and row.created_at < end]
    refunds = [
        row for order in view.orders for row in order.refunds if start <= row.occurred_at < end
    ]
    outside: tuple[dto.Reason, ...] = (
        ("OUTSIDE_SOURCE_WINDOW",)
        if period.from_date < view.earliest_business_day
        or period.to_date > view.latest_business_day + timedelta(days=1)
        else ()
    )
    payment_reasons = outside + (("UNKNOWN_PAYMENT_TIME",) if unknown else ())
    with localcontext() as context:
        context.prec = 50
        paid_amount = sum((Decimal(row.net_amount) for row in paid), Decimal(0))
        refund_amount = sum((Decimal(row.amount) for row in refunds), Decimal(0))
        average = (
            (paid_amount / len(paid)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
            if paid
            else Decimal(0)
        )
    return (
        _metric(view, "created_order_count", Decimal(len(created)), len(created), reasons=outside),
        _metric(
            view,
            "paid_order_count",
            Decimal(len(paid)),
            len(paid),
            reasons=payment_reasons,
            excluded=len(unknown),
            settlement=True,
        ),
        _metric(
            view,
            "paid_order_amount",
            paid_amount,
            len(paid),
            money=True,
            reasons=payment_reasons,
            excluded=len(unknown),
            settlement=True,
        ),
        _metric(
            view,
            "refund_event_count",
            Decimal(len(refunds)),
            len(refunds),
            reasons=outside + ("UNKNOWN_SETTLEMENT",),
            settlement=True,
        ),
        _metric(
            view,
            "refund_event_amount",
            refund_amount,
            len(refunds),
            money=True,
            reasons=outside + ("UNKNOWN_SETTLEMENT",),
            settlement=True,
        ),
        _metric(
            view,
            "average_paid_order_amount",
            average,
            len(paid),
            money=True,
            reasons=payment_reasons + (() if paid else ("NO_DENOMINATOR",)),
            excluded=len(unknown),
            unavailable=not paid,
            settlement=True,
        ),
    )


def dashboard(view: EffectiveView, query: dto.PeriodQuery, read_at: datetime) -> dto.DashboardData:
    period = period_for(view, query)
    metrics = period_metrics(view, period)
    skus = [sku for product in view.products for sku in product.skus]
    unknown_stock = [sku for sku in skus if sku.available_units is None]
    low_stock = [
        sku
        for sku in skus
        if sku.available_units is not None and sku.available_units <= LOW_STOCK_UNITS
    ]
    metrics += (
        _metric(view, "product_count", Decimal(len(view.products)), len(view.products)),
        _metric(
            view,
            "low_stock_count",
            Decimal(len(low_stock)),
            len(skus) - len(unknown_stock),
            reasons=("UNKNOWN_STOCK",) if unknown_stock else (),
            excluded=len(unknown_stock),
        ),
    )
    points = []
    current = period.from_date
    while current < period.to_date:
        daily = period_for(
            view,
            dto.PeriodQuery(
                shop_id=query.shop_id, from_date=current, to_date=current + timedelta(days=1)
            ),
        )
        points.append(dto.TrendPoint(day=current, metrics=period_metrics(view, daily)))
        current += timedelta(days=1)
    unknown_payments = tuple(row.order_id for row in view.orders if row.paid_at is None)
    low_products = tuple(
        product.product_id
        for product in view.products
        if any(sku in low_stock for sku in product.skus)
    )
    refund_orders = tuple(
        order.order_id
        for order in view.orders
        if any(period.from_utc <= row.occurred_at < period.to_utc for row in order.refunds)
    )
    insights = [
        dto.RuleInsight(
            rule="unknown_cost",
            resource_ids=tuple(p.product_id for p in view.products[:100]),
            reason="UNKNOWN_COST",
        )
    ]
    if unknown_payments:
        insights.append(
            dto.RuleInsight(
                rule="unknown_payment_time",
                resource_ids=unknown_payments,
                reason="UNKNOWN_PAYMENT_TIME",
            )
        )
    if low_products:
        insights.append(
            dto.RuleInsight(
                rule="low_stock",
                resource_ids=low_products,
                reason=None,
                threshold_units=LOW_STOCK_UNITS,
            )
        )
    if refund_orders:
        insights.append(
            dto.RuleInsight(
                rule="refund_events", resource_ids=refund_orders, reason="UNKNOWN_SETTLEMENT"
            )
        )
    return dto.DashboardData(
        snapshot=snapshot_for(view, query.model_dump(mode="json"), read_at),
        period=period,
        metrics=metrics,
        trend=tuple(points),
        insights=tuple(insights),
    )
