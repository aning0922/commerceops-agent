"""唯一串行 runner 合同；正式 LangGraph 实现由 P1-04 注入。"""

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

JobKind = Literal["analyze", "resume", "recover"]


@dataclass(frozen=True)
class RunRequest:
    job_id: UUID
    task_id: UUID
    organization_id: UUID
    shop_id: UUID
    thread_id: str
    workflow_version: str
    kind: JobKind
    payload_ref: str
    owner: str
    attempt: int


@dataclass(frozen=True)
class RunResult:
    status: Literal["done", "interrupted", "retry"] = "done"
    delay_seconds: int = 0


class RunnerPort(Protocol):
    @property
    def workflow_versions(self) -> frozenset[str]: ...

    async def run(self, request: RunRequest) -> RunResult:
        """事务外调用；中断须持久化后返回，取消须等待底层调用确实停止。

        不启动脱离本调用生命周期的后台任务。业务状态及 checkpoint 由实现
        分别持久化；job done/interrupted 不等于 business_task completed。
        不支持的 workflow_version 须拒绝，不将旧任务隐式改到新图。
        """
        ...
