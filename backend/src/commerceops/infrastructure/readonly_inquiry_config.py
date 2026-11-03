"""Explicit local inquiry deployment; no implicit fixtures, provider, or credentials."""

from pathlib import Path
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from commerceops.infrastructure.readonly_inquiry_store import InquiryConfig
from commerceops.infrastructure.web_config import private_bytes


class InquiryDeployment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["p6-inquiry-deployment-v1"]
    shop_id: UUID
    fixture_directory: Path
    fixture_case: Literal["baseline"] = "baseline"
    enabled: bool = False
    source_kind: Literal["mock"] = "mock"
    model_mode: Literal["offline_stub"] = "offline_stub"
    model_requests_enabled: Literal[False] = False
    external_sender_enabled: Literal[False] = False

    @model_validator(mode="before")
    @classmethod
    def boolean_flags(cls, value: Any) -> Any:
        if isinstance(value, dict):
            for name in ("enabled", "model_requests_enabled", "external_sender_enabled"):
                if name in value and type(value[name]) is not bool:
                    raise ValueError("INVALID_INQUIRY_DEPLOYMENT")
        return value

    @model_validator(mode="after")
    def explicit_directory(self) -> Self:
        if not self.fixture_directory.is_absolute() or ".." in self.fixture_directory.parts:
            raise ValueError("INVALID_INQUIRY_DEPLOYMENT")
        return self

    @classmethod
    def load(cls, path: Path) -> "InquiryDeployment":
        # Existing bounded no-follow private config reader; never loads a fixture on import.
        try:
            return cls.model_validate_json(private_bytes(path))
        except (OSError, ValueError):
            raise ValueError("INVALID_INQUIRY_DEPLOYMENT") from None

    def runtime(self) -> InquiryConfig:
        value = self.model_validate_json(self.model_dump_json())
        return InquiryConfig(
            shop_id=value.shop_id,
            fixture_directory=value.fixture_directory,
            fixture_case=value.fixture_case,
            enabled=value.enabled,
        )
