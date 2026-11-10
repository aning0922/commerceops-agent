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
from .image_provenance import runtime_files
from .owned_manifest import OwnedManifest
from .test_fixed_daemon import tools as daemon_tools
from .test_owned_manifest import bound as bound
from .test_owner_setup import build_fixture

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


@pytest.mark.parametrize("static_bad", [True, False])
def test_static_daemon_mismatch_has_zero_calls_and_server_mismatch_has_identity_only(
    bound: tuple[OwnedManifest, Path, datetime], monkeypatch: MonkeyPatch, static_bad: bool
) -> None:
    manifest, root, _ = bound
    monkeypatch.setattr(driver, "ROOT", root)
    case = driver.Case(**asdict(manifest))
    driver.prepare(case)
    directory = Path(case.directory)
    tool, _, receipt = daemon_tools(root.parent)
    if static_bad:
        receipt["docker_endpoint"] = "tcp://unapproved"
    receipt.update(
        source_sha=case.source_sha,
        source_tree=case.source_tree,
        test_image_id=case.test_image,
    )
    build, raw_expected = build_fixture(
        runtime_files(root), case.source_sha, case.source_tree, case.test_image
    )
    public.private(directory / "image-build.safe.json", json.dumps(build))
    public.private(directory / "expected-runtime.json", raw_expected.decode())
    public.private(directory / "docker-host.safe.json", json.dumps(receipt))
    (root / ".git/info/exclude").write_text(".tools/\nfrontend/node_modules/\n")
    for name in [".tools/node/bin/node", "frontend/node_modules/next/dist/bin/next"]:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("public tool fixture")
    monkeypatch.setattr(driver, "runtime_handoff", lambda _case, **_options: {})
    monkeypatch.setattr(driver, "reserve_ports", lambda *_ports: None)
    monkeypatch.setattr(public, "compose", lambda _case: (str(tool), "compose"))
    if static_bad:
        with pytest.raises(ValueError, match="EXPLICIT_LOCAL_UNIX"):
            driver.execute(case, True)
        assert not tool.with_suffix(".calls").exists()
        assert not (directory / "execution.once").exists()
    else:
        report = driver.execute(case, True)
        calls = [json.loads(line) for line in tool.with_suffix(".calls").read_text().splitlines()]
        assert calls == [["--host", "unix:///approved/local.sock", "info", "--format", "{{.ID}}"]]
        assert not report["information"].get("namespace_initial_empty")
        assert not report["cleanup"]["confirmed"]
        assert [row["stage"] for row in report["required"]] == ["docker_server"]
