"""Independent hand-calculated goldens on the actual seed, not a mirror sum implementation."""

import json
from datetime import UTC, date, datetime, timedelta
from decimal import localcontext
from uuid import uuid4

import pytest
from commerceops.application.v4_demo.seed_contract import FixtureContent, SeedBundle, generate_seed
from commerceops.application.v41 import contracts as dto
from commerceops.application.v41.analytics import dashboard, snapshot_for
from commerceops.application.v41.effective import (
    FulfillmentEffect,
    ImportedProduct,
    TagEffect,
    ViewScope,
    build_view,
    product_detail,
)
from commerceops.domain.commerce_values import facts_hash

pytestmark = pytest.mark.offline
READ_AT = datetime(2026, 11, 4, tzinfo=UTC)


@pytest.fixture(scope="module")
def seed() -> SeedBundle:
    return generate_seed()


def scope() -> ViewScope:
    return ViewScope(tenant_id=uuid4(), shop_id=uuid4(), reset_epoch=0, template_key="v4-shop-a")


def test_actual_seed_seven_days_have_known_subtotals_not_settled_cash(seed: SeedBundle) -> None:
    owner = scope()
    view = build_view(seed.content, seed.manifest.content_digest, owner)
    result = dashboard(view, dto.PeriodQuery(shop_id=owner.shop_id), READ_AT)
    metrics = {row.metric: row for row in result.metrics}
    # Oct26..Nov01 paid records: 780,160,340,540,100,220; Nov01 has unknown pay time.
    assert metrics["created_order_count"].value == "7"
    paid = metrics["paid_order_amount"]
    assert (paid.value, paid.known_value, paid.included_count, paid.excluded_count) == (
        None,
        "2140",
        6,
        1,
    )
    assert paid.completeness == "PARTIAL"
    assert paid.reason_codes == ("UNKNOWN_PAYMENT_TIME",)
    assert metrics["paid_order_count"].known_value == "6"
    assert metrics["average_paid_order_amount"].known_value == "356.666667"
    refund = metrics["refund_event_amount"]
    assert refund.value == "90" and refund.settlement_status == "UNKNOWN"
    assert metrics["refund_event_count"].value == "1"
    assert metrics["product_count"].value == "8"
    assert metrics["low_stock_count"].value == "1"
    assert result.period.from_date == date(2026, 10, 26)
    assert result.period.to_date == date(2026, 11, 2)
    assert result.period.from_utc == datetime(2026, 10, 25, 16, tzinfo=UTC)
    last = {row.metric: row for row in result.trend[-1].metrics}
    assert last["paid_order_amount"].value is None
    assert last["paid_order_amount"].known_value == "0"
    assert last["refund_event_amount"].value == "90"
    assert result.comparison_value is None and result.model_mode == "not_used"
    assert all(sku.cost_amount is None for product in view.products for sku in product.skus)


def test_refund_date_is_not_order_creation_or_known_settlement(seed: SeedBundle) -> None:
    owner = scope()
    view = build_view(seed.content, seed.manifest.content_digest, owner)
    result = dashboard(
        view,
        dto.PeriodQuery(
            shop_id=owner.shop_id, from_date=date(2026, 10, 25), to_date=date(2026, 10, 26)
        ),
        READ_AT,
    )
    metrics = {row.metric: row for row in result.metrics}
    # Oct24 order has total410 and 328 refund event on Oct25; Oct25 order pays570.
    assert metrics["paid_order_amount"].value == "570"
    assert metrics["refund_event_amount"].value == "328"
    assert metrics["refund_event_amount"].settlement_status == "UNKNOWN"
    assert metrics["paid_order_count"].value == "1"
    assert len(result.trend) == 1


def test_fourteen_day_goldens_and_decimal_context_independence(seed: SeedBundle) -> None:
    owner = scope()
    view = build_view(seed.content, seed.manifest.content_digest, owner)
    with localcontext() as context:
        context.prec = 2
        result = dashboard(view, dto.PeriodQuery(shop_id=owner.shop_id, days=14), READ_AT)
    metrics = {row.metric: row for row in result.metrics}
    # First eleven order totals = 320+450+630+410+570+780+160+340+540+100+220.
    assert metrics["paid_order_amount"].known_value == "4520"
    assert metrics["paid_order_amount"].value is None
    assert metrics["average_paid_order_amount"].known_value == "410.909091"
    assert metrics["refund_event_amount"].value == "418"  # 328 + 90; no cash inference.
    assert metrics["created_order_count"].value == "12"


def test_outside_window_and_empty_denominator_remain_nullable(seed: SeedBundle) -> None:
    owner = scope()
    view = build_view(seed.content, seed.manifest.content_digest, owner)
    result = dashboard(
        view,
        dto.PeriodQuery(
            shop_id=owner.shop_id, from_date=date(2026, 10, 1), to_date=date(2026, 10, 2)
        ),
        READ_AT,
    )
    metrics = {row.metric: row for row in result.metrics}
    assert metrics["paid_order_amount"].value is None
    assert metrics["paid_order_amount"].known_value == "0"
    average = metrics["average_paid_order_amount"]
    assert average.value is None and average.completeness == "UNAVAILABLE"
    assert average.reason_codes == ("OUTSIDE_SOURCE_WINDOW", "NO_DENOMINATOR")


