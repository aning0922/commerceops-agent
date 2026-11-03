"""Offline TTL authority/room checks; no real waiting, HTTP or PG execution."""

import json
import signal
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from .owned_driver import Case
from .preflight import ROOT
from .supervisor import Budget
from .test_owned_driver import case as case
from .ttl_probe import persist, require_expired, stamp, verify_ttl

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


@pytest.mark.parametrize("termination", ["sigterm", "python_error"])
def test_complete_child_interrupt_retains_initial_unknown_without_success(
    tmp_path: Path,
    termination: str,
) -> None:
    script = r"""
import os,signal,sys
from pathlib import Path
from datetime import UTC,datetime,timedelta
from tests.e2e.v4 import ttl_probe as t
from tests.e2e.v4.supervisor import Budget
now=datetime.now(UTC);expiry=now+timedelta(minutes=30)
facts=dict(tenant_id="synthetic",created_at=now.isoformat(),expires_at=expiry.isoformat(),
 session_created_at=now.isoformat(),session_expires_at=expiry.isoformat(),db_utc=now.isoformat(),
 tenant_revoked=False,session_revoked=False)
class Visitor:
 def __init__(self,*args):pass
 def create(self):return {"context":{"tenant_id":"synthetic"},"data":{
  "creation_request_key":"synthetic-original-key","expires_at":expiry.isoformat()}}
 def close(self):pass
class Adapter:
 def ttl_facts(self,tenant):return dict(facts)
def stop(*args):
 if sys.argv[2]=="sigterm":os.kill(os.getpid(),signal.SIGTERM)
 raise TimeoutError("synthetic interrupt at long wait")
t.Visitor=Visitor;t.wait_monotonic=stop
try:
 t.run_natural_ttl("http://unused","http://unused",Budget.bind(now,now+timedelta(minutes=45)),
  Adapter(),Path(sys.argv[1])/"natural_ttl.safe.json")
except BaseException:
 raise SystemExit(1) from None
"""
    child = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), termination],
        cwd=ROOT,
        env={},
        capture_output=True,
        timeout=5,
        check=False,
    )
    assert child.returncode == (-signal.SIGTERM if termination == "sigterm" else 1)
    initial = tmp_path / "natural_ttl.initial.safe.json"
    row = json.loads(initial.read_text())
    assert row["status"] == "UNKNOWN" and row["initial"]["expires_at"]
    assert row["request_key"] == "synthetic-original-key"
    assert not (tmp_path / "natural_ttl.success.safe.json").exists()
    assert initial.stat().st_mode & 0o777 == 0o600
    assert all("NATURAL_TTL_OBSERVED" not in path.read_text() for path in tmp_path.glob("*.json"))


def test_stage_documents_are_exclusive_and_not_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "initial.json"
    persist(path, {"status": "UNKNOWN"})
    with pytest.raises(FileExistsError):
        persist(path, {"status": "should-not-replace"})
    assert json.loads(path.read_text()) == {"status": "UNKNOWN"}
