"""CI失败绑定全Fake；C闭合schema另由原C测试，不起PG/网络/SDK。"""

import ast
import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

pytestmark = pytest.mark.offline
ROOT = Path(__file__).resolve().parents[1]
NODE = ROOT / ".tools/node/bin/node"
BASE = "e9b9c1bf67c14fc8b9ff12e091c516433aa899e4"


def workflow(text: str | None = None) -> dict[str, Any]:
    return dict(yaml.safe_load(text or (ROOT / ".github/workflows/quality.yml").read_text()))


def step(job: str, identity: str) -> dict[str, Any]:
    return next(s for s in workflow()["jobs"][job]["steps"] if s.get("id") == identity)


def javascript(job: str) -> str:
    identity = "n01_failure_evidence" if job == "n01-web" else "frontend_failure_evidence"
    lines = step(job, identity)["run"].splitlines()
    assert lines[0].endswith("<<'JS'") and lines[-1] == "JS"
    return "\n".join(lines[1:-1])


def test_original_success_gate_and_upload_bytes_preserved_with_separate_failure_step() -> None:
    previous = workflow(
        subprocess.check_output(
            ["git", "show", f"{BASE}:.github/workflows/quality.yml"],
            cwd=ROOT,
            text=True,
        )
    )
    current = workflow()
    for name, identity, run_id in (
        ("n01-web", "n01_evidence", "n01"),
        ("frontend", "frontend_evidence", "live"),
    ):
        old_steps, new_steps = previous["jobs"][name]["steps"], current["jobs"][name]["steps"]
        for old in old_steps:
            if old.get("id") == identity or "steps." + identity + ".outcome" in old.get("if", ""):
                expected = dict(old)
                if old.get("id") == "frontend_evidence":
                    original = '    "frontend/playwright.live.config.ts",\n'
                    assert old["run"].count(original) == 1
                    expected["run"] = old["run"].replace(
                        original,
                        original + '    "frontend/tooling/live-failure.schema.json",\n',
                    )
                elif old.get("id") == "n01_evidence":
                    names = '    "live-results.json", "pg-invariants.safe.json", '
                    names += '"resource-stop.safe.json"'
                    original = names + ")}\n"
                    assert old["run"].count(original) == 1
                    expected["run"] = old["run"].replace(
                        original,
                        names + ',\n    "failure-diagnostic.safe.json")}\n',
                    )
                assert expected in new_steps
        failure = step(
            name, "n01_failure_evidence" if name == "n01-web" else "frontend_failure_evidence"
        )
        assert failure["if"] == "${{ always() && steps." + run_id + ".outcome == 'failure' }}"
        uploads = [s for s in new_steps if "actions/upload-artifact" in s.get("uses", "")]
        assert len(uploads) == 2
        failure_upload = next(s for s in uploads if "failure_evidence.outcome" in s.get("if", ""))
        assert "always()" in failure_upload["if"] and "outcome == 'failure'" in failure_upload["if"]
        assert "outcome == 'success'" in failure_upload["if"]
        paths = failure_upload["with"]["path"].splitlines()
        assert len(paths) == 2 and paths[0].endswith(".outputs.sidecar_path }}")
        assert paths[1] == ".audit/live-failure-binding.safe.json"
        assert current["jobs"][name]["timeout-minutes"] == 25
        for entry in new_steps:
            if "run" not in entry:
                continue
            check = subprocess.run(
                ["bash", "-n"], input=entry["run"], text=True, capture_output=True
            )
            assert check.returncode == 0, entry.get("name")
            lines = entry["run"].splitlines()
            for index, line in enumerate(lines):
                if line == "python3 - <<'PY'":
                    stop = lines.index("PY", index + 1)
                    ast.parse("\n".join(lines[index + 1 : stop]))
    assert javascript("frontend") == javascript("n01-web")


