"""Owned LAB only HTTP endpoint/WS transport. Original SDK parsing/handlers/SQL remain live."""

import asyncio
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from types import SimpleNamespace
from typing import Any


class OwnedPublicationError(RuntimeError):
    """Fixed owned transport diagnostic; never include input or upstream text."""

    def __init__(self, stage: str):
        super().__init__("OWNED_PUBLICATION_INVALID")
        self.stage = stage


def completed_owned_body(path: Path, *, publisher_sha256: str) -> bytes | None:
    """Read the existing exclusive-body/atomic-completion protocol for event/ACK files."""
    from scripts.p4_acceptance import bound_bytes

    stage = "completion"
    try:
        if re.fullmatch(r"[0-9a-f]{64}", publisher_sha256) is None:
            raise OwnedPublicationError(stage)
        parent = os.lstat(path.parent)
        if (
            not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != os.geteuid()
            or stat.S_IMODE(parent.st_mode) != 0o700
        ):
            raise OwnedPublicationError(stage)
        completion = path.with_name(".complete-" + path.name + ".json")
        try:
            os.lstat(completion)
        except FileNotFoundError:
            return None
        receipt_body = bound_bytes(completion, private=True)
        receipt = json.loads(receipt_body)
        if (
            type(receipt) is not dict
            or receipt.get("schema") != "owned-save-complete-v1"
            or receipt.get("publisher_sha256") != publisher_sha256
            or type(receipt.get("bytes")) is not int
        ):
            raise OwnedPublicationError(stage)
        stage = "body"
        body = bound_bytes(path, private=True)
        if (
            receipt["bytes"] != len(body)
            or receipt.get("sha256") != hashlib.sha256(body).hexdigest()
            or bound_bytes(completion, private=True) != receipt_body
        ):
            raise OwnedPublicationError(stage)
        stage = "json_object"
        if type(json.loads(body)) is not dict:
            raise OwnedPublicationError(stage)
        return body
    except OwnedPublicationError:
        raise
    except Exception:
        raise OwnedPublicationError(stage) from None


def install(directory: Path, *, publisher_sha256: str | None = None) -> None:
    import lark_oapi.ws.client as client  # type: ignore[import-untyped]
    from lark_oapi.ws.pb.pbbp2_pb2 import Frame  # type: ignore[import-untyped]
    from websockets.protocol import State

    counts = {"endpoint_HTTP": 0, "websocket_connect": 0, "frames_delivered": 0, "frames_sent": 0}
    consumed: set[Path] = set()
    publication_failure: OwnedPublicationError | None = None
    sequence = 0

    def record(*, failure: OwnedPublicationError | None = None) -> None:
        nonlocal sequence
        sequence += 1
        path = directory / (f"transport-{os.getpid()}-{sequence:04}.safe.json")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            value: dict[str, Any] = {**counts, "external_network_calls": 0}
            if failure is not None:
                value["publication_failure"] = {
                    "code": "OWNED_PUBLICATION_INVALID",
                    "error_class": "OwnedPublicationError",
                    "stage": failure.stage,
                }
            json.dump(value, stream)

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
            nonlocal publication_failure
            while True:
                if publication_failure is not None:
                    raise publication_failure
                if (directory / "lost.request").exists():
                    self.state = State.CLOSED
                    raise ConnectionError("LAB_TRANSPORT_LOST")
                pending = sorted(set(directory.glob("event-*.json")) - consumed)
                if pending:
                    path = pending[0]
                    try:
                        body = (
                            completed_owned_body(path, publisher_sha256=publisher_sha256)
                            if publisher_sha256 is not None
                            else path.read_bytes()
                        )
                    except OwnedPublicationError as error:
                        publication_failure = error
                        self.state = State.CLOSED
                        record(failure=error)
                        raise
                    if body is None:
                        await asyncio.sleep(0.02)
                        continue
                    consumed.add(path)
                    frame = Frame(SeqID=1, LogID=1, service=1, method=1, payload=body)
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
