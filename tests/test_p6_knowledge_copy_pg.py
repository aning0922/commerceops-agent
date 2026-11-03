"""K2 real owned-PG tests; collection is offline, execution requires Root's explicit new window.

Uses only self-authored synthetic SOP/vector fixtures and the existing local session fixture.
No external embedding/model, API server process, publishing, or simulated-SQL pass claims.
"""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import timedelta
from threading import Event
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from commerceops.application.knowledge_copy.citations import Embedding
from commerceops.application.knowledge_copy.contracts import Manifest, Query, Scope, vector_digest
from commerceops.application.replenishment.contracts import WebFailure
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.knowledge_copy_repository import (
    grant_knowledge_runtime,
    register_synthetic_corpus,
    retrieve_in_transaction,
)
from commerceops.infrastructure.knowledge_copy_values import (
    PgRetrieval,
    canonical,
    vector_bytes,
)
from psycopg import sql

from tests.p3_support import P3Fixture
from tests.pg_support import seed
from tests.test_p3_pg import fixture as fixture
from tests.test_p6_knowledge_copy_contracts import (
    document,
    embedding,
    manifest,
    profile,
    query,
    sha,
)

pytestmark = pytest.mark.integration


@dataclass
class KnowledgeFixture:
    f: P3Fixture
    registry: UUID
    manifest: Manifest
    corpus: tuple[Embedding, ...]

    def read(self, **changes: Any) -> PgRetrieval:
        options: dict[str, Any] = dict(
            actor=self.f.actor,
            shop_id=self.f.inventory.data.shop,
            registry_id=self.registry,
            expected_registry_digest=self.manifest.manifest_digest,
            query=query(),
        )
        with connect(self.f.inventory.app) as db:
            return retrieve_in_transaction(db, **(options | changes))


def configure(
    f: P3Fixture,
    vectors: tuple[tuple[float, ...], ...] = ((1.0, 0.0),),
    *,
    names: tuple[str, ...] | None = None,
    **doc_changes: Any,
) -> KnowledgeFixture:
    scope = Scope(
        organization_id=str(f.inventory.data.organization), shop_id=str(f.inventory.data.shop)
    )
    with connect(f.inventory.owner) as db:
        stamp = db.execute("SELECT clock_timestamp() AS t").fetchone()
        assert stamp
        now = stamp["t"]
        metadata = dict(
            scope=scope,
            approved_at=now - timedelta(days=2),
            valid_from=now - timedelta(days=1),
            expires_at=now + timedelta(days=1),
        )
        corpus = tuple(
            embedding(doc=document(name, **(metadata | doc_changes)), vector=vector)
            for name, vector in zip(
                names or tuple(f"doc-{i:02}" for i in range(len(vectors))), vectors, strict=True
            )
        )
        m = manifest(corpus, scope=scope)
        identifier = uuid4()
        register_synthetic_corpus(db, identifier, m, corpus)
    return KnowledgeFixture(f, identifier, m, corpus)


@pytest.fixture
def knowledge(fixture: P3Fixture) -> Iterator[KnowledgeFixture]:
    with connect(fixture.inventory.owner) as db:
        grant_knowledge_runtime(db)
    yield configure(fixture, names=("initial",))


def test_real_extension_wire_digest_and_independent_distances(knowledge: KnowledgeFixture) -> None:
    k = configure(knowledge.f, ((3.0, 4.0), (4.0, 3.0), (1.0, 0.0), (0.0, 1.0), (-1.0, 0.0)))
    result = k.read()
    assert result.evidence_mode == "synthetic_vector" and result.complete and result.exhaustive
    assert result.eligible_count == 5
    distances = {
        item.origin.citation.chunk.document.document_id: item.distance for item in result.pool
    }
    assert distances == pytest.approx(
        {"doc-00": 0.4, "doc-01": 0.2, "doc-02": 0.0, "doc-03": 1.0, "doc-04": 2.0}, abs=2e-6
    )
    assert [c.chunk.document.document_id for c in result.hits] == ["doc-02", "doc-01"]
    for item in result.pool:
        assert item.stored_hex == vector_bytes(item.origin.vector).hex()
    assert PgRetrieval.model_validate_json(result.model_dump_json()) == result
    with connect(k.f.inventory.app) as db:
        row = db.execute("""SELECT extversion,n.nspname FROM pg_extension e
         JOIN pg_namespace n ON n.oid=e.extnamespace WHERE extname='vector'""").fetchone()
        assert row == {"extversion": "0.8.7", "nspname": "knowledge_ext"}


