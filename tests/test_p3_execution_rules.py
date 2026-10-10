"""A03实质重观测/严格确定性纯规则；不是PG/权限/执行恢复证据。"""

import asyncio
from dataclasses import replace
from datetime import timedelta
from typing import Any

import pytest
from commerceops.application.commerce.analysis_task import InventoryTaskRequest
from commerceops.application.replenishment.execution import material_hash, verified_observation
from commerceops.domain.commerce_values import facts_hash
from commerceops.workflows.inventory_analysis import MockCollectorFactory

from tests.inventory_support import DIRECTORY

pytestmark = pytest.mark.offline
PARAMETERS = InventoryTaskRequest().model_dump(mode="json", exclude={"schema_version"})


def collected() -> Any:
    return asyncio.run(MockCollectorFactory(DIRECTORY)(InventoryTaskRequest()).collect())


def test_material_policy_preserves_all_facts_but_ignores_capture_only_and_row_order() -> None:
    original = collected()
    data = original.data
    advanced = data.now + timedelta(seconds=1)

    def provenance(p: Any) -> Any:
        return p.model_copy(
            update={"captured_at": advanced, "raw_hash": facts_hash({"capture": advanced})}
        )

    source = data.source.model_copy(update={"provenance": provenance(data.source.provenance)})
    updates: dict[str, Any] = {"source": source, "now": advanced}
    for name in ("products", "order_lines", "refunds", "inventories"):
        updates[name] = tuple(
            row.model_copy(
                update={
                    "source": provenance(row.source),
                    **({"observed_at": advanced} if name == "inventories" else {}),
                }
            )
            for row in reversed(getattr(data, name))
        )
    refreshed = data.model_copy(update=updates)
    verified_observation(replace(original, data=refreshed), PARAMETERS)
    assert material_hash(data, PARAMETERS) == material_hash(refreshed, PARAMETERS)


@pytest.mark.parametrize(
    "field,value",
    [
        ("available_stock", 21),
        ("inbound_units", 3),
        ("stock_status", "outofstock"),
        ("backorders", "notify"),
        ("source_version", "new-source-version"),
    ],
)
def test_material_stock_and_source_change_invalidates_even_when_quantity_can_coincide(
    field: str, value: Any
) -> None:
    original = collected().data
    first = original.inventories[0].model_copy(update={field: value})
    changed = original.model_copy(update={"inventories": (first, *original.inventories[1:])})
    assert material_hash(original, PARAMETERS) != material_hash(changed, PARAMETERS)


def test_material_raw_sales_change_is_not_hidden_by_equal_total_demand() -> None:
    original = collected().data
    first = original.order_lines[0]
    changed = original.model_copy(
        update={
            "order_lines": (
                first.model_copy(
                    update={"status": "completed" if first.status != "completed" else "processing"}
                ),
                *original.order_lines[1:],
            )
        }
    )
    assert material_hash(original, PARAMETERS) != material_hash(changed, PARAMETERS)
    assert material_hash(original, PARAMETERS) != material_hash(original, {**PARAMETERS, "L": 4})


def test_verified_observation_rejects_native_bool_units_before_serialization() -> None:
    original = collected()
    invalid = original.data.model_copy(
        update={
            "inventories": (
                original.data.inventories[0].model_copy(update={"available_stock": True}),
                *original.data.inventories[1:],
            )
        }
    )
    with pytest.raises(ValueError):
        verified_observation(replace(original, data=invalid), PARAMETERS)


def test_verified_observation_is_bound_to_full_input_and_deterministic_report() -> None:
    data, report, normalized = verified_observation(collected(), PARAMETERS)
    assert report.input_hash == facts_hash(normalized)
    assert report.items[0].suggested_units == 100 and report.items[0].A == 20
    assert report.L == 3 and report.R == 7 and report.S == 2 and data.complete
