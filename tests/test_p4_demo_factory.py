"""既有20SKU collector逐SKU金标/全unknown集合与原known_inbound无交叉pool。"""

import asyncio

import pytest
from commerceops.application.commerce.analysis_task import InventoryTaskRequest
from commerceops.application.commerce.inventory_analysis import analyze_inventory
from commerceops.domain.inventory_rules import RuleParameters

from tests.e2e.web.live_item_worker import twenty
from tests.p4_demo_factory import M1DemoFactory

pytestmark = pytest.mark.offline


def test_same_reviewed_twenty_source_report_each_sku_quantity_and_full_assumption_set() -> None:
    factory = M1DemoFactory()
    request = InventoryTaskRequest()
    selected = asyncio.run(factory(request).collect())
    original = asyncio.run(twenty(request).collect())
    assert selected.data.model_dump() == original.data.model_dump()
    a, b = (analyze_inventory(c.data, RuleParameters()) for c in (selected, original))
    assert a.model_dump() == b.model_dump()
    assert len(a.items) == 20
    assert all(i.suggested_units == 100 for i in a.items)
    assert sum(i.suggested_units or 0 for i in a.items) == 2000
    assert sum(i.inbound_units is None for i in a.items) == 1


def test_original_private_known_inbound_remains_one_sku_and_disjoint_group_pools() -> None:
    factory = M1DemoFactory()
    private = asyncio.run(factory(InventoryTaskRequest(fixture_case="known_inbound")).collect())
    group = asyncio.run(factory(InventoryTaskRequest()).collect())
    report = analyze_inventory(private.data, RuleParameters())
    assert len(report.items) == 1 and report.items[0].suggested_units == 70
    assert {i.stock_pool_key for i in private.data.inventories}.isdisjoint(
        i.stock_pool_key for i in group.data.inventories
    )
