"""p3-web-v1严格输入和可信服务端上下文；没有授权布尔旁路。"""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from commerceops.application.commerce.analysis_task import (
    AnalysisRequest,
    InventoryTaskRequest,
    WooInventoryTaskRequest,
    parse_analysis_request,
)
from commerceops.application.commerce.source_binding import RegisteredWooSource

TASK_KIND = "inventory_replenishment"
WORKFLOW_VERSION = "p3-inventory-replenishment-v1"
SCHEMA_VERSION = "p3-web-v1"
Role = Literal["operator", "approver", "admin"]


class Input(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    schema_version: Literal["p3-web-v1"]


class Parameters(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    source_mode: Literal["mock"]
    dataset_version: Literal["inventory-v1"]
    fixture_case: str = Field(min_length=1, max_length=100)
    L: int = Field(ge=0, le=365)
    R: int = Field(ge=0, le=365)
    S: int = Field(ge=0, le=365)

    def analysis_request(self) -> InventoryTaskRequest:
        return InventoryTaskRequest(**self.model_dump())


class WooCreateParameters(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    source_mode: Literal["woocommerce_test"]
    source_config_version: str = Field(min_length=1, max_length=256)
    L: int = Field(ge=0, le=365)
    R: int = Field(ge=0, le=365)
    S: int = Field(ge=0, le=365)

    def bind(self, registered: RegisteredWooSource) -> WooInventoryTaskRequest:
        if self.source_config_version != registered.source_config_version:
            raise ValueError("COMMERCE_SOURCE_UNAVAILABLE")
        return WooInventoryTaskRequest(
            **self.model_dump(),
            source_binding_id=registered.binding_id,
            organization_id=registered.organization_id,
            shop_id=registered.shop_id,
        )


def analysis_request_from_parameters(value: object) -> AnalysisRequest:
    if isinstance(value, dict) and value.get("source_mode") == "woocommerce_test":
        return parse_analysis_request(value)
    return Parameters.model_validate(value).analysis_request()


class CreateFromReport(Input):
    mode: Literal["from_report"]
    request_key: UUID
    source_task_id: UUID
    source_report_id: UUID
    snapshot_id: UUID
    facts_hash: str = Field(pattern="^[a-f0-9]{64}$")


class CreateNewCycle(Input):
    mode: Literal["new_cycle"]
    request_key: UUID
    shop_id: UUID
    parameters: Parameters | WooCreateParameters = Field(discriminator="source_mode")


CreateInput = CreateFromReport | CreateNewCycle


class LoginInput(Input):
    login: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024, repr=False)


class LogoutInput(Input):
    pass


class DecisionInput(Input):
    request_key: UUID
    approval_id: UUID
    plan_id: UUID
    plan_version: int = Field(ge=1)
    plan_hash: str = Field(pattern="^[a-f0-9]{64}$")
    action: Literal["approve", "reject", "approve_with_assumptions", "reject_assumptions"]
    acknowledged_assumption_keys: tuple[str, ...] = Field(max_length=20)
    nonce: str = Field(pattern="^[A-Za-z0-9_-]{43}$", repr=False)

    @model_validator(mode="after")
    def valid_keys(self) -> "DecisionInput":
        acks = self.acknowledged_assumption_keys
        if len(set(acks)) != len(acks) or any(
            not key.startswith("inbound_unknown_zero:")
            or len(key) > 300
            or len(key) == len("inbound_unknown_zero:")
            for key in acks
        ):
            raise ValueError("INVALID_REQUEST")
        if (self.action == "approve_with_assumptions") != bool(acks):
            raise ValueError("INVALID_REQUEST")
        return self


class ResolveInput(Input):
    request_key: UUID
    action: Literal["complete", "close"]
    reason: str = Field(min_length=1, max_length=1000)
    expected_version: int = Field(ge=1)

    @model_validator(mode="after")
    def nonempty_reason(self) -> "ResolveInput":
        if not self.reason.strip():
            raise ValueError("INVALID_REQUEST")
        return self


@dataclass(frozen=True)
class WebActor:
    """仅由服务端PG会话解析器构造；用例仍须锁后查询当前权限。"""

    session_id: UUID
    principal_id: UUID
    identity_id: UUID
    organization_id: UUID
    auth_version: int


@dataclass(frozen=True)
class FeishuActor:
    """只由正式Gateway的PG identity桥接构造，不依赖Web session。"""

    principal_id: UUID
    identity_id: UUID
    organization_id: UUID
    auth_version: int
    app_id: str
    tenant_key: str
    open_id: str
    chat_id: str
    topic_key: str = "p4-inventory-v1"


Actor = WebActor | FeishuActor


class WebFailure(Exception):
    def __init__(self, code: str, status: int = 409):
        self.code, self.status = code, status
        super().__init__(code)
