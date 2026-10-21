"""单部署/单App受控SDK consumer窗口，默认关闭，非wire认证证明。"""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.application.replenishment.contracts import Parameters


def require_group_operation_scope(settings: BusinessSettings, chat_id: str) -> None:
    """Explicit operation-only group scope; never widens ordinary Gateway windows."""
    if (
        settings.allowed_group_chat_ids != frozenset({chat_id})
        or len(settings.allowed_open_ids) < 2
        or settings.f02_enabled
        or settings.external_sender_enabled
    ):
        raise PermissionError("P4_GROUP_OPERATION_SCOPE_REQUIRED")


class GatewayWindow(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)

    schema_version: Literal["p4-gateway-v1"]
    window_id: UUID
    organization_id: UUID
    shop_id: UUID
    expires_at: datetime
    max_callbacks: int = Field(default=100, ge=1, le=100)
    max_workflows: int = Field(default=5, ge=0, le=5)
    parameters: Parameters
    enabled: bool = False
    group_operation_chat_id: str | None = Field(
        default=None, min_length=1, max_length=512, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def bounded(self) -> "GatewayWindow":
        if self.expires_at.utcoffset() is None or self.parameters.source_mode != "mock":
            raise ValueError("P4_GATEWAY_WINDOW_INVALID")
        if self.group_operation_chat_id is not None and (
            self.max_workflows != 0
            or self.max_callbacks > 14
            or self.parameters.model_dump()
            != dict(
                source_mode="mock",
                dataset_version="inventory-v1",
                fixture_case="baseline",
                L=3,
                R=7,
                S=2,
            )
        ):
            raise ValueError("P4_GROUP_OPERATION_SCOPE_REQUIRED")
        return self

    def active(self, *, group_operation: bool = False) -> bool:
        if self.group_operation_chat_id is not None and not group_operation:
            return False
        limit = 600 if group_operation and self.group_operation_chat_id is not None else 300
        return self.enabled and 0 < (self.expires_at - datetime.now(UTC)).total_seconds() <= limit
