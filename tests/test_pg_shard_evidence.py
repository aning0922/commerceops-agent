"""Opt-in N-way PG evidence: pure command simulation, never real speed/PG proof."""

import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pytest import MonkeyPatch as Patch

from scripts.pg_ci_evidence import (
    G2_V2_REQUIRED,
    document_hash,
    finalize_shard,
    plan_shards,
    safe_shard_report,
    shard_groups,
    validate_plan,
    verify_shards,
)
from scripts.pg_diagnostic import run_combined
from tests.test_pg_ci_evidence import META
from tests.test_pg_diag_partition import collection

pytestmark = pytest.mark.offline
FULL = [
    "tests/test_checkpoint_pg.py::checkpoint",
    *[f"tests/test_p5_example_{i}_pg.py::case" for i in range(8)],
    "tests/test_p4_terminal_recovery_pg.py::case[0015]",
    "tests/test_p4_terminal_recovery_pg.py::case[0016]",
]
BINDING: dict[str, Any] = {
    **META,
    "execution": {"run_id": "123", "attempt": "1"},
    "environment": {
        "os": "Linux",
        "arch": "x86_64",
        "runner_image": "ubuntu24",
        "runner_version": "20261025.1",
        "runner_version_source": "Hosted environment ImageVersion",
        "docker": "Docker version 28.0.0, build abc",
        "compose": "2.40.0",
        "pg_image": "postgres:17.11-bookworm@sha256:" + "e" * 64,
    },
}


def plan(count: int = 4) -> dict[str, Any]:
    return plan_shards(FULL, {n: float(i + 1) for i, n in enumerate(FULL)}, count, BINDING)


def evidence(
    p: dict[str, Any], shard: int, binding: dict[str, Any] | None = None
) -> dict[str, Any]:
    records = [collection(FULL)]
    raw: dict[str, Any] = {
        "records": records,
        "result": "passed_no_hang_reproduced",
        "cleanup_exit": 0,
        "stopping_confirmed": True,
        "g1_complete": shard == 0,
        "project": f"p123-{shard:012x}",
        "volume": f"p123-{shard:012x}_pg_data",
        "started_at": "2026-10-28T08:00:00+00:00",
        "finished_at": "2026-10-28T08:10:00+00:00",
        "deadline": "2026-10-28T08:15:00+00:00",
        "remaining_resources": {"containers": 0, "networks": 0, "volumes": 0},
        "pg_image_id": "sha256:" + "f" * 64,
        "raw_secret": "dummy",
    }
    called = []

    def command(label: str, paths: list[str], cap: float) -> bool:
        assert cap == 300
        selected = sorted(n for n in FULL if n in paths or n.split("::")[0] in paths)
        assert selected == p["groups"][label]  # detects arbitrary-module overcollection
        called.append(label)
        records.append(collection(selected))
        records.extend(
            {
                "event": "pytest_progress",
                "data": {
                    "event": "phase_end",
                    "phase": "call",
                    "outcome": "passed",
                    "nodeid": node,
                },
            }
            for node in selected
        )
        records.append({"event": "command_end", "label": label, "exit": 0})
        return True

    run_combined(records, raw, command, shard_plan=p, shard_id=shard)
    assert sorted(called) == p["shards"][shard]["groups"]
    if shard == 0:
        records.extend(
            {"event": "g1_persistence", "kind": "verified", "count_one": True} for _ in range(3)
        )
        records.extend({"event": "g2_evidence", "data": {"scenario": s}} for s in G2_V2_REQUIRED)
    exported = safe_shard_report(raw, BINDING if binding is None else binding, p, shard)
    assert exported["native_exit"] is None
    return finalize_shard(exported, 0)


def reports(p: dict[str, Any]) -> list[dict[str, Any]]:
    return [evidence(p, i) for i in range(len(p["shards"]))]


def outcomes(p: dict[str, Any]) -> dict[str, str]:
    return {str(i): "success" for i in range(len(p["shards"]))}


@pytest.mark.parametrize("count", [4, 6])
def test_real_helpers_plan_execute_export_and_aggregate_pure(count: int) -> None:
    p = plan(count)
    assert p == plan_shards(FULL[::-1], p["weights"], count, BINDING)
    assert p["shards"][0]["smoke"] is True
    assert "combined-existing" in p["shards"][0]["groups"]
    result = reports(p)
    assert all("raw_secret" not in r and "records" not in r for r in result)
    verify_shards(p, result[::-1], outcomes(p))


