"""Independent float32 wire and numerical safety goldens. No PG/model/provider calls."""

import math
import struct
from typing import Any

import pytest
from commerceops.application.knowledge_copy.citations import Embedding
from commerceops.infrastructure.knowledge_copy_values import (
    PgEvidence,
    canonical,
    f32_vector,
    pg_digest,
    pg_profile,
    query_parameter,
    vector_bytes,
    vector_parameter,
)

from tests.test_p6_knowledge_copy_contracts import embedding, profile, query

pytestmark = pytest.mark.offline


def test_float32_wire_has_dimension_unused_and_network_endianness() -> None:
    assert vector_bytes((1.0, -2.0)).hex() == "000200003f800000c0000000"
    assert vector_bytes((1.0, -0.0)).hex() == "000200003f80000000000000"
    assert vector_parameter((0.1, 1.0)) == "[0.100000001,1]"
    assert f32_vector((0.1, 1.0)) == (struct.unpack("!f", bytes.fromhex("3dcccccd"))[0], 1.0)


@pytest.mark.parametrize(
    "values",
    [
        (),
        (0.0, 0.0),
        (float("nan"), 1.0),
        (float("inf"), 1.0),
        (True, 1.0),
        (1e38, 1e38),
        (1e20, 1.0),
        (1e-30, 1.0),
        (1e-30, 1e-30),
        (1e-100, 1.0),
        (1e-7, 1.0),
        (1e6, 1e6),
        (1.0, 0),
    ],
)
def test_extremes_rejected_before_pg_can_clamp_inf_or_hide_underflow(
    values: tuple[float, ...],
) -> None:
    with pytest.raises(ValueError):
        f32_vector(values)


def test_safe_nonzero_components_and_profile_binding() -> None:
    assert f32_vector((0.0, 1e6)) == (0.0, 1e6)
    assert math.isclose(f32_vector((2e-6, 0.0))[0], 2e-6, rel_tol=1e-7)
    pg = pg_profile(profile().profile_digest, 2)
    assert str(pg.distance_version) != str(profile().distance_version)
    assert query_parameter(query(), pg) == "[1,0]"
    with pytest.raises(ValueError):
        query_parameter(query(), pg_profile("0" * 64, 2))


def test_stored_evidence_cannot_bless_changed_binary_or_reference_distance() -> None:
    original = embedding(vector=(3.0, 4.0))
    prof = pg_profile(original.profile.profile_digest, 2)
    raw = bytes.fromhex("000200004040000040800000")
    fields: dict[str, Any] = dict(
        origin=original,
        profile=prof,
        stored_hex=raw.hex(),
        query=query(),
        stored_sha256=pg_digest(prof.profile_digest, original.citation.evidence_id, raw),
        distance=0.4,
        reference_distance=0.4,
    )
    evidence = PgEvidence.model_validate(fields)
    assert evidence.distance == 0.4
    assert PgEvidence.model_validate_json(evidence.model_dump_json()) == evidence
    for changes in (
        {"stored_hex": "000200000000000000000000"},
        {"stored_sha256": "0" * 64},
        {"reference_distance": 0.3},
        {"distance": 0.3},
    ):
        with pytest.raises(ValueError):
            PgEvidence.model_validate(fields | changes)


def test_clamped_valid_looking_pg_distance_does_not_admit_extreme_source() -> None:
    original = embedding(vector=(1e38, 1e38))
    prof = pg_profile(original.profile.profile_digest, 2)
    with pytest.raises(ValueError, match="KNOWLEDGE_NUMERIC_POLICY"):
        PgEvidence(
            origin=original,
            profile=prof,
            stored_hex="00",
            stored_sha256="0" * 64,
            distance=0.0,
            query=query(),
            reference_distance=0.0,
        )


def test_pg_result_rebuilds_hits_scope_count_and_mode() -> None:
    from uuid import UUID

    from commerceops.infrastructure.knowledge_copy_values import PgRetrieval

    from tests.test_p6_knowledge_copy_contracts import NOW, SCOPE, changed, seal

    original = embedding(vector=(3.0, 4.0))
    prof = pg_profile(original.profile.profile_digest, 2)
    raw = bytes.fromhex("000200004040000040800000")
    evidence = PgEvidence(
        origin=original,
        profile=prof,
        stored_hex=raw.hex(),
        query=query(),
        stored_sha256=pg_digest(prof.profile_digest, original.citation.evidence_id, raw),
        distance=0.4,
        reference_distance=0.4,
    )
    # Pure receipt fixture, not a claim that SQL returned this row.
    value = seal(
        PgRetrieval,
        "result_hash",
        scope=SCOPE,
        registry_id=UUID(int=1),
        registry_version="pure-fixture-v1",
        registry_digest="0" * 64,
        profile=prof,
        query=query(),
        as_of=NOW,
        eligible_count=1,
        pool=(evidence,),
        hits=(),
        max_distance=0.35,
        reason="INSUFFICIENT_EVIDENCE",
    )
    assert PgRetrieval.model_validate_json(value.model_dump_json()) == value
    for updates in (
        {"hits": (original.citation,), "reason": "OK"},
        {"eligible_count": 0},
        {"evidence_mode": "actual_provider"},
        {"complete": False},
        {"reason": "OK"},
        {"as_of": NOW.replace(year=2027)},
    ):
        with pytest.raises(ValueError):
            changed(value, "result_hash", **updates)


