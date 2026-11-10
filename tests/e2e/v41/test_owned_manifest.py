"""Temporary public Git fixtures only; no services, config, credentials or images."""

import hashlib
import os
import subprocess
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from .owned_manifest import INPUTS, OwnedManifest

pytestmark = pytest.mark.offline


@pytest.fixture
def bound(tmp_path: Path) -> tuple[OwnedManifest, Path, datetime]:
    root = tmp_path / "public-source"
    root.mkdir()
    for name in INPUTS:
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("public fixture\n")

    package = root / "backend/src/commerceops/__init__.py"
    package.parent.mkdir(parents=True, exist_ok=True)
    package.write_text('"""Public package fixture."""\n')

    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", *args], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()

    git("init", "-q")
    git("add", ".")
    git(
        "-c",
        "user.name=Local QA",
        "-c",
        "user.email=qa@localhost",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "public fixture",
    )
    now = datetime.now(UTC)
    manifest = OwnedManifest(
        source_sha=git("rev-parse", "HEAD"),
        source_tree=git("rev-parse", "HEAD^{tree}"),
        inputs={n: hashlib.sha256((root / n).read_bytes()).hexdigest() for n in INPUTS},
        scenario="import_csv",
        project="v41qa_public_fixture01",
        database="v4_demo_v41_fixture01",
        directory=str(tmp_path / "new-case"),
        pg_image="sha256:" + "a" * 64,
        test_image="sha256:" + "b" * 64,
        api_port=18500,
        web_port=13500,
        pg_subnet="10.242.200.0/24",
        host_subnet="10.242.201.0/24",
        starts_at=(now - timedelta(seconds=1)).isoformat(),
        deadline=(now + timedelta(minutes=10)).isoformat(),
        parent_deadline=(now + timedelta(minutes=15)).isoformat(),
        uid=os.getuid(),
    )
    return manifest, root, now


def test_exact_public_preflight_is_read_only_and_does_not_claim_resources(
    bound: tuple[OwnedManifest, Path, datetime],
) -> None:
    manifest, root, now = bound
    result = manifest.preflight(root, now)
    assert result["runtime"] == "NOT_RUN" and result["image_inventory"] == "NOT_INSPECTED"
    assert not Path(manifest.directory).exists()
    assert "0025" in next(n for n in manifest.inputs if "migrations" in n)


@pytest.mark.parametrize(
    "change",
    [
        {"project": "v4qa_old_case000"},
        {"database": "v4_demo_old"},
        {"scenario": "arbitrary"},
        {"api_port": 13500},
        {"pg_subnet": "10.242.201.0/24"},
        {"test_image": "mutable:tag"},
        {"source_sha": "c" * 40},
        {"inputs": {}},
    ],
)
def test_unbound_or_old_run_identity_refused(
    bound: tuple[OwnedManifest, Path, datetime], change: dict[str, object]
) -> None:
    manifest, root, now = bound
    with pytest.raises(ValueError):
        replace(manifest, **change).validate(root, now)  # type: ignore[arg-type]


def test_insufficient_or_over_parent_window_and_existing_case_refused(
    bound: tuple[OwnedManifest, Path, datetime],
) -> None:
    manifest, root, now = bound
    for changed in [
        replace(manifest, deadline=(now + timedelta(seconds=180)).isoformat()),
        replace(manifest, parent_deadline=now.isoformat()),
    ]:
        with pytest.raises(ValueError):
            changed.validate(root, now)
    Path(manifest.directory).mkdir()
    with pytest.raises(ValueError, match="new canonical"):
        manifest.validate(root, now)


def test_missing_new_migration_or_dirty_source_never_falls_back_to_0024(
    bound: tuple[OwnedManifest, Path, datetime],
) -> None:
    manifest, root, now = bound
    (root / "backend/migrations/versions/0025_v41_catalog_operations.py").unlink()
    with pytest.raises(ValueError):
        manifest.validate(root, now)