def test_new_nodes_are_not_limited_by_old_weights_or_baseline_count() -> None:
    p = plan()
    new = FULL + ["tests/test_p5_added_pg.py::fresh"]
    result = plan_shards(new, p["weights"] | {"tests/test_removed.py::old": 100.0}, 4, BINDING)
    assert result["full_node_ids"] == sorted(new)
    assert "tests/test_p5_added_pg.py::fresh" in [n for g in result["groups"].values() for n in g]
    assert "tests/test_removed.py::old" not in result["weights"]


@pytest.mark.parametrize("change", ["groups", "shards", "weights", "digest", "extra"])
def test_plan_tampering_rejected_even_with_rehashed_envelope(change: str) -> None:
    p = copy.deepcopy(plan())
    if change == "groups":
        p["groups"]["combined-existing"].append(FULL[1])
    elif change == "shards":
        p["shards"][1]["groups"].append("combined-existing")
    elif change == "weights":
        p["weights"][FULL[0]] = float("nan")
    elif change == "extra":
        p["raw"] = "reject"
    else:
        p["weights_sha256"] = "0" * 64
    p["plan_sha256"] = document_hash({k: v for k, v in p.items() if k != "plan_sha256"})
    with pytest.raises(ValueError):
        validate_plan(p)


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "duplicate-shard",
        "same-project",
        "source",
        "tree",
        "tool",
        "run",
        "attempt",
        "runner",
        "plan",
        "full",
        "selected",
        "actual",
        "passed",
        "exit",
        "cleanup",
        "stopped",
        "g1",
        "g2-sixth",
        "extra",
        "image",
        "resources",
        "deadline",
    ],
)
def test_aggregate_negative_evidence_fails_closed(change: str) -> None:
    p = plan()
    rs = copy.deepcopy(reports(p))
    r = rs[0]
    if change == "missing":
        rs.pop()
    elif change == "duplicate-shard":
        rs[1] = copy.deepcopy(r)
    elif change == "same-project":
        rs[1]["resources"]["project"] = r["resources"]["project"]
        rs[1]["resources"]["volume"] = r["resources"]["volume"]
    elif change in {"source", "tree"}:
        r["binding"]["source_sha" if change == "source" else "source_tree"] = "c" * 40
    elif change == "tool":
        r["binding"]["fingerprints"]["binaries"]["uv"] = "d" * 64
    elif change in {"run", "attempt"}:
        r["binding"]["execution"]["run_id" if change == "run" else "attempt"] = "99"
    elif change == "runner":
        r["binding"]["environment"]["runner_version"] = "different"
    elif change in {"plan", "full"}:
        r["plan_sha256" if change == "plan" else "full_node_ids_sha256"] = "0" * 64
    elif change in {"selected", "actual"}:
        r[change + "_node_ids"] = []
    elif change == "passed":
        r["modules"][0]["passed_node_ids"] = []
    elif change == "exit":
        r["modules"][0]["exit_code"] = True
    elif change == "cleanup":
        r["cleanup_exit"] = True
    elif change == "stopped":
        r["stopping_confirmed"] = False
    elif change == "g1":
        r["g1_verified_count"] = 2
    elif change == "g2-sixth":
        r["g2_scenarios"].remove("retired_probe_version_refused")
    elif change == "extra":
        r["raw_log"] = "reject"
    elif change == "image":
        r["resources"]["pg_image_id"] = "sha256:" + "a" * 64
    elif change == "resources":
        r["resources"]["remaining_resources"]["volumes"] = 1
    else:
        r["resources"]["finished_at"] = "2026-10-28T08:16:00+00:00"
    with pytest.raises(ValueError):
        verify_shards(p, rs, outcomes(p))


@pytest.mark.parametrize("outcome", ["cancelled", "failure", "skipped", "timed_out"])
def test_failed_native_job_cannot_be_saved_by_valid_artifacts(outcome: str) -> None:
    p = plan()
    with pytest.raises(ValueError, match="native jobs"):
        verify_shards(p, reports(p), outcomes(p) | {"1": outcome})


def test_collection_drift_refused_before_any_command() -> None:
    p = plan()
    with pytest.raises(ValueError, match="collection"):
        shard_groups(p, 0, FULL + ["tests/test_p5_new_pg.py::case"])
    with pytest.raises(ValueError, match="mix"):
        run_combined(
            [collection(FULL)],
            {},
            lambda *_: pytest.fail("must not run"),
            "existing",
            shard_plan=p,
            shard_id=0,
        )


@pytest.mark.parametrize("value", [None, True, 1, 143])
def test_unconfirmed_or_failed_parent_exit_rejected(value: object) -> None:
    p = plan()
    rs = reports(p)
    rs[0]["native_exit"] = value
    with pytest.raises(ValueError, match="parent exit"):
        verify_shards(p, rs, outcomes(p))


