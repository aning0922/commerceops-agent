"""Same-source filtered pages, signed cursors, JSON CSV exports and read-only context."""

import base64
import binascii
import csv
import hashlib
import hmac
import io
import json
from collections.abc import Callable, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from commerceops.application.v4_demo.contracts import Contract
from commerceops.application.v41 import contracts as dto
from commerceops.application.v41.analytics import (
    LOW_STOCK_UNITS,
    dashboard,
    period_for,
    snapshot_for,
)
from commerceops.application.v41.effective import EffectiveView, product_detail
from commerceops.domain.commerce_values import canonical_bytes, facts_hash


def _filter_material(query: Contract) -> dict[str, Any]:
    return query.model_dump(mode="json", exclude={"limit", "cursor"})


def _bound(view: EffectiveView, query: dto.Query) -> None:
    if query.shop_id != view.scope.shop_id:
        raise ValueError("RESOURCE_NOT_FOUND")


def _signature(data: str, secret: bytes) -> str:
    if len(secret) < 32:
        raise ValueError("CURSOR_SIGNING_CONFIGURATION")
    return hmac.new(secret, b"v41-page-v1:" + data.encode("ascii"), hashlib.sha256).hexdigest()


def _encode(material: dict[str, Any], secret: bytes) -> str:
    data = base64.urlsafe_b64encode(canonical_bytes(material)).decode("ascii").rstrip("=")
    return data + "." + _signature(data, secret)


def _decode(cursor: str, secret: bytes) -> dict[str, Any]:
    if len(cursor) > 2048 or not cursor.isascii():
        raise ValueError("INVALID_REQUEST")
    parts = cursor.split(".")
    if len(parts) != 2 or not hmac.compare_digest(_signature(parts[0], secret), parts[1]):
        raise ValueError("INVALID_REQUEST")
    try:
        raw = base64.b64decode(parts[0] + "=" * (-len(parts[0]) % 4), altchars=b"-_", validate=True)
        value = json.loads(raw)
    except (ValueError, binascii.Error, UnicodeError):
        raise ValueError("INVALID_REQUEST") from None
    if not isinstance(value, dict):
        raise ValueError("INVALID_REQUEST")
    return value


def _position[T: Contract](
    view: EffectiveView,
    query: dto.PageQuery | dto.OrderQuery | dto.DrilldownQuery,
    items: tuple[T, ...],
    generation: int,
    secret: bytes,
    identity: Callable[[T], UUID],
    sort_value: Callable[[T], str],
) -> tuple[int, dict[str, Any]]:
    _bound(view, query)
    if type(generation) is not int or generation < 0:
        raise ValueError("INVALID_REQUEST")
    if len(secret) < 32:
        raise ValueError("CURSOR_SIGNING_CONFIGURATION")
    base = dict(
        v=1,
        scope=view.scope.model_dump(mode="json"),
        generation=generation,
        revision=view.revision(),
        query=facts_hash(_filter_material(query)),
    )
    if query.cursor is None:
        return 0, base
    material = _decode(query.cursor, secret)
    for index, item in enumerate(items):
        expected = dict(base, last_id=str(identity(item)), last_key=sort_value(item))
        if material == expected:
            return index + 1, base
    raise ValueError("SNAPSHOT_CHANGED")


def _page[T: Contract](
    view: EffectiveView,
    query: dto.PageQuery | dto.OrderQuery | dto.DrilldownQuery,
    items: tuple[T, ...],
    read_at: datetime,
    generation: int,
    secret: bytes,
    identity: Callable[[T], UUID],
    sort_value: Callable[[T], str],
    *,
    response_model: type[dto.Page[T]],
) -> dto.Page[T]:
    start, base = _position(view, query, items, generation, secret, identity, sort_value)
    end = min(start + query.limit, len(items))
    cursor = None
    if end < len(items):
        cursor = _encode(
            dict(base, last_id=str(identity(items[end - 1])), last_key=sort_value(items[end - 1])),
            secret,
        )
    return response_model(
        snapshot=snapshot_for(view, _filter_material(query), read_at),
        items=items[start:end],
        total=len(items),
        next_cursor=cursor,
    )


def _product_sort(query: dto.ProductQuery) -> Callable[[dto.Product], str]:
    if query.sort.startswith("price"):
        return lambda product: str(min(Decimal(sku.price) for sku in product.skus))
    return lambda product: product.title.casefold()


