"""日报专用规范化与有界采集，不改变原库存adapter/transport合同。"""

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import Field

from commerceops.adapters.commerce.woocommerce import gmt, object_rows
from commerceops.adapters.commerce.woocommerce_config import WooFilePins, WooReadOnlyConfig
from commerceops.adapters.commerce.woocommerce_http import WooHTTP, platform_id
from commerceops.application.commerce.contracts import Window
from commerceops.application.daily.aggregation import aggregate_daily, amount, micro_units
from commerceops.application.daily.contracts import (
    DailyCoverage,
    DailyDTO,
    DailyInput,
    DailyOrder,
    DailyOrderLine,
    DailyRefund,
    DailyRefundLine,
    DailyReport,
    QualityCode,
)
from commerceops.application.daily.source import (
    DailyManifest,
    DailyMetadata,
    DailyTaskRequest,
    DailyUnsafe,
    WooMetadata,
)
from commerceops.domain.commerce_values import canonical_bytes, facts_hash, money


class CollectionReceipt(DailyDTO):
    schema_version: Literal["p6-daily-collection-v1"]
    source_binding_id: str
    config_digest: str
    manifest_digest: str
    expected_set_hash: str
    observed_set_hash: str
    snapshot_content_hash: str
    query_profile: Literal["daily-all-orders-trash-refunds-v1", "daily-complete-fixture-v1"]
    all_queries_revalidated: bool
    request_count: int = Field(ge=0, le=256)
    response_bytes: int = Field(ge=0)
    elapsed_ms: int = Field(ge=0, le=18000)
    http_status_counts: tuple[tuple[int, int], ...]


def required_gmt(value: object) -> datetime:
    result = gmt(value)
    if result is None:
        raise ValueError("DAILY_TIME_INVALID")
    return result