def test_effect_revision_is_separate_from_read_clock_and_original_facts(seed: SeedBundle) -> None:
    owner = scope()
    original = build_view(seed.content, seed.manifest.content_digest, owner)
    product_id = seed.content.shops[0].products[0].ref.id
    order_id = seed.content.shops[0].orders[0].ref.id
    view = build_view(
        seed.content,
        seed.manifest.content_digest,
        owner,
        tags=(TagEffect(scope=owner, product_id=product_id, version=1, tags=("演示标签",)),),
        fulfillments=(
            FulfillmentEffect(scope=owner, order_id=order_id, version=1, status="demo_fulfilled"),
        ),
    )
    assert view.revision() != original.revision()
    query = dto.PeriodQuery(shop_id=owner.shop_id)
    a = dashboard(view, query, READ_AT)
    b = dashboard(view, query, READ_AT + timedelta(days=20))
    assert a.snapshot.data_revision == b.snapshot.data_revision
    assert a.snapshot.snapshot_id == b.snapshot.snapshot_id
    assert a.period == b.period and a.metrics == b.metrics
    detail = product_detail(view, product_id, a.snapshot)
    assert detail.product.tags == ("演示标签",) and detail.product.version == 1
    assert order_id in detail.related_order_ids
    assert view.orders != original.orders
    assert [o.net_amount for o in view.orders] == [o.net_amount for o in original.orders]
    with pytest.raises(ValueError, match="SNAPSHOT_CHANGED"):
        product_detail(view, product_id, snapshot_for(original, {}, READ_AT))


def test_context_source_and_unknown_payment_fulfillment_fail_closed(seed: SeedBundle) -> None:
    owner = scope()
    other = scope()
    with pytest.raises(ValueError, match="EFFECT_SCOPE_MISMATCH"):
        build_view(
            seed.content,
            seed.manifest.content_digest,
            owner,
            tags=(
                TagEffect(
                    scope=other,
                    product_id=seed.content.shops[0].products[0].ref.id,
                    version=1,
                    tags=(),
                ),
            ),
        )
    with pytest.raises(ValueError, match="PAYMENT_STATE_UNKNOWN"):
        build_view(
            seed.content,
            seed.manifest.content_digest,
            owner,
            fulfillments=(
                FulfillmentEffect(
                    scope=owner,
                    order_id=seed.content.shops[0].orders[-1].ref.id,
                    version=1,
                    status="demo_fulfilled",
                ),
            ),
        )
    with pytest.raises(ValueError, match="FIXTURE_DIGEST_MISMATCH"):
        build_view(seed.content, "a" * 64, owner)


def test_import_changes_only_catalog_and_truthful_mixed_provenance(seed: SeedBundle) -> None:
    owner = scope()
    row = ImportedProduct(
        scope=owner,
        product_id=uuid4(),
        sku_id=uuid4(),
        import_job_id=uuid4(),
        import_row=2,
        file_digest="a" * 64,
        product=dto.NormalizedProduct(
            sku="NEW-1",
            canonical_sku="new-1",
            title="演示上传",
            price="0.1",
            currency="TWD",
            tags=(),
        ),
    )
    view = build_view(seed.content, seed.manifest.content_digest, owner, imports=(row,))
    result = dashboard(view, dto.PeriodQuery(shop_id=owner.shop_id), READ_AT)
    metrics = {row.metric: row for row in result.metrics}
    assert metrics["product_count"].value == "9"
    assert metrics["paid_order_amount"].known_value == "2140"
    assert metrics["low_stock_count"].value is None
    assert result.snapshot.source.data_mode == "demo_mixed"
    source = result.snapshot.source.uploads[0]
    assert source.import_job_id == row.import_job_id and source.import_row == 2
    assert source.file_digest == row.file_digest
    detail = product_detail(view, row.product_id, result.snapshot)
    assert detail.product.skus[0].available_units is None
    assert detail.related_order_ids == ()
    with pytest.raises(ValueError, match="IMPORT_IDENTITY_CONFLICT"):
        build_view(seed.content, seed.manifest.content_digest, owner, imports=(row, row))


def test_unknown_stock_remains_partial_without_changing_generator(seed: SeedBundle) -> None:
    owner = scope()
    content = seed.content.model_dump(mode="json")
    content["shops"][0]["inventory"][1].update(available_units=None, stock_reason="UNKNOWN_STOCK")
    fixture = FixtureContent.model_validate_json(json.dumps(content))
    view = build_view(fixture, facts_hash(content), owner)
    result = dashboard(view, dto.PeriodQuery(shop_id=owner.shop_id), READ_AT)
    low = next(row for row in result.metrics if row.metric == "low_stock_count")
    assert low.value is None and low.known_value == "1" and low.excluded_count == 1
