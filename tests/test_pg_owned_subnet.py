"""Explicit M3-owned IPAM only; all Docker calls are doubles, no daemon changes."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts import pg_diagnostic as pg
from scripts.m3_pgvector import compose_files

pytestmark = pytest.mark.offline


@pytest.mark.parametrize(
    "value", ["172.16.241.0/24", "172.16.242.0/24", "10.9.8.0/24", "192.168.255.0/24"]
)
def test_explicit_private_canonical_network(value: str) -> None:
    assert pg.owned_subnet(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "172.16.241/24",
        "172.16.241.1/24",
        "172.16.241.0/255.255.255.0",
        "172.16.241.0/23",
        "172.32.0.0/24",
        "127.0.0.0/24",
        "169.254.0.0/24",
        "100.64.0.0/24",
        "192.0.2.0/24",
        "8.8.8.0/24",
        "fc00::/24",
        "10.00.0.0/24",
        " 10.0.0.0/24",
    ],
)
def test_reject_noncanonical_or_non_rfc1918(value: str) -> None:
    with pytest.raises(ValueError):
        pg.owned_subnet(value)


def test_overlay_is_network_only_exclusive_private_and_hash_bound(tmp_path: Path) -> None:
    path, digest = pg.subnet_overlay(tmp_path, "172.16.241.0/24")
    assert json.loads(path.read_text()) == {
        "networks": {"default": {"ipam": {"config": [{"subnet": "172.16.241.0/24"}]}}}
    }
    assert path.stat().st_mode & 0o777 == 0o600
    pg.verify_subnet_overlay(path, digest)
    assert compose_files(tmp_path, True, path) == [
        str(tmp_path / "compose.yml"),
        str(tmp_path / "compose.m3.yml"),
        str(path),
    ]
    with pytest.raises(FileExistsError):
        pg.subnet_overlay(tmp_path, "172.16.242.0/24")
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError):
        pg.verify_subnet_overlay(path, digest)


@pytest.mark.parametrize(
    "case",
    [
        "clear",
        "equal",
        "supernet",
        "subnet",
        "malformed",
        "inspect_fail",
        "changed",
        "ls_fail",
        "timeout",
    ],
)
def test_readonly_inventory_overlap_and_incomplete_snapshot_fail_closed(case: str) -> None:
    calls: list[list[str]] = []
    ranges = {
        "clear": "172.16.240.0/24",
        "equal": "172.16.241.0/24",
        "supernet": "172.16.0.0/16",
        "subnet": "172.16.241.0/25",
    }

    def capture(command: list[str], seconds: float) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert seconds == 5
        if case == "timeout":
            raise subprocess.TimeoutExpired("synthetic", 5)
        if command[2] == "ls":
            data = "b" * 64 if case == "changed" and len(calls) > 1 else "a" * 64
            return subprocess.CompletedProcess(command, int(case == "ls_fail"), data, "")
        assert command[:3] == ["docker", "network", "inspect"]
        data = (
            "bad"
            if case == "malformed"
            else json.dumps([{"Subnet": ranges.get(case, "172.16.240.0/24")}])
        )
        return subprocess.CompletedProcess(command, int(case == "inspect_fail"), data, "")

    if case == "clear":
        pg.check_subnet_available("172.16.241.0/24", capture)
    else:
        with pytest.raises((ValueError, subprocess.TimeoutExpired)):
            pg.check_subnet_available("172.16.241.0/24", capture)
    assert all(command[2] in {"ls", "inspect"} for command in calls)


def test_non_m3_flag_rejected_before_any_resource(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pg, "ROOT", tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "pg",
            "--deadline",
            "2099-01-01T00:00:00Z",
            "--round",
            "1",
            "--owned-subnet",
            "172.16.241.0/24",
        ],
    )
    with pytest.raises(SystemExit):
        pg.main()
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("wrong", [False, True])
def test_registered_cleanup_requires_exact_ordered_config_files(wrong: bool) -> None:
    files = [
        "/source/compose.yml",
        "/source/compose.m3.yml",
        "/source/runtime/owned/owned-subnet.json",
    ]
    commands: list[list[str]] = []

    def capture(command: list[str], seconds: float) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[1] == "inspect":
            info: dict[str, Any] = {
                "Name": "/owned-cli",
                "Id": "a" * 64,
                "Config": {
                    "Labels": {
                        "com.docker.compose.project": "owned",
                        "com.docker.compose.project.config_files": ",".join(
                            files[::-1] if wrong else files
                        ),
                    }
                },
                "State": {"Running": False, "Pid": 0, "Status": "exited"},
            }
            return subprocess.CompletedProcess(command, 0, json.dumps([info]), "")
        return subprocess.CompletedProcess(command, 0, "a" * 64, "")

    if wrong:
        with pytest.raises(RuntimeError):
            pg.cleanup_registered_containers(
                ["owned-cli"], "owned", capture, lambda *a: None, config_files=files
            )
        assert len(commands) == 1
    else:
        assert (
            pg.cleanup_registered_containers(
                ["owned-cli"], "owned", capture, lambda *a: None, config_files=files
            )
            == 1
        )