def test_native_finalization_cannot_overwrite_original_outcome() -> None:
    p = plan()
    with pytest.raises(ValueError, match="one actual"):
        finalize_shard(reports(p)[0], 0)


def test_finalize_cli_runs_without_pg_docker_or_identity_probe(tmp_path: Path) -> None:
    p = plan()
    r = reports(p)[0]
    r["native_exit"] = None
    path = tmp_path / "safe.json"
    path.write_text(json.dumps(r))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.pg_ci_evidence",
            "finalize",
            "--report",
            str(path),
            "--exit",
            "143",
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(path.read_text())["native_exit"] == 143


@pytest.mark.parametrize("count", [4, 6])
def test_frozen_native_timing_input_preserves_all_existing_execution_units(
    count: int, monkeypatch: Patch
) -> None:
    weights = json.loads(
        (Path(__file__).resolve().parents[1] / "docs/harness/h2/weights.json").read_text()
    )
    assert len(weights) == 590  # Historical fixture size only, never production selection.
    monkeypatch.setattr(sys.modules[__name__], "FULL", list(weights))
    p = plan_shards(list(weights), weights, count, BINDING)
    assert len(p["groups"]) == 35
    verify_shards(p, reports(p), outcomes(p))
    assert sorted(n for r in reports(p) for n in r["actual_node_ids"]) == sorted(weights)


def test_shadow_is_pr_merge_sha_bound_and_unrelated_branches_cannot_start_pg() -> None:
    import yaml  # type: ignore[import-untyped]

    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/harness-pg-shadow.yml").read_text())
    events = workflow.get("on", workflow.get(True))
    assert set(events) == {"pull_request"}
    jobs = workflow["jobs"]
    guard = jobs["h2-plan"]["if"]
    assert "github.head_ref == 'codex/harness-v3'" in guard
    assert "head.repo.full_name == github.repository" in guard
    assert "github.repository == 'aning0922/commerceops-agent'" in guard
    assert jobs["h2-shards"]["needs"] == "h2-plan"
    assert jobs["h2-shards"]["strategy"]["fail-fast"] is False
    collection_step = next(
        s for s in jobs["h2-plan"]["steps"] if s.get("name", "").startswith("Discover")
    )
    assert collection_step["env"] == {"P123_DIAG": "1", "P123_TRACE_CHILD": "0"}
    for job in jobs.values():
        checkout = next(
            s for s in job["steps"] if s.get("uses", "").startswith("actions/checkout@")
        )
        assert checkout["with"]["ref"] == "${{ github.sha }}"
        assert checkout["with"]["persist-credentials"] is False
        assert job["timeout-minutes"] <= 45
    native = next(s for s in jobs["h2-shards"]["steps"] if s.get("name", "").startswith("Native"))
    assert native["run"].index("native_exit=$?") < native["run"].index("pg_ci_evidence finalize")
    # H3 may cache public packages and remove only checks still run by scripts.check.
    old = subprocess.check_output(
        ["git", "show", "6d3a8f7:.github/workflows/quality.yml"], cwd=root
    )
    original = yaml.safe_load(old)["jobs"]
    current = yaml.safe_load(
        subprocess.check_output(
            [
                "git",
                "show",
                "226917d4dba57bdb2eef54180df97e57510e4169:.github/workflows/quality.yml",
            ],
            cwd=root,
        )
    )["jobs"]
    for name in original:
        candidate = dict(current[name])
        if name in {"n01-web", "frontend"}:
            candidate["env"] = dict(candidate["env"])
            candidate["steps"] = [
                dict(step)
                for step in candidate["steps"]
                if step.get("name")
                not in {
                    "Restore only public npm content cache",
                    "Observe safe public-cache identity",
                }
            ]
            for step in candidate["steps"]:
                if step.get("name", "").startswith(("Prepare locked", "Locked tools")):
                    step["run"] = step["run"].replace(
                        'export npm_config_cache="${RUNNER_TEMP:?}/commerceops-npm"\n', ""
                    )
        if name == "n01-web":
            del candidate["outputs"]
            candidate["steps"] = candidate["steps"][:-1]
            preparation = next(
                step
                for step in candidate["steps"]
                if step.get("name", "").startswith("Prepare locked")
            )
            preparation["run"] = (
                preparation["run"]
                .replace(
                    'cd "$GITHUB_WORKSPACE/frontend"\n',
                    'cd "$GITHUB_WORKSPACE/frontend"\n'
                    "run_before_cleanup npm ci --ignore-scripts\n"
                    "run_before_cleanup npm run check:toolchain\n"
                    "run_before_cleanup npm run typecheck\n",
                )
                .replace(
                    "# Complete scripts.check above covers this same source.\n",
                    "",
                )
            )
        assert original[name] == candidate


