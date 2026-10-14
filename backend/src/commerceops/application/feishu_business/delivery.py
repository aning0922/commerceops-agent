"""A持久投影协调规则：原快照/原键及历史验证不得替当前版本同步。"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from commerceops.application.feishu_business.contracts import (
    ProjectionRequest,
    ProjectionResult,
    bind_projection_result,
)
from commerceops.application.feishu_business.recovery import RecoveryProjection


@dataclass(frozen=True)
class DeliveryGate:
    organization_id: UUID
    shop_id: UUID
    task_ids: frozenset[UUID]
    target_key: str = field(repr=False)
    expires_at: datetime
    enabled: bool = False
    verification_mode: Literal["offline_fake", "controlled_sdk"] = "offline_fake"
    outbox_ids: frozenset[UUID] | None = None
    first_create: RecoveryProjection | None = None
    first_create_window_id: UUID | None = None
    explicit_ro_window_id: UUID | None = None

    def __post_init__(self) -> None:
        if (
            not self.target_key
            or len(self.target_key) > 100
            or not self.task_ids
            or len(self.task_ids) > 5
            or self.expires_at.utcoffset() is None
            or type(self.enabled) is not bool
            or self.verification_mode not in ("offline_fake", "controlled_sdk")
            or self.outbox_ids is not None
            and (not self.outbox_ids or len(self.outbox_ids) > 2)
            or (self.first_create is None) != (self.first_create_window_id is None)
            or self.first_create is not None
            and (
                self.first_create.version != 1
                or len(self.task_ids) != 1
                or self.verification_mode != "controlled_sdk"
                or self.outbox_ids is not None
            )
            or self.explicit_ro_window_id is not None
            and (
                self.first_create is not None
                or self.verification_mode != "controlled_sdk"
                or self.outbox_ids is None
                or len(self.outbox_ids) != 1
                or len(self.task_ids) != 1
            )
        ):
            raise ValueError("INVALID_P4_DELIVERY_GATE")

    def active(self) -> bool:
        return self.enabled and datetime.now(UTC) < self.expires_at


@dataclass(frozen=True)
class DeliveryDisposition:
    status: Literal["verified", "pending", "unknown", "conflict", "fatal", "stale"]
    code: str
    # 只允许全15字段/原版本完整唯一读回的record产生稳定锚；无HTTP猜测。
    anchor: str | None = field(default=None, repr=False)
    observed_version: int | None = None
    current_synced: bool = False
    delay_seconds: int = 30


def disposition(
    request: ProjectionRequest,
    result: ProjectionResult,
    *,
    current_version: int,
    attempts: int,
) -> DeliveryDisposition:
    request = ProjectionRequest.model_validate(request.model_dump())
    if type(current_version) is not int or current_version < request.projection.sync_version:
        raise ValueError("INVALID_CURRENT_PROJECTION_VERSION")
    if type(attempts) is not int or not 1 <= attempts <= 3:
        raise ValueError("INVALID_PROJECTION_ATTEMPTS")
    result = bind_projection_result(request, ProjectionResult.model_validate(result.model_dump()))
    if result.outcome == "verified":
        return DeliveryDisposition(
            "verified",
            result.code,
            result.external_id,
            result.observed_version,
            current_version == request.projection.sync_version,
        )
    if result.outcome == "retryable":
        # 已知无写只允许写请求本身有限重试；未知后的读回无行不能复活原create。
        if request.operation == "reconcile":
            return DeliveryDisposition("unknown", "UNKNOWN_WRITE_HELD")
        return DeliveryDisposition(
            "pending" if attempts < 3 else "fatal",
            result.code if attempts < 3 else "RETRY_BUDGET_EXHAUSTED",
            delay_seconds=result.retry_after_seconds or 30,
        )
    return DeliveryDisposition(
        result.outcome, result.code, observed_version=result.observed_version
    )


def next_operation(
    *,
    status: str,
    version: int,
    anchor: str | None,
    attempts: int,
) -> Literal["create", "update", "reconcile"] | None:
    if type(version) is not int or version not in (1, 2):
        raise ValueError("INVALID_ORIGINAL_PROJECTION_VERSION")
    if type(attempts) is not int or not 0 <= attempts <= 3:
        raise ValueError("INVALID_PROJECTION_ATTEMPTS")
    if status in {"verified", "conflict", "fatal", "stale"} or attempts >= 3:
        return None
    if status == "unknown":
        return "reconcile"  # 任何年龄均不create/update；不依赖IM一小时UUID窗。
    if status != "pending":
        return None
    if version == 1 and anchor is None:
        return "create"
    if version > 1 and anchor is not None:
        return "update"
    return None  # v2无v1锚时必须等待/关注，不能重新create或假定记录不存在。
