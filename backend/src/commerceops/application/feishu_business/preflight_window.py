"""一轮窄metadata窗口；公开方法cap明确，不能借此解除业务sender。"""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from commerceops.application.feishu_business.sdk_calls import SDKMethod
from commerceops.application.feishu_business.sdk_window import SDKWindow


class PreflightWindow(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)

    schema_version: Literal["p4-preflight-v1"]
    window_id: UUID
    organization_id: UUID
    shop_id: UUID
    expires_at: datetime
    caps: dict[SDKMethod, int]
    enabled: bool = False

    def window(self) -> SDKWindow:
        allowed = {
            "auth.v3.tenant_access_token.internal": 1,
            "bot.v3.info": 1,
            "bitable.v1.app_table.list": 2,
            "bitable.v1.app_table_field.list": 2,
        }
        if (
            self.expires_at.utcoffset() is None
            or not 0 < (self.expires_at - datetime.now(UTC)).total_seconds() <= 90
            or set(self.caps) - set(allowed)
            or self.caps.get("auth.v3.tenant_access_token.internal") != 1
            or self.caps.get("bot.v3.info") != 1
            or self.caps.get("bitable.v1.app_table_field.list") not in (1, 2)
            or any(
                type(value) is not int or not 1 <= value <= allowed[key]
                for key, value in self.caps.items()
            )
        ):
            raise ValueError("P4_PREFLIGHT_WINDOW_INVALID")
        return SDKWindow(
            self.window_id,
            self.organization_id,
            self.shop_id,
            self.expires_at,
            self.caps,
            enabled=self.enabled,
            verification_mode="controlled_sdk",
        )
