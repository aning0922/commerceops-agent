"""P204新增只读/受控路由DTO，保留P203字段及OpenAPI合同。"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from commerceops.application.commerce.inventory_routing import ModelRoute, RoutingDecision
from commerceops.application.commerce.read_models import ErrorDetail, TaskRead
from commerceops.application.model_explanation.contracts import ErrorCode

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Identifier = Annotated[str, Field(pattern=r"^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$")]


class ExplanationDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)


class ExplanationRefs(ExplanationDTO):
    snapshot_id: Identifier
    report_id: Identifier


class ExplanationUsage(ExplanationDTO):
    input_tokens: int = Field(ge=0, le=8000)
    output_tokens: int = Field(ge=0, le=800)
    total_tokens: int = Field(ge=0, le=8800)


class ExplanationMetadata(ExplanationDTO):
    content: None
    error_code: ErrorCode | None
    evidence_mode: Literal["not_used", "offline_stub", "actual_provider"]
    provider: Literal["deepseek"] | None
    requested_model: Literal["deepseek-flash"] | None
    returned_model: Literal["deepseek-flash"] | None
    prompt_version: Literal["inventory-explanation-v1", "inventory-routing-v1"]
    request_id: Identifier | None
    usage: ExplanationUsage | None
    latency_ms: int | None = Field(ge=0)
    pricing_version: Literal["ds-v41-peak-20261010"] | None
    cost_estimate: Annotated[str, Field(pattern=r"^[0-9]+(\.[0-9]+)?$")] | None
    stop_required: bool


class ExplanationItem(ExplanationDTO):
    sku_key: str
    reason: Literal[
        "risk", "stockout", "normal", "no_recent_demand", "manual_check", "quality_blocked"
    ]
    text: str
    facts_hash: Digest
    reference_ids: ExplanationRefs


class ExplanationContent(ExplanationDTO):
    facts_hash: Digest
    narrative_mode: Literal["template", "model_selected"]
    binding_mode: Literal["caller_references"]
    summary: str
    lines: list[ExplanationItem]
    reference_ids: ExplanationRefs
    metadata: ExplanationMetadata


class ExplanationRead(ExplanationDTO):
    schema_version: Literal["p204-read-v1"] = "p204-read-v1"
    analysis_only: Literal[True] = True
    execution_available: Literal[False] = False
    identity_mode: Literal["simulated"] = "simulated"
    task_id: Identifier
    explanation_id: Identifier
    child_task_id: Identifier
    result: ExplanationContent


class ExplanationError(ExplanationDTO):
    schema_version: Literal["p204-read-v1"] = "p204-read-v1"
    analysis_only: Literal[True] = True
    execution_available: Literal[False] = False
    error: ErrorDetail


class RoutingRead(ExplanationDTO):
    decision: RoutingDecision
    identity_mode: Literal["simulated"] = "simulated"
    created_task_id: Identifier | None
    job_id: Identifier | None
    task: TaskRead | None = None


class IntentQueuedRead(ExplanationDTO):
    schema_version: Literal["p204-route-queued-v1"] = "p204-route-queued-v1"
    analysis_only: Literal[True] = True
    execution_available: Literal[False] = False
    identity_mode: Literal["simulated"] = "simulated"
    task_id: Identifier
    job_id: Identifier
    state: Literal["queued"] = "queued"


class IntentContent(ExplanationDTO):
    proposal: ModelRoute
    decision: RoutingDecision
    metadata: ExplanationMetadata

    @field_validator("proposal", mode="before")
    @classmethod
    def stored_proposal(cls, value: object) -> ModelRoute:
        if isinstance(value, ModelRoute):
            return value
        import json

        return ModelRoute.model_validate_json(json.dumps(value))


class IntentRead(ExplanationDTO):
    schema_version: Literal["p204-route-read-v1"] = "p204-route-read-v1"
    analysis_only: Literal[True] = True
    execution_available: Literal[False] = False
    identity_mode: Literal["simulated"] = "simulated"
    task_id: Identifier
    state: Literal["queued", "analyzing", "completed", "failed", "needs_attention"]
    result: IntentContent | None