def normalize(
    request: DailyTaskRequest,
    metadata: DailyMetadata,
    orders: tuple[dict[str, Any], ...],
    refunds: dict[str, tuple[dict[str, Any], ...]],
    manifest: DailyManifest,
    started: datetime,
    ended: datetime,
) -> DailyInput:
    source = metadata.source(request.daily_source.source_binding_id)
    if (manifest.organization_id, manifest.shop_id, manifest.source_config_version) != (
        metadata.organization_id,
        metadata.shop_id,
        metadata.source_config_version,
    ):
        raise DailyUnsafe("DAILY_SOURCE_BINDING_CHANGED")
    if source != request.daily_source or not (
        manifest.earliest_business_day <= request.business_day <= manifest.latest_business_day
    ):
        raise DailyUnsafe("DAILY_SOURCE_BINDING_CHANGED")
    if len(orders) > metadata.limits.max_orders:
        raise DailyUnsafe("DAILY_SOURCE_INCOMPLETE")
    headers: list[DailyOrder] = []
    lines: list[DailyOrderLine] = []
    refund_rows: list[DailyRefund] = []
    flags: set[QualityCode] = set()
    expected = {entry.order_id: entry for entry in manifest.orders}
    observed_ids = {platform_id(row["id"]) for row in orders}
    if len(observed_ids) != len(orders):
        raise DailyUnsafe("DAILY_SOURCE_INCOMPLETE")
    if observed_ids != set(expected) or set(refunds) != observed_ids:
        flags.add("COVERAGE_UNPROVEN")
    for row in orders:
        identity = platform_id(row["id"])
        line_rows = object_rows(row["line_items"])
        fees = object_rows(row["fee_lines"])
        paid = gmt(row["date_paid_gmt"], optional=True)
        if row["status"] in {"pending", "on-hold", "failed", "trash"} and paid is not None:
            flags.add("PAYMENT_STATUS_CONFLICT")
        header = DailyOrder(
            source=source,
            order_id=identity,
            currency=row["currency"],
            status=row["status"],
            created_at=required_gmt(row["date_created_gmt"]),
            paid_at=paid,
            shipping_net=money(row["shipping_total"]),
            shipping_tax=money(row["shipping_tax"]),
            fee_net=amount(sum(micro_units(money(fee["total"])) for fee in fees)),
            fee_tax=amount(sum(micro_units(money(fee["total_tax"])) for fee in fees)),
            order_total=money(row["total"]),
        )
        headers.append(header)
        line_ids: set[str] = set()
        for line in line_rows:
            line_id = platform_id(line["id"])
            if line_id in line_ids:
                raise DailyUnsafe("DAILY_SOURCE_INCOMPLETE")
            line_ids.add(line_id)
            lines.append(
                DailyOrderLine(
                    source=source,
                    order_id=identity,
                    line_id=line_id,
                    currency=header.currency,
                    quantity=line["quantity"],
                    net_amount=money(line["total"]),
                    tax_amount=money(line["total_tax"]),
                )
            )
        actual_refunds = refunds.get(identity, ())
        refund_ids = {platform_id(refund["id"]) for refund in actual_refunds}
        header_refunds = {platform_id(refund["id"]) for refund in object_rows(row["refunds"])}
        entry = expected.get(identity)
        if (
            entry is None
            or line_ids != set(entry.line_ids)
            or refund_ids != set(entry.refund_ids)
            or header_refunds != refund_ids
            or len(refund_ids) != len(actual_refunds)
        ):
            flags.add("COVERAGE_UNPROVEN")
        for refund in actual_refunds:
            known_lines: list[DailyRefundLine] = []
            unmapped = False
            for rline in object_rows(refund["line_items"]):
                # 正式Woo退款line id不一定是原订单line id。仅明确_refunded_item_id映射可用。
                refs = [
                    m["value"]
                    for m in object_rows(rline["meta_data"])
                    if m.get("key") == "_refunded_item_id"
                ]
                quantity = rline["quantity"]
                if quantity is not None and type(quantity) is not int:
                    raise DailyUnsafe("DAILY_SOURCE_INCOMPLETE")
                if len(refs) != 1 or str(refs[0]) not in line_ids:
                    unmapped = True
                    continue
                known_lines.append(
                    DailyRefundLine(
                        line_id=str(refs[0]),
                        quantity=abs(quantity) if quantity is not None else None,
                        quantity_reason="SOURCE_QUANTITY_UNAVAILABLE" if quantity is None else None,
                    )
                )
            refund_rows.append(
                DailyRefund(
                    source=source,
                    order_id=identity,
                    refund_id=platform_id(refund["id"]),
                    currency=header.currency,
                    occurred_at=required_gmt(refund["date_created_gmt"]),
                    amount=money(refund["amount"]).copy_abs(),
                    lines=() if unmapped else tuple(known_lines),
                    quantity_reason="LINE_MAPPING_UNVERIFIED"
                    if unmapped
                    else ("AMOUNT_ONLY" if not known_lines else None),
                    restocked=None,
                )
            )
    if len(lines) > metadata.limits.max_lines or len(refund_rows) > metadata.limits.max_refunds:
        raise DailyUnsafe("DAILY_SOURCE_INCOMPLETE")
    return DailyInput(
        snapshot_id=request.snapshot_id,
        source=source,
        business_day=request.business_day,
        as_of=ended,
        coverage=DailyCoverage(
            strategy="full_store" if isinstance(metadata, WooMetadata) else "complete_fixture",
            orders_complete=not flags,
            order_lines_complete=not flags,
            refunds_complete=not flags,
            discovered_order_count=len(headers),
            discovered_line_count=len(lines),
            discovered_refund_count=len(refund_rows),
            quality_flags=tuple(sorted(flags)),
            collection_started_at=started,
            collected_at=ended,
        ),
        orders=tuple(headers),
        order_lines=tuple(lines),
        refunds=tuple(refund_rows),
        rules=request.rules,
    )


