"""Single inquiry loop with fixed read names and fail-closed total budgets."""

import asyncio
import hashlib
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from functools import partial
from time import monotonic
from typing import TypeVar

from commerceops.application.commerce.readonly_inquiry_contracts import (
    Calls,
    ChoicePort,
    Claim,
    Context,
    Final,
    IdentityPort,
    InventoryCall,
    OrdersCall,
    ProductMatch,
    ProductsCall,
    ReadPort,
    ReadResult,
    ReportsCall,
    ToolCall,
    Window,
    parse_choice,
)

T = TypeVar("T")
NAMES = frozenset(
    {"commerce.read_products", "commerce.read_orders", "commerce.read_inventory", "reports.read"}
)


@dataclass(frozen=True)
class Tool:
    effect: str
    port: ReadPort


@dataclass(frozen=True)
class Trace:
    tool_call_id: str
    name: str
    args_hash: str


@dataclass(frozen=True)
class Outcome:
    status: str
    model_calls: int
    tool_calls: int
    scanned_rows: int
    traces: tuple[Trace, ...]
    results: tuple[ReadResult, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    claims: tuple[Claim, ...] = ()
    clarification_options: tuple[ProductMatch, ...] = ()
    evidence_mode: str = "offline_stub"
    workflow_version: str = "p6-readonly-inquiry-v1"


class Stop(ValueError):
    pass


async def execute(
    context: Context,
    chooser: ChoicePort,
    identity: IdentityPort,
    registry: Mapping[str, Tool],
    *,
    clock: Callable[[], float] = monotonic,
) -> Outcome:
    registry = dict(registry)
    deadline = clock() + 60
    models = tools = rows = 0
    traces: list[Trace] = []
    results: list[ReadResult] = []
    ids: set[str] = set()
    skus: set[str] = set()
    windows: list[Window] = []
    executed: list[ToolCall] = []

    async def bounded(operation: Callable[[], Awaitable[T]]) -> T:
        remaining = deadline - clock()
        if remaining <= 0:
            raise Stop("timeout")
        async with asyncio.timeout(remaining):
            value = await operation()
        if clock() >= deadline:
            raise Stop("timeout")
        return value

    async def authorize(call: ToolCall | None = None) -> None:
        # Invocation-specific object access is part of this injected authority port.
        if not await bounded(lambda: identity.authorize(context, call)):
            raise Stop("access_denied")

    def bounds(new_skus: tuple[str, ...], new_windows: tuple[Window, ...]) -> None:
        skus.update(new_skus)
        windows.extend(new_windows)
        if len(skus) > 100:
            raise Stop("budget_exceeded")
        if windows and max(w.end for w in windows) - min(w.start for w in windows) > timedelta(
            days=30
        ):
            raise Stop("budget_exceeded")

    def outcome(
        status: str,
        final: Final | None = None,
        options: tuple[ProductMatch, ...] = (),
    ) -> Outcome:
        return Outcome(
            status,
            models,
            tools,
            rows,
            tuple(traces),
            tuple(results) if final is not None else (),
            final.evidence_refs if final is not None else (),
            final.claims if final is not None else (),
            options,
        )

    try:
        # Revalidate even model_construct/copy supplied context.
        context = Context.model_validate_json(context.model_dump_json())
        for _ in range(3):
            await authorize()
            for old_call in executed:
                await authorize(old_call)
            models += 1
            choice = parse_choice(await bounded(lambda: chooser.choose(context, tuple(results))))
            if isinstance(choice, Final):
                await authorize()
                # Recheck every object whose evidence could be disclosed, not just login.
                for old_call in executed:
                    await authorize(old_call)
                known = {fact.evidence_id: fact for result in results for fact in result.facts}
                if len(set(choice.evidence_refs)) != len(choice.evidence_refs):
                    raise Stop("invalid_response")
                if not set(choice.evidence_refs) <= known.keys():
                    raise Stop("insufficient_evidence")
                if {ref for claim in choice.claims for ref in claim.refs} != set(
                    choice.evidence_refs
                ):
                    raise Stop("invalid_response")
                for claim in choice.claims:
                    if claim.kind == "compare":
                        first, second = (known[ref] for ref in claim.refs)
                        if (
                            first.window is None
                            or second.window is None
                            or first.metric != second.metric
                            or first.sku_key != second.sku_key
                            or first.currency != second.currency
                            or first.unit != second.unit
                            or first.window == second.window
                            or min(first.window.end, second.window.end)
                            > max(first.window.start, second.window.start)
                        ):
                            raise Stop("invalid_response")
                if choice.intent != "readonly_inquiry":
                    return outcome(choice.intent)
                if not choice.evidence_refs:
                    raise Stop("insufficient_evidence")
                return outcome("complete", choice)
            if not isinstance(choice, Calls):
                raise Stop("invalid_response")
            if models == 3 or tools + len(choice.calls) > 4:
                raise Stop("budget_exceeded")
            proposed_ids = [call.tool_call_id for call in choice.calls]
            if len(set(proposed_ids)) != len(proposed_ids) or ids.intersection(proposed_ids):
                raise Stop("invalid_response")
            # Validate entire proposed batch before the first read.
            for call in choice.calls:
                spec = registry.get(call.name)
                if call.name not in NAMES or spec is None or spec.effect != "read":
                    raise Stop("tool_denied")
                if isinstance(call, OrdersCall):
                    bounds(call.args.skus, call.args.windows)
                elif isinstance(call, InventoryCall):
                    bounds(call.args.skus, ())
            for call in choice.calls:
                if isinstance(call, OrdersCall) and rows >= 10_000:
                    raise Stop("budget_exceeded")
                await authorize(call)
                ids.add(call.tool_call_id)
                tools += 1
                traces.append(
                    Trace(
                        call.tool_call_id,
                        call.name,
                        hashlib.sha256(call.args.model_dump_json().encode()).hexdigest(),
                    )
                )
                result = await bounded(
                    partial(registry[call.name].port.read, context, call, deadline, 10_000 - rows)
                )
                result = ReadResult.model_validate_json(result.model_dump_json())
                if (
                    result.shop_id != context.shop_id
                    or result.source_binding != context.source_binding
                    or result.tool_call_id != call.tool_call_id
                ):
                    raise Stop("invalid_response")
                if isinstance(call, (InventoryCall, OrdersCall)) and not set(
                    result.sku_keys
                ) <= set(call.args.skus):
                    raise Stop("invalid_response")
                if isinstance(call, OrdersCall) and result.windows != call.args.windows:
                    raise Stop("invalid_response")
                if isinstance(call, ReportsCall) and result.report_id != call.args.report_id:
                    raise Stop("invalid_response")
                rows += result.scanned_rows
                bounds(result.sku_keys, result.windows)
                if rows > 10_000:
                    raise Stop("budget_exceeded")
                if not result.complete:
                    raise Stop("source_incomplete")
                if isinstance(call, ProductsCall):
                    if len(result.products) > 1:
                        await authorize(call)
                        return outcome("clarify", options=result.products)
                    if not result.products:
                        raise Stop("insufficient_evidence")
                previous = {f.evidence_id for r in results for f in r.facts}
                incoming = [f.evidence_id for f in result.facts]
                if len(set(incoming)) != len(incoming) or previous.intersection(incoming):
                    raise Stop("invalid_response")
                # A revoked result never reaches the model's next turn.
                await authorize(call)
                results.append(result)
                executed.append(call)
        raise Stop("budget_exceeded")
    except Stop as exc:
        return outcome(str(exc))
    except TimeoutError:
        return outcome("timeout")
    except Exception:
        return outcome("invalid_response")
