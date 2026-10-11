"""锁定官方 SDK 的真实请求构造，HTTP 全部 Fake；认证/真 Base 未运行。"""

import asyncio
import json
from importlib.metadata import version
from types import SimpleNamespace
from typing import Any

import httpx
import lark_oapi as lark  # type: ignore[import-untyped]
import pytest
from commerceops.adapters.feishu.business_base import BusinessRecordSDK, operation_deadline
from commerceops.adapters.feishu.projection_contract import (
    BASE_FIELDS,
    ApiReply,
    ProjectionContractError,
)
from commerceops.adapters.feishu.projection_rules import WriteOutcome, write_outcome

from tests.test_p4_base_contract import sample, terminal

pytestmark = pytest.mark.offline
FIXED_TOKEN = "00000000-0000-4000-8000-000000000042"  # noqa: S105 - synthetic UUIDv4


def sdk() -> BusinessRecordSDK:
    client = lark.Client.builder().enable_set_token(True).timeout(2.0).build()
    option = lark.RequestOption.builder().tenant_access_token("REDACTED").build()
    return BusinessRecordSDK(client, option=option)


def test_locked_sdk_exact_business_columns_fixed_token_and_null_clearing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    async def request(self: Any, method: str, url: str, **kwargs: Any) -> SimpleNamespace:
        calls.append({"method": method, "url": url, **kwargs})
        data = (
            {"items": [], "has_more": False, "total": 0}
            if method == "GET"
            else {"record": {"record_id": "synthetic-row", "fields": sample().wire_fields()}}
        )
        return SimpleNamespace(
            status_code=200, headers={}, content=json.dumps({"code": 0, "data": data}).encode()
        )

    monkeypatch.setattr(httpx.AsyncClient, "request", request)
    transport = sdk()
    assert version("lark-oapi") == "1.7.3"
    assert write_outcome(
        asyncio.run(transport.create("test-base", "test-table", FIXED_TOKEN, sample()))
    ) == (WriteOutcome.ACKNOWLEDGED)
    assert asyncio.run(transport.list("test-base", "test-table", "synthetic-page-2")).success
    assert asyncio.run(
        transport.update("test-base", "test-table", "synthetic-row", sample())
    ).success
    assert asyncio.run(
        transport.update("test-base", "test-table", "synthetic-row", terminal())
    ).success
    assert [call["method"] for call in calls] == ["POST", "GET", "PUT", "PUT"]
    assert dict(calls[0]["params"])["client_token"] == FIXED_TOKEN
    assert dict(calls[0]["params"])["ignore_consistency_check"] == "False"
    body = calls[0]["json"]["fields"]
    assert set(body) == set(BASE_FIELDS)
    assert body["ResolvedAt"] is None
    query = dict(calls[1]["params"])
    assert json.loads(query["field_names"]) == list(BASE_FIELDS)
    assert query["page_size"] == "100"
    assert query["page_token"] == "synthetic-page-2"  # noqa: S105 - synthetic cursor
    assert query["text_field_as_array"] == "False"
    assert query["automatic_fields"] == "False"
    assert "view_id" not in query and "filter" not in query
    assert calls[2]["url"].endswith("/records/synthetic-row")
    assert calls[2]["json"]["fields"]["ResolutionReason"] is None
    assert calls[3]["json"]["fields"] == terminal().wire_fields()
    assert all(call["timeout"] == 2.0 for call in calls)


@pytest.mark.parametrize(
    "status,code,expected",
    [
        (200, 0, WriteOutcome.ACKNOWLEDGED),
        (200, 1254291, WriteOutcome.DEFERRED),
        (200, 1254290, WriteOutcome.DEFERRED),
        (429, 1254290, WriteOutcome.DEFERRED),
        (429, None, WriteOutcome.UNKNOWN),
        (429, 0, WriteOutcome.UNKNOWN),
        (500, 0, WriteOutcome.UNKNOWN),
        (503, 1254291, WriteOutcome.UNKNOWN),
        (200, 1254045, WriteOutcome.REJECTED),
        (200, 1254002, WriteOutcome.UNKNOWN),
        (200, 1255001, WriteOutcome.UNKNOWN),
        (200, 1255003, WriteOutcome.UNKNOWN),
        (200, 9999999, WriteOutcome.UNKNOWN),
        (403, 1254302, WriteOutcome.REJECTED),
        (400, 1255006, WriteOutcome.CONFLICT),
        (200, 1255006, WriteOutcome.CONFLICT),
        (504, 1255040, WriteOutcome.UNKNOWN),
        (400, 1254607, WriteOutcome.UNKNOWN),
        (403, 1254608, WriteOutcome.UNKNOWN),
        (200, None, WriteOutcome.UNKNOWN),
        (True, 0, WriteOutcome.UNKNOWN),
        (200, False, WriteOutcome.UNKNOWN),
    ],
)
def test_http_business_errors_are_sanitized_and_never_report_synced(
    status: Any,
    code: Any,
    expected: WriteOutcome,
) -> None:
    reply = ApiReply(status, code, {"record": {"record_id": "synthetic-row"}})
    assert write_outcome(reply) == expected