@pytest.mark.parametrize(
    "path,value",
    [
        (("environment", "runner_image"), "ubuntu22"),
        (("environment", "compose"), "2.38.2"),
        (("fingerprints", "binaries", "uv"), "1" * 64),
        (("execution", "attempt"), "2"),
        (("source_sha",), "2" * 40),
    ],
)
def test_strict_binding_diagnoses_only_changed_field_digests(
    path: tuple[str, ...], value: str
) -> None:
    from scripts.pg_ci_evidence import require_same_binding

    actual = copy.deepcopy(BINDING)
    target = actual
    for key in path[:-1]:
        target = target[key]
    original = target[path[-1]]
    target[path[-1]] = value
    require_same_binding(BINDING, BINDING, "same")
    with pytest.raises(ValueError) as error:
        require_same_binding(BINDING, actual, "strict mismatch")
    message = str(error.value)
    differences = json.loads(message.split("binding_diff=", 1)[1])
    assert differences == [
        {
            "field": ".".join(path),
            "expected_sha256": document_hash(original),
            "actual_sha256": document_hash(value),
        }
    ]
    if len(value) > 8:
        assert value not in message
    if len(original) > 8:
        assert original not in message


@pytest.mark.parametrize("side", ["expected", "actual"])
def test_unknown_binding_shape_rejected_before_diagnostic_output(side: str) -> None:
    from scripts.pg_ci_evidence import require_same_binding

    modified = copy.deepcopy(BINDING)
    modified["environment"]["unexpected"] = "private-value"
    pair = (modified, BINDING) if side == "expected" else (BINDING, modified)
    with pytest.raises(ValueError) as error:
        require_same_binding(*pair, "strict mismatch")
    assert "binding_diff=" not in str(error.value)
    assert "private-value" not in str(error.value)


@pytest.mark.parametrize(
    "native_exit,report_present,finalize_exit,deadline_kind,expected_exit",
    [
        (23, False, 0, "registered", 23),
        (0, False, 0, "registered", 1),
        (0, True, 0, "registered", 0),
        (0, True, 9, "registered", 9),
        (23, True, 9, "registered", 23),
        (0, False, 0, "missing", 1),
        (0, False, 0, "invalid", 1),
        (0, False, 0, "naive", 1),
    ],
)
@pytest.mark.parametrize("full", [False, True])
def test_actual_shadow_shell_preserves_registered_deadline_and_first_failure(
    tmp_path: Path,
    native_exit: int,
    report_present: bool,
    finalize_exit: int,
    deadline_kind: str,
    expected_exit: int,
    full: bool,
) -> None:
    import os
    import shutil
    from datetime import UTC, datetime, timedelta

    import yaml

    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/harness-pg-shadow.yml").read_text())
    if full:
        workflow = yaml.safe_load((root / ".github/workflows/quality.yml").read_text())
    steps = workflow["jobs"]["pg-shards" if full else "h2-shards"]["steps"]
    assert steps[0]["name"].startswith("Register immutable")
    assert steps[1]["uses"].startswith("actions/checkout@")
    assert steps[1]["with"].get("clean", True) is True
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    environment_file = tmp_path / "github-env"
    env = {**os.environ, "GITHUB_ENV": str(environment_file)}
    before = datetime.now(UTC)
    registered = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", steps[0]["run"]],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
    )
    assert registered.returncode == 0, registered.stderr
    name, stop = environment_file.read_text().strip().split("=", 1)
    assert name == ("COMMERCEOPS_FULL_PG_STOP_AT_UTC" if full else "COMMERCEOPS_H2_STOP_AT_UTC")
    assert before + timedelta(minutes=43) <= datetime.fromisoformat(stop)
    assert datetime.fromisoformat(stop) <= datetime.now(UTC) + timedelta(minutes=43)
    # Reproduce the observed fresh-checkout removal, only in this disposable temp dir.
    shutil.rmtree(workspace)
    workspace.mkdir()
    assert environment_file.exists() and not (workspace / ".audit/ci-deadline").exists()
    env.pop(name, None)
    if deadline_kind != "missing":
        env[name] = {"registered": stop, "invalid": "invalid", "naive": "2026-10-28T00:00:00"}[
            deadline_kind
        ]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv = bin_dir / "uv"
    uv.write_text(
        "#!/usr/bin/env python3\n"
        "import json,os,sys\nfrom pathlib import Path\n"
        "with Path(os.environ['CALL_LOG']).open('a') as f:\n"
        " f.write(json.dumps(sys.argv[1:])+'\\n')\n"
        "if 'scripts.pg_diagnostic' in sys.argv:\n"
        " if os.environ['REPORT_PRESENT']=='1':\n"
        "  p=Path('.audit/ci-evidence-shard-1.json'); p.parent.mkdir(); p.write_text('{}')\n"
        " sys.exit(int(os.environ['NATIVE_EXIT']))\n"
        "sys.exit(int(os.environ['FINALIZE_EXIT']))\n"
    )
    uv.chmod(0o700)
    log = tmp_path / "calls.jsonl"
    env.update(
        PATH=str(bin_dir) + os.pathsep + env["PATH"],
        SHARD_ID="1",
        CALL_LOG=str(log),
        REPORT_PRESENT=str(int(report_present)),
        NATIVE_EXIT=str(native_exit),
        FINALIZE_EXIT=str(finalize_exit),
    )
    native = next(s for s in steps if s.get("name", "").startswith("Native"))
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", native["run"]],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == expected_exit, result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    if deadline_kind != "registered":
        assert calls == []  # Invalid registration fails before any diagnostic/finalize call.
    else:
        assert calls[0][calls[0].index("--deadline") + 1] == stop
        assert len(calls) == (2 if report_present else 1)
        if report_present:
            assert calls[1][calls[1].index("--exit") + 1] == str(native_exit)
        else:
            assert "test evidence unavailable" in result.stdout


