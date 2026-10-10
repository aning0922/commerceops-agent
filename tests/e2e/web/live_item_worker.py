"""B04独立Mock窗口薄Worker入口；同固定20 SKU用于P2与T4，业务实现全部已审。"""

import asyncio
import json
import signal
import sys
from dataclasses import replace
from pathlib import Path
from uuid import UUID

from commerceops.adapters.commerce.mock import Fixture, MockCommerce
from commerceops.application.commerce.analysis_task import InventoryTaskRequest
from commerceops.application.commerce.collection import InventoryCollector
from commerceops.domain.commerce_values import facts_hash, sku_key, stock_pool_key
from commerceops.infrastructure.explanation_repository import ExplanationStore
from commerceops.infrastructure.intent_repository import IntentStore
from commerceops.infrastructure.inventory_repository import InventoryStore
from commerceops.infrastructure.replenishment_repository import ApprovalStore
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.worker import Worker
from commerceops.infrastructure.worker_lock import WorkerSession
from commerceops.workflows.inventory_analysis import InventoryRunner
from commerceops.workflows.inventory_routing import IntentRunner
from commerceops.workflows.replenishment import ApprovalRunner
from commerceops.workflows.report_explanation import (
    ExplanationRunner,
    InventoryCompositeRunner,
    ProviderFactory,
)

from tests.e2e.web.live_origins import registered_origins
from tests.inventory_support import DIRECTORY


def twenty(request: InventoryTaskRequest) -> InventoryCollector:
    # Identical public Mock fixture provenance/rows to the approved B02/B03 seeder.
    if request.fixture_case != "baseline":
        raise ValueError("CONTROLLED_TWENTY_BASELINE_ONLY")
    baseline = Fixture.load(DIRECTORY)
    provenance = baseline.source.provenance.model_copy(
        update={
            "fixture_version": "p3b02-owned-20",
            "raw_hash": facts_hash({"controlled_fixture": "p3b02-owned-20"}),
        }
    )
    source = baseline.source.model_copy(update={"provenance": provenance})
    products, orders, inventories = [], [], []
    for n in range(20):
        product_id = "b02-" + str(n)
        key, pool = (
            sku_key(source.shop_id, product_id, None),
            stock_pool_key(source.shop_id, product_id),
        )
        products.append(
            baseline.products[0].model_copy(
                update={
                    "product_id": product_id,
                    "sku_key": key,
                    "stock_pool_key": pool,
                    "source": provenance,
                    "sku_label": "完整披露中文商品名称用于验证窄屏换行与未知在途风险" + str(n),
                }
            )
        )
        orders.append(
            baseline.orders[0].model_copy(
                update={"order_id": "b02-order-" + str(n), "sku_key": key, "source": provenance}
            )
        )
        inventories.append(
            baseline.inventories[0].model_copy(
                update={
                    "sku_key": key,
                    "stock_pool_key": pool,
                    "source": provenance,
                    "inbound_units": None if n == 19 else baseline.inventories[0].inbound_units,
                    "inbound_quality": "unknown" if n == 19 else "reliable",
                    "inbound_reason": "UNKNOWN_INBOUND" if n == 19 else None,
                }
            )
        )
    controlled = replace(
        baseline,
        source=source,
        products=tuple(products),
        orders=tuple(orders),
        inventories=tuple(inventories),
    )
    return InventoryCollector(MockCommerce(controlled), source, baseline.now)


async def serve(directory: Path) -> None:
    registered_origins(directory)
    config = WebConfig.from_file(directory / "configuration.json")
    facts = json.loads((directory / "b04-facts.json").read_text())
    stop = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    session = WorkerSession(config.database, UUID(facts["organization"]))
    await session.start()
    approval = ApprovalRunner(ApprovalStore(config, session), collector_factory=twenty)
    provider = ProviderFactory()  # template only; no key file/actual permission.
    runner = InventoryCompositeRunner(
        InventoryRunner(InventoryStore(config.database, session), twenty),
        ExplanationRunner(ExplanationStore(config.database, session), provider),
        IntentRunner(IntentStore(config.database, session), provider),
        approval,
    )
    await Worker(
        session,
        runner,
        reconcile=approval.reconcile,
        recovery_scan_seconds=config.recovery_scan_seconds,
    ).run(stop)


if __name__ == "__main__":
    try:
        asyncio.run(serve(Path(sys.argv[1])))
    except Exception as error:
        print(json.dumps({"stage": "B04 owned worker", "category": type(error).__name__}))
        raise SystemExit(2) from None
