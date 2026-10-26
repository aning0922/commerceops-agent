"""N01 闭合 Web 草稿 DTO；没有业务写入、请求键或授权 capability。"""

import re
from datetime import datetime
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from commerceops.application.commerce.inventory_routing import _explicit_lrs_spans
from commerceops.application.replenishment.contracts import Input, Parameters, WooCreateParameters

Name = Literal["L", "R", "S"]
DEFAULT_PARAMETERS: tuple[tuple[Name, int], ...] = (("L", 3), ("R", 7), ("S", 2))


class Closed(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)


class PreflightInput(Input):
    shop_id: UUID
    fixture_case: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=2000)


class WooPreflightInput(Input):
    source_mode: Literal["woocommerce_test"]
    shop_id: UUID
    source_config_version: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1, max_length=2000)


PreflightRequest = PreflightInput | WooPreflightInput


class Candidate(Closed):
    name: Name
    value: int = Field(ge=0, le=365)
    source: Literal["explicit_text", "demo_assumption"]
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def span(self) -> "Candidate":
        if self.source == "explicit_text":
            if self.start is None or self.end is None or self.end <= self.start:
                raise ValueError("INVALID_PREFLIGHT_SPAN")
        elif self.start is not None or self.end is not None:
            raise ValueError("INVALID_PREFLIGHT_SPAN")
        return self


class Source(Closed):
    source_mode: Literal["mock"] = "mock"
    dataset_version: Literal["inventory-v1"] = "inventory-v1"
    fixture_case: str
    evidence_mode: Literal["not_used"] = "not_used"


class Window(Closed):
    kind: Literal["last_seven_complete_days"] = "last_seven_complete_days"
    start: datetime
    end: datetime
    timezone: str
    as_of: datetime
    source: Literal["mock_fixture"] = "mock_fixture"


class Scope(Closed):
    kind: Literal["all_fixture_products"] = "all_fixture_products"
    shop_id: UUID
    source: Literal["selected_shop"] = "selected_shop"


class PreflightResult(Closed):
    schema_version: Literal["p4-n01-web-v1"] = "p4-n01-web-v1"
    status: Literal["ready", "clarify", "unsupported"]
    reason: Literal[
        "EXPLICIT_PARAMETERS", "MISSING_PARAMETERS", "INVALID_PARAMETERS", "UNSUPPORTED_TEXT"
    ]
    shop_id: UUID
    source: Source
    window: Window
    scope: Scope
    candidates: tuple[Candidate, ...] = Field(min_length=3, max_length=3)
    missing: tuple[Name, ...]
    draft: Parameters | None
    requires_confirmation: Literal[True] = True
    execution_available: Literal[False] = False

    @model_validator(mode="after")
    def closed_draft(self) -> "PreflightResult":
        if tuple(c.name for c in self.candidates) != ("L", "R", "S"):
            raise ValueError("INVALID_PREFLIGHT_CANDIDATES")
        if (self.status == "ready") != (self.draft is not None) or (
            self.status == "ready" and (self.missing or self.reason != "EXPLICIT_PARAMETERS")
        ):
            raise ValueError("INVALID_PREFLIGHT_DRAFT")
        return self


class WooSource(Closed):
    source_mode: Literal["woocommerce_test"] = "woocommerce_test"
    source_config_version: str = Field(min_length=1, max_length=256)
    evidence_mode: Literal["not_used"] = "not_used"


class WooWindow(Closed):
    kind: Literal["last_seven_complete_days"] = "last_seven_complete_days"
    start: datetime
    end: datetime
    timezone: str
    as_of: datetime
    source: Literal["commerce_configuration"] = "commerce_configuration"


class WooScope(Closed):
    kind: Literal["all_shop_products"] = "all_shop_products"
    shop_id: UUID
    source: Literal["selected_shop"] = "selected_shop"


class WooPreflightResult(Closed):
    schema_version: Literal["p5-n01-web-v1"] = "p5-n01-web-v1"
    status: Literal["ready", "clarify", "unsupported"]
    reason: Literal[
        "EXPLICIT_PARAMETERS", "MISSING_PARAMETERS", "INVALID_PARAMETERS", "UNSUPPORTED_TEXT"
    ]
    shop_id: UUID
    source: WooSource
    window: WooWindow
    scope: WooScope
    candidates: tuple[Candidate, ...] = Field(min_length=3, max_length=3)
    missing: tuple[Name, ...]
    draft: WooCreateParameters | None
    requires_confirmation: Literal[True] = True
    execution_available: Literal[False] = False

    @model_validator(mode="after")
    def closed_draft(self) -> "WooPreflightResult":
        if tuple(c.name for c in self.candidates) != ("L", "R", "S"):
            raise ValueError("INVALID_PREFLIGHT_CANDIDATES")
        if (self.status == "ready") != (self.draft is not None) or (
            self.status == "ready" and (self.missing or self.reason != "EXPLICIT_PARAMETERS")
        ):
            raise ValueError("INVALID_PREFLIGHT_DRAFT")
        return self


