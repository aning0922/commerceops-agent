"""首批 Woo CommercePort；平台只读观测，不接通任务或审批执行。"""

import hashlib
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

import httpx

from commerceops.adapters.commerce.woocommerce_config import WooReadOnlyConfig
from commerceops.adapters.commerce.woocommerce_http import WooHTTP, WooReadFailure, platform_id
from commerceops.application.commerce.contracts import (
    DTO,
    Capabilities,
    CommerceFailure,
    ErrorCode,
    Inventory,
    InventoryResult,
    OrderLine,
    Page,
    Product,
    Provenance,
    Quality,
    Refund,
    RefundLine,
    Source,
    Window,
    error,
)
from commerceops.domain.commerce_values import (
    canonical_bytes,
    facts_hash,
    integer,
    money,
    sku_key,
    stock_pool_key,
)


def gmt(value: Any, *, optional: bool = False) -> datetime | None:
    if optional and value is None:
        return None
    if type(value) is not str:
        raise ValueError("INVALID_GMT_TIME")
    instant = datetime.fromisoformat(value)
    if instant.utcoffset() is None:
        instant = instant.replace(tzinfo=UTC)
    if instant.utcoffset() != timedelta(0):
        raise ValueError("GMT_OFFSET_MISMATCH")
    return instant.astimezone(UTC)


def object_rows(value: Any) -> list[dict[str, Any]]:
    if type(value) is not list or any(type(row) is not dict for row in value):
        raise ValueError("INVALID_ARRAY")
    return cast(list[dict[str, Any]], value)


