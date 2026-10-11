"""p4-v1共享投影DTO与B adapter Protocol候选；Root独审后跨线冻结。"""

from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

P4_SCHEMA: Literal["p4-v1"] = "p4-v1"
MAX_ATTEMPTS = 3
IM_DEDUPE_SECONDS = 3600
BASE_FIELDS = (
    "CommerceOpsItemID",
    "TaskID",
    "SKU",
    "Quantity",
    "Risk",
    "Window",
    "SourceMode",
    "ApprovalStatus",
    "ApprovedBy",
    "BusinessStatus",
    "ResolutionReason",
    "ResolvedBy",
    "ResolvedAt",
    "SyncVersion",
    "UpdatedAt",
)


class Contract(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)


class ItemProjection(Contract):
    item_id: UUID
    task_id: UUID
    sku: str = Field(min_length=1, max_length=300)
    quantity: int = Field(gt=0)
    risk: str = Field(min_length=1, max_length=100)
    window: str = Field(min_length=1, max_length=300)
    source_mode: Literal["mock"]
    approval_status: Literal["approved"]
    approved_by: str = Field(min_length=1, max_length=300)
    business_status: Literal["open", "completed", "closed"]
    resolution_reason: str | None = Field(default=None, min_length=1, max_length=1000)
    resolved_by: str | None = Field(default=None, min_length=1, max_length=300)
    resolved_at: datetime | None = None
    sync_version: int = Field(ge=1)
    updated_at: datetime

    @model_validator(mode="after")
    def valid_terminal(self) -> "ItemProjection":
        resolution = (self.resolution_reason, self.resolved_by, self.resolved_at)
        if self.business_status == "open":
            if any(value is not None for value in resolution):
                raise ValueError("INVALID_PROJECTION")
        elif any(value is None for value in resolution):
            raise ValueError("INVALID_PROJECTION")
        if self.resolution_reason is not None and not self.resolution_reason.strip():
            raise ValueError("INVALID_PROJECTION")
        for value in (self.updated_at, self.resolved_at):
            if value is not None and value.utcoffset() is None:
                raise ValueError("INVALID_PROJECTION")
        return self

    def fields(self) -> dict[str, str | int]:
        """v1全15列为文本/整数；空终态字段用空文本，避免额外平台人员权限。"""
        return dict(
            zip(
                BASE_FIELDS,
                (
                    str(self.item_id),
                    str(self.task_id),
                    self.sku,
                    self.quantity,
                    self.risk,
                    self.window,
                    self.source_mode,
                    self.approval_status,
                    self.approved_by,
                    self.business_status,
                    self.resolution_reason or "",
                    self.resolved_by or "",
                    self.resolved_at.isoformat() if self.resolved_at else "",
                    self.sync_version,
                    self.updated_at.isoformat(),
                ),
                strict=True,
            )
        )


class ProjectionRequest(Contract):
    schema_version: Literal["p4-v1"] = P4_SCHEMA
    outbox_id: UUID
    organization_id: UUID
    shop_id: UUID
    target_key: str = Field(min_length=1, max_length=100, repr=False)
    operation: Literal["create", "update", "reconcile"]
    client_token: UUID
    external_id: str | None = Field(default=None, min_length=1, max_length=256, repr=False)
    projection: ItemProjection
    # 整个operation含完整分页的绝对总deadline，不能逐页/SDK请求重置。
    timeout_seconds: int = Field(default=10, ge=1, le=10)
    max_pages: int = Field(default=100, ge=1, le=100)

    @model_validator(mode="after")
    def valid_operation(self) -> "ProjectionRequest":
        if self.client_token.version != 4:
            raise ValueError("INVALID_PROJECTION")
        if (self.operation == "update" and self.external_id is None) or (
            self.operation == "create" and self.external_id is not None
        ):
            raise ValueError("INVALID_PROJECTION")
        return self


class ProjectionResult(Contract):
    outcome: Literal["verified", "retryable", "unknown", "conflict", "fatal", "stale"]
    code: str = Field(pattern="^[A-Z][A-Z0-9_]{0,79}$")
    external_id: str | None = Field(default=None, min_length=1, max_length=256, repr=False)
    observed_version: int | None = Field(default=None, ge=1)
    retry_after_seconds: int | None = Field(default=None, ge=1, le=300)
    write_rejected: bool = False
    complete: bool = False
    matched_count: int = Field(default=0, ge=0)
    content_matches: bool = False

    @model_validator(mode="after")
    def verified_requires_readback(self) -> "ProjectionResult":
        if self.outcome == "verified" and not (
            self.external_id
            and self.observed_version is not None
            and self.complete
            and self.matched_count == 1
            and self.content_matches
        ):
            raise ValueError("UNVERIFIED_PROJECTION")
        if self.outcome == "retryable" and not self.write_rejected:
            raise ValueError("WRITE_OUTCOME_UNPROVEN")
        if self.outcome != "retryable" and self.retry_after_seconds is not None:
            raise ValueError("INVALID_PROJECTION_RESULT")
        return self


class BaseProjectionAdapter(Protocol):
    """B只执行一次有界transport操作/完整读回；A唯一Worker协调调用。"""

    async def project(self, request: ProjectionRequest) -> ProjectionResult: ...
