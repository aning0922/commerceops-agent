"""K3 internal drafts: structured source-bound copy and explicit web review commands."""

from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from commerceops.application.commerce.contracts import Digest, Identifier
from commerceops.application.knowledge_copy.contracts import Contract


class CreateCopy(Contract):
    schema_version: Literal["p6-copy-web-v1"] = "p6-copy-web-v1"
    shop_id: UUID
    registry_id: UUID
    registry_digest: Digest
    product_source_id: UUID
    query_ref: Identifier
    reviewer_id: UUID
    request_key: UUID


class ReviewCopy(Contract):
    schema_version: Literal["p6-copy-web-v1"] = "p6-copy-web-v1"
    candidate_version: Literal["v1"]
    candidate_hash: Digest
    request_key: UUID
    action: Literal["approve", "reject"]
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def meaningful(self) -> Self:
        if not self.reason.strip():
            raise ValueError("COPY_REASON_REQUIRED")
        return self


class CopyReceipt(Contract):
    schema_version: Literal["p6-copy-receipt-v1"] = "p6-copy-receipt-v1"
    request_key: UUID
    state: Literal["saved", "rejected", "UNKNOWN"]
    candidate_id: UUID
    candidate_hash: Digest
    decision_id: UUID | None = None
    draft_id: UUID | None = None
    publication_allowed: Literal[False] = False

    @model_validator(mode="after")
    def shape(self) -> Self:
        if (
            self.state == "saved"
            and (self.decision_id is None or self.draft_id is None)
            or self.state == "rejected"
            and (self.decision_id is None or self.draft_id is not None)
            or self.state == "UNKNOWN"
            and (self.decision_id is not None or self.draft_id is not None)
        ):
            raise ValueError("COPY_RECEIPT_INVALID")
        return self
