"""离线验证N01公开证据拒绝旧源/漏例/私有字段；不启动Docker或服务。"""

import ast
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

pytestmark = pytest.mark.offline
WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/quality.yml"


def job() -> dict[str, Any]:
    return dict(yaml.safe_load(WORKFLOW.read_text())["jobs"]["n01-web"])


def inline(step: dict[str, Any]) -> str:
    lines = str(step["run"]).splitlines()
    start = lines.index("python3 - <<'PY'") + 1
    return "\n".join(lines[start : lines.index("PY", start)])


def test_n01_deadline_fixed_before_checkout_and_only_verified_public_outputs() -> None:
    value = job()
    assert value["timeout-minutes"] == 25
    steps = value["steps"]
    assert "Register immutable N01 deadline before checkout" == steps[0]["name"]
    assert "timedelta(minutes=23)" in inline(steps[0])
    assert steps[1]["with"]["ref"] == "${{ github.sha }}"
    assert steps[1]["with"]["persist-credentials"] is False
    for step in steps:
        if "run" in step:
            parsed = subprocess.run(
                ["bash", "-n"], input=step["run"], text=True, capture_output=True
            )
            assert parsed.returncode == 0, parsed.stderr
            if str(step["run"]).startswith("python3 - <<'PY'"):
                ast.parse(inline(step))
    preparation = next(s["run"] for s in steps if s.get("name", "").startswith("Prepare locked"))
    assert "COMMERCEOPS_N01_STOP_AT_UTC" in preparation and "- 85" in preparation
    assert "timeout --signal=TERM --kill-after=10" in preparation
    runner = next(s["run"] for s in steps if s.get("id") == "n01")
    assert "tests.e2e.web.run_c09_n01" in runner and "--stop-at-utc" in runner
    assert runner.count("rm -f") == 1
    uploads = [s for s in steps if "actions/upload-artifact" in s.get("uses", "")]
    assert len(uploads) == 1 and "steps.n01_evidence.outcome == 'success'" in uploads[0]["if"]
    assert uploads[0]["with"]["path"].splitlines() == [
        "frontend/evidence/p4-c09/n01/live-results.json",
        "frontend/evidence/p4-c09/n01/pg-invariants.safe.json",
        "frontend/evidence/p4-c09/n01/resource-stop.safe.json",
    ]


