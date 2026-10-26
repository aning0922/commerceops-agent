"""Positive lab contracts only; platform/PG acceptance requires separate actual runs."""

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pytest import MonkeyPatch as MP

from scripts.woo_lab import lab
from scripts.woo_lab.expectations import expected_document, positive_golden
from scripts.woo_lab.profiles import (
    MIXED_SHA256,
    POSITIVE,
    SYNTHETIC_SHOP,
    ProfileFailure,
    bind_profile,
    encoded,
    read_bound_spec,
    resolve_positive,
)

pytestmark = pytest.mark.offline
ROOT = lab.ROOT


def resolved() -> dict[str, Any]:
    template = json.loads((ROOT / "tests/fixtures/woocommerce-local/positive.json").read_text())
    return resolve_positive(
        template, "2026-10-26", SYNTHETIC_SHOP, datetime(2026, 10, 26, tzinfo=UTC)
    )


def mapping_for(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "products": {p["key"]: 10 + i for i, p in enumerate(spec["products"])},
        "orders": {
            o["key"]: {"id": 100 + i, "lines": [{"id": 200 + i}]}
            for i, o in enumerate(spec["orders"])
        },
        "refunds": {},
    }


def test_positive_four_exact_pools_and_independent_arithmetic_golden() -> None:
    spec = resolved()
    mapping = mapping_for(spec)
    expected = expected_document(spec, mapping)
    assert {k: len(v) for k, v in expected["expected"].items()} == {
        "products": 4,
        "order_lines": 4,
        "refunds": 0,
        "inventories": 4,
    }
    inventory = expected["expected"]["inventories"]
    assert [i["available_stock"] for i in inventory] == [20, 8, 0, 5]
    assert all(i["manage_stock"] and i["pool_allocation"] == "exact" for i in inventory)
    assert all(i["inbound_units"] is None and i["inbound_quality"] == "unknown" for i in inventory)
    assert len({i["stock_pool_key"] for i in inventory}) == 4
    gold = positive_golden(spec, mapping)
    assert [r["suggested_units"] for r in gold["facts"]] == [100, 40, 60, 19]
    assert [r["T"] for r in gold["facts"]] == [120, 48, 60, 24]
    assert gold["total_quantity"] == 219 and gold["net_amount"] == "994"
    assert gold["complete"] and gold["requires_review"] and gold["assumption_count"] == 4
    assert all(
        r["required_assumptions"] == ["inbound_unknown_zero:" + r["sku_key"]]
        and not r["hard_blocks"]
        for r in gold["facts"]
    )
    assert gold["execution_or_pg_acceptance"] == "not_proven_by_this_document"


def test_frozen_seven_day_window_and_shop_namespace() -> None:
    spec = resolved()
    assert spec["clock"] == "2026-10-26T00:00:00+08:00"
    assert spec["window_start"] == "2026-10-19T00:00:00+08:00"
    assert spec["window_end"] == spec["clock"]
    before = encoded(spec)
    later = resolve_positive(
        json.loads((ROOT / "tests/fixtures/woocommerce-local/positive.json").read_text()),
        "2026-10-26",
        SYNTHETIC_SHOP,
        datetime(2026, 11, 1, tzinfo=UTC),
    )
    assert encoded(later) == before
    uuid = "00000000-0000-4000-8000-000000000123"
    spec["shop_id"] = uuid
    expected = expected_document(spec, mapping_for(spec))
    assert expected["shop_id"] == uuid
    assert all(
        p["shop_id"] == uuid and p["sku_key"].startswith("sku/" + uuid + "/")
        for p in expected["expected"]["products"]
    )


@pytest.mark.parametrize("anchor", ["2026-10-27", "2026-2-01", "not-a-day"])
def test_future_or_invalid_anchor_refused(anchor: str) -> None:
    template = json.loads((ROOT / "tests/fixtures/woocommerce-local/positive.json").read_text())
    with pytest.raises(ProfileFailure, match="ANCHOR"):
        resolve_positive(template, anchor, SYNTHETIC_SHOP, datetime(2026, 10, 26, tzinfo=UTC))


