"""Synthetic K1 inputs. Authority/clock are supplied by the trusted caller, never by RAG text."""

import hashlib
import json
import math
import struct
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from commerceops.application.commerce.contracts import Digest, Identifier, Timestamp


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class Contract(BaseModel):
    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
        revalidate_instances="always",
    )

    def payload(self, *excluded: str) -> object:
        return self.model_dump(mode="json", exclude=set(excluded))


def checked[T: Contract](value: T) -> T:
    """Rebuild even model_copy/model_construct values at every public function boundary."""
    return type(value).model_validate(value)


class Scope(Contract):
    organization_id: Identifier
    shop_id: Identifier


class Document(Contract):
    scope: Scope
    document_id: Identifier
    document_version: Identifier
    source_kind: Literal["synthetic"] = "synthetic"
    title: str = Field(min_length=1, max_length=300)
    source_ref: Identifier
    license_ref: Identifier
    license_digest: Digest
    approved_by: Identifier
    approved_at: Timestamp
    valid_from: Timestamp
    expires_at: Timestamp
    approved: bool = True
    revoked: bool = False
    body: str = Field(min_length=1, max_length=20000)
    content_sha256: Digest

    @model_validator(mode="after")
    def valid_content(self) -> Self:
        if (
            "\r" in self.body
            or text_digest(self.body) != self.content_sha256
            or self.valid_from >= self.expires_at
            or self.approved_at > self.valid_from
        ):
            raise ValueError("DOCUMENT_INVALID")
        return self

    def available(self, now: datetime) -> bool:
        return self.approved and not self.revoked and self.valid_from <= now < self.expires_at


class Profile(Contract):
    profile_id: Identifier
    profile_version: Identifier
    provider: Literal["synthetic"] = "synthetic"
    model: Literal["hand-authored-vector"] = "hand-authored-vector"
    model_version: Identifier
    dimension: int = Field(ge=1, le=2000)
    preprocessing_version: Literal["unchanged-codepoints-v1"] = "unchanged-codepoints-v1"
    distance_version: Literal["cosine-f64-v1"] = "cosine-f64-v1"
    profile_digest: Digest

    @model_validator(mode="after")
    def valid_digest(self) -> Self:
        if digest(self.payload("profile_digest")) != self.profile_digest:
            raise ValueError("PROFILE_HASH_INVALID")
        return self


class DocumentBinding(Contract):
    document_id: Identifier
    document_version: Identifier
    content_sha256: Digest
    license_digest: Digest

    @classmethod
    def of(cls, document: Document) -> Self:
        document = checked(document)
        return cls(**{key: getattr(document, key) for key in cls.model_fields})


class Manifest(Contract):
    scope: Scope
    manifest_version: Identifier
    profile: Profile
    documents: tuple[DocumentBinding, ...] = Field(min_length=1, max_length=100)
    evidence_ids: tuple[Digest, ...] = Field(min_length=1, max_length=1000)
    ranking_version: Literal["knowledge-ranking-v1"] = "knowledge-ranking-v1"
    top_k: Literal[5] = 5
    max_candidates: Literal[20] = 20
    max_distance: float = Field(default=0.35, ge=0, le=2, allow_inf_nan=False)
    manifest_digest: Digest

    @model_validator(mode="after")
    def valid_manifest(self) -> Self:
        keys = [(d.document_id, d.document_version) for d in self.documents]
        if (
            keys != sorted(set(keys))
            or list(self.evidence_ids) != sorted(set(self.evidence_ids))
            or digest(self.payload("manifest_digest")) != self.manifest_digest
        ):
            raise ValueError("MANIFEST_INVALID")
        return self

    def permits(self, document: Document, now: datetime) -> bool:
        return (
            document.scope == self.scope
            and document.available(now)
            and DocumentBinding.of(document) in self.documents
        )


def vector_values(value: object) -> tuple[float, ...]:
    if type(value) is not tuple or not 1 <= len(value) <= 2000:
        raise ValueError("VECTOR_INVALID")
    if any(
        type(x) is not float or not math.isfinite(x) or abs(x) > 3.4028234663852886e38
        for x in value
    ):
        raise ValueError("VECTOR_INVALID")
    # Representability only. This does not convert the f64 ranking/hash into a PG f32 digest.
    if not any(struct.unpack("!f", struct.pack("!f", x))[0] != 0 for x in value):
        raise ValueError("VECTOR_ZERO")
    return tuple(0.0 if x == 0 else x for x in value)


def parse_vector(value: object, info: ValidationInfo) -> tuple[float, ...]:
    if info.mode == "json" and type(value) is list:
        value = tuple(value)
    return vector_values(value)


Vector = Annotated[tuple[float, ...], Field(min_length=1, max_length=2000)]


def vector_digest(profile: Profile, identity: str, vector: tuple[float, ...]) -> str:
    profile = checked(profile)
    vector = vector_values(vector)
    if len(vector) != profile.dimension:
        raise ValueError("VECTOR_DIMENSION_INVALID")
    return digest(
        {
            "encoding": "knowledge-vector-f64-v1",
            "profile": profile.profile_digest,
            "identity": identity,
            "values": [x.hex() for x in vector],
        }
    )


class Query(Contract):
    text: str = Field(min_length=1, max_length=2000)
    query_hash: Digest
    profile: Profile
    vector: Vector
    vector_sha256: Digest
    evidence_mode: Literal["synthetic_vector"] = "synthetic_vector"

    _vector = field_validator("vector", mode="before")(parse_vector)

    @model_validator(mode="after")
    def valid_query(self) -> Self:
        if (
            text_digest(self.text) != self.query_hash
            or vector_digest(self.profile, self.query_hash, self.vector) != self.vector_sha256
        ):
            raise ValueError("QUERY_INVALID")
        return self


class ProductFacts(Contract):
    scope: Scope
    snapshot_id: Identifier
    source_kind: Literal["synthetic"] = "synthetic"
    source_binding_id: Identifier
    source_version: Identifier
    source_digest: Digest
    sku: Identifier
    captured_at: Timestamp
    expires_at: Timestamp
    revoked: bool = False
    title: str = Field(min_length=1, max_length=300)
    facts_hash: Digest

    @model_validator(mode="after")
    def valid_facts(self) -> Self:
        if (
            self.captured_at >= self.expires_at
            or digest(self.payload("facts_hash")) != self.facts_hash
        ):
            raise ValueError("PRODUCT_INVALID")
        return self
