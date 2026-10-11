"""正式P4 SDK入口；复用纯消息校验，旧技术probe模块原字节保留。"""

import json
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import NAMESPACE_URL, uuid5

import lark_oapi as lark  # type: ignore[import-untyped]
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1  # type: ignore[import-untyped]
from lark_oapi.event.callback.model.p2_card_action_trigger import (  # type: ignore[import-untyped]
    P2CardActionTrigger,
    P2CardActionTriggerResponse,
)
from pydantic import ValidationError

from commerceops.adapters.feishu.contracts import (
    ContractCode,
    MessageProbe,
    PlatformIdentity,
    ProbeContractError,
    ProbePolicy,
    _envelope,
    _identity,
    _object,
    _string,
    decode_payload,
    parse_message,
)
from commerceops.adapters.feishu.sdk import restrict_sdk_logs
from commerceops.application.replenishment.contracts import DecisionInput, WebFailure

CARD_VALUE_FIELDS = frozenset(
    {
        "approval_id",
        "plan_id",
        "plan_version",
        "plan_hash",
        "action",
        "acknowledged_assumption_keys",
        "nonce",
    }
)


@dataclass(frozen=True)
class BusinessCard:
    event_id: str
    identity: PlatformIdentity
    chat_id: str
    message_id: str
    request: DecisionInput


def parse_business_card(payload: object, policy: ProbePolicy) -> BusinessCard:
    event_id, event = _envelope(payload, policy, "card.action.trigger")
    operator = _object(event.get("operator"))
    identity = _identity(operator, operator.get("open_id"), policy)
    context = _object(event.get("context"))
    chat, message = _string(context.get("open_chat_id")), _string(context.get("open_message_id"))
    action = _object(event.get("action"))
    value = _object(action.get("value"))
    if action.get("tag") != "button" or set(value) != CARD_VALUE_FIELDS:
        raise ProbeContractError(ContractCode.INVALID_PAYLOAD)
    try:
        request = DecisionInput.model_validate_json(
            json.dumps(
                {
                    **value,
                    "schema_version": "p3-web-v1",
                    "request_key": str(
                        uuid5(
                            NAMESPACE_URL,
                            f"p4-card:{identity.app_id}:{identity.tenant_key}:{event_id}",
                        )
                    ),
                }
            )
        )
    except (ValueError, TypeError, ValidationError):
        raise ProbeContractError(ContractCode.INVALID_PAYLOAD) from None
    return BusinessCard(event_id, identity, chat, message, request)


class BusinessReceiver(Protocol):
    def message(self, message: MessageProbe) -> dict[str, Any]: ...

    def card(self, card: BusinessCard) -> dict[str, Any]: ...


class BusinessGateway:
    def __init__(self, receiver: BusinessReceiver, policy: ProbePolicy):
        restrict_sdk_logs()
        self.receiver, self.policy = receiver, policy

    def on_message(self, data: P2ImMessageReceiveV1) -> None:
        try:
            message = parse_message(decode_payload(lark.JSON.marshal(data).encode()), self.policy)
            self.receiver.message(message)
        except ProbeContractError:
            # 明确过滤的事件无业务写；DB/未知异常传播给SDK失败帧，不假ACK。
            return
        except WebFailure as error:
            if error.status >= 500:
                raise
            return

    def on_card(self, data: P2CardActionTrigger) -> P2CardActionTriggerResponse:
        try:
            card = parse_business_card(
                decode_payload(lark.JSON.marshal(data).encode()), self.policy
            )
            receipt = self.receiver.card(card)
        except ProbeContractError as error:
            return P2CardActionTriggerResponse(
                {
                    "toast": {"type": "error", "content": "审批未受理：" + error.code.value},
                }
            )
        except WebFailure as error:
            if error.status >= 500:
                raise
            return P2CardActionTriggerResponse(
                {
                    "toast": {"type": "warning", "content": "审批未受理：" + error.code},
                }
            )
        text = (
            "已有审批决定，本次重复"
            if receipt["duplicate"]
            else "已拒绝，不创建补货项"
            if receipt["approval_status"] == "rejected"
            else "审批意见已记录，等待执行"
        )
        return P2CardActionTriggerResponse({"toast": {"type": "info", "content": text}})

    def dispatcher(self) -> Any:
        return (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self.on_message)
            .register_p2_card_action_trigger(self.on_card)
            .build()
        )
