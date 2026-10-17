"""窄固定澄清合同：错误输入不变成模型/库存或另一调度系统。"""

from uuid import uuid1, uuid4

import pytest
from commerceops.application.feishu_business.clarification import (
    CLARIFICATION_TEXT,
    ClarificationMessage,
    NoticeResult,
)
from pydantic import ValidationError

pytestmark = pytest.mark.offline


def test_clarification_is_fixed_text_and_original_uuid4() -> None:
    reply = ClarificationMessage(reply_id=uuid4(), provider_uuid=uuid4(), chat_id="synthetic-chat")
    assert reply.text == CLARIFICATION_TEXT
    assert "没有创建分析、审批或补货项" in reply.text
    with pytest.raises(ValidationError):
        ClarificationMessage(reply_id=uuid4(), provider_uuid=uuid1(), chat_id="synthetic-chat")
    with pytest.raises(ValidationError):
        ClarificationMessage(
            reply_id=uuid4(), provider_uuid=uuid4(), chat_id="synthetic-chat", text="任意模型输出"
        )


def test_sent_requires_actual_message_id_and_unknown_cannot_claim_ack() -> None:
    with pytest.raises(ValidationError):
        NoticeResult(outcome="sent", code="SUCCESS")
    with pytest.raises(ValidationError):
        NoticeResult(outcome="unknown", code="ACK_UNKNOWN", message_id="synthetic-message")
    assert (
        NoticeResult(outcome="sent", code="ACK", message_id="synthetic-message").outcome == "sent"
    )