def filtered_products(view: EffectiveView, query: dto.ProductQuery) -> tuple[dto.Product, ...]:
    _bound(view, query)
    needle = query.q.casefold()
    items = [
        row
        for row in view.products
        if (
            not needle
            or needle in row.title.casefold()
            or any(needle in sku.label.casefold() for sku in row.skus)
        )
        and (query.tag is None or query.tag in row.tags)
        and (query.origin is None or query.origin == row.source.data_mode)
    ]
    if query.sort.startswith("price"):
        items.sort(
            key=lambda row: (min(Decimal(sku.price) for sku in row.skus), row.product_id),
            reverse=query.sort.endswith("desc"),
        )
    else:
        items.sort(
            key=lambda row: (row.title.casefold(), row.product_id),
            reverse=query.sort.endswith("desc"),
        )
    return tuple(items)


def products_page(
    view: EffectiveView, query: dto.ProductQuery, read_at: datetime, generation: int, secret: bytes
) -> dto.Page[dto.Product]:
    return _page(
        view,
        query,
        filtered_products(view, query),
        read_at,
        generation,
        secret,
        lambda row: row.product_id,
        _product_sort(query),
        response_model=dto.Page[dto.Product],
    )


def filtered_orders(view: EffectiveView, query: dto.OrderQuery) -> tuple[dto.Order, ...]:
    _bound(view, query)
    if query.time_basis == "paid" and query.payment == "unknown":
        raise ValueError("INVALID_REQUEST")
    period = period_for(view, query)
    items = []
    for row in view.orders:
        stamp = row.created_at if query.time_basis == "created" else row.paid_at
        if stamp is None or not period.from_utc <= stamp < period.to_utc:
            continue
        if query.payment is not None and (row.paid_at is None) != (query.payment == "unknown"):
            continue
        if query.fulfillment is not None and query.fulfillment != row.demo_fulfillment:
            continue
        if query.q and query.q.casefold() not in str(row.order_id):
            continue
        items.append(row)
    if query.sort.startswith("amount"):
        items.sort(
            key=lambda row: (Decimal(row.net_amount), row.order_id),
            reverse=query.sort.endswith("desc"),
        )
    else:
        items.sort(
            key=lambda row: (row.created_at, row.order_id), reverse=query.sort.endswith("desc")
        )
    return tuple(items)


def _order_sort(query: dto.OrderQuery) -> Callable[[dto.Order], str]:
    if query.sort.startswith("amount"):
        return lambda row: row.net_amount
    return lambda row: row.created_at.isoformat()


def orders_page(
    view: EffectiveView, query: dto.OrderQuery, read_at: datetime, generation: int, secret: bytes
) -> dto.Page[dto.Order]:
    return _page(
        view,
        query,
        filtered_orders(view, query),
        read_at,
        generation,
        secret,
        lambda row: row.order_id,
        _order_sort(query),
        response_model=dto.Page[dto.Order],
    )


def order_detail(view: EffectiveView, order_id: UUID, read_at: datetime) -> dto.OrderDetail:
    row = next((row for row in view.orders if row.order_id == order_id), None)
    if row is None:
        raise ValueError("RESOURCE_NOT_FOUND")
    return dto.OrderDetail(
        snapshot=snapshot_for(view, dict(order_id=str(order_id)), read_at), order=row
    )


def _safe_csv(value: str) -> str:
    if any(not character.isprintable() for character in value):
        raise ValueError("INVALID_REQUEST")
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def _export(
    view: EffectiveView,
    query: dto.Query,
    read_at: datetime,
    filename: str,
    headers: tuple[str, ...],
    rows: Sequence[tuple[str, ...]],
) -> dto.ExportData:
    if len(rows) > 500:
        raise ValueError("LIMIT_EXCEEDED")
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows(tuple(_safe_csv(value) for value in row) for row in rows)
    output = buffer.getvalue()
    if len(output.encode("utf-8")) > 1048576:
        raise ValueError("LIMIT_EXCEEDED")
    return dto.ExportData(
        snapshot=snapshot_for(view, _filter_material(query), read_at),
        filename="products.csv" if filename == "products" else "orders.csv",
        csv_text=output,
        row_count=len(rows),
    )


