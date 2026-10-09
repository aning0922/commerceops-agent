"""冻结金标、状态/退款口径、完整性、候选容量与hash业务不变量。"""

import hashlib
import json
from pathlib import Path

import pytest
from commerceops.adapters.commerce.mock import Behavior, Fixture, MockCommerce
from commerceops.application.commerce.contracts import Quality, Window
from commerceops.application.commerce.inventory_analysis import (
    InventoryAnalysisError,
    analyze_inventory,
)
from commerceops.application.commerce.inventory_facts import (
    InventoryInput,
    InventoryReport,
    OpenWorkItemInput,
)
from commerceops.domain.commerce_values import complete_days, utc_time
from commerceops.domain.inventory_rules import RuleParameters
from pydantic import ValidationError

pytestmark = pytest.mark.offline
DIRECTORY = Path(__file__).parent / "fixtures/commerce/inventory-v1"
RAW = json.loads((DIRECTORY / "datasets.json").read_text())
GOLD = json.loads((DIRECTORY / "goldens.json").read_text())["expectations"]


def data(case: str = "baseline") -> InventoryInput:
    f = Fixture.load(DIRECTORY, case)
    now = utc_time(GOLD[case]["explicit_now"]) if case == "dst" else f.now
    return InventoryInput(
        source=f.source,
        now=now,
        products=f.products,
        order_lines=f.orders,
        refunds=f.refunds,
        inventories=f.inventories,
        complete=True,
        open_items=tuple(
            OpenWorkItemInput.model_validate(row) for row in RAW["cases"][case]["open_items"]
        ),
    )


@pytest.mark.parametrize("case", [key for key, g in GOLD.items() if "T" in g])
def test_all_eighteen_numeric_goldens_match_production_facts(case: str) -> None:
    gold = GOLD[case]
    report = analyze_inventory(data(case), RuleParameters(L=gold["L"], R=gold["R"], S=gold["S"]))
    actual = report.items[0].model_dump(mode="json")
    assert {key: actual[key] for key in gold} == gold
    assert not report.execution_available and all(
        not f.eligible_for_execution for f in report.items
    )
    assert report.facts_hash == hashlib.sha256(report.canonical_bytes()).hexdigest()


def test_status_evidence_inclusion_and_unmapped_status_review() -> None:
    report = analyze_inventory(data("statuses"))
    fact = report.items[0]
    gold = GOLD["statuses"]
    assert fact.gross_units == gold["gross_units"] == 70
    assert list(fact.included_order_ids) == gold["included_order_ids"]
    assert list(fact.excluded_order_ids) == gold["excluded_order_ids"]
    assert list(fact.review_order_ids) == sorted(gold["review_order_ids"])
    assert fact.suggested_units is None and "ORDER_STATUS_REVIEW" in fact.hard_blocks


@pytest.mark.parametrize("case", ["boundaries", "dst"])
def test_window_other_goldens(case: str) -> None:
    report = analyze_inventory(data(case))
    fact = report.items[0]
    gold = GOLD[case]
    assert fact.gross_units == gold["gross_units"]
    assert set(fact.included_order_ids) == set(gold["included_order_ids"])
    assert report.window.start == utc_time(gold["start"])
    assert report.window.end == utc_time(gold["end"])


def test_open_and_identity_other_goldens() -> None:
    report = analyze_inventory(data("open_item"))
    fact = report.items[0]
    assert len(fact.open_item_ids) == GOLD["open_item"]["open_items"] == 1
    assert "OPEN_WORK_ITEM" in fact.hard_blocks and fact.suggested_units is None
    assert fact.effective_inbound_units == GOLD["open_item"]["effective_inbound_units"] == 0
    shared = analyze_inventory(data("identity"))
    gold = GOLD["identity"]
    products = [f for f in shared.items if f.active is not None]
    assert len(products) == gold["unique_sku_keys"] == 4
    assert sum(f.sku_label in (None, "") for f in products) == gold["empty_or_null_sku_labels"] == 2
    assert sum(f.sku_label == gold["duplicate_label"] for f in products) == 2
    pooled = [f for f in products if f.stock_pool_key == gold["shared_pool_key"]]
    assert len(pooled) == 3 and all(gold["hard_block"] in f.hard_blocks for f in pooled)
    deleted = next(f for f in shared.items if f.sku_key == gold["deleted_sku_key"])
    assert "DELETED_PRODUCT" in deleted.hard_blocks and deleted.suggested_units is None
    assert not shared.complete and all(f.suggested_units is None for f in shared.items)


@pytest.mark.parametrize("case", ["empty_products", "empty_orders"])
def test_true_empty_other_goldens(case: str) -> None:
    report = analyze_inventory(data(case))
    gold = GOLD[case]
    assert len(report.items) == gold["products"] and report.complete == gold["complete"]
    assert sum(f.known_gross_units for f in report.items) == gold["orders"] == 0
    assert report.candidate_count == 0 and not report.scope_required
    assert all(f.suggested_units is None for f in report.items)