def collect(
    request: DailyTaskRequest,
    metadata: DailyMetadata,
    manifest: DailyManifest,
    *,
    absolute_deadline: float,
    pins: WooFilePins | None = None,
    transport: Any = None,
    fixture: tuple[list[dict[str, Any]], dict[str, Any]] | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> tuple[DailyInput, DailyReport, CollectionReceipt]:
    start = clock()
    tick = time.monotonic()
    deadline = min(absolute_deadline, tick + metadata.limits.max_elapsed_seconds)
    http: WooHTTP | None = None
    try:
        if tick >= deadline:
            raise DailyUnsafe("DAILY_SOURCE_UNAVAILABLE")
        if isinstance(metadata, WooMetadata):
            if pins is None:
                raise DailyUnsafe("DAILY_SOURCE_UNAVAILABLE")
            config = WooReadOnlyConfig(
                base_url=metadata.origin,
                consumer_key_file=metadata.consumer_key_file,
                consumer_secret_file=metadata.consumer_secret_file,
                ca_file=metadata.ca_file,
                shop_id=metadata.external_shop_key,
                currency=metadata.currency,
                timezone=metadata.timezone,
                window=request_window(request),
                **metadata.limits.model_dump(
                    include={
                        "per_page",
                        "max_pages",
                        "max_requests",
                        "timeout_seconds",
                        "max_elapsed_seconds",
                        "max_response_bytes",
                        "max_retries",
                    }
                ),
            )
            http = WooHTTP(config, pins=pins, transport=transport, absolute_deadline=deadline)
            all_orders = http.scan("orders", {"status": "any", "dp": 6})
            trash = http.scan("orders", {"status": "trash", "dp": 6})
            merged = {platform_id(row["id"]): row for row in all_orders}
            for row in trash:
                key = platform_id(row["id"])
                if key in merged and canonical_bytes(merged[key]) != canonical_bytes(row):
                    raise DailyUnsafe("DAILY_SOURCE_INCOMPLETE")
                merged[key] = row
            if len(merged) > metadata.limits.max_orders:
                raise DailyUnsafe("DAILY_SOURCE_INCOMPLETE")
            orders = tuple(merged[key] for key in sorted(merged))
            refunds = {key: http.scan(f"orders/{key}/refunds", {"dp": 6}) for key in sorted(merged)}
            http.revalidate()
            http.remaining()
        else:
            if fixture is None:
                raise DailyUnsafe("DAILY_SOURCE_UNAVAILABLE")
            orders = tuple(fixture[0])
            refunds = {key: tuple(object_rows(rows)) for key, rows in fixture[1].items()}
        ended = clock()
        snapshot = normalize(request, metadata, orders, refunds, manifest, start, ended)
        report = aggregate_daily(snapshot)
        expected = {
            o.order_id: {"line_ids": sorted(o.line_ids), "refund_ids": sorted(o.refund_ids)}
            for o in manifest.orders
        }
        observed = {
            o.order_id: {
                "line_ids": sorted(
                    line.line_id for line in snapshot.order_lines if line.order_id == o.order_id
                ),
                "refund_ids": sorted(
                    r.refund_id for r in snapshot.refunds if r.order_id == o.order_id
                ),
            }
            for o in snapshot.orders
        }
        receipt = CollectionReceipt(
            schema_version="p6-daily-collection-v1",
            source_binding_id=str(request.daily_source.source_binding_id),
            config_digest=metadata.config_digest,
            manifest_digest=metadata.manifest_digest,
            expected_set_hash=facts_hash(expected),
            observed_set_hash=facts_hash(observed),
            snapshot_content_hash=snapshot.content_hash,
            query_profile="daily-all-orders-trash-refunds-v1"
            if http
            else "daily-complete-fixture-v1",
            all_queries_revalidated=True,
            request_count=sum(http.counts.values()) if http else 0,
            response_bytes=http.response_bytes if http else 0,
            elapsed_ms=int((time.monotonic() - tick) * 1000),
            http_status_counts=tuple(sorted(http.status_counts.items())) if http else (),
        )
        if (
            len(canonical_bytes(snapshot.canonical_content()))
            + len(receipt.model_dump_json().encode())
            > metadata.limits.max_snapshot_bytes
        ):
            raise DailyUnsafe("DAILY_SOURCE_INCOMPLETE")
        if time.monotonic() >= deadline:
            raise DailyUnsafe("DAILY_SOURCE_UNAVAILABLE")
        return snapshot, report, receipt
    except DailyUnsafe:
        raise
    except (KeyError, TypeError, ValueError, OverflowError):
        raise DailyUnsafe("DAILY_SOURCE_UNAVAILABLE") from None
    finally:
        if http is not None:
            http.close()


def request_window(request: DailyTaskRequest) -> Window:
    from commerceops.application.daily.contracts import day_window

    return day_window(request.business_day, request.daily_source.timezone)
