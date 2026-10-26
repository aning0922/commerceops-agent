"""显式连接配置，不加载 .env，不把 DSN/错误原文写入日志。"""

import os
import stat
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import NullPool


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COMMERCEOPS_DB_", extra="ignore")

    host: str = Field(min_length=1)
    port: int = Field(default=5432, ge=1, le=65535)
    name: str = Field(min_length=1)
    user: str = Field(min_length=1)
    password_file: Path
    runtime_password_file: Path | None = None

    def password(self) -> SecretStr:
        value = self.password_file.read_text().strip()
        if not value:
            raise ValueError("empty password file")
        return SecretStr(value)

    def bounded_password(self) -> SecretStr:
        """Bound the trusted PG secret read without importing Woo ownership policy.

        Compose bind secrets retain the host UID on Linux. The existing PG contract
        trusts the configured file and kernel read permission, not equality with
        the container UID. Never chmod/chown a mount or reuse this for Woo pins.
        """
        path = self.password_file
        if not path.is_absolute() or ".." in path.parts:
            raise ValueError("INVALID_DATABASE_PASSWORD_FILE")
        with ExitStack() as stack:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            current = os.open(path.anchor, flags)
            stack.callback(os.close, current)
            for name in path.parts[1:-1]:
                current = os.open(name, flags, dir_fd=current)
                stack.callback(os.close, current)
            descriptor = os.open(
                path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=current
            )
            with os.fdopen(descriptor, "rb") as stream:
                info = os.fstat(stream.fileno())
                if (
                    not stat.S_ISREG(info.st_mode)
                    or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_size > 32768
                ):
                    raise ValueError("INVALID_DATABASE_PASSWORD_FILE")
                raw = stream.read(32769)
            if len(raw) > 32768:
                raise ValueError("INVALID_DATABASE_PASSWORD_FILE")
        try:
            value = raw.decode().strip()
        except UnicodeError:
            raise ValueError("INVALID_DATABASE_PASSWORD_FILE") from None
        if not value:
            raise ValueError("INVALID_DATABASE_PASSWORD_FILE")
        return SecretStr(value)

    def kwargs(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.name,
            "user": self.user,
            "password": self.password().get_secret_value(),
            "connect_timeout": 5,
        }


def connect(settings: DatabaseSettings) -> psycopg.Connection[dict[str, Any]]:
    """调用者拥有事务；上下文成功提交，异常回滚，不自动重试。"""
    return psycopg.connect(**settings.kwargs(), row_factory=dict_row)


def migration_engine(settings: DatabaseSettings) -> Engine:
    return create_engine(
        "postgresql+psycopg://",
        creator=lambda: psycopg.connect(**settings.kwargs()),
        poolclass=NullPool,
        hide_parameters=True,
    )
