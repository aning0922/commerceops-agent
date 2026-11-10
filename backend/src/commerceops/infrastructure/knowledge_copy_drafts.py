"""K3 source-bound template over PG retrieval; no provider or persistence."""

from datetime import timedelta
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from commerceops.application.commerce.contracts import Digest, Timestamp
from commerceops.application.knowledge_copy.citations import ProductCitation
from commerceops.application.knowledge_copy.contracts import Contract, checked, digest
from commerceops.application.knowledge_copy.prompt import Claim, product_claim, sop_claim
from commerceops.infrastructure.knowledge_copy_values import PgRetrieval


class CopyCandidate(Contract):
    schema_version: Literal["p6-copy-candidate-v1"] = "p6-copy-candidate-v1"
    candidate_id: UUID
    candidate_version: Literal["v1"] = "v1"
    owner_id: UUID
    reviewer_id: UUID
    product_source_id: UUID
    retrieval: PgRetrieval
    product: ProductCitation
    as_of: Timestamp
    expires_at: Timestamp
    claims: tuple[Claim, ...] = Field(min_length=2, max_length=6)
    text: str
    candidate_hash: Digest
    narrative_mode: Literal["template"] = "template"
    model_evidence_mode: Literal["not_used"] = "not_used"
    publication_allowed: Literal[False] = False

    @model_validator(mode="after")
    def source_bound(self) -> Self:
        r, product = self.retrieval, self.product.snapshot
        if (
            r.reason != "OK"
            or product.scope != r.scope
            or product.revoked
            or not r.as_of <= self.as_of
            or not product.captured_at <= self.as_of < product.expires_at
            or any(not c.chunk.document.available(self.as_of) for c in r.hits)
        ):
            raise ValueError("COPY_EVIDENCE_INVALID")
        claims = (product_claim(self.product), *(sop_claim(c) for c in r.hits))
        expiry = min(
            self.as_of + timedelta(minutes=15),
            product.expires_at,
            *(c.chunk.document.expires_at for c in r.hits),
        )
        if (
            self.claims != claims
            or self.text != "\n".join(c.text for c in claims)
            or self.expires_at != expiry
            or digest(self.payload("candidate_hash")) != self.candidate_hash
        ):
            raise ValueError("COPY_CANDIDATE_INVALID")
        return self


def make_copy(
    candidate_id: UUID,
    owner_id: UUID,
    reviewer_id: UUID,
    product_source_id: UUID,
    retrieval: PgRetrieval,
    product: ProductCitation,
    *,
    now: Timestamp,
) -> CopyCandidate:
    retrieval, product = checked(retrieval), checked(product)
    if retrieval.reason != "OK":
        raise ValueError("COPY_EVIDENCE_INVALID")
    claims = (product_claim(product), *(sop_claim(c) for c in retrieval.hits))
    fields: dict[str, Any] = dict(
        candidate_id=candidate_id,
        owner_id=owner_id,
        reviewer_id=reviewer_id,
        product_source_id=product_source_id,
        retrieval=retrieval,
        product=product,
        as_of=now,
        expires_at=min(
            now + timedelta(minutes=15),
            product.snapshot.expires_at,
            *(c.chunk.document.expires_at for c in retrieval.hits),
        ),
        claims=claims,
        text="\n".join(c.text for c in claims),
    )
    raw = CopyCandidate.model_construct(**fields)
    return CopyCandidate.model_validate(
        fields | {"candidate_hash": digest(raw.payload("candidate_hash"))}
    )
