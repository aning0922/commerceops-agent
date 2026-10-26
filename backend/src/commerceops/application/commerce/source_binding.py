"""M2 非秘密来源合同；登记值与运行配置比较，不执行网络或登记写入。"""

from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Literal, Self
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from commerceops.application.commerce.contracts import (
    Currency,
    Digest,
    Identifier,
    Timezone,
    Window,
)
from commerceops.domain.commerce_values import complete_days, facts_hash


class SourceBindingError(ValueError):
    def __init__(self) -> None:
        super().__init__("COMMERCE_SOURCE_UNAVAILABLE")


class WooSourceMetadata(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    schema_version: Literal["p5-woo-source-v1"] = "p5-woo-source-v1"
    organization_id: UUID
    shop_id: UUID
    config_ref: Identifier
    source_config_version: Identifier
    adapter_kind: Literal["woocommerce_test"] = "woocommerce_test"
    environment: Literal["test"] = "test"
    origin: str
    external_shop_key: Identifier
    currency: Currency
    timezone: Timezone
    profile: Literal["mixed-v1", "positive-v1"]
    anchor_day: date
    consumer_key_file: str = Field(repr=False)
    consumer_secret_file: str = Field(repr=False)
    ca_file: str = Field(repr=False)
    private_pin_ref: Identifier
    per_page: int = Field(default=2, ge=1, le=100)
    max_pages: int = Field(default=32, ge=1, le=200)
    max_requests: int = Field(default=256, ge=1, le=2000)
    timeout_seconds: int = Field(default=10, ge=1, le=18)
    max_elapsed_seconds: int = Field(default=18, ge=1, le=18)
    max_response_bytes: int = Field(default=2097152, ge=128, le=8388608)
    max_retries: Literal[0] = 0

    @model_validator(mode="after")
    def safe_metadata(self) -> Self:
        from urllib.parse import urlsplit

        url = urlsplit(self.origin)
        if (
            url.scheme != "https"
            or url.hostname not in {"localhost", "127.0.0.1", "::1"}
            or url.username is not None
            or url.password is not None
            or url.path
            or url.query
            or url.fragment
            or url.port is None
        ):
            raise SourceBindingError()
        files = (self.consumer_key_file, self.consumer_secret_file, self.ca_file)
        if len(set(files)) != 3 or any(
            not Path(p).is_absolute() or ".." in Path(p).parts for p in files
        ):
            raise SourceBindingError()
        return self

    @property
    def business_now(self) -> datetime:
        return datetime.combine(self.anchor_day, time.min, ZoneInfo(self.timezone)).astimezone(UTC)

    @property
    def window(self) -> Window:
        start, end = complete_days(self.business_now, self.timezone)
        return Window(start=start, end=end)

    @property
    def config_digest(self) -> str:
        return facts_hash(self.model_dump(mode="json"))


class RegisteredWooSource(BaseModel):
    """Owner 登记后不可变；应用 runtime 只有 SELECT 权限。"""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    binding_id: UUID
    organization_id: UUID
    shop_id: UUID
    config_ref: Identifier
    source_config_version: Identifier
    config_digest: Digest

    def verify(self, actual: WooSourceMetadata) -> None:
        if (
            any(
                getattr(self, key) != getattr(actual, key)
                for key in ("organization_id", "shop_id", "config_ref", "source_config_version")
            )
            or self.config_digest != actual.config_digest
        ):
            raise SourceBindingError()


class CommerceSourceCapability(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    schema_version: Literal["p5-commerce-source-v1"] = "p5-commerce-source-v1"
    source_kind: Literal["mock", "woocommerce_test"]
    source_config_version: Identifier | None
    creation_enabled: bool

    @model_validator(mode="after")
    def valid_version(self) -> Self:
        if self.source_kind == "mock" and self.source_config_version is not None:
            raise SourceBindingError()
        if self.source_kind == "woocommerce_test" and self.creation_enabled:
            if self.source_config_version is None:
                raise SourceBindingError()
        return self