@pytest.mark.parametrize(
    "damage",
    [
        None,
        "old_source",
        "old_deadline",
        "missing_case",
        "failed_case",
        "private_error",
        "extra_invariant",
        "second_pair",
        "business_changed",
        "import_hash",
        "source_hash",
        "running_pg",
        "child_unknown",
        "remaining_network",
        "volume_deleted",
        "old_public_stop",
    ],
)
def test_n01_inline_gate_accepts_complete_current_fake_and_rejects_partial_or_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    damage: str | None,
) -> None:
    root, private = tmp_path / "source", tmp_path / "private"
    private.mkdir(mode=0o700)
    public = root / "frontend/evidence/p4-c09/n01"
    public.mkdir(parents=True)
    build = root / "frontend/.next/BUILD_ID"
    build.parent.mkdir(parents=True)
    build.write_text("fake-build")
    titles = ["N01 显式唯一创建"] + [f"N01 fake negative {n}" for n in range(5)]
    spec = root / "tests/e2e/web/live/n01.spec.ts"
    spec.parent.mkdir(parents=True)
    spec.write_text("\n".join(f'test("{title}", () => {{}});' for title in titles))
    manifest = {str(spec.relative_to(root)): hashlib.sha256(spec.read_bytes()).hexdigest()}
    modules = [
        "application/replenishment/nl_preflight.py",
        "infrastructure/web_preflight.py",
        "entrypoints/replenishment_http.py",
        "entrypoints/web_openapi.py",
    ]
    imports = {"pid": 123, "four_imports_match": True, "hashes": {}}
    for name in modules:
        module = root / "backend/src/commerceops" / name
        module.parent.mkdir(parents=True, exist_ok=True)
        module.write_text("# fake imported source\n")
        imports["hashes"][name] = hashlib.sha256(module.read_bytes()).hexdigest()  # type: ignore[index]
    window: dict[str, Any] = {
        "owner": "phase4-C09-Web",
        "owner_uid": os.getuid(),
        "checkout": str(root),
        "private_directory": str(private),
        "source_commit": "a" * 40,
        "build_id": "fake-build",
        "status": "stopped",
        "passed": True,
        "test_exit": 0,
        "failure_category": None,
        "max_new_cycle_requests": 1,
        "worker_started": False,
        "sdk_provider_started": False,
        "pg_container_created": True,
        "pg_running": False,
        "pg_pid": 0,
        "owned_listeners_remaining": False,
        "volume_preserved": True,
        "started_at_utc": "2026-10-12T00:00:00+00:00",
        "stop_at_utc": "2026-10-12T00:23:00+00:00",
        "stopped_at_utc": "2026-10-12T00:10:00+00:00",
        "child_exit_codes": [0, -15, -15],
        "api_pid": 123,
    }
    cleanup: dict[str, Any] = {
        "containers": 0,
        "networks": 0,
        "down_exit": 0,
        "volume_preserved": True,
        "stopped_at_utc": "2026-10-12T00:11:00+00:00",
    }
    report: dict[str, Any] = {
        "status": "passed",
        "duration_ms": 1,
        "trace": "off",
        "video": "off",
        "automatic_screenshot": "off",
        "source_mode": "live-api",
        "commerce_source_mode": "mock-fixture",
        "identity_mode": "session",
        "tests": [
            {
                "test": t,
                "status": "passed",
                "duration_ms": 1,
                "location": "e2e/web/live/n01.spec.ts:1",
            }
            for t in titles
        ],
    }
    invariants: dict[str, Any] = {
        "source": "actual owned PostgreSQL",
        "worker": "not_started",
        "sdk_provider": "not_started",
        "tests": [
            {"test": t, "business_unchanged": n != 0, "explicit_pair_only": n == 0}
            for n, t in enumerate(titles)
        ],
    }
    fields = {
        "passed",
        "source_commit",
        "build_id",
        "test_exit",
        "failure_category",
        "pg_running",
        "pg_pid",
        "owned_listeners_remaining",
        "volume_preserved",
        "worker_started",
        "sdk_provider_started",
        "started_at_utc",
        "stop_at_utc",
        "stopped_at_utc",
    }
    summary = {key: window[key] for key in fields}
    if damage == "old_source":
        window["source_commit"] = "b" * 40
    elif damage == "old_deadline":
        window["stop_at_utc"] = "2026-10-12T01:00:00+00:00"
    elif damage == "missing_case":
        report["tests"].pop()
    elif damage == "failed_case":
        report["tests"][0]["status"] = "failed"
    elif damage == "private_error":
        report["tests"][0]["error"] = "withheld fake raw error"
    elif damage == "extra_invariant":
        invariants["private"] = "not public"
    elif damage == "second_pair":
        invariants["tests"][1]["explicit_pair_only"] = True
    elif damage == "business_changed":
        invariants["tests"][1]["business_unchanged"] = False
    elif damage == "import_hash":
        imports["hashes"][modules[0]] = "b" * 64  # type: ignore[index]
    elif damage == "source_hash":
        manifest[str(spec.relative_to(root))] = "b" * 64
    elif damage == "running_pg":
        window["pg_running"] = True
    elif damage == "child_unknown":
        window["child_exit_codes"].append(None)
    elif damage == "remaining_network":
        cleanup["networks"] = 1
    elif damage == "volume_deleted":
        cleanup["volume_preserved"] = False
    elif damage == "old_public_stop":
        summary["source_commit"] = "b" * 40
    for name, value in [
        ("source-files.safe.json", manifest),
        ("api-imports.safe.json", imports),
        ("ci-cleanup.safe.json", cleanup),
    ]:
        target = private / name
        target.write_text(json.dumps(value))
        target.chmod(0o600)
    window["source_manifest_sha256"] = hashlib.sha256(
        (private / "source-files.safe.json").read_bytes()
    ).hexdigest()
    target = private / "window.json"
    target.write_text(json.dumps(window))
    target.chmod(0o600)
    for name, value in [
        ("live-results.json", report),
        ("pg-invariants.safe.json", invariants),
        ("resource-stop.safe.json", summary),
    ]:
        (public / name).write_text(json.dumps(value))
    monkeypatch.setenv("GITHUB_WORKSPACE", str(root))
    monkeypatch.setenv("N01_CI_PRIVATE_DIRECTORY", str(private))
    monkeypatch.setenv("COMMERCEOPS_N01_STOP_AT_UTC", "2026-10-12T00:23:00+00:00")

    def git(command: list[str], **kwargs: object) -> str:
        assert command[:1] == ["git"]
        if command[1:3] == ["rev-parse", "HEAD"]:
            return "a" * 40
        if command[1:3] == ["rev-parse", "HEAD^{tree}"]:
            return "c" * 40
        assert command[1:] == ["ls-files", "frontend", "tests/e2e/web"]
        return "\n".join(
            [
                str(spec.relative_to(root)),
                str((public / "resource-stop.safe.json").relative_to(root)),
            ]
        )

    monkeypatch.setattr(subprocess, "check_output", git)
    source = inline(next(s for s in job()["steps"] if s.get("id") == "n01_evidence"))
    if damage is None:
        exec(compile(source, "<N01 CI evidence fake>", "exec"), {})  # noqa: S102 本仓固定CI源码，Git工具全Fake。
        assert (
            json.loads((public / "resource-stop.safe.json").read_text())["source_tree"] == "c" * 40
        )
    else:
        with pytest.raises(AssertionError):
            exec(compile(source, "<N01 CI evidence fake>", "exec"), {})  # noqa: S102 同一固定源码负例。


