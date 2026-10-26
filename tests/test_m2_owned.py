"""Offline/native-process checks only; no Docker, PG, Woo or browser is started."""

import json
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from scripts import m2_owned as target
from scripts.m2_backup import BackupFailure
from scripts.m2_state import save
from scripts.woo_lab.expectations import expected_document, positive_golden
from tests.test_woo_positive_lab import mapping_for, resolved

pytestmark = pytest.mark.offline


@pytest.mark.parametrize("phase", ["source", "restored"])
def test_frozen_selector_and_allowlist_match_machine_template(phase: str) -> None:
    template = json.loads(
        (target.ROOT / f"docs/contracts/p5-m2-live-{phase}.example.json").read_text()
    )
    consumer = template["files"]["consumer.private.json"]
    assert target.consumer_argv(phase) == consumer["argv"]
    assert target.outputs(phase) == consumer["allowed_output_files"]
    target.selected_one(
        f"Listing tests:\n  m2.spec.ts:4:1 › M2 {phase}\nTotal: 1 test in 1 file\n", phase
    )


@pytest.mark.parametrize(
    "text",
    [
        "Total: 0 tests in 0 files",
        "Total: 2 tests in 1 file",
        "other.spec.ts:1:1 › M2 source\nTotal: 1 test in 1 file",
        "m2.spec.ts:1:1 › M2 restored\nTotal: 1 test in 1 file",
    ],
)
def test_selector_rejects_zero_multiple_wrong_file_or_phase(text: str) -> None:
    with pytest.raises(BackupFailure, match="M2_CONSUMER_SELECTION"):
        target.selected_one(text, "source")


def fixture_request(root: Path) -> tuple[Path, dict[str, Any]]:
    run = uuid4()
    directory = root / "runtime" / ("m2-" + run.hex)
    directory.mkdir(mode=0o700, parents=True)
    for name in ("commands", "source", "restored", "canonical"):
        (directory / name).mkdir(mode=0o700)
    now = datetime.now(UTC)
    request: dict[str, Any] = dict(
        schema_version="p5-m2-owned-run-v1",
        run_id=str(run),
        source_sha="a" * 40,
        source_tree="b" * 40,
        anchor_day=now.date().isoformat(),
        started_at_utc=now.isoformat(),
        stop_at_utc=(now + timedelta(seconds=600)).isoformat(),
        cleanup_reserve_seconds=180,
        api_origin="http://127.0.0.1:49001",
        web_origin="http://127.0.0.1:49002",
        databases={},
    )
    for i, phase in enumerate(target.DATABASE_PHASES):
        project = "m2-" + phase + "-" + run.hex[:12]
        request["databases"][phase] = dict(
            project=project, database="m2_" + phase, volume=project + "_pg_data", port=49003 + i
        )
    return directory, request


@pytest.mark.parametrize(
    "mutation",
    [
        "old_project",
        "old_volume",
        "external",
        "same_port",
        "missing_clone",
        "clone_collision",
        "extra",
    ],
)
def test_private_registration_cannot_redirect_to_existing_assets(
    tmp_path: Path, monkeypatch: Any, mutation: str
) -> None:
    directory, request = fixture_request(tmp_path)
    monkeypatch.setattr(target, "ROOT", tmp_path)
    target.validate_request(request, directory)
    if mutation == "old_project":
        request["databases"]["source"]["project"] = "old-owned-project"
    elif mutation == "old_volume":
        request["databases"]["source"]["volume"] = "old-owned-volume"
    elif mutation == "external":
        request["api_origin"] = "https://example.invalid:443"
    elif mutation == "same_port":
        request["databases"]["source"]["port"] = 49001
    elif mutation == "missing_clone":
        del request["databases"]["revoked"]
    elif mutation == "clone_collision":
        request["databases"]["expired"]["port"] = request["databases"]["restored"]["port"]
    else:
        request["automatic_retry"] = True
    with pytest.raises(BackupFailure):
        target.validate_request(request, directory)


