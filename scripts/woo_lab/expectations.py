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
    shop = spec.get("shop_id", "woo-local")
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
    from scripts.woo_lab.lab import fixture_spec, write_private

    spec = fixture_spec(config, directory)
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
        "shop_id": expected["shop_id"],
        "timezone": spec["timezone"],
        "currency": spec["currency"],
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
    if spec.get("profile") == "positive-v1":
        write_private(
            directory / "analysis-golden.private.json", positive_golden(spec, seed["mapping"])
        )
        write_private(
            directory / "fixture-binding.safe.json",
            {
                k: config[k]
                for k in (
                    "profile",
                    "anchor_day",
                    "shop_id",
                    "shop_identity",
                    "external_shop_key",
                    "template_sha256",
                    "spec_sha256",
                )
            },
        )


def positive_golden(spec: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    """Independent arithmetic oracle, not adapter output or a PG execution receipt."""
    from fractions import Fraction

    if spec.get("profile") != "positive-v1":
        raise ValueError("POSITIVE_PROFILE_REQUIRED")
    declared = spec["analysis_gold"]
    parameters = declared["parameters"]
    normalized = expected_document(spec, mapping)
    products = [p for p in spec["products"] if p["type"] != "variable"]
    if len(products) != 4 or spec["refunds"]:
        raise ValueError("POSITIVE_GOLD_SHAPE")
    gross = {p["key"]: 0 for p in products}
    amount = Decimal(0)
    for order in spec["orders"]:
        if order["status"] not in {"processing", "completed"}:
            raise ValueError("POSITIVE_ORDER_STATUS")
        for line in order["lines"]:
            gross[line["product"]] += line["quantity"]
            amount += Decimal(line["total"])
    facts = []
    for row, product in zip(products, normalized["expected"]["products"], strict=True):
        units, available = gross[row["key"]], row["stock_quantity"]
        if not row["manage_stock"] or type(available) is not int:
            raise ValueError("POSITIVE_STOCK_UNKNOWN")
        daily = Fraction(units, 7)
        exact_target = daily * sum(parameters.values())
        target = -(-exact_target.numerator // exact_target.denominator)
        trigger = daily * (parameters["L"] + parameters["S"])
        quantity = max(0, target - available)
        if quantity != declared["expected_quantities"][row["key"]] or quantity <= 0:
            raise ValueError("POSITIVE_QUANTITY_GOLD")
        facts.append(
            {
                "logical_key": row["key"],
                "sku_key": product["sku_key"],
                "stock_pool_key": product["stock_pool_key"],
                "gross_units": units,
                "net_units": units,
                "known_refunded_units": 0,
                "D": {"numerator": str(daily.numerator), "denominator": str(daily.denominator)},
                "A": available,
                "T": target,
                "trigger": {
                    "numerator": str(trigger.numerator),
                    "denominator": str(trigger.denominator),
                },
                "suggested_units": quantity,
                "risk": "stockout" if available <= 0 else "risk",
                "pool_allocation": "exact",
                "inbound_units": None,
                "effective_inbound_units": 0,
                "inbound_reason": "WOOCOMMERCE_INBOUND_UNAVAILABLE",
                "required_assumptions": ["inbound_unknown_zero:" + product["sku_key"]],
                "hard_blocks": [],
                "suggestion_mode": "assumption_draft",
            }
        )
    if len({row["stock_pool_key"] for row in facts}) != 4:
        raise ValueError("POSITIVE_POOL_GOLD")
    total = sum(row["suggested_units"] for row in facts)
    if (total, sum(gross.values()), money(str(amount))) != (
        declared["total_quantity"],
        declared["gross_units"],
        declared["net_amount"],
    ):
        raise ValueError("POSITIVE_TOTAL_GOLD")
    return {
        "schema_version": "woo-positive-golden-v1",
        "evidence": "independent_expected_only",
        "profile": spec["profile"],
        "anchor_day": spec["anchor_day"],
        "fixture_version": spec["schema_version"],
        "shop_id": normalized["shop_id"],
        "business_now": normalized["business_now"],
        "window": normalized["window"],
        "rule_version": declared["rule_version"],
        "parameters": parameters,
        "facts": facts,
        "candidate_count": 4,
        "assumption_count": 4,
        "complete": True,
        "source_complete": True,
        "requires_review": True,
        "scope_required": False,
        "total_quantity": total,
        "gross_units": sum(gross.values()),
        "net_amount": money(str(amount)),
        "tax_amount": "0",
        "currency": spec["currency"],
        "execution_or_pg_acceptance": "not_proven_by_this_document",
    }