@pytest.mark.parametrize("entry", ["diagnostic", "aggregate", "malformed-aggregate"])
def test_entrypoints_reject_before_resources_or_report_reads(
    tmp_path: Path, monkeypatch: Patch, entry: str
) -> None:
    from scripts import pg_ci_evidence as checker
    from scripts import pg_diagnostic as diagnostic

    p = copy.deepcopy(plan())
    if entry == "malformed-aggregate":
        p["unexpected"] = "private-value"
    file = tmp_path / "plan.json"
    file.write_text(json.dumps(p))
    actual = copy.deepcopy(BINDING)
    actual["environment"]["docker"] = "different Docker version"
    module = diagnostic if entry == "diagnostic" else checker
    monkeypatch.setattr(module, "identity", lambda _: META)
    monkeypatch.setattr(module, "execution_identity", lambda: actual["execution"])
    monkeypatch.setattr(module, "environment_identity", lambda _: actual["environment"])
    monkeypatch.setattr(
        diagnostic, "prepare", lambda *_: pytest.fail("resource preparation must not start")
    )
    if entry == "diagnostic":
        argv = [
            "pg_diagnostic",
            "--session",
            "ci",
            "--round",
            "1",
            "--combined",
            "--shard-plan",
            str(file),
            "--shard-id",
            "0",
            "--full-smoke",
            "--deadline",
            "2026-10-28T00:00:00+00:00",
        ]
        run = diagnostic.main
    else:
        argv = [
            "pg_ci_evidence",
            "aggregate",
            "--plan",
            str(file),
            "--job-results",
            str(tmp_path / "absent-jobs.json"),
            str(tmp_path / "absent-report.json"),
        ]
        run = checker.shard_main
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(ValueError) as error:
        run()
    if entry == "malformed-aggregate":
        assert "binding_diff=" not in str(error.value)
    else:
        assert '"field": "environment.docker"' in str(error.value)
    assert "private-value" not in str(error.value)


