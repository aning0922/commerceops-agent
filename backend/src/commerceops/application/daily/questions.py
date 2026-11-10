"""冻结日报的四类模板追问与脱敏证据；纯函数，不采集、不调用模型或写工具。"""

import json
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from commerceops.application.commerce.contracts import Digest
from commerceops.application.daily.contracts import DailyDTO, DailyEvidence, DailyReport, MetricKey
from commerceops.domain.commerce_values import facts_hash, utc_time

QUESTION_WORKFLOW = "p6-daily-question-v1"

QuestionKind = Literal["metric_definition", "metric_evidence", "finding_reason", "data_quality"]
DEFINITIONS: dict[str, str] = {
    "created_order_count": "按报告业务日创建时间统计的distinct订单数，包含所有已识别状态。",
    "paid_order_count": "按报告业务日记录的支付时间统计distinct订单，创建日不限；不证明网关到账。",
    "paid_product_net": "支付cohort商品行折扣后未税金额；不扣退款，不重复扣优惠券。",
    "paid_product_tax": "支付cohort商品行税额。",
    "paid_shipping_net": "支付cohort订单运费未税金额，逐单仅计一次。",
    "paid_shipping_tax": "支付cohort订单运费税额，逐单仅计一次。",
    "paid_fee_net": "支付cohort显式订单费用未税金额，逐单仅计一次。",
    "paid_fee_tax": "支付cohort显式订单费用税额，逐单仅计一次。",
    "paid_order_total": "支付cohort商品、税、运费和费用六项之和；不代表利润或实际结算。",
    "refund_count": "按报告业务日退款发生时间统计distinct退款记录，订单创建/支付日不限。",
    "refunded_order_count": "当日退款记录对应的distinct订单数。",
    "refund_amount": "当日平台退款记录金额，不从金额推件数或已回库，不证明退款网关成功。",
    "average_paid_order_value": "paid_order_total除以paid_order_count的精确比值；零分母为null。",
    "orders_without_payment_timestamp": "本业务日创建但未记录paid_at的订单数；不能据此判断未支付。",
}


class QuestionSpec(DailyDTO):
    kind: QuestionKind
    metric_key: MetricKey | None
    finding_id: Digest | None

    @model_validator(mode="after")
    def selected(self) -> Self:
        if self.kind in {"metric_definition", "metric_evidence"}:
            if self.metric_key is None or self.finding_id is not None:
                raise ValueError("DAILY_QUESTION_TARGET_INVALID")
        elif self.kind == "finding_reason":
            if self.finding_id is None or self.metric_key is not None:
                raise ValueError("DAILY_QUESTION_TARGET_INVALID")
        elif self.metric_key is not None or self.finding_id is not None:
            raise ValueError("DAILY_QUESTION_TARGET_INVALID")
        return self


class QuestionInput(DailyDTO):
    schema_version: Literal["p6-daily-question-v1"]
    request_key: UUID
    report_id: UUID
    snapshot_id: UUID
    content_hash: Digest
    facts_hash: Digest
    question: QuestionSpec


class QuestionTaskRequest(DailyDTO):
    schema_version: Literal["p6-daily-question-task-v1"]
    parent_task_id: UUID
    input: QuestionInput
    request_hash: Digest
    requester_auth_version: Annotated[int, Field(ge=1)]

    @model_validator(mode="after")
    def request_digest(self) -> Self:
        if self.request_hash != facts_hash(self.input.model_dump(mode="json")):
            raise ValueError("DAILY_QUESTION_REQUEST_INVALID")
        return self


class Citation(DailyDTO):
    citation_id: Digest
    snapshot_id: UUID
    entity_kind: Literal["order", "order_line", "refund", "coverage", "rule", "metric"]
    entity_ref: str
    field_path: str
    # 精确值来自允许事实；不得带源原文/客户字段/配置引用。
    value: str | None


