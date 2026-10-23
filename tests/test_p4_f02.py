"""F02纯命令/候选/发送Fake；没有资源、密钥、模型或平台请求。"""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from commerceops.adapters.feishu.business_im import BusinessIMSDK
from commerceops.application.feishu_business.clarification import (
    F02Candidate,
    F02Message,
    F02Source,
    parse_f02_command,
)
from commerceops.application.replenishment.nl_preflight import Scope, Source, Window
from commerceops.domain.commerce_values import facts_hash
from pydantic import ValidationError

pytestmark = pytest.mark.offline


def candidate(*, complete: bool = True, round: int = 1) -> F02Candidate:
    parameters = {"L": 3, "R": 7, "S": 2} if complete else {"L": 3}
    return F02Candidate.model_validate(
        {
            "request_id": uuid4(),
            "round": round,
            "kind": "ready" if complete else "question",
            "source": Source(fixture_case="baseline"),
            "window": Window(
                start=datetime(2026, 10, 1, tzinfo=UTC),
                end=datetime(2026, 10, 8, tzinfo=UTC),
                timezone="Asia/Shanghai",
                as_of=datetime(2026, 10, 8, tzinfo=UTC),
            ),
            "scope": Scope(shop_id=uuid4()),
            "parameters": parameters,
            "parameter_sources": {
                k: F02Source(inbox_id=uuid4(), text_hash="a" * 64, start=0, end=1)
                for k in parameters
            },
        }
    )


@pytest.mark.parametrize("block", ["L=3 R=7 S=2", "L:3天，R:7天；S:2天。", "R=0", "S=365"])
def test_explicit_command_consumes_parameters_and_actual_spans(block: str) -> None:
    identifier = uuid4()
    text = f"补充澄清 {identifier} 第1轮 {block}"
    result = parse_f02_command(text)
    assert result and result.request_id == identifier and result.action == "supplement"
    for key, value in result.parameters.items():
        start, end = result.spans[key]
        assert text[start:end] == str(value)


@pytest.mark.parametrize(
    "tail",
    [
        "L=03",
        "L=-1",
        "L=1.5",
        "L=3 L=4",
        "L=366",
        "L=3/2",
        "L=true",
        "L=3元",
        "L=3 trailing",
        "随便L=3",
        "",
        "R=7 S=2未知",
    ],
)
def test_invalid_partial_or_unknown_suffix_never_becomes_parameters(tail: str) -> None:
    with pytest.raises(ValueError):
        parse_f02_command(f"补充澄清 {uuid4()} 第1轮 {tail}")


@pytest.mark.parametrize("tail", ["L=3 R=7 S=2", "确认", "。"])
def test_confirmation_is_explicit_only_current_number_round_and_no_extra_text(tail: str) -> None:
    with pytest.raises(ValueError):
        parse_f02_command(f"确认澄清 {uuid4()} 第1轮 {tail}")
    command = parse_f02_command(f"确认澄清 {uuid4()} 第1轮")
    assert command and command.action == "confirm" and command.parameters == {}
    assert parse_f02_command("确认") is None


def test_round_has_no_new_product_max3_and_immutable_full_candidate_hash() -> None:
    value = candidate(round=12)
    assert value.round == 12
    assert len(value.confirmation_hash()) == 64
    changed = value.model_copy(update={"round": 13})
    assert changed.confirmation_hash() != value.confirmation_hash()
    assert "尚未创建分析、审批或补货项" in value.text()
    assert "正式任务" not in value.text()
    assert "还缺R、S" in candidate(complete=False).text()


@pytest.mark.parametrize("value", [True, -1, 366, 0.5, "3"])
def test_candidate_rejects_untrusted_scalar_types_and_ranges(value: object) -> None:
    body = candidate().model_dump()
    body["parameters"]["L"] = value
    with pytest.raises(ValidationError):
        F02Candidate.model_validate(body)


def test_frozen_message_hash_provider_uuid_and_renderer_cannot_be_replaced() -> None:
    value = candidate()
    request = F02Message(
        reply_id=uuid4(),
        provider_uuid=uuid4(),
        chat_id="synthetic-chat",
        candidate=value,
        payload_hash=facts_hash(value.model_dump(mode="json")),
    )
    assert request.text == value.text()
    with pytest.raises(ValidationError):
        F02Message.model_validate({**request.model_dump(), "payload_hash": "b" * 64})
    with pytest.raises(ValidationError):
        F02Message.model_validate({**request.model_dump(), "text": "任意模型输出"})


def test_created_receipt_never_guesses_current_execution_state_when_delivery_is_late() -> None:
    value = candidate()
    created = F02Candidate.model_validate(
        {**value.model_dump(), "kind": "created", "task_id": uuid4()}
    )
    assert "创建回执已记录" in created.text()
    assert "当前审批和执行状态" in created.text()
    assert "尚未审批或执行" not in created.text()


def test_original_IM_transport_sends_frozen_F02_text_and_original_uuid_once() -> None:
    value = candidate()
    request = F02Message(
        reply_id=uuid4(),
        provider_uuid=uuid4(),
        chat_id="synthetic-chat",
        candidate=value,
        payload_hash=facts_hash(value.model_dump(mode="json")),
    )
    create = AsyncMock(
        return_value=SimpleNamespace(
            raw=SimpleNamespace(status_code=200),
            code=0,
            data=SimpleNamespace(message_id="synthetic-message", chat_id=request.chat_id),
        )
    )
    client = SimpleNamespace(
        im=SimpleNamespace(v1=SimpleNamespace(message=SimpleNamespace(acreate=create)))
    )
    result = asyncio.run(BusinessIMSDK(client).send_f02(request))
    assert result.outcome == "sent" and create.await_count == 1
    body = create.call_args.args[0].request_body
    assert body.uuid == str(request.provider_uuid) and body.msg_type == "text"
    assert request.text in __import__("json").loads(body.content)["text"]
