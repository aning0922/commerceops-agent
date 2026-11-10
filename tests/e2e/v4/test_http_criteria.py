"""Offline decision tests only; no HTTP/PG/mocked network Gate evidence."""

import copy
from typing import Any

import pytest

from .http_probe import capacity_rejection, concurrent_reset_result, receipt_binding
from .test_strict_response import KEY, TIME, check

pytestmark = pytest.mark.offline
OTHER = "8d643bb1-53da-4ee9-8b96-d76eb398069b"


def committed(operation: str = "reset", key: str = KEY) -> dict[str, Any]:
    return {
        "schema_version": "v4-demo-v1",
        "server_time": TIME,
        "trace_id": KEY,
        "status": "COMMITTED",
        "data": {
            "receipt": {
                "receipt_id": OTHER,
                "operation": operation,
                "request_key": key,
                "payload_digest": "a" * 64,
                "status": "COMMITTED",
                "committed_at": TIME,
                "reset_epoch": 1,
                "auth_generation": 1,
            }
        },
    }


def rejection(code: str = "CSRF_INVALID") -> dict[str, Any]:
    return {"error": {"code": code}}


@pytest.mark.parametrize(
    "code,wait",
    [
        ("RATE_LIMITED", "10"),
        ("CAPACITY_LIMIT", "0"),
        ("CAPACITY_LIMIT", "-1"),
        ("CAPACITY_LIMIT", None),
        ("CAPACITY_LIMIT", "1.5"),
        ("CAPACITY_LIMIT", "١"),
        ("CAPACITY_LIMIT", ""),
    ],
)
def test_noncapacity_or_invalid_wait_cannot_sign_capacity(code: str, wait: str | None) -> None:
    with pytest.raises(AssertionError):
        capacity_rejection(rejection(code), wait)


def test_exact_capacity_reason_with_positive_wait() -> None:
    capacity_rejection(rejection("CAPACITY_LIMIT"), "10")


@pytest.mark.parametrize("operation,key", [("persona", KEY), ("session_create", OTHER)])
def test_schema_valid_wrong_receipt_owner_is_rejected(operation: str, key: str) -> None:
    reply = committed(operation, key)
    check("readDemoControlReceipt", 200, reply)  # Format validity is deliberately insufficient.
    with pytest.raises(AssertionError, match="operation/key"):
        receipt_binding(reply, "session_create", KEY)


def test_receipt_binding_accepts_original_key() -> None:
    reply = committed("session_create")
    assert receipt_binding(reply, "session_create", KEY)["request_key"] == KEY


def test_minimal_bootstrap_branch_bound_to_create_key_only() -> None:
    reply = {
        "data": {
            "operation": "session_create",
            "request_key": KEY,
            "status": "COMMITTED",
            "recovery": "OWNER_RECOVERY_REQUIRED",
        }
    }
    assert receipt_binding(reply, "session_create", KEY)["status"] == "COMMITTED"
    with pytest.raises(AssertionError):
        receipt_binding(reply, "session_create", OTHER)
    reply["data"]["operation"] = "reset"
    with pytest.raises(AssertionError, match="session_create only"):
        receipt_binding(reply, "reset", KEY)


@pytest.mark.parametrize("reverse", [False, True])
def test_concurrent_one_commit_one_old_csrf_denial_is_legal(reverse: bool) -> None:
    outcomes = [(200, committed()), (403, rejection())]
    if reverse:
        outcomes.reverse()
    assert concurrent_reset_result(outcomes, KEY) == committed()["data"]["receipt"]


def test_concurrent_two_identical_commits_is_legal() -> None:
    assert concurrent_reset_result([(200, committed()), (200, committed())], KEY)


@pytest.mark.parametrize("code", ["ACCESS_DENIED", "ORIGIN_DENIED", "SESSION_INVALID"])
def test_other_denials_are_not_accepted_concurrency(code: str) -> None:
    with pytest.raises(AssertionError, match="unexpected"):
        concurrent_reset_result([(200, committed()), (403, rejection(code))], KEY)


def test_no_success_stays_unverified() -> None:
    with pytest.raises(AssertionError, match="UNKNOWN"):
        concurrent_reset_result([(403, rejection()), (403, rejection())], KEY)


def test_different_committed_receipts_are_rejected() -> None:
    different = copy.deepcopy(committed())
    different["data"]["receipt"]["receipt_id"] = KEY
    with pytest.raises(AssertionError, match="different receipt"):
        concurrent_reset_result([(200, committed()), (200, different)], KEY)
