"""BC02受限模型候选接口；guard负责参数来源，不用关键词匹配冒充LLM。"""

import asyncio
import re
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Intent = Literal[
    "inventory_replenishment", "task_status", "explain_report", "clarify", "unsupported"
]


class RoutingInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    text: str = Field(min_length=1, max_length=2000)
    context_task_id: UUID | None = None

    @field_validator("context_task_id", mode="before")
    @classmethod
    def context_uuid(cls, value: object) -> object:
        return UUID(value) if isinstance(value, str) else value


class ParameterCandidate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    name: Literal["L", "R", "S"]
    value: int = Field(ge=0, le=365)
    start: int = Field(ge=0)
    end: int = Field(ge=1)
    source: Literal["explicit_text"]


class ModelRoute(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    intent: Intent
    candidates: tuple[ParameterCandidate, ...] = ()
    evidence_mode: Literal["offline_stub", "actual_provider", "not_used"]


class RoutingPort(Protocol):
    async def route(self, text: str) -> ModelRoute: ...


class RoutingDecision(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal["p204-route-v1"] = "p204-route-v1"
    intent: Intent
    evidence_mode: Literal["offline_stub", "actual_provider", "not_used"]
    parameters: dict[str, int]
    parameter_sources: dict[str, str]
    safe_reason: str
    analysis_only: Literal[True] = True
    execution_available: Literal[False] = False


def _explicit_lrs_spans(text: str) -> set[tuple[str, int, int, str]]:
    """只消费有限LRS参数块；前置意图保留，块内未知字符必澄清。"""
    first = re.search(r"(?<![A-Za-z0-9_])([LRS])(?:=|:)", text)
    if first is None:
        return set()
    spans: set[tuple[str, int, int, str]] = set()
    seen: set[str] = set()
    cursor = first.start()

    def space_end(at: int) -> int:
        while at < len(text) and text[at].isspace():
            at += 1
        return at

    while cursor < len(text):
        field = re.match(r"([LRS])(?:=|:)([0-9]+)", text[cursor:])
        if field is None:
            raise ValueError("PARAMETER_BLOCK_NOT_CONSUMED")
        name, scalar = field.groups()
        if name in seen or len(scalar) > 3 or not 0 <= int(scalar) <= 365:
            raise ValueError("AMBIGUOUS_PARAMETERS")
        start, end = cursor + field.start(2), cursor + field.end(2)
        seen.add(name)
        spans.add((name, start, end, scalar))
        cursor = end
        unit_at = space_end(cursor)
        if unit_at < len(text) and text[unit_at] == "天":
            cursor = unit_at + 1
        following = space_end(cursor)
        if following == len(text):
            return spans
        # 只允许明确参数间隔、有限标点及句末；不接受任意未知续词。
        if text[following] in "。!！?？":
            while following < len(text) and text[following] in "。!！?？":
                following = space_end(following + 1)
            if following != len(text):
                raise ValueError("PARAMETER_BLOCK_NOT_CONSUMED")
            return spans
        if text[following] in ",，;；":
            following = space_end(following + 1)
            if following == len(text):
                return spans
        elif following == cursor:
            raise ValueError("PARAMETER_SEPARATOR_REQUIRED")
        # 下一次迭代必须是精确NAME+SEP+UINT，任何分数/范围/文字均不消费。
        cursor = following
    return spans


class GuardedRouter:
    def __init__(self, port: RoutingPort | None = None, *, allow_actual_routing: bool = False):
        self.port, self.allow_actual_routing = port, allow_actual_routing

    async def route(self, request: RoutingInput) -> RoutingDecision:
        from commerceops.application.commerce.inventory_analysis import _native_input_value

        request = RoutingInput.model_validate(_native_input_value(request))
        parameters = {"L": 3, "R": 7, "S": 2}
        sources = {k: "demo_assumption" for k in parameters}
        mode: Literal["offline_stub", "actual_provider", "not_used"] = "not_used"
        selected: Intent = "clarify"
        reason = "ROUTER_NOT_CONFIGURED"
        if self.port is not None:
            try:
                async with asyncio.timeout(20):
                    proposed = await self.port.route(request.text)
                # 保留原始bool等类型，拒model_construct/copy的候选越界。

                proposed = ModelRoute.model_validate(_native_input_value(proposed))
                if proposed.evidence_mode == "actual_provider" and not self.allow_actual_routing:
                    raise ValueError("REAL_ROUTING_NOT_ENABLED")
                mode = proposed.evidence_mode
                selected = proposed.intent
                reason = "VALIDATED_MODEL_PROPOSAL"
                spans = _explicit_lrs_spans(request.text)
                if proposed.intent == "inventory_replenishment" and spans != {
                    (c.name, c.start, c.end, str(c.value)) for c in proposed.candidates
                }:
                    raise ValueError("UNACKNOWLEDGED_PARAMETERS")
                seen: set[str] = set()
                for candidate in proposed.candidates:
                    if (
                        candidate.name in seen
                        or candidate.end > len(request.text)
                        or request.text[candidate.start : candidate.end] != str(candidate.value)
                        or request.text[max(0, candidate.start - 2) : candidate.start]
                        not in (candidate.name + "=", candidate.name + ":")
                    ):
                        raise ValueError("AMBIGUOUS_PARAMETERS")
                    seen.add(candidate.name)
                    parameters[candidate.name] = candidate.value
                    sources[candidate.name] = "explicit_text"
                if proposed.candidates and selected != "inventory_replenishment":
                    raise ValueError("PARAMETERS_OUT_OF_ROUTE")
                if (
                    selected in ("task_status", "explain_report")
                    and request.context_task_id is None
                ):
                    selected = "clarify"
                    reason = "TASK_SCOPE_REQUIRED"
            except Exception:
                selected = "clarify"
                parameters = {"L": 3, "R": 7, "S": 2}
                sources = {k: "demo_assumption" for k in parameters}
                reason = "UNSAFE_OR_AMBIGUOUS_PROPOSAL"
        return RoutingDecision(
            intent=selected,
            evidence_mode=mode,
            parameters=parameters,
            parameter_sources=sources,
            safe_reason=reason,
        )