@pytest.mark.parametrize(
    "quality",
    [
        Quality.DUPLICATE_ID,
        Quality.MISSING_PAGE,
        Quality.SOURCE_CHANGED,
        Quality.CAPACITY_LIMIT,
        Quality.PARTIAL_FAILURE,
    ],
)
def test_source_faults_cannot_be_waived_by_unknown_inbound(quality: Quality) -> None:
    base = data("unknown_inbound")
    report = analyze_inventory(base.model_copy(update={"complete": False, "warnings": (quality,)}))
    f = report.items[0]
    assert f.known_gross_units == 70 and f.gross_units is None and f.D is None
    assert f.refunded_units is None and f.net_units is None
    assert not report.complete and f.suggested_units is None and not f.can_form_suggestion
    assert f.required_assumptions == () and f.inbound_units is None


@pytest.mark.parametrize(
    "behavior",
    [
        Behavior(duplicate_second_page=True),
        Behavior(omit_second_page=True),
        Behavior(change_second_page=True),
        Behavior(max_pages=1),
        Behavior(fail_on_call=2),
    ],
)
def test_actual_mock_partial_pages_feed_hard_block(behavior: Behavior) -> None:
    fixture = Fixture.load(DIRECTORY, "statuses")
    mock = MockCommerce(fixture, page_size=2, behavior=behavior)
    window = Window(
        start=utc_time("2026-10-01T00:00:00+08:00"), end=utc_time("2026-10-08T00:00:00+08:00")
    )
    pages = [mock.list_order_lines(window)]
    while pages[-1].next_cursor is not None and pages[-1].error is None:
        pages.append(mock.list_order_lines(window, cursor=pages[-1].next_cursor))
    value = data("statuses").model_copy(
        update={
            "order_lines": tuple(row for page in pages for row in page.items),
            "complete": False,
            "warnings": tuple(sorted({flag for page in pages for flag in page.warnings})),
        }
    )
    report = analyze_inventory(value)
    assert not report.complete and report.candidate_count == 0
    assert all(f.suggested_units is None and f.D is None for f in report.items)


@pytest.mark.parametrize("bad", [True, 1.5, float("nan"), "2"])
def test_no_internal_model_copy_quantity_coercion(bad: object) -> None:
    value = data()
    row = value.order_lines[0].model_copy(update={"quantity": bad})
    with pytest.raises(InventoryAnalysisError, match="^INVALID_INVENTORY_INPUT$"):
        analyze_inventory(value.model_copy(update={"order_lines": (row,)}))


def test_mixed_currency_and_provenance_block_all_metrics() -> None:
    value = data()
    mixed = value.order_lines[0].model_copy(update={"currency": "USD"})
    report = analyze_inventory(value.model_copy(update={"order_lines": (mixed,)}))
    assert "CURRENCY_MISMATCH" in report.warnings
    assert report.items[0].D is None and report.items[0].suggested_units is None
    changed = value.order_lines[0].source.model_copy(update={"fixture_version": "inventory-v2"})
    row = value.order_lines[0].model_copy(update={"source": changed})
    assert (
        "PROVENANCE_MISMATCH"
        in analyze_inventory(value.model_copy(update={"order_lines": (row,)})).warnings
    )


def many(count: int) -> InventoryInput:
    base = data()
    products = []
    orders = []
    inventories = []
    for i in range(count):
        pid = str(100 + i)
        sku = f"sku/demo/{pid}/p"
        pool = f"pool/demo/{pid}"
        products.append(
            base.products[0].model_copy(
                update={"product_id": pid, "sku_key": sku, "stock_pool_key": pool}
            )
        )
        orders.append(
            base.order_lines[0].model_copy(update={"order_id": "o" + pid, "sku_key": sku})
        )
        inventories.append(
            base.inventories[0].model_copy(update={"sku_key": sku, "stock_pool_key": pool})
        )
    return base.model_copy(
        update={
            "products": tuple(products),
            "order_lines": tuple(orders),
            "inventories": tuple(inventories),
        }
    )


@pytest.mark.parametrize("count", [20, 21])
def test_twenty_candidate_limit_never_truncates(count: int) -> None:
    report = analyze_inventory(many(count))
    assert len(report.items) == count and report.candidate_count == count
    assert report.scope_required == (count > 20)
    if count == 20:
        assert all(f.suggested_units == 100 and f.can_form_suggestion for f in report.items)
    else:
        assert all(f.suggested_units is None and not f.can_form_suggestion for f in report.items)
        assert all("SCOPE_TOO_LARGE" in f.hard_blocks for f in report.items)


