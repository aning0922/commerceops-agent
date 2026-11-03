"""Citations carry their source: rehashing forged display text cannot validate it."""

from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from commerceops.application.commerce.contracts import Digest, Identifier
from commerceops.application.knowledge_copy.contracts import (
    Contract,
    Document,
    ProductFacts,
    Profile,
    Vector,
    digest,
    parse_vector,
    vector_digest,
)


class Chunk(Contract):
    document: Document
    chunk_id: Identifier
    chunk_version: Identifier
    chunker_version: Identifier
    section: str = Field(min_length=1, max_length=300)
    start: int = Field(ge=0)
    end: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=2000)
    text_sha256: Digest

    @model_validator(mode="after")
    def valid_slice(self) -> Self:
        from commerceops.application.knowledge_copy.contracts import text_digest

        if (
            not self.start < self.end <= len(self.document.body)
            or self.document.body[self.start : self.end] != self.text
            or text_digest(self.text) != self.text_sha256
        ):
            raise ValueError("CHUNK_INVALID")
        return self


class SopCitation(Contract):
    source_kind: Literal["sop"] = "sop"
    chunk: Chunk
    evidence_id: Digest

    @model_validator(mode="after")
    def valid_reference(self) -> Self:
        if digest(self.payload("evidence_id")) != self.evidence_id:
            raise ValueError("CITATION_INVALID")
        return self


class ProductCitation(Contract):
    source_kind: Literal["product"] = "product"
    snapshot: ProductFacts
    field_path: Literal["title"] = "title"
    text: str
    evidence_id: Digest

    @model_validator(mode="after")
    def valid_reference(self) -> Self:
        if (
            self.text != self.snapshot.title
            or digest(self.payload("evidence_id")) != self.evidence_id
        ):
            raise ValueError("CITATION_INVALID")
        return self


class Embedding(Contract):
    citation: SopCitation
    profile: Profile
    vector: Vector
    vector_sha256: Digest
    evidence_mode: Literal["synthetic_vector"] = "synthetic_vector"

    _vector = field_validator("vector", mode="before")(parse_vector)

    @model_validator(mode="after")
    def valid_vector(self) -> Self:
        if (
            vector_digest(self.profile, self.citation.evidence_id, self.vector)
            != self.vector_sha256
        ):
            raise ValueError("EMBEDDING_INVALID")
        return self
