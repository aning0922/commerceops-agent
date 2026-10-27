"""Woo 的只读来源注册解析；请求路径无 INSERT/UPDATE 或秘密注册行为。"""

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from psycopg import AsyncConnection

from commerceops.adapters.commerce.woocommerce_config import WooFilePins
from commerceops.adapters.commerce.woocommerce_http import invalid_constant, object_pairs
from commerceops.application.commerce.source_binding import (
    RegisteredWooSource,
    SourceBindingError,
    WooSourceMetadata,
)
from commerceops.infrastructure.web_config import private_bytes


@dataclass(frozen=True)
class CommerceSourceFiles:
    """部署方提供的只读指针及私有 pin 锚；不向客户端或 DB 导出。"""

    directory: Path = field(repr=False)
    bindings: Mapping[tuple[UUID, UUID], UUID] = field(repr=False)
    private_pin_digests: Mapping[str, str] = field(repr=False)

    def __post_init__(self) -> None:
        if not self.directory.is_absolute() or ".." in self.directory.parts:
            raise SourceBindingError()
        for scope, identifier in self.bindings.items():
            if len(scope) != 2 or not all(isinstance(x, UUID) for x in (*scope, identifier)):
                raise SourceBindingError()
        for reference, digest in self.private_pin_digests.items():
            if re.fullmatch(r"[A-Za-z0-9_-]{1,100}", reference) is None:
                raise SourceBindingError()
            if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise SourceBindingError()
        object.__setattr__(self, "bindings", MappingProxyType(dict(self.bindings)))
        object.__setattr__(
            self, "private_pin_digests", MappingProxyType(dict(self.private_pin_digests))
        )

    @classmethod
    def from_config(cls, body: Any) -> "CommerceSourceFiles":
        try:
            if type(body) is not dict or set(body) != {
                "directory",
                "bindings",
                "private_pin_digests",
            }:
                raise SourceBindingError()
            bindings = {}
            for item in body["bindings"]:
                if set(item) != {"organization_id", "shop_id", "binding_id"}:
                    raise SourceBindingError()
                scope = (UUID(item["organization_id"]), UUID(item["shop_id"]))
                if scope in bindings:
                    raise SourceBindingError()
                bindings[scope] = UUID(item["binding_id"])
            return cls(Path(body["directory"]), bindings, body["private_pin_digests"])
        except (ValueError, TypeError, KeyError, AttributeError):
            raise SourceBindingError() from None

    def metadata(self, registered: RegisteredWooSource) -> WooSourceMetadata:
        try:
            if (
                self.bindings.get((registered.organization_id, registered.shop_id))
                != registered.binding_id
            ):
                raise SourceBindingError()
            encoded = private_bytes(self.directory / f"{registered.binding_id}.json")
            json.loads(encoded, object_pairs_hook=object_pairs, parse_constant=invalid_constant)
            actual = WooSourceMetadata.model_validate_json(encoded)
            registered.verify(actual)
            if actual.anchor_day > datetime.now(UTC).astimezone(ZoneInfo(actual.timezone)).date():
                raise SourceBindingError()
            if actual.private_pin_ref not in self.private_pin_digests:
                raise SourceBindingError()
            return actual
        except (ValueError, TypeError, OSError):
            raise SourceBindingError() from None

    def credential_pins(
        self, registered: RegisteredWooSource, actual: WooSourceMetadata
    ) -> WooFilePins:
        """只供授权后的实际 factory；N01/capability 不调用此方法。"""
        try:
            registered.verify(actual)
            reference = actual.private_pin_ref
            encoded = private_bytes(self.directory / f"{reference}.pins.json")
            if not hmac.compare_digest(
                hashlib.sha256(encoded).hexdigest(), self.private_pin_digests[reference]
            ):
                raise SourceBindingError()
            body = json.loads(
                encoded, object_pairs_hook=object_pairs, parse_constant=invalid_constant
            )
            if set(body) != {
                "schema_version",
                "binding_id",
                "config_digest",
                "key",
                "secret",
                "ca",
            }:
                raise SourceBindingError()
            if (
                body["schema_version"] != "p5-private-pins-v1"
                or body["binding_id"] != str(registered.binding_id)
                or body["config_digest"] != registered.config_digest
            ):
                raise SourceBindingError()
            return WooFilePins(body["key"], body["secret"], body["ca"])
        except (ValueError, TypeError, OSError, KeyError):
            raise SourceBindingError() from None


SOURCE_SQL = """SELECT b.id AS binding_id,b.organization_id,b.shop_id,b.config_ref,
 b.source_config_version,b.config_digest,s.external_shop_key,s.currency,s.timezone
 FROM business.p5_commerce_source_bindings b JOIN business.shops s
 ON s.id=b.shop_id AND s.organization_id=b.organization_id AND s.config_ref=b.config_ref
 WHERE b.id=%s AND b.organization_id=%s AND b.shop_id=%s
 AND s.adapter_kind='woocommerce_test' AND s.environment='test'"""


def _pointer(
    files: CommerceSourceFiles | None,
    organization: UUID,
    shop: UUID,
    expected: UUID | None,
) -> UUID:
    if files is None:
        raise SourceBindingError()
    identifier = files.bindings.get((organization, shop))
    if identifier is None or (expected is not None and identifier != expected):
        raise SourceBindingError()
    return identifier


def _resolved(
    files: CommerceSourceFiles | None, row: Any, expected_version: str | None
) -> tuple[RegisteredWooSource, WooSourceMetadata]:
    if files is None or row is None:
        raise SourceBindingError()
    registered = RegisteredWooSource.model_validate(
        {key: row[key] for key in RegisteredWooSource.model_fields}
    )
    if expected_version is not None and registered.source_config_version != expected_version:
        raise SourceBindingError()
    actual = files.metadata(registered)
    if any(
        getattr(actual, key) != row[key] for key in ("external_shop_key", "currency", "timezone")
    ):
        raise SourceBindingError()
    return registered, actual


def resolve_woo_source(
    db: Any,
    files: CommerceSourceFiles | None,
    organization: UUID,
    shop: UUID,
    *,
    expected_version: str | None = None,
    expected_binding: UUID | None = None,
) -> tuple[RegisteredWooSource, WooSourceMetadata]:
    """每次解析当前店铺资格、登记记录和实际非秘密配置；不读 key/CA。"""
    identifier = _pointer(files, organization, shop, expected_binding)
    row = db.execute(SOURCE_SQL, (identifier, organization, shop)).fetchone()
    return _resolved(files, row, expected_version)


async def resolve_woo_source_async(
    db: AsyncConnection[dict[str, Any]],
    files: CommerceSourceFiles | None,
    organization: UUID,
    shop: UUID,
    *,
    expected_version: str,
    expected_binding: UUID | None = None,
) -> tuple[RegisteredWooSource, WooSourceMetadata]:
    identifier = _pointer(files, organization, shop, expected_binding)
    cursor = await db.execute(SOURCE_SQL, (identifier, organization, shop))
    return _resolved(files, await cursor.fetchone(), expected_version)
