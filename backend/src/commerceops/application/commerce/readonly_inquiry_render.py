"""Deterministic Chinese answer from verified typed claims and evidence refs."""

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext

from commerceops.application.commerce.readonly_inquiry_contracts import Fact, Window
from commerceops.application.commerce.readonly_inquiry_executor import Outcome

LABELS = {
    "available_stock": "可用库存",
    "inbound_units": "在途数量",
    "sold_units": "订单售出件数（按订单创建时间）",
    "order_net": "订单原口径净额",
    "order_average": "每行订单均额",
    "refund_cohort": "对应订单 cohort 的退款额（非本窗口现金流）",
}
SAFE_STATUS = {
    "clarify": "商品或请求范围有歧义，请明确要查询的对象。",
    "insufficient_evidence": "证据不足，无法安全给出结论。",
    "source_incomplete": "来源读取不完整，无法安全给出结论。",
    "access_denied": "当前身份无权查看此结果。",
    "budget_exceeded": "本次查询已达到范围或调用上限。",
    "timeout": "本次查询超时，请核对来源后重试。",
}


@dataclass(frozen=True)
class RenderedAnswer:
    text: str
    evidence_refs: tuple[str, ...]


def window_text(window: Window | None) -> str:
    if window is None:
        return ""
    return f"[{window.start.isoformat()}, {window.end.isoformat()})"


def number(value: str) -> str:
    with localcontext() as decimal_context:
        decimal_context.prec = 50
        decimal = Decimal(value)
        if not decimal.is_finite():
            raise ValueError("INVALID_NUMBER")
        return format(decimal, "f")


def value_text(fact: Fact) -> str:
    if fact.value is None:
        return "不可计算（分母为 0）" if "ZERO_DENOMINATOR" in fact.quality_flags else "未知"
    unit = fact.currency or fact.unit
    return f"{number(fact.value)} {unit}"


def start_of(fact: Fact) -> datetime:
    if fact.window is None:
        raise ValueError("INVALID_COMPARISON")
    return fact.window.start


def render(outcome: Outcome) -> RenderedAnswer:
    if outcome.status != "complete":
        return RenderedAnswer(SAFE_STATUS.get(outcome.status, "此结果暂时无法安全展示。"), ())
    indexed: dict[str, tuple[Fact, str]] = {}
    for result in outcome.results:
        for fact in result.facts:
            if fact.evidence_id in indexed:
                raise ValueError("DUPLICATE_EVIDENCE")
            indexed[fact.evidence_id] = (fact, (fact.as_of or result.as_of).isoformat())
    if (
        not outcome.claims
        or set(outcome.evidence_refs) != {ref for claim in outcome.claims for ref in claim.refs}
        or not set(outcome.evidence_refs) <= indexed.keys()
    ):
        raise ValueError("INVALID_CLAIMS")
    sentences = []
    for claim in outcome.claims:
        facts = [indexed[ref][0] for ref in claim.refs]
        if claim.kind == "fact":
            fact = facts[0]
            label = LABELS.get(fact.metric)
            if label is None:
                raise ValueError("UNKNOWN_METRIC")
            sku = f"{fact.sku_key}：" if fact.sku_key else ""
            quality = f"；质量：{'、'.join(fact.quality_flags)}" if fact.quality_flags else ""
            sentences.append(
                f"{sku}{label} {value_text(fact)}；窗口 {window_text(fact.window) or '当前观测'}；"
                f"观测 {indexed[claim.refs[0]][1]}{quality}；证据 {claim.refs[0]}。"
            )
            continue
        if claim.kind != "compare" or len(facts) != 2:
            raise ValueError("INVALID_CLAIM")
        if any(item.window is None for item in facts):
            raise ValueError("INVALID_COMPARISON")
        before, after = sorted(facts, key=start_of)
        if (
            before.window is None
            or after.window is None
            or before.window.end > after.window.start
            or before.metric != after.metric
            or before.sku_key != after.sku_key
            or before.currency != after.currency
            or before.unit != after.unit
        ):
            raise ValueError("INVALID_COMPARISON")
        label = LABELS.get(before.metric)
        if label is None:
            raise ValueError("UNKNOWN_METRIC")
        if before.value is None or after.value is None:
            detail = "变化不可计算（至少一期数值未知）"
        else:
            with localcontext() as decimal_context:
                decimal_context.prec = 50
                old, new = Decimal(before.value), Decimal(after.value)
                delta = new - old
                if old == 0:
                    rate = "比例不可计算（前期为 0）"
                else:
                    percent = ((delta / old) * 100).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    rate = f"变化率 {format(percent, 'f')}%"
                detail = f"变化 {format(delta, 'f')} {before.currency or before.unit}；{rate}"
        before_time = before.as_of.isoformat() if before.as_of else "未报告"
        after_time = after.as_of.isoformat() if after.as_of else "未报告"
        sentences.append(
            f"{before.sku_key or '所选范围'}：{label}；前期 {value_text(before)} "
            f"{window_text(before.window)}（观测 {before_time}）；"
            f"本期 {value_text(after)} {window_text(after.window)}"
            f"（观测 {after_time}）；"
            f"{detail}；证据 {claim.refs[0]}、{claim.refs[1]}。"
        )
    return RenderedAnswer("\n".join(sentences), outcome.evidence_refs)
