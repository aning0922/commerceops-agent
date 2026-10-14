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


class SenderGatewayLineage(BaseModel):
    """后续首写者的真实Gateway；不替代原入站来源。"""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)

    gateway_id: UUID
    gateway_hash: str = Field(pattern="^[a-f0-9]{64}$")
    termination_id: UUID


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
    sender_gateway: SenderGatewayLineage | None = None

    @model_validator(mode="after")
    def original_pair(self) -> "ApprovedOutboxRecovery":
        if (
            self.expires_at.utcoffset() is None
            or self.original_gateway_id == self.gateway_window_id
            or tuple(p.version for p in self.projections) not in ((1,), (1, 2))
            or len({p.item_id for p in self.projections}) != 1
            or len({p.outbox_id for p in self.projections}) != len(self.projections)
            or len({p.client_token for p in self.projections}) != len(self.projections)
            or self.sender_gateway is not None
            and (
                tuple(p.version for p in self.projections) != (1,)
                or self.sender_gateway.gateway_id
                in (self.original_gateway_id, self.gateway_window_id)
            )
        ):
            raise ValueError("P4_RECOVERY_ORIGINAL_PAIR_REQUIRED")
        return self


class ApprovedWorkflowRecovery(BaseModel):
    """单个原在途 workflow 的显式跨 Gateway 接续；不是新 T1 或重开审批。"""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)

    schema_version: Literal["p4-approved-workflow-v1"]
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
    task_binding_hash: str = Field(pattern="^[a-f0-9]{64}$")
    inbox_id: UUID
    receipt_hash: str = Field(pattern="^[a-f0-9]{64}$")
    operator_auth_version: int = Field(ge=1)
    approval_id: UUID | None
    approval_binding_hash: str | None = Field(pattern="^[a-f0-9]{64}$")
    decision_id: UUID | None
    decision_payload_hash: str | None = Field(pattern="^[a-f0-9]{64}$")
    execution_id: UUID | None
    target_key: str = Field(min_length=1, max_length=100, repr=False)

    @model_validator(mode="after")
    def bound_original(self) -> "ApprovedWorkflowRecovery":
        if (
            self.expires_at.utcoffset() is None
            or self.original_gateway_id == self.gateway_window_id
            or self.original_sdk_window_id == self.worker_window_id
            or (self.approval_id is None) != (self.approval_binding_hash is None)
            or (self.decision_id is None) != (self.decision_payload_hash is None)
            or self.approval_id is None
            and self.decision_id is not None
            or self.decision_id is None
            and self.execution_id is not None
        ):
            raise ValueError("P4_WORKFLOW_RECOVERY_BINDING_REQUIRED")
        return self
