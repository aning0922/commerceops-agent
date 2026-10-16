"""queued恢复新profile及仅显式WS运行适配；无PG/平台/真实秘密。"""

import asyncio
import importlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from commerceops.adapters.feishu.business_gateway import BusinessGateway
from commerceops.adapters.feishu.queued_gateway_ready import QueuedReadyClient
from commerceops.adapters.feishu.sdk import restrict_sdk_logs
from commerceops.application.feishu_business.worker_window import (
    KNOWN70_CAPS,
    ControlledWorkerWindow,
)
from websockets.protocol import State

from tests.test_p4_controlled_worker import configured

pytestmark = pytest.mark.offline


def queued_manifest() -> tuple[Any, dict[str, Any]]:
    settings, native, _ = configured()
    settings = settings.model_copy(
        update={"allowed_open_ids": frozenset({"offline-A"}), "allowed_group_chat_ids": frozenset()}
    )
    body = native.model_dump(mode="json")
    task = body["task_ids"][0]
    body.update(
        profile="approved_queued_start",
        expires_at=(datetime.now(UTC) + timedelta(seconds=240)).isoformat(),
        caps=dict(KNOWN70_CAPS),
    )
    body["queued_start"] = dict(
        schema_version="p4-approved-queued-start-v1",
        worker_window_id=body["window_id"],
        gateway_window_id=body["gateway_window_id"],
        expires_at=body["expires_at"],
        original_gateway_id=str(uuid4()),
        original_gateway_hash="a" * 64,
        gateway_termination_id=str(uuid4()),
        task_id=task,
        source_task_id=str(uuid4()),
        task_version=1,
        task_binding_hash="b" * 64,
        source_binding_hash="c" * 64,
        job_ids=[str(uuid4()), str(uuid4())],
        jobs_binding_hash="d" * 64,
        inbox_id=str(uuid4()),
        receipt_hash="e" * 64,
        operator_auth_version=3,
        target_key=settings.base_target_key,
    )
    return settings, body


def test_new_profile_exact_caps_and_old_serialized_shape() -> None:
    settings, body = queued_manifest()
    assert (
        sum(
            ControlledWorkerWindow.model_validate_json(json.dumps(body))
            .window(settings)
            .caps.values()
        )
        == 14
    )
    _, old, _ = configured()
    assert "queued_start" not in old.model_dump(mode="json")


@pytest.mark.parametrize(
    "change",
    [
        "no_binding",
        "other_task",
        "old_equals_new",
        "same_job",
        "same_source",
        "bool_version",
        "cap",
        "old_profile",
        "different_expiry",
        "other_target",
    ],
)
def test_queued_window_cannot_expand_or_mix_original_contracts(change: str) -> None:
    settings, body = queued_manifest()
    r = body["queued_start"]
    if change == "no_binding":
        body["queued_start"] = None
    elif change == "other_task":
        body["task_ids"] = [str(uuid4())]
    elif change == "old_equals_new":
        r["original_gateway_id"] = body["gateway_window_id"]
    elif change == "same_job":
        r["job_ids"] = [r["job_ids"][0]] * 2
    elif change == "same_source":
        r["source_task_id"] = r["task_id"]
    elif change == "bool_version":
        r["task_version"] = True
    elif change == "cap":
        body["caps"]["im.v1.message.create"] = 3
    elif change == "old_profile":
        body["profile"] = "known70"
    elif change == "different_expiry":
        r["expires_at"] = (datetime.now(UTC) + timedelta(seconds=200)).isoformat()
    else:
        r["target_key"] = "different"
    with pytest.raises((ValueError, PermissionError)):
        ControlledWorkerWindow.model_validate_json(json.dumps(body)).window(settings)


