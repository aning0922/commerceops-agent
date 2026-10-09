import copy
import json
from typing import Any
from uuid import uuid4

import lark_oapi as lark  # type: ignore[import-untyped]
import pytest
import requests
from commerceops.adapters.feishu.base import BaseProbe, request_hash
from lark_oapi.core.model import RequestOption  # type: ignore[import-untyped]

from scripts.feishu_probe_harness.base_closeout import (
    UpdateReadbackSDK,
    finish_base_closeout,
    finish_update_once,
)

from .support import fixture

pytestmark = pytest.mark.offline


def recovered(failure: Any = None) -> Any:
    store, sdk, pid, probe, _, fields, updated = fixture(failure)
    probe.prepare(pid, *probe.target, fields)
    store.row.update(status="succeeded", record_id="rec_synthetic")
    sdk.remote = copy.deepcopy(fields)
    store.queries.clear()
    t = UpdateReadbackSDK(sdk, pid, probe.target, 9999999999)
    p = BaseProbe(store.connection, probe.scope, t, target=probe.target)
    return (store, sdk, pid, p, t, fields, updated)


def test_update_once_preserves_original_fields_hash_key_and_anchor() -> None:
    s, sdk, pid, p, t, fields, updated = recovered()
    token, digest = (s.row["client_token"], s.row["request_sha256"])
    result = finish_update_once(p, t, pid, fields, updated)
    assert result["full_updated_six_fields_unique_original_record_verified"] is True
    assert [m for m, _ in sdk.calls] == ["update", "list"]
    assert t.counts == dict(create=0, list=1, update=1) and s.locked == 0
    assert s.row["client_token"] == token and s.row["request_sha256"] == digest
    assert s.row["fields"] == fields and s.row["pending_fields"] == updated
    assert s.row["pending_sha256"] == request_hash(t.target[0], t.target[1], updated)
    assert s.row["record_id"] == "rec_synthetic" and sdk.remote == updated
    assert not any(q.lstrip().startswith("INSERT") for q in s.queries)
    assert result["success_platform_create_replay_armed"] is False
    assert all(
        v not in json.dumps(result)
        for v in (str(pid), str(token), "rec_synthetic", "app_synthetic", "PRIVATE_CANARY")
    )


@pytest.mark.parametrize(
    "failure,verified",
    [
        ("update_unknown", True),
        ("wrong_update_record", True),
        ("missing_row", False),
        ("foreign_row", False),
        ("duplicate_row", False),
        ("content_mismatch", False),
        ("infinite_pagination", False),
    ],
)
def test_unknown_or_mismatch_single_controlled_query_stop_no_retry_create_or_new_key(
    failure: Any, verified: Any
) -> None:
    s, sdk, pid, p, t, fields, updated = recovered(failure)
    token = s.row["client_token"]
    result = finish_update_once(p, t, pid, fields, updated)
    assert result["full_updated_six_fields_unique_original_record_verified"] is verified
    assert sum((m == "update" for m, _ in sdk.calls)) == 1 and t.counts["list"] <= 2
    assert all((m in ("update", "list") for m, _ in sdk.calls)) and s.locked == 0
    assert s.row["client_token"] == token and result["followup_mutations"] is False
    assert result["success_platform_create_replay_armed"] is False
    if failure in ("update_unknown", "wrong_update_record"):
        assert (
            result["update_method_status"] == "unknown"
            and result["reconcile_status"] == "succeeded"
        )
    if failure == "duplicate_row":
        assert result["reconcile_status"] == "unknown"
        assert result["safe_exception_categories"] == [
            dict(stage="EXISTING_RECORD_ANCHOR_CHECK", category="RECORD_ANCHOR_MISMATCH")
        ]


@pytest.mark.parametrize(
    "change",
    [
        "unknown",
        "ready",
        "pending_update",
        "empty_anchor",
        "changed_hash",
        "changed_target",
        "changed_updated_probe",
    ],
)
def test_no_unsafe_resume_or_changed_binding_before_SDK(change: Any) -> None:
    s, sdk, pid, p, t, fields, updated = recovered()
    if change in ("unknown", "ready"):
        s.row["status"] = change
    elif change == "pending_update":
        s.row.update(
            pending_kind="update",
            pending_fields=updated,
            pending_sha256=request_hash(t.target[0], t.target[1], updated),
        )
    elif change == "empty_anchor":
        s.row["record_id"] = None
    elif change == "changed_hash":
        s.row["request_sha256"] = "0" * 64
    elif change == "changed_target":
        s.row["table_id"] = "foreign"
    else:
        updated = {**updated, "ProbeID": str(uuid4())}
    with pytest.raises(ValueError):
        finish_update_once(p, t, pid, fields, updated)
    assert sdk.calls == []


