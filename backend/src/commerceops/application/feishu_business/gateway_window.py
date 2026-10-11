"""单部署/单App受控SDK consumer窗口，默认关闭，非wire认证证明。"""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from commerceops.application.replenishment.contracts import Parameters


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

    @model_validator(mode="after")
    def bounded(self) -> "GatewayWindow":
        if self.expires_at.utcoffset() is None or self.parameters.source_mode != "mock":
            raise ValueError("P4_GATEWAY_WINDOW_INVALID")
        return self

    def active(self) -> bool:
        return self.enabled and 0 < (self.expires_at - datetime.now(UTC)).total_seconds() <= 300