@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "missing",
        "multiple",
        "short-container",
        "selection-error",
        "inspect-error",
        "wrong-container",
        "wrong-project",
        "wrong-service",
        "stopped",
        "short-image",
        "no-prefix",
        "extra-fields",
    ],
)
def test_owned_pg_image_uses_native_full_id_and_checks_actual_container(case: str) -> None:
    from scripts.pg_diagnostic import owned_pg_image_id

    project = "p123-0123456789ab"
    compose = ["docker", "compose", "-p", project, "-f", "compose.yml"]
    container, image = "a" * 64, "sha256:" + "b" * 64
    selected = {
        "missing": "",
        "multiple": container + "\n" + "c" * 64,
        "short-container": container[:12],
    }.get(case, container)
    fields = [container, image, "true", project, "postgres"]
    changes = {
        "wrong-container": (0, "c" * 64),
        "wrong-project": (3, "p123-other"),
        "wrong-service": (4, "db-init"),
        "stopped": (2, "false"),
        "short-image": (1, "sha256:" + "b" * 12),
        "no-prefix": (1, "b" * 64),
    }
    if case in changes:
        index, value = changes[case]
        fields[index] = value
    if case == "extra-fields":
        fields.append("private")
    calls = []

    def capture(command: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if len(calls) == 1:
            assert command == compose + ["ps", "--quiet", "postgres"]
            return subprocess.CompletedProcess(command, int(case == "selection-error"), selected)
        assert command[:4] == ["docker", "container", "inspect", "--format"]
        assert command[-1] == container and len(command) == 6
        assert ".Image" in command[4] and ".State.Running" in command[4]
        assert "com.docker.compose.project" in command[4]
        assert "com.docker.compose.service" in command[4] and "Env" not in command[4]
        return subprocess.CompletedProcess(command, int(case == "inspect-error"), "|".join(fields))

    if case == "valid":
        assert owned_pg_image_id(compose, project, capture) == image
    else:
        with pytest.raises(RuntimeError) as error:
            owned_pg_image_id(compose, project, capture)
        assert "private" not in str(error.value)


def test_real_main_preserves_image_failure_and_cleanup_without_inventing_collection(
    tmp_path: Path, monkeypatch: Patch, capsys: pytest.CaptureFixture[str]
) -> None:
    import os
    from datetime import UTC, datetime, timedelta

    from scripts import pg_diagnostic as diagnostic
    from tests.test_pg_diag_shutdown import Process

    p = plan()
    file = tmp_path / "plan.json"
    file.write_text(json.dumps(p))
    monkeypatch.setattr(diagnostic, "ROOT", tmp_path)
    monkeypatch.setattr(diagnostic, "identity", lambda _: META)
    monkeypatch.setattr(diagnostic, "execution_identity", lambda: BINDING["execution"])
    monkeypatch.setattr(diagnostic, "environment_identity", lambda _: BINDING["environment"])

    def prepare(directory: Path) -> None:
        directory.mkdir(parents=True)
        for name in ["owner_password", "app_password"]:
            (directory / name).write_text("dummy")

    monkeypatch.setattr(diagnostic, "prepare", prepare)

    def completed_process(*args: Any, **kwargs: Any) -> Process:
        process = Process([])
        process.returncode = 0
        monkeypatch.setattr(process, "wait", lambda **kw: 0)
        return process

    monkeypatch.setattr(subprocess, "Popen", completed_process)
    monkeypatch.setattr(os, "killpg", lambda *a: pytest.fail("no real PID signal"))
    calls = []

    def capture(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[-3:] == ["ps", "--quiet", "postgres"]:
            return subprocess.CompletedProcess(command, 0, "a" * 64)
        if command[:3] == ["docker", "container", "inspect"]:
            return subprocess.CompletedProcess(command, 0, "private")
        assert "down" in command or "--filter" in command
        return subprocess.CompletedProcess(command, 0, "")

    monkeypatch.setattr(subprocess, "run", capture)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pg_diagnostic",
            "--session",
            "ci",
            "--round",
            "1",
            "--combined",
            "--shard-plan",
            str(file),
            "--shard-id",
            "1",
            "--deadline",
            (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        ],
    )
    with pytest.raises(SystemExit) as error:
        diagnostic.main()
    assert error.value.code == 1
    output = capsys.readouterr().out
    assert "private" not in output
    events = [json.loads(line) for line in output.splitlines()]
    primary = next(e for e in events if e.get("event") == "diagnostic_failed")
    assert primary["stage"] == "pg-image-identity" and primary["code"] == "RuntimeError"
    assert any(e.get("event") == "shard_evidence_unavailable" for e in events)
    final = events[-1]
    assert final["result"] == "failed" and final["cleanup_exit"] == 0
    assert final["cleanup_stage"] == "complete"
    report = json.loads((tmp_path / ".audit/issue23-ci/round-1.json").read_text())
    assert "full_node_ids" not in report and "pg_image_id" not in report
    assert report["remaining_resources"] == {"containers": 0, "networks": 0, "volumes": 0}
    assert not list((tmp_path / ".audit").glob("ci-evidence-shard-*.json"))
    assert any("down" in c for c in calls)


@pytest.mark.parametrize("mixed", [False, True])
def test_revision_only_difference_survives_export_and_aggregate(mixed: bool) -> None:
    from scripts.pg_ci_evidence import runner_revision_observations

    p = plan()
    rs = reports(p)
    if mixed:
        binding = copy.deepcopy(BINDING)
        binding["environment"]["runner_version"] = "20261026.354.1"
        rs[0] = evidence(p, 0, binding)
    checker = copy.deepcopy(BINDING)
    checker["environment"]["runner_version"] = "20261027.355.1" if mixed else "20261025.1"
    verify_shards(p, rs, outcomes(p))
    result = runner_revision_observations(p, rs, checker)
    assert result["mixed_host_revisions"] is mixed
    assert len(result["runner_revision_observations"]) == len(rs) + 2
    assert (
        result["runner_revision_observations"][-1]["runner_version"]
        == checker["environment"]["runner_version"]
    )
    assert (
        result["runner_revision_observations"][1]["runner_version"]
        == rs[0]["binding"]["environment"]["runner_version"]
    )
    assert len(result["distinct_runner_revisions"]) == (3 if mixed else 1)


@pytest.mark.parametrize("bad", [None, "", "UNKNOWN", "unknown", "20261026.354.1\n"])
@pytest.mark.parametrize("role", ["plan", "shard", "aggregate"])
def test_revision_observation_missing_or_unknown_fails_closed(bad: Any, role: str) -> None:
    from scripts.pg_ci_evidence import require_same_binding

    actual = copy.deepcopy(BINDING)
    if bad is None:
        del actual["environment"]["runner_version"]
    else:
        actual["environment"]["runner_version"] = bad
    with pytest.raises(ValueError):
        if role == "plan":
            plan_shards(FULL, {}, 4, actual)
        elif role == "shard":
            p = plan()
            rs = copy.deepcopy(reports(p))
            rs[0]["binding"] = actual
            verify_shards(p, rs, outcomes(p))
        else:
            require_same_binding(BINDING, actual, "checker")


def test_revision_source_is_fixed_and_required() -> None:
    from scripts.pg_ci_evidence import require_same_binding

    for source in (None, "setup-log", ""):
        actual = copy.deepcopy(BINDING)
        if source is None:
            del actual["environment"]["runner_version_source"]
        else:
            actual["environment"]["runner_version_source"] = source
        with pytest.raises(ValueError):
            require_same_binding(BINDING, actual, "source")


@pytest.mark.parametrize(
    "field,value",
    [
        ("os", "Darwin"),
        ("arch", "aarch64"),
        ("runner_image", "ubuntu22"),
        ("docker", "Docker version different"),
        ("compose", "2.38.2"),
        ("pg_image", "postgres:17.11-bookworm@sha256:" + "a" * 64),
    ],
)
def test_mixed_revision_does_not_hide_other_environment_changes(field: str, value: str) -> None:
    from scripts.pg_ci_evidence import require_same_binding

    actual = copy.deepcopy(BINDING)
    actual["environment"].update(runner_version="20261026.354.1", **{field: value})
    with pytest.raises(ValueError):
        require_same_binding(BINDING, actual, "other fields remain strict")


def test_aggregate_cli_reports_every_job_revision(
    tmp_path: Path, monkeypatch: Patch, capsys: pytest.CaptureFixture[str]
) -> None:
    from scripts import pg_ci_evidence as checker

    p = plan()
    rs = copy.deepcopy(reports(p))
    rs[0]["binding"]["environment"]["runner_version"] = "20261026.354.1"
    actual = copy.deepcopy(BINDING)
    actual["environment"]["runner_version"] = "20261027.355.1"
    files = []
    for i, report in enumerate(rs):
        path = tmp_path / f"shard-{i}.json"
        path.write_text(json.dumps(report))
        files.append(str(path))
    plan_file, jobs_file = tmp_path / "plan.json", tmp_path / "jobs.json"
    plan_file.write_text(json.dumps(p))
    jobs_file.write_text(json.dumps(outcomes(p)))
    monkeypatch.setattr(checker, "identity", lambda _: META)
    monkeypatch.setattr(checker, "execution_identity", lambda: actual["execution"])
    monkeypatch.setattr(checker, "environment_identity", lambda _: actual["environment"])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pg_ci_evidence",
            "aggregate",
            "--plan",
            str(plan_file),
            "--job-results",
            str(jobs_file),
            *files,
        ],
    )
    with pytest.raises(SystemExit) as exit_result:
        checker.shard_main()
    assert exit_result.value.code == 0
    output = capsys.readouterr().out.splitlines()
    summary = json.loads(output[0])
    assert summary["mixed_host_revisions"] is True
    assert summary["distinct_runner_revisions"] == [
        "20261025.1",
        "20261026.354.1",
        "20261027.355.1",
    ]
    entries = summary["runner_revision_observations"]
    assert [e["job"] for e in entries] == [
        "plan",
        "shard-0",
        "shard-1",
        "shard-2",
        "shard-3",
        "aggregate",
    ]
    assert all(e["source"] == "Hosted environment ImageVersion" for e in entries)


