"""K2 synthetic-only float32 numeric policy; no DB or provider access."""

import hashlib
import json
import math
import struct
from typing import Final, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from commerceops.application.commerce.contracts import Digest, Timestamp
from commerceops.application.knowledge_copy.citations import Embedding, SopCitation
from commerceops.application.knowledge_copy.contracts import Contract, Query, Scope, checked, digest
from commerceops.application.knowledge_copy.ranking import cosine_distance

ENCODING: Final = "knowledge-vector-pg-f32-v1"
NUMERIC: Final = "bounded-components-1e-6-1e6-normsq-1e-12-1e12-v1"
DISTANCE: Final = "cosine-pgvector-0.8.7-f32-v1"


def canonical(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def f32_vector(values: tuple[float, ...]) -> tuple[float, ...]:
    if type(values) is not tuple or not 1 <= len(values) <= 2000:
        raise ValueError("KNOWLEDGE_VECTOR_INVALID")
    output = []
    for item in values:
        if type(item) is not float or not math.isfinite(item) or abs(item) > 1e6:
            raise ValueError("KNOWLEDGE_NUMERIC_POLICY")
        rounded = struct.unpack("!f", struct.pack("!f", item))[0]
        if item != 0 and (rounded == 0 or abs(rounded) < 1e-6):
            raise ValueError("KNOWLEDGE_NUMERIC_POLICY")
        output.append(0.0 if rounded == 0 else rounded)
    normsq = math.fsum(x * x for x in output)
    if not 1e-12 <= normsq <= 1e12:
        raise ValueError("KNOWLEDGE_NUMERIC_POLICY")
    return tuple(output)


def vector_bytes(values: tuple[float, ...]) -> bytes:
    values = f32_vector(values)
    return struct.pack("!hh", len(values), 0) + struct.pack("!" + "f" * len(values), *values)


def vector_parameter(values: tuple[float, ...]) -> str:
    return "[" + ",".join(format(x, ".9g") for x in f32_vector(values)) + "]"


def pg_digest(profile_digest: str, identity: str, stored: bytes) -> str:
    return hashlib.sha256(
        f"{ENCODING}:{profile_digest}:{identity}:".encode("ascii") + stored
    ).hexdigest()


class PgProfile(Contract):
    origin_profile_digest: Digest
    dimension: int = Field(ge=1, le=2000)
    encoding_version: Literal["knowledge-vector-pg-f32-v1"] = ENCODING
    numeric_policy: Literal["bounded-components-1e-6-1e6-normsq-1e-12-1e12-v1"] = NUMERIC
    distance_version: Literal["cosine-pgvector-0.8.7-f32-v1"] = DISTANCE
    profile_digest: Digest

    @model_validator(mode="after")
    def valid_digest(self) -> Self:
        if digest(self.payload("profile_digest")) != self.profile_digest:
            raise ValueError("KNOWLEDGE_PROFILE_INVALID")
        return self


def pg_profile(origin: str, dimension: int) -> PgProfile:
    body = dict(
        origin_profile_digest=origin,
        dimension=dimension,
        encoding_version=ENCODING,
        numeric_policy=NUMERIC,
        distance_version=DISTANCE,
    )
    return PgProfile.model_validate(body | {"profile_digest": digest(body)})


class PgEvidence(Contract):
    origin: Embedding
    profile: PgProfile
    stored_hex: str = Field(pattern=r"^[0-9a-f]+$")
    stored_sha256: Digest
    distance: float = Field(ge=0, le=2, allow_inf_nan=False)
    query: Query
    reference_distance: float = Field(ge=0, le=2, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid_evidence(self) -> Self:
        original = self.origin
        profile = pg_profile(original.profile.profile_digest, original.profile.dimension)
        raw = vector_bytes(original.vector)
        expected = cosine_distance(f32_vector(original.vector), f32_vector(self.query.vector))
        if (
            self.profile != profile
            or self.query.profile != original.profile
            or self.stored_hex != raw.hex()
            or self.stored_sha256
            != pg_digest(profile.profile_digest, original.citation.evidence_id, raw)
            or self.reference_distance != expected
            or abs(self.distance - expected) > 2e-6
        ):
            raise ValueError("KNOWLEDGE_STORED_VECTOR_INVALID")
        return self


def key(value: PgEvidence) -> tuple[float, str, str, str]:
    chunk = value.origin.citation.chunk
    return (
        value.distance,
        chunk.document.document_id,
        chunk.document.document_version,
        chunk.chunk_id,
    )


class PgRetrieval(Contract):
    schema_version: Literal["p6-pg-retrieval-v1"] = "p6-pg-retrieval-v1"
    registry_id: UUID
    registry_version: str = Field(min_length=1, max_length=256)
    scope: Scope
    registry_digest: Digest
    profile: PgProfile
    query: Query
    as_of: Timestamp
    evidence_mode: Literal["synthetic_vector"] = "synthetic_vector"
    complete: Literal[True] = True
    exhaustive: Literal[True] = True
    eligible_count: int = Field(ge=0, le=20)
    pool: tuple[PgEvidence, ...] = Field(max_length=20)
    hits: tuple[SopCitation, ...] = Field(max_length=5)
    max_distance: float = Field(ge=0, le=2, allow_inf_nan=False)
    reason: Literal["OK", "INSUFFICIENT_EVIDENCE"]
    result_hash: Digest

    @model_validator(mode="after")
    def semantic_result(self) -> Self:
        if self.profile != pg_profile(
            self.query.profile.profile_digest, self.query.profile.dimension
        ):
            raise ValueError("KNOWLEDGE_PROFILE_INVALID")
        keys = [key(item) for item in self.pool]
        identities = [item.origin.citation.evidence_id for item in self.pool]
        if (
            self.eligible_count != len(self.pool)
            or keys != sorted(keys)
            or len(identities) != len(set(identities))
        ):
            raise ValueError("KNOWLEDGE_POOL_INVALID")
        for item in self.pool:
            doc = item.origin.citation.chunk.document
            if (
                item.query != self.query
                or item.profile != self.profile
                or doc.scope != self.scope
                or not doc.available(self.as_of)
            ):
                raise ValueError("KNOWLEDGE_EVIDENCE_INVALID")
        expected = tuple(
            item.origin.citation for item in self.pool if item.distance <= self.max_distance
        )[:5]
        if (
            self.hits != expected
            or self.reason != ("OK" if expected else "INSUFFICIENT_EVIDENCE")
            or digest(self.payload("result_hash")) != self.result_hash
        ):
            raise ValueError("KNOWLEDGE_RESULT_INVALID")
        return self


def query_parameter(query: Query, profile: PgProfile) -> str:
    query, profile = checked(query), checked(profile)
    if profile != pg_profile(query.profile.profile_digest, query.profile.dimension):
        raise ValueError("KNOWLEDGE_PROFILE_INVALID")
    return vector_parameter(query.vector)
