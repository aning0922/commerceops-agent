"""P4本地配置结构核实：不加载.env、不读取秘密、不构建SDK或访问PG。"""

import os
import stat
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from commerceops.adapters.feishu.contracts import ProbePolicy


class BusinessSettings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)

    schema_version: Literal["p4-v1"]
    organization_id: UUID
    shop_id: UUID
    app_id: str = Field(min_length=1, max_length=256, repr=False)
    tenant_key: str = Field(min_length=1, max_length=256, repr=False)
    bot_open_id: str = Field(min_length=1, max_length=256, repr=False)
    allowed_open_ids: frozenset[str] = Field(min_length=1, max_length=5, repr=False)
    allowed_group_chat_ids: frozenset[str] = Field(max_length=1, repr=False)
    app_secret_file: Path = Field(repr=False)
    web_config_file: Path = Field(repr=False)
    base_target_key: str = Field(min_length=1, max_length=100)
    base_app_token_file: Path = Field(repr=False)
    base_table_id_file: Path | None = Field(default=None, repr=False)
    base_table_name: str | None = Field(default=None, min_length=1, max_length=100, repr=False)
    external_sender_enabled: Literal[False] = False
    f02_enabled: bool = False

    @model_validator(mode="after")
    def verify_structure(self) -> "BusinessSettings":
        self.policy()
        if self.base_table_id_file is None and self.base_table_name is None:
            raise ValueError("INVALID_P4_CONFIGURATION")
        for value in (
            self.app_secret_file,
            self.web_config_file,
            self.base_app_token_file,
            self.base_table_id_file,
        ):
            if value is not None and (not value.is_absolute() or ".." in value.parts):
                raise ValueError("INVALID_P4_CONFIGURATION")
        return self

    def policy(self) -> ProbePolicy:
        return ProbePolicy(
            self.app_id,
            self.tenant_key,
            self.bot_open_id,
            self.allowed_open_ids,
            self.allowed_group_chat_ids,
        )


def verify_config(path: Path) -> dict[str, str | int | bool]:
    # 只读调用者明确选择的无密钥配置；不存在自动寻找旧runtime或env的路径。
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("INVALID_P4_CONFIGURATION")
            body = stream.read(32769)
        if len(body) > 32768:
            raise ValueError("INVALID_P4_CONFIGURATION")
        settings = BusinessSettings.model_validate_json(body)
    except Exception:
        raise ValueError("INVALID_P4_CONFIGURATION") from None
    return {
        "schema_version": "p4-v1",
        "structure_valid": True,
        "secret_contents_read": False,
        "sdk_constructed": False,
        "pg_connected": False,
        "external_sender_enabled": False,
        "allowed_user_count": len(settings.allowed_open_ids),
        "allowed_group_count": len(settings.allowed_group_chat_ids),
        "platform_resources_verified": False,
    }
