"""M3独立来源注册/manifest/任务合同；不读取秘密、不执行I/O。"""

from datetime import date
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from commerceops.application.commerce.contracts import Currency, Digest, Identifier, Timezone
from commerceops.application.daily.contracts import DailyDTO, DailyRuleConfig, DailySource
from commerceops.domain.commerce_values import facts_hash

WORKFLOW = "p6-daily-report-v1"
KIND = "daily_report"


class DailyUnsafe(ValueError):
    def __init__(self, code: str = "DAILY_WORKFLOW_UNSAFE"):
        self.code = code
        super().__init__(code)


class DailyLimits(DailyDTO):
    per_page: int = Field(ge=1, le=100)
    max_pages: int = Field(ge=1, le=32)
    max_requests: int = Field(ge=1, le=256)
    timeout_seconds: int = Field(ge=1, le=10)
    max_elapsed_seconds: int = Field(ge=1, le=18)
    max_response_bytes: int = Field(ge=128, le=2097152)
    max_orders: int = Field(ge=1, le=1000)
    max_lines: int = Field(ge=1, le=10000)
    max_refunds: int = Field(ge=1, le=10000)
    max_snapshot_bytes: int = Field(ge=128, le=8388608)
    max_retries: Literal[0]


class ManifestOrder(DailyDTO):
    order_id: Identifier
    line_ids: tuple[Identifier, ...]
    refund_ids: tuple[Identifier, ...]

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len(set(self.line_ids)) != len(self.line_ids) or len(set(self.refund_ids)) != len(
            self.refund_ids
        ):
            raise ValueError("DAILY_MANIFEST_DUPLICATE")
        return self


class DailyManifest(DailyDTO):
    @field_validator("controlled_dataset", "no_external_writers", mode="before")
    @classmethod
    def strict_attestation(cls, value: object) -> object:
        if type(value) is not bool:
            raise ValueError("DAILY_BOOLEAN_INVALID")
        return value

    schema_version: Literal["p6-daily-manifest-v1"]
    organization_id: UUID
    shop_id: UUID
    source_config_version: Identifier
    dataset_version: Identifier
    earliest_business_day: date
    latest_business_day: date
    orders: tuple[ManifestOrder, ...]
    controlled_dataset: Literal[True]
    no_external_writers: Literal[True]

    @model_validator(mode="after")
    def unique(self) -> Self:
        if self.earliest_business_day > self.latest_business_day or (
            len({o.order_id for o in self.orders}) != len(self.orders)
        ):
            raise ValueError("DAILY_MANIFEST_INVALID")
        return self


class MetadataBase(DailyDTO):
    schema_version: Literal["p6-daily-binding-v1"]
    organization_id: UUID
    shop_id: UUID
    config_ref: Identifier
    source_config_version: Identifier
    external_shop_key: Identifier
    timezone: Timezone
    currency: Currency
    earliest_business_day: date
    manifest_ref: str
    manifest_digest: Digest
    limits: DailyLimits
    metric_version: Literal["daily-metrics-v1"]
    status_mapping_version: Literal["daily-status-v1"]

    @model_validator(mode="after")
    def paths(self) -> Self:
        from pathlib import Path

        path = Path(self.manifest_ref)
        if not path.is_absolute() or ".." in path.parts:
            raise ValueError("DAILY_SOURCE_REFERENCE_INVALID")
        return self

    @property
    def config_digest(self) -> str:
        return facts_hash(self.model_dump(mode="json"))

    def source(self, binding: UUID) -> DailySource:
        return DailySource(
            organization_id=self.organization_id,
            shop_id=self.shop_id,
            source_binding_id=binding,
            source_config_version=self.source_config_version,
            config_digest=self.config_digest,
            source_kind=self.adapter_kind,
            fixture_version=self.fixture_version if isinstance(self, MockMetadata) else None,
            currency=self.currency,
            timezone=self.timezone,
        )

    @property
    def adapter_kind(self) -> Literal["mock", "woocommerce_test"]:
        raise NotImplementedError


class MockMetadata(MetadataBase):
    source_kind: Literal["mock"]
    environment: Literal["mock", "test"]
    coverage_profile: Literal["complete_fixture_v1"]
    fixture_ref: str
    fixture_digest: Digest
    fixture_version: Identifier

    @property
    def adapter_kind(self) -> Literal["mock"]:
        return "mock"


class WooMetadata(MetadataBase):
    source_kind: Literal["woocommerce_test"]
    environment: Literal["test"]
    coverage_profile: Literal["closed_test_manifest_v1"]
    origin: str
    consumer_key_file: str = Field(repr=False)
    consumer_secret_file: str = Field(repr=False)
    ca_file: str = Field(repr=False)
    private_pin_ref: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")]

    @property
    def adapter_kind(self) -> Literal["woocommerce_test"]:
        return "woocommerce_test"

    @model_validator(mode="after")
    def transport(self) -> Self:
        from pathlib import Path
        from urllib.parse import urlsplit

        url = urlsplit(self.origin)
        if (
            url.scheme != "https"
            or url.hostname not in {"localhost", "127.0.0.1", "::1"}
            or url.port is None
            or url.username is not None
            or url.password is not None
            or url.path
            or url.query
            or url.fragment
        ):
            raise ValueError("DAILY_SOURCE_ORIGIN_INVALID")
        paths = (self.consumer_key_file, self.consumer_secret_file, self.ca_file)
        if len(set(paths)) != 3 or any(
            not Path(p).is_absolute() or ".." in Path(p).parts for p in paths
        ):
            raise ValueError("DAILY_SOURCE_REFERENCE_INVALID")
        return self


DailyMetadata = Annotated[MockMetadata | WooMetadata, Field(discriminator="source_kind")]


class DailyTaskRequest(DailyDTO):
    schema_version: Literal["p6-daily-task-v1"]
    daily_source: DailySource
    business_day: date
    snapshot_id: UUID
    rules: DailyRuleConfig
    request_key: UUID
    request_hash: Digest
    conversation_id: UUID
    requester_auth_version: int = Field(ge=1)

    @model_validator(mode="after")
    def currency(self) -> Self:
        if self.rules.currency != self.daily_source.currency:
            raise ValueError("DAILY_RULE_CURRENCY_MISMATCH")
        return self
