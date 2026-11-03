"""Offline preparation/command-boundary tests; no Docker, HTTP or PG calls."""

import hashlib
import json
import os
import stat
import subprocess
import sys
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from . import owned_driver as driver
from .preflight import ROOT
from .supervisor import Budget

pytestmark = pytest.mark.offline


@pytest.fixture
def case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> driver.Case:
    monkeypatch.setattr(
        driver,
        "git",
        lambda *args: {
            ("rev-parse", "HEAD"): "a" * 40,
            ("rev-parse", "HEAD^{tree}"): "b" * 40,
            ("status", "--porcelain"): "",
        }[args],
    )
    now = datetime.now(UTC)
    digest = hashlib.sha256(
        (ROOT / "backend/migrations/versions/0024_v4_demo_foundation.py").read_bytes()
    ).hexdigest()
    return driver.Case(
        "v4qa_20261103_case",
        "v4_demo_20261103_case",
        str(tmp_path / "fresh"),
        "a" * 40,
        "b" * 40,
        "sha256:" + "c" * 64,
        "sha256:" + "d" * 64,
        18440,
        13440,
        now.isoformat(),
        (now + timedelta(minutes=15)).isoformat(),
        "lifecycle",
        digest,
        os.getuid(),
        "172.30.250.0/24",
        "172.30.251.0/24",
    )


def test_new_runtime_configuration_excludes_owner_and_separates_secrets(case: driver.Case) -> None:
    driver.prepare(case)
    root = Path(case.directory)
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    for path in root.rglob("*"):
        if path.is_file():
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not (root / "api/owner_password").exists()
    assert (root / "api/runtime-password").read_bytes() == (
        root / "owner/app_password"
    ).read_bytes()
    assert (root / "api/csrf-key").read_bytes() != (root / "api/nonce-key").read_bytes()
    web = json.loads((root / "api/web.json").read_text())
    assert web["database"]["user"] == "commerceops_app"
    assert set(web["origins"]) == {case.api, case.web}
    assert json.loads((root / "api/demo.json").read_text())["api_origin"] == case.api
    assert (root / "owner/owner_password").read_text() not in (root / "compose.env").read_text()


def expanded_model(case: driver.Case) -> dict[str, Any]:
    """Observed compose config JSON shape, not a runtime/model acceptance result."""
    return {
        "networks": {
            "default": {
                "name": case.project + "_default",
                "internal": True,
                "ipam": {"config": [{"subnet": case.pg_subnet}]},
            },
            "host_facing": {
                "name": case.project + "_host_facing",
                "driver": "bridge",
                "ipam": {"config": [{"subnet": case.host_subnet}]},
            },
        },
        "services": {
            name: {
                "image": case.pg_image if name == "postgres" else case.test_image,
                "networks": {
                    key: None
                    for key in (("default", "host_facing") if name == "v4-api" else ("default",))
                },
                **(
                    {
                        "ports": [
                            {
                                "mode": "ingress",
                                "host_ip": "127.0.0.1",
                                "target": case.api_port,
                                "published": str(case.api_port),
                                "protocol": "tcp",
                            }
                        ]
                    }
                    if name == "v4-api"
                    else {}
                ),
            }
            for name in ("postgres", "pg-test", "v4-api")
        },
    }


def test_preparation_never_overwrites_or_reuses_a_case(case: driver.Case) -> None:
    driver.prepare(case)
    original = (Path(case.directory) / "owner/owner_password").read_bytes()
    with pytest.raises(FileExistsError):
        driver.prepare(case)
    assert (Path(case.directory) / "owner/owner_password").read_bytes() == original


@pytest.mark.parametrize(
    "change",
    [
        {"database": "commerceops"},
        {"project": "old"},
        {"api_port": 13440},
        {"pg_image": "latest"},
        {"scenario": "unknown"},
        {"source_sha": "f" * 40},
        {"migration_sha256": "0" * 64},
        {"uid": -1},
    ],
)
def test_nonowned_or_unbound_cases_refused(case: driver.Case, change: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        replace(case, **change).validate()  # type: ignore[arg-type]


def test_overlay_has_no_pg_host_port_or_api_owner_env() -> None:
    overlay = json.loads(Path(driver.__file__).with_name("owned.compose.yml").read_text())
    services = overlay["services"]
    assert "ports" not in services["postgres"]
    api = services["v4-api"]
    assert not any(name.startswith("COMMERCEOPS_DB_") for name in api["environment"])
    assert "secrets" not in api
    assert len(api["volumes"]) == 1 and "/run/v4_api:ro" in api["volumes"][0]
    assert api["ports"][0].startswith("127.0.0.1:")
    assert overlay["networks"]["default"]["internal"] is True


def test_nonzero_diagnostic_evidence_preserved_before_raise(
    case: driver.Case,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = {"status": "FAILED", "chain": [{"sqlstate": "42601"}]}
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 1, json.dumps(row).encode(), b""),
    )
    now = datetime.now(UTC)
    budget = Budget.bind(now - timedelta(seconds=1), now + timedelta(minutes=5))
    records: list[dict[str, object]] = []
    path = tmp_path / "diagnostic.json"
    with pytest.raises(RuntimeError):
        driver.checked(["/never-executed"], budget, records, "migrate", evidence=path)
    assert records == [{"stage": "migrate", "native_exit": 1}]
    assert json.loads(path.read_text()) == row


def test_execute_requires_explicit_root_window_flag(
    case: driver.Case,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = tmp_path / "input.json"
    manifest.write_text(json.dumps(asdict(case)))
    monkeypatch.setattr(sys, "argv", ["owned_driver", "execute", "--case", str(manifest)])
    monkeypatch.setattr(driver, "execute", lambda value: pytest.fail("must not execute"))
    with pytest.raises(SystemExit) as stopped:
        driver.main()
    assert stopped.value.code == 1
    assert json.loads(capsys.readouterr().out)["status"] == "FAILED_OR_UNKNOWN"
