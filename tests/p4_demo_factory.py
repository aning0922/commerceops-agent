"""P4受控演示的既有fixture选择；P2/T2/T4共同注入，不参与生产CLI。"""

from commerceops.application.commerce.analysis_task import InventoryTaskRequest
from commerceops.application.commerce.collection import InventoryCollector
from commerceops.workflows.inventory_analysis import MockCollectorFactory

from tests.e2e.web.live_item_worker import twenty
from tests.inventory_support import DIRECTORY


class M1DemoFactory:
    def __init__(self) -> None:
        self.original = MockCollectorFactory(DIRECTORY)

    def __call__(self, request: InventoryTaskRequest) -> InventoryCollector:
        if request.fixture_case == "baseline":
            return twenty(request)
        return self.original(request)
