"""Only new private-file preparation and pre-Docker admission; no runtime resources."""

import hashlib
import json
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from tests.e2e.v4 import owned_driver as public

from . import owned_driver as driver
from .owned_manifest import OwnedManifest
from .test_owned_manifest import bound as bound

pytestmark = pytest.mark.offline


def test_prepare_uses_new_random_private_inputs_and_v41_binding(
    bound: tuple[OwnedManifest, Path, datetime], monkeypatch: MonkeyPatch
) -> None:
    manifest, root, _ = bound
    monkeypatch.setattr(driver, "ROOT", root)
    case = driver.Case(**asdict(manifest))
    driver.prepare(case)
    directory = Path(case.directory)
    assert json.loads((directory / "case.json").read_text())["source_sha"] == manifest.source_sha
    seal = json.loads((directory / "config.seal.json").read_text())
    assert seal == {
        str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in driver.config_files(directory)
    }
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in driver.config_files(directory))
    assert directory.stat().st_mode & 0o777 == 0o700
    second = replace(
        case,
        directory=str(directory.with_name("second-case")),
        project="v41qa_second_new_case",
        database="v4_demo_v41_second",
    )
    driver.prepare(second)
    assert (directory / "api/csrf-key").read_bytes() != (
        Path(second.directory) / "api/csrf-key"
    ).read_bytes()
    with pytest.raises(ValueError):
        driver.prepare(case)


def test_execute_requires_root_window_and_unaligned_handoff_blocks_before_docker(
    bound: tuple[OwnedManifest, Path, datetime], monkeypatch: MonkeyPatch
) -> None:
    manifest, root, _ = bound
    monkeypatch.setattr(driver, "ROOT", root)
    case = driver.Case(**asdict(manifest))
    with pytest.raises(ValueError, match="ROOT_EXACT"):
        driver.execute(case, False)
    driver.prepare(case)

    def forbidden(*args: object) -> None:
        pytest.fail("Docker/compose must not be reached before API/SQL handoff")

    monkeypatch.setattr(public, "compose", forbidden)
    with pytest.raises(ValueError, match="HANDOFF_PENDING"):
        driver.execute(case, True)
    assert not (Path(case.directory) / "execution.once").exists()