def test_stable_topk_twenty_and_capacity_twenty_one(knowledge: KnowledgeFixture) -> None:
    k = configure(
        knowledge.f, ((1.0, 0.0),) * 20, names=tuple(f"tie-{i:02}" for i in reversed(range(20)))
    )
    result = k.read()
    assert result.eligible_count == 20
    assert [c.chunk.document.document_id for c in result.hits] == [f"tie-{i:02}" for i in range(5)]
    too_many = configure(
        knowledge.f, ((1.0, 0.0),) * 21, names=tuple(f"capacity-{i:02}" for i in range(21))
    )
    with pytest.raises(ValueError, match="KNOWLEDGE_CAPACITY"):
        too_many.read()


def test_revoked_high_scores_are_filtered_before_capacity_and_do_not_leak(
    knowledge: KnowledgeFixture,
) -> None:
    k = configure(
        knowledge.f,
        ((4.0, 3.0),) + ((1.0, 0.0),) * 25,
        names=("authorized", *(f"private-{i}" for i in range(25))),
    )
    with connect(k.f.inventory.owner) as db:
        db.execute("""UPDATE business.p6_knowledge_authorizations a SET revoked=true
         FROM business.p6_knowledge_documents d WHERE a.document_id=d.id
         AND d.document_key LIKE 'private-%%'""")
    result = k.read()
    assert result.eligible_count == 1
    assert [c.chunk.document.document_id for c in result.hits] == ["authorized"]
    assert "private-" not in result.model_dump_json()
    assert k.read().hits == result.hits


@pytest.mark.parametrize(
    "change", ["shop", "organization", "session", "auth", "role", "scope", "digest"]
)
def test_current_identity_scope_registry_fail_closed(
    knowledge: KnowledgeFixture, change: str
) -> None:
    k = knowledge
    options: dict[str, Any] = {}
    if change == "shop":
        options["shop_id"] = uuid4()
    elif change == "organization":
        options["actor"] = replace(k.f.actor, organization_id=uuid4())
    elif change == "session":
        options["actor"] = replace(k.f.actor, session_id=uuid4())
    elif change == "digest":
        options["expected_registry_digest"] = "0" * 64
    else:
        with connect(k.f.inventory.owner) as db:
            if change == "auth":
                db.execute(
                    "UPDATE business.principals SET auth_version=auth_version+1 WHERE id=%s",
                    (k.f.actor.principal_id,),
                )
            elif change == "role":
                db.execute(
                    "UPDATE business.principals SET roles=ARRAY['approver'] WHERE id=%s",
                    (k.f.actor.principal_id,),
                )
            else:
                db.execute(
                    "UPDATE business.principal_role_shop_grants SET enabled=false "
                    "WHERE principal_id=%s",
                    (k.f.actor.principal_id,),
                )
    with pytest.raises((ValueError, WebFailure)):
        k.read(**options)


def test_expiry_unapproved_registry_disable_and_empty_results(knowledge: KnowledgeFixture) -> None:
    k = knowledge
    with connect(k.f.inventory.owner) as db:
        db.execute("UPDATE business.p6_knowledge_authorizations SET approved=false")
    empty = k.read()
    assert empty.pool == () and empty.hits == ()
    assert empty.reason == "INSUFFICIENT_EVIDENCE"
    with connect(k.f.inventory.owner) as db:
        db.execute(
            "UPDATE business.p6_knowledge_registries SET enabled=false WHERE id=%s", (k.registry,)
        )
    with pytest.raises(WebFailure):
        k.read()
    # Re-registration is idempotent; it cannot turn current revoked/disabled status back on.
    with connect(k.f.inventory.owner) as db:
        register_synthetic_corpus(db, k.registry, k.manifest, k.corpus)
    with pytest.raises(WebFailure):
        k.read()


