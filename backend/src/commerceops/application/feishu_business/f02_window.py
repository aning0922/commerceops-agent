"""单个持久F02回复的显式SDK窗口；默认关闭，不授权业务Graph或Base。"""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Literal
from uuid import UUID

from pydantic import Field

from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.application.feishu_business.contracts import Contract
from commerceops.application.feishu_business.sdk_calls import SDKMethod
from commerceops.application.feishu_business.sdk_window import SDKWindow

F02_CAPS: Mapping[SDKMethod, int] = MappingProxyType(
    {
        "auth.v3.tenant_access_token.internal": 1,
        "bot.v3.info": 1,
        "im.v1.message.create": 5,
    }
)


class F02WorkerWindow(Contract):
    schema_version: Literal["p4-f02-worker-window-v1"]
    window_id: UUID
    gateway_window_id: UUID
    organization_id: UUID
    shop_id: UUID
    expires_at: datetime
    enabled: bool = False
    method_caps: dict[SDKMethod, int]

    def window(self, settings: BusinessSettings) -> SDKWindow:
        checked = type(self).model_validate(self.model_dump())
        remaining = (
            (checked.expires_at - datetime.now(UTC)).total_seconds()
            if checked.expires_at.utcoffset() == timedelta(0)
            else 0
        )
        if (
            not checked.enabled
            or not settings.f02_enabled
            or not 15 < remaining <= 300
            or (checked.organization_id, checked.shop_id)
            != (settings.organization_id, settings.shop_id)
            or set(checked.method_caps) != set(F02_CAPS)
            or any(not 1 <= n <= F02_CAPS[method] for method, n in checked.method_caps.items())
            or checked.method_caps.get("auth.v3.tenant_access_token.internal") != 1
            or checked.method_caps.get("bot.v3.info") != 1
            or any(type(n) is not int for n in checked.method_caps.values())
        ):
            raise PermissionError("F02_WINDOW_CLOSED")
        return SDKWindow(
            checked.window_id,
            checked.organization_id,
            checked.shop_id,
            checked.expires_at,
            checked.method_caps,
            enabled=True,
            verification_mode="controlled_sdk",
        )


class F02Window(F02WorkerWindow):
    """由同Gateway已提交选择回执构造，不由操作者拼接业务标识。"""

    schema_version: Literal["p4-f02-window-v1"]  # type: ignore[assignment]
    request_id: UUID
    reply_id: UUID
    inbox_id: UUID
    round: int = Field(ge=1)
    payload_hash: str = Field(pattern="^[a-f0-9]{64}$")
