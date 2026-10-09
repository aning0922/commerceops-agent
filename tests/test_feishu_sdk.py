"""执行锁定官方 SDK 的类型/dispatcher/WS 编码/HTTP 构造；网络全部替身。"""

import asyncio
import base64
import json
import logging
from importlib.metadata import version
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import lark_oapi as lark  # type: ignore[import-untyped]
import pytest
import requests
from commerceops.adapters.feishu.base import ApiReply, RecordSDK
from commerceops.adapters.feishu.repository import ProbeDatabaseFailure, ProbeReceipt
from commerceops.adapters.feishu.sdk import ProbeGateway, restrict_sdk_logs
from lark_oapi.event.callback.model.p2_card_action_trigger import (  # type: ignore[import-untyped]
    P2CardActionTriggerResponse,
)
from lark_oapi.ws.pb.pbbp2_pb2 import Frame  # type: ignore[import-untyped]

from tests.test_feishu_contracts import fixture

pytestmark = pytest.mark.offline


class Receiver:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.payloads: list[object] = []

    def receive_message(self, payload: object) -> ProbeReceipt:
        if self.fail:
            raise ProbeDatabaseFailure()
        self.payloads.append(payload)
        return ProbeReceipt(uuid4(), "message_received")

    def receive_card(self, payload: object) -> ProbeReceipt:
        if self.fail:
            raise ProbeDatabaseFailure()
        self.payloads.append(payload)
        return ProbeReceipt(uuid4(), "probe_recorded:approve_with_assumptions")


def frame(payload: dict[str, Any]) -> Any:
    result = Frame()
    result.SeqID = 1
    result.LogID = 1
    result.service = 1
    result.method = 1
    result.payload = json.dumps(payload).encode()
    for key, value in {
        "type": "event",
        "message_id": "probe-frame",
        "sum": "1",
        "seq": "0",
        "trace_id": "probe-trace",
    }.items():
        header = result.headers.add()
        header.key = key
        header.value = value
    return result


def test_locked_sdk_types_and_dispatcher_without_network() -> None:
    assert version("lark-oapi") == "1.7.3"
    receiver = Receiver()
    dispatcher = ProbeGateway(receiver).dispatcher()
    response = dispatcher._do_without_validation(json.dumps(fixture("card_callback")).encode())
    assert isinstance(response, P2CardActionTriggerResponse)
    assert json.loads(lark.JSON.marshal(response))["toast"]["type"] == "success"
    dispatcher._do_without_validation(json.dumps(fixture("message_group")).encode())
    parsed = receiver.payloads[-1]
    assert isinstance(parsed, dict)
    assert parsed["event"]["message"]["mentions"][0]["mentioned_type"] == "bot"
    assert parsed["event"]["message"]["mentions"][0]["id"]["open_id"] == "probe-bot"


@pytest.mark.parametrize("fail,expected", [(False, 200), (True, 500)])
def test_sdk_ws_response_encoding_and_db_failure_frame(
    fail: bool, expected: int, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gateway = ProbeGateway(Receiver(fail=fail))
    captured: list[bytes] = []

    async def write(data: bytes) -> None:
        captured.append(data)

    async def handle() -> None:
        client = lark.ws.Client("probe-app", "REDACTED", event_handler=gateway.dispatcher())
        restrict_sdk_logs()
        monkeypatch.setattr(client, "_write_message", write)
        try:
            await client._handle_data_frame(frame(fixture("card_callback")))
        finally:
            client._cache._cron.cancel()
            await asyncio.gather(client._cache._cron, return_exceptions=True)

    asyncio.run(handle())
    assert len(captured) == 1
    reply = Frame()
    reply.ParseFromString(captured[0])
    body = json.loads(reply.payload)
    assert body["code"] == expected
    if not fail:
        assert json.loads(base64.b64decode(body["data"]))["toast"]["type"] == "success"
    else:
        assert body.get("data") is None
    assert capsys.readouterr() == ("", "")


def test_sdk_log_restriction_covers_payload_url_and_exception_text(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    restrict_sdk_logs()
    with caplog.at_level(logging.DEBUG):
        for name in ("Lark", "websockets.client", "httpcore.connection", "psycopg.pool"):
            logger = logging.getLogger(name)
            logger.error("CANARY_PRIVATE_PAYLOAD wss://probe.invalid/?credential=CANARY_PRIVATE")
    assert "CANARY_PRIVATE" not in caplog.text
    assert capsys.readouterr() == ("", "")


def test_official_sdk_http_requests_have_client_token_fields_and_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def request(method: str, url: str, **kwargs: Any) -> SimpleNamespace:
        calls.append({"method": method, "url": url, **kwargs})
        data: dict[str, Any] = (
            {"items": [], "has_more": False}
            if method == "GET"
            else {"record": {"record_id": "probe-record", "fields": {"ProbeID": "sample"}}}
        )
        return SimpleNamespace(
            status_code=200, headers={}, content=json.dumps({"code": 0, "data": data}).encode()
        )

    monkeypatch.setattr(requests, "request", request)
    client = lark.Client.builder().enable_set_token(True).timeout(2.0).build()
    option = lark.RequestOption.builder().tenant_access_token("REDACTED").build()
    transport = RecordSDK(client, option=option)
    token = str(uuid4())
    assert transport.create("probe-base", "probe-table", token, {"ProbeID": "sample"}).success
    assert transport.list("probe-base", "probe-table", "page-2").success
    assert transport.update(
        "probe-base", "probe-table", "probe-record", {"State": "updated"}
    ).success
    assert [call["method"] for call in calls] == ["POST", "GET", "PUT"]
    assert dict(calls[0]["params"])["client_token"] == token
    assert json.loads(calls[0]["data"])["fields"]["ProbeID"] == "sample"
    assert dict(calls[1]["params"])["page_token"] == "page-2"  # noqa: S105 - synthetic cursor
    assert dict(calls[1]["params"])["page_size"] == "100"
    assert calls[2]["url"].endswith("/records/probe-record")
    assert all(call["timeout"] == 2.0 for call in calls)


@pytest.mark.parametrize(
    "status,code", [(200, 1254291), (500, 0), (200, None), (200, False), (True, 0)]
)
def test_http_and_business_code_are_both_required(status: Any, code: Any) -> None:
    assert not ApiReply(status, code, {}).success
