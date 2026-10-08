"""锁定 SDK 边界；原始 logger 被禁用，handler 不输出平台数据。"""

import logging
from typing import Any, Protocol

import lark_oapi as lark  # type: ignore[import-untyped]
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1  # type: ignore[import-untyped]
from lark_oapi.event.callback.model.p2_card_action_trigger import (  # type: ignore[import-untyped]
    P2CardActionTrigger,
    P2CardActionTriggerResponse,
)

from commerceops.adapters.feishu.contracts import ProbeContractError, decode_payload
from commerceops.adapters.feishu.repository import ProbeConflict, ProbeReceipt


def restrict_sdk_logs() -> None:
    """进程内限制 SDK/传输/连接池原文；应用自行输出固定分类，不恢复原文 logger。"""
    prefixes = ("Lark", "websockets", "httpx", "httpcore", "urllib3", "psycopg")
    names = set(prefixes) | {"psycopg.pool"}
    names.update(
        name
        for name in logging.Logger.manager.loggerDict
        if any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes)
    )
    for name in names:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.addHandler(logging.NullHandler())
        logger.propagate = False
        logger.disabled = True


class Receiver(Protocol):
    def receive_message(self, payload: object) -> ProbeReceipt: ...

    def receive_card(self, payload: object) -> ProbeReceipt: ...


class ProbeGateway:
    def __init__(self, receiver: Receiver):
        restrict_sdk_logs()
        self.receiver = receiver

    def on_message(self, data: P2ImMessageReceiveV1) -> None:
        payload = decode_payload(lark.JSON.marshal(data).encode())
        try:
            self.receiver.receive_message(payload)
        except ProbeContractError as error:
            logging.getLogger("commerceops.feishu_probe").warning(
                "message_filtered code=%s", error.code.value
            )
            return
        except ProbeConflict:
            logging.getLogger("commerceops.feishu_probe").warning(
                "message_filtered code=EVENT_CONFLICT"
            )
            # 被明确过滤/冲突的消息不进入任务；DB异常继续抛出，由 SDK 生成失败帧。
            return

    def on_card(self, data: P2CardActionTrigger) -> P2CardActionTriggerResponse:
        payload = decode_payload(lark.JSON.marshal(data).encode())
        try:
            receipt = self.receiver.receive_card(payload)
        except ProbeContractError as error:
            logging.getLogger("commerceops.feishu_probe").warning(
                "card_rejected code=%s", error.code.value
            )
            return P2CardActionTriggerResponse(
                {"toast": {"type": "error", "content": "技术探针已拒绝：" + error.code.value}}
            )
        except ProbeConflict:
            logging.getLogger("commerceops.feishu_probe").warning(
                "card_rejected code=EVENT_CONFLICT"
            )
            return P2CardActionTriggerResponse(
                {"toast": {"type": "error", "content": "技术探针已拒绝：身份、合同或事件冲突"}}
            )
        if receipt.result == "decision_conflict" or receipt.result.endswith(":decision_conflict"):
            text = "技术探针已有相反或其他身份的决定，本次冲突"
            toast_type = "warning"
        elif receipt.result.startswith("duplicate"):
            text = "技术探针已记录，本次重复；不创建补货项"
            toast_type = "info"
        else:
            text = "已持久记录技术探针动作；不创建补货项"
            toast_type = "success"
        return P2CardActionTriggerResponse({"toast": {"type": toast_type, "content": text}})

    def dispatcher(self) -> Any:
        return (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self.on_message)
            .register_p2_card_action_trigger(self.on_card)
            .build()
        )