def chunk_version_variant(
    base: Embedding, version: str, vector: tuple[float, ...] = (1.0, 0.0)
) -> Embedding:
    from commerceops.application.knowledge_copy.citations import SopCitation
    from commerceops.application.knowledge_copy.contracts import vector_digest

    from tests.test_p6_knowledge_copy_contracts import seal

    chunk = base.citation.chunk.model_copy(
        update={"chunk_version": version, "section": "version " + version}
    )
    citation = seal(SopCitation, "evidence_id", chunk=chunk)
    return Embedding(
        citation=citation,
        profile=base.profile,
        vector=vector,
        vector_sha256=vector_digest(base.profile, citation.evidence_id, vector),
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_k2_same_distance_six_versions_cannot_return_order_dependent_top_five(
    reverse: bool,
) -> None:
    from uuid import UUID

    from commerceops.application.knowledge_copy.ranking import retrieve
    from commerceops.infrastructure.knowledge_copy_values import (
        PgRetrieval,
        validate_logical_corpus,
    )

    from tests.test_p6_knowledge_copy_contracts import NOW, SCOPE, manifest, seal

    items = tuple(chunk_version_variant(embedding(), "v" + str(i)) for i in range(6))
    items = tuple(reversed(items)) if reverse else items
    prof = pg_profile(items[0].profile.profile_digest, 2)
    raw = vector_bytes((1.0, 0.0))
    pool = tuple(
        PgEvidence(
            origin=e,
            profile=prof,
            query=query(),
            stored_hex=raw.hex(),
            stored_sha256=pg_digest(prof.profile_digest, e.citation.evidence_id, raw),
            distance=0.0,
            reference_distance=0.0,
        )
        for e in items
    )
    # Root's old reproducer accepted v0..v4 or v5..v1 as two "complete" outputs. Both now reject.
    with pytest.raises(ValueError, match="KNOWLEDGE_REGISTRY_AMBIGUOUS"):
        validate_logical_corpus(items)
    with pytest.raises(ValueError, match="KNOWLEDGE_POOL_INVALID"):
        seal(
            PgRetrieval,
            "result_hash",
            scope=SCOPE,
            registry_id=UUID(int=1),
            registry_version="ambiguous-fixture",
            registry_digest="0" * 64,
            profile=prof,
            query=query(),
            as_of=NOW,
            eligible_count=6,
            pool=pool,
            hits=tuple(e.citation for e in items[:5]),
            max_distance=0.35,
            reason="OK",
        )
    with pytest.raises(ValueError, match="RETRIEVAL_POOL_INVALID"):
        retrieve(manifest(items), query(), items, now=NOW, complete=True)


def test_one_logical_version_per_registry_allows_other_registries_and_exact_references() -> None:
    from commerceops.application.knowledge_copy.ranking import retrieve
    from commerceops.infrastructure.knowledge_copy_values import validate_logical_corpus

    from tests.test_p6_knowledge_copy_contracts import NOW, manifest

    a, b = chunk_version_variant(embedding(), "v1"), chunk_version_variant(embedding(), "v2")
    for item, expected in ((a, "v1"), (b, "v2")):
        validate_logical_corpus((item,))
        result = retrieve(manifest((item,)), query(), (item,), now=NOW, complete=True)
        assert result.hits[0].embedding.citation.chunk.chunk_version == expected
    with pytest.raises(ValueError, match="KNOWLEDGE_REGISTRY_AMBIGUOUS"):
        validate_logical_corpus((a, chunk_version_variant(b, "v3", (4.0, 3.0))))


def test_source_ambiguity_guard_executes_before_ranking_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from typing import cast
    from uuid import UUID

    import commerceops.infrastructure.knowledge_copy_repository as repo
    from commerceops.application.knowledge_copy.contracts import Scope
    from commerceops.application.replenishment.contracts import WebActor

    from tests.test_p6_knowledge_copy_contracts import document, manifest

    actor = WebActor(UUID(int=1), UUID(int=2), UUID(int=3), UUID(int=4), 1)
    scope = Scope(organization_id=str(actor.organization_id), shop_id=str(UUID(int=5)))
    base = embedding(doc=document("same-document", scope=scope))
    m = manifest(
        (chunk_version_variant(base, "v1"), chunk_version_variant(base, "v2")), scope=scope
    )
    profile_pg = pg_profile(m.profile.profile_digest, 2)
    calls: list[str] = []

    class Cursor:
        def __init__(self, row: dict[str, Any] | None):
            self.row = row

        def fetchone(self) -> dict[str, Any] | None:
            return self.row

    class SourceFault:
        autocommit = False

        def execute(self, statement: str, parameters: object = None) -> Cursor:
            calls.append(statement)
            if statement.startswith("SET LOCAL"):
                return Cursor(None)
            if "p6_lock_knowledge" in statement:
                return Cursor({"allowed": True})
            if "SELECT manifest,manifest_digest,profile,profile_digest" in statement:
                return Cursor(
                    dict(
                        manifest=canonical(m.payload("manifest_digest")),
                        manifest_digest=m.manifest_digest,
                        profile=canonical(profile_pg.payload("profile_digest")),
                        profile_digest=profile_pg.profile_digest,
                    )
                )
            if statement == repo.REGISTRY_DUPLICATES_SQL:
                return Cursor({"ambiguous": True})
            raise AssertionError("ambiguous source reached a later query")

    monkeypatch.setattr(repo, "actor_guard", lambda db, value: {})
    with pytest.raises(ValueError, match="KNOWLEDGE_REGISTRY_AMBIGUOUS"):
        repo.retrieve_in_transaction(
            cast(repo.DB, SourceFault()),
            actor,
            UUID(int=5),
            UUID(int=6),
            m.manifest_digest,
            query(),
        )
    assert repo.RETRIEVE_SQL not in calls
