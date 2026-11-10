"""Single natural 30-minute expiry observation; no TTL override or background worker."""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .http_probe import PREFIX, Visitor
from .owned_adapter import OwnedAdapter
from .supervisor import Budget


def stamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() != timedelta(0):
        raise ValueError("authoritative UTC timestamp required")
    return parsed


def verify_ttl(
    facts: dict[str, Any], tenant: str, declared_expiry: str, budget: Budget
) -> datetime:
    if (
        set(facts)
        != {
            "tenant_id",
            "created_at",
            "expires_at",
            "session_created_at",
            "session_expires_at",
            "db_utc",
            "tenant_revoked",
            "session_revoked",
        }
        or facts["tenant_id"] != tenant
    ):
        raise AssertionError("exact original tenant/session TTL facts required")
    if facts["tenant_revoked"] is not False or facts["session_revoked"] is not False:
        raise AssertionError("explicit revocation cannot prove natural expiry")
    created, expires = stamp(facts["created_at"]), stamp(facts["expires_at"])
    if expires - created != timedelta(minutes=30):
        raise AssertionError("not the fixed natural 30-minute TTL")
    if (
        stamp(facts["session_created_at"]) != created
        or stamp(facts["session_expires_at"]) != expires
    ):
        raise AssertionError("bound DemoSession TTL mismatch")
    if stamp(declared_expiry) != expires or stamp(facts["db_utc"]) >= expires:
        raise AssertionError("expiry mismatched or initial session already expired")
    if budget.deadline - timedelta(seconds=budget.reserve) < expires + timedelta(seconds=60):
        raise TimeoutError("insufficient expiry observation and cleanup reserve; no extension")
    return expires


def wait_monotonic(target: float, budget: Budget) -> None:
    while time.monotonic() < target:
        time.sleep(min(30, target - time.monotonic(), budget.timeout(30)))


def require_expired(reply: dict[str, Any]) -> None:
    if reply["error"]["code"] not in {"SESSION_INVALID", "EXPIRED"}:
        raise AssertionError("natural expiry rejected for an unrelated reason")


def stage_paths(evidence: Path) -> dict[str, Path]:
    return {
        stage: evidence.parent / f"natural_ttl.{stage}.safe.json"
        for stage in ("initial", "before", "after", "success")
    }


def persist(path: Path, value: dict[str, Any]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)


def run_natural_ttl(
    api: str, origin: str, budget: Budget, adapter: OwnedAdapter, evidence: Path
) -> None:
    visitor = Visitor(api, origin, budget, adapter)
    observation: dict[str, Any] = {"status": "UNKNOWN", "mode": "NATURAL_30_MINUTES"}
    paths = stage_paths(evidence)
    try:
        original = visitor.create()
        tenant = original["context"]["tenant_id"]
        key = original["data"]["creation_request_key"]
        facts = adapter.ttl_facts(tenant)
        observation.update(tenant_id=tenant, request_key=key, initial=facts)
        persist(paths["initial"], {**observation, "stage": "initial"})
        expires = verify_ttl(facts, tenant, original["data"]["expires_at"], budget)
        remaining = (expires - stamp(facts["db_utc"])).total_seconds()
        if remaining < 60:
            raise TimeoutError("initial natural window too short; no late start acceptance")
        target = time.monotonic() + remaining
        # No business or PG polling while Root runs its separate Full regression.
        wait_monotonic(target - 30, budget)
        before = adapter.ttl_facts(tenant)
        observation["before"] = before
        persist(paths["before"], {**observation, "stage": "before"})
        if stamp(before["db_utc"]) >= expires:
            raise TimeoutError("pre-expiry boundary missed; retain UNKNOWN")
        active = visitor.read_current()
        if stamp(active["context"]["authorized_at"]) >= expires:
            raise AssertionError("active response authorized at/after expiry")
        wait_monotonic(target + 2, budget)
        after = adapter.ttl_facts(tenant)
        observation["after"] = after
        persist(paths["after"], {**observation, "stage": "after"})
        if stamp(after["db_utc"]) < expires:
            raise TimeoutError("DB clock did not reach natural expiry; no extension")
        if any(after[name] != facts[name] for name in facts if name != "db_utc"):
            raise AssertionError("original creation/expiry facts changed")
        require_expired(visitor.read_current(expected=(401,)))
        visitor.current = original
        for shop in original["data"]["shops"]:
            require_expired(visitor.summary(shop["shop_id"], expected=(401,)))
        response = visitor.client.get(
            f"{PREFIX}/operations/session_create/{key}",
            headers={"Origin": origin},
            timeout=budget.timeout(10),
        )
        require_expired(visitor.check("readDemoControlReceipt", response, (401,)))
        budget.timeout(1)
    finally:
        try:
            visitor.close()
        finally:
            persist(evidence, observation)
        # An interrupt/transport/DB failure escapes with UNKNOWN evidence, never success.
    # Reached only after all assertions AND Python cleanup/summary persistence.
    # Prior stage documents remain immutable UNKNOWN even when this is appended.
    persist(
        paths["success"],
        {**observation, "stage": "success", "status": "NATURAL_TTL_OBSERVED_PENDING_REVIEW"},
    )
