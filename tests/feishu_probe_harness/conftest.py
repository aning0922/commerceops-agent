"""本目录回归禁止任何真实网络或子进程。"""

import socket
import subprocess
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def no_resources(monkeypatch: Any) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("REAL_RESOURCE_FORBIDDEN")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
