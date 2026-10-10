"""A02纯集合/hash/官方snapshot类型绑定；非真实PG恢复证据。"""

import json
from typing import Any
from uuid import uuid4

import pytest
from commerceops.application.replenishment.contracts import (
    WORKFLOW_VERSION,
    DecisionInput,
    WebFailure,
)
from commerceops.application.replenishment.decisions import (
    confirm_set,
    decision_hash,
    decision_request_hash,
)
from commerceops.domain.commerce_values import facts_hash
from commerceops.infrastructure.approval_recovery import snapshot_binding
from commerceops.infrastructure.inventory_repository import AnalysisUnsafe
from langgraph.types import Interrupt, StateSnapshot
from pydantic import ValidationError

pytestmark = pytest.mark.offline


def decision(**changes: Any) -> DecisionInput:
    return DecisionInput.model_validate_json(
        json.dumps(
            {
                "schema_version": "p3-web-v1",
                "request_key": str(uuid4()),
                "approval_id": "00000000-0000-4000-8000-000000000001",
                "plan_id": "00000000-0000-4000-8000-000000000002",
                "plan_version": 1,
                "plan_hash": "0" * 64,
                "action": "approve",
                "acknowledged_assumption_keys": [],
                "nonce": "N" * 43,
                **changes,
            }
        )
    )


def test_unknown_inbound_needs_exact_joint_set_and_plain_approve_never_confirms() -> None:
    acks = ["inbound_unknown_zero:sku/A", "inbound_unknown_zero:sku/B"]
    plan = {
        "disclosure_complete": True,
        "hard_blocks": [],
        "required_assumptions": [{"key": value} for value in acks],
    }
    with pytest.raises(WebFailure) as error:
        confirm_set(decision(), plan)
    assert error.value.code == "ASSUMPTION_ACK_REQUIRED"
    for supplied in (acks[:1], acks + ["inbound_unknown_zero:sku/extra"]):
        with pytest.raises(WebFailure) as error:
            confirm_set(
                decision(action="approve_with_assumptions", acknowledged_assumption_keys=supplied),
                plan,
            )
        assert error.value.code == "ASSUMPTION_SET_MISMATCH"
    confirm_set(
        decision(action="approve_with_assumptions", acknowledged_assumption_keys=acks[::-1]), plan
    )
    confirm_set(decision(action="reject_assumptions"), plan)


def test_decision_semantic_hash_excludes_nonce_key_and_sorts_full_set() -> None:
    acks = ["inbound_unknown_zero:sku/A", "inbound_unknown_zero:sku/B"]
    first = decision(action="approve_with_assumptions", acknowledged_assumption_keys=acks)
    second = decision(
        action="approve_with_assumptions", acknowledged_assumption_keys=acks[::-1], nonce="X" * 43
    )
    assert decision_hash(first) == decision_hash(second)
    assert decision_request_hash(first, str(first.approval_id)) != decision_request_hash(
        second, str(first.approval_id)
    )
    assert decision_hash(first) != decision_hash(decision(action="reject_assumptions"))


@pytest.mark.parametrize(
    "change",
    [
        {"approved": True},
        {"plan_version": True},
        {"plan_version": 1.0},
        {
            "action": "approve_with_assumptions",
            "acknowledged_assumption_keys": ["inbound_unknown_zero:a"] * 2,
        },
        {
            "action": "approve_with_assumptions",
            "acknowledged_assumption_keys": ["inbound_unknown_zero:" + "x" * 301],
        },
    ],
)
def test_frozen_input_strict_shape_stays_rejected(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        decision(**change)


def sample() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    task = {"id": uuid4(), "normalized_request": {"schema_version": "p3-web-v1"}}
    approval = {
        "id": uuid4(),
        "plan_id": uuid4(),
        "plan_hash": "0" * 64,
        "plan_version": 1,
        "decision_id": uuid4(),
        "decision_payload_hash": "1" * 64,
        "status": "approved",
    }
    values = {
        "workflow_version": WORKFLOW_VERSION,
        "task_id": str(task["id"]),
        "request_hash": facts_hash(task["normalized_request"]),
        "approval_id": str(approval["id"]),
        "plan_id": str(approval["plan_id"]),
        "plan_hash": approval["plan_hash"],
        "plan_version": 1,
        "decision_id": str(approval["decision_id"]),
        "decision_hash": approval["decision_payload_hash"],
        "outcome": "awaiting_execution",
    }
    return task, approval, values


def snapshot(
    task: dict[str, Any],
    values: dict[str, Any],
    *,
    next_node: tuple[str, ...],
    interrupts: tuple[Interrupt, ...] = (),
) -> StateSnapshot:
    return StateSnapshot(
        values,
        next_node,
        {"configurable": {"thread_id": str(task["id"]), "checkpoint_id": str(uuid4())}},
        None,
        "2026-10-10T14:00:00Z",
        None,
        (),
        interrupts,
    )


def test_static_boundary_has_no_human_interrupt_and_uses_existing_next() -> None:
    task, approval, values = sample()
    saved = snapshot(task, values, next_node=("revalidate",))
    assert snapshot_binding(saved, task, approval) == "execution_boundary"
    binding = {k: values[k] for k in ("approval_id", "plan_id", "plan_hash", "plan_version")}
    with pytest.raises(AnalysisUnsafe):
        snapshot_binding(saved._replace(interrupts=(Interrupt(binding),)), task, approval)
    waiting = snapshot(task, values, next_node=("wait_approval",), interrupts=(Interrupt(binding),))
    assert snapshot_binding(waiting, task, approval) == "waiting"


@pytest.mark.parametrize(
    "field,value",
    [
        ("workflow_version", "unknown"),
        ("task_id", "other"),
        ("request_hash", "bad"),
        ("approval_id", "other"),
        ("plan_hash", "bad"),
        ("plan_version", True),
        ("decision_id", "other"),
        ("decision_hash", "bad"),
    ],
)
def test_static_boundary_rejects_any_frozen_binding_change(field: str, value: object) -> None:
    task, approval, values = sample()
    values[field] = value
    with pytest.raises(AnalysisUnsafe):
        snapshot_binding(snapshot(task, values, next_node=("revalidate",)), task, approval)


def test_unknown_next_never_restarts_start() -> None:
    task, approval, values = sample()
    with pytest.raises(AnalysisUnsafe):
        snapshot_binding(snapshot(task, values, next_node=("execute",)), task, approval)
