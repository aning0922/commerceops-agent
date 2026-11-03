"""Readable offline goldens: model scripts inspect actual previous safe results."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from commerceops.application.commerce.readonly_inquiry_contracts import (
    Context,
    InventoryCall,
    OrdersCall,
    ReadResult,
    ReportsCall,
    ToolCall,
    parse_choice,
)
from commerceops.application.commerce.readonly_inquiry_executor import NAMES, Outcome, Tool, execute

pytestmark = pytest.mark.offline


def ctx() -> Context:
    return Context(
        request_id="q",
        principal_id="p",
        organization_id="o",
        shop_id="s",
        identity_id="i",
        auth_version=1,
        source_binding="mock-v1",
        question="库存查询",
    )


def calls(name: str, args: dict[str, object], key: str = "c1") -> str:
    return json.dumps(
        {
            "kind": "call_tools",
            "intent": "readonly_inquiry",
            "calls": [{"tool_call_id": key, "name": name, "args": args}],
        }
    )


def final(refs: tuple[str, ...] = ("f1",)) -> str:
    return json.dumps(
        {
            "kind": "final",
            "intent": "readonly_inquiry",
            "evidence_refs": refs,
            "claims": [{"kind": "fact", "refs": [ref]} for ref in refs],
        }
    )


class Identity:
    allowed = True

    async def authorize(self, context: Context, call: ToolCall | None) -> bool:
        return self.allowed


class Reader:
    def __init__(self, sku: str = "A") -> None:
        self.sku = sku
        self.calls: list[ToolCall] = []
        self.rows = 1
        self.complete = True
        self.identity: Identity | None = None
        self.source = "mock-v1"
        self.remaining: list[int] = []

    async def read(
        self, context: Context, call: ToolCall, deadline: float, rows_remaining: int
    ) -> ReadResult:
        self.calls.append(call)
        self.remaining.append(rows_remaining)
        if self.identity:
            self.identity.allowed = False
        return ReadResult.model_validate_json(
            json.dumps(
                {
                    "tool_call_id": call.tool_call_id,
                    "shop_id": "s",
                    "source_binding": self.source,
                    "snapshot_id": f"snap{len(self.calls)}",
                    "report_id": call.args.report_id if isinstance(call, ReportsCall) else None,
                    "windows": [json.loads(w.model_dump_json()) for w in call.args.windows]
                    if isinstance(call, OrdersCall)
                    else [],
                    "as_of": "2026-11-03T01:00:00Z",
                    "complete": self.complete,
                    "scanned_rows": self.rows,
                    "sku_keys": [self.sku],
                    "products": [{"sku_key": self.sku}] if call.name.endswith("products") else [],
                    "facts": [
                        {
                            "evidence_id": f"f{len(self.calls)}",
                            "metric": "available_stock",
                            "sku_key": self.sku,
                            "as_of": "2026-11-03T01:00:00Z",
                            "value": "12",
                            "unit": "件",
                            "currency": None,
                        }
                    ],
                }
            )
        )


class Script:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.seen: list[tuple[ReadResult, ...]] = []

    async def choose(self, context: Context, results: tuple[ReadResult, ...]) -> str:
        self.seen.append(results)
        return self.responses[len(self.seen) - 1]


def run(
    script: Script, reader: Reader, identity: Identity | None = None, effect: str = "read"
) -> Outcome:
    return asyncio.run(
        execute(
            ctx(), script, identity or Identity(), {name: Tool(effect, reader) for name in NAMES}
        )
    )


@pytest.mark.parametrize("sku", ["A", "B"])
def test_dynamic_resolution_changes_next_model_arguments(sku: str) -> None:
    class Dynamic(Script):
        async def choose(self, context: Context, results: tuple[ReadResult, ...]) -> str:
            self.seen.append(results)
            if not results:
                return calls("commerce.read_products", {"query": "杯子"})
            if len(results) == 1:
                resolved = results[0].products[0].sku_key
                return calls("commerce.read_inventory", {"skus": [resolved]}, "c2")
            return final(("f2",))

    reader = Reader(sku)
    result = run(Dynamic([]), reader)
    assert result.status == "complete"
    assert isinstance(reader.calls[1], InventoryCall)
    assert reader.calls[1].args.skus == (sku,)
    assert result.model_calls == 3 and result.tool_calls == 2
    assert result.evidence_mode == "offline_stub"


def test_known_sku_only_calls_inventory_and_keeps_time() -> None:
    reader = Reader()
    result = run(Script([calls("commerce.read_inventory", {"skus": ["A"]}), final()]), reader)
    assert result.status == "complete" and result.tool_calls == 1
    assert result.results[0].as_of == datetime(2026, 11, 3, 1, tzinfo=UTC)
    assert result.results[0].facts[0].value == "12"  # Independent stock golden, not model prose.


@pytest.mark.parametrize(
    "raw",
    [
        calls("approval.prepare", {}),
        calls("reports.read", {"report_id": "r", "sql": "select"}),
        '{"kind":"final","kind":"call_tools"}',
        '{"kind":"final","intent":"readonly_inquiry","evidence_refs":[],"calls":[]}',
        calls("commerce.read_inventory", {"skus": [True]}),
    ],
)
def test_invalid_choice_never_reaches_io(raw: str) -> None:
    reader = Reader()
    result = run(Script([raw]), reader)
    assert result.status != "complete" and reader.calls == []
    with pytest.raises(ValueError):
        parse_choice(raw)


def test_effect_denied_before_read() -> None:
    reader = Reader()
    result = run(
        Script([calls("commerce.read_inventory", {"skus": ["A"]})]), reader, effect="internal_write"
    )
    assert result.status == "tool_denied" and not reader.calls


@pytest.mark.parametrize("case", ["partial", "rows", "source", "revoked"])
def test_unsafe_read_never_reaches_next_model_or_disclosure(case: str) -> None:
    reader, identity = Reader(), Identity()
    if case == "partial":
        reader.complete = False
    elif case == "rows":
        reader.rows = 10001
    elif case == "source":
        reader.source = "other"
    else:
        reader.identity = identity
    script = Script([calls("commerce.read_inventory", {"skus": ["A"]}), final()])
    result = run(script, reader, identity)
    assert result.status != "complete" and not result.results
    assert len(script.seen) == 1


def test_third_model_tool_proposal_is_not_executed() -> None:
    reader = Reader()
    result = run(
        Script([calls("commerce.read_inventory", {"skus": ["A"]}, f"c{i}") for i in range(3)]),
        reader,
    )
    assert result.status == "budget_exceeded" and len(reader.calls) == 2
    assert result.model_calls == 3


def test_duplicate_call_id_not_executed_twice() -> None:
    reader = Reader()
    proposal = calls("commerce.read_inventory", {"skus": ["A"]})
    result = run(Script([proposal, proposal]), reader)
    assert result.status == "invalid_response" and len(reader.calls) == 1


def test_scanned_rows_are_cumulative_even_when_only_one_sku_returns() -> None:
    reader = Reader()
    reader.rows = 6000
    result = run(
        Script([calls("commerce.read_inventory", {"skus": ["A"]}, f"c{i}") for i in range(2)]),
        reader,
    )
    assert result.status == "budget_exceeded" and result.scanned_rows == 12000
    assert reader.remaining == [10000, 4000]
    assert not result.results


def test_windows_cannot_bypass_inquiry_span() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)

    def order(offset: int, key: str) -> str:
        return calls(
            "commerce.read_orders",
            {
                "skus": ["A"],
                "windows": [
                    {
                        "start": (start + timedelta(days=offset)).isoformat(),
                        "end": (start + timedelta(days=offset + 1)).isoformat(),
                    }
                ],
            },
            key,
        )

    reader = Reader()
    result = run(Script([order(0, "c1"), order(31, "c2")]), reader)
    assert result.status == "budget_exceeded" and len(reader.calls) == 1


def test_unique_sku_limit_spans_tools() -> None:
    reader = Reader("0")
    result = run(
        Script(
            [
                calls("commerce.read_inventory", {"skus": [str(i) for i in range(100)]}),
                calls("commerce.read_inventory", {"skus": ["new"]}, "c2"),
            ]
        ),
        reader,
    )
    assert result.status == "budget_exceeded" and len(reader.calls) == 1


def test_clock_expiry_after_await_discards_late_result() -> None:
    now = [0.0]

    class Late(Script):
        async def choose(self, context: Context, results: tuple[ReadResult, ...]) -> str:
            now[0] = 61
            return final()

    result = asyncio.run(execute(ctx(), Late([]), Identity(), {}, clock=lambda: now[0]))
    assert result.status == "timeout" and not result.results


def test_revoke_during_final_model_prevents_disclosure() -> None:
    identity = Identity()

    class Revoke(Script):
        async def choose(self, context: Context, results: tuple[ReadResult, ...]) -> str:
            if results:
                identity.allowed = False
                return final()
            return calls("commerce.read_inventory", {"skus": ["A"]})

    result = run(Revoke([]), Reader(), identity)
    assert result.status == "access_denied" and not result.results


def test_fabricated_citation_is_rejected() -> None:
    result = run(
        Script([calls("commerce.read_inventory", {"skus": ["A"]}), final(("made-up",))]), Reader()
    )
    assert result.status == "insufficient_evidence" and not result.results


def test_tool_limit_checks_whole_batch_before_any_read() -> None:
    proposal = json.loads(calls("commerce.read_inventory", {"skus": ["A"]}))
    first = proposal["calls"][0]
    proposal["calls"] = [{**first, "tool_call_id": f"c{i}"} for i in range(3)]
    second = {**proposal, "calls": [{**first, "tool_call_id": f"c{i}"} for i in range(3, 5)]}
    reader = Reader()
    result = run(Script([json.dumps(proposal), json.dumps(second)]), reader)
    assert result.status == "budget_exceeded" and len(reader.calls) == 3


def test_four_tools_serially_then_final_is_allowed() -> None:
    proposal = json.loads(calls("commerce.read_inventory", {"skus": ["A"]}))
    first = proposal["calls"][0]
    proposal["calls"] = [{**first, "tool_call_id": f"c{i}"} for i in range(4)]
    reader = Reader()
    result = run(Script([json.dumps(proposal), final(("f4",))]), reader)
    assert result.status == "complete" and len(reader.calls) == 4
    assert result.model_calls == 2


def test_object_revoked_before_next_model_does_not_disclose_previous_result() -> None:
    class ObjectIdentity(Identity):
        checks = 0

        async def authorize(self, context: Context, call: ToolCall | None) -> bool:
            if call is not None:
                self.checks += 1
                return self.checks <= 2
            return True

    script = Script([calls("reports.read", {"report_id": "r"}), final()])
    result = run(script, Reader(), ObjectIdentity())
    assert result.status == "access_denied" and not result.results
    assert len(script.seen) == 1


def test_distinct_observation_times_and_unknown_value_remain_explicit() -> None:
    class Observations(Reader):
        async def read(
            self, context: Context, call: ToolCall, deadline: float, rows_remaining: int
        ) -> ReadResult:
            result = await super().read(context, call, deadline, rows_remaining)
            data = json.loads(result.model_dump_json())
            if len(self.calls) == 2:
                data["as_of"] = "2026-11-03T02:00:00Z"
                data["facts"][0]["value"] = None
            return ReadResult.model_validate_json(json.dumps(data))

    script = Script(
        [
            calls("commerce.read_inventory", {"skus": ["A"]}, "c1"),
            calls("commerce.read_inventory", {"skus": ["A"]}, "c2"),
            final(("f1", "f2")),
        ]
    )
    result = run(script, Observations())
    assert result.status == "complete"
    assert result.results[0].as_of != result.results[1].as_of
    assert result.results[1].facts[0].value is None


@pytest.mark.parametrize("where", ["identity", "read"])
def test_deadline_covers_identity_and_read_await(where: str) -> None:
    now = [0.0]

    class TimedIdentity(Identity):
        async def authorize(self, context: Context, call: ToolCall | None) -> bool:
            if where == "identity":
                now[0] = 60.0
            return True

    class TimedReader(Reader):
        async def read(
            self, context: Context, call: ToolCall, deadline: float, rows_remaining: int
        ) -> ReadResult:
            result = await super().read(context, call, deadline, rows_remaining)
            now[0] = 60.0
            return result

    script = Script([calls("commerce.read_inventory", {"skus": ["A"]})])
    result = asyncio.run(
        execute(
            ctx(),
            script,
            TimedIdentity(),
            {n: Tool("read", TimedReader()) for n in NAMES},
            clock=lambda: now[0],
        )
    )
    assert result.status == "timeout" and not result.results


def test_read_result_outside_requested_sku_is_rejected() -> None:
    reader = Reader("other")
    result = run(Script([calls("commerce.read_inventory", {"skus": ["A"]}), final()]), reader)
    assert result.status == "invalid_response" and not result.results


def test_read_result_report_binding_is_checked() -> None:
    class WrongReport(Reader):
        async def read(
            self, context: Context, call: ToolCall, deadline: float, rows_remaining: int
        ) -> ReadResult:
            result = await super().read(context, call, deadline, rows_remaining)
            data = json.loads(result.model_dump_json())
            data["report_id"] = "another-report"
            return ReadResult.model_validate_json(json.dumps(data))

    result = run(Script([calls("reports.read", {"report_id": "r"}), final()]), WrongReport())
    assert result.status == "invalid_response" and not result.results


def test_named_product_two_period_sales_and_inventory_golden() -> None:
    class Sales(Reader):
        async def read(
            self, context: Context, call: ToolCall, deadline: float, rows_remaining: int
        ) -> ReadResult:
            result = await super().read(context, call, deadline, rows_remaining)
            if isinstance(call, OrdersCall):
                data = json.loads(result.model_dump_json())
                # Fixed external gold: selected periods have 3 + 5 units, not model arithmetic.
                base = data["facts"][0]
                data["facts"] = [
                    {
                        **base,
                        "evidence_id": f"f2-{index}",
                        "metric": "sold_units",
                        "window": json.loads(window.model_dump_json()),
                        "currency": "CNY",
                        "value": value,
                    }
                    for index, (window, value) in enumerate(
                        zip(call.args.windows, ("3", "5"), strict=True)
                    )
                ]
                data["scanned_rows"] = 2
                return ReadResult.model_validate_json(json.dumps(data))
            return result

    class SalesChoice(Script):
        async def choose(self, context: Context, results: tuple[ReadResult, ...]) -> str:
            if not results:
                return calls("commerce.read_products", {"query": "杯子"})
            if len(results) == 1:
                sku = results[0].products[0].sku_key
                order = json.loads(
                    calls(
                        "commerce.read_orders",
                        {
                            "skus": [sku],
                            "windows": [
                                {"start": "2026-10-20T00:00:00Z", "end": "2026-10-27T00:00:00Z"},
                                {"start": "2026-10-27T00:00:00Z", "end": "2026-11-03T00:00:00Z"},
                            ],
                        },
                        "c2",
                    )
                )
                inventory = json.loads(calls("commerce.read_inventory", {"skus": [sku]}, "c3"))
                order["calls"].extend(inventory["calls"])
                return json.dumps(order)
            return final(("f2-0", "f2-1", "f3"))

    reader = Sales()
    result = run(SalesChoice([]), reader)
    assert result.status == "complete" and result.model_calls == 3
    assert [call.name for call in reader.calls] == [
        "commerce.read_products",
        "commerce.read_orders",
        "commerce.read_inventory",
    ]
    assert [fact.value for fact in result.results[1].facts] == ["3", "5"]
    assert result.results[2].facts[0].value == "12"
    assert result.scanned_rows == 4
