"""Independent 842/ba3e contract oracle from synthetic inputs plus platform-created IDs.

No adapter imports and no use of adapter OUTPUT. Woo 11.2.1 variation REST `name`
is wc_get_formatted_variation(flat=true, include_names=false): our single color.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import quote


def utc(value: str) -> str:
    return datetime.fromisoformat(value).astimezone(UTC).isoformat().replace("+00:00", "Z")


def money(value: str) -> str:
    number = Decimal(value)
    if not number.is_finite():
        raise ValueError("NONFINITE_FIXTURE_MONEY")
    text = format(number, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def expected_document(spec: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    shop = "woo-local"
    by_key = {p["key"]: p for p in spec["products"]}
    ids = mapping["products"]

    def identity(row: dict[str, Any]) -> tuple[str, str | None, str]:
        if row["type"] == "variation":
            pid, vid = str(ids[row["parent"]]), str(ids[row["key"]])
            key = f"sku/{quote(shop, safe='')}/{pid}/v/{vid}"
        else:
            pid, vid = str(ids[row["key"]]), None
            key = f"sku/{quote(shop, safe='')}/{pid}/p"
        return pid, vid, key

    products, stocks, lines, refunds = [], [], [], []
    for row in spec["products"]:
        if row["type"] == "variable":
            continue
        pid, vid, key = identity(row)
        shared = row.get("parent") == "shared_parent"
        stock = by_key[row["parent"]] if shared else row
        pool = f"pool/{quote(shop, safe='')}/{ids[stock['key']]}"
        products.append(
            {
                "shop_id": shop,
                "product_id": pid,
                "variant_id": vid,
                "sku_key": key,
                "sku_label": row["sku"] or None,
                "title": row["color"] if vid is not None else row["name"],
                "active": True,
                "stock_pool_key": pool,
            }
        )
        available = stock["stock_quantity"] if stock["manage_stock"] else None
        reason = (
            None
            if available is not None
            else ("STOCK_QUANTITY_UNKNOWN" if stock["manage_stock"] else "STOCK_NOT_MANAGED")
        )
        stocks.append(
            {
                "sku_key": key,
                "stock_pool_key": pool,
                "manage_stock": stock["manage_stock"],
                "available_stock": available,
                "stock_reason": reason,
                "stock_status": stock["stock_status"],
                "backorders": stock.get("backorders", "no"),
                "stock_semantics": "adapter_available_already_adjusted",
                "inbound_units": None,
                "inbound_reason": "WOOCOMMERCE_INBOUND_UNAVAILABLE",
                "inbound_quality": "unknown",
                "pool_allocation": "unresolved" if shared else "exact",
            }
        )
    start, end = (datetime.fromisoformat(spec[k]) for k in ("window_start", "window_end"))
    cohort = set()
    for order in spec["orders"]:
        if not start <= datetime.fromisoformat(order["created_at"]) < end:
            continue
        cohort.add(order["key"])
        bound = mapping["orders"][order["key"]]
        if len(bound["lines"]) != len(order["lines"]):
            raise ValueError("FIXTURE_ORDER_LINE_BINDING")
        for index, line in enumerate(order["lines"]):
            _, _, key = identity(by_key[line["product"]])
            stamp = utc(order["created_at"])
            lines.append(
                {
                    "order_id": str(bound["id"]),
                    "line_id": str(bound["lines"][index]["id"]),
                    "sku_key": key,
                    "status": "refunded" if order["key"] == "full_refund" else order["status"],
                    "created_at": stamp,
                    "paid_at": stamp if order["status"] in ("processing", "completed") else None,
                    "completed_at": stamp if order["status"] == "completed" else None,
                    "quantity": line["quantity"],
                    "net_amount": money(line["total"]),
                    "tax_amount": "0",
                    "currency": "CNY",
                }
            )
    for refund in spec["refunds"]:
        if refund["order"] not in cohort:
            continue
        order = mapping["orders"][refund["order"]]
        quantity = refund["quantity"]
        linked = (
            []
            if quantity is None
            else [
                {
                    "line_id": str(order["lines"][0]["id"]),
                    "refunded_quantity": quantity,
                    "quantity_reason": None,
                }
            ]
        )
        refunds.append(
            {
                "refund_id": str(mapping["refunds"][refund["key"]]),
                "order_id": str(order["id"]),
                "created_at": utc(refund["created_at"]),
                "refund_amount": money(refund["amount"]),
                "currency": "CNY",
                "lines": linked,
                "restocked": None,
                "quantity_reason": "AMOUNT_ONLY_REFUND" if quantity is None else None,
            }
        )
    return {
        "schema_version": "woo-local-expectations-v1",
        "fixture_version": spec["schema_version"],
        "shop_id": shop,
        "timezone": spec["timezone"],
        "currency": spec["currency"],
        "business_now": utc(spec["clock"]),
        "window": {"start": utc(spec["window_start"]), "end": utc(spec["window_end"])},
        "expected": {
            "products": products,
            "order_lines": lines,
            "refunds": refunds,
            "inventories": stocks,
        },
    }


def write_handoff(config: dict[str, Any], directory: Path, seed: dict[str, Any]) -> None:
    from scripts.woo_lab.lab import FIXTURE, write_private

    spec = json.loads(FIXTURE.read_text())
    expected = expected_document(spec, seed["mapping"])
    auth = json.loads((directory / "runtime-auth.json").read_text())
    write_private(directory / "consumer_key", (auth["consumer_key"] + "\n").encode())
    write_private(directory / "consumer_secret", (auth["consumer_secret"] + "\n").encode())
    write_private(directory / "expected.private.json", expected)
    probe_config = {
        "base_url": config["url"],
        "consumer_key_file": str(directory / "consumer_key"),
        "consumer_secret_file": str(directory / "consumer_secret"),
        "ca_file": str(directory / "ca.crt"),
        "shop_id": "woo-local",
        "timezone": "Asia/Shanghai",
        "currency": "CNY",
        "window": expected["window"],
        "per_page": 2,
        "max_pages": 32,
        "max_requests": 256,
        "timeout_seconds": 10,
        "max_elapsed_seconds": 180,
        "max_response_bytes": 2097152,
        "max_retries": 0,
    }
    write_private(directory / "probe-config.private.json", probe_config)
