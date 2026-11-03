"""Closed M3 PG image preparation/binding; no PG startup, credentials or application wiring."""

import argparse
import hashlib
import json
import os
import platform
import re
import signal
import stat
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "commerceops-m3-pgvector:8ee1df0-v1"
INPUTS = (
    "compose.yml",
    ".dockerignore",
    "compose.m3.yml",
    "infrastructure/knowledge_pgvector.Dockerfile",
    "infrastructure/knowledge_pgvector.pins.json",
    "scripts/m3_pgvector.py",
)
RECEIPT = ".audit/m3-pgvector-image.safe.json"


def compose_files(root: Path, enabled: bool, overlay: Path | None = None) -> list[str]:
    files = [root / "compose.yml"]
    if enabled:
        files.append(root / "compose.m3.yml")
    if overlay is not None:
        files.append(overlay)
    return [str(path) for path in files]


def compose_flags(root: Path, enabled: bool, overlay: Path | None = None) -> list[str]:
    return [arg for path in compose_files(root, enabled, overlay) for arg in ("-f", path)]


def up_flags(enabled: bool) -> list[str]:
    return ["--no-build", "--pull", "never"] if enabled else []


def source_hashes(root: Path) -> dict[str, str]:
    if any((root / name).is_symlink() for name in INPUTS):
        raise ValueError("M3 image input symlink refused")
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in INPUTS}


def source_identity(root: Path, timeout: float = 5) -> dict[str, str]:
    rows = subprocess.check_output(
        ["git", "rev-parse", "HEAD", "HEAD^{tree}"],
        cwd=root,
        text=True,
        stderr=subprocess.DEVNULL,
        timeout=timeout,
    ).splitlines()
    if len(rows) != 2 or any(not re.fullmatch(r"[0-9a-f]{40}", row) for row in rows):
        raise ValueError("M3 exact source identity refused")
    return dict(zip(("source_commit", "source_tree"), rows, strict=True))


def image_metadata(raw: Any, machine: str) -> dict[str, str]:
    arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64", "AMD64": "amd64"}.get(machine)
    if not arch or not isinstance(raw, list) or len(raw) != 1:
        raise ValueError("M3 image metadata refused")
    info = raw[0]
    if not isinstance(info, dict) or not isinstance(info.get("Config"), dict):
        raise ValueError("M3 image metadata refused")
    config = info["Config"]
    labels = config.get("Labels") or {}
    if not isinstance(labels, dict) or not isinstance(config.get("Env"), list):
        raise ValueError("M3 image metadata refused")
    if (
        not re.fullmatch(r"sha256:[0-9a-f]{64}", str(info.get("Id")))
        or info.get("Os") != "linux"
        or info.get("Architecture") != arch
        or IMAGE not in info.get("RepoTags", [])
        or labels.get("commerceops.pgvector.version") != "0.8.7"
        or labels.get("commerceops.pgvector.commit") != "f37c13f68b57d2c3472b2214fbcff699d6d34876"
        or not {"PG_MAJOR=17", "PG_VERSION=17.11-1.pgdg12+2"}.issubset(config.get("Env", []))
    ):
        raise ValueError("M3 image metadata refused")
    return {"image": IMAGE, "image_id": info["Id"], "architecture": arch}


def inspect_image(timeout: float) -> dict[str, str]:
    result = subprocess.run(
        ["docker", "image", "inspect", IMAGE], capture_output=True, timeout=timeout, check=False
    )
    if result.returncode:
        raise ValueError("M3 prepared image missing")
    return image_metadata(json.loads(result.stdout), platform.machine())


def validate_binding(root: Path, binding: dict[str, Any], timeout: float = 5) -> None:
    if (
        set(binding)
        != {"image", "image_id", "architecture", "inputs", "source_commit", "source_tree"}
        or binding["image"] != IMAGE
        or binding["architecture"] not in {"arm64", "amd64"}
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(binding["image_id"]))
        or binding["inputs"] != source_hashes(root)
        or {key: binding[key] for key in ("source_commit", "source_tree")}
        != source_identity(root, timeout)
    ):
        raise ValueError("M3 frozen image binding changed")