def test_hash_replay_permutation_display_and_input_change() -> None:
    value = many(3)
    first = analyze_inventory(value)
    reordered = value.model_copy(
        update={
            "products": value.products[::-1],
            "order_lines": value.order_lines[::-1],
            "inventories": value.inventories[::-1],
        }
    )
    assert first.model_dump_json() == analyze_inventory(reordered).model_dump_json()
    assert first.facts_hash == analyze_inventory(value).facts_hash
    changed = value.inventories[0].model_copy(update={"available_stock": 21})
    assert (
        first.facts_hash
        != analyze_inventory(
            value.model_copy(update={"inventories": (changed, *value.inventories[1:])})
        ).facts_hash
    )
    f = first.items[0]
    display = f.display.model_copy(update={"D": "client display override"})
    altered = first.model_copy(
        update={"items": (f.model_copy(update={"display": display}), *first.items[1:])}
    )
    assert first.canonical_bytes() == altered.canonical_bytes()
    assert first.facts_hash == altered.facts_hash
    loaded = InventoryReport.model_validate_json(first.model_dump_json())
    assert loaded == first


def test_hard_stock_quality_pool_mismatch_and_approval_fields() -> None:
    value = data("unknown_inbound")
    missing = value.model_copy(update={"inventories": ()})
    fact = analyze_inventory(missing).items[0]
    assert fact.suggested_units is None and "UNKNOWN_STOCK" in fact.hard_blocks
    stock = value.inventories[0].model_copy(update={"stock_pool_key": "pool/demo/101"})
    report = analyze_inventory(value.model_copy(update={"inventories": (stock,)}))
    assert "STOCK_POOL_MISMATCH" in report.warnings and report.items[0].D is None
    payload = value.model_dump(mode="python")
    payload["approved"] = True
    with pytest.raises(ValidationError, match="extra_forbidden"):
        InventoryInput.model_validate(payload)
    with pytest.raises(ValidationError):
        fact.model_validate({**fact.model_dump(mode="python"), "eligible_for_execution": True})


def test_refund_overflow_unmatched_lines_and_open_quantity_not_inbound() -> None:
    value = data("partial_refund")
    line = value.refunds[0].lines[0].model_copy(update={"refunded_quantity": 71})
    refund = value.refunds[0].model_copy(update={"lines": (line,)})
    fact = analyze_inventory(value.model_copy(update={"refunds": (refund,)})).items[0]
    assert (
        fact.known_refunded_units == 71 and fact.refunded_units is None and fact.net_units is None
    )
    assert "REFUND_QUANTITY_EXCEEDS_LINE" in fact.hard_blocks and fact.suggested_units is None
    bad_line = line.model_copy(update={"line_id": "missing"})
    bad = refund.model_copy(update={"lines": (bad_line,)})
    fact = analyze_inventory(value.model_copy(update={"refunds": (bad,)})).items[0]
    assert "REFUND_LINE_UNRESOLVED" in fact.hard_blocks and fact.net_units is None
    open_value = data("open_item")
    known = analyze_inventory(open_value).items[0]
    changed = open_value.open_items[0].model_copy(update={"quantity": 999})
    other = analyze_inventory(open_value.model_copy(update={"open_items": (changed,)})).items[0]
    assert known.effective_inbound_units == other.effective_inbound_units == 0
    assert known.suggested_units is None and other.suggested_units is None


def test_midnight_fold_at_application_window_boundary() -> None:
    value = data()
    source = value.source.model_copy(update={"timezone": "America/Havana"})
    first_today = value.order_lines[0].model_copy(
        update={"order_id": "today", "created_at": utc_time("2026-11-01T00:15:00-04:00")}
    )
    yesterday = value.order_lines[0].model_copy(
        update={"order_id": "yesterday", "created_at": utc_time("2026-10-31T23:59:59-04:00")}
    )
    report = analyze_inventory(
        value.model_copy(
            update={
                "source": source,
                "now": utc_time("2026-11-01T00:30:00-05:00"),
                "order_lines": (first_today, yesterday),
            }
        )
    )
    assert report.window.end == utc_time("2026-11-01T04:00:00Z")
    assert report.items[0].included_order_ids == ("yesterday",)
    assert report.items[0].gross_units == 70


def test_non_seven_day_window_and_duplicate_ids_are_incomplete() -> None:
    value = data()
    wrong_window = Window(start=utc_time("2026-10-02T00:00:00+08:00"), end=value.now)
    report = analyze_inventory(value.model_copy(update={"window": wrong_window}))
    assert not report.source_complete and "WINDOW_MISMATCH" in report.warnings
    assert report.items[0].gross_units is None and report.items[0].suggested_units is None
    duplicate = value.model_copy(update={"order_lines": (*value.order_lines, *value.order_lines)})
    report = analyze_inventory(duplicate)
    assert report.items[0].known_gross_units == 70
    assert report.items[0].gross_units is None and "DUPLICATE_ID" in report.warnings