SUPPORTED_INTENTS = (
    "分析最近七天的商品销量和库存情况，找出可能缺货的商品，生成补货建议",
    "分析最近七天的销量和库存，找出缺货风险并生成补货建议",
    "分析库存并生成补货建议",
    "查看库存并生成补货建议",
    "分析库存",
    "查看库存",
    "生成补货建议",
    "库存补货",
)


def supported_header(header: str) -> bool:
    """只消费明确支持句式及有限窗口/范围；未知前缀不成为授权意图。"""
    header = header.strip().rstrip("。，,：:!！?？").rstrip()
    prefix = r"(?:请|帮我)?(?:" + "|".join(re.escape(s) for s in SUPPORTED_INTENTS) + r")"
    found = re.match(prefix + r"(?=$|\s|[，,：:])", header)
    if found is None:
        return False
    tail = header[found.end() :]
    seen: set[str] = set()
    while tail:
        separator = re.match(r"[\s，,：:]+", tail)
        if separator is None:
            return False
        tail = tail[separator.end() :]
        if not tail:
            return True
        token = re.match(
            r"(最近七个完整自然日|最近7个完整自然日|全店|全部SKU)(?=$|\s|[，,：:])", tail
        )
        if token is None:
            return False
        kind = "window" if token[1].startswith("最近") else "scope"
        if kind in seen:
            return False
        seen.add(kind)
        tail = tail[token.end() :]
    return True


def _parse_text(
    text: str,
) -> tuple[
    Literal["ready", "clarify", "unsupported"],
    Literal["EXPLICIT_PARAMETERS", "MISSING_PARAMETERS", "INVALID_PARAMETERS", "UNSUPPORTED_TEXT"],
    tuple[Candidate, ...],
    tuple[Name, ...],
]:
    """复用原 P2 全消费 LRS 文法，结果只能供本地结构化确认。"""
    first = re.search(r"(?<![A-Za-z0-9_])([LRS])(?:=|:)", text)
    header = text if first is None else text[: first.start()]
    status: Literal["ready", "clarify", "unsupported"] = "clarify"
    reason: Literal[
        "EXPLICIT_PARAMETERS", "MISSING_PARAMETERS", "INVALID_PARAMETERS", "UNSUPPORTED_TEXT"
    ] = "MISSING_PARAMETERS"
    candidates: dict[str, Candidate] = {
        name: Candidate(name=name, value=value, source="demo_assumption")
        for name, value in DEFAULT_PARAMETERS
    }
    if not supported_header(header):
        status, reason = "unsupported", "UNSUPPORTED_TEXT"
    else:
        try:
            spans = _explicit_lrs_spans(text)
            for name, start, end, scalar in spans:
                if str(int(scalar)) != scalar:
                    raise ValueError("INVALID_PARAMETERS")
                candidates[name] = Candidate(
                    name=cast(Name, name),
                    value=int(scalar),
                    source="explicit_text",
                    start=start,
                    end=end,
                )
            if len(spans) == 3:
                status, reason = "ready", "EXPLICIT_PARAMETERS"
        except ValueError:
            reason = "INVALID_PARAMETERS"
            candidates = {
                name: Candidate(name=name, value=value, source="demo_assumption")
                for name, value in DEFAULT_PARAMETERS
            }
    ordered = tuple(candidates[name] for name in ("L", "R", "S"))
    missing = tuple(c.name for c in ordered if c.source == "demo_assumption")
    return status, reason, ordered, missing


def parse_preflight(request: PreflightInput, window: Window) -> PreflightResult:
    status, reason, ordered, missing = _parse_text(request.text)
    return PreflightResult(
        status=status,
        reason=reason,
        shop_id=request.shop_id,
        source=Source(fixture_case=request.fixture_case),
        window=window,
        scope=Scope(shop_id=request.shop_id),
        candidates=ordered,
        missing=missing,
        draft=Parameters(
            source_mode="mock",
            dataset_version="inventory-v1",
            fixture_case=request.fixture_case,
            **{c.name: c.value for c in ordered},
        )
        if status == "ready"
        else None,
    )


def parse_woo_preflight(request: WooPreflightInput, window: WooWindow) -> WooPreflightResult:
    status, reason, ordered, missing = _parse_text(request.text)
    return WooPreflightResult(
        status=status,
        reason=reason,
        shop_id=request.shop_id,
        source=WooSource(source_config_version=request.source_config_version),
        window=window,
        scope=WooScope(shop_id=request.shop_id),
        candidates=ordered,
        missing=missing,
        draft=WooCreateParameters(
            source_mode="woocommerce_test",
            source_config_version=request.source_config_version,
            **{c.name: c.value for c in ordered},
        )
        if status == "ready"
        else None,
    )
