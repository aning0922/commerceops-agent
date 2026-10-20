"""群专用入口不受理旧私聊；真实mention规范化与规范查询hash使用原parser。"""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from commerceops.adapters.feishu.business_gateway import BusinessGateway
from commerceops.adapters.feishu.contracts import ProbePolicy, parse_message
from commerceops.application.feishu_business.gateway_window import GatewayWindow
from commerceops.application.feishu_business.read_intents import parse_read_intent
from commerceops.application.replenishment.contracts import Parameters, WebFailure
from commerceops.domain.commerce_values import facts_hash
from commerceops.entrypoints.feishu_gateway_child import BoundedReceiver
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1  # type: ignore[import-untyped]

from tests.test_feishu_contracts import fixture

pytestmark = pytest.mark.offline


def group_message(text: str) -> tuple[dict[str, Any], ProbePolicy]:
    body = fixture("message_group")
    sender = body["event"]["sender"]
    mention = body["event"]["message"]["mentions"][0]
    policy = ProbePolicy(
        body["header"]["app_id"],
        body["header"]["tenant_key"],
        mention["id"]["open_id"],
        frozenset({sender["sender_id"]["open_id"]}),
        frozenset({body["event"]["message"]["chat_id"]}),
    )
    body["event"]["message"]["content"] = json.dumps({"text": "@_user_1 " + text})
    return body, policy


@pytest.mark.parametrize("kind", ["task_status", "explain_report"])
def test_group_real_mention_normalization_matches_full_plain_query_hash(kind: str) -> None:
    task, report = uuid4(), uuid4()
    text = f"查询任务{task}进度" if kind == "task_status" else f"解释任务{task}的报告{report}"
    body, policy = group_message(text)
    incoming = parse_message(body, policy)
    assert incoming.text == text and facts_hash(incoming.text) == facts_hash(text)
    intent = parse_read_intent(incoming.text)
    assert intent and intent.kind == kind and intent.task_id == task
    assert intent.report_id == (report if kind == "explain_report" else None)
    received = []

    class Receiver:
        def message(self, value: Any) -> dict[str, Any]:
            received.append(value)
            return {"accepted": True}

    receiver: Any = Receiver()
    BusinessGateway(receiver, policy).on_message(P2ImMessageReceiveV1(body))
    assert received == [incoming] and facts_hash(received[0].text) == facts_hash(text)


def test_explicit_group_receiver_rejects_private_or_other_chat_before_admission_or_store() -> None:
    body, policy = group_message(f"查询任务{uuid4()}进度")
    incoming = parse_message(body, policy)
    calls = []

    class Store:
        def message(self, value: Any) -> dict[str, Any]:
            calls.append(value)
            return {"accepted": True}

    store: Any = Store()
    window = GatewayWindow(
        schema_version="p4-gateway-v1",
        window_id=uuid4(),
        organization_id=uuid4(),
        shop_id=uuid4(),
        expires_at=datetime.now(UTC) + timedelta(seconds=120),
        max_workflows=0,
        max_callbacks=2,
        parameters=Parameters(
            source_mode="mock",
            dataset_version="inventory-v1",
            fixture_case="baseline",
            L=3,
            R=7,
            S=2,
        ),
        enabled=True,
    )
    receiver = BoundedReceiver(store, window, group_chat_ids=frozenset({incoming.chat_id}))
    for changed in (replace(incoming, chat_type="p2p"), replace(incoming, chat_id="other-group")):
        with pytest.raises(WebFailure, match="GATEWAY_GROUP_SCOPE_REQUIRED"):
            receiver.message(changed)
    assert calls == [] and receiver.admitted == 0
    assert receiver.message(incoming) == {"accepted": True} and receiver.admitted == 1
    default = BoundedReceiver(store, window)
    assert default.message(replace(incoming, chat_type="p2p")) == {"accepted": True}