class TemplateAnswer(DailyDTO):
    schema_version: Literal["p6-daily-answer-v1"]
    report_id: UUID
    snapshot_id: UUID
    content_hash: Digest
    facts_hash: Digest
    kind: QuestionKind
    summary: str
    total_evidence_count: Annotated[int, Field(ge=0)]
    citation_ids: tuple[Digest, ...]

    @model_validator(mode="after")
    def evidence_count(self) -> Self:
        if len(set(self.citation_ids)) != len(
            self.citation_ids
        ) or self.total_evidence_count != len(self.citation_ids):
            raise ValueError("DAILY_CITATION_COUNT_INVALID")
        return self

    @field_validator(
        "model_requests_enabled", "external_sender_enabled", mode="before", check_fields=False
    )
    @classmethod
    def no_numeric_flags(cls, value: object) -> object:
        if type(value) is not bool:
            raise ValueError("DAILY_BOOLEAN_INVALID")
        return value

    narrative_mode: Literal["template"]
    evidence_mode: Literal["not_used"]
    model_requests_enabled: Literal[False]
    external_sender_enabled: Literal[False]


class QuestionResult(DailyDTO):
    answer: TemplateAnswer
    citations: tuple[Citation, ...]

    @model_validator(mode="after")
    def citations_match(self) -> Self:
        if self.answer.citation_ids != tuple(item.citation_id for item in self.citations) or any(
            item.snapshot_id != self.answer.snapshot_id for item in self.citations
        ):
            raise ValueError("DAILY_CITATION_BINDING_INVALID")
        return self


