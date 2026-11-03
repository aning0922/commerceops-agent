"""日报详情的真实 wire DTO；schema由这些类型生成，不能手工修补导出资产。"""

from datetime import date
from typing import Annotated, Literal, Self
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, field_validator, model_validator

from commerceops.application.daily.contracts import (
    DailyDTO,
    DailyFinding,
    DailyMetrics,
    DailyReport,
    ExactAverage,
    MetricDisplay,
    QualityCode,
    Status,
    metric_display,
)

Count = Annotated[int, Field(ge=0)]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
PublicCurrency = Literal["CNY", "USD", "EUR", "JPY", "GBP", "AUD", "CAD", "HKD", "CHF", "SGD"]
MoneyText = Annotated[
    str,
    Field(pattern=r"^(0|[1-9][0-9]{0,13})(\.[0-9]{0,5}[1-9])?$"),
]
SignedMoneyText = Annotated[
    str,
    Field(pattern=r"^(0|-?[1-9][0-9]{0,13}|-?(0|[1-9][0-9]{0,13})\.[0-9]{0,5}[1-9])$"),
]
QuestionKinds = tuple[
    Literal["metric_definition"],
    Literal["metric_evidence"],
    Literal["finding_reason"],
    Literal["data_quality"],
]
QUESTION_KINDS: QuestionKinds = (
    "metric_definition",
    "metric_evidence",
    "finding_reason",
    "data_quality",
)
FailureCode = Literal[
    "DAILY_SOURCE_INCOMPLETE",
    "DAILY_SOURCE_UNAVAILABLE",
    "DAILY_PERMISSION_INVALID",
    "DAILY_SOURCE_BINDING_CHANGED",
    "DAILY_STORAGE_FAILURE",
    "DAILY_WORKFLOW_UNSAFE",
]


class ReadStatusCount(DailyDTO):
    status: Status
    count: Count


class ReadMetrics(DailyDTO):
    created_order_count: Count
    paid_order_count: Count
    paid_product_net: MoneyText
    paid_product_tax: MoneyText
    paid_shipping_net: MoneyText
    paid_shipping_tax: MoneyText
    paid_fee_net: SignedMoneyText
    paid_fee_tax: SignedMoneyText
    paid_order_total: MoneyText
    refund_count: Count
    refunded_order_count: Count
    refund_amount: MoneyText
    orders_without_payment_timestamp: Count
    status_counts: tuple[ReadStatusCount, ...]
    average_paid_order_value: ExactAverage | None
    average_reason: Literal["ZERO_DENOMINATOR"] | None

    def internal(self) -> DailyMetrics:
        return DailyMetrics.model_validate_json(self.model_dump_json())

    @model_validator(mode="after")
    def invariants(self) -> Self:
        self.internal()  # 精确比值/计数/组成公式仍由同S1规则校验。
        return self


class ReadWindow(DailyDTO):
    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def interval(self) -> Self:
        if self.start >= self.end:
            raise ValueError("DAILY_WINDOW_INVALID")
        return self


class PublicSource(DailyDTO):
    source_kind: Literal["mock", "woocommerce_test"]
    source_config_version: Annotated[str, Field(min_length=1, max_length=256)]
    fixture_version: Annotated[str, Field(min_length=1, max_length=256)] | None
    currency: PublicCurrency
    timezone: Annotated[str, Field(min_length=1, max_length=256)]
    coverage_scope: Literal["controlled_test_dataset"]

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ValueError, KeyError):
            raise ValueError("DAILY_TIMEZONE_INVALID") from None
        return value

    @model_validator(mode="after")
    def fixture(self) -> Self:
        if (self.source_kind == "mock") != (self.fixture_version is not None):
            raise ValueError("DAILY_FIXTURE_SOURCE_MISMATCH")
        return self


class ReportFields(DailyDTO):
    report_id: UUID
    snapshot_id: UUID
    content_hash: Digest
    facts_hash: Digest
    business_day: date
    window: ReadWindow
    source: PublicSource
    collection_started_at: AwareDatetime
    collected_at: AwareDatetime
    quality_flags: tuple[QualityCode, ...]
    findings: tuple[DailyFinding, ...]
    evidence_count: Count

    @model_validator(mode="after")
    def dates(self) -> Self:
        from commerceops.application.daily.contracts import day_window

        window = day_window(self.business_day, self.source.timezone)
        if (self.window.start, self.window.end) != (window.start, window.end) or (
            self.collection_started_at < self.window.end
            or self.collected_at < self.collection_started_at
        ):
            raise ValueError("DAILY_TIME_BOUNDARY_INVALID")
        return self


