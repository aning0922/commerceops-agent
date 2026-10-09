"""最小确定性分页/故障合同，不部署服务，不代表网络联调。"""

import base64
from dataclasses import replace
from pathlib import Path

import pytest
from commerceops.adapters.commerce.mock import Behavior, Endpoint, Fixture, MockCommerce
from commerceops.application.commerce.contracts import (
    DTO,
    CommerceFailure,
    ErrorCode,
    OrderLine,
    Page,
    Product,
    Quality,
    Refund,
    Window,
)
from commerceops.application.commerce.ports import CommercePort
from commerceops.domain.commerce_values import complete_days

pytestmark = pytest.mark.offline
DIRECTORY = Path(__file__).parent / "fixtures/commerce/inventory-v1"


def window(fixture: Fixture) -> Window:
    start, end = complete_days(fixture.now, fixture.source.timezone)
    return Window(start=start, end=end)


def collect[T: DTO](pages: list[Page[T]]) -> tuple[T, ...]:
    return tuple(item for page in pages for item in page.items)


def test_five_ports_pagination_and_true_empty() -> None:
    fixture = Fixture.load(DIRECTORY, "statuses")
    port: CommercePort = MockCommerce(fixture, page_size=2)
    pages = [port.list_order_lines(window(fixture))]
    while pages[-1].next_cursor is not None:
        pages.append(port.list_order_lines(window(fixture), cursor=pages[-1].next_cursor))
    assert collect(pages) == fixture.orders
    assert not pages[0].complete and pages[-1].complete
    assert all(not p.warnings and p.error is None for p in pages)
    assert port.capabilities().read_only and port.capabilities().refund_scope == "order_cohort"
    assert port.list_products().complete
    assert port.list_refunds(()).complete
    assert port.get_inventory(fixture.products[0].sku_key).item == fixture.inventories[0]
    empty = MockCommerce(Fixture.load(DIRECTORY, "empty_products"))
    assert empty.list_products().complete and empty.list_products().items == ()
    assert empty.list_order_lines(window(fixture)).complete
    missing = port.get_inventory("missing")
    assert (
        not missing.complete
        and missing.error
        and missing.error.code == ErrorCode.RESOURCE_NOT_FOUND
    )


@pytest.mark.parametrize(
    "code", [ErrorCode.TIMEOUT, ErrorCode.RATE_LIMITED, ErrorCode.PROVIDER_UNAVAILABLE]
)
@pytest.mark.parametrize("nth", [1, 2, 3])
def test_nth_call_failure_retry_and_reset(code: ErrorCode, nth: int) -> None:
    fixture = Fixture.load(DIRECTORY, "statuses")
    mock = MockCommerce(fixture, page_size=2, behavior=Behavior(fail_on_call=nth, failure=code))
    cursor = None
    for _ in range(nth - 1):
        cursor = mock.list_order_lines(window(fixture), cursor=cursor).next_cursor
    failed = mock.list_order_lines(window(fixture), cursor=cursor)
    assert not failed.complete and not failed.items
    assert failed.error and failed.error.code == code and failed.error.partial_page == nth
    assert failed.warnings == (Quality.PARTIAL_FAILURE,)
    assert failed.next_cursor == cursor
    recovered = mock.list_order_lines(window(fixture), cursor=cursor)
    assert recovered.error is None and len(recovered.items) == 2
    assert mock.call_counts == {"orders": nth + 1}
    mock.reset_call_counts()
    assert mock.call_counts == {}
    for _ in range(nth - 1):
        mock.list_order_lines(window(fixture))
    assert mock.list_order_lines(window(fixture)).error is not None


@pytest.mark.parametrize(
    "setting,flag",
    [
        ("duplicate_second_page", Quality.DUPLICATE_ID),
        ("omit_second_page", Quality.MISSING_PAGE),
        ("change_second_page", Quality.SOURCE_CHANGED),
    ],
)
def test_anomalies_never_become_complete(setting: str, flag: Quality) -> None:
    fixture = Fixture.load(DIRECTORY, "statuses")
    behavior = Behavior(
        duplicate_second_page=setting == "duplicate_second_page",
        omit_second_page=setting == "omit_second_page",
        change_second_page=setting == "change_second_page",
    )
    mock = MockCommerce(fixture, page_size=2, behavior=behavior)
    pages = [mock.list_order_lines(window(fixture))]
    while pages[-1].next_cursor:
        pages.append(mock.list_order_lines(window(fixture), cursor=pages[-1].next_cursor))
    assert all(not page.complete and flag in page.warnings for page in pages)
    rows = collect(pages)
    assert len({(row.order_id, row.line_id) for row in rows}) == len(rows)
    if setting == "duplicate_second_page":
        assert rows == fixture.orders
    elif setting == "omit_second_page":
        assert len(rows) == len(fixture.orders) - 2
    else:
        assert rows[2].quantity == fixture.orders[2].quantity + 1
        assert rows[2].source.raw_hash != fixture.orders[2].source.raw_hash


