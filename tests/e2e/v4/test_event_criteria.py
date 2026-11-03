"""Offline event semantics; no SQL execution or HTTP/PG Gate evidence."""

import pytest

from .adapter import OperationFacts, require_operation_events

pytestmark = pytest.mark.offline


def facts(kinds: tuple[str, ...], *, count: int | None = None) -> OperationFacts:
    return OperationFacts(1, len(kinds) if count is None else count, kinds, None, None, 1)


@pytest.mark.parametrize(
    "kinds",
    [
        ("demo.session_created", "demo.seed_materialized"),
        ("demo.seed_materialized", "demo.session_created"),
    ],
)
def test_exact_creation_events_accept_either_observation_order(kinds: tuple[str, ...]) -> None:
    require_operation_events(facts(kinds), "session_create")


@pytest.mark.parametrize(
    "kinds",
    [
        (),
        ("demo.session_created",),
        ("demo.session_created", "demo.session_created"),
        ("demo.reset_committed", "demo.session_revoked"),
        ("demo.session_created", "demo.seed_materialized", "demo.persona_changed"),
        ("demo.session_created", "demo.seed_materialized", "demo.seed_materialized"),
    ],
)
def test_missing_duplicate_wrong_or_extra_creation_events_rejected(kinds: tuple[str, ...]) -> None:
    with pytest.raises(AssertionError):
        require_operation_events(facts(kinds), "session_create")


def test_exact_reset_event_accepted() -> None:
    require_operation_events(facts(("demo.reset_committed",)), "reset")


@pytest.mark.parametrize(
    "kinds",
    [
        (),
        ("demo.persona_changed",),
        ("demo.session_created",),
        ("demo.reset_committed", "demo.reset_committed"),
        ("demo.reset_committed", "demo.session_revoked"),
    ],
)
def test_wrong_same_count_or_extra_reset_events_rejected(kinds: tuple[str, ...]) -> None:
    with pytest.raises(AssertionError):
        require_operation_events(facts(kinds), "reset")


def test_count_cannot_hide_truncated_sequence() -> None:
    with pytest.raises(AssertionError):
        require_operation_events(facts(("demo.reset_committed",), count=2), "reset")
