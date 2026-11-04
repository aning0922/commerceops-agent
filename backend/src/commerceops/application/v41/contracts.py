"""Strict business wire contracts. Identity and permission always come from the server."""

from datetime import date
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from commerceops.application.v4_demo.contracts import (
    Context,
    Contract,
    Counter,
    Currency,
    Digest,
    Timestamp,
)

Amount = Annotated[str, Field(pattern=r"^(0|[1-9][0-9]{0,19})(\.[0-9]{0,5}[1-9])?$")]
ShortText = Annotated[str, Field(min_length=1, max_length=120)]
Tag = Annotated[str, Field(min_length=1, max_length=24)]
Tags = Annotated[tuple[Tag, ...], Field(max_length=8)]
SkuLabel = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")]
Operation = Literal["product_tags", "order_fulfillment", "import_confirm"]
MetricId = Literal[
    "created_order_count",
    "paid_order_count",
    "paid_order_amount",
    "refund_event_count",
    "refund_event_amount",
    "average_paid_order_amount",
    "product_count",
    "low_stock_count",
]
Reason = Literal[
    "UNKNOWN_PAYMENT_TIME",
    "UNKNOWN_SETTLEMENT",
    "UNKNOWN_COST",
    "UNKNOWN_STOCK",
    "UNKNOWN_INBOUND",
    "NO_DENOMINATOR",
    "OUTSIDE_SOURCE_WINDOW",
    "NO_COMPARABLE_PERIOD",
]


def canonical_tags(tags: tuple[str, ...]) -> tuple[str, ...]:
    if len(tags) != len(set(tags)) or any(tag.strip() != tag for tag in tags):
        raise ValueError("NONCANONICAL_TAGS")
    return tags


class Query(Contract):
    shop_id: UUID


class PeriodQuery(Query):
    from_date: date | None = None
    to_date: date | None = None
    days: Literal[7, 14] = 7

    @model_validator(mode="after")
    def bounded_period(self) -> Self:
        if (self.from_date is None) != (self.to_date is None):
            raise ValueError("PERIOD_PAIR_REQUIRED")
        if self.from_date is not None and self.to_date is not None:
            if not 1 <= (self.to_date - self.from_date).days <= 90:
                raise ValueError("PERIOD_LIMIT")
        return self


class Period(Contract):
    from_date: date
    to_date: date
    timezone: Literal["Asia/Taipei", "Asia/Shanghai"]
    from_utc: Timestamp
    to_utc: Timestamp


class PageQuery(Query):
    q: Annotated[str, Field(max_length=80)] = ""
    limit: Annotated[int, Field(ge=1, le=100)] = 20
    cursor: Annotated[str, Field(min_length=1, max_length=2048)] | None = None


class ProductQuery(PageQuery):
    tag: Tag | None = None
    origin: Literal["demo_fixture", "demo_upload"] | None = None
    sort: Literal["title_asc", "title_desc", "price_asc", "price_desc"] = "title_asc"


class OrderQuery(PeriodQuery):
    q: Annotated[str, Field(max_length=80)] = ""
    limit: Annotated[int, Field(ge=1, le=100)] = 20
    cursor: Annotated[str, Field(min_length=1, max_length=2048)] | None = None
    time_basis: Literal["created", "paid"] = "created"
    payment: Literal["recorded", "unknown"] | None = None
    fulfillment: Literal["demo_unfulfilled", "demo_fulfilled"] | None = None
    sort: Literal["created_desc", "created_asc", "amount_desc", "amount_asc"] = "created_desc"


class DrilldownQuery(PeriodQuery):
    metric: MetricId
    limit: Annotated[int, Field(ge=1, le=100)] = 20
    cursor: Annotated[str, Field(min_length=1, max_length=2048)] | None = None


class ReadContextQuery(PeriodQuery):
    kind: Literal["dashboard", "product", "order"]
    resource_id: UUID | None = None

    @model_validator(mode="after")
    def resource_pair(self) -> Self:
        if (self.kind == "dashboard") != (self.resource_id is None):
            raise ValueError("CONTEXT_RESOURCE_MISMATCH")
        return self


