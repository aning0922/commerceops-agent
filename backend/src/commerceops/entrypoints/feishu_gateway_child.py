"""原官方SDK阻塞长连接的受控子进程；仅Root窗口启，默认无入口自动启用。"""

import argparse
import signal
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import lark_oapi as lark  # type: ignore[import-untyped]

from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.adapters.feishu.business_factory import private_value
from commerceops.adapters.feishu.business_gateway import BusinessCard, BusinessGateway
from commerceops.adapters.feishu.contracts import MessageProbe
from commerceops.adapters.feishu.sdk import restrict_sdk_logs
from commerceops.application.feishu_business.gateway_window import GatewayWindow
from commerceops.application.replenishment.contracts import WebFailure
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_business import FeishuBusinessStore
from commerceops.infrastructure.feishu_gateway_window import (
    claim_gateway,
    gateway_process_started,
    guard_gateway,
)
from commerceops.infrastructure.replenishment_repository import ReplenishmentStore
from commerceops.infrastructure.web_config import WebConfig


class BoundedReceiver:
    def __init__(self, store: FeishuBusinessStore, window: GatewayWindow):
        self.store, self.window, self.admitted = store, window, 0

    def admit(self) -> None:
        if not self.window.active() or self.admitted >= self.window.max_callbacks:
            raise WebFailure("GATEWAY_CALLBACK_CAP_EXHAUSTED", 503)
        self.admitted += 1  # 当前SDK业务callback admissions，不称raw frame/ACK/wire次数。

    def message(self, message: MessageProbe) -> dict[str, Any]:
        self.admit()
        return self.store.message(message)

    def card(self, card: BusinessCard) -> dict[str, Any]:
        self.admit()
        return self.store.card(card)


def serve(config_file: Path, window_file: Path, *, web_config_sha256: str | None = None) -> None:
    restrict_sdk_logs()  # 在读取任何秘密/构造SDK之前禁原文logger与传播。
    settings = BusinessSettings.model_validate_json(private_value(config_file))
    window = GatewayWindow.model_validate_json(private_value(window_file))
    if not window.active():
        raise PermissionError("P4_GATEWAY_WINDOW_CLOSED")
    # 独立CLI误用也不能无限留socket；OS alarm只使结果未知，父进程仍必须wait/reap。
    signal.setitimer(signal.ITIMER_REAL, (window.expires_at - datetime.now(UTC)).total_seconds())
    web = (
        WebConfig.from_file(settings.web_config_file)
        if web_config_sha256 is None
        else WebConfig.from_file(settings.web_config_file, expected_sha256=web_config_sha256)
    )
    if web.database.user != "commerceops_app":
        raise PermissionError("P4_GATEWAY_RUNTIME_ROLE_REQUIRED")
    # lease仅本child的同步连接，不借用WorkerSession/跨loop AsyncConnection。
    with connect(web.database) as lease:
        claim_gateway(lease, settings, window)
        gateway_process_started(lease, window)
        store = FeishuBusinessStore(
            ReplenishmentStore(web, Path("tests/fixtures/commerce/inventory-v1")),
            settings.shop_id,
            window.parameters,
            allow_live_bindings=True,
            gateway_guard=lambda db, create: guard_gateway(db, window, create),
            f02_enabled=settings.f02_enabled,
            f02_gateway_window_id=window.window_id if settings.f02_enabled else None,
        )
        receiver = BoundedReceiver(store, window)
        websocket = lark.ws.Client(
            settings.app_id,
            private_value(settings.app_secret_file),
            event_handler=BusinessGateway(receiver, settings.policy()).dispatcher(),
            auto_reconnect=False,
        )
        restrict_sdk_logs()
        websocket.start()  # 1.7.3无public stop，父进程在固定截止terminate/wait/reap。


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--window-file", required=True, type=Path)
    parser.add_argument("--web-config-sha256")
    args = parser.parse_args()
    try:
        serve(args.config, args.window_file, web_config_sha256=args.web_config_sha256)
    except Exception as error:
        raise SystemExit(f"P4 gateway child failed: {type(error).__name__}") from None


if __name__ == "__main__":
    main()