def test_normal_unknown_inbound_is_not_an_unneeded_approval_proposal() -> None:
    value = data("unknown_inbound")
    stock = value.inventories[0].model_copy(update={"available_stock": 51})
    fact = analyze_inventory(value.model_copy(update={"inventories": (stock,)})).items[0]
    assert fact.inbound_units is None and fact.inbound_reason == "not_provided"
    assert fact.risk == "normal" and fact.suggested_units is None
    assert fact.required_assumptions == () and not fact.eligible_for_execution


def test_open_and_candidate_cap_are_not_partial_collection() -> None:
    open_report = analyze_inventory(data("open_item"))
    capped = analyze_inventory(many(21))
    assert open_report.source_complete and open_report.complete and open_report.requires_review
    assert (
        capped.source_complete
        and capped.complete
        and capped.scope_required
        and capped.requires_review
    )
    assert analyze_inventory(data("unknown_stock")).source_complete
    assert not analyze_inventory(data("unknown_stock")).complete


def test_empty_report_hash_binds_parameters_and_internal_approval_rejected() -> None:
    empty = data("empty_products")
    assert (
        analyze_inventory(empty).facts_hash
        != analyze_inventory(empty, RuleParameters(L=4)).facts_hash
    )
    value = data().model_copy(update={"approved": True})
    with pytest.raises(InventoryAnalysisError):
        analyze_inventory(value)


def test_exact_shared_labels_do_not_prove_stock_allocation() -> None:
    value = data("identity")
    rows = tuple(row.model_copy(update={"pool_allocation": "exact"}) for row in value.inventories)
    report = analyze_inventory(value.model_copy(update={"inventories": rows}))
    pooled = [f for f in report.items if f.stock_pool_key == "pool/demo/10"]
    assert len(pooled) == 3
    assert all(
        f.suggested_units is None and "SHARED_POOL_UNRESOLVED" in f.hard_blocks for f in pooled
    )


@pytest.mark.parametrize("paid_at", ["2030-01-01T00:00:00Z", "2020-01-01T00:00:00Z"])
def test_impossible_refunded_timestamp_is_not_payment_evidence(paid_at: str) -> None:
    value = data("full_refund")
    row = value.order_lines[0].model_copy(update={"paid_at": utc_time(paid_at)})
    fact = analyze_inventory(value.model_copy(update={"order_lines": (row,)})).items[0]
    assert fact.gross_units == 0 and fact.review_order_ids == ("o1",)
    assert fact.suggested_units is None and "ORDER_STATUS_REVIEW" in fact.hard_blocks


def test_malformed_but_matching_pool_is_not_complete_source() -> None:
    value = data()
    pool = "pool/demo/100/v"
    product = value.products[0].model_copy(update={"stock_pool_key": pool})
    stock = value.inventories[0].model_copy(update={"stock_pool_key": pool})
    report = analyze_inventory(
        value.model_copy(update={"products": (product,), "inventories": (stock,)})
    )
    assert not report.source_complete and report.items[0].suggested_units is None


def test_unknown_parameter_object_is_not_defaulted() -> None:
    with pytest.raises(ValueError, match="INVALID_PARAMETERS"):
        analyze_inventory(data(), False)  # type: ignore[arg-type]


def test_explicit_default_window_has_same_exact_facts_hash() -> None:
    value = data()
    start, end = complete_days(value.now, value.source.timezone)
    explicit = value.model_copy(update={"window": Window(start=start, end=end)})
    assert analyze_inventory(value).facts_hash == analyze_inventory(explicit).facts_hash


@pytest.mark.parametrize("field", ["available_stock", "inbound_units"])
def test_stock_integer_fields_reject_internal_bool(field: str) -> None:
    value = data()
    stock = value.inventories[0].model_copy(update={field: True})
    with pytest.raises(InventoryAnalysisError):
        analyze_inventory(value.model_copy(update={"inventories": (stock,)}))


def test_nested_dict_model_provenance_cannot_bypass_native_validation() -> None:
    value = data()
    forged = value.source.provenance.model_copy(update={"source_kind": True})
    source = {**value.source.__dict__, "provenance": forged}
    products = tuple({**row.__dict__, "source": forged} for row in value.products)
    orders = tuple({**row.__dict__, "source": forged} for row in value.order_lines)
    stocks = tuple({**row.__dict__, "source": forged} for row in value.inventories)
    mixed = value.model_copy(
        update={
            "source": source,
            "products": products,
            "order_lines": orders,
            "inventories": stocks,
        }
    )
    with pytest.raises(InventoryAnalysisError, match="^INVALID_INVENTORY_INPUT$"):
        analyze_inventory(mixed)
