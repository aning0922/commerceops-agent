"""Fixed real GET readbacks; independent comparisons, never a fake HTTP transport."""

import csv
import io
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .kpi_reference import assert_metrics, reference
from .subjects import registry

if TYPE_CHECKING:
    from .http_recipes import Business

PRODUCT_COLUMNS = (
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
)
ORDER_COLUMNS = (
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
)


def same_source(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    if any(actual[k] != expected[k] for k in ("data_revision", "source")):
        raise AssertionError("V41_READ_SOURCE_REVISION_DRIFT")


def identity(row: dict[str, Any]) -> str:
    return str(next(row[k] for k in ("refund_id", "product_id", "order_id") if k in row))


def all_pages(
    business: "Business", name: str, query: dict[str, str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if "cursor" in query or "limit" in query:
        raise ValueError("FIRST_PAGE_FILTER_ONLY_REQUIRED")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    cursors: set[str] = set()
    snapshot: dict[str, Any] | None = None
    total: int | None = None
    params = {**query, "limit": "5"}
    for _ in range(101):  # At most 500 rows, including an empty terminal page.
        page = business.call(name, query=params)["data"]
        if snapshot is None:
            snapshot, total = page["snapshot"], page["total"]
            if type(total) is not int or not 0 <= total <= 500:
                raise AssertionError("V41_BOUNDED_PAGE_TOTAL_REQUIRED")
        else:
            same_source(page["snapshot"], snapshot)
            if page["snapshot"]["snapshot_id"] != snapshot["snapshot_id"] or page["total"] != total:
                raise AssertionError("V41_PAGE_SNAPSHOT_OR_TOTAL_DRIFT")
        for row in page["items"]:
            key = identity(row)
            if key in seen:
                raise AssertionError("V41_PAGE_DUPLICATE_OBJECT")
            seen.add(key)
            rows.append(row)
        assert total is not None
        cursor = page["next_cursor"]
        if cursor is None:
            if len(rows) != total:
                raise AssertionError("V41_PAGE_MISSING_OBJECTS")
            return rows, snapshot
        if not page["items"] or len(rows) >= total or cursor in cursors:
            raise AssertionError("V41_PAGE_CURSOR_LOOP_OR_OVERFLOW")
        cursors.add(cursor)
        params = {**query, "limit": "5", "cursor": cursor}
    raise AssertionError("V41_PAGE_BOUND_EXCEEDED")


def safe_cell(text: str) -> str:
    if any(not c.isprintable() for c in text):
        raise AssertionError("V41_EXPORT_UNSAFE_CONTROL")
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


def assert_export(
    data: dict[str, Any], kind: str, objects: list[dict[str, Any]], snapshot: dict[str, Any]
) -> None:
    same_source(data["snapshot"], snapshot)
    expected: list[list[str]] = []
    revision = snapshot["data_revision"]
    if kind == "products":
        columns: tuple[str, ...] = PRODUCT_COLUMNS
        for p in objects:
            source = p["source"]
            for sku in p["skus"]:
                expected.append(
                    [
                        p["product_id"],
                        sku["sku_id"],
                        sku["label"],
                        p["title"],
                        sku["price"],
                        sku["currency"],
                        str(sku["available_units"]) if sku["available_units"] is not None else "",
                        sku["stock_reason"] or "KNOWN",
                        ";".join(p["tags"]),
                        source["data_mode"],
                        source["import_job_id"] or "",
                        str(source["import_row"]) if source["import_row"] is not None else "",
                        source["file_digest"] or "",
                        source["fixture_digest"],
                        revision,
                    ]
                )
    elif kind == "orders":
        columns = ORDER_COLUMNS
        for o in objects:
            expected.append(
                [
                    o["order_id"],
                    datetime.fromisoformat(o["created_at"]).isoformat(),
                    datetime.fromisoformat(o["paid_at"]).isoformat() if o["paid_at"] else "",
                    o["payment_status"],
                    o["net_amount"],
                    o["currency"],
                    o["demo_fulfillment"],
                    o["source"]["data_mode"],
                    o["source"]["fixture_digest"],
                    revision,
                ]
            )
    else:
        raise ValueError("FIXED_EXPORT_KIND_REQUIRED")
    actual = list(csv.reader(io.StringIO(data["csv_text"], newline=""), strict=True))
    if (
        data["format"] != "csv"
        or data["filename"] != kind + ".csv"
        or data["row_count"] != len(expected)
        or not actual
        or actual[0] != list(columns)
        or actual[1:] != [[safe_cell(cell) for cell in row] for row in expected]
    ):
        raise AssertionError("V41_EXPORT_NOT_COMPLETE_FILTERED_ROWS")


def expected_drill(
    metric: str,
    products: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    start: datetime,
    end: datetime,
) -> set[str]:
    if metric in {"product_count", "low_stock_count"}:
        return {
            p["product_id"]
            for p in products
            if metric == "product_count"
            or any(
                s["available_units"] is not None and s["available_units"] <= 3 for s in p["skus"]
            )
        }
    if metric.startswith("refund_event_"):
        return {
            r["refund_id"]
            for o in orders
            for r in o["refunds"]
            if start <= datetime.fromisoformat(r["occurred_at"]) < end
        }
    stamp = "created_at" if metric == "created_order_count" else "paid_at"
    return {
        o["order_id"]
        for o in orders
        if o[stamp] is not None and start <= datetime.fromisoformat(o[stamp]) < end
    }


def assert_read_context(
    data: dict[str, Any],
    kind: str,
    snapshot: dict[str, Any],
    *,
    resource: dict[str, Any] | None = None,
    metrics: list[dict[str, Any]] | None = None,
) -> None:
    same_source(data["snapshot"], snapshot)
    ids = [] if resource is None else [resource[kind + "_id"]]
    if (
        data["kind"] != kind
        or data["model_mode"] != "not_used"
        or data["resource_ids"] != ids
        or data["product"] != (resource if kind == "product" else None)
        or data["order"] != (resource if kind == "order" else None)
        or data["metrics"] != (metrics or [])
        or any(not set(i["resource_ids"]).issubset(ids) for i in data["insights"])
        and kind != "dashboard"
    ):
        raise AssertionError("V41_READ_CONTEXT_RESOURCE_OR_METRICS_DRIFT")


def readback_shop(business: "Business", *, imported: int = 0, golden: bool = True) -> None:
    from commerceops.application.v4_demo.seed_contract import generate_seed

    seed = generate_seed()
    content = seed.content.model_dump(mode="json")
    end = date.fromisoformat(content["latest_business_day"]) + timedelta(days=1)
    start = end - timedelta(days=14)
    period = {"from_date": start.isoformat(), "to_date": end.isoformat()}
    products, ps = all_pages(business, "products", {"sort": "title_asc"})
    orders, os = all_pages(business, "orders", {**period, "sort": "created_asc"})
    same_source(ps, os)
    for kind, objects, snapshot, query in (
        ("products", products, ps, {"sort": "title_asc"}),
        ("orders", orders, os, {**period, "sort": "created_asc"}),
    ):
        # limit=1 deliberately proves export includes more than the first list page.
        data = business.call(kind + "_export", query={**query, "limit": "1"})["data"]
        assert_export(data, kind, objects, snapshot)
        # A real empty filter must produce a valid header-only export and zero rows.
        empty_query = {**query, "q": "qa-empty-" + business.shop["shop_id"]}
        empty, es = all_pages(business, kind, empty_query)
        if empty:
            raise AssertionError("V41_EMPTY_FILTER_NOT_EMPTY")
        assert_export(business.call(kind + "_export", query=empty_query)["data"], kind, [], es)
    for days in (14, 7, 1):
        query = {"from_date": (end - timedelta(days=days)).isoformat(), "to_date": end.isoformat()}
        dashboard = business.call("dashboard", query=query)["data"]
        same_source(dashboard["snapshot"], ps)
        p = dashboard["period"]
        if p["from_date"] != query["from_date"] or p["to_date"] != query["to_date"]:
            raise AssertionError("V41_EXPLICIT_PERIOD_DRIFT")
        if golden:
            expected = reference(
                content,
                business.shop["currency"],
                date.fromisoformat(p["from_date"]),
                end,
                imported=imported,
            )
            assert_metrics(dashboard, expected)
            if dashboard["snapshot"]["source"]["fixture_digest"] != seed.manifest.content_digest:
                raise AssertionError("V41_KPI_SEED_DIGEST_DRIFT")
        if [r["day"] for r in dashboard["trend"]] != [
            (end - timedelta(days=days) + timedelta(days=n)).isoformat() for n in range(days)
        ]:
            raise AssertionError("V41_TREND_CIVIL_DAYS_DRIFT")
        if golden:
            for point in dashboard["trend"]:
                day = date.fromisoformat(point["day"])
                daily = reference(content, business.shop["currency"], day, day + timedelta(days=1))
                daily = {
                    k: v for k, v in daily.items() if k not in {"product_count", "low_stock_count"}
                }
                if {m["metric"]: m for m in point["metrics"]} != daily or len(
                    point["metrics"]
                ) != 6:
                    raise AssertionError("V41_DAILY_KPI_LEDGER_DRIFT")
        context = business.call("read_context", query={**query, "kind": "dashboard"})["data"]
        assert_read_context(context, "dashboard", ps, metrics=dashboard["metrics"])
        if days == 14:
            for metric in dashboard["metrics"]:
                drill, ds = all_pages(business, "drilldown", {**query, "metric": metric["metric"]})
                same_source(ds, ps)
                wanted = expected_drill(
                    metric["metric"],
                    products,
                    orders,
                    datetime.fromisoformat(p["from_utc"]),
                    datetime.fromisoformat(p["to_utc"]),
                )
                if {identity(r) for r in drill} != wanted:
                    raise AssertionError("V41_DRILLDOWN_MEMBERSHIP_DRIFT")
    for kind, objects in (("product", products), ("order", orders)):
        if not objects:
            raise AssertionError("V41_SYNTHETIC_SOURCE_OBJECT_REQUIRED")
        resource = objects[0]
        detail = business.call(kind, ids={kind + "_id": resource[kind + "_id"]})["data"]
        same_source(detail["snapshot"], ps)
        if detail[kind] != resource:
            raise AssertionError("V41_LIST_DETAIL_DRIFT")
        context = business.call(
            "read_context",
            query={
                **period,
                "kind": kind,
                "resource_id": resource[kind + "_id"],
            },
        )["data"]
        assert_read_context(context, kind, ps, resource=resource)


def readback_both_shops(business: "Business") -> None:
    current = business.visitor.current
    if current is None or {s["currency"] for s in current["data"]["shops"]} != {"TWD", "CNY"}:
        raise AssertionError("V41_TWO_CURRENCY_SHOPS_REQUIRED")
    original = business.shop
    try:
        for shop in current["data"]["shops"]:
            business.shop = shop
            registry(Path(business.case.directory), current["context"], shop["shop_id"])
            readback_shop(business)
    finally:
        business.shop = original
