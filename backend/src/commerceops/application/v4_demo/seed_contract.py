"""Versioned, purely synthetic V4 seed. No filesystem, database, clock or external calls."""

import hashlib
import random
from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, localcontext
from types import MappingProxyType
from typing import Annotated, ClassVar, Literal, Self
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator, model_validator

from commerceops.application.v4_demo.contracts import (
    Contract,
    Currency,
    Digest,
    ShopKey,
    SummaryCounts,
    Timestamp,
)
from commerceops.domain.commerce_values import canonical_bytes, facts_hash

GENERATOR_VERSION = "v4-seed-generator-1"
RANDOM_SEED = 4000001
ANCHOR_DAY = date(2026, 11, 1)
SNAPSHOT_AT = datetime(2026, 11, 2, tzinfo=UTC)
TEMPLATE_NAMESPACE = UUID("e6c28525-1dca-510b-9093-a52c23b93598")
MoneyText = Annotated[str, Field(pattern=r"^(0|[1-9][0-9]{0,13})(\.[0-9]{0,5}[1-9])?$")]
Units = Annotated[int, Field(ge=0)]
EntityKind = Literal[
    "product",
    "sku",
    "inventory",
    "order",
    "order_line",
    "refund",
    "customer",
    "supplier",
    "quote",
    "knowledge",
    "purchase_ref",
    "support_ref",
    "campaign_ref",
]
ScenarioId = Literal[
    "stockout",
    "high_refund",
    "slow_moving",
    "purchase_pending",
    "support_escalation",
    "marketing_draft",
]
KNOWLEDGE_BODIES = (
    "合成演示退货说明：先核对演示订单与商品，再记录退货原因；不发送真实消息。",
    "合成演示保管说明：商品置于干燥处；本文不包含功效、销量或真实客户事实。",
)
SHOP_PARAMETERS: Mapping[ShopKey, tuple[str, str, Currency]] = MappingProxyType(
    {
        "v4-shop-a": ("台北合成演示店", "Asia/Taipei", "TWD"),
        "v4-shop-b": ("上海合成演示店", "Asia/Shanghai", "CNY"),
    }
)