def test_full_reuses_shadow_native_jobs_and_keeps_exact_rollback() -> None:
    import yaml

    root = Path(__file__).resolve().parents[1]
    full = yaml.safe_load((root / ".github/workflows/quality.yml").read_text())["jobs"]
    shadow = yaml.safe_load((root / ".github/workflows/harness-pg-shadow.yml").read_text())["jobs"]
    for original, candidate in (("h2-plan", "quality"), ("h2-shards", "pg-shards")):
        expected = copy.deepcopy(shadow[original])
        expected.pop("if", None)
        if original == "h2-shards":
            expected["needs"] = "quality"
        encoded = json.dumps(expected)
        for before, after in (
            ("h2-plan-", "full-pg-plan-"),
            ("h2-shard-", "full-pg-shard-"),
            ("COMMERCEOPS_H2_STOP_AT_UTC", "COMMERCEOPS_FULL_PG_STOP_AT_UTC"),
            ("registered H2", "registered Full PG"),
            ("H2 report", "Full PG report"),
        ):
            encoded = encoded.replace(before, after)
        assert full[candidate] == json.loads(encoded)
    rollback = subprocess.check_output(
        ["git", "show", "226917d4dba57bdb2eef54180df97e57510e4169:.github/workflows/quality.yml"],
        cwd=root,
    )
    base = subprocess.check_output(
        ["git", "show", "48fbc7a5a5a68a1e3cc6c9df007272608951f5d0:.github/workflows/quality.yml"],
        cwd=root,
    )
    assert rollback == base
    old = yaml.safe_load(rollback)["jobs"]
    for job in ("frontend", "n01-web", "merge-gate"):
        assert full[job] == old[job]
    for name in ("phase3", "pg-pair"):
        job = full[name]
        assert job["if"] == "always()"
        assert {"quality", "pg-shards"} <= set(job["needs"])
        assert "continue-on-error" not in job
        downloads = [s["with"] for s in job["steps"] if "download-artifact@" in s.get("uses", "")]
        assert downloads == [
            {
                "name": "full-pg-plan-${{ github.run_id }}-${{ github.run_attempt }}",
                "path": ".audit/plan",
            },
            {
                "pattern": "full-pg-shard-*-${{ github.run_id }}-${{ github.run_attempt }}",
                "path": ".audit/shards",
                "merge-multiple": True,
            },
        ]
        assert "scripts.pg_ci_evidence aggregate" in job["steps"][-1]["run"]


