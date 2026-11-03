"""真实Read DTO与生成资产的边界；外部JSON Schema引擎另用同一组wire案例核验。"""

import copy
import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from commerceops.application.daily.read_models import (
    QUESTION_KINDS,
    DailyRead,
    public_report,
)
from pydantic import ValidationError

from scripts.export_daily_schema import TARGET, schema_bytes
from tests.test_daily_report import END, order, raw, report

pytestmark = pytest.mark.offline


def valid_read() -> dict[str, Any]:
    stored = report(raw((order("1", shipping_net="12.34", order_total="12.34"),)))
    return {
        "schema_version": "p3-web-v1",
        "identity_mode": "session",
        "server_time": stored.as_of.isoformat(),
        "trace_id": str(UUID(int=11)),
        "daily": {
            "schema_version": "p6-m3-web-v1",
            "task_id": str(UUID(int=12)),
            "shop_id": str(UUID(int=2)),
            "kind": "daily_report",
            "workflow_version": "p6-daily-report-v1",
            "created_at": END.isoformat(),
            "updated_at": END.isoformat(),
            "question_creation_enabled": False,
            "question_kinds": list(QUESTION_KINDS),
            "schedule_enabled": False,
            "delivery_enabled": False,
            "state": "completed",
            "failure_code": None,
            "report": public_report(UUID(int=13), stored).model_dump(mode="json"),
        },
    }


def wire_cases() -> list[tuple[str, dict[str, Any], bool, bool]]:
    """最后两列分别是DTO语义与JSON Schema结构预期，不假装schema能验公式/hash。"""
    base = valid_read()
    cases = [("valid", base, True, True)]
    for state in ("queued", "analyzing", "failed", "needs_attention"):
        other = copy.deepcopy(base)
        other["daily"].update(
            state=state,
            report=None,
            failure_code=(None if state in ("queued", "analyzing") else "DAILY_SOURCE_UNAVAILABLE"),
        )
        cases.append((f"valid-{state}", other, True, True))
    other = copy.deepcopy(base)
    quality = report(raw(coverage={"order_lines_complete": False}))
    other["daily"].update(
        state="needs_attention",
        failure_code="DAILY_SOURCE_INCOMPLETE",
        report=public_report(UUID(int=13), quality).model_dump(mode="json"),
    )
    cases.append(("valid-quality-diagnostic", other, True, True))
    paths = [
        ("created_order_count",),
        ("paid_order_count",),
        ("refund_count",),
        ("refunded_order_count",),
        ("orders_without_payment_timestamp",),
        ("status_counts", 0, "count"),
    ]
    for path in paths:
        other = copy.deepcopy(base)
        target = other["daily"]["report"]["metrics"]
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = -1
        cases.append((f"negative-{path}", other, False, False))
    for key in ("paid_order_total", "paid_fee_net"):
        for invalid in (12.34, "-0", "012.34", "12x34", "1.0000001", "100000000000000"):
            other = copy.deepcopy(base)
            other["daily"]["report"]["metrics"][key] = invalid
            cases.append((f"money-{key}-{invalid}", other, False, False))
    other = copy.deepcopy(base)
    other["daily"]["report"]["metrics"]["extra"] = True
    cases.append(("extra-metric", other, False, False))
    other = copy.deepcopy(base)
    other["daily"]["report"]["evidence_count"] = -1
    cases.append(("negative-evidence-count", other, False, False))
    other = copy.deepcopy(base)
    other["daily"]["state"] = "failed"
    cases.append(("failed-with-complete-report", other, False, False))
    other = copy.deepcopy(base)
    other["daily"]["report"]["facts_hash"] = "not-a-digest"
    cases.append(("malformed-hash", other, False, False))
    other = copy.deepcopy(base)
    other["daily"]["report"]["display"] = []
    cases.append(("missing-display", other, False, True))
    other = copy.deepcopy(base)
    other["daily"]["report"]["metrics"]["average_paid_order_value"] = {
        "numerator": "2",
        "denominator": "1",
    }
    cases.append(("wrong-average", other, False, True))
    other = copy.deepcopy(base)
    other["daily"]["report"]["findings"][0]["finding_id"] = "b" * 64
    cases.append(("wrong-finding-hash", other, False, True))
    return cases


@pytest.mark.parametrize("name,body,accepted,_schema_accepted", wire_cases())
def test_wire_cases(
    name: str, body: dict[str, Any], accepted: bool, _schema_accepted: bool
) -> None:
    if accepted:
        read = DailyRead.model_validate_json(json.dumps(body))
        assert DailyRead.model_validate_json(read.model_dump_json()) == read
    else:
        with pytest.raises(ValidationError):
            DailyRead.model_validate_json(json.dumps(body))


def test_asset_is_exact_model_generation_and_standard_count_constraints() -> None:
    assert TARGET.read_bytes() == schema_bytes()
    schema = json.loads(TARGET.read_bytes())
    props = schema["$defs"]["ReadMetrics"]["properties"]
    for key in (
        "created_order_count",
        "paid_order_count",
        "refund_count",
        "refunded_order_count",
        "orders_without_payment_timestamp",
    ):
        assert props[key]["minimum"] == 0 and "ge" not in props[key]
    assert schema["$defs"]["ReadStatusCount"]["properties"]["count"]["minimum"] == 0
    # 所有模型明示extra=forbid，生成资产不得后处理约束。
    for value in schema["$defs"].values():
        if value.get("type") == "object":
            assert value["additionalProperties"] is False
    assert Path(TARGET).is_file()


def test_public_projection_verifies_stored_hash_and_excludes_private_fields() -> None:
    stored = report(raw())
    with pytest.raises(ValidationError, match="DAILY_FACTS_HASH_MISMATCH"):
        public_report(UUID(int=1), stored.model_copy(update={"facts_hash": "b" * 64}))
    body = valid_read()["daily"]["report"]
    assert set(body["source"]) == {
        "source_kind",
        "source_config_version",
        "fixture_version",
        "currency",
        "timezone",
        "coverage_scope",
    }
    assert "evidence" not in body and "config_digest" not in body["source"]
