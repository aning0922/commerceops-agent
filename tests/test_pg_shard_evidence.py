"""Opt-in N-way PG evidence: pure command simulation, never real speed/PG proof."""

import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

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
BINDING = {
    **META,
    "execution": {"run_id": "123", "attempt": "1"},
    "environment": {
        "os": "Linux",
        "arch": "x86_64",
        "runner_image": "ubuntu24",
        "runner_version": "20261025.1",
        "docker": "Docker version 28.0.0, build abc",
        "compose": "2.40.0",
        "pg_image": "postgres:17.11-bookworm@sha256:" + "e" * 64,
    },
}


def plan(count: int = 4) -> dict[str, Any]:
    return plan_shards(FULL, {n: float(i + 1) for i, n in enumerate(FULL)}, count, BINDING)


def evidence(p: dict[str, Any], shard: int) -> dict[str, Any]:
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
        "raw_secret": "must-not-be-exported",
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
    exported = safe_shard_report(raw, BINDING, p, shard)
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
    count: int, monkeypatch: pytest.MonkeyPatch
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
    for job in jobs.values():
        checkout = next(
            s for s in job["steps"] if s.get("uses", "").startswith("actions/checkout@")
        )
        assert checkout["with"]["ref"] == "${{ github.sha }}"
        assert checkout["with"]["persist-credentials"] is False
        assert job["timeout-minutes"] <= 45
    native = next(s for s in jobs["h2-shards"]["steps"] if s.get("name", "").startswith("Native"))
    assert native["run"].index("native_exit=$?") < native["run"].index("pg_ci_evidence finalize")
    # Existing required workflow remains byte-for-byte at the accepted product base.
    old = subprocess.check_output(
        ["git", "show", "6d3a8f7:.github/workflows/quality.yml"], cwd=root
    )
    assert old == (root / ".github/workflows/quality.yml").read_bytes()