@pytest.mark.parametrize(
    "damage", [None, "wrong_uid", "foreign_label", "running_pg", "lost_volume"]
)
def test_n01_cleanup_only_registered_project_with_private_compose_inputs_and_preserved_volume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str | None
) -> None:
    root, private = tmp_path / "source", tmp_path / "private"
    root.mkdir()
    private.mkdir(mode=0o700)
    stop = (datetime.now(UTC) + timedelta(minutes=23)).isoformat()
    project = "p4c09-n01-0123456789"
    window = {
        "owner": "phase4-C09-Web",
        "owner_uid": os.getuid(),
        "checkout": str(root),
        "private_directory": str(private),
        "source_commit": "a" * 40,
        "stop_at_utc": stop,
        "project": project,
    }
    if damage == "wrong_uid":
        window["owner_uid"] = os.getuid() + 1
    path = private / "window.json"
    path.write_text(json.dumps(window))
    path.chmod(0o600)
    monkeypatch.setenv("GITHUB_WORKSPACE", str(root))
    monkeypatch.setenv("N01_CI_PRIVATE_DIRECTORY", str(private))
    monkeypatch.setenv("COMMERCEOPS_N01_STOP_AT_UTC", stop)
    commands: list[list[str]] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert kwargs["env"]["COMMERCEOPS_PG_RUNTIME_DIR"] == str(private)
        assert command[0] == "docker" and "-v" not in command
        commands.append(command)
        if command[1] == "ps":
            assert command[-1] == "label=com.docker.compose.project=" + project
            output = "" if any("down" in c for c in commands) else "fake-container"
        elif command[1:2] == ["inspect"]:
            labels = {
                "com.docker.compose.project": project,
                "com.docker.compose.project.working_dir": str(root),
                "com.docker.compose.project.config_files": str(root / "compose.yml")
                + ","
                + str(private / "compose-port.json"),
            }
            if damage == "foreign_label":
                labels["com.docker.compose.project"] = "foreign"
            output = json.dumps(
                [
                    {
                        "Config": {"Labels": labels},
                        "State": {
                            "Running": damage == "running_pg",
                            "Pid": 1 if damage == "running_pg" else 0,
                        },
                        "Mounts": [{"Type": "volume", "Name": "fake-owned-volume"}],
                    }
                ]
            )
        elif command[1:3] == ["volume", "inspect"]:
            output = json.dumps(
                [{"Name": "lost" if damage == "lost_volume" else "fake-owned-volume"}]
            )
        elif command[1:3] == ["network", "ls"]:
            assert command[-1] == "label=com.docker.compose.project=" + project
            output = ""
        else:
            assert command[1] == "compose" and command[command.index("-p") + 1] == project
            assert command[command.index("--env-file") + 1] == str(private / "compose-input.conf")
            output = ""
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs: "a" * 40)
    source = inline(next(s for s in job()["steps"] if s.get("id") == "n01_cleanup"))
    if damage is None:
        exec(compile(source, "<N01 CI cleanup fake>", "exec"), {})  # noqa: S102 本仓固定CI源码，Docker全Fake。
        assert (
            json.loads((private / "ci-cleanup.safe.json").read_text())["volume_preserved"] is True
        )
        assert sum("down" in command for command in commands) == 1
    else:
        with pytest.raises(AssertionError):
            exec(compile(source, "<N01 CI cleanup fake>", "exec"), {})  # noqa: S102 同一固定源码负例。
        if damage in ("wrong_uid", "foreign_label", "running_pg"):
            assert not any("down" in command for command in commands)
