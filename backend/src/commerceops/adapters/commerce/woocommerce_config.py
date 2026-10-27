"""首批本地 Woo HTTPS 只读配置；秘密只从本次显式私有文件读取。"""

import hashlib
import hmac
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from commerceops.application.commerce.contracts import Currency, Identifier, Timezone, Window


class WooReadOnlyConfig(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    base_url: str
    consumer_key_file: str = Field(repr=False)
    consumer_secret_file: str = Field(repr=False)
    ca_file: str
    shop_id: Identifier
    timezone: Timezone
    currency: Currency
    window: Window
    per_page: int = Field(default=50, ge=1, le=100)
    max_pages: int = Field(default=100, ge=1, le=200)
    max_requests: int = Field(default=1000, ge=1, le=2000)
    timeout_seconds: int = Field(default=10, ge=1, le=30)
    max_elapsed_seconds: int = Field(default=180, ge=1, le=600)
    max_response_bytes: int = Field(default=2097152, ge=128, le=8388608)
    max_retries: int = Field(default=0, ge=0, le=1)

    @model_validator(mode="after")
    def local_origin(self) -> Self:
        url = urlsplit(self.base_url)
        if (
            url.scheme != "https"
            or url.hostname not in {"localhost", "127.0.0.1", "::1"}
            or url.username is not None
            or url.password is not None
            or url.path not in {"", "/"}
            or url.query
            or url.fragment
            or url.port is None
        ):
            raise ValueError("INVALID_LOCAL_HTTPS_ORIGIN")
        paths = (self.consumer_key_file, self.consumer_secret_file, self.ca_file)
        if any(not Path(p).is_absolute() for p in paths) or len(set(paths)) != 3:
            raise ValueError("EXPLICIT_DISTINCT_ABSOLUTE_FILES_REQUIRED")
        return self


def read_private_file(filename: str, maximum: int) -> bytes:
    """在同一目录/文件描述符核身份权限并有界读取，拒绝symlink和TOCTOU换文件。"""
    path = Path(filename)
    if not path.is_absolute():
        raise ValueError("ABSOLUTE_PRIVATE_FILE_REQUIRED")
    parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parent = os.fstat(parent_fd)
        if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
            raise ValueError("CREDENTIAL_DIRECTORY_UNSAFE")
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd)
    finally:
        os.close(parent_fd)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_size > maximum
        ):
            raise ValueError("CREDENTIAL_FILE_UNSAFE")
        raw = bytearray()
        while len(raw) <= maximum:
            chunk = os.read(fd, min(16384, maximum + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        if len(raw) > maximum:
            raise ValueError("PRIVATE_FILE_CAPACITY")
        return bytes(raw)
    finally:
        os.close(fd)


def read_credential(filename: str, prefix: str) -> str:
    return credential_value(read_private_file(filename, 128), prefix)


def credential_value(encoded: bytes, prefix: str) -> str:
    raw = encoded.decode("ascii").removesuffix("\n")
    if re.fullmatch(prefix + r"_[0-9a-f]{40}", raw) is None:
        raise ValueError("CREDENTIAL_FORMAT_INVALID")
    return raw


@dataclass(frozen=True)
class WooFilePins:
    """只存在可信私有配置/内存；不进入来源 DTO、DB 或诊断输出。"""

    consumer_key: str = field(repr=False)
    consumer_secret: str = field(repr=False)
    ca: str = field(repr=False)

    def __post_init__(self) -> None:
        if any(
            re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in (self.consumer_key, self.consumer_secret, self.ca)
        ):
            raise ValueError("INVALID_PRIVATE_CREDENTIAL_PIN")

    @staticmethod
    def read(filename: str, maximum: int, expected: str) -> bytes:
        # Compare the same FD-read bytes later used for TLS/auth, without reopening.
        data = read_private_file(filename, maximum)
        if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), expected):
            raise ValueError("PRIVATE_CREDENTIAL_PIN_MISMATCH")
        return data
