"""Closed Web responses for the actual K3 store shapes; no persistence or authority."""

from typing import Any, Literal, Self, get_args
from uuid import UUID

from pydantic import Field, ValidationInfo, model_validator

from commerceops.application.commerce.contracts import Timestamp
from commerceops.application.knowledge_copy.commands import CopyReceipt
from commerceops.application.knowledge_copy.contracts import Contract
from commerceops.infrastructure.knowledge_copy_drafts import CopyCandidate


def strict_flags(value: Any) -> Any:
    """Literal[False/True] otherwise accepts 0/1 even under Pydantic strict mode."""
    flags = {
        "source_current",
        "publication_allowed",
        "approved",
        "revoked",
        "complete",
        "exhaustive",
        "provider_enabled",
        "model_requests_enabled",
        "enabled",
        "retryable",
    }
    if isinstance(value, Contract):
        value = value.model_dump(mode="python")
    if isinstance(value, dict):
        for key, item in value.items():
            if key in flags and type(item) is not bool:
                raise ValueError("COPY_BOOLEAN_INVALID")
            strict_flags(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            strict_flags(item)
    return value


class CopyWebDTO(Contract):
    @model_validator(mode="before")
    @classmethod
    def wire(cls, value: Any, info: ValidationInfo) -> Any:
        strict_flags(value)

        # A before/wrap parent can lose JSON-array handling for nested strict tuples.
        # These contracts use immutable tuples for every array; Python input stays strict.
        def arrays(item: Any) -> Any:
            if isinstance(item, list):
                return tuple(arrays(child) for child in item)
            if isinstance(item, dict):
                return {key: arrays(child) for key, child in item.items()}
            return item

        return arrays(value) if info.mode == "json" else value


class CandidateRead(CopyWebDTO):
    candidate: CopyCandidate
    state: Literal["saved", "rejected", "awaiting_review", "source_unavailable"]
    source_current: bool
    draft_id: UUID | None
    publication_allowed: Literal[False]

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (
            (self.state == "saved") != (self.draft_id is not None)
            or self.state == "awaiting_review"
            and not self.source_current
            or self.state == "source_unavailable"
            and self.source_current
        ):
            raise ValueError("COPY_READ_STATE_INVALID")
        return self


class SavedCandidate(CandidateRead):
    state: Literal["saved"]
    draft_id: UUID


class RejectedCandidate(CandidateRead):
    state: Literal["rejected"]
    draft_id: Literal[None]


class PendingCandidate(CandidateRead):
    state: Literal["awaiting_review"]
    source_current: Literal[True]
    draft_id: Literal[None]


class UnavailableCandidate(CandidateRead):
    state: Literal["source_unavailable"]
    source_current: Literal[False]
    draft_id: Literal[None]


class UnknownCandidate(CopyWebDTO):
    state: Literal["UNKNOWN"]
    request_key: UUID
    publication_allowed: Literal[False]


class WebDecision(CopyReceipt, CopyWebDTO):
    schema_version: Literal["p6-copy-receipt-v1"]
    publication_allowed: Literal[False]


class SavedDecision(WebDecision):
    state: Literal["saved"]
    decision_id: UUID
    draft_id: UUID


class RejectedDecision(WebDecision):
    state: Literal["rejected"]
    decision_id: UUID
    draft_id: Literal[None]


class UnknownDecision(WebDecision):
    state: Literal["UNKNOWN"]
    decision_id: Literal[None]
    draft_id: Literal[None]


class CandidateResponse(CopyWebDTO):
    schema_version: Literal["p6-copy-web-v1"]
    data: SavedCandidate | RejectedCandidate | PendingCandidate | UnavailableCandidate


class UnknownCandidateResponse(CopyWebDTO):
    schema_version: Literal["p6-copy-web-v1"]
    data: UnknownCandidate


class DecisionResponse(CopyWebDTO):
    schema_version: Literal["p6-copy-web-v1"]
    data: SavedDecision | RejectedDecision


class UnknownDecisionResponse(CopyWebDTO):
    schema_version: Literal["p6-copy-web-v1"]
    data: UnknownDecision


# Exactly the original P3 error-code enum, also checked against its frozen asset.
CopyErrorCode = Literal[
    "INVALID_CURSOR",
    "INVALID_FILTER",
    "INVALID_JSON",
    "SESSION_INVALID",
    "LOGIN_FAILED",
    "ACCESS_DENIED",
    "CSRF_INVALID",
    "ORIGIN_DENIED",
    "RESOURCE_NOT_FOUND",
    "PLAN_CHANGED",
    "APPROVAL_SUPERSEDED",
    "DECISION_CONFLICT",
    "IDEMPOTENCY_CONFLICT",
    "ITEM_STATE_CONFLICT",
    "ITEM_VERSION_CONFLICT",
    "ASSUMPTION_ACK_REQUIRED",
    "ASSUMPTION_SET_MISMATCH",
    "DATA_INCOMPLETE",
    "SCOPE_REQUIRED",
    "NOT_READY",
    "APPROVAL_EXPIRED",
    "UNSUPPORTED_MEDIA_TYPE",
    "INVALID_REQUEST",
    "RATE_LIMITED",
    "SERVICE_UNAVAILABLE",
]
COPY_ERROR_CODES = frozenset(get_args(CopyErrorCode))


class CopyErrorDetail(CopyWebDTO):
    code: CopyErrorCode
    safe_message: str = Field(max_length=200)
    retryable: Literal[False]
    receipt: Literal[None]


class CopyError(CopyWebDTO):
    """The copy paths emit the P3 error shape with no business-decision receipt."""

    schema_version: Literal["p3-web-v1"]
    server_time: Timestamp | None
    trace_id: UUID
    error: CopyErrorDetail