@pytest.mark.parametrize(
    "table", ["documents", "authorizations", "chunks", "embeddings", "registries"]
)
def test_runtime_cannot_register_mutate_or_truncate(
    knowledge: KnowledgeFixture, table: str
) -> None:
    for verb in ("DELETE FROM", "TRUNCATE"):
        with (
            pytest.raises(psycopg.errors.InsufficientPrivilege),
            connect(knowledge.f.inventory.app) as db,
        ):
            db.execute(
                sql.SQL("{} business.{}").format(
                    sql.SQL(verb), sql.Identifier("p6_knowledge_" + table)
                )
            )
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        connect(knowledge.f.inventory.app) as db,
    ):
        db.execute(
            sql.SQL("UPDATE business.{} SET shop_id=shop_id").format(
                sql.Identifier("p6_knowledge_" + table)
            )
        )
    with (
        pytest.raises(ValueError, match="KNOWLEDGE_OWNER_REQUIRED"),
        connect(knowledge.f.inventory.app) as db,
    ):
        register_synthetic_corpus(db, uuid4(), knowledge.manifest, knowledge.corpus)
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        connect(knowledge.f.inventory.app) as db,
    ):
        db.execute(
            sql.SQL("INSERT INTO business.{} DEFAULT VALUES").format(
                sql.Identifier("p6_knowledge_" + table)
            )
        )


def test_runtime_cannot_create_or_upgrade_and_owner_cannot_rewrite_evidence(
    knowledge: KnowledgeFixture,
) -> None:
    k = knowledge
    for statement in (
        "CREATE SCHEMA unapproved_knowledge",
        "CREATE TABLE knowledge_ext.unapproved(x int)",
        "ALTER EXTENSION vector UPDATE TO '0.8.7'",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege), connect(k.f.inventory.app) as db:
            db.execute(statement)
    for statement in (
        "UPDATE business.p6_knowledge_documents SET body=body||' forged'",
        "DELETE FROM business.p6_knowledge_chunks",
        "TRUNCATE business.p6_knowledge_registries",
    ):
        with pytest.raises(psycopg.errors.CheckViolation), connect(k.f.inventory.owner) as db:
            db.execute(statement)


@pytest.mark.parametrize(
    "vector", ["[1e38,1e38]", "[1e20,1]", "[1e-30,1]", "[1e-30,1e-30]", "[0,0]"]
)
def test_database_numeric_policy_rejects_pg_clamp_extremes(
    knowledge: KnowledgeFixture, vector: str
) -> None:
    with connect(knowledge.f.inventory.app) as db:
        row = db.execute(
            "SELECT business.p6_vector_safe(%s::knowledge_ext.vector) AS allowed", (vector,)
        ).fetchone()
        assert row == {"allowed": False}
    # Match source/vector and computed digest so rejection specifically reaches the numeric CHECK.
    with (
        pytest.raises(psycopg.errors.CheckViolation) as caught,
        connect(knowledge.f.inventory.owner) as db,
    ):
        db.execute(
            """INSERT INTO business.p6_knowledge_embeddings
         SELECT %s,organization_id,shop_id,chunk_id,%s,dimension,evidence_id,
          jsonb_set(origin::jsonb,'{vector}',%s::jsonb)::text,%s::knowledge_ext.vector,
          encode(sha256(convert_to('knowledge-vector-pg-f32-v1:'||%s||':'||evidence_id||':','UTF8')
           ||knowledge_ext.vector_send(%s::knowledge_ext.vector)),'hex')
         FROM business.p6_knowledge_embeddings LIMIT 1""",
            (uuid4(), "1" * 64, vector, vector, "1" * 64, vector),
        )
    assert caught.value.diag.constraint_name == "p6_embedding_numeric_safe"


