"""Offline SQL-fault boundary only; actual concurrent PostgreSQL proof is separate."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from commerceops.application.knowledge_copy.contracts import digest
from commerceops.application.replenishment.contracts import WebActor, WebFailure
from commerceops.infrastructure import knowledge_copy_draft_store as module
from commerceops.infrastructure.database import DatabaseSettings
from commerceops.infrastructure.knowledge_copy_repository import DB
from commerceops.infrastructure.knowledge_copy_values import canonical
from psycopg.errors import UniqueViolation
from psycopg.pq import DiagnosticField

from tests.test_p6_copy_drafts import ORG, OWNER, SHOP, review_command, sample_copy

pytestmark = pytest.mark.offline


@pytest.mark.parametrize(
    "outcome,schema,table,constraint",
    [
        ("conflict", "business", "p6_copy_decisions", "p6_copy_decision_request_key"),
        ("replay", "business", "p6_copy_decisions", "p6_copy_decision_request_key"),
        ("missing", "business", "p6_copy_decisions", "p6_copy_decision_request_key"),
        ("unrelated", "business", "p6_copy_decisions", "p6_copy_decisions_candidate_id_key"),
        ("unrelated", "other", "p6_copy_decisions", "p6_copy_decision_request_key"),
        ("unrelated", "business", "other", "p6_copy_decision_request_key"),
    ],
)
def test_request_key_collision_rolls_back_then_reads_without_repeating_insert(
    monkeypatch: pytest.MonkeyPatch, outcome: str, schema: str, table: str, constraint: str
) -> None:
    candidate, request = sample_copy(), review_command()
    semantics = request.model_dump(mode="json", exclude={"request_key"})
    semantics["candidate_id"] = str(candidate.candidate_id)
    winner = dict(
        request_key=request.request_key,
        candidate_id=candidate.candidate_id,
        candidate_hash=candidate.candidate_hash,
        id=UUID(int=11),
        draft_id=UUID(int=12),
        action="approve",
        request_hash=digest(semantics) if outcome == "replay" else "f" * 64,
    )
    collision = UniqueViolation(
        "synthetic decision uniqueness conflict",
        info={
            DiagnosticField.SCHEMA_NAME: schema.encode(),
            DiagnosticField.TABLE_NAME: table.encode(),
            DiagnosticField.CONSTRAINT_NAME: constraint.encode(),
        },
    )

    class Cursor:
        def __init__(self, row: dict[str, Any] | None = None) -> None:
            self.row = row

        def fetchone(self) -> dict[str, Any] | None:
            return self.row

    class FaultDB:
        autocommit = False
        receipt_reads = 0
        inserts = 0
        rolled_back = False

        @contextmanager
        def transaction(self) -> Iterator[None]:
            try:
                yield
            except UniqueViolation:
                self.rolled_back = True
                raise

        def execute(self, statement: str, parameters: object = None) -> Cursor:
            if statement.startswith("SET LOCAL"):
                return Cursor()
            if "SELECT * FROM business.p6_copy_candidates" in statement:
                return Cursor(
                    dict(
                        payload=canonical(candidate.payload("candidate_hash")),
                        candidate_hash=candidate.candidate_hash,
                        shop_id=SHOP,
                    )
                )
            if statement == module.RECEIPT:
                self.receipt_reads += 1
                if self.receipt_reads < 3:
                    return Cursor()
                assert self.rolled_back
                return Cursor(None if outcome == "missing" else winner)
            if "SELECT business.p6_lock_copy(" in statement:
                return Cursor(dict(allowed=True))
            if "SELECT 1 FROM business.p6_copy_decisions" in statement:
                return Cursor()
            if "SELECT business.p6_copy_sources_current(" in statement:
                return Cursor(dict(allowed=True))
            if "INSERT INTO business.p6_copy_decisions" in statement:
                self.inserts += 1
                raise collision
            raise AssertionError("unexpected SQL or draft write after decision failure")

    monkeypatch.setattr(module, "actor_guard", lambda *_: None)
    monkeypatch.setattr(module, "role_scope", lambda *_: True)
    monkeypatch.setattr(module.CopyStore, "verify_sources", lambda *_, **__: None)
    store = module.CopyStore(
        DatabaseSettings(
            host="owned.invalid",
            port=5432,
            name="not-connected",
            user="commerceops_app",
            password_file=Path("/not-read"),
            runtime_password_file=None,
        ),
        {},
    )
    db = FaultDB()
    actor = WebActor(UUID(int=1), OWNER, UUID(int=3), ORG, 1)
    if outcome == "unrelated":
        with pytest.raises(UniqueViolation) as error:
            store._review_in_transaction(cast(DB, db), actor, candidate.candidate_id, request)
        assert error.value is collision and db.receipt_reads == 2
    elif outcome == "replay":
        result = store._review_in_transaction(cast(DB, db), actor, candidate.candidate_id, request)
        assert result.state == "saved" and result.decision_id == winner["id"]
        assert result.draft_id == winner["draft_id"] and db.receipt_reads == 3
    else:
        with pytest.raises(WebFailure) as failure:
            store._review_in_transaction(cast(DB, db), actor, candidate.candidate_id, request)
        expected = (
            ("COPY_RECEIPT_UNAVAILABLE", 503)
            if outcome == "missing"
            else ("IDEMPOTENCY_CONFLICT", 409)
        )
        assert (failure.value.code, failure.value.status) == expected
        assert db.receipt_reads == 3
    assert db.inserts == 1 and db.rolled_back
