"""Single backend handoff seam. No guessed configuration or SQL object names."""

from dataclasses import dataclass
from typing import Any, Protocol

from .supervisor import Role


@dataclass(frozen=True)
class Snapshot:
    tenant_id: str
    epoch: int
    generation: int
    digest: str
    receipts: int
    tombstones: int
    db_utc: str


@dataclass(frozen=True)
class CapacityFacts:
    active_tenants: int
    active_sessions: int
    creation_receipts: int


@dataclass(frozen=True)
class OperationFacts:
    receipts: int
    events: int
    event_kinds: tuple[str, ...]
    receipt_id: str | None
    tenant_id: str | None
    epoch: int | None


def require_operation_events(facts: OperationFacts, operation: str) -> None:
    expected = {
        "session_create": ("demo.seed_materialized", "demo.session_created"),
        "reset": ("demo.reset_committed",),
    }[operation]
    if facts.events != len(facts.event_kinds) or tuple(sorted(facts.event_kinds)) != expected:
        raise AssertionError("original receipt event kinds missing/duplicate/extra/wrong")


class V4Adapter(Protocol):
    """Root wires one reviewed adapter after API/seed/WEB handoff.

    validate_response must use frozen strict OpenAPI (including format/extra fields).
    snapshot uses only the exact new owned PG, read-only, bounded statement/lock
    timeouts, explicit credentials, no inherited DSN. It must observe real DB UTC.
    No adapter implementation exists yet; absence blocks runtime, never skips it.
    """

    def validate_response(self, operation: str, status: int, payload: Any) -> None: ...

    def snapshot(self, tenant_id: str, *, final_collection: bool = False) -> Snapshot: ...

    def launch_spec(self, role: Role) -> tuple[tuple[str, ...], dict[str, str]]: ...

    def persona_ids(self) -> tuple[str, str]: ...

    def capacity_facts(self) -> CapacityFacts: ...

    def operation_facts(self, operation: str, key: str) -> OperationFacts: ...
