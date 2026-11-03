"""Strict inquiry Web/persistence DTOs; server-only source and offline mode."""

from dataclasses import asdict
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from commerceops.application.commerce.readonly_inquiry_contracts import (
    Claim,
    ProductMatch,
    ReadResult,
    Strict,
    Window,
)
from commerceops.application.commerce.readonly_inquiry_executor import Outcome, Trace

WORKFLOW: Literal["p6-readonly-inquiry-v1"] = "p6-readonly-inquiry-v1"
KIND = "readonly_inquiry"


class CreateInquiry(Strict):
    schema_version: Literal["p6-inquiry-web-v1"]
    shop_id: UUID
    question: str = Field(min_length=1, max_length=2000)
    context_report_id: UUID | None = None
    request_key: UUID

    @model_validator(mode="after")
    def nonempty(self) -> "CreateInquiry":
        if not self.question.strip():
            raise ValueError("EMPTY_QUESTION")
        return self


class TraceRead(Strict):
    tool_call_id: str = Field(min_length=1, max_length=128)
    name: Literal[
        "commerce.read_products", "commerce.read_orders", "commerce.read_inventory", "reports.read"
    ]
    args_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ResultPayload(Strict):
    schema_version: Literal["p6-inquiry-result-v1"] = "p6-inquiry-result-v1"
    status: Literal[
        "complete",
        "clarify",
        "unsupported",
        "insufficient_evidence",
        "invalid_response",
        "source_incomplete",
        "access_denied",
        "budget_exceeded",
        "timeout",
        "tool_denied",
    ]
    model_calls: int = Field(ge=0, le=3)
    tool_calls: int = Field(ge=0, le=4)
    scanned_rows: int = Field(ge=0)
    traces: tuple[TraceRead, ...] = Field(max_length=4)
    results: tuple[ReadResult, ...] = Field(max_length=4)
    evidence_refs: tuple[str, ...] = Field(max_length=100)
    claims: tuple[Claim, ...] = Field(max_length=100)
    clarification_options: tuple[ProductMatch, ...] = Field(max_length=100)
    evidence_mode: Literal["offline_stub"] = "offline_stub"
    workflow_version: Literal["p6-readonly-inquiry-v1"] = WORKFLOW

    @classmethod
    def from_outcome(cls, value: Outcome) -> "ResultPayload":
        raw = asdict(value)
        return cls.model_validate(raw)

    def outcome(self) -> Outcome:
        return Outcome(
            status=self.status,
            model_calls=self.model_calls,
            tool_calls=self.tool_calls,
            scanned_rows=self.scanned_rows,
            traces=tuple(Trace(**trace.model_dump()) for trace in self.traces),
            results=self.results,
            evidence_refs=self.evidence_refs,
            claims=self.claims,
            clarification_options=self.clarification_options,
        )

    @model_validator(mode="after")
    def disclosure(self) -> "ResultPayload":
        if len(self.traces) != self.tool_calls or len(
            {trace.tool_call_id for trace in self.traces}
        ) != len(self.traces):
            raise ValueError("TRACE_BINDING")
        if any(
            result.tool_call_id not in {trace.tool_call_id for trace in self.traces}
            for result in self.results
        ):
            raise ValueError("RESULT_TRACE_BINDING")
        if any(not result.complete for result in self.results):
            raise ValueError("INCOMPLETE_DISCLOSURE")
        if self.status != "complete" and (self.results or self.evidence_refs or self.claims):
            raise ValueError("FAILURE_DISCLOSURE")
        if self.status != "clarify" and self.clarification_options:
            raise ValueError("INVALID_OPTIONS")
        return self


State = Literal["queued", "analyzing", "completed", "failed", "needs_attention"]


class InquiryReceipt(Strict):
    schema_version: Literal["p6-inquiry-web-v1"] = "p6-inquiry-web-v1"
    identity_mode: Literal["session"] = "session"
    task_id: UUID
    shop_id: UUID
    request_key: UUID
    state: State
    duplicate: bool
    source_mode: Literal["mock"] = "mock"
    source_binding: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_domain: Window
    evidence_mode: Literal["offline_stub"] = "offline_stub"
    server_time: datetime
    trace_id: UUID


class InquiryRead(InquiryReceipt):
    result: ResultPayload | None
    answer: str | None
    data_label: Literal["本地演示数据 / 离线模型替身"] = "本地演示数据 / 离线模型替身"


class InquiryError(Strict):
    schema_version: Literal["p6-inquiry-web-v1"] = "p6-inquiry-web-v1"
    code: Literal[
        "SESSION_INVALID",
        "ACCESS_DENIED",
        "RESOURCE_NOT_FOUND",
        "INVALID_REQUEST",
        "INVALID_JSON",
        "UNSUPPORTED_MEDIA_TYPE",
        "ORIGIN_DENIED",
        "CSRF_INVALID",
        "IDEMPOTENCY_CONFLICT",
        "SERVICE_UNAVAILABLE",
        "INQUIRY_DISABLED",
        "NOT_READY",
    ]
    message: Literal["无法处理此查询，请核对当前权限、输入或原请求回执。"] = (
        "无法处理此查询，请核对当前权限、输入或原请求回执。"
    )
    trace_id: UUID
