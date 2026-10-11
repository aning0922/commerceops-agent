"""显式批准的原Base意图恢复绑定；不授予新任务、执行或发送键。"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RecoveryProjection(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)

    outbox_id: UUID
    item_id: UUID
    client_token: UUID
    version: Literal[1, 2]
    projection_hash: str = Field(pattern="^[a-f0-9]{64}$")
    request_hash: str = Field(pattern="^[a-f0-9]{64}$")


class ApprovedOutboxRecovery(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)

    schema_version: Literal["p4-approved-outbox-v1"]
    worker_window_id: UUID
    gateway_window_id: UUID
    expires_at: datetime
    original_gateway_id: UUID
    original_gateway_hash: str = Field(pattern="^[a-f0-9]{64}$")
    gateway_termination_id: UUID
    worker_owner: UUID
    worker_termination_id: UUID
    original_sdk_window_id: UUID
    original_sdk_window_hash: str = Field(pattern="^[a-f0-9]{64}$")
    task_id: UUID
    task_version: int = Field(ge=1)
    inbox_id: UUID
    receipt_hash: str = Field(pattern="^[a-f0-9]{64}$")
    plan_id: UUID
    plan_version: int = Field(ge=1)
    plan_hash: str = Field(pattern="^[a-f0-9]{64}$")
    approval_id: UUID
    decision_id: UUID
    execution_id: UUID
    operator_auth_version: int = Field(ge=1)
    approver_auth_version: int = Field(ge=1)
    target_key: str = Field(min_length=1, max_length=100, repr=False)
    projections: tuple[RecoveryProjection, ...] = Field(min_length=1, max_length=2, repr=False)

    @model_validator(mode="after")
    def original_pair(self) -> "ApprovedOutboxRecovery":
        if (
            self.expires_at.utcoffset() is None
            or self.original_gateway_id == self.gateway_window_id
            or tuple(p.version for p in self.projections) not in ((1,), (1, 2))
            or len({p.item_id for p in self.projections}) != 1
            or len({p.outbox_id for p in self.projections}) != len(self.projections)
            or len({p.client_token for p in self.projections}) != len(self.projections)
        ):
            raise ValueError("P4_RECOVERY_ORIGINAL_PAIR_REQUIRED")
        return self
