"""commerce-v1 标准 DTO；平台对象必须在 adapter 边界转换。"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer, model_validator

from commerceops.domain import commerce_values as values

SCHEMA_VERSION: Literal["commerce-v1"] = "commerce-v1"
Identifier = Annotated[str, BeforeValidator(values.identifier)]
Units = Annotated[int, BeforeValidator(values.integer)]
PositiveUnits = Annotated[Units, Field(gt=0)]
NonnegativeUnits = Annotated[Units, Field(ge=0)]
Timestamp = Annotated[datetime, BeforeValidator(values.utc_time)]
Money = Annotated[
    Decimal,
    BeforeValidator(values.money),
    PlainSerializer(values.decimal_text, return_type=str, when_used="json"),
]
Currency = Annotated[str, BeforeValidator(values.currency)]
Timezone = Annotated[str, BeforeValidator(values.shop_timezone)]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class DTO(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    schema_version: Literal["commerce-v1"] = SCHEMA_VERSION


class Quality(StrEnum):
    DUPLICATE_ID = "DUPLICATE_ID"
    MISSING_PAGE = "MISSING_PAGE"
    SOURCE_CHANGED = "SOURCE_CHANGED"
    CAPACITY_LIMIT = "CAPACITY_LIMIT"
    PARTIAL_FAILURE = "PARTIAL_FAILURE"
    UNKNOWN_STOCK = "UNKNOWN_STOCK"
    SHARED_POOL_UNRESOLVED = "SHARED_POOL_UNRESOLVED"
    DELETED_PRODUCT = "DELETED_PRODUCT"


class Provenance(DTO):
    source_kind: Literal["mock", "woocommerce_test"]
    fixture_version: Identifier | None
    captured_at: Timestamp
    raw_hash: Digest
    quality_flags: tuple[Quality, ...] = ()

    @model_validator(mode="after")
    def mock_version(self) -> Self:
        if self.source_kind == "mock" and self.fixture_version is None:
            raise ValueError("MISSING_FIXTURE_VERSION")
        return self


class Source(DTO):
    shop_id: Identifier
    timezone: Timezone
    currency: Currency
    provenance: Provenance


class Window(DTO):
    start: Timestamp
    end: Timestamp

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.start >= self.end:
            raise ValueError("INVALID_WINDOW")
        return self

    def contains(self, instant: datetime) -> bool:
        return self.start <= values.utc_time(instant) < self.end


class Product(DTO):
    source: Provenance
    shop_id: Identifier
    product_id: Identifier
    variant_id: Identifier | None
    sku_key: Identifier
    sku_label: str | None
    title: str
    active: bool
    stock_pool_key: Identifier

    @model_validator(mode="after")
    def identity(self) -> Self:
        if self.sku_key != values.sku_key(self.shop_id, self.product_id, self.variant_id):
            raise ValueError("SKU_IDENTITY_MISMATCH")
        return self


class OrderLine(DTO):
    source: Provenance
    order_id: Identifier
    line_id: Identifier
    sku_key: Identifier
    status: Identifier
    created_at: Timestamp
    paid_at: Timestamp | None
    completed_at: Timestamp | None
    quantity: PositiveUnits
    net_amount: Money
    tax_amount: Money
    currency: Currency


class RefundLine(DTO):
    line_id: Identifier
    refunded_quantity: NonnegativeUnits | None
    quantity_reason: Identifier | None

    @model_validator(mode="after")
    def unknown(self) -> Self:
        if self.refunded_quantity is None and self.quantity_reason is None:
            raise ValueError("UNKNOWN_QUANTITY_REASON_REQUIRED")
        if self.refunded_quantity is not None and self.quantity_reason is not None:
            raise ValueError("KNOWN_QUANTITY_WITH_UNKNOWN_REASON")
        return self


class Refund(DTO):
    source: Provenance
    refund_id: Identifier
    order_id: Identifier
    created_at: Timestamp
    refund_amount: Annotated[Money, Field(ge=0)]
    currency: Currency
    lines: tuple[RefundLine, ...]
    restocked: bool | None
    # 纯金额无行退款明确表示未知数量，而非隐含 0 件。
    quantity_reason: Identifier | None = None

    @model_validator(mode="after")
    def no_lines(self) -> Self:
        if not self.lines and self.quantity_reason is None:
            raise ValueError("UNKNOWN_QUANTITY_REASON_REQUIRED")
        if len({line.line_id for line in self.lines}) != len(self.lines):
            raise ValueError("DUPLICATE_REFUND_LINE")
        return self


class Inventory(DTO):
    source: Provenance
    sku_key: Identifier
    stock_pool_key: Identifier
    manage_stock: bool
    available_stock: Units | None
    stock_reason: Identifier | None
    stock_status: Identifier
    backorders: Literal["no", "notify", "yes"]
    stock_semantics: Literal["adapter_available_already_adjusted"]
    observed_at: Timestamp
    source_version: Identifier | None
    inbound_units: NonnegativeUnits | None
    inbound_reason: Identifier | None
    inbound_quality: Literal["reliable", "unknown"]
    pool_allocation: Literal["exact", "unresolved"]

    @model_validator(mode="after")
    def unknowns(self) -> Self:
        if (self.inbound_units is None) != (self.inbound_quality == "unknown"):
            raise ValueError("INBOUND_QUALITY_MISMATCH")
        for count, reason in (
            (self.available_stock, self.stock_reason),
            (self.inbound_units, self.inbound_reason),
        ):
            if (count is None) != (reason is not None):
                raise ValueError("UNKNOWN_REASON_MISMATCH")
        return self


class ErrorCode(StrEnum):
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    INVALID_DATA = "INVALID_DATA"
    INVALID_CURSOR = "INVALID_CURSOR"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"


SAFE_MESSAGES = {
    ErrorCode.TIMEOUT: "读取超时",
    ErrorCode.RATE_LIMITED: "来源限流",
    ErrorCode.PROVIDER_UNAVAILABLE: "来源暂时不可用",
    ErrorCode.INVALID_DATA: "来源数据不符合合同",
    ErrorCode.INVALID_CURSOR: "分页游标无效",
    ErrorCode.RESOURCE_NOT_FOUND: "来源资源不存在",
}


class CommerceError(DTO):
    code: ErrorCode
    safe_message: str
    retryable: bool
    provider_code: Literal["429", "500"] | None = None
    request_id: Identifier | None = None
    partial_page: NonnegativeUnits | None = None
    retry_after_seconds: NonnegativeUnits | None = None

    @model_validator(mode="after")
    def safe(self) -> Self:
        if self.safe_message != SAFE_MESSAGES[self.code]:
            raise ValueError("UNSAFE_MESSAGE")
        retryable = self.code in {
            ErrorCode.TIMEOUT,
            ErrorCode.RATE_LIMITED,
            ErrorCode.PROVIDER_UNAVAILABLE,
        }
        if self.retryable != retryable:
            raise ValueError("RETRYABILITY_MISMATCH")
        return self


class CommerceFailure(ValueError):
    def __init__(self, error: CommerceError):
        self.error = error
        super().__init__(error.code.value)


def error(code: ErrorCode, *, page: int | None = None) -> CommerceError:
    return CommerceError(
        code=code,
        safe_message=SAFE_MESSAGES[code],
        retryable=code
        in {ErrorCode.TIMEOUT, ErrorCode.RATE_LIMITED, ErrorCode.PROVIDER_UNAVAILABLE},
        provider_code=(
            "429"
            if code == ErrorCode.RATE_LIMITED
            else "500"
            if code == ErrorCode.PROVIDER_UNAVAILABLE
            else None
        ),
        partial_page=page,
        retry_after_seconds=2 if code == ErrorCode.RATE_LIMITED else None,
    )


class Page[T: DTO](DTO):
    items: tuple[T, ...]
    next_cursor: str | None
    source: Source
    observed_at: Timestamp
    complete: bool
    warnings: tuple[Quality, ...] = ()
    error: CommerceError | None = None

    @model_validator(mode="after")
    def completeness(self) -> Self:
        if self.complete and (
            self.next_cursor is not None or self.warnings or self.error is not None
        ):
            raise ValueError("FALSE_COMPLETENESS")
        return self


class InventoryResult(DTO):
    item: Inventory | None
    source: Source
    observed_at: Timestamp
    complete: bool
    warnings: tuple[Quality, ...] = ()
    error: CommerceError | None = None

    @model_validator(mode="after")
    def completeness(self) -> Self:
        if self.complete and (self.item is None or self.error is not None or self.warnings):
            raise ValueError("FALSE_COMPLETENESS")
        return self


class Capabilities(DTO):
    source_kind: Literal["mock", "woocommerce_test"]
    read_only: Literal[True] = True
    consistency: Literal["observational"] = "observational"
    pagination: Literal["opaque_cursor"] = "opaque_cursor"
    refund_scope: Literal["order_cohort"] = "order_cohort"
    currencies: tuple[str, ...]
    reliable_inbound: bool = False
    stock_semantics: Literal["adapter_available_already_adjusted"] = (
        "adapter_available_already_adjusted"
    )
