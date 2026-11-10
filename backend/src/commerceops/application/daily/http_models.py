"""M3新增操作wire类型；继承原session envelope，内层单独版本。"""

from datetime import date
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator, model_validator

from commerceops.application.commerce.contracts import Digest
from commerceops.application.daily.contracts import DailyDTO
from commerceops.application.daily.questions import (
    Citation,
    QuestionKind,
    QuestionSpec,
    TemplateAnswer,
)
from commerceops.application.daily.read_models import FailureCode, PublicSource


class CreateDailyInput(DailyDTO):
    schema_version: Literal["p6-m3-web-v1"]
    shop_id: UUID
    source_config_version: Annotated[str, Field(min_length=1, max_length=256)]
    request_key: UUID
    business_day: date | None = None


class Envelope(DailyDTO):
    schema_version: Literal["p3-web-v1"]
    identity_mode: Literal["session"]
    server_time: AwareDatetime
    trace_id: UUID


class DailyCapabilities(DailyDTO):
    schema_version: Literal["p6-m3-web-v1"]
    shop_id: UUID
    enabled: bool
    source: PublicSource | None
    earliest_business_day: date | None
    metric_version: Literal["daily-metrics-v1"] | None
    question_kinds: tuple[QuestionKind, ...]
    schedule_management_mode: Literal["controlled_cli"]
    delivery_mode: Literal["fake_only"]
    model_requests_enabled: Literal[False]
    external_sender_enabled: Literal[False]

    @field_validator("enabled", "model_requests_enabled", "external_sender_enabled", mode="before")
    @classmethod
    def literal_bool(cls, value: object) -> object:
        if type(value) is not bool:
            raise ValueError("DAILY_BOOLEAN_INVALID")
        return value

    @model_validator(mode="after")
    def availability(self) -> Self:
        if self.enabled != (self.source is not None) or self.enabled != (
            self.earliest_business_day is not None and self.metric_version is not None
        ):
            raise ValueError("DAILY_CAPABILITY_INVALID")
        return self


class CapabilityRead(Envelope):
    capabilities: DailyCapabilities


class DailyAccepted(DailyDTO):
    schema_version: Literal["p6-m3-web-v1"]
    task_id: UUID
    state: Literal["queued", "analyzing", "completed", "failed", "needs_attention"]


class AcceptanceRead(Envelope):
    accepted: DailyAccepted


class CreationReceipt(DailyDTO):
    schema_version: Literal["p6-m3-web-v1"]
    lookup_status: Literal["accepted"]
    request_key: UUID
    shop_id: UUID
    task_id: UUID
    state: Literal["queued", "analyzing", "completed", "failed", "needs_attention"]
    failure_code: FailureCode | None
    request_hash: Digest


class DailyCreationReceipt(CreationReceipt):
    operation: Literal["daily_report.create"]
    source_config_version: Annotated[str, Field(min_length=1, max_length=256)]
    business_day: date


class QuestionCreationReceipt(CreationReceipt):
    operation: Literal["daily_question.create"]
    parent_task_id: UUID
    report_id: UUID
    snapshot_id: UUID
    content_hash: Digest
    facts_hash: Digest
    question: QuestionSpec


class CreationReceiptRead(Envelope):
    receipt: DailyCreationReceipt | QuestionCreationReceipt


class QuestionView(DailyDTO):
    schema_version: Literal["p6-m3-web-v1"]
    parent_task_id: UUID
    question_id: UUID
    state: Literal["queued", "analyzing", "completed", "failed", "needs_attention"]
    failure_code: FailureCode | None
    answer: TemplateAnswer | None
    citations: tuple[Citation, ...]
    total_evidence_count: Annotated[int, Field(ge=0)]
    next_cursor: Annotated[str, Field(max_length=4096)] | None

    @model_validator(mode="after")
    def state_shape(self) -> Self:
        if (
            (self.state == "completed") != (self.answer is not None)
            or (
                self.answer is None
                and (self.citations or self.total_evidence_count or self.next_cursor)
            )
            or len(self.citations) > 50
        ):
            raise ValueError("DAILY_QUESTION_READ_INVALID")
        return self


class QuestionRead(Envelope):
    question: QuestionView


class EvidenceView(DailyDTO):
    schema_version: Literal["p6-m3-web-v1"]
    task_id: UUID
    report_id: UUID
    snapshot_id: UUID
    content_hash: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    facts_hash: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    citations: tuple[Citation, ...]
    total_evidence_count: Annotated[int, Field(ge=0)]
    next_cursor: Annotated[str, Field(max_length=4096)] | None

    @model_validator(mode="after")
    def bound_page(self) -> Self:
        if (
            len(self.citations) > 50
            or self.total_evidence_count < len(self.citations)
            or any(item.snapshot_id != self.snapshot_id for item in self.citations)
        ):
            raise ValueError("DAILY_EVIDENCE_PAGE_INVALID")
        return self


class EvidenceRead(Envelope):
    evidence: EvidenceView
