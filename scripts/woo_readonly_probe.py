"""显式新本地 Woo 只读采集/合成预期对账；不接业务服务或数据库。"""

import argparse
import json
import os
import stat
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from commerceops.adapters.commerce.woocommerce import WooCommerce
from commerceops.adapters.commerce.woocommerce_config import WooReadOnlyConfig
from commerceops.adapters.commerce.woocommerce_http import (
    WooReadFailure,
    invalid_constant,
    object_pairs,
)
from commerceops.application.commerce.contracts import (
    DTO,
    CommerceFailure,
    ErrorCode,
    Inventory,
    OrderLine,
    Page,
    Product,
    Provenance,
    Quality,
    Refund,
    Window,
    error,
)
from commerceops.domain.commerce_values import canonical_bytes, identifier, utc_time


def project(value: Any) -> Any:
    if isinstance(value, DTO):
        return project(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {
            k: project(v)
            for k, v in value.items()
            if k not in {"schema_version", "source", "observed_at", "source_version"}
        }
    if isinstance(value, (tuple, list)):
        return [project(v) for v in value]
    return value


def read_json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > 8388608:
        raise ValueError("INPUT_CAPACITY_LIMIT")
    result = json.loads(
        path.read_bytes(), object_pairs_hook=object_pairs, parse_constant=invalid_constant
    )
    if not isinstance(result, dict):
        raise ValueError("INVALID_JSON_OBJECT")
    canonical_bytes(result)  # rejects float/noncanonical values, including expected Money floats
    return result


def drain[T: DTO](read: Callable[[str | None], Page[T]], source: Any, limit: int) -> list[T]:
    rows: list[T] = []
    seen: set[str] = set()
    cursor = None
    for _ in range(limit):
        page = read(cursor)
        if page.error is not None:
            raise CommerceFailure(page.error)
        if page.source != source or page.warnings:
            raise CommerceFailure(error(ErrorCode.INVALID_DATA))
        rows.extend(page.items)
        cursor = page.next_cursor
        if cursor is None:
            if not page.complete:
                raise CommerceFailure(error(ErrorCode.INVALID_DATA))
            return rows
        if cursor in seen:
            raise CommerceFailure(error(ErrorCode.INVALID_CURSOR))
        seen.add(cursor)
    raise CommerceFailure(error(ErrorCode.INVALID_DATA))


def compare_groups(actual: dict[str, list[Any]], expected: dict[str, Any]) -> dict[str, bool]:
    if set(expected) != set(actual):
        raise ValueError("EXPECTED_GROUPS_REQUIRED")
    results = {}
    identities = {
        "products": ("sku_key",),
        "order_lines": ("order_id", "line_id"),
        "refunds": ("refund_id",),
        "inventories": ("sku_key",),
    }
    for name, rows in actual.items():
        wanted = expected[name]
        if type(wanted) is not list or any(type(row) is not dict for row in wanted):
            raise ValueError("EXPECTED_ARRAY_REQUIRED")
        for group in (rows, wanted):
            ids = [tuple(row[field] for field in identities[name]) for row in group]
            if len(set(ids)) != len(ids):
                raise ValueError("DUPLICATE_RECONCILIATION_ID")
        results[name] = sorted(canonical_bytes(r) for r in rows) == sorted(
            canonical_bytes(r) for r in wanted
        )
    return results


def collect(adapter: WooCommerce) -> tuple[dict[str, list[Any]], list[str]]:
    config = adapter.config
    products = drain(lambda c: adapter.list_products(cursor=c), adapter.source, config.max_pages)
    orders = drain(
        lambda c: adapter.list_order_lines(config.window, cursor=c),
        adapter.source,
        config.max_pages,
    )
    cohort = tuple(sorted({r.order_id for r in orders}))
    refunds = drain(
        lambda c: adapter.list_refunds(cohort, cursor=c), adapter.source, config.max_pages
    )
    stocks = []
    flags: set[str] = set()
    for product in products:
        stock = adapter.get_inventory(product.sku_key)
        if stock.error is not None:
            raise CommerceFailure(stock.error)
        if (
            stock.source != adapter.source
            or stock.item is None
            or set(stock.warnings) - {Quality.UNKNOWN_STOCK, Quality.SHARED_POOL_UNRESOLVED}
        ):
            raise CommerceFailure(error(ErrorCode.INVALID_DATA))
        flags.update(stock.warnings)
        stocks.append(stock.item)
    adapter.http.revalidate()
    return {
        "products": project(products),
        "order_lines": project(orders),
        "refunds": project(refunds),
        "inventories": project(stocks),
    }, sorted(flags)


def expected_input(config: WooReadOnlyConfig, expected: dict[str, Any]) -> None:
    if expected["schema_version"] != "woo-local-expectations-v1":
        raise ValueError("INVALID_EXPECTED_SCHEMA")
    identifier(expected["fixture_version"])
    utc_time(expected["business_now"])
    if (
        (expected["shop_id"], expected["timezone"], expected["currency"])
        != (config.shop_id, config.timezone, config.currency)
        or Window.model_validate(expected["window"]) != config.window
        or type(expected["expected"]) is not dict
        or set(expected["expected"]) != {"products", "order_lines", "refunds", "inventories"}
    ):
        raise ValueError("EXPECTED_SOURCE_MISMATCH")

    expected["expected"] = project(expected["expected"])
    provenance = Provenance(
        source_kind="woocommerce_test",
        fixture_version=None,
        captured_at=utc_time(expected["business_now"]),
        raw_hash="0" * 64,
    )
    for name, model, maximum in (
        ("products", Product, 1000),
        ("order_lines", OrderLine, 10000),
        ("refunds", Refund, 10000),
        ("inventories", Inventory, 1000),
    ):
        rows = expected["expected"][name]
        if type(rows) is not list or len(rows) > maximum:
            raise ValueError("EXPECTED_CAPACITY_OR_TYPE")
        for row in rows:
            if type(row) is not dict:
                raise ValueError("EXPECTED_ROW_INVALID")
            extra = (
                {"observed_at": utc_time(expected["business_now"]), "source_version": None}
                if model is Inventory
                else {}
            )
            item = model.model_validate({**row, "source": provenance, **extra})
            if canonical_bytes(project(item)) != canonical_bytes(row):
                raise ValueError("EXPECTED_NOT_CANONICAL_FULL_DTO")
    compare_groups(expected["expected"], expected["expected"])


def write_output(path: Path, value: dict[str, Any], *, redact: Callable[[str], str]) -> None:
    parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(parent_fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("OUTPUT_DIRECTORY_UNSAFE")
        fd = os.open(
            path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent_fd
        )
    finally:
        os.close(parent_fd)
    with os.fdopen(fd, "w") as stream:
        stream.write(redact(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)) + "\n")


def probe(config_path: Path, expected_path: Path, output_path: Path) -> int:
    started = datetime.now(UTC)
    adapter = None
    report: dict[str, Any] = {
        "schema_version": "woo-readonly-probe-v1",
        "started_at": started.isoformat(),
        "source_kind": "woocommerce_test",
        "consistency": "observational",
        "complete": False,
    }
    code = 2
    try:
        config = WooReadOnlyConfig.model_validate_json(config_path.read_bytes())
        expected = read_json(expected_path)
        expected_input(config, expected)
        report.update(
            {
                "shop_id": config.shop_id,
                "timezone": config.timezone,
                "currency": config.currency,
                "window": config.window.model_dump(mode="json"),
                "fixture_version": expected["fixture_version"],
            }
        )
        report["limits"] = config.model_dump(
            include={
                "per_page",
                "max_pages",
                "max_requests",
                "timeout_seconds",
                "max_elapsed_seconds",
                "max_response_bytes",
                "max_retries",
            }
        )
        adapter = WooCommerce(config)
        actual, flags = collect(adapter)
        report.update(
            {
                "actual": actual,
                "quality_flags": flags,
                "matches": compare_groups(actual, expected["expected"]),
                "complete": True,
            }
        )
        code = 0 if all(report["matches"].values()) else 1
        report["status"] = "MATCHED" if code == 0 else "MISMATCH"
    except WooReadFailure as exc:
        code = 1
        report.update(
            {
                "status": "READ_FAILED",
                "error": error(exc.code).model_dump(mode="json"),
                "quality_flags": [exc.quality.value],
            }
        )
    except CommerceFailure as exc:
        code = 1
        report.update({"status": "READ_FAILED", "error": exc.error.model_dump(mode="json")})
    except (ValueError, TypeError, KeyError, OSError, OverflowError, RecursionError):
        report.update({"status": "INPUT_OR_DATA_INVALID", "error_code": "INVALID_DATA"})
    finally:
        if adapter is not None:
            report["request_counts"] = dict(adapter.http.counts)
            report["request_total"] = sum(adapter.http.counts.values())
            report["http_status_counts"] = {
                str(k): v for k, v in adapter.http.status_counts.items()
            }
            report["response_bytes"] = adapter.http.response_bytes
            adapter.close()
        report["ended_at"] = datetime.now(UTC).isoformat()
    try:
        write_output(
            output_path, report, redact=adapter.http.redact if adapter is not None else lambda s: s
        )
    except (OSError, ValueError):
        print("Woo readonly: OUTPUT_UNSAFE_OR_EXISTS")
        return 2
    print("Woo readonly: " + str(report["status"]))
    return code


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--expected", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(probe(args.config, args.expected, args.output))


if __name__ == "__main__":
    main()
