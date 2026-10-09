import json
from types import SimpleNamespace
from typing import Any, cast

import lark_oapi as lark  # type: ignore[import-untyped]
import pytest
import requests
from commerceops.adapters.feishu.base import BaseProbe
from lark_oapi.core.model import RequestOption  # type: ignore[import-untyped]

from scripts.feishu_probe_harness.base_http_deadline import DeadlineQueryOnlySDK
from scripts.feishu_probe_harness.base_query import query_only

from .support import fixture

pytestmark = pytest.mark.offline


def transport(clock: Any, deadline: Any = 30) -> Any:
    store, sdk, pid, probe, _, fields, _ = fixture()
    probe.prepare(pid, *probe.target, fields)
    store.row["status"] = "unknown"
    store.queries.clear()
    t = DeadlineQueryOnlySDK(sdk, pid, probe.target, deadline, clock=clock)
    p = BaseProbe(store.connection, probe.scope, t, target=probe.target)
    return (store, sdk, pid, p, t, fields)


@pytest.mark.parametrize("now,expected", [(0, 5), (18, 5), (21, 3), (23.8, 0.2)])
def test_public_HTTP_wait_max5_recomputed_with_remaining_normal_deadline(
    monkeypatch: Any, now: Any, expected: Any
) -> None:
    _, _, _, _, t, _ = transport(lambda: now)
    seen: list[Any] = []
    response = SimpleNamespace(status_code=200)

    def original(*args: Any, **kwargs: Any) -> Any:
        wait = kwargs["timeout"]
        seen.append(wait)
        assert wait.total == pytest.approx(expected)
        assert wait.connect_timeout == pytest.approx(expected)
        return response

    monkeypatch.setattr(requests, "request", original)
    with t.public_HTTP_deadline():
        assert (
            cast(Any, requests.request)(
                object(), object(), headers=object(), data=object(), timeout=2
            )
            is response
        )
    assert requests.request is original and len(seen) == 1
    assert t.http_wait_records == [
        dict(
            stage="PUBLIC_HTTP_WITHIN_LIST_SERVICE",
            wait_budget_seconds=pytest.approx(expected),
            http_status=200,
            exception_category=None,
            raw_values_recorded=False,
        )
    ]


def test_multiple_HTTPs_inside_single_SDK_method_each_remaining_budget_clamped(
    monkeypatch: Any,
) -> None:
    clock = SimpleNamespace(now=18)
    _, _, _, _, t, _ = transport(lambda: clock.now)
    seconds: list[Any] = []

    def original(*a: Any, **k: Any) -> Any:
        seconds.append(k["timeout"].total)
        clock.now += 4
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr(requests, "request", original)
    with t.public_HTTP_deadline():
        cast(Any, requests.request)(object(), object(), timeout=2)
        with pytest.raises(TimeoutError):
            cast(Any, requests.request)(object(), object(), timeout=2)
    assert seconds == [5, 2] and requests.request is original
    assert t.http_wait_records[1]["exception_category"] == "DEADLINE_OR_TIMEOUT"


@pytest.mark.parametrize("now", [24, 24.1, 30])
def test_no_HTTP_offer_at_or_after_normal_deadline(monkeypatch: Any, now: Any) -> None:
    _, _, _, _, t, _ = transport(lambda: now)
    calls: list[Any] = []

    def original(*a: Any, **k: Any) -> Any:
        calls.append(True)

    monkeypatch.setattr(requests, "request", original)
    with t.public_HTTP_deadline():
        with pytest.raises(TimeoutError):
            cast(Any, requests.request)(object(), object(), timeout=2)
    assert calls == [] and t.http_wait_records == [] and (requests.request is original)


def test_public_HTTP_exception_same_object_no_message_repr_or_request_values(
    monkeypatch: Any,
) -> None:

    class HostileTimeout(requests.exceptions.ReadTimeout):
        def __str__(self: Any) -> Any:
            raise AssertionError("FORBIDDEN_MESSAGE")

        def __repr__(self: Any) -> Any:
            raise AssertionError("FORBIDDEN_REPR")

    _, _, _, _, t, _ = transport(lambda: 0)
    error = HostileTimeout("SYNTHETIC_PRIVATE_CANARY")

    def original(*a: Any, **k: Any) -> Any:
        raise error

    monkeypatch.setattr(requests, "request", original)
    with t.public_HTTP_deadline():
        with pytest.raises(HostileTimeout) as captured:
            cast(Any, requests.request)(object(), object(), timeout=2)
    assert captured.value is error and requests.request is original
    assert t.http_wait_records[0]["exception_category"] == "READ_TIMEOUT"
    assert "SYNTHETIC_PRIVATE_CANARY" not in json.dumps(t.http_wait_records)