def _safe_evidence(evidence: DailyEvidence) -> Citation:
    # public entity_ref不暴露原平台ID；绑定同snapshot的原始evidence_id仍可定位内部行。
    ref = (
        evidence.entity_kind
        + ":"
        + facts_hash(
            {"kind": evidence.entity_kind, "ref": evidence.entity_ref, "order": evidence.order_id}
        )[:16]
    )
    raw = json.loads(evidence.value) if evidence.value is not None else None
    value = None
    if isinstance(raw, dict):
        allowed = {
            "order": (
                "currency",
                "status",
                "created_at",
                "paid_at",
                "shipping_net",
                "shipping_tax",
                "fee_net",
                "fee_tax",
                "order_total",
            ),
            "order_line": ("currency", "quantity", "net_amount", "tax_amount"),
            "refund": ("currency", "occurred_at", "amount", "quantity_reason", "restocked"),
            "coverage": (
                "strategy",
                "orders_complete",
                "order_lines_complete",
                "refunds_complete",
                "quality_flags",
                "consistency",
            ),
            "rule": ("rule_version", "currency", "low_paid_total", "high_refund_amount"),
        }[evidence.entity_kind]
        value = json.dumps(
            {key: raw[key] for key in allowed if key in raw},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    return Citation(
        citation_id=evidence.evidence_id,
        snapshot_id=evidence.snapshot_id,
        entity_kind=evidence.entity_kind,
        entity_ref=ref,
        field_path=evidence.field_path,
        value=value,
    )


def answer(
    report_id: UUID, stored: DailyReport, spec: QuestionSpec
) -> tuple[TemplateAnswer, tuple[Citation, ...]]:
    report = DailyReport.model_validate_json(stored.model_dump_json())
    spec = QuestionSpec.model_validate_json(spec.model_dump_json())
    refs: tuple[DailyEvidence, ...]
    citations: tuple[Citation, ...]
    summary: str
    if spec.kind in {"metric_definition", "metric_evidence"}:
        if report.metrics is None or spec.metric_key is None:
            raise ValueError("DAILY_METRICS_UNAVAILABLE")
        value = report.metrics.model_dump(mode="json")[spec.metric_key]
        metric = Citation(
            citation_id=facts_hash(
                {"report": str(report_id), "facts": report.facts_hash, "metric": spec.metric_key}
            ),
            snapshot_id=report.snapshot_id,
            entity_kind="metric",
            entity_ref="report_metric",
            field_path="metrics." + spec.metric_key,
            value=json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )
        if spec.kind == "metric_definition":
            citations = (metric,)
        else:
            refs = metric_evidence(report, spec.metric_key)
            citations = (metric, *(_safe_evidence(item) for item in refs))
        shown = next(item.value for item in report.display if item.metric_key == spec.metric_key)
        summary = (
            DEFINITIONS[spec.metric_key]
            + f" 本报告展示值：{shown if shown is not None else '未知（零分母）'}。"
        )
    elif spec.kind == "finding_reason":
        matches = [finding for finding in report.findings if finding.finding_id == spec.finding_id]
        if len(matches) != 1:
            raise ValueError("DAILY_FINDING_NOT_FOUND")
        finding = matches[0]
        refs = tuple(item for item in report.evidence if item.evidence_id in finding.evidence_ids)
        if len(refs) != len(finding.evidence_ids):
            raise ValueError("DAILY_EVIDENCE_BINDING_INVALID")
        citations = tuple(_safe_evidence(item) for item in refs)
        summary = f"规则{finding.code}，级别{finding.severity}；依据与阈值取本报告冻结版本。"
    else:
        refs = tuple(
            item
            for item in report.evidence
            if item.entity_kind == "coverage"
            or any(
                item.evidence_id in finding.evidence_ids
                for finding in report.findings
                if finding.severity == "blocking"
            )
        )
        citations = tuple(_safe_evidence(item) for item in refs)
        summary = (
            "来源完整，指标基于观测快照；不证明平台结算或库存变化。"
            if report.complete
            else "来源或金额存在阻断，完整日报指标不可用；未将缺失数据当作零。"
        )
    citations = tuple(sorted(citations, key=lambda item: item.citation_id))
    return TemplateAnswer(
        schema_version="p6-daily-answer-v1",
        report_id=report_id,
        snapshot_id=report.snapshot_id,
        content_hash=report.content_hash,
        facts_hash=report.facts_hash,
        kind=spec.kind,
        summary=summary,
        total_evidence_count=len(citations),
        citation_ids=tuple(item.citation_id for item in citations),
        narrative_mode="template",
        evidence_mode="not_used",
        model_requests_enabled=False,
        external_sender_enabled=False,
    ), citations


def metric_evidence(report: DailyReport, metric: MetricKey) -> tuple[DailyEvidence, ...]:
    parsed = {
        item.evidence_id: json.loads(item.value)
        for item in report.evidence
        if item.value is not None
    }
    paid = {
        item.entity_ref
        for item in report.evidence
        if item.entity_kind == "order"
        and parsed[item.evidence_id].get("paid_at") is not None
        and report.window.contains(utc_time(parsed[item.evidence_id]["paid_at"]))
    }
    refs = []
    for item in report.evidence:
        row = parsed.get(item.evidence_id, {})
        selected = False
        if metric in {"created_order_count", "orders_without_payment_timestamp"}:
            selected = item.entity_kind == "order" and report.window.contains(
                utc_time(row["created_at"])
            )
            if metric == "orders_without_payment_timestamp":
                selected = selected and row["paid_at"] is None
        elif metric in {"refund_count", "refunded_order_count", "refund_amount"}:
            selected = item.entity_kind == "refund" and report.window.contains(
                utc_time(row["occurred_at"])
            )
        elif metric in {"paid_product_net", "paid_product_tax"}:
            selected = item.entity_kind == "order_line" and item.order_id in paid
        else:
            selected = item.entity_kind == "order" and item.entity_ref in paid
        if selected:
            refs.append(item)
    # 完整空日也引用覆盖证明，不能将无订单证据当作读取失败。
    if not refs:
        refs = [item for item in report.evidence if item.entity_kind == "coverage"]
    return tuple(refs)
