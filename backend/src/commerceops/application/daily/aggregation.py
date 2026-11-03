"""冻结日报的纯聚合；用整数微单位和有理数避免 Decimal context 舍入。"""

from collections import Counter, defaultdict
from collections.abc import Iterable
from decimal import Decimal
from fractions import Fraction
from typing import Literal

from commerceops.application.daily.contracts import (
    DailyEvidence,
    DailyFinding,
    DailyInput,
    DailyMetrics,
    DailyReport,
    ExactAverage,
    FindingCode,
    MetricDisplay,
    MetricKey,
    StatusCount,
    metric_display,
)
from commerceops.domain.commerce_values import canonical_bytes, facts_hash, money


class AggregateOutOfRange(ValueError):
    """精确累计值超过持久金额边界，不能提交完整指标。"""


MONEY_LIMIT = 10**20  # numeric(20,6) 的整数微单位上界（不含）。


def micro_units(value: Decimal) -> int:
    checked = money(value)
    if checked == 0:
        return 0
    parts = checked.as_tuple()
    exponent = parts.exponent
    if not isinstance(exponent, int):
        raise ValueError("INVALID_MONEY")
    integer = int("".join(str(digit) for digit in parts.digits)) * int(10 ** (exponent + 6))
    return -integer if parts.sign else integer


def amount(units: int) -> Decimal:
    if abs(units) >= MONEY_LIMIT:
        raise AggregateOutOfRange("DAILY_AGGREGATE_OUT_OF_RANGE")
    return Decimal((int(units < 0), tuple(int(d) for d in str(abs(units))), -6))


def total(values: Iterable[Decimal]) -> Decimal:
    # 无浮点或 Decimal 加法；即使有负费用，结果也不受输入顺序或 precision 影响。
    return amount(sum(micro_units(value) for value in values))


def _evidence(
    data: DailyInput,
    kind: Literal["order", "order_line", "refund", "coverage", "rule"],
    ref: str,
    value: object,
    *,
    order_id: str | None = None,
) -> DailyEvidence:
    body = {
        "snapshot_id": str(data.snapshot_id),
        "entity_kind": kind,
        "entity_ref": ref,
        "order_id": order_id,
        "field_path": "record",
        "value": canonical_bytes(value).decode("utf-8"),
    }
    return DailyEvidence.model_validate(
        {**body, "snapshot_id": data.snapshot_id, "evidence_id": facts_hash(body)}
    )


def _finding(
    data: DailyInput,
    code: FindingCode,
    severity: Literal["info", "warning", "blocking"],
    evidence: Iterable[DailyEvidence],
    metric_key: MetricKey | None = None,
) -> DailyFinding:
    draft = DailyFinding.model_construct(
        finding_id="0" * 64,
        code=code,
        severity=severity,
        metric_key=metric_key,
        evidence_ids=tuple(sorted(e.evidence_id for e in evidence)),
        rule_config_hash=data.rules.config_hash,
    )
    body = draft.model_dump(mode="python", exclude={"finding_id"})
    return DailyFinding.model_validate({**body, "finding_id": facts_hash(body)})


def _finish(
    data: DailyInput,
    evidence: list[DailyEvidence],
    findings: list[DailyFinding],
    metrics: DailyMetrics | None = None,
    display: tuple[MetricDisplay, ...] = (),
) -> DailyReport:
    # 暂存构造后立即完整校验，不向调用者返回未校验的 DTO。
    draft = DailyReport.model_construct(
        snapshot_id=data.snapshot_id,
        content_hash=data.content_hash,
        source=data.source,
        business_day=data.business_day,
        as_of=data.as_of,
        window=data.window,
        coverage=data.coverage.model_copy(
            update={"quality_flags": tuple(sorted(data.coverage.quality_flags))}
        ),
        rules=data.rules,
        complete=metrics is not None,
        metrics=metrics,
        findings=tuple(sorted(findings, key=lambda f: (f.code, f.evidence_ids))),
        evidence=tuple(sorted(evidence, key=lambda e: e.evidence_id)),
        display=display,
        facts_hash="0" * 64,
    )
    return DailyReport.model_validate(
        {**draft.model_dump(mode="python"), "facts_hash": facts_hash(draft.canonical_facts())}
    )