class SourceRef(Contract):
    data_mode: Literal["demo_fixture", "demo_upload"]
    evidence_mode: Literal["synthetic_demo"] = "synthetic_demo"
    fixture_version: Literal["v4-demo-seed-1"] = "v4-demo-seed-1"
    fixture_digest: Digest
    baseline_snapshot_at: Timestamp
    import_job_id: UUID | None
    import_row: Annotated[int, Field(ge=2, le=501)] | None = None
    file_digest: Digest | None = None

    @model_validator(mode="after")
    def upload_identity(self) -> Self:
        upload_fields = (self.import_job_id, self.import_row, self.file_digest)
        if self.data_mode == "demo_upload" and any(value is None for value in upload_fields):
            raise ValueError("SOURCE_JOB_MISMATCH")
        if self.data_mode == "demo_fixture" and any(value is not None for value in upload_fields):
            raise ValueError("SOURCE_JOB_MISMATCH")
        return self


class DatasetSource(Contract):
    data_mode: Literal["demo_fixture", "demo_mixed"]
    evidence_mode: Literal["synthetic_demo"] = "synthetic_demo"
    fixture_version: Literal["v4-demo-seed-1"] = "v4-demo-seed-1"
    fixture_digest: Digest
    baseline_snapshot_at: Timestamp
    uploads: tuple[SourceRef, ...] = Field(max_length=500)

    @model_validator(mode="after")
    def mixed_source(self) -> Self:
        if (self.data_mode == "demo_mixed") != bool(self.uploads):
            raise ValueError("MIXED_SOURCE_MISMATCH")
        if any(
            row.data_mode != "demo_upload"
            or row.fixture_digest != self.fixture_digest
            or row.baseline_snapshot_at != self.baseline_snapshot_at
            for row in self.uploads
        ):
            raise ValueError("MIXED_SOURCE_IDENTITY")
        if len({(row.import_job_id, row.import_row) for row in self.uploads}) != len(self.uploads):
            raise ValueError("DUPLICATE_UPLOAD_SOURCE")
        return self


class Snapshot(Contract):
    data_revision: Digest
    snapshot_id: Digest
    read_at: Timestamp
    source: DatasetSource


class Metric(Contract):
    metric: MetricId
    value: Amount | None
    known_value: Amount
    unit: Literal["count", "money"]
    currency: Currency | None
    completeness: Literal["COMPLETE", "PARTIAL", "UNAVAILABLE"]
    reason_codes: tuple[Reason, ...]
    included_count: Counter
    excluded_count: Counter
    settlement_status: Literal["NOT_APPLICABLE", "UNKNOWN"]

    @model_validator(mode="after")
    def honest_value(self) -> Self:
        if (self.completeness == "COMPLETE") != (self.value is not None):
            raise ValueError("METRIC_COMPLETENESS_MISMATCH")
        if self.value is not None and self.value != self.known_value:
            raise ValueError("METRIC_KNOWN_VALUE_MISMATCH")
        if self.completeness != "COMPLETE" and not self.reason_codes:
            raise ValueError("METRIC_REASON_REQUIRED")
        if (self.unit == "money") != (self.currency is not None):
            raise ValueError("METRIC_CURRENCY_MISMATCH")
        return self


class TrendPoint(Contract):
    day: date
    metrics: tuple[Metric, ...]


class RuleInsight(Contract):
    rule: Literal["unknown_payment_time", "unknown_cost", "low_stock", "refund_events"]
    rule_version: Literal["v41-rules-1"] = "v41-rules-1"
    analysis_mode: Literal["deterministic_rules"] = "deterministic_rules"
    resource_ids: tuple[UUID, ...] = Field(max_length=100)
    reason: Reason | None
    threshold_units: Counter | None = None


