"""固定澄清文本与窄发送协议；无模型、业务任务或跨轮会话。"""

from typing import Literal, Protocol
from uuid import UUID

from pydantic import Field, model_validator

from commerceops.application.feishu_business.contracts import Contract

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
