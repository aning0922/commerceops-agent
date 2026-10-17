"""Offline tooling rejection/exit/cleanup tests, never business-PG acceptance evidence."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from tests.e2e.web.m1_acceptance_capture import (
    QUERIES,
    CaptureContext,
    CaptureFailure,
    canonical_digest,
    capture_worker,
    validate_base_readback,
    validate_worker,
    verify_t6_association,
    verify_t6_outbox,
)
from tests.e2e.web.m1_acceptance_driver import (
    NATIVE_COUNTERS,
    PROCESS_RESTART_SCOPE,
    STAGES,
    ZERO_REAL_COUNTERS,
    CleanupPlan,
    CleanupResult,
    CommandResult,
    Ledger,
    StageFailure,
    cleanup_owned,
    command,
    consume_stage,
    controlled_environment,
    reap_owned_processes,
    run_consumer,
    safe_failure,
    ui_command,
    validate_app_lifecycle,
    validate_restart_epochs,
    validate_transport_counters,
    verify_container,
    write_private_json,
)

pytestmark = pytest.mark.offline
ROOT = Path(__file__).resolve().parents[3]


def uid(number: int) -> str:
    return str(UUID(int=number))


def context() -> CaptureContext:
    return CaptureContext(
        "0016_p4_clarification_requests",
        uid(1),
        uid(2),
        uid(3),
        uid(10),
        uid(4),
        uid(5),
        2,
        (uid(3),),
        request_key=uid(6),
        case_kind="batch_twenty_items",
        expected_item_count=20,
        expected_quantity_total="2000",
    )


def semantic_fixture() -> tuple[dict[str, Any], dict[str, Any]]:
    """Pure validator input, not a synthetic production DB or final fixture producer."""
    c = context()
    resolution = {
        "request_key": c.request_key,
        "action": "close",
        "reason": "LAB checked",
        "resolved_by": c.principal_id,
        "resolved_at": "2026-10-15T00:00:00Z",
        "before_version": 1,
        "after_version": 2,
        "resolution_payload_hash": "a" * 64,
        "resolution_id": uid(7),
    }
    receipt = {
        "request_key": c.request_key,
        "duplicate": False,
        "item": {"item_id": c.item_id, "state": "closed", "version": 2},
        "resolution": resolution,
    }
    items = [
        {
            "id": uid(n),
            "sku_key": str(n),
            "task_id": c.task_id,
            "execution_id": uid(8),
            "status": "closed" if n == 10 else "open",
            "version": 2 if n == 10 else 1,
            "quantity": "100",
            "resolved_by": c.principal_id,
            "resolved_identity_id": c.identity_id,
            "resolved_auth_version": 2,
            "resolution_request_key": c.request_key,
            "resolution_reason": "LAB checked",
            "resolution_payload_hash": "a" * 64,
            "resolution_id": uid(7),
            "resolved_at": "2026-10-15T00:00:00+00:00",
        }
        for n in range(10, 30)
    ]
    data: dict[str, Any] = {
        "TASK": [{"id": c.task_id, "state": "completed"}],
        "IDENTITY": [
            {
                "principal_id": c.principal_id,
                "enabled": True,
                "auth_version": 2,
                "identity_id": c.identity_id,
                "provider": "web",
            }
        ],
        "PLANS": [{"id": uid(40), "canonical_hash_matches": True, "plan_hash": "b" * 64}],
        "APPROVALS": [
            {"id": uid(41), "plan_id": uid(40), "plan_hash": "b" * 64, "status": "approved"}
        ],
        "EXECUTIONS": [
            {
                "id": uid(8),
                "status": "completed",
                "plan_id": uid(40),
                "approval_id": uid(41),
                "item_ids": [uid(n) for n in range(10, 30)],
            }
        ],
        "ITEMS": items,
        "REQUEST": [
            {
                "task_id": c.task_id,
                "request_hash": "a" * 64,
                "result": {"resolution": copy.deepcopy(resolution)},
            }
        ],
        "ITEM_AUDIT": [
            {
                "actor_id": c.principal_id,
                "source": "replenishment",
                "action": "item_closed",
                "task_id": c.task_id,
                "entity_id": c.item_id,
            }
        ],
    }
    return {"queries": {k: {"status": "PASSED", "rows": v} for k, v in data.items()}}, receipt


def complete_cleanup() -> CleanupResult:
    return CleanupResult(
        commands=[{"exit_code": 0}],
        worker_confirmed=True,
        processes_reaped=True,
        pg_running=False,
        pg_pid=0,
        containers=[],
        networks=[],
        volumes=["own_pg_data"],
        listeners={"32001": False, "32002": False},
        expected_volume="own_pg_data",
        down_attempted=True,
        down_completed_no_v=True,
    )


def ledger(directory: Path) -> Ledger:
    directory.chmod(0o700)
    return Ledger(directory, "synthetic-run-001", "a" * 40, "b" * 40, "c" * 64)


def test_fixed_queries_parameterized_scoped_and_no_known_dto_columns() -> None:
    assert len({q.query_id for q in QUERIES}) == len(QUERIES)
    for q in QUERIES:
        assert q.sql.startswith("SELECT ") and q.sql.count("%s") == len(q.parameters)
        assert "outcome" not in q.sql and "max_attempts" not in q.sql
        assert ";" not in q.sql
        if q.query_id.startswith("CP_"):
            assert "thread_id=ANY(%s::text[])" in q.sql
    request = next(q for q in QUERIES if q.query_id == "REQUEST")
    assert "request_hash" in request.sql and ",status" not in request.sql


@pytest.mark.parametrize(
    "change",
    [
        {"auth_version": True},
        {"task_id": "not-uuid"},
        {"checkpoint_threads": ()},
        {"checkpoint_threads": ("bad%wildcard",)},
        {"revision": "future"},
    ],
)
def test_context_rejects_unregistered_types_and_scopes(change: dict[str, Any]) -> None:
    with pytest.raises(CaptureFailure):
        replace(context(), **change)


@pytest.mark.parametrize(
    "change",
    [
        {"case_kind": "unknown_case"},
        {"case_kind": "recover_single_item"},
        {"expected_item_count": True},
        {"expected_item_count": 19},
        {"expected_quantity_total": "100"},
        {"expected_quantity_total": "NaN"},
        {"expected_quantity_total": 2000},
    ],
)
def test_case_has_no_fallback_or_default(change: dict[str, Any]) -> None:
    with pytest.raises(CaptureFailure, match="CASE_CONTEXT_INVALID"):
        replace(context(), **change)


def test_single_item_case_exact_target_transition_is_separate_from_twenty_gate() -> None:
    snapshot, receipt = semantic_fixture()
    single = replace(
        context(),
        case_kind="recover_single_item",
        expected_item_count=1,
        expected_quantity_total="100",
    )
    snapshot["queries"]["ITEMS"]["rows"] = snapshot["queries"]["ITEMS"]["rows"][:1]
    snapshot["queries"]["EXECUTIONS"]["rows"][0]["item_ids"] = [single.item_id]
    verify_t6_association(snapshot, single, receipt, "LAB checked", "a" * 64)
    with pytest.raises(CaptureFailure, match="ITEM_SET_INVALID"):
        verify_t6_association(snapshot, context(), receipt, "LAB checked", "a" * 64)
    wrong_total = replace(single, expected_quantity_total="2000")
    with pytest.raises(CaptureFailure, match="ITEM_SET_INVALID"):
        verify_t6_association(snapshot, wrong_total, receipt, "LAB checked", "a" * 64)
    assert single.scope()["case_kind"] == "recover_single_item"
    assert context().scope()["expected_item_count"] == 20


def test_native_receipt_semantic_identity_audit_link_and_timestamp_equivalence() -> None:
    snapshot, receipt = semantic_fixture()
    verify_t6_association(snapshot, context(), receipt, "LAB checked", "a" * 64)


@pytest.mark.parametrize(
    "part",
    [
        "reason",
        "identity",
        "auth",
        "key",
        "hash",
        "audit",
        "other_item",
        "request_result",
        "timestamp",
    ],
)
def test_receipt_or_pg_mismatch_cannot_pass(part: str) -> None:
    snapshot, receipt = semantic_fixture()
    item = snapshot["queries"]["ITEMS"]["rows"][0]
    if part == "reason":
        item["resolution_reason"] = "different"
    elif part == "identity":
        item["resolved_identity_id"] = uid(99)
    elif part == "auth":
        item["resolved_auth_version"] = 1
    elif part == "key":
        receipt["request_key"] = uid(99)
    elif part == "hash":
        item["resolution_payload_hash"] = "b" * 64
    elif part == "audit":
        snapshot["queries"]["ITEM_AUDIT"]["rows"] *= 2
    elif part == "other_item":
        snapshot["queries"]["ITEMS"]["rows"][1]["status"] = "closed"
    elif part == "request_result":
        snapshot["queries"]["REQUEST"]["rows"][0]["result"]["resolution"]["reason"] = "different"
    elif part == "timestamp":
        receipt["resolution"]["resolved_at"] = "2026-10-15T00:00:01Z"
    with pytest.raises(CaptureFailure):
        verify_t6_association(snapshot, context(), receipt, "LAB checked", "a" * 64)


def test_base_binding_does_not_relabel_native_controlled_shape_as_real_transport() -> None:
    snapshot, _ = semantic_fixture()
    row = {
        "outbox_id": uid(80),
        "item_id": context().item_id,
        "target_key": "synthetic",
        "version": 1,
        "status": "verified",
        "complete_unique_verified": True,
        "observed_version": 1,
        "verification_mode": "controlled_sdk",
        "external_id": "synthetic-record",
        "projection_hash": "d" * 64,
    }
    snapshot["queries"]["PROJECTIONS"] = {"status": "PASSED", "rows": [row]}
    snapshot["queries"]["ANCHOR"] = {
        "status": "PASSED",
        "rows": [
            {
                "target_key": "synthetic",
                "external_id": "synthetic-record",
                "original_outbox_id": uid(80),
            }
        ],
    }
    validate_base_readback(
        snapshot,
        context(),
        version=1,
        target_key="synthetic",
        external_id="synthetic-record",
        verification_mode="controlled_sdk",
        native_projection_hash="d" * 64,
    )
    row["observed_version"] = 2
    with pytest.raises(CaptureFailure):
        validate_base_readback(
            snapshot,
            context(),
            version=1,
            target_key="synthetic",
            external_id="synthetic-record",
            verification_mode="controlled_sdk",
            native_projection_hash="d" * 64,
        )


def test_real_zero_native_nonzero_counters_are_separate() -> None:
    values = {**dict.fromkeys(ZERO_REAL_COUNTERS, 0), **dict.fromkeys(NATIVE_COUNTERS, 3)}
    validate_transport_counters(values)
    values["platform_http_egress"] = 1
    with pytest.raises(StageFailure):
        validate_transport_counters(values)
    values["platform_http_egress"] = False
    with pytest.raises(StageFailure):
        validate_transport_counters(values)


def test_progress_never_pass_and_final_requires_all_stages_and_cleanup(tmp_path: Path) -> None:
    result = ledger(tmp_path)
    assert all(s["status"] == "NOT_RUN" for s in result.stages.values())
    result.enter("source")
    assert json.loads((tmp_path / "stages.in-progress.json").read_text())["business_pass"] is False
    write_private_json(tmp_path / "source.json", {"unit_evidence": True})
    result.record("source", "source.json")
    assert not (tmp_path / "result.json").exists()
    assert result.finish(complete_cleanup()) == 1
    final = json.loads((tmp_path / "result.json").read_text())
    assert final["status"] == "FAILED" and final["stages"]["ui_submit"]["status"] == "NOT_RUN"


def test_local_stage_success_written_only_after_verified_cleanup(tmp_path: Path) -> None:
    result = ledger(tmp_path)
    for stage in STAGES:
        if stage == "cleanup":
            continue
        write_private_json(tmp_path / (stage + ".json"), {"unit_evidence": True})
        result.enter(stage)
        result.record(stage, stage + ".json")
    assert not (tmp_path / "result.json").exists()
    assert result.finish(complete_cleanup()) == 0
    final = json.loads((tmp_path / "result.json").read_text())
    assert final["whole_candidate_pass"] is False and final["status"] == "PASSED"


@pytest.mark.parametrize(
    "field,value",
    [
        ("pg_pid", None),
        ("worker_confirmed", None),
        ("down_completed_no_v", False),
        ("networks", None),
        ("processes_reaped", False),
    ],
)
def test_cleanup_unknowns_are_not_zero_or_pass(field: str, value: Any, tmp_path: Path) -> None:
    clean = complete_cleanup()
    setattr(clean, field, value)
    assert not clean.success
    result = ledger(tmp_path)
    assert result.finish(clean) == 1


def test_oserror_timeout_and_exception_messages_not_public(tmp_path: Path) -> None:
    marker = "private-marker-not-for-output"
    assert marker not in json.dumps(safe_failure(OSError(2, marker), "source"))
    assert marker not in json.dumps(safe_failure(RuntimeError(marker), "source"))
    missing = command(
        [str(tmp_path / "not-installed")], cwd=tmp_path, env=controlled_environment({}), timeout=1
    )
    assert missing.code is None and missing.error_code == "OS_ERROR" and missing.errno == 2
    timeout = command(
        [sys.executable, "-c", "import time;time.sleep(1)"],
        cwd=tmp_path,
        env=controlled_environment({}),
        timeout=0.02,
    )
    assert timeout.code is None and timeout.error_code == "COMMAND_TIMEOUT"


def test_failure_still_cleans_up_when_result_directory_cannot_write(tmp_path: Path) -> None:
    result = ledger(tmp_path)
    called = []

    def fail() -> None:
        tmp_path.chmod(0o755)
        raise CaptureFailure("SQL_FAILED", "TASK", "42703")

    def cleanup() -> CleanupResult:
        called.append(True)
        return complete_cleanup()

    assert run_consumer(result, fail, cleanup) != 0 and called == [True]


@pytest.mark.parametrize("kind", ["load", "sql", "dto", "call", "capture", "timeout", "cleanup"])
def test_failing_consumer_actual_process_exit_nonzero(kind: str, tmp_path: Path) -> None:
    script = (
        "from pathlib import Path;import sys;"
        "from tests.e2e.web.m1_acceptance_driver import *;"
        "from tests.e2e.web.m1_acceptance_capture import CaptureFailure;"
        "p=Path(sys.argv[1]);p.chmod(0o700);"
        "l=Ledger(p,'synthetic-run-001','a'*40,'b'*40,'c'*64);"
        "def_bad=None\n"
        "def action():\n"
        " l.enter('source')\n"
        " if sys.argv[2]=='load':__import__('missing_acceptance_tool_module')\n"
        " if sys.argv[2]=='sql':raise CaptureFailure('SQL_FAILED','TASK','42703')\n"
        " if sys.argv[2]=='dto':\n"
        "  from commerceops.application.replenishment.contracts import ResolveInput\n"
        "  ResolveInput.model_validate({'reason':{'private-marker':'private-marker'}})\n"
        " if sys.argv[2]=='call':len(None)\n"
        " if sys.argv[2]=='cleanup':return\n"
        " if sys.argv[2]=='timeout':raise TimeoutError('private-marker')\n"
        " if sys.argv[2]=='capture':raise OSError(2,'private-marker')\n"
        " raise RuntimeError('private-marker')\n"
        "def cleanup():\n"
        " (p/'cleanup-called').write_text('yes')\n"
        " if sys.argv[2]=='cleanup':raise OSError(2,'private-marker')\n"
        " return CleanupResult()\n"
        "sys.exit(run_consumer(l,action,cleanup))"
    )
    env = controlled_environment({"PYTHONPATH": str(ROOT / "backend/src") + os.pathsep + str(ROOT)})
    child = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), kind],
        cwd=ROOT,
        env=env,
        capture_output=True,
        timeout=10,
    )
    assert child.returncode != 0 and (tmp_path / "cleanup-called").exists()
    assert b"private-marker" not in child.stdout + child.stderr
    final = json.loads((tmp_path / "result.json").read_text())
    assert not final["business_pass"] and final["stages"]["ui_submit"]["status"] == "NOT_RUN"
    if kind == "dto":
        assert final["failures"][0]["code"] == "DTO_INVALID" and final["failures"][0]["dto"]
    if kind == "sql":
        assert (
            final["failures"][0]["query_id"] == "TASK"
            and final["failures"][0]["sqlstate"] == "42703"
        )


def test_container_actual_identity_and_loopback_not_rendered_config() -> None:
    value: dict[str, Any] = {
        "Image": "sha256:" + "a" * 64,
        "Config": {"Labels": {"owner": "unit"}},
        "NetworkSettings": {"Ports": {"8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "32001"}]}},
    }
    verify_container(value, image_id=value["Image"], labels={"owner": "unit"}, no_host_ports=False)
    value["NetworkSettings"]["Ports"]["8000/tcp"][0]["HostIp"] = "0.0.0.0"  # noqa: S104 - rejection input
    with pytest.raises(StageFailure):
        verify_container(
            value, image_id=value["Image"], labels={"owner": "unit"}, no_host_ports=False
        )


def test_worker_cleanup_does_not_execute_task_snapshot() -> None:
    # This assertion protects a functional independence seam; PG execution is a separate suite.
    import inspect

    source = inspect.getsource(capture_worker)
    assert "business.business_tasks" not in source and "capture_snapshot" not in source


def test_new_owned_process_is_reaped_without_foreign_pid(tmp_path: Path) -> None:
    child = subprocess.Popen(
        [sys.executable, "-c", "import time;time.sleep(30)"],
        start_new_session=True,
        cwd=tmp_path,
        env=controlled_environment({}),
    )
    try:
        assert reap_owned_processes([child], time.monotonic() + 2)
        assert child.poll() is not None
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=3)


def test_canonical_digest_unicode_order() -> None:
    assert canonical_digest({"reason": "LAB 核对", "item": 1}) == canonical_digest(
        {"item": 1, "reason": "LAB 核对"}
    )


def test_native_dto_and_stage_diagnostics_omit_input_context_and_messages() -> None:
    from commerceops.application.replenishment.contracts import ResolveInput
    from pydantic import ValidationError

    marker = "private-marker-not-for-output"
    with pytest.raises(ValidationError) as caught:
        ResolveInput.model_validate({"reason": {marker: marker}})
    safe = safe_failure(caught.value, "ui_submit")
    assert safe["code"] == "DTO_INVALID" and safe["dto"]
    error = StageFailure(
        "ui_submit",
        "DTO_INVALID",
        sqlstate=marker,
        dto=[{"loc": [marker], "type": marker, "input": marker, "ctx": marker}],
    )
    staged = safe_failure(error, "ui_submit")
    assert staged["sqlstate"] is None and staged["dto"] == [
        {"loc": ["_field"], "type": "validation_error"}
    ]
    assert marker not in json.dumps([safe, staged])


@pytest.mark.parametrize("foreign,down_error", [(True, False), (False, True), (False, False)])
def test_cleanup_scope_and_failure_continue_independent_probes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    foreign: bool,
    down_error: bool,
) -> None:
    project = "m1tools-unit-001"
    labels = {"com.docker.compose.project": project, "run-owner": "this-run"}
    plan = CleanupPlan(
        project,
        project + "_pg_data",
        ("docker", "compose", "-p", project),
        ("docker",),
        tmp_path,
        {},
        labels,
        (32001, 32002),
    )
    calls: list[tuple[str, ...]] = []
    audited: list[bool] = []
    monkeypatch.setattr("tests.e2e.web.m1_acceptance_driver.listener_open", lambda _: False)

    def execute(argv: Any, **_: Any) -> CommandResult:
        args = tuple(argv)
        calls.append(args)
        if args[:4] == ("docker", "ps", "-a", "-q"):
            return CommandResult(0, "owned-container\n" if len(calls) == 1 else "")
        if args[:2] == ("docker", "inspect"):
            if "--format" in args:
                return CommandResult(0, json.dumps({"Running": False, "Pid": 0}))
            observed = {**labels, "com.docker.compose.service": "postgres"}
            if foreign:
                observed["run-owner"] = "another-run"
            return CommandResult(0, json.dumps([{"Config": {"Labels": observed}}]))
        if "down" in args and down_error:
            raise OSError(2, "private-marker")
        if args[:3] == ("docker", "volume", "ls"):
            return CommandResult(0, project + "_pg_data\n")
        return CommandResult(0)

    def audit() -> bool:
        audited.append(True)
        return True

    result = cleanup_owned(
        plan,
        audit,
        deadline_monotonic=time.monotonic() + 5,
        execute=execute,
    )
    assert any(c[:3] == ("docker", "network", "ls") for c in calls)
    assert any(c[:3] == ("docker", "volume", "ls") for c in calls)
    if foreign:
        assert not audited and not any("stop" in c or "down" in c for c in calls)
        assert not result.success and result.worker_confirmed is None
    elif down_error:
        assert audited and result.down_attempted and not result.down_completed_no_v
        assert not result.success
    else:
        assert audited and result.success
    assert "private-marker" not in json.dumps(result.safe())


def test_js_native_generated_schema_required_nullable_numeric_and_no_coercion() -> None:
    script = r"""
