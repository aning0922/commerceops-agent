"""Offline/native-process checks only; no Docker, PG, Woo or browser is started."""

import json
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
