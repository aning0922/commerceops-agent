"""Real effective views and stateless cursors/exports; authority still belongs to the caller."""

import csv
import io
import secrets
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from commerceops.application.v4_demo.seed_contract import generate_seed
from commerceops.application.v41 import contracts as dto
from commerceops.application.v41.effective import ImportedProduct, TagEffect, ViewScope, build_view
from commerceops.application.v41.queries import (
    drilldown,
    export_orders,
    export_products,
    orders_page,
    products_page,
    read_context,
)

pytestmark = pytest.mark.offline
NOW = datetime(2026, 11, 4, tzinfo=UTC)


def scope() -> ViewScope:
    return ViewScope(tenant_id=uuid4(), shop_id=uuid4(), reset_epoch=0, template_key="v4-shop-a")


def test_product_pages_bind_scope_filter_generation_revision_and_last_sort_key() -> None:
    bundle = generate_seed()
    owner = scope()
    view = build_view(bundle.content, bundle.manifest.content_digest, owner)
    signing = secrets.token_bytes(32)
    query = dto.ProductQuery(shop_id=owner.shop_id, limit=2)
    first = products_page(view, query, NOW, 0, signing)
    assert [item.title for item in first.items] == ["合成商品00", "合成商品01"]
    assert first.total == 8 and first.next_cursor is not None
    second_query = query.model_copy(update=dict(cursor=first.next_cursor))
    second = products_page(view, second_query, NOW, 0, signing)
    assert [item.title for item in second.items] == ["合成商品02", "合成商品03"]
    assert second.snapshot.snapshot_id == first.snapshot.snapshot_id
    for bad in (second_query.model_copy(update=dict(q="different")),):
        with pytest.raises(ValueError, match="SNAPSHOT_CHANGED"):
            products_page(view, bad, NOW, 0, signing)
    with pytest.raises(ValueError, match="SNAPSHOT_CHANGED"):
        products_page(view, second_query, NOW, 1, signing)
    changed = build_view(
        bundle.content,
        bundle.manifest.content_digest,
        owner,
        tags=(
            TagEffect(
                scope=owner, product_id=first.items[0].product_id, version=1, tags=("changed",)
            ),
        ),
    )
    with pytest.raises(ValueError, match="SNAPSHOT_CHANGED"):
        products_page(changed, second_query, NOW, 0, signing)
    cursor = first.next_cursor
    tampered = cursor[:-1] + ("0" if cursor[-1] != "0" else "1")
    with pytest.raises(ValueError, match="INVALID_REQUEST"):
        products_page(view, query.model_copy(update=dict(cursor=tampered)), NOW, 0, signing)
    other = scope()
    other_view = build_view(bundle.content, bundle.manifest.content_digest, other)
    with pytest.raises(ValueError, match="SNAPSHOT_CHANGED"):
        products_page(
            other_view, dto.ProductQuery(shop_id=other.shop_id, cursor=cursor), NOW, 0, signing
        )


def test_price_sort_is_decimal_and_import_source_filter_is_real() -> None:
    bundle = generate_seed()
    owner = scope()
    records = tuple(
        ImportedProduct(
            scope=owner,
            product_id=uuid4(),
            sku_id=uuid4(),
            import_job_id=uuid4(),
            import_row=2,
            file_digest="a" * 64,
            product=dto.NormalizedProduct(
                sku=f"NEW-{index}",
                canonical_sku=f"new-{index}",
                title=f"Imported{index}",
                price=price,
                currency="TWD",
                tags=("new",),
            ),
        )
        for index, price in enumerate(("9", "1000"))
    )
    view = build_view(bundle.content, bundle.manifest.content_digest, owner, imports=records)
    result = products_page(
        view,
        dto.ProductQuery(shop_id=owner.shop_id, origin="demo_upload", tag="new", sort="price_asc"),
        NOW,
        0,
        secrets.token_bytes(32),
    )
    assert [row.skus[0].price for row in result.items] == ["9", "1000"]
    assert result.total == 2 and result.snapshot.source.data_mode == "demo_mixed"


def test_export_is_all_filtered_rows_not_current_page_and_is_formula_safe() -> None:
    bundle = generate_seed()
    owner = scope()
    view = build_view(
        bundle.content,
        bundle.manifest.content_digest,
        owner,
        tags=(
            TagEffect(
                scope=owner,
                product_id=bundle.content.shops[0].products[0].ref.id,
                version=1,
                tags=("=1+1",),
            ),
        ),
    )
    signing = secrets.token_bytes(32)
    query = dto.ProductQuery(shop_id=owner.shop_id, limit=1)
    page = products_page(view, query, NOW, 0, signing)
    exported = export_products(view, query, NOW, 0, signing)
    assert exported.filename == "products.csv" and exported.row_count == 10
    assert exported.snapshot.snapshot_id == page.snapshot.snapshot_id
    rows = list(csv.DictReader(io.StringIO(exported.csv_text)))
    assert len(rows) == 10 and rows[0]["tags"] == "'=1+1"
    assert {row["data_revision"] for row in rows} == {view.revision()}
    filtered = export_products(
        view, dto.ProductQuery(shop_id=owner.shop_id, tag="=1+1"), NOW, 0, signing
    )
    assert filtered.row_count == 2


def test_orders_unknown_payment_export_and_refund_drilldown_preserve_original_links() -> None:
    bundle = generate_seed()
    owner = scope()
    view = build_view(bundle.content, bundle.manifest.content_digest, owner)
    signing = secrets.token_bytes(32)
    query = dto.OrderQuery(shop_id=owner.shop_id, payment="unknown")
    page = orders_page(view, query, NOW, 0, signing)
    assert page.total == 1 and page.items[0].paid_at is None
    exported = export_orders(view, query, NOW, 0, signing)
    rows = list(csv.DictReader(io.StringIO(exported.csv_text)))
    assert rows[0]["paid_at"] == "" and rows[0]["payment_status"] == "payment_timestamp_unknown"
    with pytest.raises(ValueError, match="INVALID_REQUEST"):
        orders_page(view, query.model_copy(update=dict(time_basis="paid")), NOW, 0, signing)
    refunded = drilldown(
        view,
        dto.DrilldownQuery(
            shop_id=owner.shop_id,
            metric="refund_event_amount",
            from_date=date(2026, 10, 25),
            to_date=date(2026, 10, 26),
        ),
        NOW,
        0,
        signing,
    )
    assert refunded.total == 1
    item = refunded.items[0]
    assert isinstance(item, dto.RefundReference)
    assert item.amount == "328" and item.order_id == bundle.content.shops[0].orders[3].ref.id
    assert item.payment_gateway_status == "UNKNOWN"


def test_read_context_contains_authorized_view_facts_not_simulated_ai() -> None:
    bundle = generate_seed()
    owner = scope()
    view = build_view(bundle.content, bundle.manifest.content_digest, owner)
    product = bundle.content.shops[0].products[0]
    result = read_context(
        view,
        dto.ReadContextQuery(shop_id=owner.shop_id, kind="product", resource_id=product.ref.id),
        NOW,
    )
    assert result.product is not None and result.product.title == product.title
    assert result.order is None and result.model_mode == "not_used"
    dashboard_context = read_context(
        view, dto.ReadContextQuery(shop_id=owner.shop_id, kind="dashboard"), NOW
    )
    assert (
        next(m for m in dashboard_context.metrics if m.metric == "paid_order_amount").value is None
    )
    with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
        read_context(
            view,
            dto.ReadContextQuery(shop_id=owner.shop_id, kind="product", resource_id=uuid4()),
            NOW,
        )
