"""Explicit non-secret synthetic query pins. No env, database, provider or HTTP reads."""

import hashlib
import hmac
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from commerceops.application.commerce.contracts import Digest, Identifier
from commerceops.application.knowledge_copy.contracts import Query, checked, digest
from commerceops.application.knowledge_copy.http_models import CopyWebDTO
from commerceops.infrastructure.daily_sources import checked_json
from commerceops.infrastructure.knowledge_copy_values import pg_profile, query_parameter
from commerceops.infrastructure.web_config import private_bytes


class CopyQueryBinding(CopyWebDTO):
    organization_id: UUID
    shop_id: UUID
    query_ref: Identifier
    query_version: Identifier
    query: Query
    binding_digest: Digest

    @model_validator(mode="after")
    def pinned(self) -> Self:
        if not self.query_ref.endswith("@" + self.query_version):
            raise ValueError("COPY_QUERY_VERSION_REQUIRED")
        if digest(self.payload("binding_digest")) != self.binding_digest:
            raise ValueError("COPY_QUERY_BINDING_INVALID")
        query_parameter(
            self.query, pg_profile(self.query.profile.profile_digest, self.query.profile.dimension)
        )  # Reject values outside the real PG float4 policy now.
        return self


class CopyDeployment(CopyWebDTO):
    schema_version: Literal["p6-copy-query-config-v1"]
    enabled: bool = False
    bindings: tuple[CopyQueryBinding, ...] = Field(max_length=100)
    provider_enabled: Literal[False]
    model_requests_enabled: Literal[False]
    publication_allowed: Literal[False]
    config_digest: Digest

    @model_validator(mode="after")
    def pinned(self) -> Self:
        keys = [(b.organization_id, b.shop_id, b.query_ref) for b in self.bindings]
        if (
            len(set(keys)) != len(keys)
            or self.enabled != bool(self.bindings)
            or digest(self.payload("config_digest")) != self.config_digest
        ):
            raise ValueError("COPY_QUERY_CONFIGURATION_INVALID")
        return self

    def queries(self) -> Mapping[tuple[UUID, UUID, str], Query]:
        value = checked(self)
        if not value.enabled:
            raise ValueError("COPY_QUERY_CONFIGURATION_DISABLED")
        return MappingProxyType(
            {(b.organization_id, b.shop_id, b.query_ref): b.query for b in value.bindings}
        )


def load_copy_deployment(
    filename: Path | None = None, *, enabled: bool = False, expected_sha256: str | None = None
) -> CopyDeployment | None:
    """Default off reads nothing. Enabled requires an absolute NoFollow 0600 file and raw pin."""
    if type(enabled) is not bool:
        raise ValueError("COPY_QUERY_CONFIGURATION_INVALID")
    if not enabled:
        return None
    try:
        if not isinstance(filename, Path) or type(expected_sha256) is not str:
            raise ValueError
        if len(expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_sha256):
            raise ValueError
        raw = private_bytes(filename)
        if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), expected_sha256):
            raise ValueError
        checked_json(raw)  # Duplicate keys, nonfinite JSON and malformed UTF-8 are rejected.
        value = CopyDeployment.model_validate_json(raw)
        if not value.enabled:
            raise ValueError
        return value
    except (ValueError, TypeError, OSError, RecursionError, UnicodeError):
        raise ValueError("COPY_QUERY_CONFIGURATION_INVALID") from None