@pytest.mark.parametrize("mode", ["success", "failure", "timeout"])
def test_owned_native_command_preserves_exit_and_reaps(tmp_path: Path, mode: str) -> None:
    (tmp_path / "commands").mkdir(mode=0o700)
    scenario = target.Scenario(tmp_path, {}, time.monotonic() + 240)
    script = {
        "success": "print('controlled')",
        "failure": "raise SystemExit(7)",
        "timeout": "import time;time.sleep(30)",
    }[mode]
    if mode == "success":
        assert scenario.command(mode, [sys.executable, "-c", script], cap=1) == b"controlled\n"
    else:
        with pytest.raises(BackupFailure, match="M2_COMMAND_FAILED"):
            scenario.command(
                mode, [sys.executable, "-c", script], cap=0.05 if mode == "timeout" else 1
            )
    receipt = target.load(tmp_path / "commands" / f"001-{mode}.safe.json")
    assert receipt["reaped"] is True and receipt["timed_out"] == (mode == "timeout")
    assert receipt["native_exit"] == ({"success": 0, "failure": 7}.get(mode, -15))
    assert (tmp_path / "commands" / f"001-{mode}.private.log").stat().st_mode & 0o777 == 0o600


def test_command_cannot_consume_cleanup_reserve(tmp_path: Path) -> None:
    scenario = target.Scenario(tmp_path, {}, time.monotonic() + 179)
    with pytest.raises(BackupFailure, match="M2_DEADLINE"):
        scenario.remaining(1)
    assert scenario.remaining(1, cleanup=True) == 1


