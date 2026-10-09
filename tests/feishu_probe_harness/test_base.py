import json
from typing import Any
from uuid import uuid4

import pytest
from commerceops.adapters.feishu.base import request_hash

from scripts.feishu_probe_harness.base_live_core import ScopedRecordSDK, run_crud

from .support import fixture

pytestmark = pytest.mark.offline


def test_default_original_CRUD_fixed_key_hash_same_table_and_sdk_real_calls() -> None:
    store, sdk, pid, probe, transport, fields, updated = fixture()
    result = run_crud(probe, transport, pid, fields, updated)
    assert result["state"] == "BASE_CRUD_FIELDS_READBACK_VERIFIED_NOT_GATE"
    assert [m for m, _ in sdk.calls] == ["create", "list", "update", "list"]
    assert store.row["client_token"].version == 4 and store.row["request_sha256"] == request_hash(
        transport.target[0], transport.target[1], fields
    )
    assert store.row["pending_fields"] == updated and store.row["pending_sha256"] == request_hash(
        transport.target[0], transport.target[1], updated
    )
    assert store.locked == 0 and result["persistent_token_unchanged"] is True
    assert result["original_key_second_real_SDK_create_executed"] is False
    assert result["success_replay_extension"] == "UNAPPROVED_ACTUAL_EXTENSION_NOT_ARMED"
    text = json.dumps(result)
    assert (
        "rec_synthetic" not in text
        and "app_synthetic" not in text
        and (str(pid) not in text)
        and ("PRIVATE_CANARY" not in text)
    )


@pytest.mark.parametrize(
    "failure",
    [
        "create_unknown",
        "update_unknown",
        "HTTP_500",
        "known_rejection",
        "foreign_row",
        "duplicate_row",
        "missing_row",
        "content_mismatch",
        "infinite_pagination",
        "wrong_update_record",
    ],
)
def test_unknown_mismatch_rejection_stops_keeps_original_key_and_no_blind_retry(
    failure: Any,
) -> None:
    store, sdk, pid, probe, transport, fields, updated = fixture(failure)
    result = run_crud(probe, transport, pid, fields, updated)
    assert result["state"] != "BASE_CRUD_FIELDS_READBACK_VERIFIED_NOT_GATE"
    assert (
        store.row["client_token"].version == 4
        and transport.fixed_token == store.row["client_token"]
    )
    assert (
        sum((m == "create" for m, _ in sdk.calls)) == 1
        and sum((m == "update" for m, _ in sdk.calls)) <= 1
    )
    assert transport.counts["list"] <= 4 and store.locked == 0
    if failure in ("create_unknown", "update_unknown"):
        assert result["state"] == "STOPPED_UNKNOWN_OR_RECONCILED_PARTIAL"
    if failure == "known_rejection":
        assert len(sdk.calls) == 1 and store.row["status"] == "blocked"


def test_succeeded_cache_is_not_real_second_sdk_call_or_replay_evidence() -> None:
    store, sdk, pid, probe, transport, fields, updated = fixture()
    token = probe.prepare(pid, *transport.target, fields)
    transport.bind_token(token)
    assert probe.create_once(pid) == "succeeded"
    assert probe.create_once(pid) == "succeeded"
    assert [m for m, _ in sdk.calls] == ["create"]
    assert probe.prepare(pid, *transport.target, fields) == token


def test_scoped_transport_caps_target_token_update_anchor_and_deadline() -> None:
    store, sdk, pid, probe, t, fields, updated = fixture()
    token = probe.prepare(pid, *t.target, fields)
    t.bind_token(token)
    with pytest.raises(ValueError):
        t.create("foreign", "table_synthetic", str(token), fields)
    with pytest.raises(ValueError):
        t.create(*t.target, str(uuid4()), fields)
    with pytest.raises(ValueError):
        t.update(*t.target, "foreign_row", updated)
    expired = ScopedRecordSDK(sdk, pid, t.target, 10, clock=lambda: 5)
    with pytest.raises(ValueError):
        expired.list(t.target[0], t.target[1], None)
