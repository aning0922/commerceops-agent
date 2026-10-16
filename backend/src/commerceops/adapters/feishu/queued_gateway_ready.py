"""仅queued恢复显式使用的锁定SDK运行就绪适配；不修改SDK库/旧Gateway。"""

import asyncio
import hashlib
import importlib.metadata
import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any

import lark_oapi as lark  # type: ignore[import-untyped]
from lark_oapi.ws.client import Client as SDKClient  # type: ignore[import-untyped]
from websockets.protocol import State

SDK_WS_SHA256 = "18a93f6aa06d7729671dc883c087e8e12a57bcc28e29150b828046816ce53d69"


def require_transport_shape() -> None:
    source = inspect.getsourcefile(SDKClient)
    if (
        importlib.metadata.version("lark-oapi") != "1.7.3"
        or importlib.metadata.version("websockets") != "15.0.1"
        or source is None
        or hashlib.sha256(Path(source).read_bytes()).hexdigest() != SDK_WS_SHA256
    ):
        raise PermissionError("P4_QUEUED_GATEWAY_SDK_SHAPE")


def handlers_installed(dispatcher: Any) -> bool:
    return (
        isinstance(dispatcher, lark.EventDispatcherHandler)
        and set(dispatcher._processorMap) == {"p2.im.message.receive_v1"}
        and set(dispatcher._callback_processor_map) == {"p2.card.action.trigger"}
    )


class QueuedReadyClient(SDKClient):  # type: ignore[misc]
    def __init__(
        self,
        *args: Any,
        persist_ready: Callable[[], None],
        persist_lost: Callable[[], None],
        **kwargs: Any,
    ):
        require_transport_shape()
        if kwargs.get("auto_reconnect") is not False or not handlers_installed(
            kwargs.get("event_handler")
        ):
            raise PermissionError("P4_QUEUED_GATEWAY_HANDLER")
        self._persist_ready, self._persist_lost = persist_ready, persist_lost
        self._ready_attempted = False
        self._ready_reported = False
        self._lost_reported = False
        super().__init__(*args, **kwargs)

    async def _connect(self) -> None:
        if self._ready_reported:
            raise PermissionError("P4_QUEUED_GATEWAY_NOT_READY")
        await super()._connect()
        receives = [
            task
            for task in asyncio.all_tasks()
            if not task.done()
            and inspect.iscoroutine(coro := task.get_coro())
            and coro.cr_code is SDKClient._receive_message_loop.__code__
            and coro.cr_frame is not None
            and coro.cr_frame.f_locals.get("self") is self
        ]
        if (
            self._ready_reported
            or self._conn is None
            or getattr(self._conn, "state", None) is not State.OPEN
            or not handlers_installed(self._event_handler)
            or len(receives) != 1
        ):
            raise PermissionError("P4_QUEUED_GATEWAY_NOT_READY")
        self._ready_attempted = True
        self._persist_ready()
        self._ready_reported = True

    async def _disconnect(self) -> None:
        try:
            if self._ready_attempted and not self._lost_reported:
                self._lost_reported = True
                self._persist_lost()
        finally:
            await super()._disconnect()