@pytest.mark.parametrize("failure", [None, "timeout", "missing", "duplicate", "page3"])
def test_public_SDK_original_query_only_fixed_key_HTTP5_full_fields_or_unknown_stop(
    monkeypatch: Any, failure: Any
) -> None:
    store, sdk, pid, p, t, fields = transport(lambda: 0, 9999999999)
    token, digest = (store.row["client_token"], store.row["request_sha256"])
    calls: list[Any] = []

    def request(method: Any, url: Any, **kwargs: Any) -> Any:
        calls.append(True)
        assert kwargs["timeout"].total == 5
        if failure == "timeout":
            raise requests.exceptions.ReadTimeout("SYNTHETIC_PRIVATE_CANARY")
        items = [] if failure == "missing" else [dict(record_id="rec_synthetic", fields=fields)]
        if failure == "duplicate":
            items.append(dict(record_id="rec_synthetic2", fields=fields))
        data = dict(
            items=items, has_more=failure == "page3", page_token="synthetic_next_" + str(len(calls))
        )
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(dict(code=0, msg="synthetic_success", data=data)).encode()
        return response

    monkeypatch.setattr(requests, "request", request)
    client = (
        lark.Client.builder()
        .app_id("synthetic_app")
        .app_secret("synthetic_secret")
        .enable_set_token(True)
        .timeout(2)
        .build()
    )
    t.client = client
    t.option = RequestOption.builder().tenant_access_token("synthetic_token").build()
    result = query_only(p, t, pid, fields)
    assert result["reconcile_status"] == (
        "succeeded" if failure is None else "conflict" if failure == "duplicate" else "unknown"
    )
    assert t.counts["create"] == t.counts["update"] == 0 and t.counts["list"] <= 2
    assert len(calls) <= 2 and requests.request is request and (store.locked == 0)
    assert store.row["client_token"] == token and store.row["request_sha256"] == digest
    assert not any(q.lstrip().startswith("INSERT") for q in store.queries)
    assert all(
        v not in json.dumps(result) for v in (str(token), str(pid), "SYNTHETIC_PRIVATE_CANARY")
    )


def test_original_live_client_public_builder_and_guard_remain_timeout2(monkeypatch: Any) -> None:
    import commerceops.entrypoints.feishu_probe as entry

    calls: list[Any] = []

    class Builder:
        def app_id(self: Any, value: Any) -> Any:
            return self

        def app_secret(self: Any, value: Any) -> Any:
            return self

        def timeout(self: Any, value: Any) -> Any:
            calls.append(value)
            return self

        def build(self: Any) -> Any:
            return SimpleNamespace(
                request=lambda request: SimpleNamespace(
                    raw=SimpleNamespace(
                        status_code=200, content=b'{"bot":{"open_id":"ou_synthetic_bot"}}'
                    ),
                    code=0,
                )
            )

    monkeypatch.setattr(lark.Client, "builder", lambda: Builder())
    settings = SimpleNamespace(
        app_id="cli_synthetic",
        bot_open_id="ou_synthetic_bot",
        secret=lambda: SimpleNamespace(get_secret_value=lambda: "SYNTHETIC_SECRET"),
    )
    cast(Any, entry.live_client)(settings)
    assert calls == [2.0]


def test_HTTP_boundary_only_list_scope_outside_default2_restored(monkeypatch: Any) -> None:
    _, _, _, _, t, _ = transport(lambda: 0)
    values: list[Any] = []

    def original(*args: Any, **kwargs: Any) -> Any:
        timeout = kwargs["timeout"]
        values.append(timeout.total if hasattr(timeout, "total") else timeout)
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr(requests, "request", original)
    cast(Any, requests.request)(object(), object(), timeout=2)
    with t.public_HTTP_deadline():
        cast(Any, requests.request)(object(), object(), timeout=2)
    cast(Any, requests.request)(object(), object(), timeout=2)
    assert values == [2, 5, 2] and requests.request is original


def test_Timeout_object_supported_by_public_Requests_session_send_boundary(
    monkeypatch: Any,
) -> None:
    _, _, _, _, t, _ = transport(lambda: 21)
    original = requests.request
    calls: list[Any] = []

    def send(self: Any, request: Any, **kwargs: Any) -> Any:
        timeout = kwargs["timeout"]
        calls.append(timeout.total)
        assert timeout.total == 3 and timeout.connect_timeout == 3
        response = requests.Response()
        response.status_code = 200
        response._content = b"synthetic response"
        return response

    monkeypatch.setattr(requests.Session, "send", send)
    with t.public_HTTP_deadline():
        assert (
            cast(Any, requests.request)("GET", "https://synthetic.invalid", timeout=2).status_code
            == 200
        )
    assert calls == [3] and requests.request is original
