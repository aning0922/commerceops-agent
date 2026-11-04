"""Offline DTO examples only; never evidence of HTTP, PG or browser execution."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from .strict_response import validate_response
from .supervisor import Budget

pytestmark = pytest.mark.offline
KEY = "d659abdc-0f84-4a89-ab97-1b7ac2f82d47"
TIME = "2026-11-03T12:00:00Z"


def check(operation: str, status: int, payload: dict[str, Any]) -> None:
    now = datetime.now(UTC)
    window = Budget.bind(now - timedelta(seconds=1), now + timedelta(minutes=5))
    validate_response(operation, status, payload, window)


def bootstrap() -> dict[str, Any]:
    return {
        "schema_version": "v4-demo-v1",
        "server_time": TIME,
        "trace_id": KEY,
        "status": "OK",
        "data": {
            "csrf_token": "new-offline-example-only",
            "expires_at": TIME,
            "state": "anonymous_bootstrap",
        },
    }


def test_bootstrap_matches_frozen_strict_schema() -> None:
    check("bootstrap", 200, bootstrap())


@pytest.mark.parametrize(
    "change",
    [
        {"extra": "forbidden"},
        {"trace_id": "invalid-uuid"},
        {"server_time": "not-db-time"},
        {"schema_version": "wrong"},
        {"data": {"csrf_token": "only-one-field"}},
    ],
)
def test_invalid_bootstrap_is_rejected(change: dict[str, Any]) -> None:
    with pytest.raises(AssertionError, match="strict"):
        check("bootstrap", 200, {**bootstrap(), **change})


def test_minimal_bootstrap_recovery_never_exposes_tenant() -> None:
    response = {
        "schema_version": "v4-demo-v1",
        "server_time": TIME,
        "trace_id": KEY,
        "status": "COMMITTED",
        "data": {
            "operation": "session_create",
            "request_key": KEY,
            "status": "COMMITTED",
            "recovery": "OWNER_RECOVERY_REQUIRED",
        },
    }
    check("readDemoControlReceipt", 200, response)
    response["data"]["tenant_id"] = KEY  # type: ignore[index]
    with pytest.raises(AssertionError, match="strict"):
        check("readDemoControlReceipt", 200, response)


def test_db_failure_allows_null_time_but_never_retryable_post() -> None:
    response: dict[str, Any] = {
        "schema_version": "v4-demo-v1",
        "server_time": None,
        "trace_id": KEY,
        "status": "UNKNOWN",
        "error": {
            "code": "SERVICE_UNAVAILABLE",
            "safe_message": "unavailable",
            "retryable": False,
            "request_key": KEY,
        },
    }
    check("resetCurrentDemoTenant", 503, response)
    response["error"]["retryable"] = True
    with pytest.raises(AssertionError, match="strict"):
        check("resetCurrentDemoTenant", 503, response)


def test_unlisted_operation_status_never_passes() -> None:
    with pytest.raises(AssertionError, match="strict"):
        check("bootstrap", 299, bootstrap())
