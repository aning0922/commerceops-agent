"""BC01/05 的 P203 版本化只读 DTO；只投影分析证据。"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from commerceops.application.commerce.inventory_facts import InventoryReport

TaskState = Literal["queued", "analyzing", "completed", "failed", "needs_attention"]
Outcome = Literal["report_ready", "no_action"]


class ReadDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    schema_version: Literal["p203-read-v1"] = "p203-read-v1"
    analysis_only: Literal[True] = True
    execution_available: Literal[False] = False


class ScopedRead(ReadDTO):
    task_id: UUID
    identity_mode: Literal["simulated"] = "simulated"


class TaskRead(ScopedRead):
    state: TaskState
    kind: Literal["inventory_analysis_only"]
    workflow_version: Literal["p203-inventory-analysis-v1"]
    created_at: datetime
    updated_at: datetime
    failure_code: str | None
    outcome: Outcome | None


class ReportRead(ScopedRead):
    snapshot_id: UUID
    report_id: UUID
    content_hash: str
    outcome: Outcome
    collection_started_at: datetime
    collected_at: datetime
    source_complete: bool
    consistency: Literal["observational"]
    facts: InventoryReport


class EventDetails(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    snapshot_id: UUID | None = None
    report_id: UUID | None = None
    complete: bool | None = None
    outcome: Outcome | None = None
    state: TaskState | None = None
    code: (
        Literal[
            "ANALYSIS_PERMISSION_INVALID",
            "ANALYSIS_STATE_INVALID",
            "ANALYSIS_INPUT_INVALID",
            "ANALYSIS_CHECKPOINT_UNSAFE",
            "ANALYSIS_STORAGE_FAILURE",
        ]
        | None
    ) = None


class EventRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    occurred_at: datetime
    action: Literal["analysis_started", "analysis_failed", "analysis_report_saved"]
    details: EventDetails


class EventsRead(ScopedRead):
    items: list[EventRead]
    next_cursor: str | None


class ErrorDetail(BaseModel):
    code: str
    safe_message: str


class ErrorRead(ReadDTO):
    error: ErrorDetail
