"""Private metadata/argv assembly only; fake catalog records are never runtime evidence."""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from tests.e2e.v4.owned_driver import private

from . import owned_driver as driver
from . import owner_bridge as bridge
from .image_provenance import runtime_files
from .owned_manifest import OwnedManifest
from .owner_setup import ACTIONS, CONFIG_PATHS, operation, private_bytes, sha
from .test_owned_manifest import bound as bound
from .test_owner_setup import authorization, build_fixture

pytestmark = pytest.mark.offline


def test_exact_owner_recipe_is_bound_to_root_case_config_and_real_files(
    bound: tuple[OwnedManifest, Path, datetime],
    monkeypatch: MonkeyPatch,
) -> None:
    manifest, root, _ = bound
    monkeypatch.setattr(driver, "ROOT", root)
    case = driver.Case(**asdict(manifest))
    driver.prepare(case)
    directory = Path(case.directory)
    value = authorization()
    for field in (
        "source_sha",
        "source_tree",
        "test_image",
        "pg_image",
        "project",
        "database",
        "scenario",
        "starts_at",
        "deadline",
        "parent_deadline",
        "uid",
        "api_port",
        "web_port",
    ):
        value[field] = getattr(case, field)
    value["case_directory"] = case.directory
    private(directory / "runtime-authorization.json", json.dumps(value))
    assert bridge.authorize_case(case) == value
    build, raw = build_fixture(
        runtime_files(root), case.source_sha, case.source_tree, case.test_image
    )
    private(directory / "image-build.safe.json", json.dumps(build))
    private(directory / "expected-runtime.json", raw.decode())
    bridge.bind_inputs(directory, value)
    path, spec = bridge.operation_file(case, value, ACTIONS[0], None)
    operation(spec)
    assert private_bytes(path) == json.dumps(spec).encode()
    assert spec["source_sha"] == case.source_sha and spec["image_id"] == case.test_image
    assert spec["config_files_sha256"] == {
        name: sha(private_bytes(directory / "owner" / Path(name).relative_to("/run/v4_owner")))
        for name in CONFIG_PATHS
    }
    assert not list((directory / "owner/v41/attempts").iterdir())
    assert not (directory / "execution.once").exists()
    args = bridge.argv(("/fixed/docker", "compose", "--project-name", case.project), case, spec)
    assert args[-1] == "/run/v4_owner/v41/operations/" + spec["operation_id"] + ".json"
    assert "-T" in args and "--rm" in args and "never" in args
    assert args[args.index("pg-test") + 1 : args.index("--operation-file")] == [
        "/app/.venv/bin/python",
        "-I",
        "-B",
        "/app/tests/e2e/v41/owner_setup.py",
    ]
    assert json.loads(private_bytes(directory / "owner/v41/web.json"))["csrf_secret_file"] == str(
        Path("/run/v4_owner/v41") / "csrf-key"
    )
    assert private_bytes(directory / "owner/v41/csrf-key") == private_bytes(
        directory / "api/csrf-key"
    )
    with pytest.raises(ValueError):
        bridge.operation_file(case, value, "bootstrap", None)
    bad = {**value, "source_sha": "0" * 40}
    (directory / "runtime-authorization.json").write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="AUTHORIZATION_CASE_MISMATCH"):
        bridge.authorize_case(case)
