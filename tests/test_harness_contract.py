"""Offline H1 fail-closed input, ownership, state and schema contracts."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from scripts.current_state import ROOT, render, trusted_snapshot
from scripts.harness_contract import (
    RunAttempt,
    TaskSpec,
    spec_digest,
    validate_attempt,
    validate_owners,
)

pytestmark = pytest.mark.offline


def example() -> dict[str, Any]:
    return json.loads((ROOT / "docs/harness/task.example.json").read_text())  # type: ignore[no-any-return]


def spec_with(**changes: Any) -> TaskSpec:
    data = example()
    data.update(changes)
    data["spec_sha256"] = spec_digest(data)
    return TaskSpec.model_validate(data)


def attempt(spec: TaskSpec, **changes: Any) -> RunAttempt:
    data: dict[str, Any] = {
        "schema_version": "harness-attempt-v3.1",
        "task_id": spec.task_id,
        "spec_sha256": spec.spec_sha256,
        "attempt_id": "attempt-1",
        "attempt_number": 1,
        "turns": 1,
        "wall_seconds": 1.0,
        "state": "LOCAL_PASS",
        "exit_code": 0,
        "resolved_model": "gpt-6.1-sol",
        "effort": "medium",
        "usage_source": "UNKNOWN",
    }
    data.update(changes)
    return RunAttempt.model_validate(data)


def test_example_schema_and_default_policy() -> None:
    spec = TaskSpec.model_validate(example())
    assert spec.model_policy.model == "gpt-6.1-sol"
    assert spec.model_policy.effort == "medium"
    assert not spec.model_policy.allow_api_key_billing
    assert spec.state == "DRAFT"  # Example does not grant this session authority.
    assert isinstance(spec.allowed_files, tuple)
    assert isinstance(spec.required_checks, tuple)
    for name, model in (("task", TaskSpec), ("attempt", RunAttempt)):
        committed = json.loads((ROOT / f"docs/harness/{name}.schema.json").read_text())
        assert committed == model.model_json_schema()


@pytest.mark.parametrize(
    "changes",
    [
        {"unexpected": "field"},
        {"state": "READY"},
        {"allowed_files": ["../outside"]},
        {"allowed_files": ["/absolute"]},
        {"allowed_files": ["scripts/*"]},
        {"allowed_files": ["scripts//verify.py"]},
        {"allowed_files": ["scripts/verify.py", "scripts/verify.py"]},
        {"required_checks": ["fast"]},
        {"risk": "unknown", "required_checks": ["fast", "impacted"]},
        {"bounds": {"max_attempts": 3}},
        {"bounds": {"max_attempts": True}},
        {"bounds": {"max_wall_minutes": 46}},
        {"model_policy": {"model": "gpt-6-astra"}},
        {"model_policy": {"allow_api_key_billing": True}},
        {"model_policy": {"allow_api_key_billing": 0}},
        {"model_policy": {"model": "gpt-6-astra", "astra_approval_ref": " "}},
        {"model_policy": {"model": "unlisted-model"}},
    ],
)
def test_task_rejects_unsafe_or_incomplete_contract(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        spec_with(**changes)


def test_changed_spec_without_new_digest_is_rejected() -> None:
    data = example()
    data["summary"] = "changed after freezing"
    with pytest.raises(ValidationError, match="digest mismatch"):
        TaskSpec.model_validate(data)


def ready_spec() -> TaskSpec:
    return spec_with(
        state="READY",
        approval={
            "approval_id": "synthetic-approval",
            "approval_ref": "offline-test-only",
            "scope": "local_only",
        },
    )


def test_attempt_exact_identity_caps_and_reconciliation() -> None:
    spec = ready_spec()
    first = attempt(spec)
    validate_attempt(spec, first, [])
    with pytest.raises(ValueError, match="only READY"):
        validate_attempt(spec_with(), first, [])
    for changes in (
        {"task_id": "different-task"},
        {"resolved_model": "gpt-6-astra"},
        {"effort": "high"},
    ):
        with pytest.raises(ValueError):
            validate_attempt(spec, attempt(spec, **changes), [])
    second = attempt(spec, attempt_id="attempt-2", attempt_number=2)
    with pytest.raises(ValueError, match="contiguous"):
        validate_attempt(spec, second, [])
    with pytest.raises(ValueError, match="reconcile"):
        validate_attempt(spec, second, [first])
    for state in ("INTERRUPTED", "NEEDS_RECONCILIATION", "RUNNING"):
        previous = attempt(spec, state=state, exit_code=143 if state == "INTERRUPTED" else None)
        with pytest.raises(ValueError, match="reconcile"):
            validate_attempt(spec, second, [previous])
    failed = attempt(spec, state="FAILED", exit_code=1)
    validate_attempt(spec, second, [failed])
    with pytest.raises(ValueError, match="already consumed"):
        validate_attempt(spec, attempt(spec, attempt_number=2), [failed])
    capped = spec_with(
        state="READY",
        approval=spec.approval.model_dump() if spec.approval else None,
        bounds={"max_attempts": 1, "max_turns_per_attempt": 1, "max_wall_minutes": 1},
    )
    with pytest.raises(ValueError, match="attempt cap"):
        validate_attempt(capped, attempt(capped, attempt_number=2), [])
    with pytest.raises(ValueError, match="turn cap"):
        validate_attempt(capped, attempt(capped, turns=2), [])
    with pytest.raises(ValueError, match="wall cap"):
        validate_attempt(capped, attempt(capped, wall_seconds=61.0), [])


@pytest.mark.parametrize(
    "changes",
    [
        {"state": "LOCAL_PASS", "exit_code": None},
        {"state": "FAILED", "exit_code": 0},
        {"state": "NOT_RUN", "exit_code": 0},
        {"state": "NEEDS_RECONCILIATION", "exit_code": 0},
        {"attempt_number": 3},
        {"turns": True},
        {"wall_seconds": float("nan")},
        {"usage_source": "invented quota reservation"},
    ],
)
def test_not_run_failure_unknown_never_become_success(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        attempt(ready_spec(), **changes)


def test_scope_denial_and_single_writer_conflicts(tmp_path: Path) -> None:
    spec = spec_with(allowed_files=["scripts/**"], forbidden_files=["scripts/private/**"])
    assert spec.permits("scripts/verify.py")
    assert not spec.permits("scripts/private/secret.py")
    assert not spec.permits("backend/src/commerceops/__init__.py")
    owner = spec.owner.model_dump()
    owner.update(owner_id="another-writer", worktree=str(tmp_path), branch="codex/other")
    for allowed in (["scripts/verify.py"], ["scripts/**"]):
        with pytest.raises(ValueError, match="ownership conflict"):
            validate_owners(spec, [spec_with(owner=owner, allowed_files=allowed)])
    validate_owners(spec, [spec_with(owner=owner, allowed_files=["docs/other.md"])])
    with pytest.raises(ValueError, match="ownership conflict"):
        validate_owners(spec, [spec_with(allowed_files=["docs/other.md"])])


def test_pinned_state_archive_and_generation(tmp_path: Path) -> None:
    snapshot = trusted_snapshot()
    assert (ROOT / "CURRENT_STATE.md").read_text() == render(snapshot)
    assert snapshot["issues"][0]["state"] == "closed"
    assert snapshot["harness_stage"] in render(snapshot)
    assert snapshot["later_gates"] in render(snapshot)
    (tmp_path / "docs/harness").mkdir(parents=True)
    source = ROOT / "docs/harness/state_snapshot.json"
    edited = copy.deepcopy(snapshot)
    edited["harness_stage"] = "H5 PASS"
    (tmp_path / source.relative_to(ROOT)).write_text(json.dumps(edited))
    with pytest.raises(ValueError, match="observation changed"):
        trusted_snapshot(tmp_path)
