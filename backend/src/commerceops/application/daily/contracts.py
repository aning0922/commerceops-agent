"""独立日报契约；不扩张 inventory/commerce-v1 的数据与权限含义。"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from fractions import Fraction
from typing import Annotated, Literal, Self
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from commerceops.application.commerce.contracts import (
    Currency,
    Digest,
    Identifier,
    Money,
    NonnegativeUnits,
    PositiveUnits,
    Timestamp,
    Timezone,
    Window,
)
from commerceops.domain.commerce_values import canonical_bytes, facts_hash

Status = Literal[
    "pending", "processing", "on-hold", "completed", "cancelled", "refunded", "failed", "trash"
]
NonnegativeMoney = Annotated[Money, Field(ge=0)]
MetricKey = Literal[
    "created_order_count",
    "paid_order_count",
    "paid_product_net",
    "paid_product_tax",
    "paid_shipping_net",
    "paid_shipping_tax",
    "paid_fee_net",
    "paid_fee_tax",
    "paid_order_total",
    "refund_count",
    "refunded_order_count",
    "refund_amount",
    "average_paid_order_value",
    "orders_without_payment_timestamp",
]
QualityCode = Literal[
    "MISSING_PAGE",
    "DUPLICATE_ID",
    "SOURCE_CHANGED",
    "CAPACITY_LIMIT",
    "PARTIAL_FAILURE",
    "COVERAGE_UNPROVEN",
    "PAYMENT_STATUS_CONFLICT",
]
FindingCode = Literal[
    "SOURCE_INCOMPLETE",
    "ORDER_AMOUNT_MISMATCH",
    "AGGREGATE_OUT_OF_RANGE",
    "PAYMENT_TIMESTAMP_MISSING",
    "NO_RECORDED_PAYMENTS",
    "LOW_PAID_TOTAL",
    "HIGH_REFUND_AMOUNT",
    "RULE_NOT_CONFIGURED",
]


def day_window(day: date, timezone: str) -> Window:
    if day == date.max:
        raise ValueError("DAILY_TIME_BOUNDARY_INVALID")
    zone = ZoneInfo(timezone)
    return Window(
        start=datetime.combine(day, time.min, zone),
        end=datetime.combine(day + timedelta(days=1), time.min, zone),
    )


class DailyDTO(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)


class DailySource(DailyDTO):
    schema_version: Literal["p6-daily-source-v1"] = "p6-daily-source-v1"
    organization_id: UUID
    shop_id: UUID
    source_binding_id: UUID
    source_config_version: Identifier
    config_digest: Digest
    source_kind: Literal["mock", "woocommerce_test"]
    fixture_version: Identifier | None
    currency: Currency
    timezone: Timezone
    status_mapping_version: Literal["daily-status-v1"] = "daily-status-v1"

    @model_validator(mode="after")
    def fixture(self) -> Self:
        if (self.source_kind == "mock") != (self.fixture_version is not None):
            raise ValueError("DAILY_FIXTURE_SOURCE_MISMATCH")
        return self


class DailyOrder(DailyDTO):
    source: DailySource
    order_id: Identifier
    currency: Currency
    status: Status
    created_at: Timestamp
    paid_at: Timestamp | None
    shipping_net: NonnegativeMoney
    shipping_tax: NonnegativeMoney
    fee_net: Money
    fee_tax: Money
    order_total: NonnegativeMoney

    @model_validator(mode="after")
    def dates(self) -> Self:
        if self.paid_at is not None and self.paid_at < self.created_at:
            raise ValueError("PAYMENT_BEFORE_ORDER")
        return self


class DailyOrderLine(DailyDTO):
    source: DailySource
    order_id: Identifier
    line_id: Identifier
    currency: Currency
    quantity: PositiveUnits
    net_amount: NonnegativeMoney
    tax_amount: NonnegativeMoney


class DailyRefundLine(DailyDTO):
    line_id: Identifier
    quantity: NonnegativeUnits | None
    quantity_reason: Identifier | None

    @model_validator(mode="after")
    def unknown(self) -> Self:
        if (self.quantity is None) != (self.quantity_reason is not None):
            raise ValueError("REFUND_QUANTITY_REASON_MISMATCH")
        return self


class DailyRefund(DailyDTO):
    source: DailySource
    order_id: Identifier
    refund_id: Identifier
    currency: Currency
    occurred_at: Timestamp
    amount: NonnegativeMoney
    lines: tuple[DailyRefundLine, ...]
    quantity_reason: Identifier | None
    restocked: bool | None

    @model_validator(mode="after")
    def quantities(self) -> Self:
        if (not self.lines) != (self.quantity_reason is not None):
            raise ValueError("REFUND_QUANTITY_REASON_MISMATCH")
        if len({line.line_id for line in self.lines}) != len(self.lines):
            raise ValueError("DUPLICATE_REFUND_LINE")
        return self


class DailyCoverage(DailyDTO):
    """采集方的显式覆盖声明；此纯 DTO 自身不证明真实端点覆盖。"""

    strategy: Literal["full_store", "complete_fixture"]
    orders_complete: bool
    order_lines_complete: bool
    refunds_complete: bool
    discovered_order_count: NonnegativeUnits
    discovered_line_count: NonnegativeUnits
    discovered_refund_count: NonnegativeUnits
    quality_flags: tuple[QualityCode, ...] = ()
    collection_started_at: Timestamp
    collected_at: Timestamp
    consistency: Literal["observational"] = "observational"

    @model_validator(mode="after")
    def interval(self) -> Self:
        if self.collection_started_at > self.collected_at:
            raise ValueError("DAILY_COLLECTION_INTERVAL_INVALID")
        if len(set(self.quality_flags)) != len(self.quality_flags):
            raise ValueError("DUPLICATE_QUALITY_FLAG")
        return self


class DailyRuleConfig(DailyDTO):
    rule_version: Literal["daily-rules-v1"] = "daily-rules-v1"
    currency: Currency
    low_paid_total: NonnegativeMoney | None = None
    high_refund_amount: NonnegativeMoney | None = None

    @property
    def config_hash(self) -> str:
        return facts_hash(self.model_dump(mode="json"))


class DailyInput(DailyDTO):
    schema_version: Literal["p6-daily-snapshot-v1"] = "p6-daily-snapshot-v1"
    snapshot_id: UUID
    source: DailySource
    business_day: date
    as_of: Timestamp
    coverage: DailyCoverage
    orders: tuple[DailyOrder, ...]
    order_lines: tuple[DailyOrderLine, ...]
    refunds: tuple[DailyRefund, ...]
    rules: DailyRuleConfig

    @property
    def window(self) -> Window:
        return day_window(self.business_day, self.source.timezone)

    @model_validator(mode="after")
    def bindings(self) -> Self:
        if (
            self.as_of < self.window.end
            or self.coverage.collection_started_at < self.window.end
            or self.coverage.collected_at > self.as_of
        ):
            raise ValueError("DAILY_TIME_BOUNDARY_INVALID")
        if self.rules.currency != self.source.currency:
            raise ValueError("DAILY_RULE_CURRENCY_MISMATCH")
        strategy = "complete_fixture" if self.source.source_kind == "mock" else "full_store"
        if self.coverage.strategy != strategy:
            raise ValueError("DAILY_COVERAGE_SOURCE_MISMATCH")
        orders = {order.order_id: order for order in self.orders}
        lines = {(line.order_id, line.line_id) for line in self.order_lines}
        if len(orders) != len(self.orders) or len(lines) != len(self.order_lines):
            raise ValueError("DUPLICATE_DAILY_ENTITY")
        if len({r.refund_id for r in self.refunds}) != len(self.refunds):
            raise ValueError("DUPLICATE_DAILY_ENTITY")
        entities: tuple[DailyOrder | DailyOrderLine | DailyRefund, ...] = (
            *self.orders,
            *self.order_lines,
            *self.refunds,
        )
        for entity in entities:
            if entity.source != self.source or entity.currency != self.source.currency:
                raise ValueError("DAILY_ENTITY_SOURCE_MISMATCH")
            if entity.order_id not in orders:
                raise ValueError("ORPHAN_DAILY_ENTITY")
        if any(
            order.created_at > self.coverage.collected_at
            or order.paid_at is not None
            and order.paid_at > self.coverage.collected_at
            for order in self.orders
        ) or any(refund.occurred_at > self.coverage.collected_at for refund in self.refunds):
            raise ValueError("DAILY_EVENT_AFTER_COLLECTION")
        for refund in self.refunds:
            if any((refund.order_id, line.line_id) not in lines for line in refund.lines):
                raise ValueError("ORPHAN_DAILY_REFUND_LINE")
            if refund.occurred_at < orders[refund.order_id].created_at:
                raise ValueError("REFUND_BEFORE_ORDER")
        if (
            self.coverage.discovered_order_count != len(self.orders)
            or self.coverage.discovered_line_count != len(self.order_lines)
            or self.coverage.discovered_refund_count != len(self.refunds)
        ):
            raise ValueError("DAILY_COVERAGE_COUNT_MISMATCH")
        return self

    def canonical_content(self) -> dict[str, object]:
        content = self.model_dump(mode="json")
        content["orders"] = [
            o.model_dump(mode="json") for o in sorted(self.orders, key=lambda o: o.order_id)
        ]
        content["order_lines"] = [
            line.model_dump(mode="json")
            for line in sorted(self.order_lines, key=lambda line: (line.order_id, line.line_id))
        ]
        content["refunds"] = [
            {
                **r.model_dump(mode="json"),
                "lines": [
                    line.model_dump(mode="json")
                    for line in sorted(r.lines, key=lambda line: line.line_id)
                ],
            }
            for r in sorted(self.refunds, key=lambda r: r.refund_id)
        ]
        content["coverage"]["quality_flags"] = sorted(self.coverage.quality_flags)
        return content

    @property
    def content_hash(self) -> str:
        return facts_hash(self.canonical_content())


class ExactAverage(DailyDTO):
    numerator: str = Field(pattern=r"^-?(0|[1-9][0-9]*)$")
    denominator: str = Field(pattern=r"^[1-9][0-9]*$")

    @model_validator(mode="after")
    def canonical(self) -> Self:
        ratio = Fraction(int(self.numerator), int(self.denominator))
        if (str(ratio.numerator), str(ratio.denominator)) != (self.numerator, self.denominator):
            raise ValueError("NON_CANONICAL_DAILY_AVERAGE")
        return self


class StatusCount(DailyDTO):
    status: Status
    count: NonnegativeUnits


class DailyMetrics(DailyDTO):
    created_order_count: NonnegativeUnits
    paid_order_count: NonnegativeUnits
    paid_product_net: NonnegativeMoney
    paid_product_tax: NonnegativeMoney
    paid_shipping_net: NonnegativeMoney
    paid_shipping_tax: NonnegativeMoney
    paid_fee_net: Money
    paid_fee_tax: Money
    paid_order_total: NonnegativeMoney
    refund_count: NonnegativeUnits
    refunded_order_count: NonnegativeUnits
    refund_amount: NonnegativeMoney
    orders_without_payment_timestamp: NonnegativeUnits
    status_counts: tuple[StatusCount, ...]
    average_paid_order_value: ExactAverage | None
    average_reason: Literal["ZERO_DENOMINATOR"] | None

    @model_validator(mode="after")
    def average(self) -> Self:
        if (
            self.orders_without_payment_timestamp > self.created_order_count
            or self.refunded_order_count > self.refund_count
            or sum(s.count for s in self.status_counts) != self.created_order_count
            or len({s.status for s in self.status_counts}) != len(self.status_counts)
            or sum(
                Fraction(value)
                for value in (
                    self.paid_product_net,
                    self.paid_product_tax,
                    self.paid_shipping_net,
                    self.paid_shipping_tax,
                    self.paid_fee_net,
                    self.paid_fee_tax,
                )
            )
            != Fraction(self.paid_order_total)
        ):
            raise ValueError("DAILY_METRICS_INCONSISTENT")
        if self.paid_order_count == 0:
            if (
                self.average_paid_order_value is not None
                or self.average_reason != "ZERO_DENOMINATOR"
            ):
                raise ValueError("DAILY_AVERAGE_INVALID")
        else:
            if self.average_reason is not None or self.average_paid_order_value is None:
                raise ValueError("DAILY_AVERAGE_INVALID")
            value = self.average_paid_order_value
            if Fraction(int(value.numerator), int(value.denominator)) != (
                Fraction(self.paid_order_total) / self.paid_order_count
            ):
                raise ValueError("DAILY_AVERAGE_INVALID")
        return self


class DailyEvidence(DailyDTO):
    evidence_id: Digest
    snapshot_id: UUID
    entity_kind: Literal["order", "order_line", "refund", "coverage", "rule"]
    entity_ref: Identifier
    order_id: Identifier | None
    field_path: Identifier
    value: str | None

    @model_validator(mode="after")
    def digest(self) -> Self:
        if self.evidence_id != facts_hash(self.model_dump(mode="json", exclude={"evidence_id"})):
            raise ValueError("DAILY_EVIDENCE_HASH_INVALID")
        return self


class DailyFinding(DailyDTO):
    finding_id: Digest
    code: FindingCode
    severity: Literal["info", "warning", "blocking"]
    metric_key: MetricKey | None
    evidence_ids: tuple[Digest, ...]
    rule_version: Literal["daily-rules-v1"] = "daily-rules-v1"
    rule_config_hash: Digest

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if self.finding_id != facts_hash(self.model_dump(mode="json", exclude={"finding_id"})):
            raise ValueError("DAILY_FINDING_HASH_INVALID")
        return self


class MetricDisplay(DailyDTO):
    metric_key: MetricKey
    value: str | None


def _display_money(value: Fraction, currency: str) -> str:
    digits = 0 if currency == "JPY" else 2
    numerator = abs(value.numerator) * 10**digits
    quotient, remainder = divmod(numerator, value.denominator)
    if remainder * 2 > value.denominator or (
        remainder * 2 == value.denominator and quotient % 2 == 1
    ):
        quotient += 1
    sign = "-" if value < 0 and quotient != 0 else ""
    if digits == 0:
        return sign + str(quotient)
    whole, fraction = divmod(quotient, 10**digits)
    return f"{sign}{whole}.{fraction:0{digits}d}"


def metric_display(metrics: DailyMetrics, currency: str) -> tuple[MetricDisplay, ...]:
    values: list[MetricDisplay] = []
    for key in DailyMetrics.model_fields:
        if key in ("status_counts", "average_reason"):
            continue
        raw = getattr(metrics, key)
        text: str | None
        if isinstance(raw, Decimal):
            text = _display_money(Fraction(raw), currency)
        elif isinstance(raw, ExactAverage):
            text = _display_money(Fraction(int(raw.numerator), int(raw.denominator)), currency)
        else:
            text = None if raw is None else str(raw)
        values.append(MetricDisplay.model_validate({"metric_key": key, "value": text}))
    return tuple(values)


class DailyReport(DailyDTO):
    schema_version: Literal["p6-daily-report-v1"] = "p6-daily-report-v1"
    metric_version: Literal["daily-metrics-v1"] = "daily-metrics-v1"
    canonical_version: Literal["canonical-facts-v1"] = "canonical-facts-v1"
    snapshot_id: UUID
    content_hash: Digest
    source: DailySource
    business_day: date
    as_of: Timestamp
    window: Window
    coverage: DailyCoverage
    rules: DailyRuleConfig
    complete: bool
    metrics: DailyMetrics | None
    findings: tuple[DailyFinding, ...]
    evidence: tuple[DailyEvidence, ...]
    display: tuple[MetricDisplay, ...]
    facts_hash: Digest
    analysis_only: Literal[True] = True
    execution_available: Literal[False] = False

    def canonical_facts(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"facts_hash", "display"})

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.canonical_facts())

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if self.complete != (self.metrics is not None) or (not self.complete and self.display):
            raise ValueError("DAILY_FALSE_COMPLETENESS")
        if (
            self.window != day_window(self.business_day, self.source.timezone)
            or self.rules.currency != self.source.currency
            or self.complete
            and (
                not self.coverage.orders_complete
                or not self.coverage.order_lines_complete
                or not self.coverage.refunds_complete
                or self.coverage.quality_flags
                or any(f.severity == "blocking" for f in self.findings)
            )
            or not self.complete
            and not any(f.severity == "blocking" for f in self.findings)
        ):
            raise ValueError("DAILY_FALSE_COMPLETENESS")
        expected_display = (
            metric_display(self.metrics, self.source.currency) if self.metrics else ()
        )
        if self.display != expected_display:
            raise ValueError("DAILY_DISPLAY_MISMATCH")
        ids = {e.evidence_id for e in self.evidence}
        if (
            len(ids) != len(self.evidence)
            or any(e.snapshot_id != self.snapshot_id for e in self.evidence)
            or len({f.finding_id for f in self.findings}) != len(self.findings)
            or any(
                not f.evidence_ids
                or not set(f.evidence_ids).issubset(ids)
                or f.rule_config_hash != self.rules.config_hash
                for f in self.findings
            )
        ):
            raise ValueError("DAILY_EVIDENCE_BINDING_INVALID")
        if self.facts_hash != facts_hash(self.canonical_facts()):
            raise ValueError("DAILY_FACTS_HASH_MISMATCH")
        return self
