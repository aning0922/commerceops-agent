"""正式IM固定消息/全披露card传输DTO；持久授权与原键由唯一Worker负责。"""

from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import Field, model_validator

from commerceops.application.feishu_business.clarification import NoticeResult
from commerceops.application.feishu_business.contracts import Contract


class BusinessMessage(Contract):
    outbox_id: UUID
    provider_uuid: UUID
    chat_id: str = Field(min_length=1, max_length=256, repr=False)
    kind: Literal["text", "interactive"]
    text: str | None = Field(default=None, min_length=1, max_length=3000, repr=False)
    card: dict[str, Any] | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def one_original_payload(self) -> "BusinessMessage":
        if self.provider_uuid.version != 4:
            raise ValueError("INVALID_ORIGINAL_IM_UUID")
        if self.kind == "text":
            if self.text is None or self.card is not None:
                raise ValueError("INVALID_IM_PAYLOAD")
        elif self.text is not None or self.card is None or self.card.get("schema") != "2.0":
            raise ValueError("INVALID_IM_PAYLOAD")
        return self


class BusinessMessageSender(Protocol):
    async def send_message(self, request: BusinessMessage) -> NoticeResult: ...
