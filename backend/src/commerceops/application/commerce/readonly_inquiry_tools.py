"""Bounded MockCommerce read facade. Real source construction remains server-owned."""

import hashlib
import json
import unicodedata
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext
from time import monotonic
from typing import Any, Protocol

from commerceops.adapters.commerce.mock import MockCommerce
from commerceops.application.commerce.contracts import OrderLine, Page, Refund
from commerceops.application.commerce.contracts import Window as CommerceWindow
from commerceops.application.commerce.readonly_inquiry_contracts import (
    Context,
    Fact,
    InventoryCall,
    Metric,
    OrdersCall,
    ProductMatch,
    ProductsCall,
    ReadResult,
    ReportsCall,
    ToolCall,
    Window,
)


class ReportReader(Protocol):
    """Caller supplies the existing current-identity authorized report read path."""

    async def read(self, context: Context, report_id: str, deadline: float) -> ReadResult: ...


class Incomplete(ValueError):
    pass


@dataclass
class Meter:
    source: MockCommerce
    context: Context
    deadline: float
    remaining: int
    clock: Callable[[], float]
    scanned: int = 0

    def check(self) -> None:
        if self.clock() >= self.deadline:
            raise Incomplete("TIMEOUT")

    def pages(self, fetch: Callable[[str | None], Page[Any]]) -> Iterator[Page[Any]]:
        seen: set[str] = set()
        cursor: str | None = None
        while True:
            self.check()
            # This source has a fixed page_size; reserve its entire possible page before I/O.
            if self.remaining - self.scanned < self.source.page_size:
                raise Incomplete("CAPACITY_LIMIT")
            page = fetch(cursor)
            self.check()
            self.scanned += len(page.items)
            if self.scanned > self.remaining:
                raise Incomplete("CAPACITY_LIMIT")
            if (
                page.source.shop_id != self.context.shop_id
                or page.source.provenance.raw_hash != self.context.source_binding
                or page.error is not None
                or page.warnings
            ):
                raise Incomplete("SOURCE_INCOMPLETE")
            yield page
            if page.next_cursor is None:
                if not page.complete:
                    raise Incomplete("SOURCE_INCOMPLETE")
                return
            if page.complete or page.next_cursor in seen:
                raise Incomplete("CURSOR_INVALID")
            seen.add(page.next_cursor)
            cursor = page.next_cursor


