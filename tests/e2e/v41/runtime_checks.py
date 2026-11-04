"""Read-only ownership predicates and startup refusal; no listener adoption or stop."""

import socket
from pathlib import Path
from typing import Any

ENV_FILES = (".env", ".env.local", ".env.development", ".env.development.local")


def reject_implicit_env(root: Path) -> None:
    if any(
        (directory / name).exists() or (directory / name).is_symlink()
        for directory in (root, root / "frontend")
        for name in ENV_FILES
    ):
        raise ValueError("IMPLICIT_ENV_FILE_REFUSED")


def reserve_ports(api: int, web: int) -> None:
    sockets: list[socket.socket] = []
    try:
        for port in (api, web):
            item = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sockets.append(item)
            item.bind(("127.0.0.1", port))
    finally:
        for item in sockets:
            item.close()


def verify_api_record(
    record: dict[str, Any], project: str, image: str, uid: int, port: int, directory: Path
) -> None:
    if (
        not record.get("running")
        or record.get("project") != project
        or record.get("service") != "v4-api"
        or record.get("image") != image
        or record.get("user") != str(uid)
    ):
        raise ValueError("API_CONTAINER_OWNERSHIP_UNPROVEN")
    if record.get("ports") != {f"{port}/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(port)}]}:
        raise ValueError("API_PUBLISHED_LOOPBACK_BINDING_UNPROVEN")
    mounts = record.get("mounts")
    if (
        not isinstance(mounts, list)
        or len(mounts) != 1
        or mounts[0].get("Destination") != "/run/v4_api"
        or mounts[0].get("Source") != str(directory / "api")
        or mounts[0].get("RW") is not False
    ):
        raise ValueError("API_RUNTIME_ONLY_MOUNT_UNPROVEN")


def verify_web_listener(listeners: list[dict[str, Any]], group: int, port: int) -> None:
    if not listeners or any(
        r.get("pgid") != group or r.get("endpoint") != f"127.0.0.1:{port}" for r in listeners
    ):
        raise ValueError("WEB_OWNED_LISTENER_UNPROVEN")


def verify_host_binding(
    receipt: dict[str, Any], context: str, endpoint: str, server: str, binary_digest: str
) -> None:
    if (
        not endpoint.startswith("unix:///")
        or receipt.get("docker_context") != context
        or receipt.get("docker_endpoint") != endpoint
        or receipt.get("docker_server_id") != server
        or receipt.get("docker_binary_sha256") != binary_digest
    ):
        raise ValueError("ROOT_LOCAL_DOCKER_BINDING_UNPROVEN")
