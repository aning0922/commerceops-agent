"""Owned-PG K3 matrix. Approval mode is simulated_web; no real human or model evidence."""

import secrets
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from commerceops.application.knowledge_copy.commands import CreateCopy, ReviewCopy
from commerceops.application.knowledge_copy.contracts import digest
from commerceops.application.replenishment.contracts import WebActor, WebFailure
from commerceops.application.replenishment.security import password_hash
from commerceops.entrypoints.knowledge_copy_http import knowledge_copy_router
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.knowledge_copy_draft_store import (
    CopyStore,
    grant_copy_runtime,
    register_copy_product,
)
from commerceops.infrastructure.knowledge_copy_drafts import CopyCandidate
from commerceops.infrastructure.knowledge_copy_values import canonical
from commerceops.infrastructure.web_sessions import SessionStore
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg import Connection, sql

from tests.p3_support import ORIGIN
from tests.test_p3_pg import fixture as fixture
from tests.test_p6_knowledge_copy_contracts import product, query
from tests.test_p6_knowledge_copy_pg import KnowledgeFixture
from tests.test_p6_knowledge_copy_pg import knowledge as knowledge

pytestmark = pytest.mark.integration


@dataclass
class CopyFixture:
    k: KnowledgeFixture
    store: CopyStore
    command: CreateCopy
    value: CopyCandidate

    def review(
        self, action: str = "approve", *, key: UUID | None = None, reason: str = "明确审核合成候选"
    ) -> ReviewCopy:
        return ReviewCopy.model_validate(
            dict(
                candidate_version="v1",
                candidate_hash=self.value.candidate_hash,
                request_key=key or uuid4(),
                action=action,
                reason=reason,
            )
        )

    def counts(self) -> tuple[int, int, int, int]:
        with connect(self.k.f.inventory.owner) as db:
            values = []
            for suffix in ("candidates", "decisions", "drafts"):
                row = db.execute(
                    sql.SQL("SELECT count(*) AS n FROM business.{}").format(
                        sql.Identifier("p6_copy_" + suffix)
                    )
                ).fetchone()
                assert row
                values.append(row["n"])
            row = db.execute(
                "SELECT count(*) AS n FROM business.audit_events WHERE source='copy_review'"
            ).fetchone()
            assert row
            return values[0], values[1], values[2], row["n"]


@pytest.fixture
def copy_case(knowledge: KnowledgeFixture) -> CopyFixture:
    k = knowledge
    product_id = uuid4()
    with connect(k.f.inventory.owner) as db:
        grant_copy_runtime(db)
        clock = db.execute("SELECT clock_timestamp() AS t").fetchone()
        assert clock
        p = product(
            scope=k.manifest.scope,
            captured_at=clock["t"] - timedelta(seconds=1),
            expires_at=clock["t"] + timedelta(minutes=30),
        )
        register_copy_product(db, product_id, p)
    store = CopyStore(
        k.f.config.database,
        {(k.f.actor.organization_id, k.f.inventory.data.shop, "synthetic-name-check"): query()},
    )
    command = CreateCopy(
        shop_id=k.f.inventory.data.shop,
        registry_id=k.registry,
        registry_digest=k.manifest.manifest_digest,
        product_source_id=product_id,
        reviewer_id=k.f.actor.principal_id,
        query_ref="synthetic-name-check",
        request_key=uuid4(),
    )
    value = store.create(k.f.actor, command)
    return CopyFixture(k, store, command, value)


def additional_reviewer(c: CopyFixture) -> tuple[WebActor, TestClient]:
    f = c.k.f
    principal, identity = uuid4(), uuid4()
    login, password = "reviewer-" + uuid4().hex[:16], secrets.token_urlsafe(24)
    data = f.inventory.data
    with connect(f.inventory.owner) as db:
        db.execute(
            "INSERT INTO business.principals(id,organization_id,display_name,roles) "
            "VALUES(%s,%s,'Synthetic assigned reviewer',ARRAY['approver'])",
            (principal, data.organization),
        )
        db.execute(
            "INSERT INTO business.principal_shop_scopes VALUES(%s,%s,%s,true)",
            (data.organization, data.shop, principal),
        )
        db.execute(
            "INSERT INTO business.principal_role_shop_grants VALUES(%s,%s,%s,'approver',true)",
            (data.organization, data.shop, principal),
        )
        db.execute(
            """INSERT INTO business.identities
         (id,organization_id,principal_id,provider,app_id,tenant_key,external_subject)
         VALUES(%s,%s,%s,'web',%s,%s,%s)""",
            (identity, data.organization, principal, data.app, data.tenant, login),
        )
        db.execute(
            "INSERT INTO business.web_credentials VALUES(%s,%s,%s,%s,%s,true)",
            (login, data.organization, principal, identity, password_hash(password)),
        )
    client = TestClient(f.client.app, base_url=ORIGIN)
    bootstrap = client.get("/api/v1/auth/csrf").json()
    result = client.post(
        "/api/v1/auth/login",
        json=dict(schema_version="p3-web-v1", login=login, password=password),
        headers={"Origin": ORIGIN, "X-CSRF-Token": bootstrap["csrf_token"]},
    )
    assert result.status_code == 200
    actor = SessionStore(f.config).authenticate(client.cookies.get("commerceops_session"))
    return actor, client


