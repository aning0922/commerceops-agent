"""窄SDK实际方法账本接口；不含request/option/凭据/平台定位。"""

from collections.abc import Awaitable, Callable
from typing import Any, Literal, Protocol

SDKMethod = Literal[
    "auth.v3.tenant_access_token.internal",
    "bot.v3.info",
    "im.v1.message.create",
    "im.v1.message.list",
    "bitable.v1.app_table_record.create",
    "bitable.v1.app_table_record.list",
    "bitable.v1.app_table_record.update",
    "bitable.v1.app_table.list",
    "bitable.v1.app_table_field.list",
]


class SDKCallLedger(Protocol):
    async def invoke(self, method: SDKMethod, call: Callable[[], Awaitable[Any]]) -> Any: ...