def test_query_wrong_profile_no_hit_and_float32_precision_receipt(
    knowledge: KnowledgeFixture,
) -> None:
    k = configure(knowledge.f, ((0.1, 1.0), (0.0, 1.0)))
    result = k.read()
    assert result.hits == () and result.reason == "INSUFFICIENT_EVIDENCE"
    assert result.pool[0].stored_sha256 != result.pool[0].origin.vector_sha256
    different = profile(profile_version="other-embedding-version")
    wrong = query(
        profile=different,
        vector_sha256=vector_digest(different, sha("如何核对商品名称？"), (1.0, 0.0)),
    )
    with pytest.raises(ValueError, match="KNOWLEDGE_PROFILE_INVALID"):
        k.read(query=wrong)
    raw = query().model_dump(mode="python") | {"vector_sha256": "0" * 64}
    with pytest.raises(ValueError):
        k.read(query=Query.model_validate(raw))
    with pytest.raises(ValueError):
        k.read(query=query(profile=knowledge.corpus[0].profile.model_copy(update={"dimension": 3})))


def test_source_status_share_lock_blocks_revocation_until_transaction_exits(
    knowledge: KnowledgeFixture,
) -> None:
    k = knowledge
    entered, finish = Event(), Event()

    def reader() -> None:
        with connect(k.f.inventory.app) as db:
            retrieve_in_transaction(
                db,
                k.f.actor,
                k.f.inventory.data.shop,
                k.registry,
                k.manifest.manifest_digest,
                query(),
            )
            entered.set()
            assert finish.wait(10)

    with ThreadPoolExecutor(max_workers=1) as pool:
        task = pool.submit(reader)
        try:
            assert entered.wait(10)
            with pytest.raises(psycopg.errors.LockNotAvailable), connect(k.f.inventory.owner) as db:
                db.execute("SET LOCAL lock_timeout='100ms'")
                db.execute("UPDATE business.p6_knowledge_authorizations SET revoked=true")
        finally:
            finish.set()
        task.result(timeout=10)
    with connect(k.f.inventory.owner) as db:
        db.execute("UPDATE business.p6_knowledge_authorizations SET revoked=true")
    assert k.read().hits == ()


def test_failed_registration_rolls_back_savepoint_and_cross_scope_fk_rejects(
    knowledge: KnowledgeFixture,
) -> None:
    k = knowledge
    with connect(k.f.inventory.owner) as db:
        before = db.execute("SELECT count(*) AS n FROM business.p6_knowledge_documents").fetchone()
        other = seed(db)
        scope = Scope(organization_id=str(other.organization), shop_id=str(other.shop))
        first = embedding(doc=document("new-first", scope=scope))
        unsafe = embedding(doc=document("unsafe-later", scope=scope), vector=(1e38, 1e38))
        m = manifest((first, unsafe), scope=scope)
        with pytest.raises(ValueError):
            register_synthetic_corpus(db, uuid4(), m, (first, unsafe))
        assert (
            db.execute("SELECT count(*) AS n FROM business.p6_knowledge_documents").fetchone()
            == before
        )
    with pytest.raises(psycopg.errors.ForeignKeyViolation), connect(k.f.inventory.owner) as db:
        db.execute(
            "INSERT INTO business.p6_knowledge_authorizations VALUES(%s,%s,%s,true,false)",
            (k.f.inventory.data.organization, uuid4(), uuid4()),
        )


def test_threshold_boundary_records_pg_semantics_without_clamping(
    knowledge: KnowledgeFixture,
) -> None:
    import math

    k = configure(
        knowledge.f,
        ((13.001, math.sqrt(231.0)), (13.0, math.sqrt(231.0)), (12.999, math.sqrt(231.0))),
    )
    result = k.read()
    distances = {e.origin.citation.chunk.document.document_id: e.distance for e in result.pool}
    assert distances["doc-00"] < 0.35 < distances["doc-02"]
    assert abs(distances["doc-01"] - 0.35) < 2e-6
    ids = {c.chunk.document.document_id for c in result.hits}
    assert ("doc-01" in ids) == (distances["doc-01"] <= 0.35)
    assert "doc-00" in ids and "doc-02" not in ids


