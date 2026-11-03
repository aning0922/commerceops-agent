"""Pure f64 oracle for later PG tests. This module does not execute vector SQL."""

import math
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from commerceops.application.commerce.contracts import Digest, Timestamp
from commerceops.application.knowledge_copy.citations import Embedding
from commerceops.application.knowledge_copy.contracts import (
    Contract,
    DocumentBinding,
    Manifest,
    Query,
    checked,
    digest,
    vector_values,
)


def cosine_distance(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    left, right = vector_values(left), vector_values(right)
    if len(left) != len(right):
        raise ValueError("VECTOR_DIMENSION_INVALID")
    a, b = math.hypot(*left), math.hypot(*right)
    cosine = math.fsum((x / a) * (y / b) for x, y in zip(left, right, strict=True))
    return 1.0 - max(-1.0, min(1.0, cosine))


def _identity(item: Embedding) -> tuple[str, str, str]:
    chunk = item.citation.chunk
    return chunk.document.document_id, chunk.document.document_version, chunk.chunk_id


def _permitted(item: Embedding, manifest: Manifest, now: Timestamp) -> bool:
    return (
        manifest.permits(item.citation.chunk.document, now)
        and item.profile == manifest.profile
        and item.citation.evidence_id in manifest.evidence_ids
    )


class Hit(Contract):
    embedding: Embedding
    query: Query
    distance: float = Field(ge=0, le=2, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid_distance(self) -> Self:
        if self.embedding.profile != self.query.profile or self.distance != cosine_distance(
            self.embedding.vector, self.query.vector
        ):
            raise ValueError("HIT_INVALID")
        return self


class ManifestView(Manifest):
    """Only eligible bindings are projected; original registry identity stays digest-only."""

    source_manifest_digest: Digest
    documents: tuple[DocumentBinding, ...] = Field(max_length=100)
    evidence_ids: tuple[Digest, ...] = Field(max_length=1000)


class Retrieval(Contract):
    manifest: ManifestView
    query: Query
    as_of: Timestamp
    complete: bool
    # Only permitted evidence enters this pool. It is internal oracle evidence, not an API DTO.
    pool: tuple[Embedding, ...] = Field(max_length=20)
    hits: tuple[Hit, ...] = Field(max_length=5)
    reason: Literal["OK", "INSUFFICIENT_EVIDENCE"]
    retrieval_hash: Digest
    evidence_mode: Literal["synthetic_vector"] = "synthetic_vector"

    @model_validator(mode="after")
    def valid_result(self) -> Self:
        if self.query.profile != self.manifest.profile:
            raise ValueError("QUERY_PROFILE_INVALID")
        keys = [_identity(item) for item in self.pool]
        if keys != sorted(set(keys)) or any(
            not _permitted(item, self.manifest, self.as_of) for item in self.pool
        ):
            raise ValueError("RETRIEVAL_POOL_INVALID")
        bindings = {DocumentBinding.of(e.citation.chunk.document) for e in self.pool}
        expected_documents = tuple(
            sorted(bindings, key=lambda b: (b.document_id, b.document_version))
        )
        if self.manifest.documents != expected_documents or self.manifest.evidence_ids != tuple(
            sorted(e.citation.evidence_id for e in self.pool)
        ):
            raise ValueError("MANIFEST_VIEW_INVALID")
        expected = _ranked(self.pool, self.query, self.manifest) if self.complete else ()
        if (
            self.hits != expected
            or self.reason != ("OK" if expected else "INSUFFICIENT_EVIDENCE")
            or digest(self.payload("retrieval_hash")) != self.retrieval_hash
        ):
            raise ValueError("RETRIEVAL_INVALID")
        return self


def _ranked(pool: tuple[Embedding, ...], query: Query, manifest: Manifest) -> tuple[Hit, ...]:
    pairs = [(cosine_distance(item.vector, query.vector), item) for item in pool]
    pairs.sort(key=lambda pair: (pair[0], _identity(pair[1])))
    return tuple(
        Hit(embedding=item, query=query, distance=distance)
        for distance, item in pairs
        if distance <= manifest.max_distance
    )[: manifest.top_k]


def retrieve(
    manifest: Manifest,
    query: Query,
    corpus: tuple[Embedding, ...],
    *,
    now: Timestamp,
    complete: bool,
) -> Retrieval:
    manifest, query = checked(manifest), checked(query)
    # Parse clock as a DTO field even when corpus is empty, so naive clocks cannot slip through.
    from pydantic import TypeAdapter

    now = TypeAdapter(Timestamp).validate_python(now)
    if query.profile != manifest.profile:
        raise ValueError("QUERY_PROFILE_INVALID")
    if type(complete) is not bool or type(corpus) is not tuple:
        raise ValueError("RETRIEVAL_INPUT_INVALID")
    eligible = []
    for raw in corpus:
        item = checked(raw)
        if _permitted(item, manifest, now):
            eligible.append(item)
    if len(eligible) > manifest.max_candidates:
        raise ValueError("RETRIEVAL_CAPACITY")
    pool = tuple(sorted(eligible, key=_identity))
    hits = _ranked(pool, query, manifest) if complete else ()
    bindings = {DocumentBinding.of(e.citation.chunk.document) for e in pool}
    view_data: dict[str, Any] = {
        name: getattr(manifest, name) for name in Manifest.model_fields if name != "manifest_digest"
    }
    view_data.update(
        source_manifest_digest=manifest.manifest_digest,
        documents=tuple(sorted(bindings, key=lambda b: (b.document_id, b.document_version))),
        evidence_ids=tuple(sorted(e.citation.evidence_id for e in pool)),
    )
    raw_view = ManifestView.model_construct(**view_data)
    view = ManifestView(**view_data, manifest_digest=digest(raw_view.payload("manifest_digest")))
    data: dict[str, Any] = dict(
        manifest=view,
        query=query,
        as_of=now,
        complete=complete,
        pool=pool,
        hits=hits,
        reason="OK" if hits else "INSUFFICIENT_EVIDENCE",
        evidence_mode="synthetic_vector",
    )
    # Construct once to obtain canonical JSON, then validate all derivations in the public DTO.
    provisional = Retrieval.model_construct(**data)
    return Retrieval(**data, retrieval_hash=digest(provisional.payload("retrieval_hash")))


def verify_retrieval(
    value: Retrieval,
    manifest: Manifest,
    query: Query,
    corpus: tuple[Embedding, ...],
    *,
    now: Timestamp,
    complete: bool,
) -> Retrieval:
    """Verify a stored result against authoritative inputs, not a caller-rehashed provenance label.

    K2 must fetch registry/corpus/clock under its own authorization boundary. These pure DTOs
    cannot authenticate an attacker-supplied source registry or certify database completeness.
    """
    value = checked(value)
    expected = retrieve(manifest, query, corpus, now=now, complete=complete)
    if value != expected:
        raise ValueError("RETRIEVAL_SOURCE_MISMATCH")
    return value