class DashboardData(Contract):
    snapshot: Snapshot
    period: Period
    metrics: tuple[Metric, ...]
    trend: tuple[TrendPoint, ...] = Field(max_length=90)
    insights: tuple[RuleInsight, ...]
    comparison_value: None = None
    comparison_reason: Literal["NO_COMPARABLE_PERIOD"] = "NO_COMPARABLE_PERIOD"
    model_mode: Literal["not_used"] = "not_used"


class SKU(Contract):
    sku_id: UUID
    label: SkuLabel
    price: Amount
    currency: Currency
    available_units: Counter | None
    stock_reason: Literal["UNKNOWN_STOCK"] | None
    cost_amount: None = None
    cost_reason: Literal["UNKNOWN_COST"] = "UNKNOWN_COST"
    inbound_units: None = None
    inbound_reason: Literal["UNKNOWN_INBOUND"] = "UNKNOWN_INBOUND"

    @model_validator(mode="after")
    def stock_knowledge(self) -> Self:
        if (self.available_units is None) != (self.stock_reason is not None):
            raise ValueError("STOCK_KNOWLEDGE_MISMATCH")
        return self


class Product(Contract):
    product_id: UUID
    title: ShortText
    tags: Tags
    version: Counter
    source: SourceRef
    skus: tuple[SKU, ...] = Field(min_length=1, max_length=100)

    @field_validator("tags")
    @classmethod
    def unique_tags(cls, tags: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_tags(tags)


class OrderLine(Contract):
    line_id: UUID
    product_id: UUID
    sku_id: UUID
    quantity: Annotated[int, Field(gt=0)]
    net_amount: Amount
    currency: Currency


class RefundEvent(Contract):
    refund_id: UUID
    occurred_at: Timestamp
    amount: Amount
    currency: Currency
    payment_gateway_status: Literal["UNKNOWN"] = "UNKNOWN"
    quantity: None = None
    restocked: None = None


class Order(Contract):
    order_id: UUID
    created_at: Timestamp
    paid_at: Timestamp | None
    payment_status: Literal["payment_recorded", "payment_timestamp_unknown"]
    net_amount: Amount
    currency: Currency
    demo_fulfillment: Literal["demo_unfulfilled", "demo_fulfilled"]
    fulfillment_version: Counter
    source: SourceRef
    lines: tuple[OrderLine, ...] = Field(min_length=1, max_length=100)
    refunds: tuple[RefundEvent, ...] = Field(max_length=100)

    @model_validator(mode="after")
    def payment_knowledge(self) -> Self:
        if (self.paid_at is None) != (self.payment_status == "payment_timestamp_unknown"):
            raise ValueError("PAYMENT_KNOWLEDGE_MISMATCH")
        return self


class ProductDetail(Contract):
    snapshot: Snapshot
    product: Product
    related_order_ids: tuple[UUID, ...] = Field(max_length=100)


class OrderDetail(Contract):
    snapshot: Snapshot
    order: Order


class Page[T](Contract):
    snapshot: Snapshot
    items: tuple[T, ...] = Field(max_length=100)
    total: Counter
    next_cursor: Annotated[str, Field(max_length=2048)] | None


class ExportData(Contract):
    snapshot: Snapshot
    format: Literal["csv"] = "csv"
    filename: Literal["products.csv", "orders.csv"]
    csv_text: Annotated[str, Field(max_length=1048576)]
    row_count: Annotated[int, Field(ge=0, le=500)]


class BusinessEnvelope[T](Contract):
    schema_version: Literal["v4-business-v1"] = "v4-business-v1"
    server_time: Timestamp
    trace_id: UUID
    status: Literal["OK", "COMMITTED", "UNKNOWN"]
    context: Context
    data: T


class WriteContext(Contract):
    shop_id: UUID
    request_key: UUID
    expected_epoch: Counter
    expected_generation: Counter
    expected_data_revision: Digest


class SetProductTags(WriteContext):
    expected_version: Counter
    tags: Tags

    @field_validator("tags")
    @classmethod
    def unique_tags(cls, tags: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_tags(tags)


class FulfillDemoOrder(WriteContext):
    expected_version: Counter
    action: Literal["mark_demo_fulfilled"]


class ActionReceipt(Contract):
    receipt_id: UUID
    operation: Operation
    request_key: UUID
    payload_digest: Digest
    resource_id: UUID
    resource_version: Counter
    committed_at: Timestamp
    before_revision: Digest
    after_revision: Digest


class ActionResult(Contract):
    receipt: ActionReceipt
    next_step: Literal["READ_CURRENT_RESOURCE"] = "READ_CURRENT_RESOURCE"


class ActionLookup(Contract):
    operation: Operation
    request_key: UUID
    status: Literal["COMMITTED", "UNKNOWN"]
    receipt: ActionReceipt | None

    @model_validator(mode="after")
    def committed_receipt(self) -> Self:
        if (self.status == "COMMITTED") != (self.receipt is not None):
            raise ValueError("ACTION_LOOKUP_MISMATCH")
        if self.receipt is not None and (
            self.receipt.operation != self.operation or self.receipt.request_key != self.request_key
        ):
            raise ValueError("ACTION_LOOKUP_IDENTITY")
        return self


class ColumnMapping(Contract):
    sku: Annotated[str, Field(min_length=1, max_length=80)]
    title: Annotated[str, Field(min_length=1, max_length=80)]
    price: Annotated[str, Field(min_length=1, max_length=80)]
    currency: Annotated[str, Field(min_length=1, max_length=80)]
    tags: Annotated[str, Field(min_length=1, max_length=80)] | None = None

    @model_validator(mode="after")
    def unique_columns(self) -> Self:
        columns = [v for v in self.model_dump().values() if v is not None]
        if len(columns) != len(set(columns)):
            raise ValueError("DUPLICATE_MAPPING")
        return self


class ImportPreviewInput(WriteContext):
    format: Literal["csv", "xlsx"]
    filename: Annotated[str, Field(min_length=1, max_length=128)]
    file_base64: Annotated[str, Field(min_length=1, max_length=2796204)] = Field(repr=False)
    mapping: ColumnMapping | None = None
    mapping_version: Literal[1] = 1
    parent_job_id: UUID | None = None

    @field_validator("mapping_version", mode="before")
    @classmethod
    def integer_mapping(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("MAPPING_VERSION_INTEGER")
        return value


ImportIssueCode = Literal[
    "EMPTY_DATA",
    "FORMULA_REJECTED",
    "INVALID_HEADER",
    "INVALID_ROW_WIDTH",
    "INVALID_SKU",
    "DUPLICATE_SKU",
    "INVALID_TITLE",
    "INVALID_PRICE",
    "CURRENCY_MISMATCH",
    "INVALID_TAGS",
    "MAPPING_REQUIRED",
    "MAPPING_COLUMN_MISSING",
    "ROW_LIMIT",
]


class ImportIssue(Contract):
    row: Counter
    column: Annotated[str, Field(max_length=80)] | None
    code: ImportIssueCode


class ImportSample(Contract):
    row: Annotated[int, Field(ge=2, le=501)]
    cells: tuple[Annotated[str, Field(max_length=512)], ...] = Field(max_length=24)


class NormalizedProduct(Contract):
    sku: SkuLabel
    canonical_sku: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,63}$")]
    title: ShortText
    price: Amount
    currency: Currency
    tags: Tags

    @model_validator(mode="after")
    def canonical_identity(self) -> Self:
        if self.canonical_sku != self.sku.casefold():
            raise ValueError("SKU_CANONICAL_MISMATCH")
        Product.unique_tags(self.tags)
        return self


class ImportJobRef(Contract):
    import_job_id: UUID
    version: Annotated[int, Field(ge=1, le=5)]
    parent_job_id: UUID | None
    job_digest: Digest
    expires_at: Timestamp


class ImportPreviewData(Contract):
    job: ImportJobRef
    state: Literal["DISCOVERED", "READY", "INVALID", "SUPERSEDED", "COMMITTED"]
    file_digest: Digest
    mapping: ColumnMapping | None
    mapping_version: Literal[1] = 1
    headers: tuple[Annotated[str, Field(min_length=1, max_length=80)], ...] = Field(
        min_length=1, max_length=24
    )
    sample: tuple[ImportSample, ...] = Field(max_length=20)
    row_count: Annotated[int, Field(ge=0, le=500)]
    issue_count: Counter
    issues: tuple[ImportIssue, ...] = Field(max_length=100)
    confirmable: bool

    @model_validator(mode="after")
    def ready_only(self) -> Self:
        if self.confirmable != (self.state == "READY"):
            raise ValueError("PREVIEW_CONFIRMABLE_MISMATCH")
        if self.confirmable and (self.mapping is None or self.issue_count or not self.row_count):
            raise ValueError("PREVIEW_NOT_VALIDATED")
        return self


class PreviewLookup(Contract):
    request_key: UUID
    status: Literal["COMMITTED", "UNKNOWN"]
    job: ImportJobRef | None

    @model_validator(mode="after")
    def committed_job(self) -> Self:
        if (self.status == "COMMITTED") != (self.job is not None):
            raise ValueError("PREVIEW_LOOKUP_MISMATCH")
        return self


class ConfirmImport(WriteContext):
    expected_job_version: Annotated[int, Field(ge=1, le=5)]
    expected_job_digest: Digest


class ReadContextData(Contract):
    snapshot: Snapshot
    kind: Literal["dashboard", "product", "order"]
    resource_ids: tuple[UUID, ...] = Field(max_length=100)
    insights: tuple[RuleInsight, ...]
    metrics: tuple[Metric, ...] = ()
    product: Product | None = None
    order: Order | None = None
    model_mode: Literal["not_used"] = "not_used"

    @model_validator(mode="after")
    def matching_context(self) -> Self:
        if self.kind == "dashboard":
            if self.product is not None or self.order is not None:
                raise ValueError("READ_CONTEXT_KIND")
        elif self.kind == "product":
            if self.product is None or self.order is not None or self.metrics:
                raise ValueError("READ_CONTEXT_KIND")
            if self.resource_ids != (self.product.product_id,):
                raise ValueError("READ_CONTEXT_RESOURCE")
        else:
            if self.order is None or self.product is not None or self.metrics:
                raise ValueError("READ_CONTEXT_KIND")
            if self.resource_ids != (self.order.order_id,):
                raise ValueError("READ_CONTEXT_RESOURCE")
        return self


class BusinessError(Contract):
    code: Literal[
        "SESSION_INVALID",
        "ORIGIN_DENIED",
        "CSRF_INVALID",
        "ACCESS_DENIED",
        "RESOURCE_NOT_FOUND",
        "EPOCH_CHANGED",
        "GENERATION_CHANGED",
        "INVALID_REQUEST",
        "IDEMPOTENCY_CONFLICT",
        "VERSION_CONFLICT",
        "STATE_CONFLICT",
        "PAYMENT_STATE_UNKNOWN",
        "SNAPSHOT_CHANGED",
        "IMPORT_INVALID",
        "IMPORT_EXPIRED",
        "LIMIT_EXCEEDED",
        "RATE_LIMITED",
        "SERVICE_UNAVAILABLE",
    ]
    safe_message: Annotated[str, Field(max_length=160)]
    retryable: Literal[False]
    request_key: UUID | None

    @field_validator("retryable", mode="before")
    @classmethod
    def false_boolean(cls, value: object) -> object:
        if value is not False:
            raise ValueError("RETRYABLE_FALSE_REQUIRED")
        return value


class FailureEnvelope(Contract):
    schema_version: Literal["v4-business-v1"] = "v4-business-v1"
    server_time: Timestamp | None
    trace_id: UUID
    status: Literal["REJECTED", "UNKNOWN"]
    error: BusinessError
