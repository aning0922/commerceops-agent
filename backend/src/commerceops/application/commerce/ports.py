"""依赖倒置的五个只读端口；refund 为订单 cohort，不按退款发生日裁剪。"""

from typing import Protocol

from commerceops.application.commerce.contracts import (
    Capabilities,
    InventoryResult,
    OrderLine,
    Page,
    Product,
    Refund,
    Window,
)


class CommercePort(Protocol):
    def list_products(self, *, cursor: str | None = None) -> Page[Product]: ...

    def list_order_lines(self, window: Window, *, cursor: str | None = None) -> Page[OrderLine]: ...

    def list_refunds(
        self, order_ids: tuple[str, ...], *, cursor: str | None = None
    ) -> Page[Refund]: ...

    def get_inventory(self, sku_key: str) -> InventoryResult: ...

    def capabilities(self) -> Capabilities: ...
