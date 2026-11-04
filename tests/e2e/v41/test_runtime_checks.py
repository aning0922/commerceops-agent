"""Pure refusal control flow only; no sockets bound, Docker invoked or HTTP requested."""

import socket
from pathlib import Path
from typing import Any

import pytest
from pytest import MonkeyPatch

from . import runtime_checks as checks

pytestmark = pytest.mark.offline


def test_env_is_refused_without_reading_it(tmp_path: Path) -> None:
    (tmp_path / "frontend").mkdir()
    checks.reject_implicit_env(tmp_path)
    (tmp_path / "frontend/.env.local").write_text("unread fixture")
    with pytest.raises(ValueError, match="ENV_FILE"):
        checks.reject_implicit_env(tmp_path)


def test_failed_bind_closes_both_and_never_probes_listener(monkeypatch: MonkeyPatch) -> None:
    closed = []

    class Socket:
        def bind(self, address: tuple[str, int]) -> None:
            if address[1] == 18002:
                raise OSError("occupied simulation")

        def close(self) -> None:
            closed.append(self)

    monkeypatch.setattr(socket, "socket", lambda *a: Socket())
    with pytest.raises(OSError):
        checks.reserve_ports(18001, 18002)
    assert len(closed) == 2


def test_running_container_or_old_listener_is_not_enough(tmp_path: Path) -> None:
    record = {
        "running": True,
        "project": "new",
        "service": "v4-api",
        "image": "image",
        "user": "501",
        "ports": {"18001/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18001"}]},
        "mounts": [{"Destination": "/run/v4_api", "Source": str(tmp_path / "api"), "RW": False}],
    }
    checks.verify_api_record(record, "new", "image", 501, 18001, tmp_path)
    changes: list[dict[str, Any]] = [
        {"project": "old"},
        {"image": "old"},
        {"ports": {}},
        {"mounts": []},
    ]
    for change in changes:
        with pytest.raises(ValueError):
            checks.verify_api_record({**record, **change}, "new", "image", 501, 18001, tmp_path)
    checks.verify_web_listener([{"pgid": 100, "endpoint": "127.0.0.1:18002"}], 100, 18002)
    with pytest.raises(ValueError):
        checks.verify_web_listener([{"pgid": 200, "endpoint": "127.0.0.1:18002"}], 100, 18002)


def test_unbound_or_remote_docker_context_never_accepts() -> None:
    receipt = {
        "docker_context": "local",
        "docker_endpoint": "unix:///local/socket",
        "docker_server_id": "new-server",
        "docker_binary_sha256": "public-tool-hash",
    }
    checks.verify_host_binding(
        receipt, "local", "unix:///local/socket", "new-server", "public-tool-hash"
    )
    with pytest.raises(ValueError):
        checks.verify_host_binding(
            receipt, "old", "unix:///local/socket", "new-server", "public-tool-hash"
        )
    with pytest.raises(ValueError):
        checks.verify_host_binding(
            receipt, "local", "tcp://remote", "new-server", "public-tool-hash"
        )