@pytest.mark.parametrize(
    "job,field,result",
    [
        (job, field, result)
        for job in ("phase3", "pg-pair")
        for field, result in (
            ("PLAN_RESULT", "failure"),
            ("MATRIX_RESULT", "failure"),
            ("MATRIX_RESULT", "cancelled"),
            ("MATRIX_RESULT", "skipped"),
            ("MATRIX_RESULT", "success"),
        )
    ]
    + [("pg-pair", "AGGREGATE_RESULT", "failure")],
)
def test_full_aggregate_shell_uses_native_results_and_propagates_failure(
    tmp_path: Path,
    job: str,
    field: str,
    result: str,
) -> None:
    import os

    import yaml

    root = Path(__file__).resolve().parents[1]
    jobs = yaml.safe_load((root / ".github/workflows/quality.yml").read_text())["jobs"]
    step = jobs[job]["steps"][-1]
    assert step["env"]["MATRIX_RESULT"] == "${{ needs.pg-shards.result }}"
    assert step["env"]["PLAN_RESULT"] == "${{ needs.quality.result }}"
    if job == "pg-pair":
        assert step["env"]["AGGREGATE_RESULT"] == "${{ needs.phase3.result }}"
    (tmp_path / ".audit").mkdir()
    binary = tmp_path / "uv"
    binary.write_text(
        "#!/usr/bin/env python3\nimport os,sys\n"
        "if sys.argv[-1]=='-': os.execv(sys.executable,[sys.executable,'-'])\n"
        "sys.exit(7)\n"
    )
    binary.chmod(0o700)
    env = {
        **os.environ,
        "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        "PLAN_RESULT": "success",
        "MATRIX_RESULT": "success",
        "AGGREGATE_RESULT": "success",
    }
    env[field] = result
    native = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    output = tmp_path / ".audit/jobs.json"
    if result == "success":
        assert native.returncode == 7
        assert json.loads(output.read_text()) == {str(i): "success" for i in range(6)}
    else:
        assert native.returncode != 0 and not output.exists()
