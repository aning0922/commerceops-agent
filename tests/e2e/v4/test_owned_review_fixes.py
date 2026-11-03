"""ce51 review regressions; command/DTO-only, no containers or HTTP execution."""

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from . import owned_driver
from .owned_adapter import OwnedAdapter, owner_run
from .owned_driver import Case, web_environment
from .owned_negatives import uncommitted_bootstrap
from .supervisor import Budget
from .test_owned_driver import case as case

pytestmark = pytest.mark.offline
KEY = "70f225c8-66bd-4b95-a204-3a83af871590"


def test_matching_bootstrap_original_key_can_be_unknown_with_http_200() -> None:
    uncommitted_bootstrap(
        {
            "data": {
                "operation": "session_create",
                "request_key": KEY,
                "status": "UNKNOWN",
                "recovery": "WAIT_READ_ONLY",
            }
        },
        KEY,
    )


@pytest.mark.parametrize(
    "change",
    [
        {"operation": "reset"},
        {"request_key": "wrong-key"},
        {"status": "COMMITTED"},
        {"recovery": "OWNER_RECOVERY_REQUIRED"},
        {"tenant_id": "must-not-leak"},
    ],
)
def test_schema_or_owner_mismatch_cannot_be_unknown_recovery(change: dict[str, str]) -> None:
    with pytest.raises(AssertionError):
        uncommitted_bootstrap(
            {
                "data": {
                    "operation": "session_create",
                    "request_key": KEY,
                    "status": "UNKNOWN",
                    "recovery": "WAIT_READ_ONLY",
                    **change,
                }
            },
            KEY,
        )


def test_web_environment_explicitly_selects_local_http(case: Case) -> None:
    env = web_environment(case, Path("/new/tools/node"))
    assert env["COMMERCEOPS_WEB_TRANSPORT"] == "local_http"
    assert env["COMMERCEOPS_API_ORIGIN"] == case.api
    assert not any(name.startswith("COMMERCEOPS_DB_") for name in env)


def test_attached_api_excludes_pg_dependencies() -> None:
    now = datetime.now(UTC)
    budget = Budget.bind(now, now + timedelta(minutes=5))
    adapter = OwnedAdapter(("/docker", "compose"), "v4qa_case_test", budget)
    command, env = adapter.launch_spec("api")
    assert command[-1] == "v4-api" and "--no-deps" in command
    assert "--abort-on-container-exit" not in command
    assert "--abort-on-container-failure" not in command
    assert "postgres" not in command
    assert not any(name.startswith("COMMERCEOPS_DB_") for name in env)


@pytest.mark.parametrize("name", [None, "v4qa_case-facts-registered"])
def test_all_owner_and_observer_invocations_forbid_pull_and_build(name: str | None) -> None:
    command = owner_run(("/docker", "compose"), name=name)
    assert "--build" not in command and "--no-deps" in command
    assert command[command.index("--pull") + 1] == "never"
    assert command[-3:] == ("pg-test", "python", "-m")
    if name:
        assert command[command.index("--name") + 1] == name


def test_frozen_model_removes_all_build_fallbacks(case: Case) -> None:
    model: dict[str, Any] = {
        "services": {
            name: {"image": image, "build": {"context": "."}}
            for name, image in (
                ("postgres", case.pg_image),
                ("pg-test", case.test_image),
                ("v4-api", case.test_image),
                ("db-init", "unused"),
            )
        }
    }
    fixed = owned_driver.no_build_model(model, case)
    assert set(fixed["services"]) == {"postgres", "pg-test", "v4-api"}
    assert all(
        "build" not in value and value["pull_policy"] == "never"
        for value in fixed["services"].values()
    )


def test_missing_image_stops_at_readonly_inspect(
    case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def missing(command: list[str], *args: object, **kwargs: object) -> bytes:
        calls.append(command)
        raise RuntimeError("no local image")

    monkeypatch.setattr(owned_driver, "checked", missing)
    now = datetime.now(UTC)
    with pytest.raises(RuntimeError):
        owned_driver.verify_images(
            case, "/docker", Budget.bind(now, now + timedelta(minutes=5)), []
        )
    assert len(calls) == 1 and calls[0][1:3] == ["image", "inspect"]


@pytest.mark.parametrize("failure", ["native137", "timeout", "bad_json"])
def test_observer_actual_failure_record_written_before_raise(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    now = datetime.now(UTC)
    adapter = OwnedAdapter(
        ("/docker", "compose"),
        "v4qa_failure_case",
        Budget.bind(now, now + timedelta(minutes=5)),
        evidence=tmp_path,
    )

    def result(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if failure == "timeout":
            raise subprocess.TimeoutExpired(
                "tool", 12, output=b"DO_NOT_EMIT", stderr=b"DO_NOT_EMIT"
            )
        return subprocess.CompletedProcess(
            [],
            137 if failure == "native137" else 0,
            b'{"status":"FAILED","secret":"DO_NOT_EMIT"}' if failure == "native137" else b"bad",
            b"DO_NOT_EMIT",
        )

    monkeypatch.setattr(subprocess, "run", result)
    with pytest.raises((RuntimeError, subprocess.TimeoutExpired)):
        adapter.capacity_facts()
    paths = list(tmp_path.glob("*.json"))
    assert len(paths) == 1
    row = json.loads(paths[0].read_text())
    assert row["action"] == "capacity" and row["container"].startswith("v4qa_failure_case-facts-")
    assert row["native_exit"] == ({"native137": 137, "timeout": None, "bad_json": 0}[failure])
    assert (
        row["result"]
        == {
            "native137": "NONZERO_UNKNOWN",
            "timeout": "TIMEOUT_UNKNOWN",
            "bad_json": "INVALID_FACT_JSON",
        }[failure]
    )
    assert "DO_NOT_EMIT" not in paths[0].read_text()
