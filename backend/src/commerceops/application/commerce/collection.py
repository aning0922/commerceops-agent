"""事务外有界采集；观测快照不等于平台原子快照。"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial

from commerceops.application.commerce.analysis_task import CollectedInventory
from commerceops.application.commerce.contracts import (
    DTO,
    Inventory,
    OrderLine,
    Page,
    Quality,
    Refund,
    Source,
    Window,
)
from commerceops.application.commerce.inventory_facts import InventoryInput, OpenWorkItemInput
from commerceops.application.commerce.ports import CommercePort
from commerceops.domain.commerce_values import complete_days, integer, utc_time


class InventoryCollector:
    def __init__(
        self,
        port: CommercePort,
        source: Source,
        now: datetime,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        max_pages: int = 200,
        attempts: int = 3,
        retry_sleep: bool = True,
        open_items: tuple[OpenWorkItemInput, ...] = (),
    ):
        if not 1 <= integer(max_pages) <= 200 or not 1 <= integer(attempts) <= 3:
            raise ValueError("INVALID_COLLECTION_LIMIT")
        self.port, self.source, self.now = port, source, utc_time(now)
        self.open_items = open_items
        self.clock, self.max_pages, self.attempts, self.retry_sleep = (
            clock,
            max_pages,
            attempts,
            retry_sleep,
        )

    async def _read[T: DTO](
        self, read: Callable[[str | None], Page[T]], limit: int, identity: Callable[[T], object]
    ) -> tuple[tuple[T, ...], set[Quality], bool]:
        rows: dict[object, T] = {}
        flags: set[Quality] = set()
        cursor = None
        seen: set[str] = set()
        for _ in range(self.max_pages):
            page = None
            for attempt in range(self.attempts):
                page = read(cursor)
                if page.error is None or not page.error.retryable:
                    break
                if attempt + 1 < self.attempts and self.retry_sleep:
                    await asyncio.sleep(min(page.error.retry_after_seconds or 0, 20))
            if page is None:
                raise ValueError("COLLECTION_PAGE_MISSING")
            flags.update(page.warnings)
            if page.source != self.source:
                flags.add(Quality.SOURCE_CHANGED)
            if page.error is not None:
                flags.add(Quality.PARTIAL_FAILURE)
                return tuple(rows.values()), flags, False
            for row in page.items:
                key = identity(row)
                if key in rows:
                    flags.add(Quality.DUPLICATE_ID)
                else:
                    if len(rows) >= limit:
                        flags.add(Quality.CAPACITY_LIMIT)
                        return tuple(rows.values()), flags, False
                    rows[key] = row
            cursor = page.next_cursor
            if cursor is None:
                return tuple(rows.values()), flags, page.complete and not flags
            if cursor in seen:
                flags.add(Quality.MISSING_PAGE)
                return tuple(rows.values()), flags, False
            seen.add(cursor)
        flags.add(Quality.CAPACITY_LIMIT)
        return tuple(rows.values()), flags, False

    def _refund_page(self, ids: tuple[str, ...], cursor: str | None) -> Page[Refund]:
        return self.port.list_refunds(ids, cursor=cursor)

    def _order_ids(self, orders: tuple[OrderLine, ...]) -> tuple[str, ...]:
        return tuple(sorted({row.order_id for row in orders}))

    def _finish_collection(self) -> tuple[set[Quality], bool]:
        return set(), True

    async def collect(self) -> CollectedInventory:
        started = utc_time(self.clock())
        start, end = complete_days(self.now, self.source.timezone)
        window = Window(start=start, end=end)
        # 来源变化最多完整重采一次，其余失败按当前观测存不完整解释。
        result: InventoryInput | None = None
        for _ in range(2):
            products, pf, pc = await self._read(
                lambda c: self.port.list_products(cursor=c), 1000, lambda p: p.sku_key
            )
            orders, of, oc = await self._read(
                lambda c: self.port.list_order_lines(window, cursor=c),
                10000,
                lambda row: (row.order_id, row.line_id),
            )
            if oc:
                order_ids = self._order_ids(orders)
                refunds, rf, rc = await self._read(
                    partial(self._refund_page, order_ids),
                    10000,
                    lambda r: r.refund_id,
                )
            else:
                refunds, rf, rc = (), {Quality.PARTIAL_FAILURE}, False
            stocks: list[Inventory] = []
            flags = pf | of | rf
            stock_complete = True
            for product in products:
                observation = None
                for attempt in range(self.attempts):
                    observation = self.port.get_inventory(product.sku_key)
                    if observation.error is None or not observation.error.retryable:
                        break
                    if attempt + 1 < self.attempts and self.retry_sleep:
                        await asyncio.sleep(min(observation.error.retry_after_seconds or 0, 20))
                if observation is None:
                    raise ValueError("COLLECTION_STOCK_MISSING")
                flags.update(observation.warnings)
                if observation.source != self.source:
                    flags.add(Quality.SOURCE_CHANGED)
                if observation.item is not None:
                    stocks.append(observation.item)
                quality_only = bool(observation.warnings) and set(observation.warnings) <= {
                    Quality.UNKNOWN_STOCK,
                    Quality.SHARED_POOL_UNRESOLVED,
                }
                if (
                    observation.error is not None
                    or observation.item is None
                    or (not observation.complete and not quality_only)
                ):
                    stock_complete = False
                    flags.add(Quality.PARTIAL_FAILURE)
            final_flags, finalized = (
                self._finish_collection() if pc and oc and rc and stock_complete else (set(), False)
            )
            flags.update(final_flags)
            # 属性UNKNOWN_STOCK/shared是已收齐的质量问题，由规则明确阻断，非缺页。
            result = InventoryInput(
                source=self.source,
                now=self.now,
                window=window,
                products=products,
                order_lines=orders,
                refunds=refunds,
                inventories=tuple(stocks),
                complete=pc
                and oc
                and rc
                and stock_complete
                and finalized
                and Quality.SOURCE_CHANGED not in flags,
                warnings=tuple(sorted(flags)),
                open_items=self.open_items,
            )
            if Quality.SOURCE_CHANGED not in flags:
                break
        if result is None:
            raise ValueError("COLLECTION_FAILED")
        return CollectedInventory(result, started, utc_time(self.clock()))
