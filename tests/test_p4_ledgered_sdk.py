"""六method实际调用边界：ledger拒绝0delegate/原参数对象透传/异常不自动重试。"""

import asyncio
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any

import pytest
from commerceops.adapters.feishu.ledgered_sdk import ledgered_client
from commerceops.application.feishu_business.sdk_calls import SDKMethod

pytestmark = pytest.mark.offline


class Ledger:
    def __init__(self, *, denied: bool = False):
        self.denied = denied
        self.methods: list[SDKMethod] = []

    async def invoke(self, method: SDKMethod, call: Callable[[], Awaitable[Any]]) -> Any:
        if self.denied:
            raise PermissionError("SDK_WINDOW_CLOSED")
        self.methods.append(method)
        return await call()


def setup(*, raises: bool = False) -> tuple[Any, list[tuple[object, object]], object]:
    calls: list[tuple[object, object]] = []
    result = object()

    async def invoke(request: object, option: object) -> object:
        calls.append((request, option))
        if raises:
            raise TimeoutError("controlled SDK timeout")
        return result

    raw = SimpleNamespace(
        im=SimpleNamespace(v1=SimpleNamespace(message=SimpleNamespace(acreate=invoke))),
        bitable=SimpleNamespace(
            v1=SimpleNamespace(
                app_table_record=SimpleNamespace(acreate=invoke, alist=invoke, aupdate=invoke),
                app_table=SimpleNamespace(alist=invoke),
                app_table_field=SimpleNamespace(alist=invoke),
            )
        ),
    )
    return raw, calls, result


def test_six_narrow_sdk_methods_require_ledger_and_keep_original_request_option_response() -> None:
    async def run() -> None:
        raw, calls, result = setup()
        ledger = Ledger()
        client = ledgered_client(raw, ledger)
        request, option = object(), object()
        for function in (
            client.im.v1.message.acreate,
            client.bitable.v1.app_table_record.acreate,
            client.bitable.v1.app_table_record.alist,
            client.bitable.v1.app_table_record.aupdate,
            client.bitable.v1.app_table.alist,
            client.bitable.v1.app_table_field.alist,
        ):
            assert await function(request, option) is result
        assert len(calls) == 6 and all(a is request and b is option for a, b in calls)
        assert ledger.methods == [
            "im.v1.message.create",
            "bitable.v1.app_table_record.create",
            "bitable.v1.app_table_record.list",
            "bitable.v1.app_table_record.update",
            "bitable.v1.app_table.list",
            "bitable.v1.app_table_field.list",
        ]
        assert not hasattr(client, "contact") and not hasattr(client, "drive")

    asyncio.run(run())


def test_denied_window_never_enters_raw_method_and_timeout_has_no_automatic_retry() -> None:
    async def run() -> None:
        raw, calls, _ = setup(raises=True)
        denied = Ledger(denied=True)
        client = ledgered_client(raw, denied)
        with pytest.raises(PermissionError, match="SDK_WINDOW_CLOSED"):
            await client.bitable.v1.app_table_record.acreate(object())
        assert calls == [] and denied.methods == []
        allowed = Ledger()
        client = ledgered_client(raw, allowed)
        with pytest.raises(TimeoutError):
            await client.im.v1.message.acreate(object())
        assert len(calls) == len(allowed.methods) == 1

    asyncio.run(run())
