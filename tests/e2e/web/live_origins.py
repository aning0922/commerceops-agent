"""B02专用登记端点校验；不启动资源、不接受默认旧端口。"""

import json
from pathlib import Path
from urllib.parse import urlsplit

from commerceops.infrastructure.web_config import private_bytes


def owned_origin(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid owned local origin")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError("invalid owned local origin") from None
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or port is None
        or not 1 <= port <= 65535
        or port == 80
        or value != f"http://127.0.0.1:{port}"
    ):
        raise ValueError("invalid owned local origin")
    return value


def registered_origins(directory: Path) -> tuple[str, str]:
    value = json.loads(private_bytes(directory / "window.json"))
    if not isinstance(value, dict):
        raise ValueError("invalid owned registration")
    return owned_origin(value.get("web_origin")), owned_origin(value.get("api_origin"))
