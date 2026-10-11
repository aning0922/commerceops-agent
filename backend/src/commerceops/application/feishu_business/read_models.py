"""安全Web投影/运行Gate/工具事实机器约束；不返回平台定位或凭据。"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from commerceops.application.feishu_business.contracts import Contract

VerificationMode = Literal["offline_fake", "controlled_sdk"]


class SenderGateRead(Contract):
    destination_alias: Literal["IM", "Base"]
    sender_enabled: bool
    reason_code: Literal[
        "NOT_CONFIGURED",
        "DISABLED_BY_CONFIGURATION",
        "WINDOW_EXPIRED",
        "WORKER_NOT_READY",
        "CONTROLLED_WINDOW_ACTIVE",
    ]
    verification_mode: VerificationMode | None
    as_of: datetime
    worker_ready: bool | None

    @model_validator(mode="after")
    def gate_facts(self) -> "SenderGateRead":
        if self.sender_enabled != (self.reason_code == "CONTROLLED_WINDOW_ACTIVE"):
            raise ValueError("INVALID_SENDER_GATE_FACT")
        if self.sender_enabled and self.verification_mode is None:
            raise ValueError("INVALID_SENDER_GATE_FACT")
        if self.as_of.utcoffset() is None:
            raise ValueError("INVALID_SENDER_GATE_TIME")
        return self


class ProjectionRead(Contract):
    outbox_id: UUID
    aggregate_id: UUID
    projection_version: int = Field(ge=1)
    outbox_status: Literal["blocked", "pending", "sending", "sent", "retry_wait", "unknown", "dead"]
    state: Literal["not_requested", "pending", "synced", "failed", "unknown"]
    source_mode: Literal["mock", "controlled_stub"]
    destination_alias: Literal["IM", "Base"]
    target_version: int = Field(ge=1)
    observed_version: int | None = Field(ge=1)
    complete_unique_verified: bool
    is_current_version: bool
    attempts: int = Field(ge=0)
    verification_mode: VerificationMode | None
    as_of: datetime
    error_code: str | None = Field(pattern="^[A-Z][A-Z0-9_]{0,79}$")

    @model_validator(mode="after")
    def original_and_current_version(self) -> "ProjectionRead":
        if self.is_current_version != (self.projection_version == self.target_version):
            raise ValueError("INVALID_CURRENT_PROJECTION_FACT")
        if self.complete_unique_verified and self.observed_version != self.projection_version:
            raise ValueError("INVALID_OBSERVED_PROJECTION_FACT")
        if self.as_of.utcoffset() is None:
            raise ValueError("INVALID_PROJECTION_TIME")
        return self


class ToolFactRead(Contract):
    category: Literal["deterministic", "sdk_adapter", "commerce_query", "sdk_method", "model"]
    name: str = Field(min_length=1, max_length=256)
    selected_by_model: bool
    sdk_method: (
        Literal[
            "im.v1.message.create",
            "bitable.v1.app_table_record.create",
            "bitable.v1.app_table_record.list",
            "bitable.v1.app_table_record.update",
        ]
        | None
    )
    verification_mode: VerificationMode | None

    @model_validator(mode="after")
    def no_invented_model_or_method(self) -> "ToolFactRead":
        if (self.category == "sdk_method") != (self.sdk_method is not None):
            raise ValueError("INVALID_SDK_METHOD_FACT")
        if self.category != "model" and self.selected_by_model:
            raise ValueError("INVALID_MODEL_SELECTION_FACT")
        return self
