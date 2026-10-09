"""显式连接配置，不加载 .env，不把 DSN/错误原文写入日志。"""

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