def export_products(
    view: EffectiveView, query: dto.ProductQuery, read_at: datetime, generation: int, secret: bytes
) -> dto.ExportData:
    items = filtered_products(view, query)
    _position(
        view, query, items, generation, secret, lambda row: row.product_id, _product_sort(query)
    )
    rows = []
    revision = view.revision()
    for row in items:
        for sku in row.skus:
            rows.append(
                (
                    str(row.product_id),
                    str(sku.sku_id),
                    sku.label,
                    row.title,
                    sku.price,
                    sku.currency,
                    str(sku.available_units) if sku.available_units is not None else "",
                    sku.stock_reason or "KNOWN",
                    ";".join(row.tags),
                    row.source.data_mode,
                    str(row.source.import_job_id) if row.source.import_job_id else "",
                    str(row.source.import_row) if row.source.import_row else "",
                    row.source.file_digest or "",
                    row.source.fixture_digest,
                    revision,
                )
            )
    return _export(
        view,
        query,
        read_at,
        "products",
        (
            "product_id",
            "sku_id",
            "sku",
            "title",
            "price",
            "currency",
            "available_units",
            "stock_status",
            "tags",
            "data_mode",
            "import_job_id",
            "import_row",
            "file_digest",
            "fixture_digest",
            "data_revision",
        ),
        rows,
    )


def export_orders(
    view: EffectiveView, query: dto.OrderQuery, read_at: datetime, generation: int, secret: bytes
) -> dto.ExportData:
    items = filtered_orders(view, query)
    _position(view, query, items, generation, secret, lambda row: row.order_id, _order_sort(query))
    revision = view.revision()
    rows = [
        (
            str(row.order_id),
            row.created_at.isoformat(),
            row.paid_at.isoformat() if row.paid_at else "",
            row.payment_status,
            row.net_amount,
            row.currency,
            row.demo_fulfillment,
            row.source.data_mode,
            row.source.fixture_digest,
            revision,
        )
        for row in items
    ]
    return _export(
        view,
        query,
        read_at,
        "orders",
        (
            "order_id",
            "created_at",
            "paid_at",
            "payment_status",
            "recorded_order_amount",
            "currency",
            "demo_fulfillment",
            "data_mode",
            "fixture_digest",
            "data_revision",
        ),
        rows,
    )


def drilldown(
    view: EffectiveView,
    query: dto.DrilldownQuery,
    read_at: datetime,
    generation: int,
    secret: bytes,
) -> dto.Page[dto.Order | dto.Product | dto.RefundReference]:
    period = period_for(view, query)
    items: tuple[dto.Order | dto.Product | dto.RefundReference, ...]
    if query.metric in ("product_count", "low_stock_count"):
        items = tuple(
            row
            for row in view.products
            if query.metric == "product_count"
            or any(
                sku.available_units is not None and sku.available_units <= LOW_STOCK_UNITS
                for sku in row.skus
            )
        )
    elif query.metric in ("refund_event_count", "refund_event_amount"):
        items = tuple(
            dto.RefundReference(order_id=order.order_id, **row.model_dump())
            for order in view.orders
            for row in order.refunds
            if period.from_utc <= row.occurred_at < period.to_utc
        )
    else:
        items = tuple(
            row
            for row in view.orders
            if (
                period.from_utc <= row.created_at < period.to_utc
                if query.metric == "created_order_count"
                else row.paid_at is not None and period.from_utc <= row.paid_at < period.to_utc
            )
        )

    def identity(row: dto.Order | dto.Product | dto.RefundReference) -> UUID:
        if isinstance(row, dto.Order):
            return row.order_id
        if isinstance(row, dto.Product):
            return row.product_id
        return row.refund_id

    items = tuple(sorted(items, key=identity))
    return _page(
        view,
        query,
        items,
        read_at,
        generation,
        secret,
        identity,
        lambda row: str(identity(row)),
        response_model=dto.Page[dto.Order | dto.Product | dto.RefundReference],
    )


def read_context(
    view: EffectiveView, query: dto.ReadContextQuery, read_at: datetime
) -> dto.ReadContextData:
    _bound(view, query)
    result = dashboard(view, query, read_at)
    if query.kind == "dashboard":
        return dto.ReadContextData(
            snapshot=result.snapshot,
            kind="dashboard",
            resource_ids=(),
            insights=result.insights,
            metrics=result.metrics,
        )
    identity = query.resource_id
    if identity is None:
        raise ValueError("INVALID_REQUEST")
    insights = tuple(
        dto.RuleInsight(
            rule=row.rule,
            reason=row.reason,
            threshold_units=row.threshold_units,
            resource_ids=(identity,),
        )
        for row in result.insights
        if identity in row.resource_ids
    )
    if query.kind == "product":
        detail = product_detail(view, identity, result.snapshot)
        return dto.ReadContextData(
            snapshot=result.snapshot,
            kind="product",
            resource_ids=(identity,),
            insights=insights,
            product=detail.product,
        )
    detail_order = order_detail(view, identity, read_at)
    return dto.ReadContextData(
        snapshot=result.snapshot,
        kind="order",
        resource_ids=(identity,),
        insights=insights,
        order=detail_order.order,
    )