const fs=require('node:fs'),assert=require('node:assert/strict');
const {responseValidator}=require('./tests/e2e/web/m1_acceptance_ui.cjs');
const schema=JSON.parse(fs.readFileSync('frontend/lib/p3-read-schema.generated.json'));
const validate=responseValidator(schema,process.cwd()+'/frontend/node_modules');
const body={schema_version:'p3-web-v1',identity_mode:'anonymous_bootstrap',
server_time:'2026-10-15T00:00:00Z',trace_id:'00000000-0000-4000-8000-000000000001',
csrf_token:'a'.repeat(43),bootstrap_expires_at:null};
validate('GET','/api/v1/auth/csrf',200,body);
for (const value of [{...body,csrf_token:null},{...body,csrf_token:123},
{...body,trace_id:undefined},{...body,server_time:'yesterday'},
{...body,extra:'private-marker'}]) {
 assert.throws(()=>validate('GET','/api/v1/auth/csrf',200,value),e=>e.code==='DTO_INVALID');
}
// Numeric safety is applied before schema validation, without coercion/defaulting.
assert.throws(()=>validate('GET','/api/v1/auth/csrf',200,{...body,extra:9007199254740992}),
 e=>e.code==='DTO_NUMERIC_INVALID');
assert.equal(body.bootstrap_expires_at,null);
process.stdout.write('native-schema-regression-passed\n');
"""
    child = subprocess.run(
        [str(ROOT / ".tools/node/bin/node"), "-e", script],
        cwd=ROOT,
        env=controlled_environment({}),
        capture_output=True,
        timeout=15,
    )
    assert child.returncode == 0, child.stderr.decode()
    assert child.stdout == b"native-schema-regression-passed\n"


def test_js_helper_invalid_source_actual_process_nonzero_before_browser(tmp_path: Path) -> None:
    import hashlib

    tmp_path.chmod(0o700)
    input_file = tmp_path / "input.json"
    write_private_json(input_file, {"contract": "wrong", "private_marker": "never-print-this"})
    child = subprocess.run(
        [
            str(ROOT / ".tools/node/bin/node"),
            str(ROOT / "tests/e2e/web/m1_acceptance_ui.cjs"),
            str(input_file),
            hashlib.sha256(input_file.read_bytes()).hexdigest(),
        ],
        cwd=ROOT,
        env=controlled_environment({}),
        capture_output=True,
        timeout=15,
    )
    assert child.returncode != 0
    diagnostic = json.loads(child.stderr)
    assert diagnostic == {"status": "FAILED", "code": "INPUT_INVALID", "dto": None}
    assert b"never-print-this" not in child.stdout + child.stderr


def test_consumer_rejects_unknown_stage_before_any_shared_import() -> None:
    with pytest.raises(StageFailure, match="STAGE_INVALID"):
        consume_stage("arbitrary", {}, handoff_ref={})


def test_ui_timeout_reaps_its_new_process_group(tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"
    script = (
        "import subprocess,sys,time;from pathlib import Path;"
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);"
        "Path(sys.argv[1]).write_text(str(p.pid));time.sleep(30)"
    )
    result = ui_command(
        [sys.executable, "-c", script, str(pid_file)],
        cwd=tmp_path,
        env=controlled_environment({}),
        timeout=0.15,
    )
    assert result.code is None and result.error_code == "COMMAND_TIMEOUT"
    pid = int(pid_file.read_text())
    # The grandchild belonged to the group allocated inside ui_command. A killed
    # process may briefly be a zombie until its new parent reaps it.
    probe = subprocess.run(["ps", "-p", str(pid), "-o", "stat="], capture_output=True, timeout=2)
    assert probe.returncode != 0 or probe.stdout.strip().startswith(b"Z")


def test_native_t6_outbox_delta_cannot_be_fabricated_from_projection() -> None:
    c = context()
    old = {"id": uid(60)}
    added: dict[str, Any] = {
        "id": uid(61),
        "organization_id": c.organization_id,
        "shop_id": c.shop_id,
        "task_id": c.task_id,
        "destination": "bitable",
        "aggregate_id": c.item_id,
        "aggregate_version": 2,
        "operation": "item_projection",
        "dedupe_key": f"item:{c.item_id}:2",
        "request_hash": "a" * 64,
        "payload": {
            "schema_version": "p3-web-v1",
            "item_id": c.item_id,
            "version": 2,
            "state": "closed",
        },
        "provider_idempotency_key": "00000000-0000-4000-8000-000000000001",
        "status": "pending",
        "attempts": 0,
    }
    before = {"queries": {"OUTBOX": {"status": "PASSED", "rows": [old]}}}
    after = {"queries": {"OUTBOX": {"status": "PASSED", "rows": [old, added]}}}
    assert verify_t6_outbox(before, after, c, "a" * 64) == added
    added["payload"]["state"] = "open"
    with pytest.raises(CaptureFailure, match="OUTBOX_BINDING_INVALID"):
        verify_t6_outbox(before, after, c, "a" * 64)


def native_app_epoch(index: int = 1) -> dict[str, Any]:
    """Native receipt shape from committed e2626df; unit input, never runtime proof."""
    return {
        "epoch": "app",
        "organization": uid(1),
        "owner": uid(100 + index),
        "process_started_id": uid(200 + index),
        "active_workers": 1,
        "reaped": False,
        "pid": 5000 + index,
        "host": "unit-runner",
        "pid_namespace": "pid:[123]",
        "start_ticks": str(9000 + index),
        "cmdline_sha256": "a" * 64,
    }


def native_lifecycle_result(action: str) -> tuple[dict[str, Any], dict[str, Any]]:
    h: dict[str, Any] = {
        "resource": {"volume": "unit_pg_data", "container_ids": ["b" * 64]},
        "fixture": {"organization_id": uid(1)},
        "worker": {"owner": uid(99)},
    }
    old = native_app_epoch()
    stopped = {**old, "reaped": True, "termination_id": uid(300)}
    value: dict[str, Any] = {
        "epoch": stopped if action == "stop" else native_app_epoch(2),
        "active_workers": 0 if action == "stop" else 1,
        "reaped": action != "start",
        "api_ready": action != "stop",
        **h["resource"],
    }
    if action != "stop":
        value.update(
            stopped_epoch=stopped if action == "restart" else None,
            restart_scope=PROCESS_RESTART_SCOPE,
        )
    return value, h


@pytest.mark.parametrize("action", ["start", "stop", "restart"])
def test_committed_lifecycle_distinguishes_current_worker_from_reaped_old_epoch(
    action: str,
) -> None:
    value, handoff = native_lifecycle_result(action)
    validate_app_lifecycle(value, action, handoff)
    if action == "restart":
        assert value["reaped"] is True and value["epoch"]["reaped"] is False
        assert "stopped_reaped" not in value
        validate_restart_epochs(native_app_epoch(), value["stopped_epoch"], value["epoch"])
    if action == "stop":
        # The receipt retains its historical started count; the outer current count is zero.
        assert value["epoch"]["active_workers"] == 1 and value["active_workers"] == 0


@pytest.mark.parametrize(
    "fault",
    [
        "missing_old",
        "missing_termination",
        "wrong_count",
        "bool_count",
        "old_reap_unproved",
        "new_marked_reaped",
        "missing_started",
        "wrong_container",
        "compose_scope",
    ],
)
def test_lifecycle_missing_or_mixed_epoch_evidence_fails_closed(fault: str) -> None:
    value, handoff = native_lifecycle_result("restart")
    if fault == "missing_old":
        del value["stopped_epoch"]
    elif fault == "missing_termination":
        del value["stopped_epoch"]["termination_id"]
    elif fault == "wrong_count":
        value["active_workers"] = 2
    elif fault == "bool_count":
        value["active_workers"] = True
    elif fault == "old_reap_unproved":
        value["reaped"] = False
    elif fault == "new_marked_reaped":
        value["epoch"]["reaped"] = True
    elif fault == "missing_started":
        del value["epoch"]["process_started_id"]
    elif fault == "wrong_container":
        value["container_ids"] = ["c" * 64]
    else:
        value["restart_scope"] = "all Compose containers rebuilt"
    with pytest.raises(StageFailure):
        validate_app_lifecycle(value, "restart", handoff)


@pytest.mark.parametrize("fault", ["old_pid", "same_process", "same_owner", "foreign_namespace"])
def test_restart_requires_original_stop_and_distinct_new_process(fault: str) -> None:
    value, _ = native_lifecycle_result("restart")
    old = native_app_epoch()
    if fault == "old_pid":
        value["stopped_epoch"]["pid"] += 1
    elif fault == "same_process":
        value["epoch"].update(pid=old["pid"], start_ticks=old["start_ticks"])
    elif fault == "same_owner":
        value["epoch"]["owner"] = old["owner"]
    else:
        value["epoch"]["pid_namespace"] = "pid:[foreign]"
    with pytest.raises(StageFailure, match="RESTART_EPOCH_INVALID"):
        validate_restart_epochs(old, value["stopped_epoch"], value["epoch"])


@pytest.mark.parametrize("mismatch", [None, "started", "termination"])
def test_worker_pg_audit_ids_bind_the_native_receipt(mismatch: str | None) -> None:
    epoch = {**native_app_epoch(), "reaped": True, "termination_id": uid(300)}
    process = {k: epoch[k] for k in ("pid", "host", "pid_namespace")}
    events = [
        {"id": epoch["process_started_id"], "action": "started", "after_state": process},
        {"id": uid(299), "action": "stopped", "after_state": process},
        {"id": epoch["termination_id"], "action": "termination_confirmed", "after_state": {}},
    ]
    value = {"owner": epoch["owner"], "organization_id": epoch["organization"], "events": events}
    if mismatch:
        events[0 if mismatch == "started" else -1]["id"] = uid(999)
        with pytest.raises(CaptureFailure, match="WORKER_AUDIT_BINDING_INVALID"):
            validate_worker(value, epoch, stopped=True)
    else:
        validate_worker(value, epoch, stopped=True)


def test_js_launch_uses_the_hash_checked_executable_and_rejects_before_launch(
    tmp_path: Path,
) -> None:
    # The fake file is never executed; this is a binding/rejection unit test, not
    # evidence of a real browser process. The real PID/binary/stop proof is captured
    # only by the existing CJS helper in the final integrated page chain.
    binary = tmp_path / "unit-placeholder-browser"
    binary.write_bytes(b"unit placeholder, never executed")
    script = r"""
