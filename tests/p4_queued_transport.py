"""Owned LAB only HTTP endpoint/WS transport. Original SDK parsing/handlers/SQL remain live."""

import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def install(directory: Path) -> None:
    import lark_oapi.ws.client as client  # type: ignore[import-untyped]
    from lark_oapi.ws.pb.pbbp2_pb2 import Frame  # type: ignore[import-untyped]
    from websockets.protocol import State

    counts = {"endpoint_HTTP": 0, "websocket_connect": 0, "frames_delivered": 0, "frames_sent": 0}
    consumed: set[Path] = set()
    sequence = 0

    def record() -> None:
        nonlocal sequence
        sequence += 1
        path = directory / (f"transport-{os.getpid()}-{sequence:04}.safe.json")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump({**counts, "external_network_calls": 0}, stream)

    def endpoint(url: str, **kwargs: Any) -> Any:
        if not url.endswith("/callback/ws/endpoint"):
            raise AssertionError("LAB_ENDPOINT_ONLY")
        counts["endpoint_HTTP"] += 1
        record()
        if (directory / "handshake-failure.request").exists():
            return SimpleNamespace(status_code=403, content=b'{"code":403}')
        body = {
            "code": 0,
            "data": {"URL": "wss://offline.invalid/ws?device_id=offline&service_id=1"},
        }
        return SimpleNamespace(status_code=200, content=json.dumps(body).encode())

    class Socket:
        state = State.OPEN

        async def recv(self) -> bytes:
            while True:
                if (directory / "lost.request").exists():
                    self.state = State.CLOSED
                    raise ConnectionError("LAB_TRANSPORT_LOST")
                pending = sorted(set(directory.glob("event-*.json")) - consumed)
                if pending:
                    path = pending[0]
                    consumed.add(path)
                    frame = Frame(SeqID=1, LogID=1, service=1, method=1, payload=path.read_bytes())
                    for key, value in {
                        "type": "event",
                        "message_id": path.stem,
                        "trace_id": "offline",
                        "sum": "1",
                        "seq": "0",
                    }.items():
                        header = frame.headers.add()
                        header.key, header.value = key, value
                    counts["frames_delivered"] += 1
                    record()
                    return frame.SerializeToString()  # type: ignore[no-any-return]
                await asyncio.sleep(0.02)

        async def send(self, value: bytes) -> None:
            counts["frames_sent"] += 1
            record()

        async def close(self) -> None:
            self.state = State.CLOSED

    async def connect(*args: Any, **kwargs: Any) -> Socket:
        counts["websocket_connect"] += 1
        record()
        return Socket()

    client.requests.post = endpoint
    client.websockets.connect = connect