@pytest.mark.parametrize(
    "kind",
    [
        "success",
        "closed",
        "raw_tls",
        "handshake_failure",
        "handler_missing",
        "receive_missing",
        "persist_failure",
        "duplicate",
        "disconnect",
    ],
)
def test_pinned_native_connect_ready_and_loss_callback_with_fake_socket_only(
    kind: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    restrict_sdk_logs()
    sdk = importlib.import_module("lark_oapi.ws.client")
    settings, _ = queued_manifest()
    calls: list[str] = []

    async def case() -> None:
        loop = asyncio.get_running_loop()
        wait = asyncio.Event()

        class Socket:
            state = None if kind == "raw_tls" else State.CLOSED if kind == "closed" else State.OPEN

            async def recv(self) -> None:
                await wait.wait()

            async def close(self) -> None:
                pass

        async def connect(*args: Any, **kwargs: Any) -> Socket:
            if kind == "handshake_failure":
                raise RuntimeError("offline failure")
            return Socket()

        class NoReceiverLoop:
            def create_task(self, coro: Any) -> None:
                coro.close()

        def persist() -> None:
            if kind == "persist_failure":
                raise RuntimeError("offline persistence failure")
            calls.append("ready")

        dispatcher = BusinessGateway(None, settings.policy()).dispatcher()  # type: ignore[arg-type]
        if kind == "handler_missing":
            dispatcher._callback_processor_map.clear()
        with monkeypatch.context() as patch:
            patch.setattr(sdk, "loop", NoReceiverLoop() if kind == "receive_missing" else loop)
            patch.setattr(sdk.websockets, "connect", connect)
            try:
                client = QueuedReadyClient(
                    "offline-app",
                    "offline-material",
                    event_handler=dispatcher,
                    auto_reconnect=False,
                    persist_ready=persist,
                    persist_lost=lambda: calls.append("lost"),
                )
                client._get_conn_url = lambda: (
                    "wss://offline.invalid/socket?device_id=offline&service_id=1"
                )
                await client._connect()
                if kind == "duplicate":
                    await client._connect()
                if kind == "disconnect":
                    await client._disconnect()
                assert kind in ("success", "disconnect")
                assert calls == (["ready", "lost"] if kind == "disconnect" else ["ready"])
            except (PermissionError, RuntimeError):
                assert kind not in ("success", "disconnect")
                assert calls == (["ready"] if kind == "duplicate" else [])
            finally:
                tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
                for task in tasks:
                    task.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(case())


def test_owned_transport_frame_reaches_native_sdk_card_handler_and_ack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transport fixture must encode all required protobuf fields; original parser stays live."""
    from tests.p4_queued_transport import install
    from tests.test_feishu_contracts import POLICY
    from tests.test_p4_gateway import Receiver, callback

    sdk = importlib.import_module("lark_oapi.ws.client")
    receiver = Receiver()
    states: list[str] = []

    async def run() -> None:
        with monkeypatch.context() as patch:
            patch.setattr(sdk, "loop", asyncio.get_running_loop())
            patch.setattr(sdk.requests, "post", sdk.requests.post)
            patch.setattr(sdk.websockets, "connect", sdk.websockets.connect)
            install(tmp_path)
            client = QueuedReadyClient(
                "offline-app",
                "offline-material",
                event_handler=BusinessGateway(receiver, POLICY).dispatcher(),
                auto_reconnect=False,
                persist_ready=lambda: states.append("ready"),
                persist_lost=lambda: states.append("lost"),
            )
            try:
                await client._connect()
                (tmp_path / "event-approval.json").write_text(json.dumps(callback()))
                async with asyncio.timeout(3):
                    while not receiver.calls:
                        await asyncio.sleep(0.01)
                    while not any(
                        json.loads(p.read_bytes())["frames_sent"] == 1
                        for p in tmp_path.glob("transport-*.safe.json")
                    ):
                        await asyncio.sleep(0.01)
                assert len(receiver.calls) == 1 and states == ["ready"]
                await client._disconnect()
                assert states == ["ready", "lost"]
            finally:
                tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(run())
