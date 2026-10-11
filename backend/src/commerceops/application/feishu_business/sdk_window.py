"""显式有界SDK窗口与安全调用scope；默认关闭，非wire证明或业务授权替代。"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType
from uuid import UUID

from commerceops.application.feishu_business.sdk_calls import SDKMethod

METHODS: frozenset[str] = frozenset(
    {
        "auth.v3.tenant_access_token.internal",
        "bot.v3.info",
        "im.v1.message.create",
        "bitable.v1.app_table_record.create",
        "bitable.v1.app_table_record.list",
        "bitable.v1.app_table_record.update",
        "bitable.v1.app_table.list",
        "bitable.v1.app_table_field.list",
    }
)


@dataclass(frozen=True)
class SDKWindow:
    window_id: UUID
    organization_id: UUID
    shop_id: UUID
    expires_at: datetime
    caps: Mapping[SDKMethod, int] = field(repr=False)
    enabled: bool = False
    verification_mode: str = "offline_fake"

    def __post_init__(self) -> None:
        if (
            self.expires_at.utcoffset() is None
            or self.verification_mode not in ("offline_fake", "controlled_sdk")
            or type(self.enabled) is not bool
        ):
            raise ValueError("INVALID_SDK_WINDOW")
        if not self.caps or any(
            k not in METHODS or type(v) is not int or not 1 <= v <= 500
            for k, v in self.caps.items()
        ):
            raise ValueError("INVALID_SDK_METHOD_CAP")
        object.__setattr__(self, "caps", MappingProxyType(dict(self.caps)))

    def allows(self, method: SDKMethod) -> bool:
        return self.enabled and datetime.now(UTC) < self.expires_at and method in self.caps


@dataclass(frozen=True)
class SDKScope:
    subject_id: UUID
    task_id: UUID | None
    kind: str

    def __post_init__(self) -> None:
        if self.kind not in (
            "preflight",
            "base_projection",
            "approval_card",
            "task_result",
            "clarification",
        ):
            raise ValueError("INVALID_SDK_SCOPE")
        if (self.kind in ("preflight", "clarification")) != (self.task_id is None):
            raise ValueError("INVALID_SDK_TASK_BINDING")
