"""M3 inquiry-only strict messages; no provider, persistence or business entry point."""

import json
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)


Key = Annotated[str, Field(min_length=1, max_length=128)]
Skus = Annotated[tuple[Key, ...], Field(min_length=1, max_length=100)]


class Window(Strict):
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def valid(self) -> Self:
        if self.start.utcoffset() is None or self.end.utcoffset() is None or self.start >= self.end:
            raise ValueError("INVALID_WINDOW")
        return self


class ProductsArgs(Strict):
    query: str = Field(min_length=1, max_length=200)


class OrdersArgs(Strict):
    skus: Skus
    windows: tuple[Window, ...] = Field(min_length=1, max_length=2)


class InventoryArgs(Strict):
    skus: Skus


class ReportsArgs(Strict):
    report_id: Key


class ProductsCall(Strict):
    tool_call_id: Key
    name: Literal["commerce.read_products"]
    args: ProductsArgs


class OrdersCall(Strict):
    tool_call_id: Key
    name: Literal["commerce.read_orders"]
    args: OrdersArgs


class InventoryCall(Strict):
    tool_call_id: Key
    name: Literal["commerce.read_inventory"]
    args: InventoryArgs


class ReportsCall(Strict):
    tool_call_id: Key
    name: Literal["reports.read"]
    args: ReportsArgs


ToolCall = Annotated[
    ProductsCall | OrdersCall | InventoryCall | ReportsCall, Field(discriminator="name")
]


class Calls(Strict):
    kind: Literal["call_tools"]
    intent: Literal["readonly_inquiry"]
    calls: tuple[ToolCall, ...] = Field(min_length=1, max_length=4)


class Claim(Strict):
    kind: Literal["fact", "compare"]
    refs: tuple[Key, ...] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def arity(self) -> Self:
        if len(self.refs) != (1 if self.kind == "fact" else 2):
            raise ValueError("INVALID_CLAIM_ARITY")
        return self


class Final(Strict):
    kind: Literal["final"]
    intent: Literal["readonly_inquiry", "clarify", "unsupported"]
    evidence_refs: tuple[Key, ...] = Field(max_length=100)
    claims: tuple[Claim, ...] = Field(max_length=100)


CHOICE: TypeAdapter[Calls | Final] = TypeAdapter(
    Annotated[Calls | Final, Field(discriminator="kind")]
)


def parse_choice(raw: str) -> Calls | Final:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    if len(raw.encode()) > 65_536:
        raise ValueError("RESPONSE_TOO_LARGE")
    json.loads(raw, object_pairs_hook=unique)
    return CHOICE.validate_json(raw)


class Context(Strict):
    request_id: Key
    principal_id: Key
    organization_id: Key
    shop_id: Key
    identity_id: Key
    auth_version: int = Field(ge=1)
    source_binding: Key
    question: str = Field(min_length=1, max_length=2000)


Metric = Literal[
    "available_stock", "inbound_units", "sold_units", "order_net", "order_average", "refund_cohort"
]


class Fact(Strict):
    evidence_id: Key
    metric: Metric
    sku_key: Key | None = None
    window: Window | None = None
    as_of: datetime | None = None
    quality_flags: tuple[Key, ...] = ()
    value: Annotated[str, Field(max_length=80)] | None
    unit: Key
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")] | None = None

    @model_validator(mode="after")
    def numeric(self) -> Self:
        if self.as_of is not None and self.as_of.utcoffset() is None:
            raise ValueError("INVALID_AS_OF")
        if self.value is not None and not Decimal(self.value).is_finite():
            raise ValueError("INVALID_NUMBER")
        return self


class ProductMatch(Strict):
    sku_key: Key
    label: Annotated[str, Field(min_length=1, max_length=80)] | None = None


class ReadResult(Strict):
    tool_call_id: Key
    shop_id: Key
    source_binding: Key
    snapshot_id: Key
    report_id: Key | None = None
    as_of: datetime
    complete: bool
    scanned_rows: int = Field(ge=0)
    sku_keys: tuple[Key, ...] = Field(max_length=100)
    products: tuple[ProductMatch, ...] = Field(default=(), max_length=100)
    facts: tuple[Fact, ...] = Field(default=(), max_length=100)
    windows: tuple[Window, ...] = Field(default=(), max_length=2)

    @model_validator(mode="after")
    def aware(self) -> Self:
        if self.as_of.utcoffset() is None:
            raise ValueError("INVALID_AS_OF")
        if not {p.sku_key for p in self.products} <= set(self.sku_keys):
            raise ValueError("INVALID_PRODUCT_BINDING")
        if any(f.sku_key is not None and f.sku_key not in self.sku_keys for f in self.facts):
            raise ValueError("INVALID_FACT_SKU")
        if any(f.window is not None and f.window not in self.windows for f in self.facts):
            raise ValueError("INVALID_FACT_WINDOW")
        return self


class ChoicePort(Protocol):
    async def choose(self, context: Context, results: tuple[ReadResult, ...]) -> str: ...


class ReadPort(Protocol):
    async def read(
        self, context: Context, call: ToolCall, deadline: float, rows_remaining: int
    ) -> ReadResult: ...


class IdentityPort(Protocol):
    async def authorize(self, context: Context, call: ToolCall | None) -> bool: ...