def test_candidate_replay_conflict_approve_once_and_read_only_draft(copy_case: CopyFixture) -> None:
    c = copy_case
    assert c.store.create(c.k.f.actor, c.command) == c.value
    assert c.counts() == (1, 0, 0, 0)
    with pytest.raises(WebFailure) as conflict:
        c.store.create(c.k.f.actor, c.command.model_copy(update={"query_ref": "another-query"}))
    assert conflict.value.status == 409
    command = c.review()
    receipt = c.store.review(c.k.f.actor, c.value.candidate_id, command)
    assert receipt.state == "saved" and receipt.draft_id is not None
    assert c.store.review(c.k.f.actor, c.value.candidate_id, command) == receipt
    assert c.counts() == (1, 1, 1, 1)
    with pytest.raises(WebFailure) as conflict:
        c.store.review(
            c.k.f.actor, c.value.candidate_id, command.model_copy(update={"reason": "异文"})
        )
    assert conflict.value.status == 409
    state = c.store.read(c.k.f.actor, c.value.candidate_id)
    assert state["state"] == "saved" and state["candidate"]["text"] == c.value.text
    assert (
        c.store.receipt(
            c.k.f.actor, c.value.candidate_id, command.request_key, c.value.candidate_hash
        )
        == receipt
    )
    assert c.counts() == (1, 1, 1, 1)


def test_reject_creates_no_draft_and_opposite_action_conflicts(copy_case: CopyFixture) -> None:
    c = copy_case
    rejected = c.review("reject")
    result = c.store.review(c.k.f.actor, c.value.candidate_id, rejected)
    assert result.state == "rejected" and result.draft_id is None
    with pytest.raises(WebFailure):
        c.store.review(c.k.f.actor, c.value.candidate_id, c.review("approve"))
    assert c.counts() == (1, 1, 0, 1)


@pytest.mark.parametrize("same_key", [True, False])
def test_two_connections_first_decision_and_draft_are_unique(
    copy_case: CopyFixture, same_key: bool
) -> None:
    c = copy_case
    first = c.review()
    second = first if same_key else c.review("reject")

    def decide(command: ReviewCopy) -> str:
        try:
            return c.store.review(c.k.f.actor, c.value.candidate_id, command).state
        except WebFailure as e:
            assert e.status == 409
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(decide, x) for x in (first, second)]
        outcomes = [f.result(timeout=20) for f in futures]
    n = c.counts()
    assert n[1] == n[3] == 1 and n[2] in (0, 1)
    assert outcomes == ["saved", "saved"] if same_key else "conflict" in outcomes


def test_only_assigned_current_approver_can_review_without_operator_role(
    copy_case: CopyFixture,
) -> None:
    c = copy_case
    reviewer, browser = additional_reviewer(c)
    try:
        request = c.command.model_copy(
            update={"request_key": uuid4(), "reviewer_id": reviewer.principal_id}
        )
        value = c.store.create(c.k.f.actor, request)
        with pytest.raises(WebFailure):
            c.store.review(c.k.f.actor, value.candidate_id, c.review())
        command = c.review().model_copy(update={"candidate_hash": value.candidate_hash})
        assert c.store.read(reviewer, value.candidate_id)["state"] == "awaiting_review"
        result = c.store.review(reviewer, value.candidate_id, command)
        assert result.state == "saved"
        with pytest.raises(WebFailure):
            c.store.read(reviewer, value.candidate_id)  # completed draft is owner-only
    finally:
        browser.close()


