"""独立日报私有配置读取；只核本次显式owned引用，不登记或修改来源。"""

import hashlib
import hmac
import json
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, TypeAdapter, field_validator, model_validator

from commerceops.adapters.commerce.woocommerce_config import WooFilePins, read_private_file
from commerceops.adapters.commerce.woocommerce_http import invalid_constant, object_pairs
from commerceops.application.commerce.contracts import Digest
from commerceops.application.daily.contracts import DailyDTO
from commerceops.application.daily.source import (
    DailyManifest,
    DailyMetadata,
    DailyUnsafe,
    MockMetadata,
    WooMetadata,
)


class ActiveBinding(DailyDTO):
    organization_id: UUID
    shop_id: UUID
    binding_id: UUID
    config_digest: Digest
    private_pin_digest: Digest | None


class DailyDeployment(DailyDTO):
    @field_validator(
        "model_requests_enabled",
        "external_sender_enabled",
        "schedules_enabled",
        "fake_delivery_enabled",
        mode="before",
    )
    @classmethod
    def strict_off(cls, value: object) -> object:
        if type(value) is not bool:
            raise ValueError("DAILY_BOOLEAN_INVALID")
        return value

    schema_version: Literal["p6-daily-deployment-v1"]
    directory: Path
    bindings: tuple[ActiveBinding, ...]
    model_requests_enabled: Literal[False]
    external_sender_enabled: Literal[False]
    schedules_enabled: bool = False
    fake_delivery_enabled: bool = False

    @model_validator(mode="after")
    def unique(self) -> "DailyDeployment":
        if (
            not self.directory.is_absolute()
            or ".." in self.directory.parts
            or (len({(b.organization_id, b.shop_id) for b in self.bindings}) != len(self.bindings))
        ):
            raise ValueError("DAILY_DEPLOYMENT_INVALID")
        return self

    @classmethod
    def load(cls, filename: Path) -> "DailyDeployment":
        try:
            raw = read_private_file(str(filename), 32768)
            checked_json(raw)
            return cls.model_validate_json(raw)
        except (ValueError, OSError):
            raise DailyUnsafe("DAILY_SOURCE_UNAVAILABLE") from None

    def active(self, org: UUID, shop: UUID) -> ActiveBinding:
        matches = [b for b in self.bindings if (b.organization_id, b.shop_id) == (org, shop)]
        if len(matches) != 1:
            raise DailyUnsafe("DAILY_SOURCE_BINDING_CHANGED")
        return matches[0]

    def metadata(self, binding: ActiveBinding) -> DailyMetadata:
        try:
            raw = read_private_file(str(self.directory / f"{binding.binding_id}.json"), 32768)
            checked_json(raw)
            actual: DailyMetadata = TypeAdapter(DailyMetadata).validate_json(raw)
            if (actual.organization_id, actual.shop_id, actual.config_digest) != (
                binding.organization_id,
                binding.shop_id,
                binding.config_digest,
            ):
                raise ValueError
            return actual
        except (OSError, ValueError):
            raise DailyUnsafe("DAILY_SOURCE_BINDING_CHANGED") from None

    def pins(self, binding: ActiveBinding, metadata: WooMetadata) -> WooFilePins:
        try:
            filename = self.directory / f"{metadata.private_pin_ref}.json"
            raw = read_private_file(str(filename), 32768)
            if binding.private_pin_digest is None or not hmac.compare_digest(
                hashlib.sha256(raw).hexdigest(), binding.private_pin_digest
            ):
                raise ValueError
            checked_json(raw)
            pin = PrivatePin.model_validate_json(raw)
            if (pin.binding_id, pin.source_config_version, pin.config_digest) != (
                binding.binding_id,
                metadata.source_config_version,
                metadata.config_digest,
            ):
                raise ValueError
            return WooFilePins(pin.consumer_key, pin.consumer_secret, pin.ca)
        except (OSError, ValueError):
            raise DailyUnsafe("DAILY_SOURCE_BINDING_CHANGED") from None


class PrivatePin(DailyDTO):
    binding_id: UUID
    source_config_version: str
    config_digest: Digest
    consumer_key: Digest = Field(repr=False)
    consumer_secret: Digest = Field(repr=False)
    ca: Digest = Field(repr=False)


def pinned_bytes(filename: str, digest: str, maximum: int) -> bytes:
    try:
        data = read_private_file(filename, maximum)
        if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), digest):
            raise ValueError
        return data
    except (OSError, ValueError):
        raise DailyUnsafe("DAILY_SOURCE_BINDING_CHANGED") from None


def manifest_for(metadata: DailyMetadata) -> DailyManifest:
    raw = pinned_bytes(metadata.manifest_ref, metadata.manifest_digest, 2097152)
    try:
        checked_json(raw)
        manifest = DailyManifest.model_validate_json(raw)
        if (
            manifest.organization_id,
            manifest.shop_id,
            manifest.source_config_version,
            manifest.earliest_business_day,
        ) != (
            metadata.organization_id,
            metadata.shop_id,
            metadata.source_config_version,
            metadata.earliest_business_day,
        ):
            raise ValueError
        if (
            isinstance(metadata, MockMetadata)
            and manifest.dataset_version != metadata.fixture_version
        ):
            raise ValueError
        return manifest
    except ValueError:
        raise DailyUnsafe("DAILY_SOURCE_BINDING_CHANGED") from None


def fixture_rows(metadata: DailyMetadata) -> tuple[list[dict[str, object]], dict[str, object]]:
    from commerceops.adapters.commerce.woocommerce_http import invalid_constant, object_pairs
    from commerceops.application.daily.source import MockMetadata

    if not isinstance(metadata, MockMetadata):
        raise DailyUnsafe("DAILY_SOURCE_UNAVAILABLE")
    try:
        raw = pinned_bytes(
            metadata.fixture_ref, metadata.fixture_digest, metadata.limits.max_snapshot_bytes
        )
        parsed = json.loads(raw, object_pairs_hook=object_pairs, parse_constant=invalid_constant)
        if type(parsed) is not dict or set(parsed) != {"orders", "refunds"}:
            raise ValueError
        if type(parsed["orders"]) is not list or type(parsed["refunds"]) is not dict:
            raise ValueError
        return parsed["orders"], parsed["refunds"]
    except DailyUnsafe:
        raise
    except (ValueError, KeyError, TypeError):
        raise DailyUnsafe("DAILY_SOURCE_UNAVAILABLE") from None


def checked_json(raw: bytes) -> None:
    json.loads(raw, object_pairs_hook=object_pairs, parse_constant=invalid_constant)
