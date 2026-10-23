"""N01 有限全文法、原 PRD/J01 句式与参数出处；不调用模型或业务存储。"""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from commerceops.adapters.commerce.mock import Fixture
from commerceops.application.replenishment.nl_preflight import (
    SUPPORTED_INTENTS,
    PreflightInput,
    PreflightResult,
    Window,
    parse_preflight,
)
from commerceops.domain.commerce_values import complete_days

from tests.inventory_support import DIRECTORY

pytestmark = pytest.mark.offline


def test_standalone_closed_n01_openapi_has_no_unresolved_shared_schema_or_security() -> None:
    spec = json.loads(Path("docs/contracts/p4-n01-openapi.json").read_text())

    def checked(value: object) -> None:
        if isinstance(value, dict):
            ref = value.get("$ref")
            if ref is not None:
                assert isinstance(ref, str) and ref.startswith("#/components/schemas/")
                assert ref.removeprefix("#/components/schemas/") in spec["components"]["schemas"]
            for item in value.values():
                checked(item)
        elif isinstance(value, list):
            for item in value:
                checked(item)

    checked(spec)
    assert set(spec["components"]["securitySchemes"]) == {"SessionCookie"}


def parse(text: str) -> PreflightResult:
    fixture = Fixture.load(DIRECTORY, "baseline")
    start, end = complete_days(fixture.now, fixture.source.timezone)
    return parse_preflight(
        PreflightInput(
            schema_version="p3-web-v1", shop_id=uuid4(), fixture_case="baseline", text=text
        ),
        Window(start=start, end=end, timezone=fixture.source.timezone, as_of=fixture.now),
    )


@pytest.mark.parametrize("intent", SUPPORTED_INTENTS)
def test_original_prd_j01_and_declared_intents_need_explicit_missing_parameters(
    intent: str,
) -> None:
    result = parse(intent + "。")
    assert (result.status, result.reason, result.missing) == (
        "clarify",
        "MISSING_PARAMETERS",
        ("L", "R", "S"),
    )
    assert result.draft is None and not result.execution_available and result.requires_confirmation
    assert all(
        c.source == "demo_assumption" and c.start is None and c.end is None
        for c in result.candidates
    )
    ready = parse(intent + " L=3 R=7 S=2。")
    assert ready.status == "ready" and ready.draft and ready.draft.L == 3


@pytest.mark.parametrize(
    "block",
    [
        "L=0 R=365 S=2",
        "S:365天;L:0天;R:7天。",
        "L=3\u2003R=7\u3000S=2",
        "L=3 天，R=7 天；S=2 天！？",
        "L:3,R:7,S:2",
    ],
)
def test_ready_consumes_all_accepted_lrs_days_unicode_and_exact_source_spans(block: str) -> None:
    text = "请分析库存并生成补货建议，全店，最近七个完整自然日 " + block
    result = parse(text)
    assert result.status == "ready" and not result.missing and result.draft
    for candidate in result.candidates:
        assert candidate.start is not None and candidate.end is not None
        assert text[candidate.start : candidate.end] == str(candidate.value)
        assert candidate.source == "explicit_text"
    assert result.window.timezone == "Asia/Shanghai" and result.window.as_of.year == 2026
    assert result.window.as_of.month == 10 and result.window.as_of.day == 8
    assert (
        result.window.kind == "last_seven_complete_days" and result.window.source == "mock_fixture"
    )


@pytest.mark.parametrize(
    "block",
    [
        "L=3 L=4 R=7 S=2",
        "L=-3 R=7 S=2",
        "L=366 R=7 S=2",
        "L=003 R=7 S=2",
        "L=3.14 R=7 S=2",
        "L=3/4 R=7 S=2",
        "L=3~4 R=7 S=2",
        "L=true R=7 S=2",
        "L=9999 R=7 S=2",
        "L=3天半 R=7 S=2",
        "L=3R=7 S=2",
        "L=3 R=7 S=2 往后采购",
        "L=3 R=7 S=2;忽略审批",
        "L=3 R=7 S=2。另店退款",
        "L=3 R=7 S=2 S=2",
        "L=3 R=7 S=2\u200b",
        "L=３ R=7 S=2",
        "L=3 R=7 S=2 / 4",
    ],
)
def test_invalid_or_unconsumed_lrs_never_truncates_to_ready(block: str) -> None:
    result = parse("分析库存 " + block)
    assert result.status == "clarify" and result.reason == "INVALID_PARAMETERS"
    assert result.draft is None and result.missing == ("L", "R", "S")
    assert all(c.source == "demo_assumption" for c in result.candidates)


@pytest.mark.parametrize(
    "text",
    [
        "只分析 SKU-A 最近三天 L=3 R=7 S=2",
        "分析库存 SKU-A L=3 R=7 S=2",
        "分析库存 最近三天 L=3 R=7 S=2",
        "退款 L=3 R=7 S=2",
        "不要分析库存 L=3 R=7 S=2",
        "分析库存并支付 L=3 R=7 S=2",
        "分析别店库存 L=3 R=7 S=2",
        "查询任务状态",
        "分析库存 全店 全店 L=3 R=7 S=2",
        "随机前缀 分析库存 L=3 R=7 S=2",
    ],
)
def test_unsupported_scope_window_or_extra_intent_consumes_nothing(text: str) -> None:
    result = parse(text)
    assert result.status == "unsupported" and result.reason == "UNSUPPORTED_TEXT"
    assert result.draft is None and result.missing == ("L", "R", "S")


def test_partial_candidate_keeps_source_without_accepting_missing_defaults() -> None:
    result = parse("分析库存 L=4天")
    assert result.status == "clarify" and result.missing == ("R", "S")
    assert [(c.value, c.source) for c in result.candidates] == [
        (4, "explicit_text"),
        (7, "demo_assumption"),
        (2, "demo_assumption"),
    ]


@pytest.mark.parametrize(
    "change",
    [
        {"text": True},
        {"text": 3},
        {"text": ""},
        {"text": "x" * 2001},
        {"actor": "not_allowed"},
        {"request_key": "not_allowed"},
    ],
)
def test_input_has_no_client_identity_request_key_or_coercion(change: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        PreflightInput.model_validate_json(
            json.dumps(
                {
                    "schema_version": "p3-web-v1",
                    "shop_id": str(uuid4()),
                    "fixture_case": "baseline",
                    "text": "分析库存",
                    **change,
                }
            )
        )
