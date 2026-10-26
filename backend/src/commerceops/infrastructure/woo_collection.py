"""M2 同一受限 Woo adapter 的完整业务采集；18秒总限额覆盖配置/DB/HTTP。"""

import time
from datetime import datetime

from commerceops.adapters.commerce.woocommerce import WooCommerce
from commerceops.adapters.commerce.woocommerce_config import WooReadOnlyConfig
from commerceops.adapters.commerce.woocommerce_http import WooReadFailure
from commerceops.application.commerce.analysis_task import (
    CollectedInventory,
    WooInventoryTaskRequest,
)
from commerceops.application.commerce.collection import InventoryCollector
from commerceops.application.commerce.contracts import OrderLine, Quality
from commerceops.infrastructure.commerce_sources import CommerceSourceFiles, resolve_woo_source
from commerceops.infrastructure.database import DatabaseSettings, connect


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

    def __call__(self, request: WooInventoryTaskRequest) -> InventoryCollector:
        deadline = time.monotonic() + 18
        with connect(self.settings) as db:
            remaining_ms = int((deadline - time.monotonic()) * 1000)
            if remaining_ms <= 0:
                raise TimeoutError("COMMERCE_SOURCE_DEADLINE")
            db.execute("SELECT set_config('statement_timeout',%s,true)", (str(remaining_ms),))
            registered, actual = resolve_woo_source(
                db,
                self.files,
                request.organization_id,
                request.shop_id,
                expected_version=request.source_config_version,
                expected_binding=request.source_binding_id,
            )
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