def test_expired_document_and_other_organization_rows_are_not_candidates(
    knowledge: KnowledgeFixture,
) -> None:
    k = knowledge
    with connect(k.f.inventory.owner) as db:
        clock = db.execute("SELECT clock_timestamp() AS t").fetchone()
        assert clock
        stamp = clock["t"]
        foreign = seed(db)
        scope = Scope(organization_id=str(foreign.organization), shop_id=str(foreign.shop))
        item = embedding(
            doc=document(
                "foreign-private",
                scope=scope,
                approved_at=stamp - timedelta(days=2),
                valid_from=stamp - timedelta(days=1),
                expires_at=stamp + timedelta(days=1),
            )
        )
        register_synthetic_corpus(db, uuid4(), manifest((item,), scope=scope), (item,))
    assert "foreign-private" not in k.read().model_dump_json()
    expired = configure(k.f, names=("expired-private",), expires_at=stamp - timedelta(hours=1))
    assert expired.read().hits == ()
    assert "expired-private" not in expired.read().model_dump_json()


def test_database_rejects_wrong_source_slice_even_with_matching_new_digest(
    knowledge: KnowledgeFixture,
) -> None:
    with pytest.raises(psycopg.errors.CheckViolation), connect(knowledge.f.inventory.owner) as db:
        db.execute(
            """WITH fake AS(SELECT organization_id,shop_id,document_id,
         (jsonb_set(jsonb_set(payload::jsonb,'{chunk,text}','"FORGED 999"'::jsonb),
           '{chunk,chunk_id}','"forged"'::jsonb))::text AS p
         FROM business.p6_knowledge_chunks LIMIT 1)
         INSERT INTO business.p6_knowledge_chunks
          (id,organization_id,shop_id,document_id,chunk_key,chunk_version,evidence_id,payload)
         SELECT %s,organization_id,shop_id,document_id,'forged','v1',
          encode(sha256(convert_to(p,'UTF8')),'hex'),p FROM fake""",
            (uuid4(),),
        )


@pytest.mark.parametrize("reverse", [False, True])
def test_one_logical_chunk_version_per_registry_is_enforced_by_application_and_database(
    knowledge: KnowledgeFixture,
    reverse: bool,
) -> None:
    from tests.test_p6_knowledge_copy_values import chunk_version_variant

    k = knowledge
    first = k.corpus[0]
    other = chunk_version_variant(first, "v2")
    second = uuid4()
    second_manifest = manifest((other,), scope=k.manifest.scope)
    with connect(k.f.inventory.owner) as db:
        register_synthetic_corpus(db, second, second_manifest, (other,))
    assert k.read().hits[0].chunk.chunk_version == "v1"
    assert (
        k.read(registry_id=second, expected_registry_digest=second_manifest.manifest_digest)
        .hits[0]
        .chunk.chunk_version
        == "v2"
    )
    ordered = (other, first) if reverse else (first, other)
    bad = manifest(ordered, scope=k.manifest.scope)
    with connect(k.f.inventory.owner) as db:
        before = db.execute("SELECT count(*) AS n FROM business.p6_knowledge_registries").fetchone()
        with pytest.raises(ValueError, match="KNOWLEDGE_REGISTRY_AMBIGUOUS"):
            register_synthetic_corpus(db, uuid4(), bad, ordered)
        assert (
            db.execute("SELECT count(*) AS n FROM business.p6_knowledge_registries").fetchone()
            == before
        )
    # Recomputed canonical/hash cannot bypass the relational guard over bound JSON members.
    with pytest.raises(psycopg.errors.CheckViolation) as caught, connect(k.f.inventory.owner) as db:
        db.execute(
            """INSERT INTO business.p6_knowledge_registries
         (id,organization_id,shop_id,manifest,manifest_digest,profile,profile_digest)
         SELECT %s,organization_id,shop_id,%s,%s,profile,profile_digest
         FROM business.p6_knowledge_registries WHERE id=%s""",
            (uuid4(), canonical(bad.payload("manifest_digest")), bad.manifest_digest, k.registry),
        )
    assert caught.value.sqlstate == "23514"
    assert "ambiguous logical chunk" in str(caught.value.diag.message_primary)