def test_created_already_updated_cannot_cache_as_real_update_evidence_or_retry() -> None:
    s, sdk, pid, p, t, fields, updated = recovered()
    finish_update_once(p, t, pid, fields, updated)
    with pytest.raises(ValueError):
        finish_update_once(p, t, pid, fields, updated)
    assert [m for m, _ in sdk.calls] == ["update", "list"]
    with pytest.raises(ValueError):
        t.update(*t.target, "rec_synthetic", updated)
    with pytest.raises(ValueError):
        t.create(*t.target, str(t.fixed_token), fields)
    assert [m for m, _ in sdk.calls] == ["update", "list"]


@pytest.mark.parametrize("failure", [None, "update_timeout", "query_timeout", "HTTP500"])
def test_public_SDK_real_request_types_update_default2_query5_original_full_roundtrip(
    monkeypatch: Any, failure: Any
) -> None:
    s, sdk, pid, p, t, fields, updated = recovered()
    calls: list[Any] = []
    remote = copy.deepcopy(fields)

    def request(method: Any, url: Any, **kw: Any) -> Any:
        calls.append(method)
        data: dict[str, Any]
        response = requests.Response()
        response.status_code = 500 if failure == "HTTP500" else 200
        if method == "PUT":
            assert kw["timeout"] == 2.0
            sent = json.loads(kw["data"])["fields"]
            assert sent == updated
            remote.update(sent)
            if failure == "update_timeout":
                raise requests.exceptions.ReadTimeout("SYNTHETIC_CANARY")
            data = dict(record=dict(record_id="rec_synthetic", fields=remote))
        else:
            assert method == "GET" and kw["timeout"].total == 5.0
            if failure == "query_timeout":
                raise requests.exceptions.ReadTimeout("SYNTHETIC_CANARY")
            data = dict(items=[dict(record_id="rec_synthetic", fields=remote)], has_more=False)
        response._content = json.dumps(dict(code=0, data=data)).encode()
        return response

    monkeypatch.setattr(requests, "request", request)
    t.client = (
        lark.Client.builder()
        .app_id("synthetic_app")
        .app_secret("synthetic_secret")
        .enable_set_token(True)
        .timeout(2.0)
        .build()
    )
    t.option = RequestOption.builder().tenant_access_token("synthetic_token").build()
    result = finish_update_once(p, t, pid, fields, updated)
    assert calls == ["PUT", "GET"] and requests.request is request
    assert result["full_updated_six_fields_unique_original_record_verified"] is (
        failure in (None, "update_timeout")
    )
    assert "SYNTHETIC_CANARY" not in json.dumps(result)


def replay_ready(failure: Any = None) -> Any:
    s, sdk, pid, p, _, fields, updated = recovered(failure)
    t = UpdateReadbackSDK(sdk, pid, p.target, 9999999999, success_replay_authorized=True)
    p = BaseProbe(s.connection, p.scope, t, target=p.target)
    return (s, sdk, pid, p, t, fields, updated)


def test_explicit_unarmed_optional_replay_safe_order_same_token_payload_then_update() -> None:
    s, sdk, pid, p, t, fields, updated = replay_ready()
    token = s.row["client_token"]
    result = finish_base_closeout(p, t, pid, fields, updated)
    assert [m for m, _ in sdk.calls] == ["list", "create", "list", "update", "list"]
    assert t.counts == dict(create=1, list=3, update=1)
    req = sdk.calls[1][1]
    assert req.client_token == str(token) and req.body.fields == fields
    assert s.row["client_token"] == token and s.row["record_id"] == "rec_synthetic"
    assert result["second_original_create_same_record_unique_full_fields_verified"] is True
    assert result["full_updated_six_fields_unique_original_record_verified"] is True
    assert sdk.remote == updated and s.locked == 0
    with pytest.raises(ValueError):
        t.create(*t.target, str(token), fields)
    assert [m for m, _ in sdk.calls].count("create") == 1


@pytest.mark.parametrize("failure", ["create_unknown", "known_rejection", "HTTP_500"])
def test_replay_unknown_or_rejection_may_query_once_but_never_update_even_if_recovered(
    failure: Any,
) -> None:
    s, sdk, pid, p, t, fields, updated = replay_ready(failure)
    result = finish_base_closeout(p, t, pid, fields, updated)
    assert [m for m, _ in sdk.calls] == ["list", "create", "list"]
    assert t.counts["update"] == 0 and t.counts["create"] == 1
    assert result["state"] == "REPLAY_STOPPED_BEFORE_UPDATE_NOT_GATE"
    assert result["success_platform_create_replay_status"] == "unknown"
    assert result["full_updated_six_fields_unique_original_record_verified"] is False
    assert s.row["pending_kind"] == "create" and s.locked == 0