def key(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def normalized(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().strip()


class MockReadFacade:
    def __init__(
        self,
        source: MockCommerce,
        report_reader: ReportReader | None = None,
        *,
        clock: Callable[[], float] = monotonic,
    ):
        if type(source) is not MockCommerce:
            raise ValueError("UNOWNED_SOURCE")
        self.source, self.report_reader, self.clock = source, report_reader, clock

    async def read(
        self, context: Context, call: ToolCall, deadline: float, rows_remaining: int
    ) -> ReadResult:
        if (
            context.shop_id != self.source.fixture.source.shop_id
            or context.source_binding != self.source.fixture.source.provenance.raw_hash
        ):
            raise ValueError("SOURCE_BINDING_MISMATCH")
        meter = Meter(self.source, context, deadline, rows_remaining, self.clock)
        if isinstance(call, ReportsCall):
            if self.report_reader is None:
                raise ValueError("REPORT_READ_UNAVAILABLE")
            meter.check()
            result = await self.report_reader.read(context, call.args.report_id, deadline)
            meter.check()
            return result
        facts: list[Fact] = []
        products: tuple[ProductMatch, ...] = ()
        windows: tuple[Window, ...] = ()
        skus: tuple[str, ...] = ()
        try:
            if isinstance(call, ProductsCall):
                matches: list[ProductMatch] = []
                query = normalized(call.args.query)
                for page in meter.pages(lambda cursor: self.source.list_products(cursor=cursor)):
                    for product in page.items:
                        if product.shop_id != context.shop_id:
                            raise Incomplete("SOURCE_SCOPE")
                        if query in {
                            normalized(product.sku_key),
                            normalized(product.title),
                            normalized(product.sku_label or ""),
                        }:
                            candidate = product.sku_label or ""
                            label = (
                                candidate
                                if candidate.isascii()
                                and candidate.isalnum()
                                and len(candidate) <= 40
                                else product.sku_key[:80]
                            )
                            matches.append(ProductMatch(sku_key=product.sku_key, label=label))
                if len(matches) > 100 or len({item.sku_key for item in matches}) != len(matches):
                    raise Incomplete("PRODUCT_CAPACITY")
                products = tuple(matches)
                skus = tuple(item.sku_key for item in products)
            elif isinstance(call, InventoryCall):
                skus = call.args.skus
                for sku in skus:
                    meter.check()
                    if meter.remaining - meter.scanned < 1:
                        raise Incomplete("CAPACITY_LIMIT")
                    inventory_result = self.source.get_inventory(sku)
                    meter.scanned += 1
                    meter.check()
                    if (
                        inventory_result.source.shop_id != context.shop_id
                        or inventory_result.source.provenance.raw_hash != context.source_binding
                    ):
                        raise Incomplete("SOURCE_SCOPE")
                    item = inventory_result.item
                    if item is None or inventory_result.error is not None or item.sku_key != sku:
                        raise Incomplete("SOURCE_INCOMPLETE")
                    # The underlying complete flag is false for known quality warnings.
                    if any(
                        flag.value not in {"UNKNOWN_STOCK", "SHARED_POOL_UNRESOLVED"}
                        for flag in inventory_result.warnings
                    ):
                        raise Incomplete("SOURCE_INCOMPLETE")
                    flags = tuple(flag.value for flag in inventory_result.warnings)
                    inventory_facts: tuple[tuple[Metric, int | None], ...] = (
                        ("available_stock", item.available_stock),
                        ("inbound_units", item.inbound_units),
                    )
                    for metric, value in inventory_facts:
                        facts.append(
                            Fact(
                                evidence_id=key(
                                    (context.source_binding, call.tool_call_id, sku, metric)
                                ),
                                metric=metric,
                                sku_key=sku,
                                as_of=item.observed_at,
                                value=None if value is None else str(value),
                                unit="件",
                                quality_flags=flags,
                            )
                        )
            elif isinstance(call, OrdersCall):
                windows = call.args.windows
                ordered = sorted(windows, key=lambda window: window.start)
                if len(ordered) == 2 and ordered[0].end > ordered[1].start:
                    raise Incomplete("OVERLAPPING_WINDOWS")
                skus = call.args.skus
                for window in windows:
                    order_ids: set[str] = set()
                    line_ids: set[tuple[str, str]] = set()
                    units = 0
                    by_currency: dict[str, Decimal] = {}
                    count_by_currency: dict[str, int] = {}
                    observed = None
                    commerce_window = CommerceWindow(start=window.start, end=window.end)

                    def fetch_orders(
                        cursor: str | None, selected_window: CommerceWindow = commerce_window
                    ) -> Page[OrderLine]:
                        return self.source.list_order_lines(selected_window, cursor=cursor)

                    for page in meter.pages(fetch_orders):
                        observed = page.observed_at
                        for row in page.items:
                            line = (row.order_id, row.line_id)
                            if line in line_ids:
                                raise Incomplete("DUPLICATE_ORDER_LINE")
                            line_ids.add(line)
                            if row.sku_key in skus:
                                order_ids.add(row.order_id)
                                units += row.quantity
                                count_by_currency[row.currency] = (
                                    count_by_currency.get(row.currency, 0) + 1
                                )
                                with localcontext() as decimal_context:
                                    decimal_context.prec = 50
                                    by_currency[row.currency] = (
                                        by_currency.get(row.currency, Decimal(0)) + row.net_amount
                                    )
                    at = observed or self.source.fixture.now
                    facts.append(
                        Fact(
                            evidence_id=key(
                                (
                                    context.source_binding,
                                    call.tool_call_id,
                                    window.model_dump_json(),
                                    "sold_units",
                                )
                            ),
                            metric="sold_units",
                            window=window,
                            as_of=at,
                            value=str(units),
                            unit="件",
                        )
                    )
                    for currency, amount in sorted(by_currency.items()):
                        facts.append(
                            Fact(
                                evidence_id=key(
                                    (
                                        context.source_binding,
                                        call.tool_call_id,
                                        window.model_dump_json(),
                                        "order_net",
                                        currency,
                                    )
                                ),
                                metric="order_net",
                                window=window,
                                as_of=at,
                                value=format(amount, "f"),
                                unit="金额",
                                currency=currency,
                            )
                        )
                    if not by_currency:
                        facts.append(
                            Fact(
                                evidence_id=key(
                                    (
                                        context.source_binding,
                                        call.tool_call_id,
                                        window.model_dump_json(),
                                        "order_average",
                                        self.source.fixture.source.currency,
                                    )
                                ),
                                metric="order_average",
                                window=window,
                                as_of=at,
                                value=None,
                                unit="金额",
                                currency=self.source.fixture.source.currency,
                                quality_flags=("ZERO_DENOMINATOR",),
                            )
                        )
                    for currency, amount in sorted(by_currency.items()):
                        with localcontext() as decimal_context:
                            decimal_context.prec = 50
                            average = (amount / count_by_currency[currency]).quantize(
                                Decimal("0.000001"), rounding=ROUND_HALF_UP
                            )
                        facts.append(
                            Fact(
                                evidence_id=key(
                                    (
                                        context.source_binding,
                                        call.tool_call_id,
                                        window.model_dump_json(),
                                        "order_average",
                                        currency,
                                    )
                                ),
                                metric="order_average",
                                window=window,
                                as_of=at,
                                value=format(average, "f"),
                                unit="金额",
                                currency=currency,
                            )
                        )
                    if order_ids:
                        refund_total: dict[str, Decimal] = {}
                        refund_observed = at
                        refund_seen: set[str] = set()
                        ids = tuple(sorted(order_ids))

                        def fetch_refunds(
                            cursor: str | None, selected_ids: tuple[str, ...] = ids
                        ) -> Page[Refund]:
                            return self.source.list_refunds(selected_ids, cursor=cursor)

                        for page in meter.pages(fetch_refunds):
                            refund_observed = page.observed_at
                            for row in page.items:
                                if row.refund_id in refund_seen or row.order_id not in order_ids:
                                    raise Incomplete("INVALID_REFUND_COHORT")
                                refund_seen.add(row.refund_id)
                                with localcontext() as decimal_context:
                                    decimal_context.prec = 50
                                    refund_total[row.currency] = (
                                        refund_total.get(row.currency, Decimal(0))
                                        + row.refund_amount
                                    )
                        for currency, amount in sorted(refund_total.items()):
                            facts.append(
                                Fact(
                                    evidence_id=key(
                                        (
                                            context.source_binding,
                                            call.tool_call_id,
                                            window.model_dump_json(),
                                            "refund_cohort",
                                            currency,
                                        )
                                    ),
                                    metric="refund_cohort",
                                    window=window,
                                    as_of=refund_observed,
                                    value=format(amount, "f"),
                                    unit="金额",
                                    currency=currency,
                                )
                            )
            else:
                raise ValueError("UNSUPPORTED_TOOL")
        except Incomplete:
            return ReadResult(
                tool_call_id=call.tool_call_id,
                shop_id=context.shop_id,
                source_binding=context.source_binding,
                snapshot_id=key((context.source_binding, call.tool_call_id)),
                as_of=self.source.fixture.now,
                complete=False,
                scanned_rows=meter.scanned,
                sku_keys=(),
                windows=windows,
            )
        return ReadResult(
            tool_call_id=call.tool_call_id,
            shop_id=context.shop_id,
            source_binding=context.source_binding,
            snapshot_id=key((context.source_binding, call.tool_call_id)),
            as_of=self.source.fixture.now,
            complete=True,
            scanned_rows=meter.scanned,
            sku_keys=skus,
            products=products,
            facts=tuple(facts),
            windows=windows,
        )
