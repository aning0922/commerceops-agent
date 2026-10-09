"""进程内确定性 MockCommerce；不访问网络/DB，不重试、不执行补货。"""

import base64
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote

from pydantic import ValidationError

from commerceops.application.commerce.contracts import (
    DTO,
    SCHEMA_VERSION,
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
    Source,
    Window,
    error,
)
from commerceops.domain.commerce_values import (
    CURRENCIES,
    canonical_bytes,
    facts_hash,
    integer,
    sku_key,
    stock_pool_key,
    utc_time,
)

Endpoint = Literal["products", "orders", "refunds", "inventory"]
SUPPORTED_METADATA = {
    "dataset_version": "inventory-v1",
    "fixture_version": "inventory-v1",
    "schema_version": SCHEMA_VERSION,
    "rule_version": "inventory-rule-v1",
    "canonical_version": "canonical-facts-v1",
}


def _sku_in_shop(key: str, shop_id: str) -> bool:
    parts = key.split("/")
    if len(parts) == 4 and parts[0] == "sku" and parts[3] == "p":
        variant = None
    elif len(parts) == 5 and parts[0] == "sku" and parts[3] == "v":
        variant = unquote(parts[4], errors="strict")
    else:
        return False
    return key == sku_key(shop_id, unquote(parts[2], errors="strict"), variant)


def _pool_in_shop(key: str, shop_id: str) -> bool:
    parts = key.split("/")
    return (
        len(parts) == 3
        and parts[0] == "pool"
        and key == stock_pool_key(shop_id, unquote(parts[2], errors="strict"))
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("INVALID_JSON_CONSTANT")


def _decode(raw: bytes) -> Any:
    return json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)


@dataclass(frozen=True)
class Fixture:
    source: Source
    now: datetime
    products: tuple[Product, ...]
    orders: tuple[OrderLine, ...]
    refunds: tuple[Refund, ...]
    inventories: tuple[Inventory, ...]

    @classmethod
    def load(cls, directory: Path, case: str = "baseline") -> "Fixture":
        """校验 manifest 字节哈希；错误只暴露分类，不带源值/本地路径。"""
        try:
            raw = (directory / "datasets.json").read_bytes()
            manifest = _decode((directory / "manifest.json").read_bytes())
            golden_bytes = (directory / "goldens.json").read_bytes()
            for name, payload in (("datasets.json", raw), ("goldens.json", golden_bytes)):
                if manifest["files"][name] != hashlib.sha256(payload).hexdigest():
                    raise ValueError("HASH_MISMATCH")
            root = _decode(raw)
            golden = _decode(golden_bytes)
            for metadata in (root, golden, manifest):
                if any(
                    metadata.get(field) != version for field, version in SUPPORTED_METADATA.items()
                ):
                    raise ValueError("UNSUPPORTED_FIXTURE")
            now = utc_time(root["now"])
            if any(utc_time(metadata["now"]) != now for metadata in (golden, manifest)):
                raise ValueError("CLOCK_MISMATCH")
            if (
                manifest["source_mode"] != "mock"
                or set(manifest["scope"]) != set(root["cases"])
                or set(golden["expectations"]) != set(root["cases"])
            ):
                raise ValueError("METADATA_MISMATCH")
            data = root["cases"][case]
            fixture_version = root["fixture_version"]

            def provenance(record: object) -> Provenance:
                return Provenance(
                    source_kind="mock",
                    fixture_version=fixture_version,
                    captured_at=now,
                    raw_hash=facts_hash(record),
                )

            def records[T: DTO](name: str, kind: type[T]) -> tuple[T, ...]:
                return tuple(
                    kind.model_validate_json(
                        json.dumps({**row, "source": provenance(row).model_dump(mode="json")})
                    )
                    for row in data[name]
                )

            source = Source(
                shop_id=data["shop_id"],
                timezone=data["timezone"],
                currency=data["currency"],
                provenance=provenance(data),
            )
            products = records("products", Product)
            orders = records("orders", OrderLine)
            refunds = records("refunds", Refund)
            inventories = records("inventories", Inventory)
            if any(
                product.shop_id != source.shop_id
                or not _pool_in_shop(product.stock_pool_key, source.shop_id)
                for product in products
            ):
                raise ValueError("SHOP_MISMATCH")
            if any(not _sku_in_shop(row.sku_key, source.shop_id) for row in orders) or any(
                not _sku_in_shop(item.sku_key, source.shop_id) for item in inventories
            ):
                raise ValueError("SHOP_MISMATCH")
            products_by_key = {product.sku_key: product for product in products}
            for item in inventories:
                product = products_by_key.get(item.sku_key)
                if (
                    not _pool_in_shop(item.stock_pool_key, source.shop_id)
                    or product is None
                    or item.stock_pool_key != product.stock_pool_key
                ):
                    raise ValueError("STOCK_POOL_MISMATCH")
            if any(row.currency != source.currency for row in orders) or any(
                row.currency != source.currency for row in refunds
            ):
                raise ValueError("CURRENCY_MISMATCH")
            identities = (
                [row.sku_key for row in products],
                [(row.order_id, row.line_id) for row in orders],
                [row.refund_id for row in refunds],
                [row.sku_key for row in inventories],
            )
            if any(len(ids) != len(set(ids)) for ids in identities):
                raise ValueError("DUPLICATE_FIXTURE_ID")
            return cls(
                source, source.provenance.captured_at, products, orders, refunds, inventories
            )
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            RecursionError,
            ValidationError,
        ):
            raise CommerceFailure(error(ErrorCode.INVALID_DATA)) from None


