"""Independent QA goldens; never call V41 aggregation to manufacture expected numbers."""

import copy
from datetime import date

import pytest
from commerceops.application.v4_demo.seed_contract import generate_seed

from .kpi_reference import reference

pytestmark = pytest.mark.offline


def test_full_default_ledger_and_unknown_payment_are_not_zero() -> None:
    content = generate_seed().content.model_dump(mode="json")
    gold = reference(content, "TWD", date(2026, 10, 26), date(2026, 11, 2))
    assert set(gold) == {
        "created_order_count",
        "paid_order_count",
        "paid_order_amount",
        "refund_event_count",
        "refund_event_amount",
        "average_paid_order_amount",
        "product_count",
        "low_stock_count",
    }
    assert gold["created_order_count"]["value"] == "7"
    assert gold["paid_order_amount"]["value"] is None
    assert gold["paid_order_amount"]["known_value"] == "2140"
    assert gold["paid_order_count"]["known_value"] == "6"
    assert gold["average_paid_order_amount"]["known_value"] == "356.666667"
    assert gold["refund_event_amount"]["value"] == "90"
    assert gold["refund_event_amount"]["settlement_status"] == "UNKNOWN"
    assert gold["product_count"]["value"] == "8" and gold["low_stock_count"]["value"] == "1"


def test_raw_currency_boundary_empty_and_import_do_not_invent_sales() -> None:
    content = generate_seed().content.model_dump(mode="json")
    for currency in ["TWD", "CNY"]:
        before = reference(content, currency, date(2026, 10, 26), date(2026, 11, 2))
        after = reference(content, currency, date(2026, 10, 26), date(2026, 11, 2), imported=1)
        assert after["product_count"]["value"] == "9"
        for metric in ["paid_order_amount", "refund_event_amount", "created_order_count"]:
            assert after[metric] == before[metric]
        assert after["low_stock_count"]["value"] is None
        assert after["low_stock_count"]["excluded_count"] == 1
    empty = reference(content, "TWD", date(2026, 10, 19), date(2026, 10, 20))
    assert empty["created_order_count"]["value"] == "0"
    assert empty["average_paid_order_amount"]["value"] is None
    assert empty["average_paid_order_amount"]["completeness"] == "UNAVAILABLE"
    mixed = copy.deepcopy(content)
    mixed["shops"][0]["orders"][0]["currency"] = "CNY"
    with pytest.raises(ValueError, match="mixed currency"):
        reference(mixed, "TWD", date(2026, 10, 26), date(2026, 11, 2))


def test_civil_midnight_boundary_and_outside_window_remain_explicit() -> None:
    content = generate_seed().content.model_dump(mode="json")
    baseline = reference(content, "TWD", date(2026, 10, 26), date(2026, 11, 2))
    just_before = copy.deepcopy(content)
    just_before["shops"][0]["orders"][0]["created_at"] = "2026-10-25T15:59:59.999999+00:00"
    exact = copy.deepcopy(content)
    exact["shops"][0]["orders"][0]["created_at"] = "2026-10-25T16:00:00+00:00"
    assert (
        reference(just_before, "TWD", date(2026, 10, 26), date(2026, 11, 2))["created_order_count"]
        == baseline["created_order_count"]
    )
    assert (
        reference(exact, "TWD", date(2026, 10, 26), date(2026, 11, 2))["created_order_count"][
            "value"
        ]
        == "8"
    )
    outside = reference(content, "TWD", date(2026, 10, 18), date(2026, 11, 2))
    assert outside["paid_order_amount"]["value"] is None
    assert "OUTSIDE_SOURCE_WINDOW" in outside["paid_order_amount"]["reason_codes"]