@pytest.mark.parametrize(
    "kind",
    ["product", "sop", "registry", "reviewer_role", "owner_scope", "auth_version", "session"],
)
def test_revocation_current_grants_and_source_status_block_save(
    copy_case: CopyFixture, kind: str
) -> None:
    c = copy_case
    with connect(c.k.f.inventory.owner) as db:
        if kind == "product":
            db.execute("UPDATE business.p6_copy_products SET enabled=false")
        elif kind == "sop":
            db.execute("UPDATE business.p6_knowledge_authorizations SET revoked=true")
        elif kind == "registry":
            db.execute("UPDATE business.p6_knowledge_registries SET enabled=false")
        elif kind == "reviewer_role":
            db.execute(
                "UPDATE business.principal_role_shop_grants SET enabled=false WHERE role='approver'"
            )
        elif kind == "owner_scope":
            db.execute(
                "UPDATE business.principal_role_shop_grants SET enabled=false WHERE role='operator'"
            )
        elif kind == "auth_version":
            db.execute("UPDATE business.principals SET auth_version=auth_version+1")
        else:
            db.execute(
                "UPDATE business.web_sessions SET revoked_at=clock_timestamp() WHERE id=%s",
                (c.k.f.actor.session_id,),
            )
    with pytest.raises((WebFailure, ValueError, psycopg.Error)):
        c.store.review(c.k.f.actor, c.value.candidate_id, c.review())
    assert c.counts() == (1, 0, 0, 0)


def test_original_server_query_replay_rejects_new_self_consistent_input(
    copy_case: CopyFixture,
) -> None:
    from commerceops.application.knowledge_copy.contracts import vector_digest

    from tests.test_p6_knowledge_copy_contracts import sha

    c = copy_case
    q = query(
        text="changed-query",
        query_hash=sha("changed-query"),
        vector_sha256=vector_digest(query().profile, sha("changed-query"), (1.0, 0.0)),
    )
    changed = CopyStore(
        c.store.settings, {(c.k.f.actor.organization_id, c.command.shop_id, c.command.query_ref): q}
    )
    with pytest.raises(ValueError, match="COPY_QUERY_OR_BINDING_CHANGED"):
        changed.review(c.k.f.actor, c.value.candidate_id, c.review())
    assert c.counts() == (1, 0, 0, 0)


def test_candidate_expiry_is_checked_at_commit_and_rolls_back_all(copy_case: CopyFixture) -> None:
    c = copy_case
    short_product = uuid4()
    with connect(c.k.f.inventory.owner) as db:
        clock = db.execute("SELECT clock_timestamp() AS t").fetchone()
        assert clock
        p = product(
            scope=c.k.manifest.scope,
            captured_at=clock["t"] - timedelta(seconds=1),
            expires_at=clock["t"] + timedelta(seconds=10),
        )
        register_copy_product(db, short_product, p)
    value = c.store.create(
        c.k.f.actor,
        c.command.model_copy(update={"request_key": uuid4(), "product_source_id": short_product}),
    )
    command = c.review().model_copy(update={"candidate_hash": value.candidate_hash})
    reached_expiry_before_commit = False
    with pytest.raises(psycopg.errors.CheckViolation), connect(c.k.f.inventory.app) as db:
        c.store.review_in_transaction(db, c.k.f.actor, value.candidate_id, command)
        assert db.execute("SHOW statement_timeout").fetchone() == {"statement_timeout": "5s"}
        # Keep the real ten-second TTL and production timeout. Each wait stays below 5s.
        for _ in range(5):
            db.execute("SELECT pg_sleep(2.1)")
        clock = db.execute(
            "SELECT clock_timestamp() >= %s AS expired", (value.expires_at,)
        ).fetchone()
        assert clock and clock["expired"]
        reached_expiry_before_commit = True
    # The expected failure must come from COMMIT, not admission.
    assert reached_expiry_before_commit
    assert c.counts() == (2, 0, 0, 0)


