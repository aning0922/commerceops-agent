import copy
import json
from typing import Any

import lark_oapi as lark  # type: ignore[import-untyped]
import pytest
import requests
from commerceops.adapters.feishu.base import BaseProbe
from lark_oapi.core.model import RequestOption  # type: ignore[import-untyped]

from scripts.feishu_probe_harness.base_query import QueryOnlySDK, query_only, safe_category

from .support import fixture

pytestmark = pytest.mark.offline


def recovery(failure: Any = None, status: Any = "unknown") -> Any:
    store, sdk, pid, probe, _, fields, _ = fixture(failure)
    probe.prepare(pid, *probe.target, fields)
    store.row["status"] = status
    store.queries.clear()
    sdk.remote = copy.deepcopy(fields)
    transport = QueryOnlySDK(sdk, pid, probe.target, 9999999999)
    probe = BaseProbe(store.connection, probe.scope, transport, target=probe.target)
    return (store, sdk, pid, probe, transport, fields)


@pytest.mark.parametrize("status", ["unknown", "inflight"])
def test_unique_full_original_fields_recovers_original_key_and_stops(status: Any) -> None:
    store, sdk, pid, probe, t, fields = recovery(status=status)
    token, digest = (store.row["client_token"], store.row["request_sha256"])
    result = query_only(probe, t, pid, fields)
    assert result["state"] == "QUERY_ONLY_RECONCILED_STOPPED"
    assert store.row["status"] == "succeeded" and store.row["client_token"] == token
    assert store.row["request_sha256"] == digest and store.row["fields"] == fields
    assert [method for method, _ in sdk.calls] == ["list"]
    assert not any(query.lstrip().startswith("INSERT") for query in store.queries)
    assert result["SDK_calls"] == dict(create=0, list=1, update=0)
    assert result["followup_mutations"] is False and store.locked == 0
    encoded = json.dumps(result)
    assert all(
        value not in encoded
        for value in (str(token), str(pid), "app_synthetic", "table_synthetic", "rec_synthetic")
    )


@pytest.mark.parametrize(
    "failure,expected",
    [
        ("missing_row", "unknown"),
        ("duplicate_row", "conflict"),
        ("content_mismatch", "unknown"),
        ("foreign_row", "unknown"),
        ("infinite_pagination", "unknown"),
    ],
)
def test_inconclusive_never_create_update_prepare_new_key_or_retry(
    failure: Any, expected: Any
) -> None:
    store, sdk, pid, probe, t, fields = recovery(failure)
    token = store.row["client_token"]
    result = query_only(probe, t, pid, fields)
    assert result["state"] == "QUERY_ONLY_INCONCLUSIVE_STOPPED"
    assert result["reconcile_status"] == expected and store.row["client_token"] == token
    assert all((method == "list" for method, _ in sdk.calls))
    assert len(sdk.calls) <= 2 and store.locked == 0
    assert not any(query.lstrip().startswith("INSERT") for query in store.queries)


@pytest.mark.parametrize(
    "field", ["ProbeMarker", "SourceMode", "ApprovalMode", "State", "UpdatedAt"]
)
def test_remote_every_original_field_must_match(field: Any) -> None:
    store, sdk, pid, probe, t, fields = recovery()
    sdk.remote[field] = "synthetic_wrong_value"
    result = query_only(probe, t, pid, fields)
    assert result["reconcile_status"] in ("unknown", "conflict")
    assert result["state"] == "QUERY_ONLY_INCONCLUSIVE_STOPPED"


def test_second_page_complete_unique_readback_success() -> None:
    store, sdk, pid, probe, t, fields = recovery()
    calls: list[Any] = []

    def listing(request: Any, option: Any = None) -> Any:
        calls.append(request)
        assert store.locked == 1
        if request.page_token is None:
            return sdk.reply(dict(items=[], has_more=True, page_token="synthetic_next"))  # noqa: S106 -- Synthetic pagination.
        assert request.page_token == "synthetic_next"  # noqa: S105 -- Synthetic pagination.
        return sdk.reply(
            dict(items=[dict(record_id="rec_synthetic", fields=fields)], has_more=False)
        )

    sdk.list = listing
    result = query_only(probe, t, pid, fields)
    assert result["reconcile_status"] == "succeeded" and len(calls) == 2
    assert result["SDK_calls"] == dict(create=0, list=2, update=0)


@pytest.mark.parametrize("status", ["ready", "succeeded", "blocked", "conflict"])
def test_status_outside_original_unknown_rejected_before_sdk(status: Any) -> None:
    store, sdk, pid, probe, t, fields = recovery(status=status)
    with pytest.raises(ValueError):
        query_only(probe, t, pid, fields)
    assert sdk.calls == [] and t.counts == dict(create=0, list=0, update=0)


