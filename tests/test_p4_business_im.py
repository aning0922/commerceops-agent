"""官方IM请求构造/原UUID/ACK映射，async client替身无认证/网络。"""

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from commerceops.adapters.feishu.business_im import BusinessIMSDK
from commerceops.application.feishu_business.clarification import ClarificationMessage

pytestmark = pytest.mark.offline


@pytest.mark.parametrize(
    "status,code,message,chat,expected",
    [
        (200, 0, "synthetic-message", "synthetic-chat", "sent"),
        (500, 0, "synthetic-message", "synthetic-chat", "unknown"),
        (429, 0, None, None, "unknown"),
        (200, 1254291, None, None, "unknown"),
        (200, 0, "synthetic-message", "other-chat", "unknown"),
        (200, False, "synthetic-message", "synthetic-chat", "unknown"),
    ],
)
def test_im_ack_requires_http_business_code_actual_id_and_bound_chat(
    status: int,
    code: Any,
    message: str | None,
    chat: str | None,
    expected: str,
) -> None:
    calls = []

    async def create(request: Any, option: Any) -> Any:
        calls.append(request)
        return SimpleNamespace(
            raw=SimpleNamespace(status_code=status),
            code=code,
            data=SimpleNamespace(message_id=message, chat_id=chat),
        )

    client = SimpleNamespace(
        im=SimpleNamespace(v1=SimpleNamespace(message=SimpleNamespace(acreate=create)))
    )
    notice = ClarificationMessage(reply_id=uuid4(), provider_uuid=uuid4(), chat_id="synthetic-chat")
    result = asyncio.run(BusinessIMSDK(client).send_clarification(notice))
    assert result.outcome == expected and len(calls) == 1
    request = calls[0]
    assert request.receive_id_type == "chat_id"
    assert request.body.uuid == str(notice.provider_uuid)
    assert request.body.receive_id == notice.chat_id
    assert request.body.msg_type == "text"
    assert json.loads(request.body.content) == {"text": notice.text}


def test_transport_exception_is_unknown_and_not_retried() -> None:
    count = 0

    async def create(request: Any, option: Any) -> Any:
        nonlocal count
        count += 1
        raise TimeoutError()

    client = SimpleNamespace(
        im=SimpleNamespace(v1=SimpleNamespace(message=SimpleNamespace(acreate=create)))
    )
    notice = ClarificationMessage(reply_id=uuid4(), provider_uuid=uuid4(), chat_id="synthetic-chat")
    assert asyncio.run(BusinessIMSDK(client).send_clarification(notice)).outcome == "unknown"
    assert count == 1