def test_confirmed_commit_with_simulated_lost_ack_recovered_by_read_only_original_key(
    copy_case: CopyFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = copy_case
    app = cast(FastAPI, c.k.f.client.app)
    app.include_router(knowledge_copy_router(c.k.f.config, c.store))
    command = c.review()

    @contextmanager
    def lost_ack(settings: DatabaseSettings) -> Iterator[Connection[dict[str, Any]]]:
        with connect(settings) as db:
            yield db
        raise psycopg.OperationalError("synthetic client acknowledgement loss after actual COMMIT")

    monkeypatch.setattr("commerceops.infrastructure.knowledge_copy_draft_store.connect", lost_ack)
    result = c.k.f.client.post(
        "/api/v1/copy/candidates/" + str(c.value.candidate_id) + "/review",
        json=command.model_dump(mode="json"),
        headers=c.k.f.headers(),
    )
    assert result.status_code == 202 and result.json()["data"]["state"] == "UNKNOWN"
    monkeypatch.undo()
    recovered = c.store.receipt(
        c.k.f.actor, c.value.candidate_id, command.request_key, c.value.candidate_hash
    )
    assert recovered.state == "saved" and c.counts() == (1, 1, 1, 1)
    fresh = CopyStore(c.store.settings, c.store.queries)
    assert (
        fresh.receipt(
            c.k.f.actor, c.value.candidate_id, command.request_key, c.value.candidate_hash
        )
        == recovered
    )


def test_no_receipt_stays_unknown_and_rollback_does_not_create_draft(
    copy_case: CopyFixture,
) -> None:
    c = copy_case
    command = c.review()
    with pytest.raises(RuntimeError), connect(c.k.f.inventory.app) as db:
        c.store.review_in_transaction(db, c.k.f.actor, c.value.candidate_id, command)
        raise RuntimeError("synthetic rollback before COMMIT")
    result = c.store.receipt(
        c.k.f.actor, c.value.candidate_id, command.request_key, c.value.candidate_hash
    )
    assert result.state == "UNKNOWN" and c.counts() == (1, 0, 0, 0)


@pytest.mark.parametrize("table", ["products", "candidates", "decisions", "drafts"])
def test_history_immutable_and_runtime_cannot_mutate_or_delete(
    copy_case: CopyFixture, table: str
) -> None:
    c = copy_case
    for verb in ("UPDATE", "DELETE", "TRUNCATE"):
        statement = (
            sql.SQL("UPDATE business.{} SET shop_id=shop_id")
            if verb == "UPDATE"
            else sql.SQL(verb + " business.{}")
            if verb == "TRUNCATE"
            else sql.SQL("DELETE FROM business.{}")
        )
        with (
            pytest.raises(psycopg.errors.InsufficientPrivilege),
            connect(c.k.f.inventory.app) as db,
        ):
            db.execute(statement.format(sql.Identifier("p6_copy_" + table)))
    if table != "products":
        with pytest.raises(psycopg.Error) as denied, connect(c.k.f.inventory.owner) as db:
            db.execute(sql.SQL("TRUNCATE business.{}").format(sql.Identifier("p6_copy_" + table)))
        # Parent-table FK safety can reject TRUNCATE before a BEFORE TRUNCATE trigger runs.
        assert denied.value.sqlstate in (
            {"0A000", "23514"} if table in ("candidates", "decisions") else {"23514"}
        )


def test_json_null_cannot_be_registered_as_product_even_with_recomputed_digest(
    copy_case: CopyFixture,
) -> None:
    c = copy_case
    with pytest.raises(psycopg.errors.CheckViolation), connect(c.k.f.inventory.owner) as db:
        db.execute(
            """INSERT INTO business.p6_copy_products
         SELECT %s,organization_id,shop_id,
          jsonb_set(payload::jsonb,'{snapshot,title}','null'::jsonb)::text,
          encode(sha256(convert_to(jsonb_set(payload::jsonb,'{snapshot,title}','null'::jsonb)::text,'UTF8')),'hex'),
          expires_at,captured_at,true FROM business.p6_copy_products LIMIT 1""",
            (uuid4(),),
        )


def test_approve_without_draft_cannot_commit_and_no_outbox_is_emitted(
    copy_case: CopyFixture,
) -> None:
    c = copy_case
    with connect(c.k.f.inventory.owner) as db:
        before = db.execute("SELECT count(*) AS n FROM business.outbox").fetchone()
    command = c.review()
    semantics = command.model_dump(mode="json", exclude={"request_key"}) | {
        "candidate_id": str(c.value.candidate_id)
    }
    with pytest.raises(psycopg.errors.CheckViolation), connect(c.k.f.inventory.app) as db:
        db.execute(
            """INSERT INTO business.p6_copy_decisions
         (id,organization_id,shop_id,candidate_id,candidate_hash,actor_id,identity_id,session_id,
          auth_version,request_key,action,reason,request_payload,request_hash)
         VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'approve',%s,%s,%s)""",
            (
                uuid4(),
                c.k.f.actor.organization_id,
                c.command.shop_id,
                c.value.candidate_id,
                c.value.candidate_hash,
                c.k.f.actor.principal_id,
                c.k.f.actor.identity_id,
                c.k.f.actor.session_id,
                c.k.f.actor.auth_version,
                command.request_key,
                command.reason,
                canonical(semantics),
                digest(semantics),
            ),
        )
    assert c.counts() == (1, 0, 0, 0)
    c.store.review(c.k.f.actor, c.value.candidate_id, command)
    with connect(c.k.f.inventory.owner) as db:
        assert db.execute("SELECT count(*) AS n FROM business.outbox").fetchone() == before


def test_different_current_actors_cannot_both_decide_same_assigned_candidate(
    copy_case: CopyFixture,
) -> None:
    c = copy_case
    other, browser = additional_reviewer(c)
    try:
        commands = ((c.k.f.actor, c.review()), (other, c.review("reject")))

        def apply(item: tuple[WebActor, ReviewCopy]) -> str:
            actor, command = item
            try:
                return c.store.review(actor, c.value.candidate_id, command).state
            except WebFailure as e:
                assert e.status in (403, 404)
                return "denied"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(apply, commands))
        assert results == ["saved", "denied"] and c.counts() == (1, 1, 1, 1)
    finally:
        browser.close()


