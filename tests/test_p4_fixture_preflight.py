"""错Mock来源在原Gateway/Worker读取Secret或构造SDK前失败关闭。"""

import asyncio
import json
import signal
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock

import lark_oapi as lark  # type: ignore[import-untyped]
import pytest
from commerceops.application.feishu_business.gateway_window import GatewayWindow
from commerceops.entrypoints import feishu_gateway_child, feishu_worker_child
from commerceops.infrastructure.feishu_gateway_window import claimed_state
from commerceops.infrastructure.web_config import WebConfig
from commerceops.workflows.inventory_analysis import MockCollectorFactory

from tests.test_p4_controlled_worker import Database, configured

pytestmark = pytest.mark.offline


def gateway() -> GatewayWindow:
    settings, window, _ = configured()
    return GatewayWindow.model_validate_json(
        json.dumps(
            {
                "schema_version": "p4-gateway-v1",
                "window_id": str(window.gateway_window_id),
                "organization_id": str(settings.organization_id),
                "shop_id": str(settings.shop_id),
                "expires_at": window.expires_at.isoformat(),
                "enabled": True,
                "parameters": {
                    "source_mode": "mock",
                    "dataset_version": "inventory-v1",
                    "fixture_case": "known_inbound",
                    "L": 3,
                    "R": 7,
                    "S": 2,
                },
            }
        )
    )


def test_gateway_source_mismatch_never_reads_secret_or_constructs_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, _, config = configured()
    window = gateway()
    cfg, win = Path("synthetic-config"), Path("synthetic-window")

    def private(path: Path) -> str:
        if path == cfg:
            return settings.model_dump_json()
        if path == win:
            return window.model_dump_json()
        raise AssertionError("SECRET_MUST_NOT_BE_READ")

    class Lease:
        def __init__(self) -> None:
            self.rows = iter(
                [
                    {"held": True},
                    {
                        "external_shop_key": "p4-ro-only",
                        "currency": "CNY",
                        "timezone": "Asia/Shanghai",
                    },
                ]
            )

        def __enter__(self) -> "Lease":
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def execute(self, *args: Any) -> Any:
            row = next(self.rows)
            return type("Cursor", (), {"fetchone": lambda self: row})()

    socket = Mock()
    reader = Mock(side_effect=private)
    monkeypatch.setattr(feishu_gateway_child, "private_value", reader)
    monkeypatch.setattr(WebConfig, "from_file", Mock(return_value=config))
    monkeypatch.setattr(feishu_gateway_child, "connect", Mock(return_value=Lease()))
    monkeypatch.setattr(signal, "setitimer", Mock())
    monkeypatch.setattr(lark.ws, "Client", socket)
    with pytest.raises(PermissionError, match="^P4_CONTROLLED_FIXTURE_SCOPE_REQUIRED$"):
        feishu_gateway_child.serve(cfg, win)
    assert reader.call_count == 2
    socket.assert_not_called()


def test_worker_source_mismatch_never_creates_ledger_factory_or_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, window, config = configured()
    original = gateway().model_copy(update={"window_id": window.gateway_window_id})
    row = {
        "after_state": claimed_state(original),
        "occurred_at": datetime.now(UTC),
        "external_shop_key": "p4-ro-only",
        "currency": "CNY",
        "timezone": "Asia/Shanghai",
    }
    session = type("Session", (), {"start": AsyncMock(), "close": AsyncMock()})()
    ledger, factory, graph = Mock(), Mock(), Mock()
    monkeypatch.setattr(feishu_worker_child, "WorkerSession", Mock(return_value=session))
    monkeypatch.setattr(
        feishu_worker_child, "open_async", AsyncMock(return_value=Database([row, []]))
    )
    monkeypatch.setattr(feishu_worker_child, "PersistentSDKLedger", ledger)
    monkeypatch.setattr(feishu_worker_child, "BusinessSDKFactory", factory)
    monkeypatch.setattr(feishu_worker_child, "Worker", graph)
    result = asyncio.run(
        feishu_worker_child.controlled_work(
            settings,
            window,
            config,
            MockCollectorFactory(Path("tests/fixtures/commerce/inventory-v1")),
        )
    )
    assert result["result"] == "failed" and result["failure_category"] == "PermissionError"
    ledger.assert_not_called()
    factory.assert_not_called()
    graph.assert_not_called()
    session.close.assert_awaited_once_with(clean=True)
