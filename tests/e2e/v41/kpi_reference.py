"""QA ledger reference from raw seed facts, independent of V41 effective/analytics code."""

from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Any
from zoneinfo import ZoneInfo


def reference(
    content: dict[str, Any], currency: str, start: date, end: date, *, imported: int = 0
) -> dict[str, dict[str, Any]]:
    shops = [s for s in content["shops"] if s["currency"] == currency]
    if len(shops) != 1 or imported < 0 or not 0 < (end - start).days <= 90:
        raise ValueError("single source currency and bounded period required")
    shop = shops[0]
    zone = ZoneInfo(shop["timezone"])

    # Bucket each raw event by the shop's civil day, not browser/UTC date or order creation.
    def day(text: str) -> date:
        return datetime.fromisoformat(text).astimezone(zone).date()

    orders = shop["orders"]
    if any(o["currency"] != currency for o in orders) or any(
        r["currency"] != currency for r in shop["refunds"]
    ):
        raise ValueError("mixed currency facts refused")
    created = [o for o in orders if start <= day(o["created_at"]) < end]
    paid = [o for o in orders if o["paid_at"] is not None and start <= day(o["paid_at"]) < end]
    unknown = sum(o["paid_at"] is None and day(o["created_at"]) < end for o in orders)
    refunds = [r for r in shop["refunds"] if start <= day(r["occurred_at"]) < end]
    outside = start < date.fromisoformat(
        content["earliest_business_day"]
    ) or end > date.fromisoformat(content["latest_business_day"]) + timedelta(days=1)
    base_reasons = ["OUTSIDE_SOURCE_WINDOW"] if outside else []
    result: dict[str, dict[str, Any]] = {}

    def record(
        name: str,
        value: Decimal,
        included: int,
        excluded: int = 0,
        *,
        money: bool = False,
        reasons: list[str] | None = None,
        unavailable: bool = False,
        settlement: bool = False,
    ) -> None:
        reasons = reasons or []
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        partial = bool(excluded or "OUTSIDE_SOURCE_WINDOW" in reasons)
        result[name] = {
            "metric": name,
            "value": None if partial or unavailable else text,
            "known_value": text,
            "unit": "money" if money else "count",
            "currency": currency if money else None,
            "completeness": "UNAVAILABLE" if unavailable else "PARTIAL" if partial else "COMPLETE",
            "reason_codes": reasons,
            "included_count": included,
            "excluded_count": excluded,
            "settlement_status": "UNKNOWN" if settlement else "NOT_APPLICABLE",
        }

    record("created_order_count", Decimal(len(created)), len(created), reasons=base_reasons)
    reasons = base_reasons + (["UNKNOWN_PAYMENT_TIME"] if unknown else [])
    with localcontext() as context:
        context.prec = 50
        paid_amount = sum((Decimal(o["net_amount"]) for o in paid), Decimal(0))
        refund_amount = sum((Decimal(r["amount"]) for r in refunds), Decimal(0))
        average = (
            (paid_amount / len(paid)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
            if paid
            else Decimal(0)
        )
    record(
        "paid_order_count", Decimal(len(paid)), len(paid), unknown, reasons=reasons, settlement=True
    )
    record(
        "paid_order_amount",
        paid_amount,
        len(paid),
        unknown,
        money=True,
        reasons=reasons,
        settlement=True,
    )
    record(
        "average_paid_order_amount",
        average,
        len(paid),
        unknown,
        money=True,
        reasons=reasons + ([] if paid else ["NO_DENOMINATOR"]),
        unavailable=not paid,
        settlement=True,
    )
    record(
        "refund_event_count",
        Decimal(len(refunds)),
        len(refunds),
        reasons=base_reasons + ["UNKNOWN_SETTLEMENT"],
        settlement=True,
    )
    record(
        "refund_event_amount",
        refund_amount,
        len(refunds),
        money=True,
        reasons=base_reasons + ["UNKNOWN_SETTLEMENT"],
        settlement=True,
    )
    unknown_stock = sum(s["available_units"] is None for s in shop["inventory"]) + imported
    low = sum(
        s["available_units"] is not None and s["available_units"] <= 3 for s in shop["inventory"]
    )
    record(
        "product_count", Decimal(len(shop["products"]) + imported), len(shop["products"]) + imported
    )
    record(
        "low_stock_count",
        Decimal(low),
        len(shop["inventory"]) + imported - unknown_stock,
        unknown_stock,
        reasons=["UNKNOWN_STOCK"] if unknown_stock else [],
    )
    return result


def assert_metrics(actual: dict[str, Any], expected: dict[str, dict[str, Any]]) -> None:
    metrics = {row["metric"]: row for row in actual["metrics"]}
    if len(actual["metrics"]) != 8 or metrics != expected:
        raise AssertionError("V41_INDEPENDENT_KPI_LEDGER_MISMATCH")
