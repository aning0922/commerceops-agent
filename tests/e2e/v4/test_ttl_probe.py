"""Offline TTL authority/room checks; no real waiting, HTTP or PG execution."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from .owned_driver import Case
from .supervisor import Budget
from .test_owned_driver import case as case
from .ttl_probe import require_expired, stamp, verify_ttl

pytestmark = pytest.mark.offline


def facts() -> dict[str, Any]:
    now = datetime.now(UTC)
    return dict(
        tenant_id="tenant-test",
        created_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=30)).isoformat(),
        session_created_at=now.isoformat(),
        session_expires_at=(now + timedelta(minutes=30)).isoformat(),
        db_utc=now.isoformat(),
        tenant_revoked=False,
        session_revoked=False,
    )


def budget(end: datetime) -> Budget:
    return Budget.bind(datetime.now(UTC) - timedelta(seconds=1), end)


def test_natural_thirty_minutes_requires_extra_observation_and_cleanup_room() -> None:
    row = facts()
    expiry = stamp(row["expires_at"])
    assert (
        verify_ttl(row, "tenant-test", row["expires_at"], budget(expiry + timedelta(minutes=4)))
        == expiry
    )


@pytest.mark.parametrize("minutes", [1, 29, 31])
def test_short_or_altered_ttl_never_signs_natural_thirty(minutes: int) -> None:
    row = facts()
    row["expires_at"] = (stamp(row["created_at"]) + timedelta(minutes=minutes)).isoformat()
    with pytest.raises(AssertionError):
        verify_ttl(
            row, "tenant-test", row["expires_at"], budget(datetime.now(UTC) + timedelta(minutes=45))
        )


def test_no_implicit_extension_when_cleanup_room_insufficient() -> None:
    row = facts()
    with pytest.raises(TimeoutError):
        verify_ttl(
            row,
            "tenant-test",
            row["expires_at"],
            budget(stamp(row["expires_at"]) + timedelta(seconds=239)),
        )


@pytest.mark.parametrize("field", ["session_created_at", "session_expires_at"])
def test_tenant_session_timestamp_mismatch_refused(field: str) -> None:
    row = facts()
    row[field] = (stamp(row[field]) + timedelta(seconds=1)).isoformat()
    with pytest.raises(AssertionError):
        verify_ttl(
            row, "tenant-test", row["expires_at"], budget(datetime.now(UTC) + timedelta(minutes=45))
        )


def test_unrelated_auth_denial_is_not_ttl_evidence() -> None:
    with pytest.raises(AssertionError):
        require_expired({"error": {"code": "CSRF_INVALID"}})
    require_expired({"error": {"code": "SESSION_INVALID"}})


def test_naive_timestamp_is_not_db_utc() -> None:
    with pytest.raises(ValueError):
        stamp("2026-11-03T00:00:00")


@pytest.mark.parametrize(
    "scenario,seconds,accepted",
    [
        ("natural_ttl", 2700, True),
        ("natural_ttl", 2701, False),
        ("lifecycle", 1800, True),
        ("lifecycle", 1801, False),
    ],
)
def test_window_extension_is_exclusive_to_natural_ttl(
    case: Case,
    scenario: str,
    seconds: int,
    accepted: bool,
) -> None:
    changed = replace(
        case,
        scenario=scenario,
        deadline=(stamp(case.starts_at) + timedelta(seconds=seconds)).isoformat(),
    )
    if accepted:
        changed.validate()
    else:
        with pytest.raises(ValueError):
            changed.validate()
