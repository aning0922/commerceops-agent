"""Bounded MockCommerce read facade. Real source construction remains server-owned."""

import hashlib
import json
import unicodedata
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext
from time import monotonic
from typing import Any, Literal, Protocol

from commerceops.adapters.commerce.mock import MockCommerce
from commerceops.application.commerce.contracts import OrderLine, Page, Product, Refund
from commerceops.application.commerce.contracts import Window as CommerceWindow
from commerceops.application.commerce.inventory_analysis import EXCLUDED_STATUSES
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

    def catalog(self) -> dict[str, Product]:
        products: dict[str, Product] = {}
        for page in self.pages(lambda cursor: self.source.list_products(cursor=cursor)):
            for product in page.items:
                if product.shop_id != self.context.shop_id or product.sku_key in products:
                    raise Incomplete("INVALID_CATALOG")
                products[product.sku_key] = product
        return products


def order_eligibility(row: OrderLine) -> Literal["included", "excluded", "review"]:
    """Frozen COMMERCE_INTEGRATION §4 / inventory_analysis effective-order rule."""
    if row.status in {"processing", "completed"} or (
        row.status == "refunded"
        and any(
            instant is not None and row.created_at <= instant <= row.source.captured_at
            for instant in (row.paid_at, row.completed_at)
        )
    ):
        return "included"
    return "excluded" if row.status in EXCLUDED_STATUSES else "review"


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
                for product in meter.catalog().values():
                    if query in {
                        normalized(product.sku_key),
                        normalized(product.title),
                        normalized(product.sku_label or ""),
                    }:
                        candidate = product.sku_label or ""
                        label = (
                            candidate
                            if candidate.isascii() and candidate.isalnum() and len(candidate) <= 40
                            else product.sku_key[:80]
                        )
                        matches.append(ProductMatch(sku_key=product.sku_key, label=label))
                if len(matches) > 100 or len({item.sku_key for item in matches}) != len(matches):
                    raise Incomplete("PRODUCT_CAPACITY")
                products = tuple(matches)
                skus = tuple(item.sku_key for item in products)
            elif isinstance(call, InventoryCall):
                skus = tuple(sorted(set(call.args.skus)))
                catalog = meter.catalog()
                if not set(skus) <= catalog.keys():
                    raise Incomplete("SKU_NOT_FOUND")
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
                    if item.stock_pool_key != catalog[sku].stock_pool_key:
                        raise Incomplete("STOCK_POOL_MISMATCH")
                    unresolved = (
                        item.pool_allocation == "unresolved"
                        or sum(
                            product.stock_pool_key == item.stock_pool_key
                            for product in catalog.values()
                        )
                        > 1
                    )
                    flags = tuple(
                        sorted(
                            {flag.value for flag in inventory_result.warnings}
                            | ({"SHARED_POOL_UNRESOLVED"} if unresolved else set())
                        )
                    )
                    inventory_facts: tuple[tuple[Metric, int | None], ...] = (
                        ("available_stock", None if unresolved else item.available_stock),
                        ("inbound_units", None if unresolved else item.inbound_units),
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
                skus = tuple(sorted(set(call.args.skus)))
                catalog = meter.catalog()
                if not set(skus) <= catalog.keys():
                    raise Incomplete("SKU_NOT_FOUND")
                for window in windows:
                    valid: list[OrderLine] = []
                    line_ids: set[tuple[str, str]] = set()
                    order_skus: dict[str, set[str]] = {}
                    observed = self.source.fixture.now
                    commerce_window = CommerceWindow(start=window.start, end=window.end)

                    def fetch_orders(
                        cursor: str | None, selected_window: CommerceWindow = commerce_window
                    ) -> Page[OrderLine]:
                        return self.source.list_order_lines(selected_window, cursor=cursor)

                    review = False
                    for page in meter.pages(fetch_orders):
                        observed = page.observed_at
                        for row in page.items:
                            line = (row.order_id, row.line_id)
                            if line in line_ids or not commerce_window.contains(row.created_at):
                                raise Incomplete("INVALID_ORDER_LINE")
                            line_ids.add(line)
                            order_skus.setdefault(row.order_id, set()).add(row.sku_key)
                            if row.sku_key in skus:
                                state = order_eligibility(row)
                                if state == "included":
                                    valid.append(row)
                                elif state == "review":
                                    review = True
                    if review:
                        raise Incomplete("ORDER_STATUS_REVIEW")
                    eligible_ids = tuple(sorted({row.order_id for row in valid}))
                    refunds: list[Refund] = []
                    refund_observed = observed
                    if eligible_ids:
                        seen_refunds: set[str] = set()

                        def fetch_refunds(
                            cursor: str | None, ids: tuple[str, ...] = eligible_ids
                        ) -> Page[Refund]:
                            return self.source.list_refunds(ids, cursor=cursor)

                        for page in meter.pages(fetch_refunds):
                            refund_observed = page.observed_at
                            for refund in page.items:
                                if (
                                    refund.refund_id in seen_refunds
                                    or refund.order_id not in eligible_ids
                                ):
                                    raise Incomplete("INVALID_REFUND_COHORT")
                                seen_refunds.add(refund.refund_id)
                                # Total refund amount has no per-line monetary allocation in v1.
                                if len(order_skus[refund.order_id]) != 1:
                                    raise Incomplete("REFUND_SCOPE_REVIEW")
                                refunds.append(refund)
                    for sku in skus:
                        selected = [row for row in valid if row.sku_key == sku]
                        currencies = sorted({row.currency for row in selected}) or [
                            self.source.fixture.source.currency
                        ]
                        for currency in currencies:
                            lines = [row for row in selected if row.currency == currency]
                            units = sum(row.quantity for row in lines)
                            with localcontext() as decimal_context:
                                decimal_context.prec = 50
                                amount = sum((row.net_amount for row in lines), Decimal(0))
                                average = (
                                    None
                                    if not lines
                                    else (amount / len(lines)).quantize(
                                        Decimal("0.000001"), rounding=ROUND_HALF_UP
                                    )
                                )
                            for metric, fact_value, unit, flags in (
                                ("sold_units", str(units), "件", ()),
                                ("order_net", format(amount, "f"), "金额", ()),
                                (
                                    "order_average",
                                    None if average is None else format(average, "f"),
                                    "金额",
                                    ("ZERO_DENOMINATOR",) if average is None else (),
                                ),
                            ):
                                facts.append(
                                    Fact(
                                        evidence_id=key(
                                            (
                                                context.source_binding,
                                                call.tool_call_id,
                                                sku,
                                                window.model_dump_json(),
                                                metric,
                                                currency,
                                            )
                                        ),
                                        metric=metric,
                                        sku_key=sku,
                                        window=window,
                                        as_of=observed,
                                        value=fact_value,
                                        unit=unit,
                                        currency=currency,
                                        quality_flags=flags,
                                    )
                                )
                        sku_refunds = [
                            refund for refund in refunds if order_skus[refund.order_id] == {sku}
                        ]
                        for currency in sorted({refund.currency for refund in sku_refunds}):
                            with localcontext() as decimal_context:
                                decimal_context.prec = 50
                                refunded = sum(
                                    (
                                        refund.refund_amount
                                        for refund in sku_refunds
                                        if refund.currency == currency
                                    ),
                                    Decimal(0),
                                )
                            facts.append(
                                Fact(
                                    evidence_id=key(
                                        (
                                            context.source_binding,
                                            call.tool_call_id,
                                            sku,
                                            window.model_dump_json(),
                                            "refund_cohort",
                                            currency,
                                        )
                                    ),
                                    metric="refund_cohort",
                                    sku_key=sku,
                                    window=window,
                                    as_of=refund_observed,
                                    value=format(refunded, "f"),
                                    unit="金额",
                                    currency=currency,
                                )
                            )
            else:
                raise ValueError("UNSUPPORTED_TOOL")
        except Incomplete as exc:
            return ReadResult(
                tool_call_id=call.tool_call_id,
                shop_id=context.shop_id,
                source_binding=context.source_binding,
                snapshot_id=key((context.source_binding, call.tool_call_id)),
                as_of=self.source.fixture.now,
                complete=False,
                quality_flags=(str(exc),),
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
