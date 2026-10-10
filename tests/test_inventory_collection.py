"""有界采集、确定性金标与默认只读身份失败关闭。"""

import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest
from commerceops.adapters.commerce.mock import Behavior, Fixture, MockCommerce
from commerceops.application.commerce.analysis_task import InventoryTaskRequest
from commerceops.application.commerce.collection import InventoryCollector
from commerceops.application.commerce.contracts import Quality
from commerceops.application.commerce.inventory_analysis import analyze_inventory
from commerceops.domain.inventory_rules import RuleParameters
from commerceops.entrypoints.api import create_app
from commerceops.workflows.inventory_analysis import MockCollectorFactory
from fastapi.testclient import TestClient

pytestmark = pytest.mark.offline
DIRECTORY = Path(__file__).parent / "fixtures/commerce/inventory-v1"
GOLD = json.loads((DIRECTORY / "goldens.json").read_text())["expectations"]


@pytest.mark.parametrize("case", [key for key, g in GOLD.items() if "T" in g])
def test_collected_numeric_goldens(case: str) -> None:
    gold = GOLD[case]
    request = InventoryTaskRequest(fixture_case=case, L=gold["L"], R=gold["R"], S=gold["S"])
    collected = asyncio.run(MockCollectorFactory(DIRECTORY)(request).collect())
    report = analyze_inventory(collected.data, RuleParameters(request.L, request.R, request.S))
    actual = report.items[0].model_dump(mode="json")
    assert {key: actual[key] for key in gold} == gold
    assert collected.consistency == "observational"
    assert collected.collected_at >= collected.collection_started_at


@pytest.mark.parametrize(
    "behavior,flag,rounds",
    [
        (Behavior(duplicate_second_page=True), Quality.DUPLICATE_ID, 1),
        (Behavior(omit_second_page=True), Quality.MISSING_PAGE, 1),
        (Behavior(change_second_page=True), Quality.SOURCE_CHANGED, 2),
        (Behavior(max_pages=1), Quality.CAPACITY_LIMIT, 1),
    ],
)
def test_failure_quality_and_one_recollection(
    behavior: Behavior, flag: Quality, rounds: int
) -> None:
    f = Fixture.load(DIRECTORY)
    f = replace(f, orders=(*f.orders, f.orders[0].model_copy(update={"order_id": "owned-second"})))
    port = MockCommerce(f, page_size=1, behavior=behavior)
    data = asyncio.run(InventoryCollector(port, f.source, f.now, retry_sleep=False).collect()).data
    assert not data.complete and flag in data.warnings
    assert len(data.order_lines) == len({(r.order_id, r.line_id) for r in data.order_lines})
    assert port.call_counts["products"] == len(f.products) * rounds
    assert not analyze_inventory(data).execution_available


def test_retry_and_page_bounds() -> None:
    f = Fixture.load(DIRECTORY)
    f = replace(f, orders=(*f.orders, f.orders[0].model_copy(update={"order_id": "owned-second"})))
    port = MockCommerce(f, page_size=1, behavior=Behavior(fail_on_call=1))
    data = asyncio.run(InventoryCollector(port, f.source, f.now, retry_sleep=False).collect()).data
    assert data.complete
    bounded = asyncio.run(InventoryCollector(port, f.source, f.now, max_pages=1).collect()).data
    assert not bounded.complete and Quality.CAPACITY_LIMIT in bounded.warnings
    with pytest.raises(ValueError):
        InventoryCollector(port, f.source, f.now, max_pages=True)


def test_default_identity_fail_closed_and_openapi() -> None:
    app = create_app()
    client = TestClient(app)
    for suffix in ("", "/report", "/events"):
        response = client.get(
            "/tasks/00000000-0000-0000-0000-000000000001" + suffix,
            headers={"X-Principal": "admin", "X-Role": "operator"},
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "IDENTITY_REQUIRED"
    spec = app.openapi()
    assert spec == json.loads(
        (DIRECTORY.parents[3] / "docs/contracts/p203-read-openapi.json").read_text()
    )
    assert "422" not in spec["paths"]["/tasks/{task_id}/events"]["get"]["responses"]
    bad = client.get("/tasks/00000000-0000-0000-0000-000000000001/events?limit=raw-secret")
    assert bad.status_code == 400 and "raw-secret" not in bad.text
    assert spec["paths"]["/tasks/{task_id}/report"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"].endswith("/ReportRead")
    assert set(spec["paths"]) >= {
        "/tasks/{task_id}",
        "/tasks/{task_id}/report",
        "/tasks/{task_id}/events",
    }
