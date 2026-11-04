"""Read recipe verdict components only; scripted pages do not claim live HTTP evidence."""

import copy
import csv
import io
import json
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from .http_recipes import ROUTES, Business
from .process import ROOT
from .read_recipes import (
    PRODUCT_COLUMNS,
    all_pages,
    assert_export,
    assert_read_context,
    expected_drill,
    safe_cell,
)

pytestmark = pytest.mark.offline


def snapshot() -> dict[str, Any]:
    return {
        "data_revision": "a" * 64,
        "snapshot_id": "b" * 64,
        "source": {"data_mode": "demo_fixture"},
        "read_at": "2026-11-04T00:00:00Z",
    }


class Pages:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = iter(rows)
        self.queries: list[dict[str, str]] = []

    def call(self, name: str, *, query: dict[str, str]) -> dict[str, Any]:
        assert name == "products"
        self.queries.append(query)
        return {"data": next(self.rows)}


def test_routes_cover_all_sixteen_actual_contract_paths() -> None:
    contract = json.loads((ROOT / "docs/v4/v4-1/API_CONTRACT.json").read_text())
    assert len(ROUTES) == 16
    assert set(ROUTES.values()) == {(r["method"], r["path"]) for r in contract["routes"]}


def page(items: list[str], total: int, cursor: str | None) -> dict[str, Any]:
    return {
        "snapshot": snapshot(),
        "items": [{"product_id": n} for n in items],
        "total": total,
        "next_cursor": cursor,
    }


def test_complete_pagination_preserves_filters_and_accepts_new_read_time() -> None:
    first, last = page(["a"], 2, "next"), page(["b"], 2, None)
    last["snapshot"]["read_at"] = "2026-11-04T00:00:01Z"
    fixture = Pages([first, last])
    rows, _ = all_pages(cast(Business, fixture), "products", {"q": "synthetic"})
    assert [r["product_id"] for r in rows] == ["a", "b"]
    assert fixture.queries == [
        {"q": "synthetic", "limit": "5"},
        {"q": "synthetic", "limit": "5", "cursor": "next"},
    ]


@pytest.mark.parametrize("fault", ["duplicate", "missing", "revision", "snapshot", "loop", "total"])
def test_partial_duplicate_loop_or_mixed_pages_cannot_pass(fault: str) -> None:
    first, last = page(["a"], 3, "next"), page(["b", "c"], 3, None)
    if fault == "duplicate":
        last["items"][0]["product_id"] = "a"
    elif fault == "missing":
        last["items"].pop()
    elif fault == "revision":
        last["snapshot"]["data_revision"] = "c" * 64
    elif fault == "snapshot":
        last["snapshot"]["snapshot_id"] = "c" * 64
    elif fault == "total":
        last["total"] = 4
    else:
        last["items"].pop()
        last["next_cursor"] = "next"
    with pytest.raises(AssertionError):
        all_pages(cast(Business, Pages([first, last])), "products", {})


def export_fixture() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    product = {
        "product_id": "product",
        "title": " =SUM(1)",
        "tags": ["QA"],
        "source": {
            "data_mode": "demo_fixture",
            "import_job_id": None,
            "import_row": None,
            "file_digest": None,
            "fixture_digest": "c" * 64,
        },
        "skus": [
            {
                "sku_id": "sku",
                "label": "SKU",
                "price": "12.5",
                "currency": "TWD",
                "available_units": None,
                "stock_reason": "UNKNOWN_STOCK",
            }
        ],
    }
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(PRODUCT_COLUMNS)
    writer.writerow(
        [
            "product",
            "sku",
            "SKU",
            "' =SUM(1)",
            "12.5",
            "TWD",
            "",
            "UNKNOWN_STOCK",
            "QA",
            "demo_fixture",
            "",
            "",
            "",
            "c" * 64,
            "a" * 64,
        ]
    )
    return (
        {
            "snapshot": snapshot(),
            "format": "csv",
            "filename": "products.csv",
            "row_count": 1,
            "csv_text": stream.getvalue(),
        },
        [product],
    )


@pytest.mark.parametrize("fault", [None, "truncated", "formula", "money", "count", "revision"])
def test_export_requires_every_filtered_cell_and_formula_neutralization(fault: str | None) -> None:
    data, rows = export_fixture()
    if fault == "truncated":
        data["csv_text"] = ",".join(PRODUCT_COLUMNS) + "\n"
    elif fault == "formula":
        data["csv_text"] = data["csv_text"].replace("' =SUM(1)", " =SUM(1)")
    elif fault == "money":
        data["csv_text"] = data["csv_text"].replace("12.5", "999")
    elif fault == "count":
        data["row_count"] = 2
    elif fault == "revision":
        data["snapshot"]["data_revision"] = "wrong"
    if fault is None:
        assert_export(data, "products", rows, snapshot())
    else:
        with pytest.raises(AssertionError):
            assert_export(data, "products", rows, snapshot())


def test_context_cannot_substitute_another_resource_or_leak_unrelated_insight() -> None:
    resource = {"product_id": "p", "title": "synthetic"}
    data: dict[str, Any] = {
        "snapshot": snapshot(),
        "kind": "product",
        "model_mode": "not_used",
        "resource_ids": ["p"],
        "product": resource,
        "order": None,
        "metrics": [],
        "insights": [{"resource_ids": ["p"]}],
    }
    assert_read_context(data, "product", snapshot(), resource=resource)
    for field, value in (
        ("resource_ids", ["other"]),
        ("model_mode", "model"),
        ("insights", [{"resource_ids": ["other"]}]),
        ("metrics", [{}]),
    ):
        bad = copy.deepcopy(data)
        bad[field] = value
        with pytest.raises(AssertionError):
            assert_read_context(bad, "product", snapshot(), resource=resource)


def test_drill_membership_distinguishes_created_paid_unknown_refund_and_low_stock() -> None:
    start, end = datetime(2026, 11, 1, tzinfo=UTC), datetime(2026, 11, 2, tzinfo=UTC)
    orders: list[dict[str, Any]] = [
        {
            "order_id": "o",
            "created_at": "2026-10-31T23:00:00Z",
            "paid_at": "2026-11-01T01:00:00Z",
            "refunds": [{"refund_id": "r", "occurred_at": "2026-11-01T02:00:00Z"}],
        },
        {"order_id": "u", "created_at": "2026-11-01T23:00:00Z", "paid_at": None, "refunds": []},
    ]
    products = [
        {"product_id": "low", "skus": [{"available_units": 3}]},
        {"product_id": "unknown", "skus": [{"available_units": None}]},
    ]
    assert expected_drill("created_order_count", products, orders, start, end) == {"u"}
    assert expected_drill("paid_order_amount", products, orders, start, end) == {"o"}
    assert expected_drill("refund_event_amount", products, orders, start, end) == {"r"}
    assert expected_drill("low_stock_count", products, orders, start, end) == {"low"}
    assert safe_cell(" @formula") == "' @formula"
    with pytest.raises(AssertionError):
        safe_cell("tab\tvalue")