@pytest.mark.parametrize(
    "failure",
    ["missing_row", "duplicate_row", "content_mismatch", "infinite_pagination", "foreign_row"],
)
def test_replay_current_remote_precheck_invalid_no_create_no_update(failure: Any) -> None:
    s, sdk, pid, p, t, fields, updated = replay_ready(failure)
    result = finish_base_closeout(p, t, pid, fields, updated)
    assert t.counts["create"] == t.counts["update"] == 0 and t.counts["list"] <= 2
    assert result["success_platform_create_replay_status"] == "not_attempted"
    assert result["followup_mutations"] is False


@pytest.mark.parametrize(
    "change", ["already_pending_update", "no_precheck_phase", "bad_updated_payload"]
)
def test_replay_cannot_follow_update_or_skip_current_row_precheck(change: Any) -> None:
    s, sdk, pid, p, t, fields, updated = replay_ready()
    if change == "already_pending_update":
        s.row.update(
            pending_kind="update",
            pending_fields=updated,
            pending_sha256=request_hash(t.target[0], t.target[1], updated),
        )
        with pytest.raises(ValueError):
            finish_base_closeout(p, t, pid, fields, updated)
    elif change == "bad_updated_payload":
        with pytest.raises(ValueError):
            finish_base_closeout(p, t, pid, fields, {**updated, "State": "created"})
    else:
        t.bind_token(s.row["client_token"])
        with pytest.raises(ValueError):
            t.create(*t.target, str(t.fixed_token), fields)
        with pytest.raises(ValueError):
            finish_update_once(p, t, pid, fields, updated)
    assert sdk.calls == []


def test_replay_postcheck_wrong_anchor_stops_no_update_or_delete() -> None:
    s, sdk, pid, p, t, fields, updated = replay_ready()
    old = sdk.list
    calls: list[Any] = []

    def listing(req: Any, option: Any = None) -> Any:
        calls.append(True)
        if len(calls) == 2:
            return sdk.reply(
                dict(items=[dict(record_id="rec_synthetic_wrong", fields=fields)], has_more=False)
            )
        return old(req, option)

    sdk.list = listing
    result = finish_base_closeout(p, t, pid, fields, updated)
    assert result["state"] == "REPLAY_STOPPED_BEFORE_UPDATE_NOT_GATE" and t.counts["update"] == 0
    assert s.row["record_id"] == "rec_synthetic" and (not any("DELETE " in q for q in s.queries))


def test_combined_replay_pre_and_post_paged_uses_budget_then_stops_before_update() -> None:
    s, sdk, pid, p, t, fields, updated = replay_ready()
    calls: list[Any] = []

    def listing(req: Any, option: Any = None) -> Any:
        calls.append(True)
        if req.page_token is None:
            return sdk.reply(dict(items=[], has_more=True, page_token="synthetic_next"))  # noqa: S106 -- Synthetic pagination.
        return sdk.reply(
            dict(items=[dict(record_id="rec_synthetic", fields=fields)], has_more=False)
        )

    sdk.list = listing
    result = finish_base_closeout(p, t, pid, fields, updated)
    assert len(calls) == 4 and t.counts == dict(create=1, list=4, update=0)
    assert (
        result["success_platform_create_replay_status"]
        == "succeeded_but_update_readback_budget_not_reserved"
    )
    assert s.row["status"] == "succeeded" and s.row["pending_kind"] == "create"


def test_original_default_closeout_calls_no_create_and_ambient_env_not_arming(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("P105_BASE_SUCCESS_REPLAY_AUTHORIZED", "true")
    s, sdk, pid, p, t, fields, updated = recovered()
    result = finish_base_closeout(p, t, pid, fields, updated)
    assert [m for m, _ in sdk.calls] == ["update", "list"]
    assert result["success_platform_create_replay_armed"] is False


def test_observed_duplicate_response_code_remains_unknown_and_does_not_update() -> None:
    store, sdk, pid, probe, transport, fields, updated = replay_ready()

    def repeated(request: Any, option: Any = None) -> Any:
        sdk.calls.append(("create", request))
        assert request.client_token == str(store.row["client_token"])
        assert request.body.fields == fields and store.locked == 1 and store.committed_inflight
        return sdk.reply({}, code=1254608, status=403)

    sdk.create = repeated
    result = finish_base_closeout(probe, transport, pid, fields, updated)
    assert transport.counts == dict(create=1, list=2, update=0)
    assert result["success_platform_create_replay_status"] == "unknown"
    assert result["state"] == "REPLAY_STOPPED_BEFORE_UPDATE_NOT_GATE"
    assert result["PG_status"] == "succeeded" and result["original_record_anchor_unchanged"]
    assert result["safe_HTTP_business_records"][1]["http_status"] == 403
    assert result["safe_HTTP_business_records"][1]["business_code"] == 1254608