def prepared_image(root: Path, timeout: float) -> dict[str, Any]:
    expires = time.monotonic() + timeout
    path = root / RECEIPT
    info = path.lstat()
    if (
        (root / ".audit").is_symlink()
        or not stat.S_ISREG(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_uid != os.getuid()
    ):
        raise ValueError("M3 image receipt refused")
    binding: dict[str, Any] = json.loads(path.read_text())
    if not isinstance(binding, dict):
        raise ValueError("M3 image receipt refused")
    validate_binding(root, binding, timeout)
    left = expires - time.monotonic()
    if left <= 0:
        raise TimeoutError("M3 image verification budget exhausted")
    actual = inspect_image(left)
    if any(binding[key] != value for key, value in actual.items()):
        raise ValueError("M3 image tag changed")
    return binding


def validate_container(
    root: Path,
    info: dict[str, Any],
    binding: dict[str, Any],
    project: str,
    overlay: Path | None = None,
    *,
    timeout: float = 5,
) -> None:
    validate_binding(root, binding, timeout)
    labels = info["Config"]["Labels"]
    if (
        info["Config"]["Image"] != IMAGE
        or info["Image"] != binding["image_id"]
        or labels.get("com.docker.compose.project") != project
        or labels.get("com.docker.compose.service") != "postgres"
        or labels.get("com.docker.compose.project.working_dir") != str(root)
        or labels.get("com.docker.compose.project.config_files")
        != ",".join(compose_files(root, True, overlay))
    ):
        raise ValueError("M3 PG container identity refused")


def prepare_image(root: Path, stop: datetime) -> None:
    if stop.tzinfo is None:
        raise ValueError("M3 timezone-aware deadline required")
    # The caller's immutable preparation window includes this build. Keep 85s for exit/cleanup.
    expires = time.monotonic() + (stop - datetime.now(UTC)).total_seconds()
    duration = min(300, expires - time.monotonic() - 85)
    if duration <= 0:
        raise ValueError("M3 build has no cleanup reserve")
    inputs, identity = source_hashes(root), source_identity(root, min(5, duration))
    path = root / RECEIPT
    if path.exists() or path.is_symlink() or (root / ".audit").is_symlink():
        raise ValueError("M3 fresh image receipt required")
    duration = min(300, expires - time.monotonic() - 85)
    if duration <= 0:
        raise ValueError("M3 build has no cleanup reserve")
    child = subprocess.Popen(
        [
            "docker",
            "build",
            "-f",
            str(root / "infrastructure/knowledge_pgvector.Dockerfile"),
            "-t",
            IMAGE,
            str(root),
        ],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        child.wait(timeout=duration)
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=5)
    left = expires - time.monotonic() - 75
    if child.returncode or left <= 0 or inputs != source_hashes(root):
        raise ValueError("M3 bounded image build failed")
    if identity != source_identity(root, min(5, left)):
        raise ValueError("M3 image build source changed")
    left = expires - time.monotonic() - 75
    if left <= 0:
        raise ValueError("M3 build exhausted preparation window")
    binding = {**inspect_image(min(5, left)), "inputs": inputs, **identity}
    left = expires - time.monotonic() - 75
    if left <= 0:
        raise ValueError("M3 build exhausted preparation window")
    validate_binding(root, binding, min(5, left))
    path.parent.mkdir(mode=0o700, exist_ok=True)
    with path.open("x") as stream:
        path.chmod(0o600)
        json.dump(binding, stream, sort_keys=True)
    print("M3 image built and source/architecture/metadata bound; SQL extension remains unverified")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stop-at-utc", required=True)
    args = parser.parse_args()
    try:
        prepare_image(ROOT, datetime.fromisoformat(args.stop_at_utc))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        raise SystemExit("M3 bounded image preparation failed (raw output withheld)") from None


if __name__ == "__main__":
    main()
