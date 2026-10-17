"""当前 P3 报告的纯模板结果；不借用 P204 child 或 provider 证据。"""

from datetime import datetime, timedelta
from typing import Literal, Self

from pydantic import model_validator

from commerceops.application.commerce.explanation_read import (
    Digest,
    ExplanationContent,
    ExplanationDTO,
    ExplanationMetadata,
    Identifier,
)

TEMPLATE_VERSION = "p3-report-template-v1"
SourceKind = Literal["p2_original", "p3_observation"]


class TemplateRenderError(RuntimeError):
    """仅已核事实上的封闭 formatter 故障可保存 unavailable。"""


class TemplateMetadata(ExplanationMetadata):
    error_code: Literal["NO_PROVIDER", "TEMPLATE_REQUIRED"]
    evidence_mode: Literal["not_used"]
    provider: None
    requested_model: None
    returned_model: None
    prompt_version: Literal["inventory-explanation-v1"]
    request_id: None
    usage: None
    latency_ms: None
    pricing_version: None
    cost_estimate: None
    stop_required: Literal[False]


class TemplateContent(ExplanationContent):
    narrative_mode: Literal["template"]
    metadata: TemplateMetadata


class P3TemplateRead(ExplanationDTO):
    schema_version: Literal["p4-p3-template-read-v1"] = "p4-p3-template-read-v1"
    analysis_only: Literal[True] = True
    execution_available: Literal[False] = False
    identity_mode: Literal["simulated"] = "simulated"
    task_id: Identifier
    source_task_id: Identifier
    source_kind: SourceKind
    observation_id: Identifier | None
    explanation_id: Identifier
    report_id: Identifier
    snapshot_id: Identifier
    facts_hash: Digest
    template_version: Literal["p3-report-template-v1"]
    created_at: datetime
    result: TemplateContent

    @model_validator(mode="after")
    def exact_report_binding(self) -> Self:
        if (
            self.created_at.utcoffset() != timedelta(0)
            or (self.source_kind == "p3_observation") != (self.observation_id is not None)
            or self.observation_id is not None
            and self.snapshot_id != self.observation_id
            or self.result.facts_hash != self.facts_hash
            or self.result.reference_ids.report_id != self.report_id
            or self.result.reference_ids.snapshot_id != self.snapshot_id
            or any(
                line.facts_hash != self.facts_hash
                or line.reference_ids != self.result.reference_ids
                for line in self.result.lines
            )
            or len({line.sku_key for line in self.result.lines}) != len(self.result.lines)
        ):
            raise ValueError("P3_TEMPLATE_READ_BINDING_INVALID")
        return self
