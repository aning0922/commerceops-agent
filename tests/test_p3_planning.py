"""P3确定性计划/严格输入/安全参数边界；offline并非PG审批验收。"""

import asyncio
import json
import secrets
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from commerceops.application.commerce.analysis_task import InventoryTaskRequest
from commerceops.application.commerce.inventory_analysis import analyze_inventory
from commerceops.application.replenishment.contracts import CreateInput
from commerceops.application.replenishment.planning import FrozenPlan, PlanRejected, freeze_plan
from commerceops.application.replenishment.security import (
    approval_nonce,
    csrf_token,
    password_hash,
    verify_password,
)
from commerceops.domain.inventory_rules import RuleParameters
from commerceops.infrastructure.database import DatabaseSettings
from commerceops.infrastructure.web_config import WebConfig
from commerceops.workflows.inventory_analysis import MockCollectorFactory
from pydantic import TypeAdapter, ValidationError

pytestmark = pytest.mark.offline
DIRECTORY = Path(__file__).parent / "fixtures/commerce/inventory-v1"


def make_plan(case: str = "baseline", **override: object) -> FrozenPlan | None:
    collected = asyncio.run(
        MockCollectorFactory(DIRECTORY)(InventoryTaskRequest(fixture_case=case)).collect()
    )
    report = analyze_inventory(collected.data, RuleParameters())
    args: dict[str, Any] = {
        "organization_id": UUID(int=1),
        "shop_id": UUID(int=2),
        "task_id": UUID(int=3),
        "plan_id": UUID(int=4),
        "version": 1,
        "report": report,
        "source": {
            "source_task_id": str(UUID(int=5)),
            "report_id": str(UUID(int=6)),
            "snapshot_id": str(UUID(int=7)),
            "facts_hash": report.facts_hash,
        },
        "expires_at": datetime(2026, 10, 12, tzinfo=UTC),
        "parameters": {
            "source_mode": "mock",
            "dataset_version": "inventory-v1",
            "fixture_case": case,
            "L": 3,
            "R": 7,
            "S": 2,
        },
        "config_version": "p3-config-v1",
    }
    args.update(override)
    return freeze_plan(**args)


def test_immutable_plan_uses_facts_and_preserves_raw_unknown() -> None:
    known = make_plan()
    unknown = make_plan("unknown_inbound")
    assert known and unknown
    assert known.content["items"][0]["quantity"] == 100
    assert unknown.content["items"][0]["raw_inbound_units"] is None
    assert unknown.content["items"][0]["effective_inbound_units"] == 0
    assert unknown.content["required_assumptions"][0]["estimated_units"] == 0
    assert known.plan_hash != unknown.plan_hash
    repeated = make_plan("unknown_inbound")
    assert repeated and repeated.plan_hash == unknown.plan_hash


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", 2),
        ("plan_id", UUID(int=8)),
        ("expires_at", datetime(2026, 10, 12, tzinfo=UTC) + timedelta(microseconds=1)),
        ("config_version", "p3-config-v2"),
    ],
)
def test_plan_hash_binds_versions_deadline_and_configuration(field: str, value: object) -> None:
    first = make_plan()
    overrides: dict[str, Any] = {field: value}
    changed = make_plan(**overrides)
    assert first and changed and first.plan_hash != changed.plan_hash


@pytest.mark.parametrize("case", ["unknown_stock", "open_item", "identity"])
def test_hard_quality_cannot_be_acknowledged(case: str) -> None:
    with pytest.raises(PlanRejected):
        make_plan(case)


@pytest.mark.parametrize("case", ["normal", "empty_products", "no_demand"])
def test_no_action_has_no_empty_approval(case: str) -> None:
    assert make_plan(case) is None


def test_capacity_no_silent_truncation() -> None:
    # 不使用临时数量修改绕过P2报告hash；真实边界由范围配置控制。
    with pytest.raises(PlanRejected):
        make_plan(max_items=0)
    with pytest.raises(PlanRejected):
        make_plan(max_items=True)


@pytest.mark.parametrize(
    "mutation",
    [
        {"actor": str(UUID(int=1))},
        {"approved": True},
        {"role": "approver"},
        {"facts_hash": "broken"},
        {"mode": "recompute"},
    ],
)
def test_client_authority_and_invalid_bindings_are_forbidden(mutation: dict[str, object]) -> None:
    body = {
        "schema_version": "p3-web-v1",
        "mode": "from_report",
        "request_key": str(UUID(int=8)),
        "source_task_id": str(UUID(int=5)),
        "source_report_id": str(UUID(int=6)),
        "snapshot_id": str(UUID(int=7)),
        "facts_hash": "0" * 64,
        **mutation,
    }
    with pytest.raises(ValidationError):
        TypeAdapter(CreateInput).validate_json(json.dumps(body))


@pytest.mark.parametrize("units", [True, 3.0, -1, 366])
def test_new_cycle_strict_integer_parameters(units: object) -> None:
    body = {
        "schema_version": "p3-web-v1",
        "mode": "new_cycle",
        "request_key": str(UUID(int=8)),
        "shop_id": str(UUID(int=2)),
        "parameters": {
            "source_mode": "mock",
            "dataset_version": "inventory-v1",
            "fixture_case": "baseline",
            "L": units,
            "R": 7,
            "S": 2,
        },
    }
    with pytest.raises(ValidationError):
        TypeAdapter(CreateInput).validate_json(json.dumps(body))


def test_scrypt_hash_and_constant_time_verification_contract() -> None:
    value = secrets.token_urlsafe(24)
    stored = password_hash(value)
    matched = verify_password(value, stored)
    rejected = not verify_password(secrets.token_urlsafe(24), stored)
    assert matched and rejected
    assert stored.split("$")[:4] == ["scrypt-v1", "131072", "8", "1"]


def test_csrf_and_nonce_bind_different_purposes_and_plan_version() -> None:
    secret = secrets.token_bytes(32)
    csrf = csrf_token(secret, UUID(int=1))
    nonce = approval_nonce(
        secret, UUID(int=1), UUID(int=2), 1, "0" * 64, datetime(2026, 10, 12, tzinfo=UTC)
    )
    changed = approval_nonce(
        secret, UUID(int=1), UUID(int=2), 2, "0" * 64, datetime(2026, 10, 12, tzinfo=UTC)
    )
    different = csrf != nonce and nonce != changed
    assert different


def config() -> WebConfig:
    return WebConfig(
        DatabaseSettings(
            host="127.0.0.1", name="owned", user="owned", password_file=Path("runtime/unused")
        ),
        secrets.token_bytes(32),
        secrets.token_bytes(32),
        ("http://127.0.0.1",),
        transport_mode="local_http",
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"origins": ("http://127.0.0.1.attacker.invalid",)},
        {"origins": ("https://*.example.invalid",), "transport_mode": "https"},
        {"origins": ("http://127.0.0.1/path",)},
        {"session_idle_seconds": 40000},
        {"approval_ttl_seconds": True},
        {"max_plan_items": 21},
    ],
)
def test_invalid_origin_and_configuration_fail_closed(changes: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        replace(config(), **changes)
