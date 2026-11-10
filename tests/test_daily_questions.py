"""报告绑定模板追问的纯金标；不调用模型、commerce、数据库或发送。"""

import json
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from commerceops.application.daily.contracts import DailyReport, MetricKey
from commerceops.application.daily.questions import QuestionSpec, answer
from pydantic import ValidationError

from tests.test_daily_report import END, START, line, order, raw, refund, report

pytestmark = pytest.mark.offline


def gold() -> DailyReport:
    return report(
        raw(
            (
                order("old", created_at=START - timedelta(days=3), order_total="10"),
                order("no-pay", paid_at=None, status="pending"),
                order(
                    "yesterday",
                    created_at=START - timedelta(days=5),
                    paid_at=START - timedelta(days=4),
                ),
            ),
            (line("old", net_amount="10"),),
            (refund("yesterday", amount="2"), refund("old", "later", occurred_at=END, amount="7")),
        )
    )


@pytest.mark.parametrize(
    "key,kind,expected_refs",
    [
        ("paid_order_count", "order", 1),
        ("created_order_count", "order", 1),
        ("orders_without_payment_timestamp", "order", 1),
        ("paid_product_net", "order_line", 1),
        ("refund_count", "refund", 1),
        ("refunded_order_count", "refund", 1),
        ("refund_amount", "refund", 1),
        ("average_paid_order_value", "order", 1),
    ],
)
def test_metric_evidence_uses_own_cohort(key: MetricKey, kind: str, expected_refs: int) -> None:
    result, citations = answer(
        UUID(int=1), gold(), QuestionSpec(kind="metric_evidence", metric_key=key, finding_id=None)
    )
    assert result.total_evidence_count == expected_refs + 1
    assert len([item for item in citations if item.entity_kind == kind]) == expected_refs
    assert result.model_requests_enabled is False and result.external_sender_enabled is False
    assert result.narrative_mode == "template" and result.evidence_mode == "not_used"
    for item in citations:
        assert item.snapshot_id == gold().snapshot_id
        if item.entity_kind != "metric":
            assert item.entity_ref not in {"old", "no-pay", "yesterday", "later"}
            assert item.value is not None and "config_digest" not in item.value
            assert "source_binding_id" not in item.value and "order_id" not in item.value


def test_definition_contains_program_value_without_external_calls() -> None:
    result, citations = answer(
        UUID(int=1),
        gold(),
        QuestionSpec(kind="metric_definition", metric_key="paid_order_total", finding_id=None),
    )
    assert (
        "10.00" in result.summary and len(citations) == 1 and citations[0].entity_kind == "metric"
    )
    assert citations[0].value is not None
    assert json.loads(citations[0].value) == "10"


def test_finding_references_are_exact_and_unknown_target_rejected() -> None:
    stored = gold()
    finding = next(f for f in stored.findings if f.code == "PAYMENT_TIMESTAMP_MISSING")
    result, citations = answer(
        UUID(int=1),
        stored,
        QuestionSpec(kind="finding_reason", metric_key=None, finding_id=finding.finding_id),
    )
    assert set(result.citation_ids) == set(finding.evidence_ids)
    assert all(item.entity_kind == "order" for item in citations)
    with pytest.raises(ValueError, match="DAILY_FINDING_NOT_FOUND"):
        answer(
            UUID(int=1),
            stored,
            QuestionSpec(kind="finding_reason", metric_key=None, finding_id="f" * 64),
        )


def test_incomplete_quality_is_explained_without_zero_metrics() -> None:
    stored = report(raw(coverage={"orders_complete": False}))
    result, citations = answer(
        UUID(int=1), stored, QuestionSpec(kind="data_quality", metric_key=None, finding_id=None)
    )
    assert "不可用" in result.summary and result.total_evidence_count == 1
    assert citations[0].entity_kind == "coverage"
    with pytest.raises(ValueError, match="DAILY_METRICS_UNAVAILABLE"):
        answer(
            UUID(int=1),
            stored,
            QuestionSpec(kind="metric_evidence", metric_key="paid_order_count", finding_id=None),
        )


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "data_quality", "metric_key": "paid_order_count", "finding_id": None},
        {"kind": "finding_reason", "metric_key": None, "finding_id": None},
        {"kind": "metric_definition", "metric_key": None, "finding_id": None},
        {"kind": "arbitrary_sql", "metric_key": None, "finding_id": None},
    ],
)
def test_question_is_strict_and_typed(body: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        QuestionSpec.model_validate(body)