@pytest.mark.parametrize("target", ["reviewer_grant", "product"])
def test_review_holds_grant_and_product_locks_until_atomic_commit(
    copy_case: CopyFixture, target: str
) -> None:
    from threading import Event

    c = copy_case
    ready, release = Event(), Event()

    def reviewing() -> None:
        with connect(c.k.f.inventory.app) as db:
            c.store.review_in_transaction(db, c.k.f.actor, c.value.candidate_id, c.review())
            ready.set()
            assert release.wait(10)

    statement = (
        "UPDATE business.principal_role_shop_grants SET enabled=false WHERE role='approver'"
        if target == "reviewer_grant"
        else "UPDATE business.p6_copy_products SET enabled=false"
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(reviewing)
        try:
            assert ready.wait(10)
            with (
                pytest.raises(psycopg.errors.LockNotAvailable),
                connect(c.k.f.inventory.owner) as db,
            ):
                db.execute("SET LOCAL lock_timeout='100ms'")
                db.execute(statement)
        finally:
            release.set()
        future.result(timeout=10)
    assert c.counts() == (1, 1, 1, 1)


@pytest.mark.parametrize("json_path", ["{claims}", "{retrieval,hits}", "{expires_at}"])
def test_candidate_json_null_rehash_cannot_bypass_database_guards(
    copy_case: CopyFixture, json_path: str
) -> None:
    c = copy_case
    with pytest.raises(psycopg.errors.CheckViolation), connect(c.k.f.inventory.app) as db:
        # New request/id and matching hashes; only one candidate JSON field is null.
        db.execute(
            """WITH input AS(SELECT c.*,
         jsonb_set(jsonb_set(payload::jsonb,'{candidate_id}',to_jsonb(%s::text)),
          %s::text[],'null'::jsonb)::text p,
         jsonb_set(request_payload::jsonb,'{query_ref}','"new-request-ref"'::jsonb)::text q
         FROM business.p6_copy_candidates c WHERE c.id=%s)
         INSERT INTO business.p6_copy_candidates
         SELECT %s,organization_id,shop_id,owner_id,reviewer_id,owner_identity,
          owner_session,owner_auth_version,
          registry_id,product_id,%s,q,encode(sha256(convert_to(q,'UTF8')),'hex'),p,
          encode(sha256(convert_to(p,'UTF8')),'hex'),created_at,expires_at FROM input""",
            (str(UUID(int=99)), json_path, c.value.candidate_id, UUID(int=99), uuid4()),
        )


def test_two_candidates_same_actor_request_key_race_returns_exact_conflict(
    copy_case: CopyFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from threading import Barrier

    c = copy_case
    second = c.store.create(c.k.f.actor, c.command.model_copy(update={"request_key": uuid4()}))
    shared = uuid4()
    left = c.review(key=shared)
    right = left.model_copy(update={"candidate_hash": second.candidate_hash})
    barrier = Barrier(2)
    original = CopyStore.verify_sources

    def meet_before_insert(
        self: CopyStore,
        db: Connection[dict[str, Any]],
        row: dict[str, Any],
        value: CopyCandidate,
        *,
        replay_rank: bool,
    ) -> None:
        original(self, db, row, value, replay_rank=replay_rank)
        # Both sessions have observed no receipt and locked different candidates at this point.
        if replay_rank:
            barrier.wait(timeout=10)

    monkeypatch.setattr(CopyStore, "verify_sources", meet_before_insert)

    def decide(item: tuple[UUID, ReviewCopy]) -> str:
        identifier, request = item
        try:
            return c.store.review(c.k.f.actor, identifier, request).state
        except WebFailure as error:
            assert error.status == 409 and error.code == "IDEMPOTENCY_CONFLICT"
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(decide, item)
            for item in ((c.value.candidate_id, left), (second.candidate_id, right))
        ]
        outcomes = [f.result(timeout=20) for f in futures]
    assert sorted(outcomes) == ["IDEMPOTENCY_CONFLICT", "saved"]
    assert c.counts() == (2, 1, 1, 1)
