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


class ExplicitRORecheck(BaseModel):
    """一次人工只读对账绑定最近已终止reader；不重标自动attempts。"""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)

    recheck_count: Literal[1]
    reader_gateway: SenderGatewayLineage
    reader_window_id: UUID
    reader_window_hash: str = Field(pattern="^[a-f0-9]{64}$")
    reader_claim_hash: str = Field(pattern="^[a-f0-9]{64}$")
    reader_owner: UUID
    reader_termination_id: UUID


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
    explicit_ro_recheck: ExplicitRORecheck | None = None

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
        if self.explicit_ro_recheck is not None:
            reader = self.explicit_ro_recheck
            if (
                self.sender_gateway is None
                or tuple(p.version for p in self.projections) != (1,)
                or reader.reader_owner == self.worker_owner
                or reader.reader_window_id in (self.original_sdk_window_id, self.worker_window_id)
                or reader.reader_gateway.gateway_id
                in (
                    self.original_gateway_id,
                    self.sender_gateway.gateway_id,
                    self.gateway_window_id,
                )
            ):
                raise ValueError("P4_EXPLICIT_RO_RECHECK_LINEAGE_REQUIRED")
        return self


class TerminalRecovery(BaseModel):
    """已结束且SDK update0的原unknown/attempt1；只授权独立一次恢复。"""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)

    recovery_count: int = Field(ge=1, le=1)
    failed_window_id: UUID
    failed_window_hash: str = Field(pattern="^[a-f0-9]{64}$")
    failed_sdk_window_hash: str = Field(pattern="^[a-f0-9]{64}$")
    failed_ledger_hash: str = Field(pattern="^[a-f0-9]{64}$")
    failed_delivery_hash: str = Field(pattern="^[a-f0-9]{64}$")
    failed_gateway_hash: str = Field(pattern="^[a-f0-9]{64}$")
    failed_gateway_termination_id: UUID
    failed_worker_owner: UUID
    failed_worker_termination_id: UUID


class ApprovedTerminalUpdate(BaseModel):
    """已核实原v1锚至原生T6 v2；不授权重读v1、create或工作流恢复。"""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)

    schema_version: Literal["p4-terminal-update-v1"]
    worker_window_id: UUID
    gateway_window_id: UUID
    expires_at: datetime
    verified_recovery: "ApprovedOutboxRecovery | VerifiedQueuedV1" = Field(
        repr=False, discriminator="schema_version"
    )
    verified_sdk_window_hash: str = Field(pattern="^[a-f0-9]{64}$")
    verified_gateway_hash: str = Field(pattern="^[a-f0-9]{64}$")
    verified_gateway_termination_id: UUID
    verified_worker_owner: UUID
    verified_worker_termination_id: UUID
    external_id: str = Field(min_length=1, max_length=200, repr=False)
    projection: RecoveryProjection = Field(repr=False)
    request_key: UUID
    semantic_hash: str = Field(pattern="^[a-f0-9]{64}$")
    resolution_id: UUID
    resolver_id: UUID
    resolver_identity_id: UUID
    resolver_auth_version: int = Field(ge=1)
    recovery_of: TerminalRecovery | None = Field(
        default=None, repr=False, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def terminal_pair(self) -> "ApprovedTerminalUpdate":
        original = self.verified_recovery
        if (
            self.expires_at.utcoffset() is None
            or isinstance(original, ApprovedOutboxRecovery)
            and (original.sender_gateway is None or original.explicit_ro_recheck is None)
            or self.worker_window_id == original.worker_window_id
            or self.gateway_window_id == original.gateway_window_id
            or isinstance(original, VerifiedQueuedV1)
            and self.gateway_window_id == original.original_gateway_id
            or self.projection.version != 2
            or self.projection.item_id != original.projections[0].item_id
            or self.projection.outbox_id == original.projections[0].outbox_id
            or self.projection.client_token == original.projections[0].client_token
            or self.recovery_of is not None
            and (
                not isinstance(original, VerifiedQueuedV1)
                or self.recovery_of.failed_window_id
                in (self.worker_window_id, original.worker_window_id)
            )
        ):
            raise ValueError("P4_TERMINAL_UPDATE_BINDING_REQUIRED")
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


class ApprovedQueuedStart(BaseModel):
    """原 T1 已提交、从未启动 Worker；独立一次接续，不伪造旧 SDK/Worker。"""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)

    schema_version: Literal["p4-approved-queued-start-v1"]
    worker_window_id: UUID
    gateway_window_id: UUID
    expires_at: datetime
    original_gateway_id: UUID
    original_gateway_hash: str = Field(pattern="^[a-f0-9]{64}$")
    gateway_termination_id: UUID
    task_id: UUID
    source_task_id: UUID
    task_version: int = Field(ge=1, le=1)
    task_binding_hash: str = Field(pattern="^[a-f0-9]{64}$")
    source_binding_hash: str = Field(pattern="^[a-f0-9]{64}$")
    job_ids: tuple[UUID, UUID]
    jobs_binding_hash: str = Field(pattern="^[a-f0-9]{64}$")
    inbox_id: UUID
    receipt_hash: str = Field(pattern="^[a-f0-9]{64}$")
    operator_auth_version: int = Field(ge=1)
    target_key: str = Field(min_length=1, max_length=100, repr=False)

    @model_validator(mode="after")
    def queued_pair(self) -> "ApprovedQueuedStart":
        if (
            self.expires_at.utcoffset() is None
            or self.original_gateway_id == self.gateway_window_id
            or self.worker_window_id in (self.original_gateway_id, self.gateway_window_id)
            or self.task_id == self.source_task_id
            or self.job_ids[0] == self.job_ids[1]
        ):
            raise ValueError("P4_QUEUED_START_BINDING_REQUIRED")
        return self


class VerifiedQueuedV1(BaseModel):
    """原queued窗口已真实创建并核实的单v1；不冒充explicit RO历史。"""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)

    schema_version: Literal["p4-verified-queued-v1"]
    queued_start: ApprovedQueuedStart = Field(repr=False)
    task_version: int = Field(ge=1)
    plan_id: UUID
    plan_version: int = Field(ge=1)
    plan_hash: str = Field(pattern="^[a-f0-9]{64}$")
    approval_id: UUID
    decision_id: UUID
    execution_id: UUID
    operator_auth_version: int = Field(ge=1)
    approver_auth_version: int = Field(ge=1)
    projections: tuple[RecoveryProjection, ...] = Field(min_length=1, max_length=1, repr=False)

    @model_validator(mode="after")
    def verified_pair(self) -> "VerifiedQueuedV1":
        if (
            self.projections[0].version != 1
            or self.operator_auth_version != self.queued_start.operator_auth_version
        ):
            raise ValueError("P4_VERIFIED_QUEUED_V1_BINDING_REQUIRED")
        return self

    @property
    def worker_window_id(self) -> UUID:
        return self.queued_start.worker_window_id

    @property
    def gateway_window_id(self) -> UUID:
        return self.queued_start.gateway_window_id

    @property
    def original_gateway_id(self) -> UUID:
        return self.queued_start.original_gateway_id

    @property
    def original_gateway_hash(self) -> str:
        return self.queued_start.original_gateway_hash

    @property
    def task_id(self) -> UUID:
        return self.queued_start.task_id

    @property
    def inbox_id(self) -> UUID:
        return self.queued_start.inbox_id

    @property
    def receipt_hash(self) -> str:
        return self.queued_start.receipt_hash

    @property
    def target_key(self) -> str:
        return self.queued_start.target_key


ApprovedTerminalUpdate.model_rebuild()
