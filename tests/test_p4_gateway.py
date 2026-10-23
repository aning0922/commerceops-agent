"""正式SDK dispatcher离线合同；no authentication/no network/no secret。"""

import copy
import json
from pathlib import Path
from typing import Any

import lark_oapi as lark  # type: ignore[import-untyped]
import pytest
from commerceops.adapters.feishu.business_config import verify_config
from commerceops.adapters.feishu.business_gateway import (
    BusinessCard,
    BusinessGateway,
    parse_business_card,
)
from commerceops.adapters.feishu.contracts import MessageProbe, ProbeContractError
from commerceops.application.replenishment.contracts import WebFailure

from tests.test_feishu_contracts import POLICY, fixture

pytestmark = pytest.mark.offline


def callback() -> dict[str, Any]:
    body = copy.deepcopy(fixture("card_callback"))
    value = body["event"]["action"]["value"]
    del value["probe_id"]
    del value["task_id"]
    value["nonce"] = "n" * 43
    return body


class Receiver:
    def __init__(self, error: Exception | None = None, status: str = "approved"):
        self.error, self.status = error, status
        self.calls: list[MessageProbe | BusinessCard] = []

    def message(self, message: MessageProbe) -> dict[str, Any]:
        if self.error:
            raise self.error
        self.calls.append(message)
        return {"task_id": "synthetic", "state": "queued"}

    def card(self, card: BusinessCard) -> dict[str, Any]:
        if self.error:
            raise self.error
        self.calls.append(card)
        return {"duplicate": False, "approval_status": self.status}


def test_official_locked_sdk_dispatches_formal_callback_and_acceptance_toast() -> None:
    receiver = Receiver()
    dispatcher = BusinessGateway(receiver, POLICY).dispatcher()
    reply = dispatcher._do_without_validation(json.dumps(callback()).encode())
    assert json.loads(lark.JSON.marshal(reply))["toast"]["content"] == "审批意见已记录，等待执行"
    assert isinstance(receiver.calls[0], BusinessCard)
    dispatcher._do_without_validation(json.dumps(fixture("message_group")).encode())
    assert isinstance(receiver.calls[1], MessageProbe)


@pytest.mark.parametrize(
    "field,value",
    [
        ("operator", "forged"),
        ("plan_version", True),
        ("nonce", "short"),
        ("acknowledged_assumption_keys", ["inbound_unknown_zero:x"] * 2),
    ],
)
def test_untrusted_callback_values_are_strict(field: str, value: object) -> None:
    body = callback()
    body["event"]["action"]["value"][field] = value
    with pytest.raises(ProbeContractError):
        parse_business_card(body, POLICY)


def test_platform_operator_cannot_be_replaced_by_button_identity() -> None:
    body = callback()
    body["event"]["operator"]["open_id"] = "outside-policy"
    with pytest.raises(ProbeContractError):
        parse_business_card(body, POLICY)


def test_db_failure_is_not_turned_into_success_or_toast() -> None:
    dispatcher = BusinessGateway(
        Receiver(RuntimeError("synthetic DB failure")), POLICY
    ).dispatcher()
    with pytest.raises(RuntimeError, match="synthetic DB failure"):
        dispatcher._do_without_validation(json.dumps(callback()).encode())
    with pytest.raises(RuntimeError, match="synthetic DB failure"):
        dispatcher._do_without_validation(json.dumps(fixture("message_group")).encode())


def test_permission_failure_reports_acceptance_failure() -> None:
    dispatcher = BusinessGateway(Receiver(WebFailure("ACCESS_DENIED", 403)), POLICY).dispatcher()
    reply = dispatcher._do_without_validation(json.dumps(callback()).encode())
    assert json.loads(lark.JSON.marshal(reply))["toast"]["content"] == "审批未受理：ACCESS_DENIED"


def test_rejected_toast_is_separate_from_execution_success() -> None:
    dispatcher = BusinessGateway(Receiver(status="rejected"), POLICY).dispatcher()
    reply = dispatcher._do_without_validation(json.dumps(callback()).encode())
    assert json.loads(lark.JSON.marshal(reply))["toast"]["content"] == "已拒绝，不创建补货项"


def test_verify_config_does_not_open_secret_paths_or_connect_resources() -> None:
    result = verify_config(Path("docs/contracts/p4-config.example.json"))
    assert result["structure_valid"]
    assert result["allowed_user_count"] == 2
    for name in (
        "secret_contents_read",
        "sdk_constructed",
        "pg_connected",
        "platform_resources_verified",
        "external_sender_enabled",
    ):
        assert result[name] is False


@pytest.mark.parametrize("payload", ["message", "card"])
def test_typed_service_unavailable_is_not_acknowledged_as_filtered_success(payload: str) -> None:
    dispatcher = BusinessGateway(
        Receiver(WebFailure("SERVICE_UNAVAILABLE", 503)), POLICY
    ).dispatcher()
    body = callback() if payload == "card" else fixture("message_group")
    with pytest.raises(WebFailure) as caught:
        dispatcher._do_without_validation(json.dumps(body).encode())
    assert caught.value.status == 503