class CompleteReport(ReportFields):
    complete: Literal[True]
    metrics: ReadMetrics
    display: tuple[MetricDisplay, ...]

    @model_validator(mode="after")
    def display_and_quality(self) -> Self:
        if self.quality_flags or any(f.severity == "blocking" for f in self.findings):
            raise ValueError("DAILY_FALSE_COMPLETENESS")
        if self.display != metric_display(self.metrics.internal(), self.source.currency):
            raise ValueError("DAILY_DISPLAY_MISMATCH")
        return self


class IncompleteReport(ReportFields):
    complete: Literal[False]
    metrics: None
    display: tuple[()]

    @model_validator(mode="after")
    def blocking(self) -> Self:
        if not any(f.severity == "blocking" for f in self.findings):
            raise ValueError("DAILY_FALSE_COMPLETENESS")
        return self


class DailyFields(DailyDTO):
    schema_version: Literal["p6-m3-web-v1"]
    task_id: UUID
    shop_id: UUID
    kind: Literal["daily_report"]
    workflow_version: Literal["p6-daily-report-v1"]
    created_at: AwareDatetime
    updated_at: AwareDatetime
    question_creation_enabled: Literal[False]
    question_kinds: QuestionKinds
    schedule_enabled: Literal[False]
    delivery_enabled: Literal[False]

    @model_validator(mode="after")
    def times(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("DAILY_TASK_TIME_INVALID")
        return self


class PendingDaily(DailyFields):
    state: Literal["queued", "analyzing"]
    failure_code: None
    report: None


class CompletedDaily(DailyFields):
    state: Literal["completed"]
    failure_code: None
    report: CompleteReport


class FailedDaily(DailyFields):
    state: Literal["failed"]
    failure_code: FailureCode
    report: None


class AttentionDaily(DailyFields):
    state: Literal["needs_attention"]
    failure_code: FailureCode
    report: IncompleteReport | None


class DailyRead(DailyDTO):
    schema_version: Literal["p3-web-v1"]
    identity_mode: Literal["session"]
    server_time: AwareDatetime
    trace_id: UUID
    daily: PendingDaily | CompletedDaily | FailedDaily | AttentionDaily

    @model_validator(mode="after")
    def observed_times(self) -> Self:
        if self.daily.updated_at > self.server_time or (
            self.daily.report is not None and self.daily.report.collected_at > self.server_time
        ):
            raise ValueError("DAILY_READ_TIME_INVALID")
        return self


def public_report(report_id: UUID, stored: DailyReport) -> CompleteReport | IncompleteReport:
    """只投影已封存且重新校验的S1；源证据/hash须由store另核，不信任客户端。"""
    report = DailyReport.model_validate_json(stored.model_dump_json())
    body = {
        "report_id": str(report_id),
        "snapshot_id": str(report.snapshot_id),
        "content_hash": report.content_hash,
        "facts_hash": report.facts_hash,
        "business_day": report.business_day.isoformat(),
        "window": {"start": report.window.start.isoformat(), "end": report.window.end.isoformat()},
        "source": {
            "source_kind": report.source.source_kind,
            "source_config_version": report.source.source_config_version,
            "fixture_version": report.source.fixture_version,
            "currency": report.source.currency,
            "timezone": report.source.timezone,
            "coverage_scope": "controlled_test_dataset",
        },
        "collection_started_at": report.coverage.collection_started_at.isoformat(),
        "collected_at": report.coverage.collected_at.isoformat(),
        "quality_flags": report.coverage.quality_flags,
        "findings": [f.model_dump(mode="json") for f in report.findings],
        "evidence_count": len(report.evidence),
        "complete": report.complete,
        "metrics": report.metrics.model_dump(mode="json") if report.metrics else None,
        "display": [item.model_dump(mode="json") for item in report.display],
    }
    import json

    model = CompleteReport if report.complete else IncompleteReport
    return model.model_validate_json(json.dumps(body))
