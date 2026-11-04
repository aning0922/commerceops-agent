"""One bounded effective view for catalog, orders and analytics, without I/O or authority."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from commerceops.application.v4_demo.contracts import Contract, Counter, Currency, Digest, ShopKey
from commerceops.application.v4_demo.seed_contract import FixtureContent
from commerceops.application.v41 import contracts as dto
from commerceops.domain.commerce_values import facts_hash


class ViewScope(Contract):
    tenant_id: UUID
    shop_id: UUID
    reset_epoch: Counter
    template_key: ShopKey


class TagEffect(Contract):
    scope: ViewScope
    product_id: UUID
    version: Annotated[int, Field(ge=1)]
    tags: dto.Tags


class FulfillmentEffect(Contract):
    scope: ViewScope
    order_id: UUID
    version: Annotated[int, Field(ge=1, le=1)]
    status: Literal["demo_fulfilled"]


class ImportedProduct(Contract):
    scope: ViewScope
    product_id: UUID
    sku_id: UUID
    import_job_id: UUID
    import_row: Annotated[int, Field(ge=2, le=501)]
    file_digest: Digest
    product: dto.NormalizedProduct


class EffectDigest(Contract):
    kind: Literal["product_tags", "order_fulfillment", "import_confirm"]
    object_id: UUID
    version: Annotated[int, Field(ge=1)]
    payload_digest: Digest


class EffectiveView(Contract):
    scope: ViewScope
    source: dto.DatasetSource
    timezone: Literal["Asia/Taipei", "Asia/Shanghai"]
    currency: Currency
    earliest_business_day: date
    latest_business_day: date
    products: tuple[dto.Product, ...] = Field(max_length=508)
    orders: tuple[dto.Order, ...] = Field(max_length=12)
    effects: tuple[EffectDigest, ...] = Field(max_length=1020)

    def revision(self) -> str:
        # Identity generation/read clock deliberately do not replace business revision.
        return facts_hash(
            dict(
                fixture_digest=self.source.fixture_digest,
                scope=self.scope.model_dump(mode="json"),
                effects=[row.model_dump(mode="json") for row in self.effects],
            )
        )


def build_view(
    fixture: FixtureContent,
    fixture_digest: str,
    scope: ViewScope,
    *,
    tags: tuple[TagEffect, ...] = (),
    fulfillments: tuple[FulfillmentEffect, ...] = (),
    imports: tuple[ImportedProduct, ...] = (),
) -> EffectiveView:
    """Caller must already authorize and lock scope; these input rows are never capabilities."""
    if facts_hash(fixture.model_dump(mode="json")) != fixture_digest:
        raise ValueError("FIXTURE_DIGEST_MISMATCH")
    # Revalidate even a caller-supplied model_copy/model_construct before using source facts.
    fixture = FixtureContent.model_validate_json(fixture.model_dump_json())
    template = next(shop for shop in fixture.shops if shop.shop_key == scope.template_key)
    source = dto.SourceRef(
        data_mode="demo_fixture",
        fixture_digest=fixture_digest,
        baseline_snapshot_at=fixture.snapshot_at,
        import_job_id=None,
    )
    if len(imports) > 500 or len(tags) > 508 or len(fulfillments) > 12:
        raise ValueError("EFFECT_LIMIT")
    scopes = (
        [item.scope for item in tags]
        + [item.scope for item in fulfillments]
        + [item.scope for item in imports]
    )
    if any(item != scope for item in scopes):
        raise ValueError("EFFECT_SCOPE_MISMATCH")
    stocks = {row.sku_ref.id: row for row in template.inventory}
    products: dict[UUID, dto.Product] = {}
    for base_product in template.products:
        skus = tuple(
            dto.SKU(
                sku_id=sku.ref.id,
                label=sku.label,
                price=sku.price,
                currency=sku.currency,
                available_units=stocks[sku.ref.id].available_units,
                stock_reason=stocks[sku.ref.id].stock_reason,
            )
            for sku in template.skus
            if sku.product_ref == base_product.ref
        )
        products[base_product.ref.id] = dto.Product(
            product_id=base_product.ref.id,
            title=base_product.title,
            tags=(),
            version=0,
            source=source,
            skus=skus,
        )
    identifiers = {row.ref.id for row in template.entities()}
    labels = {sku.label.casefold() for sku in template.skus}
    for uploaded in imports:
        item = uploaded.product
        if (
            uploaded.product_id == uploaded.sku_id
            or uploaded.product_id in identifiers
            or uploaded.sku_id in identifiers
            or item.canonical_sku in labels
            or item.currency != template.currency
        ):
            raise ValueError("IMPORT_IDENTITY_CONFLICT")
        identifiers.update((uploaded.product_id, uploaded.sku_id))
        labels.add(item.canonical_sku)
        products[uploaded.product_id] = dto.Product(
            product_id=uploaded.product_id,
            title=item.title,
            tags=item.tags,
            version=0,
            source=dto.SourceRef(
                data_mode="demo_upload",
                fixture_digest=fixture_digest,
                baseline_snapshot_at=fixture.snapshot_at,
                import_job_id=uploaded.import_job_id,
                import_row=uploaded.import_row,
                file_digest=uploaded.file_digest,
            ),
            skus=(
                dto.SKU(
                    sku_id=uploaded.sku_id,
                    label=item.sku,
                    price=item.price,
                    currency=item.currency,
                    available_units=None,
                    stock_reason="UNKNOWN_STOCK",
                ),
            ),
        )
    touched: set[UUID] = set()
    for tag in tags:
        if tag.product_id not in products or tag.product_id in touched:
            raise ValueError("TAG_SOURCE_MISMATCH")
        product = products[tag.product_id]
        products[tag.product_id] = dto.Product(
            product_id=product.product_id,
            title=product.title,
            tags=tag.tags,
            version=tag.version,
            source=product.source,
            skus=product.skus,
        )
        touched.add(tag.product_id)
    fulfillment_map = {row.order_id: row for row in fulfillments}
    if len(fulfillment_map) != len(fulfillments) or not set(fulfillment_map).issubset(
        row.ref.id for row in template.orders
    ):
        raise ValueError("FULFILLMENT_SOURCE_MISMATCH")
    sku_products = {sku.ref.id: sku.product_ref.id for sku in template.skus}
    orders = []
    for row in template.orders:
        effect = fulfillment_map.get(row.ref.id)
        if effect is not None and row.paid_at is None:
            raise ValueError("PAYMENT_STATE_UNKNOWN")
        orders.append(
            dto.Order(
                order_id=row.ref.id,
                created_at=row.created_at,
                paid_at=row.paid_at,
                payment_status=row.status_hint,
                net_amount=row.net_amount,
                currency=row.currency,
                demo_fulfillment="demo_fulfilled" if effect else "demo_unfulfilled",
                fulfillment_version=effect.version if effect else 0,
                source=source,
                lines=tuple(
                    dto.OrderLine(
                        line_id=line.ref.id,
                        product_id=sku_products[line.sku_ref.id],
                        sku_id=line.sku_ref.id,
                        quantity=line.quantity,
                        net_amount=line.net_amount,
                        currency=line.currency,
                    )
                    for line in template.order_lines
                    if line.order_ref == row.ref
                ),
                refunds=tuple(
                    dto.RefundEvent(
                        refund_id=refund.ref.id,
                        occurred_at=refund.occurred_at,
                        amount=refund.amount,
                        currency=refund.currency,
                    )
                    for refund in template.refunds
                    if refund.order_ref == row.ref
                ),
            )
        )
    return EffectiveView(
        scope=scope,
        source=dto.DatasetSource(
            data_mode="demo_mixed" if imports else "demo_fixture",
            fixture_digest=fixture_digest,
            baseline_snapshot_at=fixture.snapshot_at,
            uploads=tuple(
                products[row.product_id].source
                for row in sorted(imports, key=lambda item: (item.import_job_id, item.import_row))
            ),
        ),
        timezone="Asia/Taipei" if template.shop_key == "v4-shop-a" else "Asia/Shanghai",
        currency=template.currency,
        earliest_business_day=fixture.earliest_business_day,
        latest_business_day=fixture.latest_business_day,
        products=tuple(sorted(products.values(), key=lambda item: item.product_id)),
        orders=tuple(sorted(orders, key=lambda item: item.order_id)),
        effects=tuple(
            sorted(
                (
                    *(
                        EffectDigest(
                            kind="product_tags",
                            object_id=item.product_id,
                            version=item.version,
                            payload_digest=facts_hash(item.model_dump(mode="json")),
                        )
                        for item in tags
                    ),
                    *(
                        EffectDigest(
                            kind="order_fulfillment",
                            object_id=item.order_id,
                            version=item.version,
                            payload_digest=facts_hash(item.model_dump(mode="json")),
                        )
                        for item in fulfillments
                    ),
                    *(
                        EffectDigest(
                            kind="import_confirm",
                            object_id=item.product_id,
                            version=1,
                            payload_digest=facts_hash(item.model_dump(mode="json")),
                        )
                        for item in imports
                    ),
                ),
                key=lambda item: (item.kind, item.object_id),
            )
        ),
    )


def product_detail(
    view: EffectiveView, product_id: UUID, snapshot: dto.Snapshot
) -> dto.ProductDetail:
    if snapshot.data_revision != view.revision() or snapshot.source != view.source:
        raise ValueError("SNAPSHOT_CHANGED")
    product = next((item for item in view.products if item.product_id == product_id), None)
    if product is None:
        raise ValueError("RESOURCE_NOT_FOUND")
    return dto.ProductDetail(
        snapshot=snapshot,
        product=product,
        related_order_ids=tuple(
            order.order_id
            for order in view.orders
            if any(line.product_id == product_id for line in order.lines)
        ),
    )
