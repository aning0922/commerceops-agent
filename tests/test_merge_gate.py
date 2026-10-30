"""Exercise actual CLI rejection plus workflow mandatory-dependency wiring, without Hosted."""

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from scripts import merge_gate

pytestmark = pytest.mark.offline
ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40
TREE = "b" * 40


def needs(sha: str = SHA, tree: str = TREE) -> dict[str, Any]:
    rows = {name: {"result": "success", "outputs": {}} for name in merge_gate.REQUIRED_JOBS}
    rows["n01-web"]["outputs"] = {"source_sha": sha, "source_tree": tree}
    return rows


@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped", "unknown", None])
@pytest.mark.parametrize("job", sorted(merge_gate.REQUIRED_JOBS))
def test_each_dependency_must_actually_succeed(job: str, result: Any) -> None:
    rows = needs()
    rows[job]["result"] = result
    with pytest.raises(ValueError):
        merge_gate.validate(rows, SHA, TREE)


@pytest.mark.parametrize("damage", ["missing", "extra", "old_sha", "old_tree", "no_binding"])
def test_missing_or_stale_evidence_rejected(damage: str) -> None:
    rows = needs()
    if damage == "missing":
        del rows["frontend"]
    elif damage == "extra":
        rows["other"] = deepcopy(rows["frontend"])
    elif damage == "no_binding":
        rows["n01-web"]["outputs"] = {}
    else:
        field = "source_sha" if damage == "old_sha" else "source_tree"
        rows["n01-web"]["outputs"][field] = "c" * 40
    with pytest.raises(ValueError):
        merge_gate.validate(rows, SHA, TREE)


@pytest.mark.parametrize("damage", [None, "wrong_checkout", "wrong_foundation", "invalid_json"])
def test_native_cli_binds_real_checkout_and_does_not_echo_input(damage: str | None) -> None:
    sha, tree = (
        subprocess.check_output(["git", "rev-parse", ref], cwd=ROOT, text=True).strip()
        for ref in ("HEAD", "HEAD^{tree}")
    )
    environment = os.environ.copy()
    environment["GITHUB_SHA"] = "c" * 40 if damage == "wrong_checkout" else sha
    rows = needs("c" * 40 if damage == "wrong_foundation" else sha, tree)
    environment["MERGE_GATE_NEEDS"] = (
        "untrusted-private-context" if damage == "invalid_json" else json.dumps(rows)
    )
    process = subprocess.run(
        [sys.executable, "-m", "scripts.merge_gate"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert (process.returncode == 0) is (damage is None)
    assert "untrusted-private-context" not in process.stdout + process.stderr


def test_full_workflow_cannot_skip_foundation_or_final_dependency() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/quality.yml").read_text())
    triggers = workflow.get("on", workflow.get(True))
    assert not any("paths" in key for config in triggers.values() for key in config)
    jobs = workflow["jobs"]
    final = jobs["merge-gate"]
    assert final["if"] == "${{ always() }}"
    assert set(final["needs"]) == merge_gate.REQUIRED_JOBS
    assert "continue-on-error" not in final
    for name in merge_gate.REQUIRED_JOBS:
        job = jobs[name]
        assert "continue-on-error" not in job
        assert job.get("if") == ("always()" if name in {"phase3", "pg-pair"} else None)
        assert job.get("needs", []) == {
            "phase3": ["quality", "pg-shards"],
            "pg-pair": ["quality", "pg-shards", "phase3"],
        }.get(name, [])
        checkout = next(s for s in job["steps"] if "actions/checkout@" in s.get("uses", ""))
        assert checkout["with"]["ref"] == "${{ github.sha }}"
        assert checkout["with"]["persist-credentials"] is False
    n01 = jobs["n01-web"]
    binding = n01["steps"][-1]
    assert binding["id"] == "n01_source"
    assert "if" not in binding and "continue-on-error" not in binding
    assert 'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"' in binding["run"]
    assert n01["outputs"] == {
        "source_sha": "${{ steps.n01_source.outputs.source_sha }}",
        "source_tree": "${{ steps.n01_source.outputs.source_tree }}",
    }
    command = final["steps"][-1]
    assert command["env"] == {"MERGE_GATE_NEEDS": "${{ toJSON(needs) }}"}
    assert command["run"] == "python3 -m scripts.merge_gate"
    for job in (n01, final):
        for step in job["steps"]:
            if "run" in step:
                syntax = subprocess.run(
                    ["bash", "-n"],
                    input=step["run"],
                    text=True,
                    capture_output=True,
                )
                assert syntax.returncode == 0, syntax.stderr