def test_capacity_limit_first_page_is_not_full_snapshot() -> None:
    fixture = Fixture.load(DIRECTORY, "statuses")
    mock = MockCommerce(fixture, page_size=2, behavior=Behavior(max_pages=1))
    result = mock.list_order_lines(window(fixture))
    assert len(result.items) == 2 and result.next_cursor is None and not result.complete
    assert result.warnings == (Quality.CAPACITY_LIMIT,)


@pytest.mark.parametrize(
    "bad", ["garbage", "", base64.b64encode(b"{}").decode(), base64.b64encode(b"[null]").decode()]
)
def test_invalid_cursor_is_safe(bad: str) -> None:
    mock = MockCommerce(Fixture.load(DIRECTORY, "statuses"), page_size=2)
    with pytest.raises(CommerceFailure, match="INVALID_CURSOR") as raised:
        mock.list_products(cursor=bad)
    assert raised.value.error.retryable is False
    assert mock.call_counts == {}


def test_cursor_bound_to_query_endpoint_fixture_page_size() -> None:
    fixture = Fixture.load(DIRECTORY, "statuses")
    mock = MockCommerce(fixture, page_size=2)
    cursor = mock.list_order_lines(window(fixture)).next_cursor
    assert cursor
    other = Window(start=fixture.orders[0].created_at, end=fixture.now)
    for action in (
        lambda: mock.list_products(cursor=cursor),
        lambda: mock.list_order_lines(other, cursor=cursor),
        lambda: MockCommerce(fixture, page_size=3).list_order_lines(window(fixture), cursor=cursor),
        lambda: MockCommerce(Fixture.load(DIRECTORY), page_size=2).list_order_lines(
            window(fixture), cursor=cursor
        ),
    ):
        with pytest.raises(CommerceFailure, match="INVALID_CURSOR"):
            action()


def test_cohort_refunds_not_cashflow_and_stock_is_not_decremented() -> None:
    fixture = Fixture.load(DIRECTORY, "cross_period")
    mock = MockCommerce(fixture)
    orders = mock.list_order_lines(window(fixture)).items
    assert [row.order_id for row in orders] == ["o1"]
    refunds = mock.list_refunds(tuple(row.order_id for row in orders))
    assert [row.refund_id for row in refunds.items] == ["r-later"]
    assert not window(fixture).contains(refunds.items[0].created_at)
    assert mock.get_inventory(fixture.products[0].sku_key).item == fixture.inventories[0]
    result = mock.get_inventory(fixture.products[0].sku_key)
    assert result.item is not None and result.item.available_stock == 20


def test_quality_hard_blocks_and_deleted_product() -> None:
    for case, flag in [
        ("unknown_stock", Quality.UNKNOWN_STOCK),
        ("identity", Quality.SHARED_POOL_UNRESOLVED),
    ]:
        fixture = Fixture.load(DIRECTORY, case)
        mock = MockCommerce(fixture)
        result = mock.get_inventory(fixture.products[0].sku_key)
        assert not result.complete and flag in result.warnings
        if case == "identity":
            page = mock.list_order_lines(window(fixture))
            assert not page.complete and Quality.DELETED_PRODUCT in page.warnings
    unknown = Fixture.load(DIRECTORY, "unknown_inbound")
    result = MockCommerce(unknown).get_inventory(unknown.products[0].sku_key)
    assert result.complete and result.item and result.item.inbound_units is None


@pytest.mark.parametrize("endpoint", ["products", "orders", "refunds", "inventory"])
def test_all_endpoints_share_safe_fault_contract(endpoint: Endpoint) -> None:
    fixture = Fixture.load(DIRECTORY, "mixed_refunds")
    behavior = Behavior(endpoint=endpoint, fail_on_call=1, failure=ErrorCode.PROVIDER_UNAVAILABLE)
    mock = MockCommerce(fixture, behavior=behavior)
    result: Page[Product] | Page[OrderLine] | Page[Refund]
    if endpoint == "products":
        result = mock.list_products()
    elif endpoint == "orders":
        result = mock.list_order_lines(window(fixture))
    elif endpoint == "refunds":
        result = mock.list_refunds(("o1",))
    else:
        inventory = mock.get_inventory(fixture.products[0].sku_key)
        assert not inventory.complete and inventory.error and inventory.error.provider_code == "500"
        return
    assert not result.complete and result.error and result.error.provider_code == "500"


def test_stable_reruns_and_provenance() -> None:
    a = Fixture.load(DIRECTORY)
    b = Fixture.load(DIRECTORY)
    assert (
        MockCommerce(a).list_products().model_dump_json()
        == MockCommerce(b).list_products().model_dump_json()
    )
    assert a.source.provenance.source_kind == "mock"
    assert a.source.provenance.fixture_version == "inventory-v1"
    assert a.now == b.now
    copied = replace(a, products=())
    assert MockCommerce(copied).list_products().complete
