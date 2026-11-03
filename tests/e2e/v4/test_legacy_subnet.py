"""No Docker/API/browser launch; launcher and inventory calls are doubles."""

import hashlib
import importlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.e2e.v4 import legacy_subnet as target

pytestmark = pytest.mark.offline


def overlay(path: Path) -> bytes:
    path.mkdir(mode=0o700)
    data = b'{"services":{"postgres":{"ports":["127.0.0.1:32123:5432"]}}}\n'
    file = path / "compose-port.json"
    file.write_bytes(data)
    file.chmod(0o600)
    return data


@pytest.mark.parametrize("entry", ["web", "n01"])
def test_fixed_full_stage_sets(entry: str) -> None:
    values = [f"{stage}=10.242.{i}.0/24" for i, stage in enumerate(target.STAGES[entry])]
    assert set(target.stage_subnets(entry, values)) == set(target.STAGES[entry])


@pytest.mark.parametrize(
    "values",
    [
        [],
        ["read=10.242.1.0/24"],
        ["wrong=10.242.1.0/24"],
        ["n01=10.242.1.1/24"],
        ["n01=8.8.8.0/24"],
        ["n01=10.242.1.0/23"],
        ["n01=10.242.1.0/24", "n01=10.242.2.0/24"],
    ],
)
def test_reject_bad_stage_or_subnet(values: list[str]) -> None:
    with pytest.raises(ValueError):
        target.stage_subnets("n01", values)


def test_duplicate_stage_subnets_rejected() -> None:
    with pytest.raises(ValueError):
        target.stage_subnets("web", [f"{s}=10.242.1.0/24" for s in target.STAGES["web"]])


def test_preserve_ports_digest_and_single_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "owned"
    original = overlay(directory)
    checks: list[str] = []
    monkeypatch.setattr(target, "check_subnet_available", lambda subnet, _: checks.append(subnet))
    target.bind_overlay(directory, "10.242.1.0/24", "read")
    assert checks == ["10.242.1.0/24"]
    file = directory / "compose-port.json"
    result = json.loads(file.read_bytes())
    assert result.pop("networks") == {
        "default": {"ipam": {"config": [{"subnet": "10.242.1.0/24"}]}}
    }
    assert result == json.loads(original)
    receipt = directory / "legacy-subnet.safe.json"
    facts = json.loads(receipt.read_text())
    assert facts["original_sha256"] == hashlib.sha256(original).hexdigest()
    assert facts["overlay_sha256"] == hashlib.sha256(file.read_bytes()).hexdigest()
    assert receipt.stat().st_mode & 0o777 == 0o600
    assert file.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError):
        target.bind_overlay(directory, "10.242.1.0/24", "read")


@pytest.mark.parametrize(
    "case",
    [
        "symlink",
        "hardlink",
        "permissions",
        "directory_mode",
        "extra_service",
        "network",
        "port",
        "receipt",
        "overlap",
    ],
)
def test_reject_private_boundary_before_modification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    directory = tmp_path / "owned"
    overlay(directory)
    file = directory / "compose-port.json"
    monkeypatch.setattr(target, "check_subnet_available", lambda *_: None)
    if case == "symlink":
        other = directory / "other"
        file.rename(other)
        file.symlink_to(other)
    elif case == "hardlink":
        os.link(file, directory / "other")
    elif case == "permissions":
        file.chmod(0o644)
    elif case == "directory_mode":
        directory.chmod(0o755)
    elif case in ("extra_service", "network", "port"):
        content = json.loads(file.read_text())
        if case == "extra_service":
            content["services"]["other"] = {}
        elif case == "network":
            content["networks"] = {}
        else:
            content["services"]["postgres"]["ports"] = ["0.0.0.0:32123:5432"]
        file.write_text(json.dumps(content))
    elif case == "receipt":
        (directory / "legacy-subnet.safe.json").write_text("existing")
    else:

        def refuse(*_: object) -> None:
            raise ValueError("overlap")

        monkeypatch.setattr(target, "check_subnet_available", refuse)
    before = file.read_bytes()
    with pytest.raises((ValueError, OSError)):
        target.bind_overlay(directory, "10.242.1.0/24", "read")
    assert file.read_bytes() == before


@pytest.mark.parametrize("entry", ["web", "n01"])
def test_only_fixed_launchers_and_original_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entry: str,
) -> None:
    private = tmp_path / "new"
    sha = "a" * 40
    calls: list[tuple[object, ...]] = []
    subnets = target.stage_subnets(
        entry, [f"{s}=10.242.{i}.0/24" for i, s in enumerate(target.STAGES[entry])]
    )
    module = SimpleNamespace()

    def flags(root: Path, enabled: bool, file: Path) -> list[str]:
        assert root == target.ROOT and enabled
        assert json.loads(file.read_text())["networks"]["default"]["ipam"]["config"]
        return ["-f", str(root / "compose.yml"), "-f", str(file)]

    module.compose_flags = flags

    def main(*args: object) -> None:
        calls.append(args)
        private.mkdir(mode=0o700)
        for stage in target.STAGES[entry]:
            directory = private / stage if entry == "web" else private
            if entry == "web":
                overlay(directory)
            else:
                # overlay helper requires a nonexistent directory.
                private.rmdir()
                overlay(private)
            expected = [
                "-f",
                str(target.ROOT / "compose.yml"),
                "-f",
                str(directory / "compose-port.json"),
            ]
            assert (
                module.compose_flags(target.ROOT, True, directory / "compose-port.json") == expected
            )
            with pytest.raises(ValueError):
                module.compose_flags(target.ROOT, True, directory / "compose-port.json")

    module.main = main

    def load(name: str) -> SimpleNamespace:
        assert name == target.MODULES[entry]
        return module

    monkeypatch.setattr(importlib, "import_module", load)
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: sha + "\n")
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: None)
    monkeypatch.setattr(target, "check_subnet_available", lambda *_: None)
    deadline = datetime(2099, 1, 1, tzinfo=UTC)
    target.run(entry, private, deadline, subnets, sha)
    assert module.compose_flags is flags
    assert calls == (
        [(target.ROOT, private, deadline, "read,write,items", "reviewer", True)]
        if entry == "web"
        else [(private, deadline, True)]
    )


def test_inventory_capture_is_bounded_readonly(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    target.capture(["docker", "network", "ls"], 5)
    assert calls == [
        (
            ["docker", "network", "ls"],
            {
                "capture_output": True,
                "text": True,
                "timeout": 5,
                "check": False,
            },
        )
    ]


@pytest.mark.parametrize("case", ["entry", "existing", "wrong_sha", "dirty"])
def test_preflight_refuses_before_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    private = tmp_path / "new"
    if case == "existing":
        private.mkdir()

    def forbid(_: str) -> None:
        raise AssertionError("no launcher import permitted")

    monkeypatch.setattr(importlib, "import_module", forbid)
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: "a" * 40)

    def clean(*a: object, **kw: object) -> None:
        if case == "dirty":
            raise subprocess.CalledProcessError(1, "git")

    monkeypatch.setattr(subprocess, "run", clean)
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        target.run(
            "unknown" if case == "entry" else "n01",
            private,
            datetime(2099, 1, 1, tzinfo=UTC),
            {"n01": "10.242.1.0/24"},
            ("b" if case == "wrong_sha" else "a") * 40,
        )