@pytest.mark.parametrize(
    "body",
    [
        b"not-json",
        b"[]",
        b'{"code":false}',
        b'{"code":1,"data":{}}',
        b'{"data":{}}',
        b"x" * (4 * 1024 * 1024 + 1),
    ],
)
def test_malformed_or_oversize_sdk_reply_cannot_create_ack(body: bytes) -> None:
    response = SimpleNamespace(code=0, raw=SimpleNamespace(status_code=200, content=body))
    reply = BusinessRecordSDK._reply(response)
    assert write_outcome(reply) == WriteOutcome.UNKNOWN


@pytest.mark.parametrize("value", [None, "", "old-resolution"])
def test_raw_readback_preserves_present_null_empty_or_old_value(value: Any) -> None:
    data = {"items": [{"fields": {"ResolutionReason": value}}]}
    response = SimpleNamespace(
        code=0,
        raw=SimpleNamespace(
            status_code=200,
            content=json.dumps({"code": 0, "data": data}).encode(),
        ),
    )
    reply = BusinessRecordSDK._reply(response)
    assert "ResolutionReason" in reply.data["items"][0]["fields"]
    assert reply.data["items"][0]["fields"]["ResolutionReason"] == value


def test_raw_readback_does_not_fabricate_missing_field() -> None:
    response = SimpleNamespace(
        code=0,
        raw=SimpleNamespace(
            status_code=200,
            content=b'{"code":0,"data":{"items":[{"fields":{}}]}}',
        ),
    )
    assert "ResolutionReason" not in BusinessRecordSDK._reply(response).data["items"][0]["fields"]


@pytest.mark.parametrize("data", [{}, {"record": {}}, {"record": {"record_id": ""}}])
def test_code_zero_without_record_receipt_is_unknown(data: dict[str, Any]) -> None:
    assert write_outcome(ApiReply(200, 0, data)) == WriteOutcome.UNKNOWN


@pytest.mark.parametrize("method", ["create", "list", "update"])
def test_timeout_exception_is_one_call_and_no_secret_or_payload_log(
    method: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = 0

    async def request(*args: Any, **kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("CANARY_PRIVATE_URL_PAYLOAD")

    monkeypatch.setattr(httpx.AsyncClient, "request", request)
    transport = sdk()
    if method == "create":
        reply = asyncio.run(transport.create("test-base", "test-table", FIXED_TOKEN, sample()))
    elif method == "list":
        reply = asyncio.run(transport.list("test-base", "test-table", None))
    else:
        reply = asyncio.run(
            transport.update("test-base", "test-table", "synthetic-row", terminal())
        )
    assert write_outcome(reply) == WriteOutcome.UNKNOWN
    assert calls == 1
    assert "CANARY_PRIVATE" not in caplog.text
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("token", ["", "not-uuid", "00000000-0000-1000-8000-000000000042"])
def test_create_requires_original_standard_uuidv4_before_network(
    token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("invalid token must not reach HTTP")

    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden)
    with pytest.raises(ProjectionContractError):
        asyncio.run(sdk().create("test-base", "test-table", token, sample()))


@pytest.mark.parametrize("method", ["create", "list", "update"])
def test_operation_deadline_cancels_inflight_http_and_never_retries(
    method: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    cancelled = False

    async def request(*args: Any, **kwargs: Any) -> None:
        nonlocal calls, cancelled
        calls += 1
        try:
            await asyncio.Event().wait()
        finally:
            cancelled = True

    monkeypatch.setattr(httpx.AsyncClient, "request", request)

    async def run() -> ApiReply:
        transport = sdk()
        deadline = asyncio.get_running_loop().time() + 0.02
        if method == "create":
            return await transport.create(
                "test-base", "test-table", FIXED_TOKEN, sample(), deadline=deadline
            )
        if method == "list":
            return await transport.list("test-base", "test-table", None, deadline=deadline)
        return await transport.update(
            "test-base", "test-table", "synthetic-row", terminal(), deadline=deadline
        )

    reply = asyncio.run(run())
    assert write_outcome(reply) == WriteOutcome.UNKNOWN
    assert calls == 1 and cancelled


def test_expired_operation_deadline_makes_zero_http_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("expired operation must not call HTTP")

    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden)

    async def run() -> None:
        deadline = asyncio.get_running_loop().time() - 1.0
        transport = sdk()
        assert not (
            await transport.create(
                "test-base", "test-table", FIXED_TOKEN, sample(), deadline=deadline
            )
        ).success
        assert not (
            await transport.list("test-base", "test-table", None, deadline=deadline)
        ).success
        assert not (
            await transport.update(
                "test-base", "test-table", "synthetic-row", terminal(), deadline=deadline
            )
        ).success

    asyncio.run(run())


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), "invalid"])
def test_invalid_or_extended_deadline_rejected(value: Any) -> None:
    async def run() -> None:
        with pytest.raises(ProjectionContractError):
            operation_deadline(value)
        with pytest.raises(ProjectionContractError):
            operation_deadline(asyncio.get_running_loop().time() + 11.0)

    asyncio.run(run())