class WooCommerce:
    def __init__(self, config: WooReadOnlyConfig, *, transport: httpx.BaseTransport | None = None):
        self.config = config
        self.http = WooHTTP(config, transport=transport)
        self.captured_at = datetime.now(UTC)
        self.source = Source(
            shop_id=config.shop_id,
            timezone=config.timezone,
            currency=config.currency,
            provenance=Provenance(
                source_kind="woocommerce_test",
                fixture_version=None,
                captured_at=self.captured_at,
                raw_hash=facts_hash(
                    {
                        "origin": config.base_url,
                        "shop": config.shop_id,
                        "timezone": config.timezone,
                        "currency": config.currency,
                        "generation": str(uuid4()),
                    }
                ),
            ),
        )
        self._binding = self.source.provenance.raw_hash
        self._cache: dict[str, tuple[DTO, ...]] = {}
        self._cursors: dict[str, tuple[str, int]] = {}
        self._catalog: dict[str, tuple[Product, dict[str, Any], bool]] = {}
        self._orders: dict[str, dict[str, Any]] = {}

    def close(self) -> None:
        self.http.close()

    def capabilities(self) -> Capabilities:
        return Capabilities(source_kind="woocommerce_test", currencies=(self.config.currency,))

    def _provenance(self, row: dict[str, Any]) -> Provenance:
        return self.source.provenance.model_copy(
            update={"raw_hash": hashlib.sha256(canonical_bytes(row)).hexdigest()}
        )

    def _page[T: DTO](
        self,
        model: type[T],
        query: str,
        cursor: str | None,
        read: Callable[[], tuple[T, ...]],
    ) -> Page[T]:
        offset = 0
        if cursor is not None:
            if type(cursor) is not str or len(cursor) > 256 or cursor not in self._cursors:
                raise CommerceFailure(error(ErrorCode.INVALID_CURSOR))
            bound, offset = self._cursors[cursor]
            if bound != query:
                raise CommerceFailure(error(ErrorCode.INVALID_CURSOR))
        try:
            self.http.remaining()
            if query not in self._cache:
                self._cache[query] = read()
            rows = cast(tuple[T, ...], self._cache[query])
            selected = rows[offset : offset + self.config.per_page]
            next_offset = offset + self.config.per_page
            token = None
            if next_offset < len(rows):
                token = hashlib.sha256(
                    canonical_bytes([self._binding, query, next_offset])
                ).hexdigest()
                self._cursors[token] = (query, next_offset)
            return Page[model](  # type: ignore[valid-type]
                items=selected,
                next_cursor=token,
                source=self.source,
                observed_at=self.captured_at,
                complete=token is None,
            )
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
            code = exc.code if isinstance(exc, WooReadFailure) else ErrorCode.INVALID_DATA
            quality = exc.quality if isinstance(exc, WooReadFailure) else Quality.PARTIAL_FAILURE
            return Page[model](  # type: ignore[valid-type]
                items=(),
                next_cursor=cursor,
                source=self.source,
                observed_at=self.captured_at,
                complete=False,
                warnings=(quality,),
                error=error(code).model_copy(
                    update={
                        "provider_code": None,
                        "retry_after_seconds": self.http.retry_after_seconds
                        if code == ErrorCode.RATE_LIMITED
                        else None,
                    }
                ),
            )

    def _products(self) -> tuple[Product, ...]:
        parents = self.http.scan("products", {"status": "any"})
        variants: tuple[dict[str, Any], ...]
        catalog: dict[str, tuple[Product, dict[str, Any], bool]] = {}
        for parent in parents:
            pid = platform_id(parent["id"])
            if type(parent["manage_stock"]) is not bool:
                raise ValueError("INVALID_PARENT_MANAGE_STOCK")
            if parent["type"] == "simple":
                variants = (parent,)
                variant_mode = False
            elif parent["type"] == "variable":
                variants = self.http.scan(f"products/{pid}/variations", {"status": "any"})
                expected = parent["variations"]
                if type(expected) is not list or {platform_id(v) for v in expected} != {
                    platform_id(v["id"]) for v in variants
                }:
                    raise WooReadFailure(ErrorCode.INVALID_DATA, Quality.SOURCE_CHANGED)
                variant_mode = True
            else:
                raise ValueError("UNSUPPORTED_PRODUCT_TYPE")
            for row in variants:
                vid = platform_id(row["id"]) if variant_mode else None
                manage = row["manage_stock"]
                if type(manage) is not bool and manage != "parent":
                    raise ValueError("INVALID_MANAGE_STOCK")
                inherited = variant_mode and (
                    manage == "parent" or (manage is False and parent["manage_stock"])
                )
                if inherited and not parent["manage_stock"]:
                    raise ValueError("UNRESOLVED_PARENT_MANAGE_STOCK")
                stock = parent if inherited else row
                pool = stock_pool_key(self.config.shop_id, pid if inherited or vid is None else vid)
                label = row["sku"]
                if type(label) is not str:
                    raise ValueError("INVALID_SKU_LABEL")
                product = Product(
                    source=self._provenance(row),
                    shop_id=self.config.shop_id,
                    product_id=pid,
                    variant_id=vid,
                    sku_key=sku_key(self.config.shop_id, pid, vid),
                    sku_label=label or None,
                    title=row.get("name", parent["name"]),
                    active=parent["status"] == "publish" and row["status"] == "publish",
                    stock_pool_key=pool,
                )
                if product.sku_key in catalog:
                    raise WooReadFailure(ErrorCode.INVALID_DATA, Quality.DUPLICATE_ID)
                if len(catalog) >= 1000:
                    raise WooReadFailure(ErrorCode.INVALID_DATA, Quality.CAPACITY_LIMIT)
                catalog[product.sku_key] = product, stock, inherited
        self._catalog = catalog
        return tuple(item[0] for _, item in sorted(catalog.items()))

    def list_products(self, *, cursor: str | None = None) -> Page[Product]:
        return self._page(Product, "products:" + self._binding, cursor, self._products)

    def _order_lines(self, window: Window) -> tuple[OrderLine, ...]:
        if window != self.config.window:
            raise ValueError("WINDOW_OUTSIDE_CONFIG")
        products = self.list_products()
        if products.error is not None:
            raise WooReadFailure(
                products.error.code,
                products.warnings[0] if products.warnings else Quality.PARTIAL_FAILURE,
            )
        query: dict[str, str | int] = {
            # dates_are_gmt selects the GMT column, but WP_Date_Query converts
            # offset-bearing strings to shop-local time before SQL comparison.
            # Send UTC wall-clock values without an offset for that GMT column.
            "after": (window.start - timedelta(seconds=1)).replace(tzinfo=None).isoformat(),
            "before": window.end.replace(tzinfo=None).isoformat(),
            "dates_are_gmt": "true",
            "status": "any",
            "dp": 6,
        }
        raw = self.http.scan("orders", query)
        orders: dict[str, dict[str, Any]] = {}
        rows: list[OrderLine] = []
        seen: set[tuple[str, str]] = set()
        for order in raw:
            created = gmt(order["date_created_gmt"])
            if created is None or not window.contains(created):
                continue
            oid = platform_id(order["id"])
            if order["currency"] != self.config.currency:
                raise ValueError("CURRENCY_MISMATCH")
            orders[oid] = order
            for line in object_rows(order["line_items"]):
                line_id = platform_id(line["id"])
                identity = oid, line_id
                if identity in seen:
                    raise WooReadFailure(ErrorCode.INVALID_DATA, Quality.DUPLICATE_ID)
                seen.add(identity)
                pid = platform_id(line["product_id"])
                vid = platform_id(line["variation_id"], zero=True)
                if len(rows) >= 10000:
                    raise WooReadFailure(ErrorCode.INVALID_DATA, Quality.CAPACITY_LIMIT)
                rows.append(
                    OrderLine(
                        source=self._provenance(order),
                        order_id=oid,
                        line_id=line_id,
                        sku_key=sku_key(self.config.shop_id, pid, vid if vid != "0" else None),
                        status=order["status"],
                        created_at=created,
                        paid_at=gmt(order["date_paid_gmt"], optional=True),
                        completed_at=gmt(order["date_completed_gmt"], optional=True),
                        quantity=integer(line["quantity"]),
                        net_amount=money(line["total"]),
                        tax_amount=money(line["total_tax"]),
                        currency=order["currency"],
                    )
                )
        self._orders = orders
        return tuple(rows)

    def list_order_lines(self, window: Window, *, cursor: str | None = None) -> Page[OrderLine]:
        query = "orders:" + facts_hash(window.model_dump(mode="json"))
        page = self._page(OrderLine, query, cursor, lambda: self._order_lines(window))
        if page.error is None and any(
            isinstance(row, OrderLine) and row.sku_key not in self._catalog
            for row in self._cache.get(query, ())
        ):
            return page.model_copy(
                update={"warnings": (Quality.DELETED_PRODUCT,), "complete": False}
            )
        return page

    @property
    def observed_order_ids(self) -> tuple[str, ...]:
        """成功读取本窗口后供本批采集器取完整cohort；不从可能为空的订单行推断。"""
        query = "orders:" + facts_hash(self.config.window.model_dump(mode="json"))
        if query not in self._cache:
            raise CommerceFailure(error(ErrorCode.INVALID_DATA))
        return tuple(sorted(self._orders))

    def _refunds(self, ids: tuple[str, ...]) -> tuple[Refund, ...]:
        if any(re.fullmatch(r"[1-9][0-9]*", oid) is None or oid not in self._orders for oid in ids):
            raise ValueError("UNKNOWN_ORDER_COHORT")
        rows: list[Refund] = []
        seen_refunds: set[str] = set()
        for oid in ids:
            order = self._orders[oid]
            originals = {platform_id(line["id"]) for line in object_rows(order["line_items"])}
            observed = self.http.scan(f"orders/{oid}/refunds", {"dp": 6})
            expected_ids = {platform_id(r["id"]) for r in object_rows(order["refunds"])}
            if expected_ids != {platform_id(r["id"]) for r in observed}:
                raise WooReadFailure(ErrorCode.INVALID_DATA, Quality.SOURCE_CHANGED)
            for refund in observed:
                refund_id = platform_id(refund["id"])
                if refund_id in seen_refunds:
                    raise WooReadFailure(ErrorCode.INVALID_DATA, Quality.DUPLICATE_ID)
                seen_refunds.add(refund_id)
                lines: list[RefundLine] = []
                for line in object_rows(refund["line_items"]):
                    links = [
                        item["value"]
                        for item in object_rows(line["meta_data"])
                        if item.get("key") == "_refunded_item_id"
                    ]
                    if len(links) != 1:
                        raise ValueError("REFUND_ORIGINAL_LINE_MISSING")
                    link = links[0]
                    if type(link) is str and re.fullmatch(r"[1-9][0-9]*", link):
                        original_id = link
                    else:
                        original_id = platform_id(link)
                    if original_id not in originals:
                        raise ValueError("REFUND_ORIGINAL_LINE_MISMATCH")
                    quantity = line.get("quantity")
                    if quantity is not None:
                        quantity = integer(quantity)
                        if quantity > 0:
                            raise ValueError("INVALID_REFUND_SIGN")
                        quantity = -quantity
                    lines.append(
                        RefundLine(
                            line_id=original_id,
                            refunded_quantity=quantity,
                            quantity_reason="REFUND_QUANTITY_UNAVAILABLE"
                            if quantity is None
                            else None,
                        )
                    )
                amount = money(refund["amount"])
                if amount < 0:
                    amount = -amount
                if len(rows) >= 10000:
                    raise WooReadFailure(ErrorCode.INVALID_DATA, Quality.CAPACITY_LIMIT)
                rows.append(
                    Refund(
                        source=self._provenance(refund),
                        refund_id=platform_id(refund["id"]),
                        order_id=oid,
                        created_at=cast(datetime, gmt(refund["date_created_gmt"])),
                        refund_amount=amount,
                        currency=order["currency"],
                        lines=tuple(sorted(lines, key=lambda line: line.line_id)),
                        restocked=None,
                        quantity_reason="AMOUNT_ONLY_REFUND" if not lines else None,
                    )
                )
        return tuple(rows)

    def list_refunds(
        self, order_ids: tuple[str, ...], *, cursor: str | None = None
    ) -> Page[Refund]:
        if type(order_ids) is not tuple or any(type(oid) is not str for oid in order_ids):
            raise CommerceFailure(error(ErrorCode.INVALID_DATA))
        ids = tuple(sorted(set(order_ids)))
        return self._page(Refund, "refunds:" + facts_hash(ids), cursor, lambda: self._refunds(ids))

    def get_inventory(self, key: str) -> InventoryResult:
        try:
            self.http.remaining()
            if not self._catalog:
                page = self.list_products()
                if page.error is not None:
                    return InventoryResult(
                        item=None,
                        source=self.source,
                        observed_at=self.captured_at,
                        complete=False,
                        warnings=page.warnings,
                        error=page.error,
                    )
            if key not in self._catalog:
                raise WooReadFailure(ErrorCode.RESOURCE_NOT_FOUND)
            product, raw, shared = self._catalog[key]
            manage = raw["manage_stock"]
            if type(manage) is not bool:
                raise ValueError("INVALID_STOCK_MANAGEMENT")
            quantity = raw["stock_quantity"]
            if quantity is not None:
                quantity = integer(quantity)
            available = quantity if manage else None
            stock_reason = (
                ("STOCK_QUANTITY_UNKNOWN" if manage else "STOCK_NOT_MANAGED")
                if available is None
                else None
            )
            if raw["stock_status"] not in {"instock", "outofstock", "onbackorder"}:
                raise ValueError("INVALID_STOCK_STATUS")
            warnings = tuple(
                q
                for condition, q in (
                    (available is None, Quality.UNKNOWN_STOCK),
                    (shared, Quality.SHARED_POOL_UNRESOLVED),
                )
                if condition
            )
            item = Inventory(
                source=self._provenance(raw),
                sku_key=product.sku_key,
                stock_pool_key=product.stock_pool_key,
                manage_stock=manage,
                available_stock=available,
                stock_reason=stock_reason,
                stock_status=raw["stock_status"],
                backorders=raw["backorders"],
                stock_semantics="adapter_available_already_adjusted",
                observed_at=self.captured_at,
                source_version=raw.get("date_modified_gmt"),
                inbound_units=None,
                inbound_reason="WOOCOMMERCE_INBOUND_UNAVAILABLE",
                inbound_quality="unknown",
                pool_allocation="unresolved" if shared else "exact",
            )
            return InventoryResult(
                item=item,
                source=self.source,
                observed_at=self.captured_at,
                complete=not warnings,
                warnings=warnings,
            )
        except (ValueError, KeyError, TypeError, OverflowError) as exc:
            code = exc.code if isinstance(exc, WooReadFailure) else ErrorCode.INVALID_DATA
            return InventoryResult(
                item=None,
                source=self.source,
                observed_at=self.captured_at,
                complete=False,
                warnings=(Quality.PARTIAL_FAILURE,),
                error=error(code).model_copy(
                    update={
                        "provider_code": None,
                        "retry_after_seconds": self.http.retry_after_seconds
                        if code == ErrorCode.RATE_LIMITED
                        else None,
                    }
                ),
            )