class TemplateRef(Contract):
    shop_key: ShopKey
    kind: EntityKind
    key: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*-[0-9]{2}$")]
    id: UUID
    version: Literal[1] = 1

    @field_validator("version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("INVALID_TEMPLATE_VERSION")
        return value

    @model_validator(mode="after")
    def identity(self) -> Self:
        if not self.key.startswith(self.kind + "-") or self.id != uuid5(
            TEMPLATE_NAMESPACE, f"{self.shop_key}/{self.kind}/{self.key}"
        ):
            raise ValueError("INVALID_TEMPLATE_ID")
        return self


def template_ref(shop: ShopKey, kind: EntityKind, index: int) -> TemplateRef:
    if type(index) is not int or not 0 <= index <= 99:
        raise ValueError("INVALID_TEMPLATE_INDEX")
    key = f"{kind}-{index:02}"
    return TemplateRef(
        shop_key=shop,
        kind=kind,
        key=key,
        id=uuid5(TEMPLATE_NAMESPACE, f"{shop}/{kind}/{key}"),
    )


class Entity(Contract):
    expected_kind: ClassVar[EntityKind]
    ref: TemplateRef

    @model_validator(mode="after")
    def kind(self) -> Self:
        if self.ref.kind != self.expected_kind:
            raise ValueError("INVALID_ENTITY_KIND")
        return self


class Product(Entity):
    expected_kind = "product"
    title: Annotated[str, Field(pattern=r"^合成商品[0-9]{2}$")]
    source_kind: Literal["synthetic"] = "synthetic"


class SKU(Entity):
    expected_kind = "sku"
    label: Annotated[str, Field(pattern=r"^SKU-[0-9]{2}$")]
    product_ref: TemplateRef
    variant_ref: UUID | None
    stock_pool_ref: UUID
    price: MoneyText
    currency: Currency
    cost_amount: None = None
    cost_reason: Literal["UNKNOWN_COST"] = "UNKNOWN_COST"


class Inventory(Entity):
    expected_kind = "inventory"
    sku_ref: TemplateRef
    stock_pool_ref: UUID
    available_units: Units | None
    stock_reason: Literal["UNKNOWN_STOCK"] | None
    inbound_units: None = None
    inbound_reason: Literal["UNKNOWN_INBOUND"] = "UNKNOWN_INBOUND"

    @model_validator(mode="after")
    def unknown_stock(self) -> Self:
        if (self.available_units is None) != (self.stock_reason is not None):
            raise ValueError("INVALID_STOCK_KNOWLEDGE")
        return self


class Order(Entity):
    expected_kind = "order"
    customer_ref: TemplateRef
    created_at: Timestamp
    paid_at: Timestamp | None
    currency: Currency
    net_amount: MoneyText
    status_hint: Literal["payment_recorded", "payment_timestamp_unknown"]

    @model_validator(mode="after")
    def payment(self) -> Self:
        if (self.paid_at is None) != (self.status_hint == "payment_timestamp_unknown"):
            raise ValueError("INVALID_PAYMENT_KNOWLEDGE")
        if self.paid_at is not None and self.paid_at < self.created_at:
            raise ValueError("PAYMENT_BEFORE_CREATION")
        return self


class OrderLine(Entity):
    expected_kind = "order_line"
    order_ref: TemplateRef
    sku_ref: TemplateRef
    quantity: Annotated[int, Field(gt=0)]
    net_amount: MoneyText
    currency: Currency


class Refund(Entity):
    expected_kind = "refund"
    order_ref: TemplateRef
    occurred_at: Timestamp
    amount: MoneyText
    currency: Currency
    quantity: None = None
    restocked: None = None
    quantity_reason: Literal["UNKNOWN_REFUND_QUANTITY"] = "UNKNOWN_REFUND_QUANTITY"
    payment_gateway_status: Literal["UNKNOWN"] = "UNKNOWN"


class Customer(Entity):
    expected_kind = "customer"
    display_name: Annotated[str, Field(pattern=r"^合成客户[0-9]{2}$")]


class Supplier(Entity):
    expected_kind = "supplier"
    display_name: Annotated[str, Field(pattern=r"^合成供应商[0-9]{2}$")]
    currency: Currency


class Quote(Entity):
    expected_kind = "quote"
    supplier_ref: TemplateRef
    sku_ref: TemplateRef
    moq: Annotated[int, Field(gt=0)]
    unit_cost: MoneyText
    currency: Currency
    lead_days: Annotated[int, Field(ge=1, le=30)]
    valid_until: Timestamp


class Knowledge(Entity):
    expected_kind = "knowledge"
    document_version: Literal["v1"] = "v1"
    source_kind: Literal["synthetic"] = "synthetic"
    license: Literal["self-created-demo-v1"] = "self-created-demo-v1"
    body: str
    content_hash: Digest
    valid_from: Timestamp
    expires_at: Timestamp

    @model_validator(mode="after")
    def original_content(self) -> Self:
        if (
            self.body not in KNOWLEDGE_BODIES
            or self.content_hash != hashlib.sha256(self.body.encode()).hexdigest()
            or not self.valid_from <= SNAPSHOT_AT < self.expires_at
        ):
            raise ValueError("INVALID_SYNTHETIC_KNOWLEDGE")
        return self


class PurchaseFixture(Entity):
    expected_kind = "purchase_ref"
    sku_ref: TemplateRef
    quote_ref: TemplateRef
    supplier_ref: TemplateRef
    planned_stage: Literal["V4-2"] = "V4-2"
    hint: Literal["purchase_pending"] = "purchase_pending"


class SupportFixture(Entity):
    expected_kind = "support_ref"
    order_ref: TemplateRef
    customer_ref: TemplateRef
    knowledge_ref: TemplateRef
    planned_stage: Literal["V4-3"] = "V4-3"
    hint: Literal["support_escalation"] = "support_escalation"


class CampaignFixture(Entity):
    expected_kind = "campaign_ref"
    sku_ref: TemplateRef
    knowledge_ref: TemplateRef
    planned_stage: Literal["V4-3"] = "V4-3"
    hint: Literal["marketing_draft"] = "marketing_draft"


class SeedCounts(SummaryCounts):
    inventory: Units
    refunds: Units
    customers: Units
    suppliers: Units
    supplier_quotes: Units
    knowledge_refs: Units
    purchase_fixture_refs: Units
    support_fixture_refs: Units
    campaign_fixture_refs: Units


class ShopFixture(Contract):
    shop_key: ShopKey
    display_name: str
    timezone: str
    currency: Currency
    products: tuple[Product, ...] = Field(min_length=8, max_length=8)
    skus: tuple[SKU, ...] = Field(min_length=10, max_length=10)
    inventory: tuple[Inventory, ...] = Field(min_length=10, max_length=10)
    orders: tuple[Order, ...] = Field(min_length=12, max_length=12)
    order_lines: tuple[OrderLine, ...] = Field(min_length=18, max_length=18)
    refunds: tuple[Refund, ...] = Field(min_length=2, max_length=2)
    customers: tuple[Customer, ...] = Field(min_length=6, max_length=6)
    suppliers: tuple[Supplier, ...] = Field(min_length=2, max_length=2)
    supplier_quotes: tuple[Quote, ...] = Field(min_length=3, max_length=3)
    knowledge_refs: tuple[Knowledge, ...] = Field(min_length=2, max_length=2)
    purchase_fixture_refs: tuple[PurchaseFixture, ...] = Field(min_length=1, max_length=1)
    support_fixture_refs: tuple[SupportFixture, ...] = Field(min_length=1, max_length=1)
    campaign_fixture_refs: tuple[CampaignFixture, ...] = Field(min_length=1, max_length=1)

    def entities(self) -> tuple[Entity, ...]:
        return (
            *self.products,
            *self.skus,
            *self.inventory,
            *self.orders,
            *self.order_lines,
            *self.refunds,
            *self.customers,
            *self.suppliers,
            *self.supplier_quotes,
            *self.knowledge_refs,
            *self.purchase_fixture_refs,
            *self.support_fixture_refs,
            *self.campaign_fixture_refs,
        )

    def counts(self) -> SeedCounts:
        return SeedCounts(
            products=len(self.products),
            skus=len(self.skus),
            inventory=len(self.inventory),
            orders=len(self.orders),
            order_lines=len(self.order_lines),
            refunds=len(self.refunds),
            customers=len(self.customers),
            suppliers=len(self.suppliers),
            supplier_quotes=len(self.supplier_quotes),
            knowledge_refs=len(self.knowledge_refs),
            purchase_fixture_refs=len(self.purchase_fixture_refs),
            support_fixture_refs=len(self.support_fixture_refs),
            campaign_fixture_refs=len(self.campaign_fixture_refs),
        )

    def summary_counts(self) -> SummaryCounts:
        return SummaryCounts(
            products=len(self.products),
            skus=len(self.skus),
            orders=len(self.orders),
            order_lines=len(self.order_lines),
        )

    @model_validator(mode="after")
    def relationships(self) -> Self:
        if (self.display_name, self.timezone, self.currency) != SHOP_PARAMETERS[self.shop_key]:
            raise ValueError("INVALID_SHOP_PARAMETERS")
        groups = (
            self.products,
            self.skus,
            self.inventory,
            self.orders,
            self.order_lines,
            self.refunds,
            self.customers,
            self.suppliers,
            self.supplier_quotes,
            self.knowledge_refs,
            self.purchase_fixture_refs,
            self.support_fixture_refs,
            self.campaign_fixture_refs,
        )
        for group in groups:
            for index, entity in enumerate(group):
                if entity.ref != template_ref(self.shop_key, entity.expected_kind, index):
                    raise ValueError("INVALID_ENTITY_ORDER")
        all_entities = self.entities()
        catalog = {item.ref.id: item.ref for item in all_entities}
        if len(catalog) != len(all_entities):
            raise ValueError("DUPLICATE_ENTITY")
        for item in all_entities:
            if item.ref.shop_key != self.shop_key:
                raise ValueError("CROSS_SHOP_ENTITY")
            for field in type(item).model_fields:
                value = getattr(item, field)
                if isinstance(value, TemplateRef) and catalog.get(value.id) != value:
                    raise ValueError("INVALID_SOURCE_REF")
            if hasattr(item, "currency") and item.currency != self.currency:
                raise ValueError("MIXED_CURRENCY")
        products = {item.ref.id for item in self.products}
        skus = {item.ref.id: item for item in self.skus}
        orders = {item.ref.id: item for item in self.orders}
        customers = {item.ref.id for item in self.customers}
        suppliers = {item.ref.id for item in self.suppliers}
        quotes = {item.ref.id: item for item in self.supplier_quotes}
        knowledge = {item.ref.id for item in self.knowledge_refs}
        for index, sku in enumerate(self.skus):
            product = self.products[index // 2 if index < 4 else index - 2]
            variant = uuid5(product.ref.id, f"variant:{index}") if index < 4 else None
            if sku.product_ref != product.ref or sku.variant_ref != variant:
                raise ValueError("INVALID_SKU_PRODUCT_VARIANT")
            if sku.stock_pool_ref != uuid5(sku.ref.id, "stock-pool"):
                raise ValueError("INVALID_STOCK_POOL_SOURCE")
            if sku.product_ref.id not in products:
                raise ValueError("INVALID_PRODUCT_REF")
        if {stock.sku_ref.id for stock in self.inventory} != set(skus):
            raise ValueError("INCOMPLETE_INVENTORY_DOMAIN")
        for stock in self.inventory:
            if (
                stock.sku_ref.id not in skus
                or stock.stock_pool_ref != skus[stock.sku_ref.id].stock_pool_ref
            ):
                raise ValueError("INVALID_INVENTORY_POOL")
        start = datetime.combine(ANCHOR_DAY - timedelta(days=13), time.min, ZoneInfo(self.timezone))
        end = datetime.combine(ANCHOR_DAY + timedelta(days=1), time.min, ZoneInfo(self.timezone))
        for order in self.orders:
            if (
                order.customer_ref.id not in customers
                or not start <= order.created_at < end
                or order.paid_at is not None
                and not start <= order.paid_at < end
            ):
                raise ValueError("INVALID_ORDER_DOMAIN")
        with localcontext() as ctx:
            ctx.prec = 50
            totals = {identifier: Decimal(0) for identifier in orders}
            for line in self.order_lines:
                if line.order_ref.id not in orders or line.sku_ref.id not in skus:
                    raise ValueError("INVALID_ORDER_LINE_REF")
                if Decimal(line.net_amount) != Decimal(skus[line.sku_ref.id].price) * line.quantity:
                    raise ValueError("ORDER_LINE_AMOUNT_MISMATCH")
                totals[line.order_ref.id] += Decimal(line.net_amount)
            if any(
                totals[identifier] != Decimal(order.net_amount)
                for identifier, order in orders.items()
            ):
                raise ValueError("ORDER_TOTAL_MISMATCH")
            for refund in self.refunds:
                refunded_order = orders.get(refund.order_ref.id)
                if (
                    refunded_order is None
                    or refunded_order.paid_at is None
                    or not refunded_order.paid_at <= refund.occurred_at < end
                    or Decimal(refund.amount) > Decimal(refunded_order.net_amount)
                ):
                    raise ValueError("INVALID_REFUND_DOMAIN")
        for quote in self.supplier_quotes:
            if (
                quote.supplier_ref.id not in suppliers
                or quote.sku_ref.id not in skus
                or Decimal(quote.unit_cost) <= 0
                or quote.valid_until <= SNAPSHOT_AT
            ):
                raise ValueError("INVALID_QUOTE_REF")
        for purchase in self.purchase_fixture_refs:
            purchase_quote = quotes.get(purchase.quote_ref.id)
            if (
                purchase_quote is None
                or purchase.supplier_ref != purchase_quote.supplier_ref
                or purchase.sku_ref != purchase_quote.sku_ref
            ):
                raise ValueError("INVALID_PURCHASE_FIXTURE")
        for support in self.support_fixture_refs:
            support_order = orders.get(support.order_ref.id)
            if (
                support_order is None
                or support.customer_ref != support_order.customer_ref
                or support.knowledge_ref.id not in knowledge
            ):
                raise ValueError("INVALID_SUPPORT_FIXTURE")
        for campaign in self.campaign_fixture_refs:
            if campaign.sku_ref.id not in skus or campaign.knowledge_ref.id not in knowledge:
                raise ValueError("INVALID_CAMPAIGN_FIXTURE")
        return self


class Scenario(Contract):
    scenario_id: ScenarioId
    refs: tuple[TemplateRef, ...] = Field(min_length=1, max_length=8)
    status: Literal["fixture_links_only_not_functional_flows"] = (
        "fixture_links_only_not_functional_flows"
    )


class Modes(Contract):
    data_mode: Literal["demo_fixture"] = "demo_fixture"
    evidence_mode: Literal["synthetic_demo"] = "synthetic_demo"
    model_mode: Literal["offline_stub"] = "offline_stub"
    embedding_mode: Literal["synthetic_vector"] = "synthetic_vector"
    delivery_mode: Literal["offline_fake"] = "offline_fake"


class FixtureContent(Contract):
    schema_version: Literal["v4-demo-seed-content-v1"] = "v4-demo-seed-content-v1"
    fixture_version: Literal["v4-demo-seed-1"] = "v4-demo-seed-1"
    generator_version: Literal["v4-seed-generator-1"] = "v4-seed-generator-1"
    random_seed: Literal[4000001] = 4000001
    anchor_day: date = ANCHOR_DAY
    earliest_business_day: date = ANCHOR_DAY - timedelta(days=13)
    latest_business_day: date = ANCHOR_DAY
    snapshot_at: Timestamp = SNAPSHOT_AT
    modes: Modes
    shops: tuple[ShopFixture, ...] = Field(min_length=2, max_length=2)
    scenarios: tuple[Scenario, ...] = Field(min_length=6, max_length=6)

    @field_validator("random_seed", mode="before")
    @classmethod
    def integer_seed(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("INVALID_RANDOM_SEED")
        return value

    @model_validator(mode="after")
    def frozen_domain(self) -> Self:
        if (
            self.anchor_day != ANCHOR_DAY
            or self.earliest_business_day != ANCHOR_DAY - timedelta(days=13)
            or self.latest_business_day != ANCHOR_DAY
            or self.snapshot_at != SNAPSHOT_AT
            or tuple(shop.shop_key for shop in self.shops) != ("v4-shop-a", "v4-shop-b")
        ):
            raise ValueError("INVALID_FIXTURE_DOMAIN")
        expected = _scenarios()
        if self.scenarios != expected:
            raise ValueError("INVALID_SCENARIO_REFS")
        catalog = {item.ref.id: item for shop in self.shops for item in shop.entities()}
        for scenario in self.scenarios:
            if any(ref.id not in catalog or catalog[ref.id].ref != ref for ref in scenario.refs):
                raise ValueError("DANGLING_SCENARIO")
        shop = self.shops[0]
        stock = next(
            item for item in shop.inventory if item.sku_ref == template_ref("v4-shop-a", "sku", 0)
        )
        slow = template_ref("v4-shop-a", "sku", 9)
        slow_stock = next(item for item in shop.inventory if item.sku_ref == slow)
        if (
            stock.available_units != 0
            or not any(line.sku_ref == stock.sku_ref for line in shop.order_lines)
            or slow_stock.available_units != 80
            or any(line.sku_ref == slow for line in shop.order_lines)
        ):
            raise ValueError("INVALID_STOCK_SCENARIOS")
        if (
            shop.refunds[0].order_ref != template_ref("v4-shop-a", "order", 3)
            or shop.orders[3].customer_ref != template_ref("v4-shop-a", "customer", 3)
            or self.shops[1].purchase_fixture_refs[0].quote_ref
            != template_ref("v4-shop-b", "quote", 0)
            or self.shops[1].purchase_fixture_refs[0].sku_ref != template_ref("v4-shop-b", "sku", 0)
            or self.shops[1].support_fixture_refs[0].order_ref
            != template_ref("v4-shop-b", "order", 6)
            or self.shops[1].support_fixture_refs[0].knowledge_ref
            != template_ref("v4-shop-b", "knowledge", 0)
            or shop.campaign_fixture_refs[0].sku_ref != slow
            or shop.campaign_fixture_refs[0].knowledge_ref
            != template_ref("v4-shop-a", "knowledge", 1)
        ):
            raise ValueError("INVALID_SCENARIO_RELATIONSHIPS")
        refund = shop.refunds[0]
        order = next(item for item in shop.orders if item.ref == refund.order_ref)
        with localcontext() as ctx:
            ctx.prec = 50
            if Decimal(refund.amount) != Decimal(order.net_amount) * Decimal("0.8"):
                raise ValueError("INVALID_REFUND_SCENARIO")
        return self


class EntityDigest(Contract):
    ref: TemplateRef
    content_hash: Digest


class ShopManifest(Contract):
    shop_key: ShopKey
    counts: SeedCounts
    entities: tuple[EntityDigest, ...]


class SeedManifest(Contract):
    fixture_version: Literal["v4-demo-seed-1"] = "v4-demo-seed-1"
    generator_version: Literal["v4-seed-generator-1"] = "v4-seed-generator-1"
    content_digest: Digest
    snapshot_at: Timestamp
    shops: tuple[ShopManifest, ...] = Field(min_length=2, max_length=2)
    scenario_status: Literal["fixture_links_only_not_functional_flows"] = (
        "fixture_links_only_not_functional_flows"
    )


def _manifest(content: FixtureContent) -> SeedManifest:
    return SeedManifest(
        content_digest=facts_hash(content.model_dump(mode="json")),
        snapshot_at=content.snapshot_at,
        shops=tuple(
            ShopManifest(
                shop_key=shop.shop_key,
                counts=shop.counts(),
                entities=tuple(
                    EntityDigest(
                        ref=entity.ref, content_hash=facts_hash(entity.model_dump(mode="json"))
                    )
                    for entity in sorted(
                        shop.entities(), key=lambda item: (item.ref.kind, item.ref.key)
                    )
                ),
            )
            for shop in content.shops
        ),
    )


class SeedBundle(Contract):
    content: FixtureContent
    manifest: SeedManifest

    @model_validator(mode="after")
    def exact_manifest(self) -> Self:
        if self.manifest != _manifest(self.content):
            raise ValueError("SEED_MANIFEST_MISMATCH")
        return self

    def canonical_content(self) -> bytes:
        checked = type(self).model_validate(self)
        return canonical_bytes(checked.content.model_dump(mode="json"))


def _scenarios() -> tuple[Scenario, ...]:
    a: ShopKey = "v4-shop-a"
    b: ShopKey = "v4-shop-b"
    return (
        Scenario(
            scenario_id="stockout",
            refs=(
                template_ref(a, "sku", 0),
                template_ref(a, "inventory", 0),
                template_ref(a, "order", 0),
                template_ref(a, "order", 9),
            ),
        ),
        Scenario(
            scenario_id="high_refund",
            refs=(
                template_ref(a, "order", 3),
                template_ref(a, "refund", 0),
                template_ref(a, "customer", 3),
            ),
        ),
        Scenario(
            scenario_id="slow_moving",
            refs=(template_ref(a, "sku", 9), template_ref(a, "inventory", 9)),
        ),
        Scenario(
            scenario_id="purchase_pending",
            refs=(
                template_ref(b, "purchase_ref", 0),
                template_ref(b, "quote", 0),
                template_ref(b, "supplier", 0),
                template_ref(b, "sku", 0),
            ),
        ),
        Scenario(
            scenario_id="support_escalation",
            refs=(
                template_ref(b, "support_ref", 0),
                template_ref(b, "order", 6),
                template_ref(b, "customer", 0),
                template_ref(b, "knowledge", 0),
            ),
        ),
        Scenario(
            scenario_id="marketing_draft",
            refs=(
                template_ref(a, "campaign_ref", 0),
                template_ref(a, "sku", 9),
                template_ref(a, "knowledge", 1),
            ),
        ),
    )


def _shop(key: ShopKey, rng: random.Random) -> ShopFixture:
    display, timezone, currency = SHOP_PARAMETERS[key]
    products = tuple(
        Product(ref=template_ref(key, "product", i), title=f"合成商品{i:02}") for i in range(8)
    )
    skus = tuple(
        SKU(
            ref=template_ref(key, "sku", i),
            label=f"SKU-{i:02}",
            product_ref=products[i // 2 if i < 4 else i - 2].ref,
            variant_ref=uuid5(products[i // 2].ref.id, f"variant:{i}") if i < 4 else None,
            stock_pool_ref=uuid5(template_ref(key, "sku", i).id, "stock-pool"),
            price=str(100 + 10 * i),
            currency=currency,
        )
        for i in range(10)
    )
    customers = tuple(
        Customer(ref=template_ref(key, "customer", i), display_name=f"合成客户{i:02}")
        for i in range(6)
    )
    lines: list[OrderLine] = []
    orders: list[Order] = []
    for i in range(12):
        amounts: list[int] = []
        for j in range(2 if i < 6 else 1):
            sku = skus[(i + j) % 9]
            quantity = 1 + len(lines) % 3
            amount = int(sku.price) * quantity
            amounts.append(amount)
            lines.append(
                OrderLine(
                    ref=template_ref(key, "order_line", len(lines)),
                    order_ref=template_ref(key, "order", i),
                    sku_ref=sku.ref,
                    quantity=quantity,
                    net_amount=str(amount),
                    currency=currency,
                )
            )
        created = datetime.combine(
            ANCHOR_DAY - timedelta(days=11 - i), time(10, i), ZoneInfo(timezone)
        )
        orders.append(
            Order(
                ref=template_ref(key, "order", i),
                customer_ref=customers[i % 6].ref,
                created_at=created,
                paid_at=created + timedelta(hours=1) if i < 11 else None,
                net_amount=str(sum(amounts)),
                currency=currency,
                status_hint="payment_recorded" if i < 11 else "payment_timestamp_unknown",
            )
        )
    suppliers = tuple(
        Supplier(
            ref=template_ref(key, "supplier", i),
            display_name=f"合成供应商{i:02}",
            currency=currency,
        )
        for i in range(2)
    )
    quotes = tuple(
        Quote(
            ref=template_ref(key, "quote", i),
            supplier_ref=suppliers[i % 2].ref,
            sku_ref=skus[i].ref,
            moq=5 * (i + 1),
            unit_cost=str(40 + 5 * i),
            currency=currency,
            lead_days=rng.randint(2, 12),
            valid_until=datetime(2026, 11, 16, tzinfo=UTC),
        )
        for i in range(3)
    )
    knowledge = tuple(
        Knowledge(
            ref=template_ref(key, "knowledge", i),
            body=body,
            content_hash=hashlib.sha256(body.encode()).hexdigest(),
            valid_from=datetime(2026, 10, 1, tzinfo=UTC),
            expires_at=datetime(2026, 12, 1, tzinfo=UTC),
        )
        for i, body in enumerate(KNOWLEDGE_BODIES)
    )
    paid = orders[3].paid_at
    if paid is None:
        raise ValueError("INVALID_GENERATOR_ORDER")
    return ShopFixture(
        shop_key=key,
        display_name=display,
        timezone=timezone,
        currency=currency,
        products=products,
        skus=skus,
        customers=customers,
        orders=tuple(orders),
        order_lines=tuple(lines),
        suppliers=suppliers,
        supplier_quotes=quotes,
        knowledge_refs=knowledge,
        inventory=tuple(
            Inventory(
                ref=template_ref(key, "inventory", i),
                sku_ref=sku.ref,
                stock_pool_ref=sku.stock_pool_ref,
                available_units=0 if i == 0 else 80 if i == 9 else 20 + i,
                stock_reason=None,
            )
            for i, sku in enumerate(skus)
        ),
        refunds=(
            Refund(
                ref=template_ref(key, "refund", 0),
                order_ref=orders[3].ref,
                occurred_at=paid + timedelta(days=1),
                amount=str(int(orders[3].net_amount) * 8 // 10),
                currency=currency,
            ),
            Refund(
                ref=template_ref(key, "refund", 1),
                order_ref=orders[1].ref,
                occurred_at=datetime.combine(ANCHOR_DAY, time(12), ZoneInfo(timezone)),
                amount=str(int(orders[1].net_amount) // 5),
                currency=currency,
            ),
        ),
        purchase_fixture_refs=(
            PurchaseFixture(
                ref=template_ref(key, "purchase_ref", 0),
                sku_ref=skus[0].ref,
                quote_ref=quotes[0].ref,
                supplier_ref=suppliers[0].ref,
            ),
        ),
        support_fixture_refs=(
            SupportFixture(
                ref=template_ref(key, "support_ref", 0),
                order_ref=orders[6].ref,
                customer_ref=customers[0].ref,
                knowledge_ref=knowledge[0].ref,
            ),
        ),
        campaign_fixture_refs=(
            CampaignFixture(
                ref=template_ref(key, "campaign_ref", 0),
                sku_ref=skus[9].ref,
                knowledge_ref=knowledge[1].ref,
            ),
        ),
    )


def generate_seed() -> SeedBundle:
    """Return the one fixed fixture version; no tenant, authority, wall clock or I/O inputs."""
    rng = random.Random(RANDOM_SEED)  # noqa: S311 -- deterministic synthetic quotes, never auth.
    content = FixtureContent(
        modes=Modes(),
        shops=(_shop("v4-shop-a", rng), _shop("v4-shop-b", rng)),
        scenarios=_scenarios(),
    )
    return SeedBundle(content=content, manifest=_manifest(content))
