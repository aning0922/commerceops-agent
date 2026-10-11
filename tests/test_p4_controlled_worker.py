"""正式装配的离线准入/同原ports接线；无PG、平台或真实Secret。"""

import asyncio
import json
import socket
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import lark_oapi as lark  # type: ignore[import-untyped]
import pytest
from commerceops.adapters.feishu.business_base import BusinessBaseAdapter, BusinessRecordSDK
from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.adapters.feishu.business_im import BusinessIMSDK
from commerceops.application.feishu_business.gateway_window import GatewayWindow
from commerceops.application.feishu_business.sdk_window import SDKWindow
from commerceops.application.feishu_business.worker_window import ControlledWorkerWindow
from commerceops.entrypoints import feishu_business, feishu_worker_child
from commerceops.infrastructure import worker_lock
from commerceops.infrastructure.database import DatabaseSettings
from commerceops.infrastructure.feishu_gateway_window import claimed_state
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.worker import Worker
from commerceops.workflows.inventory_analysis import MockCollectorFactory
from commerceops.workflows.replenishment import ApprovalRunner
from pydantic import ValidationError

pytestmark = pytest.mark.offline


def configured() -> tuple[BusinessSettings, ControlledWorkerWindow, WebConfig]:
    settings = BusinessSettings.model_validate_json(
        Path("docs/contracts/p4-config.example.json").read_text()
    )
    value = {
        "schema_version": "p4-worker-v1",
        "window_id": str(uuid4()),
        "gateway_window_id": str(uuid4()),
        "organization_id": str(settings.organization_id),
        "shop_id": str(settings.shop_id),
        "task_ids": [str(uuid4())],
        "expires_at": (datetime.now(UTC) + timedelta(seconds=120)).isoformat(),
        "enabled": True,
        "caps": {
            "auth.v3.tenant_access_token.internal": 1,
            "bot.v3.info": 1,
            "bitable.v1.app_table.list": 2,
            "bitable.v1.app_table_field.list": 2,
            "im.v1.message.create": 2,
            "bitable.v1.app_table_record.create": 1,
            "bitable.v1.app_table_record.update": 1,
            "bitable.v1.app_table_record.list": 4,
        },
    }
    window = ControlledWorkerWindow.model_validate_json(json.dumps(value))
    config = WebConfig(
        DatabaseSettings(
            host="synthetic",
            name="synthetic",
            user="commerceops_app",
            password_file=Path("/synthetic-app-password"),
        ),
        b"x" * 32,
        b"y" * 32,
        ("http://127.0.0.1:18080",),
        transport_mode="local_http",
    )
    return settings, window, config


