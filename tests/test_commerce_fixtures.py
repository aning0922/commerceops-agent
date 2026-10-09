"""冻结原始样本/纸面金标及 manifest；不是 P202 生产规则测试。"""

import hashlib
import json
import shutil
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from commerceops.adapters.commerce.mock import Fixture, MockCommerce
from commerceops.application.commerce.contracts import (
    CommerceFailure,
    Inventory,
    OrderLine,
    Product,
    Refund,
    Window,
)
from commerceops.domain.commerce_values import complete_days, utc_time

pytestmark = pytest.mark.offline
DIRECTORY = Path(__file__).parent / "fixtures/commerce/inventory-v1"
GOLD: dict[str, Any] = json.loads((DIRECTORY / "goldens.json").read_text())["expectations"]


def test_manifest_hashes_scope_and_explicit_clock() -> None:
    manifest = json.loads((DIRECTORY / "manifest.json").read_text())
    raw = json.loads((DIRECTORY / "datasets.json").read_text())
    assert manifest["dataset_version"] == "inventory-v1"
    assert manifest["schema_version"] == "commerce-v1"
    assert manifest["rule_version"] == "inventory-rule-v1"
    assert manifest["seed"] == "not_used"
    assert manifest["now"] == "2026-10-08T10:00:00+08:00"
    assert manifest["source_mode"] == "mock"
    assert manifest["model_mode"] == manifest["approval_mode"] == "not_used"
    assert set(manifest["scope"]) == set(raw["cases"]) == set(GOLD)
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((DIRECTORY / name).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("case", sorted(GOLD))
def test_each_raw_fixture_validates_and_is_immutable(case: str) -> None:
    fixture = Fixture.load(DIRECTORY, case)
    assert fixture.source.provenance.raw_hash
    assert fixture.now == utc_time("2026-10-08T10:00:00+08:00")
    rows: tuple[Product | OrderLine | Refund | Inventory, ...] = (
        *fixture.products,
        *fixture.orders,
        *fixture.refunds,
        *fixture.inventories,
    )
    for row in rows:
        assert row.source.source_kind == "mock" and row.source.raw_hash
        assert row.source.fixture_version == "inventory-v1"
    assert Fixture.load(DIRECTORY, case) == fixture


@pytest.mark.parametrize(
    "case",
    [
        "baseline",
        "equal_trigger",
        "normal",
        "backlog",
        "zero_stock",
        "known_inbound",
        "unknown_inbound",
        "rational_risk",
        "rational_normal",
        "no_demand",
        "no_demand_zero",
        "no_demand_negative",
        "unknown_stock",
        "mixed_refunds",
        "full_refund",
        "partial_refund",
        "unlinked_amount_refund",
        "cross_period",
    ],
)
def test_paper_arithmetic_independent_of_future_rule_module(case: str) -> None:
    # 人类给定数字和静态 JSON 互相复核；没有生产风险/建议计算模块。
    g = GOLD[case]
    fixture = Fixture.load(DIRECTORY, case)
    gross = fixture.orders[0].quantity if fixture.orders else 0
    assert gross == g["gross_units"]
    demand = Fraction(gross, 7)
    assert demand == Fraction(int(g["D"]["numerator"]), int(g["D"]["denominator"]))
    target = demand * (g["L"] + g["R"] + g["S"])
    assert g["T"] == -(-target.numerator // target.denominator)
    assert demand * (g["L"] + g["S"]) == Fraction(
        int(g["trigger"]["numerator"]), int(g["trigger"]["denominator"])
    )
    assert fixture.inventories[0].available_stock == g["A"]
    assert fixture.inventories[0].inbound_units == g["inbound_units"]
    if g["suggested_units"] is not None:
        assert g["suggested_units"] == max(0, g["T"] - g["A"] - g["effective_inbound_units"])
    if g["coverage"] is not None:
        assert Fraction(g["A"], 1) / demand == Fraction(
            int(g["coverage"]["numerator"]), int(g["coverage"]["denominator"])
        )
    assert g["analysis_only"] and not g["eligible_for_execution"]
    if g["inbound_units"] is None:
        assert g["effective_inbound_units"] == 0
        assert g["required_assumptions"] == ["inbound_unknown_zero:sku/demo/100/p"]


def test_order_status_paper_inclusion_and_evidence() -> None:
    fixture = Fixture.load(DIRECTORY, "statuses")
    by_id = {row.order_id: row for row in fixture.orders}
    g = GOLD["statuses"]
    assert sum(by_id[key].quantity for key in g["included_order_ids"]) == 70
    assert [by_id[key].status for key in g["excluded_order_ids"]] == [
        "pending",
        "on-hold",
        "cancelled",
        "failed",
        "trash",
    ]
    assert by_id["status-2"].paid_at is not None
    assert by_id["status-3"].completed_at is not None
    assert by_id["status-4"].paid_at is None and by_id["status-4"].completed_at is None
    assert by_id["status-10"].status == "custom-plugin"
    assert (
        len(
            MockCommerce(fixture)
            .list_order_lines(Window(start=utc_time("2026-10-01T00:00:00+08:00"), end=fixture.now))
            .items
        )
        == 11
    )  # adapter 保留状态；纳入资格由未来 P202 判定。


@pytest.mark.parametrize("case", ["boundaries", "dst"])
def test_window_gold_includes_start_excludes_end(case: str) -> None:
    fixture = Fixture.load(DIRECTORY, case)
    g = GOLD[case]
    now = utc_time(g["explicit_now"]) if "explicit_now" in g else fixture.now
    start, end = complete_days(now, fixture.source.timezone)
    assert start == utc_time(g["start"]) and end == utc_time(g["end"])
    rows = MockCommerce(fixture).list_order_lines(Window(start=start, end=end)).items
    assert [row.order_id for row in rows] == g["included_order_ids"]
    assert sum(row.quantity for row in rows) == g["gross_units"]


@pytest.mark.parametrize(
    "case",
    ["mixed_refunds", "full_refund", "partial_refund", "unlinked_amount_refund", "cross_period"],
)
def test_refund_gold_quantity_completeness(case: str) -> None:
    fixture = Fixture.load(DIRECTORY, case)
    cohort = MockCommerce(fixture).list_refunds(("o1",)).items
    quantities = [line.refunded_quantity for row in cohort for line in row.lines]
    unknown = any(q is None for q in quantities) or any(not row.lines for row in cohort)
    known = sum(q for q in quantities if q is not None)
    g = GOLD[case]
    assert known == g["known_refunded_units"]
    assert g["quantity_complete"] == (not unknown)
    if unknown:
        assert g["refunded_units"] is None and g["net_units"] is None
    else:
        assert g["refunded_units"] == known and g["net_units"] == 70 - known
    assert fixture.inventories[0].available_stock == 20


@pytest.mark.parametrize(
    "mutation",
    [
        "hash",
        "bool_quantity",
        "decimal_quantity",
        "currency",
        "naive_time",
        "duplicate_id",
        "duplicate_json_key",
        "constant_nan",
        "cross_currency",
    ],
)
def test_invalid_fixture_is_safe_failure_not_empty(mutation: str, tmp_path: Path) -> None:
    for name in ("datasets.json", "goldens.json", "manifest.json"):
        shutil.copyfile(DIRECTORY / name, tmp_path / name)
    path = tmp_path / "datasets.json"
    root = json.loads(path.read_text())
    row = root["cases"]["baseline"]["orders"][0]
    if mutation == "bool_quantity":
        row["quantity"] = True
    elif mutation == "decimal_quantity":
        row["quantity"] = 1.5
    elif mutation == "currency":
        row["currency"] = "AAA"
    elif mutation == "cross_currency":
        row["currency"] = "USD"
    elif mutation == "naive_time":
        row["created_at"] = "2026-10-02T00:00:00"
    elif mutation == "duplicate_id":
        root["cases"]["baseline"]["orders"].append(row)
    payload = json.dumps(root)
    if mutation == "duplicate_json_key":
        payload = '{"dataset_version":"bad",' + payload[1:]
    if mutation == "constant_nan":
        payload = payload.replace('"quantity": 70', '"quantity": NaN', 1)
    path.write_text(payload)
    if mutation != "hash":
        manifest_path = tmp_path / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["files"]["datasets.json"] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(CommerceFailure, match="^INVALID_DATA$") as raised:
        Fixture.load(tmp_path)
    assert not raised.value.error.retryable
    assert str(tmp_path) not in str(raised.value)


def _copy_fixture() -> dict[str, dict[str, Any]]:
    return {
        name: json.loads((DIRECTORY / name).read_text())
        for name in ("datasets.json", "goldens.json", "manifest.json")
    }


def _write_fixture(directory: Path, files: dict[str, dict[str, Any]]) -> None:
    for name in ("datasets.json", "goldens.json"):
        path = directory / name
        path.write_text(json.dumps(files[name]))
        files["manifest.json"]["files"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (directory / "manifest.json").write_text(json.dumps(files["manifest.json"]))


@pytest.mark.parametrize("name", ["datasets.json", "goldens.json", "manifest.json"])
@pytest.mark.parametrize(
    "field",
    [
        "dataset_version",
        "schema_version",
        "fixture_version",
        "rule_version",
        "canonical_version",
        "now",
    ],
)
def test_fixture_rejects_inconsistent_metadata_even_with_updated_hash(
    name: str, field: str, tmp_path: Path
) -> None:
    files = _copy_fixture()
    files[name][field] = "2030-01-01T00:00:00Z" if field == "now" else "unsupported-v2"
    _write_fixture(tmp_path, files)
    with pytest.raises(CommerceFailure, match="^INVALID_DATA$"):
        Fixture.load(tmp_path)


def test_unsupported_fixture_version_cannot_be_relabelled_v1(tmp_path: Path) -> None:
    files = _copy_fixture()
    for name in files:
        files[name]["fixture_version"] = "inventory-v2"
    _write_fixture(tmp_path, files)
    with pytest.raises(CommerceFailure, match="^INVALID_DATA$"):
        Fixture.load(tmp_path)


@pytest.mark.parametrize(
    "mutation",
    [
        "inventory_pool_mismatch",
        "inventory_other_shop",
        "order_other_shop",
        "product_pool_other_shop",
        "inventory_unmapped_sku",
        "malformed_sku",
    ],
)
def test_fixture_rejects_contradictory_stock_pool_or_shop(mutation: str, tmp_path: Path) -> None:
    files = _copy_fixture()
    case = files["datasets.json"]["cases"]["baseline"]
    inventory = case["inventories"][0]
    if mutation == "inventory_pool_mismatch":
        inventory["stock_pool_key"] = "pool/demo/101"
    elif mutation == "inventory_other_shop":
        inventory["sku_key"] = "sku/other/100/p"
        inventory["stock_pool_key"] = "pool/other/100"
    elif mutation == "order_other_shop":
        case["orders"][0]["sku_key"] = "sku/other/100/p"
    elif mutation == "product_pool_other_shop":
        case["products"][0]["stock_pool_key"] = "pool/other/100"
    elif mutation == "inventory_unmapped_sku":
        inventory["sku_key"] = "sku/demo/101/p"
    else:
        inventory["sku_key"] = "sku/demo/100/v/"
    _write_fixture(tmp_path, files)
    with pytest.raises(CommerceFailure, match="^INVALID_DATA$"):
        Fixture.load(tmp_path)
