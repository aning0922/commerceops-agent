"""P3显式私有配置；不加载.env、平台凭据或开发身份替身。"""

import json
import os
import stat
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from commerceops.infrastructure.database import DatabaseSettings


def private_bytes(path: Path) -> bytes:
    # 原私配助手强化为逐级dir_fd读取；不创建/resolve/chmod未知路径。
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("INVALID_WEB_CONFIGURATION")
    with ExitStack() as stack:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        current = os.open(path.anchor, flags)
        stack.callback(os.close, current)
        for name in path.parts[1:-1]:
            current = os.open(name, flags, dir_fd=current)
            stack.callback(os.close, current)
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=current)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
                raise ValueError("INVALID_WEB_CONFIGURATION")
            if info.st_uid != os.geteuid():
                raise ValueError("INVALID_WEB_CONFIGURATION")
            body = stream.read(32769)
        if len(body) > 32768:
            raise ValueError("INVALID_WEB_CONFIGURATION")
        return body


@dataclass(frozen=True)
class WebConfig:
    database: DatabaseSettings = field(repr=False)
    csrf_secret: bytes = field(repr=False)
    nonce_secret: bytes = field(repr=False)
    origins: tuple[str, ...]
    transport_mode: str = "https"
    config_version: str = "p3-config-v1"
    key_version: str = "p3-key-v1"
    approval_ttl_seconds: int = 86400
    revalidation_max_age_seconds: int = 900
    max_plan_items: int = 20
    recovery_scan_seconds: int = 30
    session_absolute_seconds: int = 28800
    session_idle_seconds: int = 1800
    login_window_seconds: int = 300
    login_account_limit: int = 5
    login_peer_limit: int = 30

    def __post_init__(self) -> None:
        if len(self.csrf_secret) < 32 or len(self.nonce_secret) < 32:
            raise ValueError("INVALID_WEB_CONFIGURATION")
        if self.csrf_secret == self.nonce_secret or self.transport_mode not in (
            "https",
            "local_http",
        ):
            raise ValueError("INVALID_WEB_CONFIGURATION")
        if not self.origins or not self.config_version or not self.key_version:
            raise ValueError("INVALID_WEB_CONFIGURATION")
        for origin in self.origins:
            if type(origin) is not str or "*" in origin:
                raise ValueError("INVALID_WEB_CONFIGURATION")
            parsed = urlsplit(origin)
            _ = parsed.port
            if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
                raise ValueError("INVALID_WEB_CONFIGURATION")
            if not parsed.hostname or origin != f"{parsed.scheme}://{parsed.netloc}":
                raise ValueError("INVALID_WEB_CONFIGURATION")
            if self.transport_mode == "https" and parsed.scheme != "https":
                raise ValueError("INVALID_WEB_CONFIGURATION")
            if self.transport_mode == "local_http" and (
                parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1")
            ):
                raise ValueError("INVALID_WEB_CONFIGURATION")
        bounds = (
            (self.approval_ttl_seconds, 60, 604800),
            (self.revalidation_max_age_seconds, 1, 3600),
            (self.max_plan_items, 1, 20),
            (self.recovery_scan_seconds, 1, 30),
            (self.session_absolute_seconds, 60, 86400),
            (self.session_idle_seconds, 1, self.session_absolute_seconds),
            (self.login_window_seconds, 1, 300),
            (self.login_account_limit, 1, 5),
            (self.login_peer_limit, 1, 30),
        )
        if any(type(value) is not int or not low <= value <= high for value, low, high in bounds):
            raise ValueError("INVALID_WEB_CONFIGURATION")

    @classmethod
    def from_file(cls, path: Path) -> "WebConfig":
        try:
            body = json.loads(private_bytes(path))
            database = DatabaseSettings.model_validate(body.pop("database"))
            csrf = private_bytes(Path(body.pop("csrf_secret_file")))
            nonce = private_bytes(Path(body.pop("nonce_secret_file")))
            body["origins"] = tuple(body["origins"])
            return cls(database=database, csrf_secret=csrf, nonce_secret=nonce, **body)
        except Exception:
            raise ValueError("INVALID_WEB_CONFIGURATION") from None