def test_platform_mapping_is_by_logical_key_and_refuses_changed_variant(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    spec = resolved()
    mapping = mapping_for(spec)
    for name, value in {
        "seed-spec.private.json": spec,
        "seed-result.private.json": {"mapping": mapping},
        "expected.private.json": expected_document(spec, mapping),
        "analysis-golden.private.json": positive_golden(spec, mapping),
    }.items():
        save(tmp_path / name, value)
    result = target.sku_map(tmp_path)
    assert len(result) == 4 and len({x["stock_pool_key"] for x in result}) == 4
    # Same expected/golden bytes, but a changed platform ID must not be paired by order.
    mapping["products"]["independent_red"] += 100
    path = tmp_path / "seed-result.private.json"
    path.write_text(json.dumps({"mapping": mapping}))
    with pytest.raises(BackupFailure, match="M2_SKU_MAPPING"):
        target.sku_map(tmp_path)


def test_exclusive_private_output_never_overwrites_unknown_result(tmp_path: Path) -> None:
    path = tmp_path / "result.safe.json"
    save(path, {"original": True})
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        save(path, {"replacement": True})
    assert path.read_bytes() == original


def test_expired_business_budget_rejects_before_process_creation(
    tmp_path: Path, monkeypatch: Any
) -> None:
    scenario = target.Scenario(tmp_path, {}, time.monotonic() + 179)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("must not spawn after the business deadline")

    monkeypatch.setattr("scripts.m2_owned.subprocess.Popen", forbidden)
    with pytest.raises(BackupFailure, match="M2_DEADLINE"):
        scenario.command("late", [sys.executable, "-c", "pass"])
    with pytest.raises(BackupFailure, match="M2_DEADLINE"):
        scenario.spawn("late", [sys.executable, "-c", "pass"], {})
    assert not scenario.children and scenario.command_number == 0


@pytest.mark.parametrize("cleanup_ok", [True, False])
def test_failure_always_collects_cleanup_but_cannot_become_success(
    tmp_path: Path, monkeypatch: Any, cleanup_ok: bool
) -> None:
    parent = target.Scenario(
        tmp_path,
        dict(run_id="synthetic", source_sha="a" * 40, source_tree="b" * 40),
        time.monotonic() + 240,
    )
    monkeypatch.setattr(target, "open_run", lambda _: parent)
    observed = []

    def fail_action(_: Any) -> None:
        raise RuntimeError("synthetic-secret-must-not-appear")

    def finish(_: Any) -> dict[str, bool]:
        observed.append("cleanup")
        return {"stopping_confirmed": cleanup_ok}

    monkeypatch.setattr(target, "full_action", fail_action)
    monkeypatch.setattr(target, "cleanup", finish)
    assert target.run(tmp_path) == 1
    raw = (tmp_path / "result.safe.json").read_text()
    assert "synthetic-secret-must-not-appear" not in raw
    assert observed == ["cleanup"]
    assert json.loads(raw)["cleanup_confirmed"] is cleanup_ok


def test_source_handoff_matches_closed_shape_without_precreating_outputs(
    tmp_path: Path, monkeypatch: Any
) -> None:
    root = target.ROOT
    template = json.loads((root / "docs/contracts/p5-m2-live-source.example.json").read_text())[
        "files"
    ]
    directory, request = fixture_request(tmp_path)
    monkeypatch.setattr(target, "ROOT", tmp_path)
    build = tmp_path / "frontend/.next"
    build.mkdir(parents=True)
    (build / "BUILD_ID").write_text("synthetic-build-only")
    spec = resolved()
    mapping = mapping_for(spec)
    lab = tmp_path / "synthetic-lab"
    lab.mkdir(mode=0o700)
    for name, value in {
        "seed-spec.private.json": spec,
        "seed-result.private.json": {"mapping": mapping},
        "expected.private.json": expected_document(spec, mapping),
        "analysis-golden.private.json": positive_golden(spec, mapping),
    }.items():
        save(lab / name, value)
    accounts = template["web-accounts.json"]
    save(
        directory / "seed.private.json",
        dict(
            organization_id=template["window.json"]["organization_id"],
            shop_id=spec["shop_id"],
            accounts={k: accounts[k] for k in ("operator", "approver")},
        ),
    )
    save(
        directory / "binding.private.json",
        dict(
            metadata={"config_ref": "synthetic-only"},
            binding_id=str(uuid4()),
            source_config_version="synthetic-only-v1",
            registration_digest="c" * 64,
        ),
    )
    request["anchor_day"] = spec["anchor_day"]
    scenario = target.Scenario(directory, request, time.monotonic() + 600, lab_directory=lab)
    target.handoff(scenario, "source", dict(api_pid=101, web_pid=102, worker_pid=103))

    def shape(value: Any, model: Any) -> None:
        if isinstance(model, dict):
            assert isinstance(value, dict) and set(value) == set(model)
            for key in model:
                shape(value[key], model[key])
        elif isinstance(model, list):
            assert isinstance(value, list)
        elif model is None:
            assert value is None
        else:
            assert type(value) is type(model)

    for name in (
        "window.json",
        "web-accounts.json",
        "m2-source.private.json",
        "m2-facts.private.json",
        "consumer.private.json",
    ):
        shape(target.load(directory / "source" / name), template[name])
    assert all(not (directory / "source" / name).exists() for name in target.outputs("source"))
    assert not (directory / "source/app_password").exists()
    original = (directory / "source/window.json").read_bytes()
    with pytest.raises(FileExistsError):
        target.handoff(scenario, "source", dict(api_pid=101, web_pid=102, worker_pid=103))
    assert (directory / "source/window.json").read_bytes() == original


@pytest.mark.parametrize("mutation", ["old_volume", "extra_service", "command", "symlink"])
def test_overlay_drift_is_rejected_before_any_docker_call(
    tmp_path: Path, monkeypatch: Any, mutation: str
) -> None:
    directory, request = fixture_request(tmp_path)
    pgdir = directory / "pg-source"
    pgdir.mkdir(mode=0o700)
    overlay = target.pg_overlay(request["databases"]["source"])
    if mutation == "old_volume":
        overlay["services"]["postgres"]["volumes"] = ["old-data:/var/lib/postgresql/data"]
    elif mutation == "extra_service":
        overlay["services"]["unregistered"] = {"image": "unknown"}
    elif mutation == "command":
        overlay["services"]["postgres"]["command"] = ["unknown"]
    save(pgdir / "overlay.json", overlay)
    if mutation == "symlink":
        (pgdir / "overlay.json").rename(pgdir / "other.json")
        (pgdir / "overlay.json").symlink_to(pgdir / "other.json")
    scenario = target.Scenario(directory, request, time.monotonic() + 600)
    calls = []

    def command(*args: Any, **kwargs: Any) -> bytes:
        calls.append(args)
        raise AssertionError("Docker must not be reached")

    monkeypatch.setattr(target.Scenario, "command", command)
    with pytest.raises((BackupFailure, OSError, ValueError)):
        scenario.start_pg("source")
    assert calls == [] and scenario.pg_started == set()


@pytest.mark.parametrize("mutation", ["reference", "config", "compose_env"])
def test_lab_reference_or_resource_input_drift_blocks_child_before_command(
    tmp_path: Path, monkeypatch: Any, mutation: str
) -> None:
    directory, request = fixture_request(tmp_path)
    lab = tmp_path / "registered-lab"
    lab.mkdir(mode=0o700)
    save(lab / "lab.json", {"project": "owned"})
    save(lab / "compose.env", b"REGISTERED=owned\n")
    save(directory / "lab-reference.private.json", {"directory": str(lab)})
    parent = target.Scenario(directory, request, time.monotonic() + 600, lab_directory=lab)
    parent.lab_inputs = {name: target.reference(lab / name) for name in ("lab.json", "compose.env")}
    target.verify_lab_inputs(parent)
    if mutation == "reference":
        (directory / "lab-reference.private.json").write_text(
            json.dumps({"directory": str(tmp_path / "old-lab")})
        )
    else:
        (lab / ("lab.json" if mutation == "config" else "compose.env")).write_text("changed")
    calls = []
    monkeypatch.setattr(target.Scenario, "command", lambda *a, **k: calls.append(a))
    with pytest.raises(BackupFailure):
        target.child_command(parent, "bind-source")
    assert calls == []


def ready_child(parent: target.Scenario, name: str, *, graceful: bool) -> Any:
    script = "import signal,time,sys;"
    if graceful:
        script += "signal.signal(signal.SIGTERM,lambda *args:sys.exit(0));"
    script += "print('ready',flush=True);time.sleep(30)"
    child = parent.spawn(name, [sys.executable, "-c", script], target.environment())
    until = time.monotonic() + 3
    while time.monotonic() < until:
        if b"ready" in (parent.directory / (name + ".private.log")).read_bytes():
            return child
        time.sleep(0.01)
    raise AssertionError("native child did not become ready")


@pytest.mark.parametrize("graceful", [False, True])
def test_owned_service_stop_accepts_only_parent_requested_normal_or_term(
    tmp_path: Path, graceful: bool
) -> None:
    parent = target.Scenario(tmp_path, {}, time.monotonic() + 240)
    ready_child(parent, "source-worker", graceful=True)
    ready_child(parent, "source-api", graceful=graceful)
    ready_child(parent, "source-web", graceful=graceful)
    receipt = target.stop_apps(parent, "source")
    assert parent.children == {} and receipt["errors"] == []
    assert all(
        r["parent_requested_stop"] and r["accepted_exit"] for r in receipt["processes"].values()
    )
    assert receipt["processes"]["api"]["native_exit"] == (0 if graceful else -15)


@pytest.mark.parametrize("api_exit,web_exit", [(7, 9), (0, 0)])
def test_early_exit_fails_and_reaped_children_are_never_signalled(
    tmp_path: Path, monkeypatch: Any, api_exit: int, web_exit: int
) -> None:
    parent = target.Scenario(tmp_path, {}, time.monotonic() + 240)
    ended = []
    for kind, code in (("worker", 0), ("api", api_exit), ("web", web_exit)):
        child = parent.spawn(
            "source-" + kind,
            [sys.executable, "-c", f"raise SystemExit({code})"],
            target.environment(),
        )
        assert child.wait(timeout=3) == code
        ended.append(child.pid)
    calls = []
    monkeypatch.setattr("scripts.m2_owned.os.killpg", lambda pid, sig: calls.append((pid, sig)))
    with pytest.raises(BackupFailure, match="M2_APP_UNEXPECTED_EXIT"):
        target.stop_apps(parent, "source")
    assert calls == [] and parent.children == {}
    receipt = target.load(tmp_path / "source-apps-stopped.safe.json")
    assert receipt["processes"]["api"]["native_exit"] == api_exit
    assert receipt["processes"]["web"]["native_exit"] == web_exit
    assert receipt["processes"]["api"]["parent_requested_stop"] is False


def test_one_early_crash_still_stops_and_reaps_other_live_services(tmp_path: Path) -> None:
    parent = target.Scenario(tmp_path, {}, time.monotonic() + 240)
    worker = ready_child(parent, "source-worker", graceful=True)
    web = ready_child(parent, "source-web", graceful=False)
    api = parent.spawn(
        "source-api", [sys.executable, "-c", "raise SystemExit(7)"], target.environment()
    )
    assert api.wait(timeout=3) == 7
    with pytest.raises(BackupFailure, match="M2_APP_UNEXPECTED_EXIT"):
        target.stop_apps(parent, "source")
    assert parent.children == {} and worker.returncode == 0 and web.returncode == -15
    receipt = target.load(tmp_path / "source-apps-stopped.safe.json")
    assert receipt["processes"]["api"]["accepted_exit"] is False
    assert receipt["processes"]["web"]["accepted_exit"] is True


@pytest.mark.parametrize("field", ["base_url", "consumer_key_file", "ca_file"])
def test_lab_probe_cannot_redirect_to_another_owned_or_existing_source(
    tmp_path: Path, monkeypatch: Any, field: str
) -> None:
    directory, request = fixture_request(tmp_path)
    lab = tmp_path / "new-lab"
    lab.mkdir(mode=0o700)
    save(lab / "lab.json", {"url": "https://localhost:19443"})
    save(lab / "compose.env", b"REGISTERED=new\n")
    save(directory / "lab-reference.private.json", {"directory": str(lab)})
    probe = dict(
        base_url="https://localhost:19443",
        consumer_key_file=str(lab / "consumer_key"),
        consumer_secret_file=str(lab / "consumer_secret"),
        ca_file=str(lab / "ca.crt"),
    )
    probe[field] = (
        "https://localhost:19444" if field == "base_url" else str(tmp_path / "old-private-file")
    )
    save(lab / "probe-config.private.json", probe)
    parent = target.Scenario(directory, request, time.monotonic() + 600, lab_directory=lab)
    parent.lab_inputs = {name: target.reference(lab / name) for name in ("lab.json", "compose.env")}
    calls = []
    monkeypatch.setattr(target.Scenario, "command", lambda *a, **k: calls.append(a))
    with pytest.raises(BackupFailure, match="M2_LAB_PROBE_REFERENCE_CHANGED"):
        target.child_command(parent, "bind-source")
    assert calls == []


@pytest.mark.parametrize("drift", ["origin", "secret", "lab_reference", "lab_config"])
def test_full_action_rejects_drift_before_first_probe_command(
    tmp_path: Path,
    monkeypatch: Any,
    drift: str,
) -> None:
    directory, request = fixture_request(tmp_path)
    lab = tmp_path / "new-lab"
    lab.mkdir(mode=0o700)
    save(lab / "lab.json", {"url": "https://localhost:19443"})
    save(lab / "compose.env", b"REGISTERED=new\n")
    save(directory / "lab-reference.private.json", {"directory": str(lab)})
    probe = dict(
        base_url="https://localhost:19443",
        consumer_key_file=str(lab / "consumer_key"),
        consumer_secret_file=str(lab / "consumer_secret"),
        ca_file=str(lab / "ca.crt"),
    )
    parent = target.Scenario(directory, request, time.monotonic() + 600, lab_directory=lab)
    parent.lab_inputs = {name: target.reference(lab / name) for name in ("lab.json", "compose.env")}
    if drift == "origin":
        probe["base_url"] = "https://localhost:19444"
    elif drift == "secret":
        probe["consumer_secret_file"] = str(tmp_path / "old-secret")
    elif drift == "lab_reference":
        (directory / "lab-reference.private.json").write_text(
            json.dumps({"directory": str(tmp_path / "old-lab")})
        )
    else:
        (lab / "lab.json").write_text(json.dumps({"url": "https://localhost:19444"}))
    save(lab / "probe-config.private.json", probe)
    calls = []

    def command(self: Any, tag: str, *args: Any, **kwargs: Any) -> bytes:
        calls.append(tag)
        if tag.startswith("list-"):
            phase = tag.removeprefix("list-")
            return f"m2.spec.ts:1:1 › M2 {phase}\nTotal: 1 test in 1 file\n".encode()
        assert tag == "frontend-build", "probe or any later command must not be dispatched"
        return b""

    monkeypatch.setattr(target.Scenario, "command", command)
    monkeypatch.setattr(target.Scenario, "start_pg", lambda *_: "synthetic-not-started")
    monkeypatch.setattr(
        target,
        "child_command",
        lambda _parent, action: (
            None if action == "source-init" else pytest.fail("late child reached")
        ),
    )
    monkeypatch.setattr(target, "start_lab", lambda _: lab)
    with pytest.raises(BackupFailure):
        target.full_action(parent)
    assert calls == ["list-source", "list-restored", "frontend-build"]


@pytest.mark.parametrize("action", ["prepare", "build", "serve", "stop"])
def test_real_public_lab_module_enters_cli_without_starting_resources(action: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", target.LAB_MODULE, action, "--help"],
        cwd=target.ROOT,
        env=target.environment(),
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 0
    assert "{prepare,build,verify,serve,stop}" in result.stdout
    assert "--directory" in result.stdout and "--profile" in result.stdout
    assert "--anchor-day" in result.stdout and "--shop-id" in result.stdout


def test_parent_uses_public_lab_cli_argv_for_prepare_build_serve_and_stop(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    from types import SimpleNamespace

    directory, request = fixture_request(tmp_path)
    monkeypatch.setattr(target, "ROOT", tmp_path)
    save(directory / "seed.private.json", {"shop_id": str(uuid4())})
    lab = tmp_path / "runtime/woolab-123456789abc"
    lab.mkdir(mode=0o700)
    save(lab / "lab.json", {"url": "https://localhost:49009", "port": 49009})
    save(lab / "compose.env", b"REGISTERED=new\n")
    parent = target.Scenario(directory, request, time.monotonic() + 1200)
    actual = []

    def command(self: Any, tag: str, argv: list[str], **kwargs: Any) -> bytes:
        if tag in ("lab-prepare", "lab-build", "lab-stop-fallback"):
            actual.append(argv)
        if tag == "lab-prepare":
            return (str(lab) + "\n").encode()
        if tag == "lab-stop-fallback":
            save(
                lab / "cleanup.safe.json",
                dict(containers=0, networks=0, listener_absent=True, volumes_retained=[]),
            )
        return b""

    def spawn(self: Any, name: str, argv: list[str], env: Any, **kwargs: Any) -> Any:
        actual.append(argv)
        save(
            directory / "lab-serve.private.log",
            (
                json.dumps(
                    dict(
                        readonly_key_file=str(lab / "runtime-auth.json"),
                        ca_file=str(lab / "ca.crt"),
                    )
                )
                + "\n"
            ).encode(),
        )
        return SimpleNamespace(poll=lambda: None)

    class NoListeners:
        def __enter__(self) -> Any:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def settimeout(self, _: float) -> None:
            pass

        def connect_ex(self, _: Any) -> int:
            return 1

    monkeypatch.setattr(target.Scenario, "command", command)
    monkeypatch.setattr(target.Scenario, "spawn", spawn)
    monkeypatch.setattr("scripts.m2_owned.socket.socket", NoListeners)
    assert target.start_lab(parent) == lab
    assert target.cleanup(parent)["stopping_confirmed"] is True
    assert [argv[3] for argv in actual] == ["prepare", "build", "serve", "stop"]
    assert all(argv[:3] == [sys.executable, "-m", "scripts.woo_lab"] for argv in actual)
