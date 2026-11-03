"""Strict V4-0 wire DTOs; authority, clocks and session resolution remain server concerns."""

from datetime import UTC, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

FIXTURE_VERSION = "v4-demo-seed-1"
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Counter = Annotated[int, Field(ge=0)]
PersonaId = Literal["operator", "approver", "restricted_admin"]
Operation = Literal["session_create", "persona", "reset", "logout"]
ShopKey = Literal["v4-shop-a", "v4-shop-b"]
Currency = Literal["TWD", "CNY"]


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


Timestamp = Annotated[AwareDatetime, AfterValidator(_utc)]


class Contract(BaseModel):
    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
        revalidate_instances="always",
    )


class CreateSessionInput(Contract):
    request_key: UUID
    fixture_version: Literal["v4-demo-seed-1"]


class ExpectedContext(Contract):
    request_key: UUID
    expected_epoch: Counter
    expected_generation: Counter


class PersonaInput(ExpectedContext):
    persona_id: PersonaId


class ResetInput(ExpectedContext):
    fixture_version: Literal["v4-demo-seed-1"]


class LogoutInput(ExpectedContext):
    pass


class Context(Contract):
    tenant_id: UUID
    organization_id: UUID
    principal_id: UUID
    shop_id: UUID | None
    reset_epoch: Counter
    auth_generation: Counter
    authorized_at: Timestamp


class Shop(Contract):
    shop_id: UUID
    display_name: str
    timezone: str
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    grants: tuple[str, ...]

    @model_validator(mode="after")
    def unique_grants(self) -> Self:
        if len(set(self.grants)) != len(self.grants):
            raise ValueError("DUPLICATE_GRANT")
        return self


class Source(Contract):
    data_mode: Literal["demo_fixture"]
    evidence_mode: Literal["synthetic_demo"]
    fixture_version: Literal["v4-demo-seed-1"]
    fixture_digest: Digest


class Receipt(Contract):
    receipt_id: UUID
    operation: Operation
    request_key: UUID
    payload_digest: Digest
    status: Literal["COMMITTED"]
    committed_at: Timestamp
    reset_epoch: Counter
    auth_generation: Counter


class BootstrapData(Contract):
    csrf_token: str = Field(repr=False)
    expires_at: Timestamp
    state: Literal["anonymous_bootstrap"]


class SessionData(Contract):
    creation_request_key: UUID
    persona_id: str
    expires_at: Timestamp
    csrf_token: str = Field(repr=False)
    shops: tuple[Shop, ...] = Field(max_length=2)
    source: Source

    @model_validator(mode="after")
    def unique_shops(self) -> Self:
        if len({shop.shop_id for shop in self.shops}) != len(self.shops):
            raise ValueError("DUPLICATE_SHOP")
        return self


class CreateData(Contract):
    session: SessionData
    receipt: Receipt


class SummaryCounts(Contract):
    products: Counter
    skus: Counter
    orders: Counter
    order_lines: Counter


class SeedSummaryData(Contract):
    source: Source
    counts: SummaryCounts
    snapshot_at: Timestamp


class ControlData(Contract):
    receipt: Receipt
    next_step: Literal["READ_CURRENT_SESSION", "LOGGED_OUT"]


class OperationReceipt(Contract):
    receipt: Receipt


class BootstrapOperation(Contract):
    operation: Literal["session_create"]
    request_key: UUID
    status: Literal["COMMITTED", "UNKNOWN"]
    recovery: Literal["OWNER_RECOVERY_REQUIRED", "WAIT_READ_ONLY"]

    @model_validator(mode="after")
    def recovery_state(self) -> Self:
        expected = "OWNER_RECOVERY_REQUIRED" if self.status == "COMMITTED" else "WAIT_READ_ONLY"
        if self.recovery != expected:
            raise ValueError("INVALID_RECOVERY_STATE")
        return self


OperationData = OperationReceipt | BootstrapOperation
ErrorCode = Literal[
    "SESSION_INVALID",
    "EXPIRED",
    "ORIGIN_DENIED",
    "CSRF_INVALID",
    "ACCESS_DENIED",
    "RESOURCE_NOT_FOUND",
    "EPOCH_CHANGED",
    "GENERATION_CHANGED",
    "IDEMPOTENCY_CONFLICT",
    "INVALID_REQUEST",
    "CAPACITY_LIMIT",
    "RATE_LIMITED",
    "SERVICE_UNAVAILABLE",
    "OWNER_RECOVERY_REQUIRED",
]


class Error(Contract):
    code: ErrorCode
    safe_message: str
    retryable: Literal[False]
    request_key: UUID | None

    @field_validator("retryable", mode="before")
    @classmethod
    def boolean_retryable(cls, value: object) -> object:
        if type(value) is not bool:
            raise ValueError("INVALID_RETRYABLE_FLAG")
        return value


class FailureEnvelope(Contract):
    schema_version: Literal["v4-demo-v1"]
    server_time: Timestamp | None
    trace_id: UUID
    status: Literal["REJECTED", "UNKNOWN"]
    error: Error


class SuccessEnvelope[T](Contract):
    schema_version: Literal["v4-demo-v1"]
    server_time: Timestamp
    trace_id: UUID
    status: Literal["OK", "COMMITTED", "UNKNOWN"]
    data: T


class ContextEnvelope[T](SuccessEnvelope[T]):
    context: Context


class BootstrapEnvelope(SuccessEnvelope[BootstrapData]):
    pass


class SessionEnvelope(ContextEnvelope[SessionData]):
    pass


class CreateEnvelope(ContextEnvelope[CreateData]):
    pass


class SeedSummaryEnvelope(ContextEnvelope[SeedSummaryData]):
    pass


class ControlEnvelope(ContextEnvelope[ControlData]):
    pass


class OperationEnvelope(SuccessEnvelope[OperationData]):
    pass
