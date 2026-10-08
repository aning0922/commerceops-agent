"""T1 技术用例；只有显式 test 上下文，无 HTTP/SDK/真实身份入口。"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from uuid import UUID


@dataclass(frozen=True)
class TrustedTestContext:
    """仅由测试启动层构造；不是可接受的客户端授权凭证。"""

    organization_id: UUID
    shop_id: UUID
    principal_id: UUID
    conversation_id: UUID
    mode: Literal["test"]


@dataclass(frozen=True)
class TestInbound:
    app_id: str
    tenant_key: str
    event_id: str
    message_id: str | None
    normalized_request: dict[str, Any]
    workflow_version: str


@dataclass(frozen=True)
class IntakeReceipt:
    task_id: UUID
    job_id: UUID
    thread_id: str
    workflow_version: str


class TestIntakeStore(Protocol):
    def accept(
        self,
        context: TrustedTestContext,
        event: TestInbound,
        hook: Callable[[str], None] | None = None,
    ) -> IntakeReceipt: ...


class TestIntakeService:
    def __init__(self, store: TestIntakeStore):
        self.store = store

    def accept(
        self,
        context: TrustedTestContext,
        event: TestInbound,
        *,
        hook: Callable[[str], None] | None = None,
    ) -> IntakeReceipt:
        if context.mode != "test" or not event.event_id or not event.workflow_version:
            raise ValueError("explicit technical test context required")
        if "schema_version" not in event.normalized_request:
            raise ValueError("schema_version required")
        return self.store.accept(context, event, hook)