def test_preexisting_update_or_changed_target_hash_rejected_before_sdk() -> None:
    store, sdk, pid, probe, t, fields = recovery()
    store.row["pending_kind"] = "update"
    store.row["pending_fields"] = fields
    store.row["pending_sha256"] = "synthetic_wrong_hash"
    with pytest.raises(ValueError):
        query_only(probe, t, pid, fields)
    assert sdk.calls == []


def test_mutator_transport_routes_blocked_before_sdk_and_no_new_key() -> None:
    store, sdk, pid, probe, t, fields = recovery()
    t.bind_token(store.row["client_token"])
    with pytest.raises(ValueError):
        t.create(*t.target, str(t.fixed_token), fields)
    with pytest.raises(ValueError):
        t.update(*t.target, "rec_synthetic", fields)
    assert sdk.calls == [] and t.counts == dict(create=0, list=0, update=0)


@pytest.mark.parametrize(
    "kind,label",
    [
        (requests.exceptions.SSLError, "TLS_FAILURE"),
        (requests.exceptions.ConnectTimeout, "CONNECT_TIMEOUT"),
        (requests.exceptions.ReadTimeout, "READ_TIMEOUT"),
        (requests.exceptions.Timeout, "REQUEST_TIMEOUT"),
        (requests.exceptions.ConnectionError, "CONNECTION_FAILURE"),
        (AttributeError, "SDK_DTO_ATTRIBUTE_EXCEPTION"),
        (TypeError, "SDK_DTO_TYPE_EXCEPTION"),
        (ValueError, "VALUE_OR_VALIDATION_EXCEPTION"),
        (RuntimeError, "OTHER_UNKNOWN_EXCEPTION"),
    ],
)
def test_fixed_safe_exception_category_original_object_no_string_inspection(
    kind: Any, label: Any
) -> None:

    class Hostile(kind):  # type: ignore[misc]  # Parameterized synthetic exception.
        def __str__(self: Any) -> Any:
            raise AssertionError("MESSAGE_READ_FORBIDDEN")

        def __repr__(self: Any) -> Any:
            raise AssertionError("REPR_READ_FORBIDDEN")

    store, sdk, pid, probe, t, fields = recovery()
    error = Hostile("PRIVATE_SYNTHETIC_CANARY")

    def listing(*a: Any, **k: Any) -> Any:
        raise error

    sdk.list = listing
    assert safe_category(error) == label
    t.bind_token(store.row["client_token"])
    with pytest.raises(Hostile) as captured:
        t.list(t.target[0], t.target[1], None)
    assert captured.value is error
    assert t.safe_exceptions == [dict(stage="PUBLIC_SDK_LIST_METHOD", category=label)]
    assert "PRIVATE_SYNTHETIC_CANARY" not in json.dumps(t.safe_exceptions)


def test_original_dal_swallows_exception_as_unknown_preserves_fixed_category() -> None:
    store, sdk, pid, probe, t, fields = recovery()

    def listing(*a: Any, **k: Any) -> Any:
        raise requests.exceptions.ReadTimeout("PRIVATE_SYNTHETIC_CANARY")

    sdk.list = listing
    result = query_only(probe, t, pid, fields)
    assert result["reconcile_status"] == "unknown"
    assert result["safe_exception_categories"] == [
        dict(stage="PUBLIC_SDK_LIST_METHOD", category="READ_TIMEOUT")
    ]
    assert result["SDK_calls"] == dict(create=0, list=1, update=0)
    assert "PRIVATE_SYNTHETIC_CANARY" not in json.dumps(result) and store.locked == 0


def test_full_public_sdk_list_method_http_serialization_without_network(monkeypatch: Any) -> None:
    store, sdk, pid, probe, _, fields = recovery()
    observed: list[Any] = []

    def request(method: Any, url: Any, **kwargs: Any) -> Any:
        observed.append((method, url, kwargs))
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(
            dict(
                code=0,
                msg="success",
                data=dict(items=[dict(record_id="rec_synthetic", fields=fields)], has_more=False),
            )
        ).encode()
        response.headers.clear()
        return response

    monkeypatch.setattr(requests, "request", request)
    client = (
        lark.Client.builder()
        .app_id("synthetic_app")
        .app_secret("synthetic_secret")
        .enable_set_token(True)
        .build()
    )
    t = QueryOnlySDK(client, pid, probe.target, 9999999999)
    t.option = RequestOption.builder().tenant_access_token("synthetic_access_token").build()
    p = BaseProbe(store.connection, probe.scope, t, target=probe.target)
    result = query_only(p, t, pid, fields)
    assert result["reconcile_status"] == "succeeded" and len(observed) == 1
    method, url, kwargs = observed[0]
    assert method == "GET" and url.endswith(
        "/open-apis/bitable/v1/apps/app_synthetic/tables/table_synthetic/records"
    )
    params = dict(kwargs["params"])
    assert params["page_size"] == "100"
    assert params["filter"] == 'AND(CurrentValue.[ProbeID]="' + str(pid) + '")'
    assert set(json.loads(params["field_names"])) == set(fields)
