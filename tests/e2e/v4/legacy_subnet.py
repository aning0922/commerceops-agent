"""Explicit private IPAM adapter for the two unchanged legacy Web launchers only."""

import argparse
import hashlib
import importlib
import json
import os
import re
import stat
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from scripts.pg_diagnostic import check_subnet_available, owned_subnet

ROOT = Path(__file__).resolve().parents[3]
MODULES = {
    "web": "tests.e2e.web.run_live_batches",
    "n01": "tests.e2e.web.run_c09_n01",
}
STAGES = {"web": ("read", "write", "items"), "n01": ("n01",)}


def stage_subnets(entry: str, values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        stage, separator, subnet = value.partition("=")
        if not separator or stage not in STAGES[entry] or stage in result:
            raise ValueError("exact distinct legacy stage subnets required")
        result[stage] = owned_subnet(subnet)
    if set(result) != set(STAGES[entry]) or len(set(result.values())) != len(result):
        raise ValueError("one distinct subnet per fixed stage required")
    return result


def capture(command: list[str], seconds: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=seconds, check=False)


def private_directory(path: Path) -> None:
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
        or path.resolve() != path
    ):
        raise ValueError("owned canonical private 0700 directory required")


def bind_overlay(directory: Path, subnet: str, stage: str) -> None:
    """Only append default IPAM to the launcher's exact private port overlay."""
    subnet = owned_subnet(subnet)
    if stage not in (*STAGES["web"], "n01"):
        raise ValueError("fixed legacy stage required")
    private_directory(directory)
    check_subnet_available(subnet, capture)
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(directory_fd)
        current = directory.lstat()
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise ValueError("private directory changed")
        fd = os.open("compose-port.json", os.O_RDWR | os.O_NOFOLLOW, dir_fd=directory_fd)
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1
                or info.st_size > 4096
            ):
                raise ValueError("owned private regular 0600 overlay required")
            original = os.read(fd, 4097)
            value = json.loads(original)
            # Exact old launcher shape: reject any preexisting network or extra service.
            ports = value["services"]["postgres"]["ports"]
            if (
                value != {"services": {"postgres": {"ports": ports}}}
                or not isinstance(ports, list)
                or len(ports) != 1
                or not isinstance(ports[0], str)
                or not re.fullmatch(r"127\.0\.0\.1:[1-9][0-9]{0,4}:5432", ports[0])
                or not 1 <= int(ports[0].split(":")[1]) <= 65535
            ):
                raise ValueError("exact legacy port overlay required")
            value["networks"] = {"default": {"ipam": {"config": [{"subnet": subnet}]}}}
            updated = (json.dumps(value, sort_keys=True) + "\n").encode()
            receipt = {
                "stage": stage,
                "subnet": subnet,
                "owner_uid": os.getuid(),
                "overlay": str(directory / "compose-port.json"),
                "original_sha256": hashlib.sha256(original).hexdigest(),
                "overlay_sha256": hashlib.sha256(updated).hexdigest(),
            }
            # Exclusive receipt first: a failed/partial attempt cannot be silently replayed.
            record = os.open(
                "legacy-subnet.safe.json",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory_fd,
            )
            with os.fdopen(record, "wb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write((json.dumps(receipt, sort_keys=True) + "\n").encode())
                stream.flush()
                os.fsync(stream.fileno())
            os.lseek(fd, 0, os.SEEK_SET)
            with os.fdopen(os.dup(fd), "wb") as stream:
                stream.write(updated)
                stream.flush()
                os.ftruncate(stream.fileno(), len(updated))
                os.fsync(stream.fileno())
            os.fsync(directory_fd)
        finally:
            os.close(fd)
    finally:
        os.close(directory_fd)


def run(
    entry: str,
    private: Path,
    deadline: datetime,
    subnets: dict[str, str],
    source_sha: str,
    owner: str = "reviewer",
) -> None:
    if entry not in MODULES or subnets != stage_subnets(
        entry, [f"{stage}={subnet}" for stage, subnet in subnets.items()]
    ):
        raise ValueError("closed legacy entry required")
    if owner not in ("b", "reviewer", "ci"):
        raise ValueError("closed legacy owner required")
    if (
        not private.is_absolute()
        or private.parent.resolve() != private.parent
        or private.exists()
        or private.is_symlink()
    ):
        raise ValueError("new canonical absolute private directory required")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha) or head != source_sha:
        raise ValueError("exact Root frozen source required")
    subprocess.run(
        ["git", "diff", "--exit-code", "HEAD", "--"], cwd=ROOT, capture_output=True, check=True
    )
    module: Any = importlib.import_module(MODULES[entry])
    original = cast(Callable[[Path, bool, Path | None], list[str]], module.compose_flags)
    seen: set[str] = set()

    def compose_flags(root: Path, enabled: bool, overlay: Path | None = None) -> list[str]:
        if root != ROOT or enabled is not True or overlay is None:
            raise ValueError("exact M3 legacy compose call required")
        stage = overlay.parent.name if entry == "web" else "n01"
        expected = private / stage if entry == "web" else private
        if stage not in subnets or stage in seen or overlay != expected / "compose-port.json":
            raise ValueError("unexpected or repeated legacy overlay path")
        if entry == "web":
            private_directory(private)
        bind_overlay(expected, subnets[stage], stage)
        seen.add(stage)
        return original(root, enabled, overlay)

    module.compose_flags = compose_flags
    try:
        if entry == "web":
            module.main(ROOT, private, deadline, "read,write,items", owner, True)
        else:
            module.main(private, deadline, True)
    finally:
        module.compose_flags = original


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry", choices=tuple(MODULES), required=True)
    parser.add_argument("--private-directory", type=Path, required=True)
    parser.add_argument("--stop-at-utc", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--stage-subnet", action="append", required=True)
    parser.add_argument("--owner", choices=("b", "reviewer", "ci"), default="reviewer")
    args = parser.parse_args()
    run(
        args.entry,
        args.private_directory,
        datetime.fromisoformat(args.stop_at_utc.replace("Z", "+00:00")),
        stage_subnets(args.entry, args.stage_subnet),
        args.source_sha,
        args.owner,
    )


if __name__ == "__main__":
    main()
