"""正式IM固定回复transport；只消费原持久UUID，client由受控运行层提供。"""

import asyncio
import json
from typing import Any

from lark_oapi.api.im.v1 import (  # type: ignore[import-untyped]
    CreateMessageRequest,
    CreateMessageRequestBody,
)

from commerceops.adapters.feishu.sdk import restrict_sdk_logs
from commerceops.application.feishu_business.clarification import ClarificationMessage, NoticeResult
from commerceops.application.feishu_business.im_delivery import BusinessMessage


class BusinessIMSDK:
    def __init__(self, client: Any, *, option: Any = None):
        restrict_sdk_logs()
        self.client, self.option = client, option

    async def send_clarification(self, request: ClarificationMessage) -> NoticeResult:
        request = ClarificationMessage.model_validate(request.model_dump())
        return await self.send_message(
            BusinessMessage(
                outbox_id=request.reply_id,
                provider_uuid=request.provider_uuid,
                chat_id=request.chat_id,
                kind="text",
                text=request.text,
            )
        )

    async def send_message(self, request: BusinessMessage) -> NoticeResult:
        request = BusinessMessage.model_validate(request.model_dump())
        content = {"text": request.text} if request.kind == "text" else request.card
        prepared = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(request.chat_id)
                .msg_type(request.kind)
                .content(json.dumps(content, ensure_ascii=False))
                .uuid(str(request.provider_uuid))
                .build()
            )
            .build()
        )
        try:
            async with asyncio.timeout(10):
                response = await self.client.im.v1.message.acreate(prepared, self.option)
            raw, data = getattr(response, "raw", None), getattr(response, "data", None)
            status, code = getattr(raw, "status_code", None), getattr(response, "code", None)
            message, chat = getattr(data, "message_id", None), getattr(data, "chat_id", None)
            if (
                type(status) is int
                and 200 <= status < 300
                and type(code) is int
                and code == 0
                and type(message) is str
                and message
                and chat == request.chat_id
            ):
                return NoticeResult(outcome="sent", code="IM_ACK", message_id=message)
        except Exception:
            return NoticeResult(outcome="unknown", code="IM_TRANSPORT_UNKNOWN")
        # 429/5xx/业务错误/缺ACK均不能仅按HTTP宣无写入；不在transport中重试。
        return NoticeResult(outcome="unknown", code="IM_ACK_UNKNOWN")
