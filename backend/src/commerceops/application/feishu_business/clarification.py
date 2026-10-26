"""固定澄清文本与窄发送协议；无模型、业务任务或跨轮会话。"""

import re
from typing import Literal, Protocol, cast
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from commerceops.application.commerce.inventory_routing import _explicit_lrs_spans
from commerceops.application.feishu_business.contracts import Contract
from commerceops.application.replenishment.nl_preflight import (
    Name,
    Scope,
    Source,
    Window,
    WooScope,
    WooSource,
    WooWindow,
)
from commerceops.domain.commerce_values import facts_hash

F02_WORKFLOW: Literal["p3-inventory-replenishment-v1"] = "p3-inventory-replenishment-v1"
F02_TTL_SECONDS = 900

CLARIFICATION_TEXT = (
    "请求还不完整，请明确库存分析范围。当前演示可发送“分析库存并生成补货建议”。"
    "补充参数请发送一条新的完整请求；本次没有创建分析、审批或补货项。"
)


class ClarificationMessage(Contract):
    reply_id: UUID
    provider_uuid: UUID
    chat_id: str = Field(min_length=1, max_length=256, repr=False)
    text: Literal[CLARIFICATION_TEXT] = CLARIFICATION_TEXT  # type: ignore[valid-type]

    @model_validator(mode="after")
    def original_uuid4(self) -> "ClarificationMessage":
        if self.provider_uuid.version != 4:
            raise ValueError("INVALID_CLARIFICATION_SEND")
        return self


class F02Source(Contract):
    inbox_id: UUID
    text_hash: str = Field(pattern="^[a-f0-9]{64}$")
    start: int = Field(ge=0)
    end: int = Field(ge=1)
    source: Literal["explicit_text"] = "explicit_text"

    @model_validator(mode="after")
    def actual_span(self) -> "F02Source":
        if self.end <= self.start:
            raise ValueError("INVALID_F02_SOURCE")
        return self


class F02Candidate(Contract):
    schema_version: Literal["p4-f02-candidate-v1"] = "p4-f02-candidate-v1"
    request_id: UUID
    round: int = Field(ge=1)
    kind: Literal["question", "ready", "created"]
    workflow_version: Literal["p3-inventory-replenishment-v1"] = F02_WORKFLOW
    source: Source | WooSource = Field(discriminator="source_mode")
    window: Window | WooWindow = Field(discriminator="source")
    scope: Scope | WooScope = Field(discriminator="kind")
    parameters: dict[Name, int]
    parameter_sources: dict[Name, F02Source]
    task_id: UUID | None = None

    @field_validator("parameters")
    @classmethod
    def bounded_parameters(cls, value: dict[Name, int]) -> dict[Name, int]:
        if any(type(n) is not int or not 0 <= n <= 365 for n in value.values()):
            raise ValueError("INVALID_F02_PARAMETERS")
        return value

    @model_validator(mode="after")
    def closed_candidate(self) -> "F02Candidate":
        if not (
            isinstance(self.source, Source)
            and isinstance(self.window, Window)
            and isinstance(self.scope, Scope)
            or isinstance(self.source, WooSource)
            and isinstance(self.window, WooWindow)
            and isinstance(self.scope, WooScope)
        ):
            raise ValueError("INVALID_F02_SOURCE_SCOPE")
        if (
            set(self.parameters) != set(self.parameter_sources)
            or (self.kind == "question") != (len(self.parameters) < 3)
            or (self.kind == "created") != (self.task_id is not None)
        ):
            raise ValueError("INVALID_F02_CANDIDATE")
        return self

    def confirmation_hash(self) -> str:
        return facts_hash(self.model_dump(mode="json", exclude={"kind", "task_id"}))

    def text(self) -> str:
        values = "，".join(
            f"{k}={self.parameters[k]}" for k in ("L", "R", "S") if k in self.parameters
        )
        title = f"澄清请求 {self.request_id} 第{self.round}轮"
        if self.kind == "created":
            return (
                f"{title}已确认，正式任务 {self.task_id} 的创建回执已记录。"
                "请查询正式任务查看当前审批和执行状态。"
            )
        scope = (
            "最近七个完整自然日、当前授权本地Woo测试店全部商品；"
            if isinstance(self.source, WooSource)
            else "最近七个完整自然日、当前授权店铺全部Mock商品；"
        ) + values
        if self.kind == "ready":
            return (
                f"{title}：{scope}。请明确发送“确认澄清 {self.request_id} 第{self.round}轮”。"
                "确认后才创建分析任务；本次尚未创建分析、审批或补货项。"
            )
        missing = "、".join(k for k in ("L", "R", "S") if k not in self.parameters)
        return (
            f"{title}：{scope}。还缺{missing}，请发送“补充澄清 {self.request_id} "
            f"第{self.round}轮 L=… R=… S=…”，只填写明确参数。有效期15分钟；"
            "本次尚未创建分析、审批或补货项。"
        )