@pytest.mark.parametrize(
    "change",
    [
        "off",
        "fake",
        "expired",
        "long",
        "naive",
        "wrong_shop",
        "empty",
        "six",
        "double",
        "field3",
        "list1",
        "bool_cap",
    ],
)
def test_controlled_window_rejects_disabled_fake_unbounded_scope_and_caps(change: str) -> None:
    settings, window, _ = configured()
    value = window.model_dump(mode="json")
    if change == "off":
        value["enabled"] = False
    elif change == "fake":
        value["verification_mode"] = "offline_fake"
    elif change == "expired":
        value["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    elif change == "long":
        value["expires_at"] = (datetime.now(UTC) + timedelta(seconds=400)).isoformat()
    elif change == "naive":
        value["expires_at"] = datetime.now().isoformat()
    elif change == "wrong_shop":
        value["shop_id"] = str(uuid4())
    elif change == "empty":
        value["task_ids"] = []
    elif change == "six":
        value["task_ids"] = [str(uuid4()) for _ in range(6)]
    else:
        value["caps"][
            {
                "double": "auth.v3.tenant_access_token.internal",
                "field3": "bitable.v1.app_table_field.list",
                "list1": "bitable.v1.app_table_record.list",
                "bool_cap": "im.v1.message.create",
            }[change]
        ] = {"double": 2, "field3": 3, "list1": 1, "bool_cap": True}[change]
    with pytest.raises((ValidationError, PermissionError, ValueError)):
        ControlledWorkerWindow.model_validate_json(json.dumps(value)).window(settings)


@pytest.mark.parametrize(
    ("method", "ceiling"),
    [
        ("auth.v3.tenant_access_token.internal", 1),
        ("bot.v3.info", 1),
        ("bitable.v1.app_table.list", 2),
        ("bitable.v1.app_table_field.list", 2),
        ("im.v1.message.create", 2),
        ("bitable.v1.app_table_record.create", 1),
        ("bitable.v1.app_table_record.update", 1),
        ("bitable.v1.app_table_record.list", 4),
    ],
)
@pytest.mark.parametrize("amplified", [False, True])
def test_known70_rejects_each_method_above_approved_ceiling(
    method: str, ceiling: int, amplified: bool
) -> None:
    settings, window, _ = configured()
    value = window.model_dump(mode="json")
    value["caps"][method] = 500 if amplified else ceiling + 1
    with pytest.raises(PermissionError, match="P4_CONTROLLED_WORKER_WINDOW_CLOSED"):
        ControlledWorkerWindow.model_validate_json(json.dumps(value)).window(settings)


@pytest.mark.parametrize(
    "method", ["im.v1.message.update", "bitable.v1.app_table_record.delete", "unapproved.method"]
)
def test_known70_rejects_extra_method_before_sdk_window(method: str) -> None:
    settings, window, _ = configured()
    value = window.model_dump(mode="json")
    value["caps"][method] = 1
    with pytest.raises((ValidationError, PermissionError)):
        ControlledWorkerWindow.model_validate_json(json.dumps(value)).window(settings)


def test_known70_boundary_is_fourteen_without_changing_general_sdk_window() -> None:
    settings, window, _ = configured()
    approved = window.window(settings)
    assert sum(approved.caps.values()) == 14
    general = SDKWindow(
        uuid4(),
        window.organization_id,
        window.shop_id,
        window.expires_at,
        {"im.v1.message.create": 500},
        enabled=True,
        verification_mode="controlled_sdk",
    )
    assert general.caps["im.v1.message.create"] == 500


def test_formal_cli_default_off_does_not_spawn_or_read_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spawn = AsyncMock()
    monkeypatch.setattr(subprocess, "Popen", spawn)
    monkeypatch.setattr(
        "sys.argv", ["feishu_business", "worker", "--config", "/missing-private-file"]
    )
    with pytest.raises(SystemExit, match="P4_CONFIGURATION_INVALID"):
        feishu_business.main()
    spawn.assert_not_called()
    monkeypatch.delenv("COMMERCEOPS_MODE", raising=False)
    with pytest.raises(PermissionError, match="P4_CONTROLLED_TEST_MODE_REQUIRED"):
        feishu_business.run_worker(Path("/missing"), Path("/missing"))
    spawn.assert_not_called()


class Rows:
    def __init__(self, value: Any):
        self.value = value

    async def fetchone(self) -> Any:
        return self.value

    async def fetchall(self) -> Any:
        return self.value


class Database:
    def __init__(self, rows: list[Any]):
        self.rows = iter(rows)

    async def __aenter__(self) -> "Database":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    async def execute(self, *args: Any) -> Rows:
        return Rows(next(self.rows))


@pytest.mark.parametrize(
    "mutation",
    [
        "none",
        "task_missing",
        "parameter_changed",
        "fake_history",
        "gateway_changed",
        "app",
        "tenant",
        "allowlist",
        "remapped",
        "revoked",
        "original_identity",
        "original_principal",
    ],
)
def test_controlled_task_scope_requires_same_original_gateway_parameters_and_no_fake_history(
    mutation: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, window, config = configured()
    parameters = {
        "source_mode": "mock",
        "dataset_version": "inventory-v1",
        "fixture_case": "known_inbound",
        "L": 7,
        "R": 3,
        "S": 2,
    }
    gateway = GatewayWindow.model_validate_json(
        json.dumps(
            {
                "schema_version": "p4-gateway-v1",
                "window_id": str(window.gateway_window_id),
                "organization_id": str(window.organization_id),
                "shop_id": str(window.shop_id),
                "expires_at": (window.expires_at + timedelta(seconds=10)).isoformat(),
                "max_callbacks": 2,
                "max_workflows": 1,
                "parameters": parameters,
                "enabled": True,
            }
        )
    )
    state = claimed_state(gateway)
    if mutation == "gateway_changed":
        state["shop_id"] = str(uuid4())
    tasks = (
        []
        if mutation == "task_missing"
        else [
            {
                "id": next(iter(window.task_ids)),
                "parameters": {} if mutation == "parameter_changed" else parameters,
                "app_id": settings.app_id,
                "tenant_key": settings.tenant_key,
                "external_subject": next(iter(settings.allowed_open_ids)),
                "identity_id": window.window_id,
                "requester_id": window.organization_id,
                "principal_id": window.organization_id,
                "original_identity": str(window.window_id),
                "original_principal": str(window.organization_id),
                "permitted": True,
            }
        ]
    )
    if tasks and mutation in (
        "app",
        "tenant",
        "allowlist",
        "remapped",
        "revoked",
        "original_identity",
        "original_principal",
    ):
        column = {
            "app": "app_id",
            "tenant": "tenant_key",
            "allowlist": "external_subject",
            "remapped": "principal_id",
            "revoked": "permitted",
            "original_identity": "original_identity",
            "original_principal": "original_principal",
        }[mutation]
        tasks[0][column] = (
            False if mutation == "revoked" else uuid4() if mutation == "remapped" else "forged"
        )
    db = Database(
        [
            {
                "after_state": state,
                "occurred_at": datetime.now(UTC),
                "external_shop_key": "demo",
                "currency": "CNY",
                "timezone": "Asia/Shanghai",
            },
            tasks,
            {"exists": 1} if mutation == "fake_history" else None,
        ]
    )
    monkeypatch.setattr(feishu_worker_child, "open_async", AsyncMock(return_value=db))
    if mutation == "none":
        asyncio.run(feishu_worker_child.trusted_scope(config, settings, window))
    else:
        with pytest.raises(PermissionError):
            asyncio.run(feishu_worker_child.trusted_scope(config, settings, window))


@pytest.mark.parametrize("bad", ["none", "stopped_missing", "wrong_pid", "duplicate"])
def test_parent_confirms_only_unique_full_original_same_namespace_receipt(
    bad: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, _, config = configured()
    expected = {
        "pid": 123,
        "host": socket.gethostname(),
        "pid_namespace": worker_lock.process_namespace(),
    }
    owner = str(uuid4())
    rows: list[dict[str, Any]] = [
        {"entity_id": owner, "started": expected, "stopped": dict(expected)}
    ]
    if bad == "stopped_missing":
        rows[0]["stopped"] = None
    elif bad == "wrong_pid":
        rows[0]["stopped"] = {**expected, "pid": 124}
    elif bad == "duplicate":
        rows *= 2
    monkeypatch.setattr(worker_lock, "open_async", AsyncMock(return_value=Database([rows])))
    absent = pytest.MonkeyPatch()
    seen = []
    absent.setattr(worker_lock, "require_process_absent", lambda value: seen.append(value))
    confirm = AsyncMock()
    monkeypatch.setattr(worker_lock, "confirm_termination", confirm)
    try:
        if bad == "none":
            asyncio.run(feishu_business.confirm_worker_child(config, settings.organization_id, 123))
            assert seen == [expected]
            confirm.assert_awaited_once()
        else:
            with pytest.raises(worker_lock.TerminationRequired):
                asyncio.run(
                    feishu_business.confirm_worker_child(config, settings.organization_id, 123)
                )
            assert seen == []
            confirm.assert_not_called()
    finally:
        absent.undo()


@pytest.mark.parametrize("im_outcome", ["idle", "unknown"])
def test_one_session_real_ports_ledger_and_stop_on_unknown_no_later_base_dispatch(
    im_outcome: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, window, config = configured()
    sessions = []
    ports = []
    base_calls = []

    class Session:
        def __init__(self, database: Any, organization: Any):
            self.settings = database
            self.organization = organization
            self.active = False
            sessions.append(self)

        async def start(self) -> None:
            self.active = True

        async def close(self, *, clean: bool = False) -> None:
            self.active = False

    client = lark.Client.builder().app_id("synthetic").enable_set_token(True).build()

    async def target(factory: Any) -> tuple[str, str, int]:
        factory.client = client
        factory.option = object()
        return "synthetic", "synthetic", 15

    class IM:
        def __init__(
            self, session: Any, config: Any, policy: Any, sender: Any, gate: Any, ledger: Any
        ):
            assert isinstance(sender, BusinessIMSDK)
            assert ledger.session is session
            assert gate.verification_mode == "controlled_sdk"
            ports.append(ledger)

        async def dispatch_one(self) -> str:
            return im_outcome

    class Base:
        def __init__(self, session: Any, adapter: Any, gate: Any, ledger: Any):
            assert isinstance(adapter, BusinessBaseAdapter)
            assert isinstance(adapter.transport, BusinessRecordSDK)
            assert ledger.session is session
            ports.append(ledger)

        async def dispatch_one(self) -> str:
            base_calls.append(1)
            return "idle"

    class Loop:
        def __init__(
            self,
            session: Any,
            runner: Any,
            *,
            reconcile: Any,
            recovery_scan_seconds: int,
            task_ids: Any,
        ):
            self.session = session
            self.maintain = reconcile

        async def run(self, stop: asyncio.Event) -> None:
            await self.maintain()
            await self.session.close(clean=True)

    monkeypatch.setattr(feishu_worker_child, "WorkerSession", Session)
    monkeypatch.setattr(feishu_worker_child, "trusted_scope", AsyncMock())
    monkeypatch.setattr(
        feishu_worker_child, "controlled_task_ids", AsyncMock(return_value=window.task_ids)
    )
    monkeypatch.setattr(feishu_worker_child, "verified_target", target)
    monkeypatch.setattr(feishu_worker_child, "IMDeliveryStore", IM)
    monkeypatch.setattr(feishu_worker_child, "BaseDeliveryStore", Base)
    monkeypatch.setattr(feishu_worker_child, "Worker", Loop)
    monkeypatch.setattr(feishu_worker_child, "open_async", AsyncMock(return_value=Database([[]])))
    monkeypatch.setattr(ApprovalRunner, "reconcile", AsyncMock())
    result = asyncio.run(
        feishu_worker_child.controlled_work(
            settings,
            window,
            config,
            MockCollectorFactory(Path("tests/fixtures/commerce/inventory-v1")),
        )
    )
    assert len(sessions) == 1
    assert ports[0] is ports[1]
    assert result["model_requests"] == 0
    assert result["field_count"] == 15
    assert base_calls == ([] if im_outcome == "unknown" else [1])
    assert result["result"] == ("delivery_stopped" if im_outcome == "unknown" else "window_stopped")


def test_stop_requested_in_maintenance_does_not_claim_another_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        session = type("Session", (), {"close": AsyncMock()})()
        runner = type("Runner", (), {"workflow_versions": frozenset()})()
        stop = asyncio.Event()

        async def maintain() -> None:
            stop.set()

        worker = Worker(session, runner, reconcile=maintain)
        queue = type("Queue", (), {"recover_confirmed": AsyncMock(), "claim": AsyncMock()})()
        worker.queue = queue
        await worker.run(stop)
        queue.claim.assert_not_called()
        session.close.assert_awaited_once_with(clean=True)

    asyncio.run(run())
