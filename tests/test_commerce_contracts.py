"""P201 DTO/值对象合同；P202 规则尚未实现。"""

import json
from datetime import UTC, datetime
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from commerceops.adapters.commerce.mock import Fixture
from commerceops.application.commerce.contracts import (
    CommerceError,
    ErrorCode,
    Inventory,
    OrderLine,
    Page,
    Product,
    Refund,
    Window,
    error,
)
from commerceops.domain.commerce_values import (
    canonical_bytes,
    complete_days,
    facts_hash,
    money,
    sku_key,
    stock_pool_key,
    utc_time,
)
from pydantic import ValidationError

pytestmark = pytest.mark.offline
DIRECTORY = Path(__file__).parent / "fixtures/commerce/inventory-v1"


def test_ids_do_not_depend_on_sku_label_and_cannot_collide() -> None:
    assert sku_key("shop/a", "product", None) != sku_key("shop", "a/product", None)
    assert sku_key("demo", "100", None) != sku_key("demo", "100", "0")
    assert stock_pool_key("demo", "parent") == "pool/demo/parent"
    fixture = Fixture.load(DIRECTORY, "identity")
    assert len({p.sku_key for p in fixture.products}) == 4
    assert [p.sku_label for p in fixture.products] == [None, "", "SAME", "SAME"]
    raw = fixture.products[0].model_dump(mode="python")
    raw["sku_key"] = "wrong"
    with pytest.raises(ValidationError, match="SKU_IDENTITY_MISMATCH"):
        Product.model_validate(raw)


@pytest.mark.parametrize("bad", [True, False, 1.0, 1.5, "1", float("nan"), Decimal("1")])
@pytest.mark.parametrize("kind,field", [(OrderLine, "quantity"), (Inventory, "available_stock")])
def test_strict_quantities(
    kind: type[OrderLine] | type[Inventory], field: str, bad: object
) -> None:
    fixture = Fixture.load(DIRECTORY)
    raw: dict[str, Any] = (
        fixture.orders[0] if kind is OrderLine else fixture.inventories[0]
    ).model_dump(mode="python")
    raw[field] = bad
    with pytest.raises(ValidationError, match="INVALID_INTEGER"):
        kind.model_validate(raw)


@pytest.mark.parametrize(
    "bad",
    [
        True,
        0.1,
        Decimal("NaN"),
        Decimal("Infinity"),
        "NaN",
        "1e2",
        "1.0000001",
        "100000000000000",
        "USD 1",
    ],
)
def test_money_rejects_lossy_or_nonfinite_inputs(bad: object) -> None:
    with pytest.raises(ValueError):
        money(bad)


def test_money_json_canonical_and_numeric20_6_boundary() -> None:
    row = Fixture.load(DIRECTORY).orders[0]
    assert isinstance(row.net_amount, Decimal)
    assert json.loads(row.model_dump_json())["net_amount"] == "10.5"
    assert money("99999999999999.999999") == Decimal("99999999999999.999999")
    assert canonical_bytes({"money": Decimal("-0.000"), "ratio": Fraction(16, 14)}) == (
        b'{"money":"0","ratio":{"denominator":"7","numerator":"8"}}'
    )
    a = {"b": None, "a": Fraction(8, 7), "m": Decimal("10.500000")}
    b = {"m": Decimal("10.5"), "a": Fraction(16, 14), "b": None}
    assert facts_hash(a) == facts_hash(b)
    assert facts_hash(a) != facts_hash({**a, "b": 0})
    with pytest.raises(ValueError):
        canonical_bytes(1.0)


@pytest.mark.parametrize("currency", ["AAA", "cny", "CN", "CNYY", " CNY", "BTC"])
def test_invalid_or_unsupported_currency(currency: str) -> None:
    raw = Fixture.load(DIRECTORY).orders[0].model_dump(mode="python")
    raw["currency"] = currency
    with pytest.raises(ValidationError, match="UNSUPPORTED_CURRENCY"):
        OrderLine.model_validate(raw)


def test_timezone_utc_and_half_open_days() -> None:
    now = utc_time("2026-10-08T10:00:00+08:00")
    start, end = complete_days(now, "Asia/Shanghai")
    window = Window(start=start, end=end)
    assert start.isoformat() == "2026-09-30T16:00:00+00:00"
    assert end.isoformat() == "2026-10-07T16:00:00+00:00"
    assert window.contains(start) and not window.contains(end)
    assert now.tzinfo == UTC
    with pytest.raises(ValueError, match="NAIVE_TIME"):
        utc_time(datetime(2026, 10, 1))
    with pytest.raises(ValueError):
        complete_days(now, "Invalid/Timezone")
    with pytest.raises(ValidationError, match="INVALID_WINDOW"):
        Window(start=end, end=start)


@pytest.mark.parametrize(
    "now,hours", [("2026-03-09T12:00:00-04:00", 167), ("2026-11-02T12:00:00-05:00", 169)]
)
def test_dst_natural_days(now: str, hours: int) -> None:
    start, end = complete_days(utc_time(now), "America/New_York")
    assert (end - start).total_seconds() / 3600 == hours


def test_refund_unknown_not_zero_and_negative_amount_rejected() -> None:
    fixture = Fixture.load(DIRECTORY, "mixed_refunds")
    assert fixture.refunds[0].lines[0].refunded_quantity == 2
    assert fixture.refunds[1].lines[0].refunded_quantity is None
    raw = fixture.refunds[1].model_dump(mode="python")
    raw["lines"][0]["quantity_reason"] = None
    with pytest.raises(ValidationError, match="UNKNOWN_QUANTITY_REASON_REQUIRED"):
        Refund.model_validate(raw)
    raw = fixture.refunds[0].model_dump(mode="python")
    raw["refund_amount"] = Decimal("-1")
    with pytest.raises(ValidationError):
        Refund.model_validate(raw)
    raw["refund_amount"] = Decimal("1")
    raw["lines"][0]["refunded_quantity"] = True
    with pytest.raises(ValidationError, match="INVALID_INTEGER"):
        Refund.model_validate(raw)


def test_inventory_unknown_reason_and_source_semantics() -> None:
    fixture = Fixture.load(DIRECTORY, "unknown_inbound")
    raw = fixture.inventories[0].model_dump(mode="python")
    assert raw["inbound_units"] is None
    assert raw["available_stock"] == 20
    raw["inbound_reason"] = None
    with pytest.raises(ValidationError, match="UNKNOWN_REASON_MISMATCH"):
        Inventory.model_validate(raw)
    assert Fixture.load(DIRECTORY, "backlog").inventories[0].available_stock == -5


def test_safe_errors_frozen_dto_and_false_completeness() -> None:
    fixture = Fixture.load(DIRECTORY)
    failure = error(ErrorCode.RATE_LIMITED, page=2)
    assert failure.retryable and failure.retry_after_seconds == 2 and failure.provider_code == "429"
    raw = failure.model_dump(mode="python")
    raw["safe_message"] = "untrusted provider body"
    with pytest.raises(ValidationError, match="UNSAFE_MESSAGE"):
        CommerceError.model_validate(raw)
    with pytest.raises(ValidationError, match="FALSE_COMPLETENESS"):
        Page[Product](
            items=(),
            next_cursor="opaque",
            source=fixture.source,
            observed_at=fixture.now,
            complete=True,
        )
    with pytest.raises(ValidationError, match="frozen_instance"):
        field = "quantity"
        setattr(fixture.orders[0], field, 1)
    assert error(ErrorCode.INVALID_DATA).retryable is False
    assert "untrusted" not in str(failure)