class F02Message(Contract):
    reply_id: UUID
    provider_uuid: UUID
    chat_id: str = Field(min_length=1, max_length=256, repr=False)
    candidate: F02Candidate = Field(repr=False)
    payload_hash: str = Field(pattern="^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def original_payload(self) -> "F02Message":
        if (
            self.provider_uuid.version != 4
            or facts_hash(self.candidate.model_dump(mode="json")) != self.payload_hash
        ):
            raise ValueError("INVALID_F02_MESSAGE")
        return self

    @property
    def text(self) -> str:
        return self.candidate.text()


class F02Command(Contract):
    action: Literal["supplement", "confirm"]
    request_id: UUID
    round: int = Field(ge=1)
    parameters: dict[Name, int]
    spans: dict[Name, tuple[int, int]]


def parse_f02_command(text: str) -> F02Command | None:
    """显式编号+轮次，不猜native reply或上一位用户；非法关联命令固定拒绝。"""
    if not text.startswith(("补充澄清", "确认澄清")):
        return None
    found = re.fullmatch(
        r"(补充澄清|确认澄清) ([a-f0-9-]{36}) 第([1-9][0-9]{0,9})轮(?: (.+))?", text
    )
    if found is None or len(text) > 2000:
        raise ValueError("INVALID_F02_COMMAND")
    identifier = UUID(found[2])
    if str(identifier) != found[2]:
        raise ValueError("INVALID_F02_COMMAND")
    parameters: dict[Name, int] = {}
    spans: dict[Name, tuple[int, int]] = {}
    if found[1] == "确认澄清":
        if found[4] is not None:
            raise ValueError("INVALID_F02_COMMAND")
    else:
        block = found[4]
        if block is None or not re.match(r"[LRS](?:=|:)", block):
            raise ValueError("INVALID_F02_COMMAND")
        for name, start, end, scalar in _explicit_lrs_spans(block):
            if str(int(scalar)) != scalar:
                raise ValueError("INVALID_F02_COMMAND")
            key = cast(Name, name)
            parameters[key] = int(scalar)
            spans[key] = (found.start(4) + start, found.start(4) + end)
        if not parameters:
            raise ValueError("INVALID_F02_COMMAND")
    return F02Command(
        action="confirm" if found[1] == "确认澄清" else "supplement",
        request_id=identifier,
        round=int(found[3]),
        parameters=parameters,
        spans=spans,
    )


class NoticeResult(Contract):
    outcome: Literal["sent", "unknown", "rejected"]
    code: str = Field(pattern="^[A-Z][A-Z0-9_]{0,79}$")
    message_id: str | None = Field(default=None, min_length=1, max_length=256, repr=False)

    @model_validator(mode="after")
    def actual_message_ack(self) -> "NoticeResult":
        if (self.outcome == "sent") != (self.message_id is not None):
            raise ValueError("INVALID_NOTICE_ACK")
        return self


class ClarificationSender(Protocol):
    async def send_clarification(self, request: ClarificationMessage) -> NoticeResult: ...


class F02Sender(Protocol):
    async def send_f02(self, request: F02Message) -> NoticeResult: ...
