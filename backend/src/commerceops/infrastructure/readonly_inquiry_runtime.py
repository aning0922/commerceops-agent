"""Current PG authority and report reads for the explicitly offline inquiry runner."""

import asyncio
from collections.abc import Callable
from functools import partial
from typing import Any
from uuid import UUID

from commerceops.adapters.commerce.mock import MockCommerce
from commerceops.application.commerce.readonly_inquiry_contracts import (
    Context,
    Fact,
    ReadResult,
    ReportsCall,
    ToolCall,
    Window,
)
from commerceops.application.commerce.readonly_inquiry_service_demo import DomainReadPort
from commerceops.application.commerce.readonly_inquiry_tools import MockReadFacade, key
from commerceops.application.runner import RunRequest
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.inventory_repository import _stored
from commerceops.infrastructure.readonly_inquiry_store import InquiryStore
from commerceops.infrastructure.replenishment_repository import SOURCE_SQL
from commerceops.infrastructure.worker_lock import WorkerSession


async def db_call[T](function: Callable[..., T], *args: Any) -> T:
    """Cancellation joins the bounded DB transaction thread before the runner can stop."""
    task = asyncio.create_task(asyncio.to_thread(partial(function, *args)))
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError:
            cancelled = True
            if task.done():
                raise
        except Exception:
            if cancelled:
                raise asyncio.CancelledError from None
            raise
    if cancelled:
        raise asyncio.CancelledError
    return result


class InquiryAuthority:
    def __init__(self, store: InquiryStore, session: WorkerSession, run: RunRequest):
        self.store, self.session, self.run = store, session, run

    def check(self, context: Context, call: ToolCall | None) -> bool:
        with connect(self.store.settings) as db:
            row = self.store.run_row(db, self.run)
            fixture = self.store.inquiry.fixture()
            if (
                context.request_id != str(self.run.task_id)
                or context.organization_id != str(row["organization_id"])
                or context.principal_id != str(row["principal_id"])
                or context.identity_id != str(row["identity_id"])
                or context.auth_version != row["auth_version"]
                or context.shop_id != fixture.source.shop_id
                or context.source_binding != row["source_binding"]
            ):
                return False
            if isinstance(call, ReportsCall):
                self.store.report_task(
                    db, self.store.actor(row), row["shop_id"], UUID(call.args.report_id)
                )
            return True

    async def authorize(self, context: Context, call: ToolCall | None) -> bool:
        await self.session.check()
        return await db_call(self.check, context, call)


class ServiceReadPort:
    def __init__(self, store: InquiryStore, run: RunRequest, domain: Window):
        self.store, self.run, self.domain = store, run, domain
        self.fixture = store.inquiry.fixture()
        self.port = DomainReadPort(MockReadFacade(MockCommerce(self.fixture)), domain)

    async def read(
        self, context: Context, call: ToolCall, deadline: float, rows_remaining: int
    ) -> ReadResult:
        if isinstance(call, ReportsCall):
            return await db_call(self.read_report, context, call)
        return await self.port.read(context, call, deadline, rows_remaining)

    def read_report(self, context: Context, call: ReportsCall) -> ReadResult:
        with connect(self.store.settings) as db:
            row = self.store.run_row(db, self.run)
            actor = self.store.actor(row)
            task_id = self.store.report_task(db, actor, row["shop_id"], UUID(call.args.report_id))
            evidence = db.execute(
                SOURCE_SQL, (task_id, actor.organization_id, row["shop_id"])
            ).fetchone()
            if (
                evidence is None
                or str(evidence["id"]) != call.args.report_id
                or evidence["source_state"] != "completed"
            ):
                raise ValueError("REPORT_SOURCE_UNAVAILABLE")
            valid = db.execute(
                "SELECT business.valid_inventory_result(%s,%s,%s,%s) AS valid",
                (task_id, actor.organization_id, row["shop_id"], "p203-inventory-analysis-v1"),
            ).fetchone()
            if not valid or not valid["valid"]:
                raise ValueError("REPORT_SOURCE_UNAVAILABLE")
            stored = _stored(evidence, evidence["normalized_request"])
            report = stored.report
        window = Window(start=report.window.start, end=report.window.end)
        if (
            report.source.provenance.source_kind != "mock"
            or report.source.provenance.raw_hash != context.source_binding
            or report.source.shop_id != context.shop_id
            or window.start < self.domain.start
            or window.end > self.domain.end
        ):
            raise ValueError("REPORT_SOURCE_UNAVAILABLE")
        facts: list[Fact] = []
        if report.complete and report.source_complete:
            for item in report.items:
                facts.append(
                    Fact(
                        evidence_id=key((call.args.report_id, item.sku_key, "sold_units")),
                        metric="sold_units",
                        sku_key=item.sku_key,
                        window=window,
                        as_of=report.now,
                        value=None if item.gross_units is None else str(item.gross_units),
                        unit="件",
                        currency=item.currency,
                        quality_flags=item.quality_flags,
                    )
                )
        return ReadResult(
            tool_call_id=call.tool_call_id,
            shop_id=context.shop_id,
            source_binding=context.source_binding,
            snapshot_id=str(stored.snapshot_id),
            report_id=call.args.report_id,
            as_of=report.now,
            complete=report.complete and report.source_complete,
            scanned_rows=0,
            sku_keys=tuple(item.sku_key for item in report.items),
            windows=(window,),
            facts=tuple(facts),
        )
