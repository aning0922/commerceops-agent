"""显式测试资源配置；不自动加载 dotenv，不输出验证输入/凭据。"""

from pathlib import Path
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from commerceops.adapters.feishu.contracts import ProbePolicy
from commerceops.infrastructure.database import DatabaseSettings


class FeishuProbeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COMMERCEOPS_FEISHU_", extra="ignore")

    app_id: str = Field(min_length=1)
    tenant_key: str = Field(min_length=1)
    bot_open_id: str = Field(min_length=1)
    allowed_open_ids: frozenset[str]
    allowed_group_chat_ids: frozenset[str]
    organization_id: UUID
    shop_id: UUID
    app_secret_file: Path | None = None
    base_app_token: str | None = None
    base_table_id: str | None = None
    external_ready: bool = False

    def policy(self) -> ProbePolicy:
        return ProbePolicy(
            self.app_id,
            self.tenant_key,
            self.bot_open_id,
            self.allowed_open_ids,
            self.allowed_group_chat_ids,
        )

    def secret(self) -> SecretStr:
        if self.app_secret_file is None:
            raise ValueError("missing secret file")
        value = self.app_secret_file.read_text().strip()
        if not value:
            raise ValueError("empty secret file")
        return SecretStr(value)


def runtime_pool(settings: DatabaseSettings) -> ConnectionPool[Connection[dict[str, Any]]]:
    if settings.user != "commerceops_app":
        raise ValueError("probe requires restricted runtime role")
    kwargs = settings.kwargs()
    kwargs.update(
        row_factory=dict_row,
        options="-c statement_timeout=650ms -c lock_timeout=350ms -c transaction_timeout=1500ms",
    )
    # 连接建立在 Gateway 建连前完成；callback checkout 限 200ms，不等待新建连接。
    pool: ConnectionPool[Connection[dict[str, Any]]] = ConnectionPool(
        kwargs=kwargs, min_size=1, max_size=2, max_waiting=4, timeout=0.2, open=False
    )
    pool.open(wait=True, timeout=10)
    return pool
