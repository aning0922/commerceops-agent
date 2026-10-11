"""同原Gateway/显式任务白名单的正式SDK Worker窗口；默认关闭。"""

from collections.abc import Mapping
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.application.feishu_business.recovery import ApprovedOutboxRecovery
from commerceops.application.feishu_business.sdk_calls import SDKMethod
from commerceops.application.feishu_business.sdk_window import SDKWindow

KNOWN70_CAPS: Mapping[SDKMethod, int] = MappingProxyType(
    {
        "auth.v3.tenant_access_token.internal": 1,
        "bot.v3.info": 1,
        "bitable.v1.app_table.list": 2,
        "bitable.v1.app_table_field.list": 2,
        "im.v1.message.create": 2,
        "bitable.v1.app_table_record.create": 1,
        "bitable.v1.app_table_record.update": 1,
        "bitable.v1.app_table_record.list": 4,
    }
)

# 单页原适配器实际调用预算；分页/错误额外调用仍计数，耗尽即停止。
GROUP20_CAPS: Mapping[SDKMethod, int] = MappingProxyType(
    {
        **KNOWN70_CAPS,
        "im.v1.message.create": 4,
        "bitable.v1.app_table_record.create": 20,
        "bitable.v1.app_table_record.update": 1,
        "bitable.v1.app_table_record.list": 42,
    }
)
RECOVERY_CAPS: Mapping[SDKMethod, int] = MappingProxyType(
    {
        "auth.v3.tenant_access_token.internal": 1,
        "bot.v3.info": 1,
        "bitable.v1.app_table.list": 2,
        "bitable.v1.app_table_field.list": 2,
        "bitable.v1.app_table_record.update": 1,
        "bitable.v1.app_table_record.list": 4,
    }
)


class ControlledWorkerWindow(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)

    schema_version: Literal["p4-worker-v1"]
    window_id: UUID
    gateway_window_id: UUID
    organization_id: UUID
    shop_id: UUID
    task_ids: frozenset[UUID] = Field(min_length=1, max_length=5, repr=False)
    expires_at: datetime
    caps: dict[SDKMethod, int] = Field(repr=False)
    enabled: bool = False
    profile: Literal["known70", "group20", "approved_outbox"] = "known70"
    recovery: ApprovedOutboxRecovery | None = Field(default=None, repr=False)

    def window(self, settings: BusinessSettings) -> SDKWindow:
        checked = type(self).model_validate(self.model_dump())
        ceilings = {
            "known70": KNOWN70_CAPS,
            "group20": GROUP20_CAPS,
            "approved_outbox": RECOVERY_CAPS,
        }[checked.profile]
        remaining = (
            (checked.expires_at - datetime.now(UTC)).total_seconds()
            if checked.expires_at.utcoffset() is not None
            else 0
        )
        if (
            self.expires_at.utcoffset() is None
            or not 15 < remaining <= 300
            or not self.enabled
            or (self.organization_id, self.shop_id) != (settings.organization_id, settings.shop_id)
            or set(self.caps) - set(ceilings)
            or any(
                type(value) is not int or not 1 <= value <= ceilings[method]
                for method, value in self.caps.items()
            )
            or self.caps.get("auth.v3.tenant_access_token.internal") != 1
            or self.caps.get("bot.v3.info") != 1
            or self.caps.get("bitable.v1.app_table_field.list") not in (1, 2)
            or self.caps.get("bitable.v1.app_table.list", 0) not in (0, 1, 2)
            or settings.base_table_id_file is None
            and self.caps.get("bitable.v1.app_table.list", 0) == 0
            or self.profile != "approved_outbox"
            and (
                self.caps.get("im.v1.message.create", 0) < 1
                or self.caps.get("bitable.v1.app_table_record.create", 0) < 1
            )
            or self.caps.get("bitable.v1.app_table_record.list", 0) < 2
            or self.profile == "group20"
            and len(self.task_ids) > 2
            or self.profile != "approved_outbox"
            and self.recovery is not None
            or self.profile == "approved_outbox"
            and (
                self.recovery is None
                or self.task_ids != frozenset({self.recovery.task_id})
                or self.recovery.worker_window_id != self.window_id
                or self.recovery.gateway_window_id != self.gateway_window_id
                or self.recovery.expires_at != self.expires_at
                or self.recovery.target_key != settings.base_target_key
            )
        ):
            raise PermissionError("P4_CONTROLLED_WORKER_WINDOW_CLOSED")
        return SDKWindow(
            self.window_id,
            self.organization_id,
            self.shop_id,
            self.expires_at,
            self.caps,
            enabled=True,
            verification_mode="controlled_sdk",
        )
