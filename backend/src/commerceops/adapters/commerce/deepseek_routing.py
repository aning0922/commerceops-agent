"""固定DeepSeek structured候选，复用已审Chat边界；deterministic guard独立裁决。"""

from dataclasses import replace

from pydantic import ValidationError

from commerceops.application.commerce.intent_task import ROUTE_PROMPT_VERSION, routing_messages
from commerceops.application.commerce.inventory_routing import ModelRoute, ParameterCandidate
from commerceops.application.model_explanation.contracts import ExplanationProvider, ModelReply
from commerceops.application.model_explanation.service import strict_json


class DeepSeekRoutingPort:
    def __init__(self, provider: ExplanationProvider | None, input_hash: str):
        self.provider, self.input_hash = provider, input_hash
        self.reply = ModelReply(error_code="NO_PROVIDER", prompt_version=ROUTE_PROMPT_VERSION)

    async def route(self, text: str) -> ModelRoute:
        if self.provider is None:
            return ModelRoute(intent="clarify", evidence_mode="not_used")
        reply = await self.provider.complete(routing_messages(text), facts_hash=self.input_hash)
        self.reply = replace(reply, content=None)
        if reply.error_code is not None or reply.content is None:
            return ModelRoute(intent="clarify", evidence_mode=reply.evidence_mode)
        try:
            raw = strict_json(reply.content)
            if not isinstance(raw, dict) or set(raw) != {"intent", "candidates"}:
                raise ValueError("ROUTE_SCHEMA_INVALID")
            rows = raw["candidates"]
            if not isinstance(rows, list) or len(rows) > 3:
                raise ValueError("ROUTE_SCHEMA_INVALID")
            candidates = tuple(ParameterCandidate.model_validate(row) for row in rows)
            return ModelRoute.model_validate(
                {
                    "intent": raw["intent"],
                    "candidates": candidates,
                    "evidence_mode": reply.evidence_mode,
                }
            )
        except (ValueError, TypeError, KeyError, RecursionError, ValidationError):
            self.reply = replace(self.reply, error_code="UNSAFE_EXPLANATION")
            return ModelRoute(intent="clarify", evidence_mode=reply.evidence_mode)