def aggregate_daily(snapshot: DailyInput) -> DailyReport:
    """拒绝错误关联/非法标量；可诊断的不完整/金额错误输出 metrics=null。"""
    data = DailyInput.model_validate(snapshot.model_dump(mode="python"))
    content = data.canonical_content()
    coverage = _evidence(data, "coverage", "coverage", content["coverage"])
    rules = _evidence(data, "rule", "rules", data.rules.model_dump(mode="json"))
    order_evidence = {
        order.order_id: _evidence(data, "order", order.order_id, order.model_dump(mode="json"))
        for order in data.orders
    }
    line_evidence = [
        _evidence(
            data, "order_line", line.line_id, line.model_dump(mode="json"), order_id=line.order_id
        )
        for line in data.order_lines
    ]
    refund_evidence = {
        refund.refund_id: _evidence(
            data,
            "refund",
            refund.refund_id,
            {
                **refund.model_dump(mode="json"),
                "lines": [
                    line.model_dump(mode="json")
                    for line in sorted(refund.lines, key=lambda line: line.line_id)
                ],
            },
            order_id=refund.order_id,
        )
        for refund in data.refunds
    }
    evidence = [
        coverage,
        rules,
        *order_evidence.values(),
        *line_evidence,
        *refund_evidence.values(),
    ]
    findings: list[DailyFinding] = []
    if (
        not data.coverage.orders_complete
        or not data.coverage.order_lines_complete
        or not data.coverage.refunds_complete
        or (data.coverage.quality_flags)
    ):
        findings.append(_finding(data, "SOURCE_INCOMPLETE", "blocking", [coverage]))

    # 全部发现订单均对账，不能丢弃坏订单来获得完整报告。
    line_parts: dict[str, int] = defaultdict(int)
    line_refs: dict[str, list[DailyEvidence]] = defaultdict(list)
    for line in data.order_lines:
        line_parts[line.order_id] += micro_units(line.net_amount) + micro_units(line.tax_amount)
    for ref in line_evidence:
        if ref.order_id is not None:
            line_refs[ref.order_id].append(ref)
    for order in data.orders:
        parts = (order.shipping_net, order.shipping_tax, order.fee_net, order.fee_tax)
        expected = sum(micro_units(value) for value in parts) + line_parts[order.order_id]
        if expected != micro_units(order.order_total):
            refs = [order_evidence[order.order_id], *line_refs[order.order_id]]
            findings.append(_finding(data, "ORDER_AMOUNT_MISMATCH", "blocking", refs))
    if findings:
        return _finish(data, evidence, findings)

    window = data.window
    created = [order for order in data.orders if window.contains(order.created_at)]
    paid = [
        order
        for order in data.orders
        if order.paid_at is not None and window.contains(order.paid_at)
    ]
    paid_ids = {order.order_id for order in paid}
    lines = [line for line in data.order_lines if line.order_id in paid_ids]
    refunds = [refund for refund in data.refunds if window.contains(refund.occurred_at)]
    missing = [order for order in created if order.paid_at is None]
    try:
        paid_total = total(order.order_total for order in paid)
        refund_total = total(refund.amount for refund in refunds)
        ratio = Fraction(paid_total) / len(paid) if paid else None
        metrics = DailyMetrics(
            created_order_count=len(created),
            paid_order_count=len(paid),
            paid_product_net=total(line.net_amount for line in lines),
            paid_product_tax=total(line.tax_amount for line in lines),
            paid_shipping_net=total(order.shipping_net for order in paid),
            paid_shipping_tax=total(order.shipping_tax for order in paid),
            paid_fee_net=total(order.fee_net for order in paid),
            paid_fee_tax=total(order.fee_tax for order in paid),
            paid_order_total=paid_total,
            refund_count=len(refunds),
            refunded_order_count=len({refund.order_id for refund in refunds}),
            refund_amount=refund_total,
            orders_without_payment_timestamp=len(missing),
            status_counts=tuple(
                StatusCount(status=status, count=count)
                for status, count in sorted(Counter(o.status for o in created).items())
            ),
            average_paid_order_value=ExactAverage(
                numerator=str(ratio.numerator), denominator=str(ratio.denominator)
            )
            if ratio is not None
            else None,
            average_reason="ZERO_DENOMINATOR" if ratio is None else None,
        )
    except AggregateOutOfRange:
        findings.append(_finding(data, "AGGREGATE_OUT_OF_RANGE", "blocking", evidence))
        return _finish(data, evidence, findings)

    if missing:
        findings.append(
            _finding(
                data,
                "PAYMENT_TIMESTAMP_MISSING",
                "warning",
                [order_evidence[o.order_id] for o in missing],
                "orders_without_payment_timestamp",
            )
        )
    if not paid:
        findings.append(
            _finding(data, "NO_RECORDED_PAYMENTS", "info", [coverage], "paid_order_count")
        )
    if data.rules.low_paid_total is None or data.rules.high_refund_amount is None:
        findings.append(_finding(data, "RULE_NOT_CONFIGURED", "info", [rules]))
    if data.rules.low_paid_total is not None and paid_total < data.rules.low_paid_total:
        findings.append(
            _finding(
                data,
                "LOW_PAID_TOTAL",
                "warning",
                [rules, coverage, *(order_evidence[o.order_id] for o in paid)],
                "paid_order_total",
            )
        )
    if data.rules.high_refund_amount is not None and refund_total > data.rules.high_refund_amount:
        findings.append(
            _finding(
                data,
                "HIGH_REFUND_AMOUNT",
                "warning",
                [rules, coverage, *(refund_evidence[r.refund_id] for r in refunds)],
                "refund_amount",
            )
        )
    return _finish(data, evidence, findings, metrics, metric_display(metrics, data.source.currency))
