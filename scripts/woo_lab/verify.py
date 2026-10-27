"""Exact synthetic fixture checks against real Woo REST; not a CommercePort adapter."""

from __future__ import annotations

import ssl
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


def verify_shop(
    client: Any, config: dict[str, Any], directory: Path, seed: dict[str, Any]
) -> dict[str, Any]:
    from scripts.woo_lab.lab import LabFailure, fixture_spec, write_private

    spec = fixture_spec(config, directory)
    mapping = seed["mapping"]
    products = client.pages("/wp-json/wc/v3/products", spec["per_page"])
    expected_products = [p for p in spec["products"] if p["type"] != "variation"]
    if len(products) != len(expected_products):
        raise LabFailure("LAB_PRODUCT_COUNT")
    all_products = {row["id"]: row for row in products}
    for parent in [p for p in spec["products"] if p["type"] == "variable"]:
        variations = client.pages(
            f"/wp-json/wc/v3/products/{mapping['products'][parent['key']]}/variations", 1
        )
        if len(variations) != 2:
            raise LabFailure("LAB_VARIATION_COUNT")
        all_products.update({row["id"]: row for row in variations})
    defined = {row["key"]: row for row in spec["products"]}
    inventory = []
    for row in spec["products"]:
        actual = all_products[mapping["products"][row["key"]]]
        expected_title = row["color"] if row["type"] == "variation" else row["name"]
        if actual["name"] != expected_title:
            raise LabFailure("LAB_PRODUCT_TITLE")
        if actual["sku"] != row["sku"]:
            raise LabFailure("LAB_PRODUCT_SKU")
        if row["manage_stock"] and actual["stock_quantity"] != row["stock_quantity"]:
            raise LabFailure("LAB_INVENTORY_QUANTITY")
        if row["type"] != "variable" and Decimal(actual["regular_price"]) != Decimal(row["price"]):
            raise LabFailure("LAB_PRODUCT_PRICE")
        expected_quantity = (
            defined[row["parent"]]["stock_quantity"]
            if row.get("parent") == "shared_parent"
            else row["stock_quantity"]
        )
        if actual["stock_quantity"] != expected_quantity:
            raise LabFailure("LAB_NATIVE_STOCK_SEMANTICS")
        owner = row["parent"] if row.get("parent") == "shared_parent" else row["key"]
        inventory.append(
            {
                "logical_key": row["key"],
                "id": actual["id"],
                "sku": actual["sku"],
                "manage_stock": actual["manage_stock"],
                "stock_quantity": actual["stock_quantity"],
                "stock_status": actual["stock_status"],
                "inventory_owner": owner,
                "parent_id": mapping["products"].get(row.get("parent"), 0),
            }
        )
    orders = client.pages("/wp-json/wc/v3/orders", spec["per_page"])
    if len(orders) != len(spec["orders"]):
        raise LabFailure("LAB_ORDER_COUNT")
    by_id = {row["id"]: row for row in orders}
    order_checks = []
    for row in spec["orders"]:
        actual = by_id[mapping["orders"][row["key"]]["id"]]
        expected_status = "refunded" if row["key"] == "full_refund" else row["status"]
        if actual["status"] != expected_status or actual["currency"] != "CNY":
            raise LabFailure("LAB_ORDER_STATUS_CURRENCY")
        expected_total = sum(Decimal(line["total"]) for line in row["lines"])
        if Decimal(actual["total"]) != expected_total:
            raise LabFailure("LAB_ORDER_TOTAL")
        utc = (
            datetime.fromisoformat(row["created_at"])
            .astimezone(UTC)
            .replace(tzinfo=None)
            .isoformat()
        )
        if actual["date_created_gmt"] != utc:
            raise LabFailure("LAB_ORDER_TIMEZONE")
        paid = utc if row["status"] in ("processing", "completed") else None
        completed = utc if row["status"] == "completed" else None
        if actual["date_paid_gmt"] != paid or actual["date_completed_gmt"] != completed:
            raise LabFailure("LAB_ORDER_EVENT_TIME")
        for i, line in enumerate(row["lines"]):
            native = actual["line_items"][i]
            product = defined[line["product"]]
            pid = mapping["products"][product.get("parent", product["key"])]
            vid = mapping["products"][product["key"]] if product["type"] == "variation" else 0
            if (native["product_id"], native["variation_id"]) != (pid, vid):
                raise LabFailure("LAB_ORDER_PRODUCT_LINK")
            if Decimal(native["total_tax"]) != 0 or Decimal(native["total"]) != Decimal(
                line["total"]
            ):
                raise LabFailure("LAB_ORDER_LINE_AMOUNT")
        if sum(line["quantity"] for line in actual["line_items"]) != sum(
            line["quantity"] for line in row["lines"]
        ):
            raise LabFailure("LAB_ORDER_QUANTITY")
        order_checks.append(
            {
                "logical_key": row["key"],
                "id": actual["id"],
                "status": actual["status"],
                "date_created_gmt": actual["date_created_gmt"],
                "total": actual["total"],
                "currency": actual["currency"],
                "line_items": actual["line_items"],
            }
        )
    refunds = []
    for row in spec["refunds"]:
        order_id = mapping["orders"][row["order"]]["id"]
        result = client.pages(f"/wp-json/wc/v3/orders/{order_id}/refunds", 1)
        actual = [r for r in result if r["id"] == mapping["refunds"][row["key"]]]
        if (
            len(result) != 1
            or len(actual) != 1
            or Decimal(actual[0]["amount"]) != Decimal(row["amount"])
        ):
            raise LabFailure("LAB_REFUND_AMOUNT")
        lines = actual[0]["line_items"]
        if row["quantity"] is None:
            if lines:
                raise LabFailure("LAB_AMOUNT_REFUND_HAS_QUANTITY")
        elif sum(abs(line["quantity"]) for line in lines) != row["quantity"]:
            raise LabFailure("LAB_REFUND_QUANTITY")
        if row["quantity"] is not None:
            original = str(mapping["orders"][row["order"]]["lines"][0]["id"])
            links = [
                str(m["value"])
                for line in lines
                for m in line["meta_data"]
                if m["key"] == "_refunded_item_id"
            ]
            if links != [original]:
                raise LabFailure("LAB_REFUND_ORIGINAL_LINE")
        refund_utc = (
            datetime.fromisoformat(row["created_at"])
            .astimezone(UTC)
            .replace(tzinfo=None)
            .isoformat()
        )
        if actual[0]["date_created_gmt"] != refund_utc:
            raise LabFailure("LAB_REFUND_TIMEZONE")
        refunds.append(
            {
                "logical_key": row["key"],
                "order_id": order_id,
                "id": actual[0]["id"],
                "amount": actual[0]["amount"],
                "line_items": lines,
                "restock_requested": False,
            }
        )
    if spec.get("profile") == "positive-v1":
        for order in orders:
            if client.pages(f"/wp-json/wc/v3/orders/{order['id']}/refunds", 1):
                raise LabFailure("LAB_POSITIVE_UNEXPECTED_REFUND")
    before_ids = [p["id"] for p in products]
    denied = []
    for method, path, body in [
        ("POST", "/wp-json/wc/v3/products", {"name": "Must not exist", "type": "simple"}),
        ("PUT", f"/wp-json/wc/v3/products/{products[0]['id']}", {"name": "Must not change"}),
        ("DELETE", f"/wp-json/wc/v3/products/{products[0]['id']}", None),
    ]:
        code, result, _ = client.request(path, method, body)
        if code not in (401, 403):
            raise LabFailure("LAB_READONLY_WRITE_NOT_DENIED")
        denied.append({"method": method, "http_status": code, "code": result.get("code")})
    after = client.pages("/wp-json/wc/v3/products", spec["per_page"])
    write_private(directory / "permission-before.private.json", products)
    write_private(directory / "permission-after.private.json", after)
    write_private(directory / "permission-denials.safe.json", denied)

    # Woo's recommendation list is randomized on reads; it is not a stock/order mutation.
    def without_recommendations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{k: v for k, v in row.items() if k != "related_ids"} for row in rows]

    if (
        without_recommendations(after) != without_recommendations(products)
        or [p["id"] for p in after] != before_ids
    ):
        raise LabFailure("LAB_PERMISSION_PROBE_MUTATED")
    try:
        client.read_response("/", context=ssl.create_default_context())
    except LabFailure as error:
        if str(error) != "LAB_TLS_UNTRUSTED":
            raise LabFailure("LAB_TLS_FAILURE_WRONG_REASON") from None
    else:
        raise LabFailure("LAB_TLS_UNTRUSTED_ACCEPTED")
    status, login_page, _ = client.read_response("/wp-login.php", max_bytes=524288)
    if status != 200 or b'id="loginform"' not in login_page:
        raise LabFailure("LAB_LOGIN_PAGE")
    client.remaining()
    result = {
        "login_page_https": True,
        "status": "PASS_REAL_WOO_SYNTHETIC_ONLY",
        "versions": seed["versions"],
        "clock": spec["clock"],
        "timezone": seed["timezone"],
        "currency": seed["currency"],
        "product_count": len(products),
        "variation_count": len(all_products) - len(products),
        "order_count": len(orders),
        "refund_count": len(refunds),
        "inventory": inventory,
        "orders": order_checks,
        "refunds": refunds,
        "readonly_denials": denied,
        "permission_comparison_excludes": ["related_ids"],
        "reader_caps": seed["reader_caps"],
        "trusted_ca_verified": True,
        "untrusted_ca_rejected": True,
        "per_page": spec["per_page"],
        "variation_per_page": 1,
        "consistency": "observational",
        "payments_mail_external_webhooks": "disabled",
        "not_covered": [
            "production",
            "full M2 business wiring",
            "invalid duplicate SKU or illegal status",
            "HTTP fault injection",
        ],
        "observed_at": datetime.now(UTC).isoformat(),
    }
    if spec.get("profile") == "positive-v1":
        result.update(refund_order_cohort_count=len(orders), refund_empty_cohort_verified=True)
    write_private(directory / "actual-manifest.private.json", result)
    return result