@dataclass(frozen=True)
class Behavior:
    """单个端点的最小故障脚本；fail_on_call 一次失败，reset 后可复现。"""

    endpoint: Endpoint = "orders"
    fail_on_call: int | None = None
    failure: ErrorCode = ErrorCode.TIMEOUT
    duplicate_second_page: bool = False
    omit_second_page: bool = False
    change_second_page: bool = False
    max_pages: int | None = None

    def __post_init__(self) -> None:
        if self.endpoint not in {"products", "orders", "refunds", "inventory"}:
            raise ValueError("INVALID_ENDPOINT")
        for value in (self.fail_on_call, self.max_pages):
            if value is not None and integer(value) < 1:
                raise ValueError("INVALID_BEHAVIOR")
        if self.failure not in {
            ErrorCode.TIMEOUT,
            ErrorCode.RATE_LIMITED,
            ErrorCode.PROVIDER_UNAVAILABLE,
        }:
            raise ValueError("INVALID_FAILURE")
        for flag in (self.duplicate_second_page, self.omit_second_page, self.change_second_page):
            if type(flag) is not bool:
                raise ValueError("INVALID_BEHAVIOR")


class MockCommerce:
    def __init__(self, fixture: Fixture, *, page_size: int = 50, behavior: Behavior | None = None):
        if not 1 <= integer(page_size) <= 1000:
            raise ValueError("INVALID_PAGE_SIZE")
        self.fixture = fixture
        self.page_size = page_size
        self.behavior = behavior or Behavior()
        self._calls: Counter[Endpoint] = Counter()
        self._binding = facts_hash(
            {
                "source": fixture.source.model_dump(mode="json"),
                "page_size": page_size,
                "behavior": {**self.behavior.__dict__, "failure": self.behavior.failure.value},
            }
        )

    @property
    def call_counts(self) -> dict[Endpoint, int]:
        return dict(self._calls)

    def reset_call_counts(self) -> None:
        self._calls.clear()

    def capabilities(self) -> Capabilities:
        return Capabilities(
            source_kind="mock",
            currencies=tuple(sorted(CURRENCIES)),
            reliable_inbound=bool(self.fixture.inventories)
            and all(item.inbound_quality == "reliable" for item in self.fixture.inventories),
        )

    def _failure(self, endpoint: Endpoint, page: int) -> bool:
        self._calls[endpoint] += 1
        return (
            self.behavior.endpoint == endpoint
            and self.behavior.fail_on_call == self._calls[endpoint]
        )

    def _cursor(self, endpoint: Endpoint, query: str, offset: int) -> str:
        # 核心只传递；内容绑定数据版本、查询、行为与 page_size，无认证语义。
        body = canonical_bytes([self._binding, endpoint, query, offset])
        return base64.urlsafe_b64encode(body).decode("ascii")

    def _offset(self, endpoint: Endpoint, query: str, cursor: str | None) -> int:
        if cursor is None:
            return 0
        try:
            if type(cursor) is not str or len(cursor) > 4096:
                raise ValueError("INVALID_CURSOR")
            decoded = _decode(base64.b64decode(cursor, altchars=b"-_", validate=True))
            offset = decoded[3]
            if (
                type(decoded) is not list
                or len(decoded) != 4
                or decoded[:3] != [self._binding, endpoint, query]
                or type(offset) is not int
                or offset <= 0
                or offset % self.page_size
                or self._cursor(endpoint, query, offset) != cursor
            ):
                raise ValueError("INVALID_CURSOR")
            return offset
        except (ValueError, TypeError, IndexError, KeyError, UnicodeError, RecursionError):
            raise CommerceFailure(error(ErrorCode.INVALID_CURSOR)) from None

    def _page[T: DTO](
        self,
        endpoint: Endpoint,
        rows: tuple[T, ...],
        query: str,
        cursor: str | None,
    ) -> Page[T]:
        offset = self._offset(endpoint, query, cursor)
        if offset >= len(rows) and offset != 0:
            raise CommerceFailure(error(ErrorCode.INVALID_CURSOR))
        page_number = offset // self.page_size + 1
        if self._failure(endpoint, page_number):
            # 返回原游标以显式重试同一页；已成功页由调用方保留。
            return Page[T](
                items=(),
                next_cursor=cursor,
                source=self.fixture.source,
                observed_at=self.fixture.now,
                complete=False,
                warnings=(Quality.PARTIAL_FAILURE,),
                error=error(self.behavior.failure, page=page_number),
            )
        warnings: list[Quality] = []
        if endpoint == "orders":
            product_keys = {product.sku_key for product in self.fixture.products}
            if any(isinstance(row, OrderLine) and row.sku_key not in product_keys for row in rows):
                warnings.append(Quality.DELETED_PRODUCT)
        selected = list(rows[offset : offset + self.page_size])
        active = self.behavior.endpoint == endpoint and len(rows) > self.page_size
        if active:
            if self.behavior.duplicate_second_page:
                warnings.append(Quality.DUPLICATE_ID)
                if page_number == 2:
                    # 原始第二页多返回上一页的最后 ID；对已见 ID 确定性去重。
                    wire = [rows[self.page_size - 1], *selected]
                    seen = {_identity(row) for row in rows[:offset]}
                    selected = [row for row in wire if _identity(row) not in seen]
            if self.behavior.omit_second_page:
                warnings.append(Quality.MISSING_PAGE)
                if page_number == 2:
                    selected = []
            if self.behavior.change_second_page:
                warnings.append(Quality.SOURCE_CHANGED)
                if page_number == 2 and selected:
                    changed = selected[0].model_dump(mode="python")
                    if isinstance(selected[0], OrderLine):
                        changed["quantity"] += 1
                    elif isinstance(selected[0], Product):
                        changed["title"] += " (changed)"
                    elif isinstance(selected[0], Refund):
                        changed["restocked"] = not bool(changed["restocked"])
                    changed["source"] = self.fixture.source.provenance.model_copy(
                        update={
                            "raw_hash": facts_hash(
                                {k: v for k, v in changed.items() if k != "source"}
                            )
                        }
                    )
                    selected[0] = type(selected[0]).model_validate(changed)
        next_offset = offset + self.page_size
        has_more = next_offset < len(rows)
        capped = (
            self.behavior.endpoint == endpoint
            and self.behavior.max_pages is not None
            and page_number >= self.behavior.max_pages
            and has_more
        )
        if capped:
            warnings.append(Quality.CAPACITY_LIMIT)
        return Page[T](
            items=tuple(selected),
            next_cursor=self._cursor(endpoint, query, next_offset)
            if has_more and not capped
            else None,
            source=self.fixture.source,
            observed_at=self.fixture.now,
            complete=not has_more and not warnings,
            warnings=tuple(warnings),
        )

    def list_products(self, *, cursor: str | None = None) -> Page[Product]:
        return self._page("products", self.fixture.products, "all", cursor)

    def list_order_lines(self, window: Window, *, cursor: str | None = None) -> Page[OrderLine]:
        rows = tuple(row for row in self.fixture.orders if window.contains(row.created_at))
        return self._page("orders", rows, facts_hash(window.model_dump(mode="json")), cursor)

    def list_refunds(
        self, order_ids: tuple[str, ...], *, cursor: str | None = None
    ) -> Page[Refund]:
        # 校验 IDs，不允许客户端平台请求参数；cohort 保留窗口外的退款。
        from commerceops.domain.commerce_values import identifier

        if type(order_ids) is not tuple:
            raise CommerceFailure(error(ErrorCode.INVALID_DATA))
        try:
            ids = tuple(sorted({identifier(value) for value in order_ids}))
        except ValueError:
            raise CommerceFailure(error(ErrorCode.INVALID_DATA)) from None
        rows = tuple(row for row in self.fixture.refunds if row.order_id in ids)
        return self._page("refunds", rows, facts_hash(ids), cursor)

    def get_inventory(self, sku_key: str) -> InventoryResult:
        if self._failure("inventory", 1):
            return InventoryResult(
                item=None,
                source=self.fixture.source,
                observed_at=self.fixture.now,
                complete=False,
                warnings=(Quality.PARTIAL_FAILURE,),
                error=error(self.behavior.failure),
            )
        item = next((row for row in self.fixture.inventories if row.sku_key == sku_key), None)
        warnings: list[Quality] = []
        if item is not None:
            if item.available_stock is None:
                warnings.append(Quality.UNKNOWN_STOCK)
            if item.pool_allocation == "unresolved":
                warnings.append(Quality.SHARED_POOL_UNRESOLVED)
        return InventoryResult(
            item=item,
            source=self.fixture.source,
            observed_at=self.fixture.now,
            complete=item is not None and not warnings,
            warnings=tuple(warnings),
            error=error(ErrorCode.RESOURCE_NOT_FOUND) if item is None else None,
        )


def _identity(row: DTO) -> object:
    if isinstance(row, Product):
        return row.sku_key
    if isinstance(row, OrderLine):
        return row.order_id, row.line_id
    if isinstance(row, Refund):
        return row.refund_id
    raise ValueError("INVALID_PAGE_TYPE")
