"""P203任务/采集与模拟只读身份合同；不接受客户端权限声明。"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from commerceops.application.commerce.inventory_facts import InventoryInput, InventoryReport
from commerceops.domain.commerce_values import integer

TASK_KIND = "inventory_analysis_only"
WORKFLOW_VERSION = "p203-inventory-analysis-v1"


class InventoryTaskRequest(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    schema_version: Literal["inventory-task-v1"] = "inventory-task-v1"
    source_mode: Literal["mock"] = "mock"
    dataset_version: Literal["inventory-v1"] = "inventory-v1"
    fixture_case: str = Field(default="baseline", min_length=1, max_length=100)
    L: int = Field(default=3, ge=0)
    R: int = Field(default=7, ge=0)
    S: int = Field(default=2, ge=0)


class WooInventoryTaskRequest(BaseModel):
    """服务端绑定后才持久化的 Woo 请求；不是 Web 创建输入。"""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    schema_version: Literal["p5-inventory-task-v1"] = "p5-inventory-task-v1"
    source_mode: Literal["woocommerce_test"] = "woocommerce_test"
    source_config_version: str = Field(min_length=1, max_length=256)
    source_binding_id: UUID
    organization_id: UUID
    shop_id: UUID
    L: int = Field(ge=0, le=365)
    R: int = Field(ge=0, le=365)
    S: int = Field(ge=0, le=365)


AnalysisRequest = InventoryTaskRequest | WooInventoryTaskRequest


def parse_analysis_request(value: Any) -> AnalysisRequest:
    if isinstance(value, (InventoryTaskRequest, WooInventoryTaskRequest)):
        value = value.model_dump(mode="json")
    if type(value) is dict and value.get("source_mode") == "woocommerce_test":
        # DB JSON UUID strings use JSON-mode strict validation; no string coercion.
        return WooInventoryTaskRequest.model_validate_json(json.dumps(value))
    return InventoryTaskRequest.model_validate(value)


@dataclass(frozen=True)
class CollectedInventory:
    data: InventoryInput
    collection_started_at: datetime
    collected_at: datetime
    consistency: Literal["observational"] = "observational"


@dataclass(frozen=True)
class TrustedReadIdentity:
    identity_id: UUID
    principal_id: UUID
    organization_id: UUID
    shop_id: UUID
    auth_version: int
    mode: Literal["simulated"] = "simulated"

    def __post_init__(self) -> None:
        if integer(self.auth_version) < 1 or self.mode != "simulated":
            raise ValueError("INVALID_TRUSTED_IDENTITY")
        if any(
            not isinstance(value, UUID)
            for value in (self.identity_id, self.principal_id, self.organization_id, self.shop_id)
        ):
            raise ValueError("INVALID_TRUSTED_IDENTITY")


@dataclass(frozen=True)
class StoredAnalysis:
    snapshot_id: UUID
    report_id: UUID
    content_hash: str
    report: InventoryReport
    outcome: Literal["report_ready", "no_action"]
