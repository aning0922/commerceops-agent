"""P204显式说明子任务；父P203业务报告及checkpoint不改。"""

import hashlib
import json
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from commerceops.application.commerce.inventory_facts import InventoryReport
from commerceops.application.model_explanation.contracts import (
    MODEL,
    PROMPT_VERSION,
    ExplanationResult,
)
from commerceops.application.model_explanation.service import SYSTEM, reason
from commerceops.domain.commerce_values import facts_hash

EXPLANATION_KIND = "report_explanation_only"
EXPLANATION_WORKFLOW = "p204-report-explanation-v1"
EXPLANATION_VERSION = "p204-explanation-v1"
PRICING_VERSION = "ds-v41-peak-20261010"
Evidence = Literal["template", "offline_stub", "actual_provider", "local_fault"]
STAGE_BASE = "phase2-deepseek-20261010"
RESERVE_NANOS = 3_360_000
MAX_CALLS = 10
CAP_NANOS = 100_000_000


class ExplanationTaskRequest(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    schema_version: Literal["p204-task-v1"] = "p204-task-v1"
    parent_task_id: UUID
    snapshot_id: UUID
    report_id: UUID
    facts_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    identity_id: UUID
    auth_version: int = Field(ge=1, le=9223372036854775807)
    evidence_mode: Evidence
    prompt_version: Literal["inventory-explanation-v1"] = "inventory-explanation-v1"
    model: Literal["deepseek-flash"] = "deepseek-flash"
    pricing_version: Literal["ds-v41-peak-20261010"] = "ds-v41-peak-20261010"
    body_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    logical_key: str = Field(pattern=r"^p204:[a-f0-9]{64}$")


def explanation_body_hash(report: InventoryReport) -> str:
    # 固定已审B public SYSTEM/reason + 固定Chat wire profile；Admission再核实际body hash。
    user = json.dumps(
        {"items": [{"sku_key": f.sku_key, "allowed_reason": reason(f)} for f in report.items]},
        ensure_ascii=True,
        separators=(",", ":"),
    )
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        "thinking": {"type": "disabled"},
        "stream": False,
        "response_format": {"type": "json_object"},
        "max_tokens": 800,
    }
    return hashlib.sha256(
        json.dumps(body, ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()


def logical_key(
    org: UUID,
    shop: UUID,
    owner: UUID,
    parent: UUID,
    report: UUID,
    digest: str,
    body_hash: str,
    mode: Evidence,
) -> str:
    return "p204:" + facts_hash(
        {
            "org": str(org),
            "shop": str(shop),
            "owner": str(owner),
            "parent": str(parent),
            "report": str(report),
            "facts_hash": digest,
            "body_hash": body_hash,
            "prompt": PROMPT_VERSION,
            "model": MODEL,
            "mode": mode,
            "pricing": PRICING_VERSION,
        }
    )


@dataclass(frozen=True)
class StoredExplanation:
    result_id: UUID
    child_task_id: UUID
    logical_key: str
    result: ExplanationResult