const fs=require('node:fs'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const {launchBoundBrowser}=require('./tests/e2e/web/m1_acceptance_ui.cjs');
const file=process.argv[1];
const hash=crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const bound={browser_executable:file,browser_sha256:hash};let launches=[];
const chromium={executablePath:()=>file,
 launch:async options=>{launches.push(options);return 'unit-only';}};
(async()=>{
 assert.equal(await launchBoundBrowser(chromium,bound,1234),'unit-only');
 assert.equal(launches.length,1);assert.equal(launches[0].executablePath,file);
 assert.equal(launches[0].headless,true);assert.equal(launches[0].timeout,1234);
 assert(launches[0].args.includes('--disable-background-networking'));
 launches=[];
 await assert.rejects(launchBoundBrowser(chromium,{...bound,browser_sha256:'0'.repeat(64)},1234),
  error=>error.code==='BROWSER_SOURCE_MISMATCH');
 await assert.rejects(launchBoundBrowser({...chromium,executablePath:()=>file+'-other'},bound,1234),
  error=>error.code==='BROWSER_SOURCE_MISMATCH');
 assert.equal(launches.length,0);process.stdout.write('binding-unit-only-no-browser-started\n');
})().catch(()=>{process.stderr.write('binding-unit-failed\n');process.exitCode=1;});
"""
    child = subprocess.run(
        [str(ROOT / ".tools/node/bin/node"), "-e", script, str(binary)],
        cwd=ROOT,
        env=controlled_environment({}),
        capture_output=True,
        timeout=15,
    )
    assert child.returncode == 0, child.stderr.decode()
    assert child.stdout == b"binding-unit-only-no-browser-started\n"


def test_cold_private_home_binds_only_the_registered_browser_cache(tmp_path: Path) -> None:
    import hashlib

    home = tmp_path / "private-home"
    home.mkdir(mode=0o700)
    env = controlled_environment({"HOME": str(home), "TMPDIR": str(home)})
    node = str(ROOT / ".tools/node/bin/node")
    pw = str(ROOT / "frontend/node_modules/playwright")
    metadata = subprocess.run(
        [
            node,
            "-e",
            "process.stdout.write(require(process.argv[1]).chromium.executablePath())",
            pw,
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        timeout=10,
        check=True,
    )
    original = Path(metadata.stdout.decode())
    start = next(i for i, part in enumerate(original.parts) if part.startswith("chromium-"))
    cache = tmp_path / "approved-cache"
    binary = cache.joinpath(*original.parts[start:])
    binary.parent.mkdir(parents=True, mode=0o700)
    binary.write_bytes(b"unit placeholder only; never executed")
    wrong_revision = tmp_path.joinpath("wrong-cache", "chromium-0", *original.parts[start + 1 :])
    wrong_revision.parent.mkdir(parents=True, mode=0o700)
    wrong_revision.write_bytes(binary.read_bytes())
    bound = {
        "playwright_root": pw,
        "playwright_version": "1.64.0",
        "browser_executable": str(binary),
        "browser_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
    }
    script = r"""
const assert=require('node:assert/strict');
const {loadBoundChromium}=require('./tests/e2e/web/m1_acceptance_ui.cjs');
const input=JSON.parse(process.argv[1]),home=process.env.HOME;
const bound=loadBoundChromium(input);
assert.equal(bound.chromium.executablePath(),input.browser_executable);
assert.equal(process.env.HOME,home);assert.equal(bound.source.private_home_preserved,true);
assert.equal(bound.source.install_or_fallback,false);
assert.throws(()=>loadBoundChromium({...input,browser_sha256:'0'.repeat(64)}),
 error=>error.code==='BROWSER_SOURCE_MISMATCH');
assert.throws(()=>loadBoundChromium({...input,browser_executable:process.argv[2]}),
 error=>error.code==='BROWSER_CACHE_SOURCE_INVALID');
process.stdout.write(JSON.stringify({cache_root:bound.source.cache_root,metadata_only:true}));
"""
    child = subprocess.run(
        [node, "-e", script, json.dumps(bound), str(wrong_revision)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        timeout=15,
    )
    assert child.returncode == 0, child.stderr.decode()
    assert json.loads(child.stdout) == {"cache_root": str(cache), "metadata_only": True}
    assert str(original) != str(binary)


def test_browser_process_receipt_rejects_the_observer_pid_before_os_lookup() -> None:
    script = r"""
const assert=require('node:assert/strict');
const {browserProcessReceipt}=require('./tests/e2e/web/m1_acceptance_ui.cjs');
const browser={newBrowserCDPSession:async()=>({send:async()=>({processInfo:[
 {type:'browser',id:process.pid}]})})};
(async()=>{
 await assert.rejects(browserProcessReceipt(browser,{},1000),
  error=>error.code==='BROWSER_PROCESS_INVALID');
 process.stdout.write('own-node-pid-rejected-no-browser\n');
})().catch(()=>{process.stderr.write('pid-rejection-unit-failed\n');process.exitCode=1;});
"""
    child = subprocess.run(
        [str(ROOT / ".tools/node/bin/node"), "-e", script],
        cwd=ROOT,
        env=controlled_environment({}),
        capture_output=True,
        timeout=10,
    )
    assert child.returncode == 0, child.stderr.decode()
    assert child.stdout == b"own-node-pid-rejected-no-browser\n"


def test_original_get_uses_native_resolve_query_and_saves_only_safe_diagnostics() -> None:
    script = r"""
const fs=require('node:fs'),assert=require('node:assert/strict');
const h=require('./tests/e2e/web/m1_acceptance_ui.cjs');
const native=JSON.parse(fs.readFileSync('docs/contracts/p3-openapi.json'));
const schema=JSON.parse(fs.readFileSync('frontend/lib/p3-read-schema.generated.json'));
const validate=h.responseValidator(schema,process.cwd()+'/frontend/node_modules');
const params=native.paths['/api/v1/requests/{request_key}'].get.parameters;
const operation=params.find(p=>p.name==='operation'&&p.in==='query');
assert.equal(operation.required,true);assert(operation.schema.enum.includes('resolve'));
const key='00000000-0000-4000-8000-000000000001',item='00000000-0000-4000-8000-000000000002';
const marker='private-marker-not-for-diagnostics';let calls=0;
(async()=>{
 global.fetch=async (url,options)=>{
  calls++;const u=new URL(url);assert.equal(options.method,'GET');
  assert.equal(options.body,undefined);assert.equal(options.credentials,'include');
  assert.equal(options.cache,'no-store');assert(u.pathname.endsWith('/'+key));
  assert.deepEqual([...u.searchParams],[['operation','resolve']]);
  return new Response(JSON.stringify({schema_version:'p3-web-v1',server_time:null,
   trace_id:key,error:{code:'RESOURCE_NOT_FOUND',safe_message:marker,retryable:false,receipt:null}}),
   {status:404});
 };
 const observed=await h.fetchOriginalResolve({api:'http://127.0.0.1:39001',key,timeout:1000});
 const safe=h.inspectOriginalResolve(observed,validate,key,item);
 assert.equal(calls,1);assert.equal(safe.http_status,404);assert.equal(safe.schema_valid,true);
 assert.equal(safe.code,'ORIGINAL_GET_FAILED');assert.equal(safe.accepted,false);
 assert(!JSON.stringify(safe).includes(marker));assert(!JSON.stringify(safe).includes(key));
 const malformed=h.inspectOriginalResolve({...observed,status:200},validate,key,item);
 assert.equal(malformed.code,'ORIGINAL_GET_DTO_INVALID');assert(malformed.dto.length);
 assert(!JSON.stringify(malformed).includes(marker));
 global.fetch=async()=>new Response(marker,{status:503});
 const nonJSON=h.inspectOriginalResolve(await h.fetchOriginalResolve({
  api:'http://127.0.0.1:39001',key,timeout:1000}),validate,key,item);
 assert.equal(nonJSON.http_status,503);assert.equal(nonJSON.body_json,false);
 assert.equal(nonJSON.code,'ORIGINAL_GET_JSON_INVALID');assert(!JSON.stringify(nonJSON).includes(marker));
 global.fetch=async()=>{throw new Error(marker);};
 const network=h.inspectOriginalResolve(await h.fetchOriginalResolve({
  api:'http://127.0.0.1:39001',key,timeout:1000}),validate,key,item);
 assert.equal(network.http_status,null);assert.equal(network.code,'ORIGINAL_GET_NETWORK_FAILED');
 process.stdout.write('native-query-and-safe-diagnostics-unit-passed\n');
})().catch(()=>{process.stderr.write('original-contract-unit-failed\n');process.exitCode=1;});
"""
    child = subprocess.run(
        [str(ROOT / ".tools/node/bin/node"), "-e", script],
        cwd=ROOT,
        env=controlled_environment({}),
        capture_output=True,
        timeout=15,
    )
    assert child.returncode == 0, child.stderr.decode()
    assert child.stdout == b"native-query-and-safe-diagnostics-unit-passed\n"


def test_http_status_diagnostic_survives_child_exit_without_payload_or_bool_coercion(
    tmp_path: Path,
) -> None:
    script = (
        "process.stderr.write(JSON.stringify({status:'FAILED',code:'ORIGINAL_GET_DTO_INVALID',"
        "http_status:403,dto:[{loc:['receipt'],type:'required',input:'private-marker'}]}));"
        "process.exitCode=1;"
    )
    result = ui_command(
        [str(ROOT / ".tools/node/bin/node"), "-e", script],
        cwd=ROOT,
        env=controlled_environment({}),
        timeout=10,
    )
    assert result.code == 1 and result.diagnostic
    failure = safe_failure(
        StageFailure(
            "t6",
            result.diagnostic["code"],
            http_status=result.diagnostic["http_status"],
            dto=result.diagnostic["dto"],
        ),
        "t6",
    )
    assert failure["http_status"] == 403 and failure["dto"] == [
        {"loc": ["receipt"], "type": "required"}
    ]
    assert "private-marker" not in json.dumps(failure)
    assert "http_status" not in safe_failure(
        StageFailure("t6", "HTTP_FAILED", http_status=True), "t6"
    )


def test_browser_stop_poll_is_bounded_and_requires_observed_esrch() -> None:
    script = r"""
const assert=require('node:assert/strict');
const {pollProcessAbsent}=require('./tests/e2e/web/m1_acceptance_ui.cjs');
(async()=>{
 let sequence=[false,null,true];
 const ended=await pollProcessAbsent(123,Date.now()+1000,()=>sequence.shift());
 assert.equal(ended.pid_absent,true);assert.equal(ended.final_state,'ABSENT');
 assert.equal(ended.timed_out,false);assert.equal(ended.probes,3);
 const unknown=await pollProcessAbsent(123,Date.now()+10,()=>null);
 assert.equal(unknown.pid_absent,null);assert.equal(unknown.final_state,'UNKNOWN');
 assert.equal(unknown.timed_out,true);
 const present=await pollProcessAbsent(123,Date.now()-1,()=>false);
 assert.equal(present.pid_absent,false);assert.equal(present.final_state,'PRESENT');
 assert.equal(present.timed_out,true);assert.equal(present.probes,1);
 process.stdout.write('bounded-stop-poll-unit-passed\n');
})().catch(()=>{process.stderr.write('stop-poll-unit-failed\n');process.exitCode=1;});
"""
    child = subprocess.run(
        [str(ROOT / ".tools/node/bin/node"), "-e", script],
        cwd=ROOT,
        env=controlled_environment({}),
        capture_output=True,
        timeout=10,
    )
    assert child.returncode == 0, child.stderr.decode()
    assert child.stdout == b"bounded-stop-poll-unit-passed\n"


def test_snapshot_contract_keeps_role_and_queries_in_one_rr_scope_and_recovers_savepoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from contextlib import contextmanager
    from types import SimpleNamespace

    from tests.e2e.web import m1_acceptance_capture as capture

    class MissingRelation(Exception):
        sqlstate = "42P01"

    class ContractDB:
        """Protocol double only; the separate owned PG evidence tests real MVCC."""

        def __init__(self) -> None:
            self.info = SimpleNamespace(transaction_status=0)
            self.depth, self.begins, self.recovered = 0, 0, 0
            self.rr = False

        @contextmanager
        def transaction(self) -> Any:
            outer = self.depth == 0
            self.depth += 1
            self.begins += int(outer)
            try:
                yield
            except MissingRelation:
                assert self.depth == 2
                self.recovered += 1
                raise
            finally:
                self.depth -= 1

        def execute(self, sql: str, *_: Any) -> Any:
            assert self.depth in (1, 2)
            if sql.startswith("SET TRANSACTION"):
                self.rr = "REPEATABLE READ" in sql and "READ ONLY" in sql
            if "current_setting" in sql:
                return SimpleNamespace(
                    fetchone=lambda: {
                        "isolation": "repeatable read" if self.rr else "read committed",
                        "read_only": "on",
                    }
                )
            if "current_user::text" in sql:
                assert self.depth == 1 and self.rr
                return SimpleNamespace(
                    fetchone=lambda: {
                        "current_role": "commerceops_app",
                        "session_role": "commerceops_app",
                    }
                )
            if "FROM pg_roles" in sql:
                assert self.depth == 1
                return SimpleNamespace(
                    fetchone=lambda: {
                        "rolsuper": False,
                        "rolcreatedb": False,
                        "rolcreaterole": False,
                    }
                )
            if sql == "SELECT missing":
                raise MissingRelation
            if sql == "SELECT n":
                assert self.depth == 2 and self.recovered == 1
                return SimpleNamespace(
                    description=[SimpleNamespace(name="n", type_code=23)],
                    fetchall=lambda: [{"n": 1}],
                )
            return None

    monkeypatch.setattr(
        capture,
        "QUERIES",
        (
            capture.Query(
                "ABSENT",
                "SELECT missing",
                (),
                capture.fields(n=23),
                minimum_revision=capture.REVISIONS[1],
            ),
            capture.Query("FOLLOWING", "SELECT n", (), capture.fields(n=23)),
        ),
    )
    db = ContractDB()
    result = capture.capture_snapshot(db, replace(context(), revision=capture.REVISIONS[0]))
    assert db.begins == 1 and db.recovered == 1 and db.depth == 0
    assert result["transaction"] == {"isolation": "repeatable read", "read_only": "on"}
    assert result["queries"]["ABSENT"]["status"] == "EXPECTED_ABSENT"
    assert result["queries"]["FOLLOWING"]["rows"] == [{"n": 1}]


def test_snapshot_rejects_an_already_open_transaction_before_any_query() -> None:
    from types import SimpleNamespace

    from tests.e2e.web.m1_acceptance_capture import capture_snapshot

    with pytest.raises(CaptureFailure, match="FRESH_CONNECTION_REQUIRED"):
        capture_snapshot(SimpleNamespace(info=SimpleNamespace(transaction_status=2)), context())
