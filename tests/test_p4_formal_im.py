"""正式20card及固定result消息走同原UUID SDK发送；无真实client/认证/平台。"""

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from commerceops.adapters.feishu.business_cards import build_business_card
from commerceops.adapters.feishu.business_im import BusinessIMSDK
from commerceops.application.feishu_business.im_delivery import BusinessMessage
from pydantic import ValidationError

from tests.test_p4_business_cards import full_plan

pytestmark = pytest.mark.offline


def test_full_twenty_card_original_uuid_and_accepted_message_chat_ack() -> None:
    content, approval = full_plan()
    card = build_business_card(content, approval, "n" * 43)
    message = BusinessMessage(
        outbox_id=uuid4(),
        provider_uuid=uuid4(),
        chat_id="synthetic-chat",
        kind="interactive",
        card=card,
    )
    calls = []

    async def invoke(request: Any, option: Any) -> Any:
        calls.append(request)
        assert request.body.uuid == str(message.provider_uuid)
        assert request.body.msg_type == "interactive"
        actual = json.loads(request.body.content)
        assert actual == card
        assert all(
            i["sku_key"] in actual["body"]["elements"][0]["content"] for i in content["items"]
        )
        return SimpleNamespace(
            raw=SimpleNamespace(status_code=200),
            code=0,
            data=SimpleNamespace(message_id="synthetic-message", chat_id=message.chat_id),
        )

    client = SimpleNamespace(
        im=SimpleNamespace(v1=SimpleNamespace(message=SimpleNamespace(acreate=invoke)))
    )
    result = asyncio.run(BusinessIMSDK(client).send_message(message))
    assert result.outcome == "sent" and result.message_id == "synthetic-message" and len(calls) == 1


def test_result_text_and_card_are_exclusive_and_original_uuid_never_regenerated() -> None:
    value: dict[str, Any] = dict(
        outbox_id=uuid4(),
        provider_uuid=uuid4(),
        chat_id="synthetic-chat",
        kind="text",
        text="内部工作项结果：Mock演示，不采购或修改真实库存",
    )
    original = BusinessMessage(**value)
    assert (
        BusinessMessage.model_validate(original.model_dump()).provider_uuid
        == original.provider_uuid
    )
    with pytest.raises(ValidationError):
        BusinessMessage(**value, card={"schema": "2.0"})
    with pytest.raises(ValidationError):
        BusinessMessage(**(value | {"kind": "interactive"}))