def bound_directory(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    directory = tmp_path / "woolab-123456789abc"
    directory.mkdir(mode=0o700)
    binding, raw = bind_profile(ROOT, POSITIVE, "2000-01-01", None)
    config = {
        **binding,
        "project": directory.name,
        "external_shop_key": directory.name,
        "seed_file": str(directory / "seed-spec.private.json"),
        "port": 18443,
        "internal_subnet": "10.247.0.0/28",
        "ingress_subnet": "10.247.0.16/28",
    }
    lab.write_private(directory / "seed-spec.private.json", raw)
    lab.write_private(
        directory / "compose.env",
        (
            f"WOO_LAB_PROJECT={directory.name}\nWOO_LAB_PRIVATE_DIR={directory}\nWOO_LAB_PORT=18443\n"
            "WOO_LAB_INTERNAL_SUBNET=10.247.0.0/28\nWOO_LAB_INGRESS_SUBNET=10.247.0.16/28\n"
            f"WOO_LAB_SEED_FILE={config['seed_file']}\n"
        ).encode(),
    )
    return directory, config


@pytest.mark.parametrize(
    "field",
    [
        "profile",
        "anchor_day",
        "shop_id",
        "spec_sha256",
        "template_sha256",
        "external_shop_key",
        "seed_file",
    ],
)
def test_wrong_binding_never_falls_back_to_mixed(tmp_path: Path, field: str) -> None:
    directory, config = bound_directory(tmp_path)
    assert read_bound_spec(ROOT, config, directory)["profile"] == POSITIVE
    config[field] = "wrong"
    with pytest.raises(ProfileFailure):
        read_bound_spec(ROOT, config, directory)


def test_spec_and_mount_tampering_refused(tmp_path: Path) -> None:
    directory, config = bound_directory(tmp_path)
    original = (directory / "seed-spec.private.json").read_bytes()
    lab.write_private(directory / "seed-spec.private.json", original + b" ")
    with pytest.raises(ProfileFailure, match="SPEC_MISMATCH"):
        read_bound_spec(ROOT, config, directory)
    lab.write_private(directory / "seed-spec.private.json", original)
    lab.write_private(directory / "compose.env", b"WOO_LAB_SEED_FILE=/another/lab.json\n")
    with pytest.raises(ProfileFailure, match="MOUNT_BINDING"):
        read_bound_spec(ROOT, config, directory)


def test_cold_process_same_spec_and_mixed_unchanged(tmp_path: Path) -> None:
    assert hashlib.sha256(lab.FIXTURE.read_bytes()).hexdigest() == MIXED_SHA256
    directory, config = bound_directory(tmp_path)
    lab.write_private(directory / "config.json", config)
    code = (
        "import json,sys;from pathlib import Path;"
        "from scripts.woo_lab.profiles import read_bound_spec,encoded;"
        "p=Path(sys.argv[1]);d=json.loads((p/'config.json').read_text());"
        "print(encoded(read_bound_spec(Path.cwd(),d,p)).hex())"
    )
    args = [sys.executable, "-c", code, str(directory)]
    first = subprocess.check_output(args, cwd=ROOT, timeout=10)
    second = subprocess.check_output(args, cwd=ROOT, timeout=10)
    assert first == second
    assert (
        bytes.fromhex(first.decode().strip()) == (directory / "seed-spec.private.json").read_bytes()
    )
    with pytest.raises(ProfileFailure):
        bind_profile(ROOT, "unknown", None, None)
    assert not any(p.name.startswith("woolab-") for p in tmp_path.iterdir() if p != directory)


def test_independent_gold_matches_existing_pure_rules_without_pg_or_adapter_output() -> None:
    from commerceops.application.commerce.contracts import (
        Inventory,
        OrderLine,
        Product,
        Provenance,
        Source,
    )
    from commerceops.application.commerce.inventory_analysis import analyze_inventory
    from commerceops.application.commerce.inventory_facts import InventoryInput

    spec = resolved()
    mapping = mapping_for(spec)
    expected = expected_document(spec, mapping)
    provenance = Provenance(
        source_kind="woocommerce_test",
        fixture_version=None,
        captured_at=spec["clock"],
        raw_hash="a" * 64,
    )
    source = Source(
        shop_id=expected["shop_id"], timezone="Asia/Shanghai", currency="CNY", provenance=provenance
    )
    data = InventoryInput(
        source=source,
        now=spec["clock"],
        complete=True,
        products=tuple(
            Product.model_validate({**r, "source": provenance})
            for r in expected["expected"]["products"]
        ),
        order_lines=tuple(
            OrderLine.model_validate({**r, "source": provenance})
            for r in expected["expected"]["order_lines"]
        ),
        refunds=(),
        inventories=tuple(
            Inventory.model_validate(
                {**r, "source": provenance, "observed_at": spec["clock"], "source_version": None}
            )
            for r in expected["expected"]["inventories"]
        ),
    )
    report = analyze_inventory(data)
    golden = positive_golden(spec, mapping)
    assert report.complete and report.source_complete and report.requires_review
    assert report.candidate_count == 4 and not report.scope_required
    expected_rows = {r["sku_key"]: r for r in golden["facts"]}
    for fact in report.items:
        row = expected_rows[fact.sku_key]
        assert fact.suggested_units == row["suggested_units"] and fact.T == row["T"]
        assert fact.required_assumptions == tuple(row["required_assumptions"])
        assert not fact.hard_blocks and fact.inbound_units is None
    assert sum(f.suggested_units or 0 for f in report.items) == 219


@pytest.mark.parametrize("filename", ["seed-spec.private.json", "compose.env"])
def test_bound_private_input_refuses_symlinks_permissions_and_oversize(
    tmp_path: Path,
    filename: str,
) -> None:
    directory, config = bound_directory(tmp_path)
    target = directory / filename
    raw = target.read_bytes()
    target.chmod(0o644)
    with pytest.raises(ProfileFailure, match="PROFILE_FILE"):
        read_bound_spec(ROOT, config, directory)
    target.chmod(0o600)
    target.unlink()
    target.symlink_to(tmp_path / "never-consumed-other-config")
    with pytest.raises(OSError):
        read_bound_spec(ROOT, config, directory)
    target.unlink()
    lab.write_private(target, b"x" * 2097153)
    with pytest.raises(ProfileFailure, match="PROFILE_FILE"):
        read_bound_spec(ROOT, config, directory)
    lab.write_private(target, raw)
    assert read_bound_spec(ROOT, config, directory)["profile"] == POSITIVE


def test_invalid_prepare_fails_before_network_or_resource_preparation(
    monkeypatch: MP,
) -> None:
    def forbidden() -> list[str]:
        raise AssertionError("resource preflight must not run for an invalid profile")

    monkeypatch.setattr(lab, "available_subnets", forbidden)
    with pytest.raises(lab.LabFailure, match="PROFILE_REQUIRED"):
        lab.prepare("positive-v1")
    with pytest.raises(lab.LabFailure, match="MIXED_PROFILE_ARGUMENTS"):
        lab.prepare("mixed-v1", "2000-01-01")


def test_corrupt_spec_blocks_start_but_owner_cleanup_metadata_is_loadable(
    tmp_path: Path,
    monkeypatch: MP,
) -> None:
    parent = tmp_path / "runtime"
    parent.mkdir()
    directory, config = bound_directory(parent)
    fixtures = tmp_path / "tests/fixtures/woocommerce-local"
    fixtures.mkdir(parents=True)
    for name in ["seed.json", "positive.json"]:
        (fixtures / name).write_bytes(
            (ROOT / "tests/fixtures/woocommerce-local" / name).read_bytes()
        )
    config.update(schema="woo-local-lab-v1", checkout=str(tmp_path), url="https://localhost:18443")
    lab.write_private(directory / "lab.json", config)
    lab.write_private(directory / "seed-spec.private.json", b"{}")
    monkeypatch.setattr(lab, "ROOT", tmp_path)
    with pytest.raises(lab.LabFailure, match="SPEC_MISMATCH"):
        lab.load(directory)
    assert lab.load(directory, validate_profile=False)["project"] == directory.name
