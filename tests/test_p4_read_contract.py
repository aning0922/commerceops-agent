"""安全read字段/当前Gate分类与非SDK计数的严格契约；Fake PG游标不执行SQL。"""

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from commerceops.application.feishu_business.contracts import Contract
from commerceops.application.feishu_business.read_models import (
    ProjectionRead,
    SenderGateRead,
    ToolFactRead,
)
from commerceops.infrastructure.feishu_delivery_read import (
    external_enabled,
    safe_code,
    sender_gates,
)
from pydantic import ValidationError

pytestmark = pytest.mark.offline
SCHEMA = json.loads(
    (Path(__file__).resolve().parents[1] / "docs/contracts/p3-openapi.json").read_text()
)


def valid(name: str, data: object) -> None:
    models: dict[str, type[Contract]] = {
        "Projection": ProjectionRead,
        "SenderGate": SenderGateRead,
        "ToolFact": ToolFactRead,
    }
    models[name].model_validate_json(json.dumps(data))


class DB:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows
        self.sql: list[tuple[str, Any]] = []
        self.timestamp = datetime.now(UTC)

    def execute(self, query: str, params: Any = None) -> "DB":
        self.sql.append((query, params))
        return self

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows

    def fetchone(self) -> dict[str, Any]:
        return {"time": self.timestamp}


@pytest.mark.parametrize(
    "case,reason,enabled",
    [
        ("off", "DISABLED_BY_CONFIGURATION", False),
        ("expired", "WINDOW_EXPIRED", False),
        ("stopped", "WORKER_NOT_READY", False),
        ("live", "CONTROLLED_WINDOW_ACTIVE", True),
    ],
)
def test_sender_gate_requires_config_current_window_and_actual_worker_lock(
    case: str, reason: str, enabled: bool
) -> None:
    db = DB([])
    db.rows = [
        dict(
            destination_alias="Base",
            configured_enabled=case != "off",
            expires_at=db.timestamp + timedelta(seconds=-1 if case == "expired" else 60),
            worker_ready=case != "stopped",
            verification_mode="offline_fake",
            checked_at=db.timestamp,
            target_key="never-export",
            external_id="never-export",
            worker_backend_pid=99,
        )
    ]
    organization, shop = uuid4(), uuid4()
    gates = sender_gates(db, organization, [shop])  # type: ignore[arg-type]
    assert gates[0]["reason_code"] == reason and gates[0]["sender_enabled"] is enabled
    assert not external_enabled(gates)  # Fake sender enabled并不等价真实平台sender。
    assert "never-export" not in json.dumps(gates, default=str)
    assert db.sql[0][1][-2:] == ([shop], [shop])
    for g in gates:
        valid("SenderGate", {**g, "as_of": g["as_of"].isoformat()})


def test_safe_sync_original_v1_verified_is_explicitly_historical_when_target_v2() -> None:
    now = datetime.now(UTC).isoformat()
    row = dict(
        aggregate_id=str(uuid4()),
        outbox_id=str(uuid4()),
        projection_version=1,
        outbox_status="pending",
        state="synced",
        source_mode="mock",
        as_of=now,
        error_code=None,
        destination_alias="Base",
        target_version=2,
        observed_version=1,
        complete_unique_verified=True,
        is_current_version=False,
        attempts=2,
        verification_mode="offline_fake",
    )
    valid("Projection", row)
    for key in ("external_id", "target_key", "client_token", "app_token", "open_id"):
        with pytest.raises(ValidationError):
            valid("Projection", {**row, key: "never-export"})


def test_sdk_adapter_operation_and_actual_sdk_method_are_distinct_from_model_choice() -> None:
    actual = dict(
        category="sdk_adapter",
        name="feishu.base.project",
        selected_by_model=False,
        sdk_method=None,
        verification_mode="offline_fake",
    )
    valid("ToolFact", actual)
    sdk = {**actual, "category": "sdk_method", "sdk_method": "bitable.v1.app_table_record.list"}
    valid("ToolFact", sdk)
    invalid = copy.deepcopy(sdk)
    invalid["sdk_method"] = "arbitrary-sensitive-target"
    with pytest.raises(ValidationError):
        valid("ToolFact", invalid)
    assert safe_code("SQL failed: platform identifier private") == "PROJECTION_ERROR"
    assert safe_code("BASE_ACK_UNPROVEN") == "BASE_ACK_UNPROVEN"
