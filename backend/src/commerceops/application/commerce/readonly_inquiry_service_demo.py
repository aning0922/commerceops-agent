"""Explicit finite local-demo choice port; never a real model or general NL parser."""

import json
from dataclasses import dataclass

from commerceops.adapters.commerce.mock import Fixture
from commerceops.application.commerce.readonly_inquiry_contracts import (
    Context,
    OrdersCall,
    ReadPort,
    ReadResult,
    ToolCall,
    Window,
)
from commerceops.domain.commerce_values import complete_days


def fixture_domain(fixture: Fixture) -> Window:
    start, end = complete_days(fixture.now, fixture.source.timezone)
    return Window(start=start, end=end)


@dataclass(frozen=True)
class DomainReadPort:
    port: ReadPort
    domain: Window

    async def read(
        self, context: Context, call: ToolCall, deadline: float, rows_remaining: int
    ) -> ReadResult:
        if isinstance(call, OrdersCall) and any(
            window.start < self.domain.start or window.end > self.domain.end
            for window in call.args.windows
        ):
            return ReadResult(
                tool_call_id=call.tool_call_id,
                shop_id=context.shop_id,
                source_binding=context.source_binding,
                snapshot_id="domain-unavailable",
                as_of=self.domain.end,
                complete=False,
                quality_flags=("SOURCE_DOMAIN_UNAVAILABLE",),
                scanned_rows=0,
                sku_keys=(),
                windows=call.args.windows,
            )
        return await self.port.read(context, call, deadline, rows_remaining)


class DemoChoice:
    """Supports only '库存 <exact name/SKU>' or '销量 <exact name/SKU>' in offline mode."""

    def __init__(self, domain: Window, report_id: str | None = None):
        self.domain, self.report_id = domain, report_id

    async def choose(self, context: Context, results: tuple[ReadResult, ...]) -> str:
        if context.question.strip() == "解释报告" and self.report_id is not None:
            if not results:
                return json.dumps(
                    {
                        "kind": "call_tools",
                        "intent": "readonly_inquiry",
                        "calls": [
                            {
                                "tool_call_id": "report",
                                "name": "reports.read",
                                "args": {"report_id": self.report_id},
                            }
                        ],
                    }
                )
            refs = [fact.evidence_id for result in results for fact in result.facts]
            return json.dumps(
                {
                    "kind": "final",
                    "intent": "readonly_inquiry",
                    "evidence_refs": refs,
                    "claims": [{"kind": "fact", "refs": [ref]} for ref in refs],
                }
            )
        prefix, separator, query = context.question.strip().partition(" ")
        if not separator or prefix not in ("库存", "销量") or not query.strip():
            return json.dumps(
                {"kind": "final", "intent": "clarify", "evidence_refs": [], "claims": []}
            )
        if not results:
            return json.dumps(
                {
                    "kind": "call_tools",
                    "intent": "readonly_inquiry",
                    "calls": [
                        {
                            "tool_call_id": "resolve",
                            "name": "commerce.read_products",
                            "args": {"query": query.strip()},
                        }
                    ],
                }
            )
        if len(results) == 1:
            if len(results[0].products) != 1:
                return json.dumps(
                    {"kind": "final", "intent": "clarify", "evidence_refs": [], "claims": []}
                )
            sku = results[0].products[0].sku_key
            args: dict[str, object] = {"skus": [sku]}
            if prefix == "销量":
                args["windows"] = [self.domain.model_dump(mode="json")]
            return json.dumps(
                {
                    "kind": "call_tools",
                    "intent": "readonly_inquiry",
                    "calls": [
                        {
                            "tool_call_id": "read",
                            "name": "commerce.read_inventory"
                            if prefix == "库存"
                            else "commerce.read_orders",
                            "args": args,
                        }
                    ],
                }
            )
        refs = [fact.evidence_id for result in results for fact in result.facts]
        return json.dumps(
            {
                "kind": "final",
                "intent": "readonly_inquiry",
                "evidence_refs": refs,
                "claims": [{"kind": "fact", "refs": [ref]} for ref in refs],
            }
        )
