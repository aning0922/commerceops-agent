"""M2 同一受限 Woo adapter 的完整业务采集；18秒总限额覆盖配置/DB/HTTP。"""

import asyncio
import time
from datetime import datetime
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from commerceops.adapters.commerce.woocommerce import WooCommerce
from commerceops.adapters.commerce.woocommerce_config import WooReadOnlyConfig
from commerceops.adapters.commerce.woocommerce_http import WooReadFailure
from commerceops.application.commerce.analysis_task import (
    CollectedInventory,
    WooInventoryTaskRequest,
)
from commerceops.application.commerce.collection import InventoryCollector
from commerceops.application.commerce.contracts import OrderLine, Quality
from commerceops.application.commerce.source_binding import RegisteredWooSource, WooSourceMetadata
from commerceops.infrastructure.commerce_sources import (
    CommerceSourceFiles,
    resolve_woo_source_async,
)
from commerceops.infrastructure.database import DatabaseSettings
from commerceops.infrastructure.web_config import private_bytes


class WooInventoryCollector(InventoryCollector):
    def __init__(self, port: WooCommerce, business_now: datetime):
        super().__init__(
            port,
            port.source,
            business_now,
            max_pages=port.config.max_pages,
            attempts=1,
            retry_sleep=False,
        )
        self.woo = port

    def _order_ids(self, orders: tuple[OrderLine, ...]) -> tuple[str, ...]:
        return self.woo.observed_order_ids

    def _finish_collection(self) -> tuple[set[Quality], bool]:
        try:
            self.woo.http.revalidate()
            self.woo.http.remaining()
            return set(), True
        except WooReadFailure as error:
            return {error.quality}, False

    async def collect(self) -> CollectedInventory:
        try:
            return await super().collect()
        finally:
            self.woo.close()


class BoundWooCollectorFactory:
    def __init__(self, settings: DatabaseSettings, files: CommerceSourceFiles):
        self.settings, self.files = settings, files

    async def __call__(
        self,
        request: WooInventoryTaskRequest,
        *,
        absolute_deadline: float | None = None,
    ) -> InventoryCollector:
        deadline = min(
            time.monotonic() + 18,
            absolute_deadline if absolute_deadline is not None else float("inf"),
        )
        if deadline <= time.monotonic():
            raise TimeoutError("COMMERCE_SOURCE_DEADLINE")
        db: AsyncConnection[dict[str, Any]] | None = None

        async def binding() -> tuple[RegisteredWooSource, WooSourceMetadata]:
            nonlocal db
            # Explicit private FD reading also rejects FIFO/symlink DB password inputs.
            password = private_bytes(self.settings.password_file).decode().strip()
            if not password:
                raise ValueError("COMMERCE_SOURCE_UNAVAILABLE")
            remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
            db = await AsyncConnection.connect(
                host=self.settings.host,
                port=self.settings.port,
                dbname=self.settings.name,
                user=self.settings.user,
                password=password,
                connect_timeout=5,
                options=f"-c statement_timeout={remaining_ms}",
                autocommit=True,
                row_factory=dict_row,
            )
            # Server fallback only; the async client deadline governs every await,
            # including this first response. No explicit transaction is opened.
            remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
            await db.execute(
                "SELECT set_config('statement_timeout',%s,false)",
                (str(remaining_ms),),
            )
            return await resolve_woo_source_async(
                db,
                self.files,
                request.organization_id,
                request.shop_id,
                expected_version=request.source_config_version,
                expected_binding=request.source_binding_id,
            )

        operation = asyncio.create_task(binding())
        try:
            done, _ = await asyncio.wait(
                (operation,),
                timeout=max(0, deadline - time.monotonic()),
            )
            if not done:
                raise TimeoutError("COMMERCE_SOURCE_DEADLINE")
            registered, actual = operation.result()
        finally:
            # A fresh autocommit read connection has no COMMIT/ROLLBACK I/O to await.
            # Close libpq locally before cancellation: psycopg must not spend another
            # cancellation/drain window on an ACTIVE connection after our deadline.
            if db is not None:
                await db.close()
            if not operation.done():
                operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)
        if deadline <= time.monotonic():
            raise TimeoutError("COMMERCE_SOURCE_DEADLINE")
        pins = self.files.credential_pins(registered, actual)
        limits = actual.model_dump(
            include={
                "per_page",
                "max_pages",
                "max_requests",
                "timeout_seconds",
                "max_elapsed_seconds",
                "max_response_bytes",
                "max_retries",
            }
        )
        config = WooReadOnlyConfig(
            base_url=actual.origin,
            consumer_key_file=actual.consumer_key_file,
            consumer_secret_file=actual.consumer_secret_file,
            ca_file=actual.ca_file,
            shop_id=actual.external_shop_key,
            timezone=actual.timezone,
            currency=actual.currency,
            window=actual.window,
            **limits,
        )
        port = WooCommerce(config, pins=pins, absolute_deadline=deadline)
        try:
            port.http.remaining()
            return WooInventoryCollector(port, actual.business_now)
        except BaseException:
            port.close()
            raise
