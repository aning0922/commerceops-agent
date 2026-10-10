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
                explicit = list(
                    re.finditer(
                        r"(?<![A-Za-z0-9_])([LRS])(?:=|:)([0-9]+)(?![A-Za-z0-9_])", request.text
                    )
                )
                if len({m.group(1) for m in explicit}) != len(explicit):
                    raise ValueError("AMBIGUOUS_PARAMETERS")
                spans = {(m.group(1), m.start(2), m.end(2), m.group(2)) for m in explicit}
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