@pytest.mark.parametrize("job", ["frontend", "n01-web"])
@pytest.mark.parametrize(
    "damage",
    [
        None,
        "missing",
        "source",
        "tree",
        "job",
        "run",
        "attempt",
        "build",
        "window_source",
        "deadline",
        "stale",
        "clean_passed",
        "anomalous_passed",
        "policy_rejected",
        "raw_invalid_json",
        "private_mode",
        "stage",
        "window_missing",
        "old_unstarted_sample",
    ],
)
def test_binding_accepts_only_current_failure_without_inventing_body_count(
    tmp_path: Path,
    job: str,
    damage: str | None,
) -> None:
    root, private = tmp_path / "source", tmp_path / "private"
    private.mkdir(mode=0o700)
    audit = root / ".audit"
    audit.mkdir(parents=True)
    build = root / "frontend/.next/BUILD_ID"
    build.parent.mkdir(parents=True)
    build.write_text("fake-build")
    reporter = root / "frontend/tooling/live-reporter.ts"
    reporter.parent.mkdir(parents=True)
    # 只Fake两个C专用接口；这里验证A绑定，不复制C schema或政策实现。
    reporter.write_text(
        "export function liveFailurePolicy(){return {};};\n"
        "export function validLiveFailureDiagnostic(value,policy){"
        "return value.stub_valid === true;}\n"
    )
    binary = tmp_path / "bin"
    binary.mkdir()
    git = binary / "git"
    git.write_text(
        "#!/usr/bin/env python3\nimport sys\n"
        "assert sys.argv[1:2] == ['rev-parse']\n"
        "print('a'*40 if sys.argv[2] == 'HEAD' else 'b'*40)\n"
    )
    git.chmod(0o700)
    now = datetime.now(UTC)
    started, captured, deadline = (
        now - timedelta(minutes=2),
        now - timedelta(minutes=1),
        now + timedelta(minutes=20),
    )
    context: dict[str, Any] = {
        "schema_version": "ci-live-failure-binding-v1",
        "source_commit": "a" * 40,
        "source_tree": "b" * 40,
        "job": job,
        "run_id": "123",
        "run_attempt": "1",
        "build_id": "fake-build",
        "registered_at_utc": (now - timedelta(minutes=3)).isoformat(),
        "stop_at_utc": deadline.isoformat(),
    }
    stage = "n01" if job == "n01-web" else "write"
    directory = private if job == "n01-web" else private / stage
    directory.mkdir(mode=0o700, exist_ok=True)
    window: dict[str, Any] = {
        "owner": "phase4-C09-Web" if job == "n01-web" else "phase3-WebCI",
        "owner_uid": os.getuid(),
        "checkout": str(root),
        "private_directory": str(directory),
        "source_commit": "a" * 40,
        "build_id": "fake-build",
        "started_at_utc": started.isoformat(),
        "stop_at_utc": deadline.isoformat(),
        "stage": stage,
    }
    if job == "frontend":
        earlier = private / "read"
        earlier.mkdir(mode=0o700)
        (earlier / "window.json").write_text("{}")
    sidecar = root / (
        "frontend/evidence/p4-c09/n01/failure-diagnostic.safe.json"
        if job == "n01-web"
        else "frontend/evidence/b04-live/write/failure-diagnostic.safe.json"
    )
    sidecar.parent.mkdir(parents=True)
    diagnostic: dict[str, Any] = {
        "stub_valid": True,
        "stage": stage,
        "status": "failed",
        "captured_at_utc": captured.isoformat(),
        "rejected_result_count": 0,
        "global_error_count": 0,
        "actual_body_count": None,
    }
    if damage in {"source", "tree", "job", "run", "attempt", "build"}:
        field = {
            "source": "source_commit",
            "tree": "source_tree",
            "job": "job",
            "run": "run_id",
            "attempt": "run_attempt",
            "build": "build_id",
        }[damage]
        context[field] = "mismatch"
    elif damage == "window_source":
        window["source_commit"] = "c" * 40
    elif damage == "deadline":
        context["stop_at_utc"] = (deadline + timedelta(hours=1)).isoformat()
    elif damage == "stale":
        diagnostic["captured_at_utc"] = (started - timedelta(seconds=1)).isoformat()
    elif damage in {"clean_passed", "anomalous_passed"}:
        diagnostic["status"] = "passed"
        if damage == "anomalous_passed":
            diagnostic["rejected_result_count"] = 1
    elif damage == "policy_rejected":
        diagnostic["stub_valid"] = False
    elif damage == "private_mode":
        private.chmod(0o755)
    elif damage == "stage":
        diagnostic["stage"] = "read" if job == "n01-web" else "n01"
    for path, data in (
        (audit / "live-failure-context.safe.json", context),
        (directory / "window.json", window),
        (sidecar, diagnostic),
    ):
        path.write_text(json.dumps(data))
        path.chmod(0o600)
    withheld_marker = "RAW_MATERIAL_MUST_NOT_ESCAPE"
    if damage == "raw_invalid_json":
        sidecar.write_text(withheld_marker)
    elif damage == "missing":
        sidecar.unlink()
    elif damage == "window_missing":
        (directory / "window.json").unlink()
    elif damage == "old_unstarted_sample":
        old = root / "frontend/evidence/b04-live/failure-diagnostic.safe.json"
        old.parent.mkdir(parents=True, exist_ok=True)
        old.write_text(withheld_marker)
        old.chmod(0o600)
    output = tmp_path / "github-output"
    output.write_text("")
    env = {
        **os.environ,
        "PATH": str(binary) + os.pathsep + os.environ["PATH"],
        "GITHUB_WORKSPACE": str(root),
        "GITHUB_JOB": job,
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_OUTPUT": str(output),
        "COMMERCEOPS_FAILURE_PRIVATE_DIRECTORY": str(private),
        "COMMERCEOPS_N01_STOP_AT_UTC": deadline.isoformat(),
        "COMMERCEOPS_FRONTEND_STOP_AT_UTC": deadline.isoformat(),
    }
    result = subprocess.run(
        [str(NODE), "--input-type=module", "-"],
        input=javascript(job),
        text=True,
        cwd=root,
        env=env,
        capture_output=True,
        timeout=15,
    )
    assert withheld_marker not in result.stdout + result.stderr
    metadata = audit / "live-failure-binding.safe.json"
    if damage in {None, "anomalous_passed", "old_unstarted_sample"}:
        assert result.returncode == 0, result.stderr
        value = json.loads(metadata.read_text())
        assert value["job_outcome"] == "failure" and value["gate_passed"] is False
        assert value["unstarted_stages"] == ([] if job == "n01-web" else ["items"])
        assert "actual_body_count" not in value and "tests" not in value
        assert output.read_text() == "sidecar_path=" + str(sidecar.relative_to(root)) + "\n"
    else:
        assert result.returncode == 1 and not metadata.exists() and not output.read_text()
        assert (
            result.stderr.strip()
            == "Failure evidence missing or rejected; actual test counts remain unknown"
        )
