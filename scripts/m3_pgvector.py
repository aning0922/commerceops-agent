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
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

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


STAGES = (
    "BASE_PACKAGE",
    "APT_UPDATE",
    "APT_INSTALL",
    "DEV_HEADERS",
    "LIBPQ",
    "PGVECTOR",
    "COMPILE",
    "INSTALL",
)
LOG_LIMIT = 8 * 1024 * 1024


class LogTooLargeError(ValueError):
    """A complete diagnostic log exceeds the fixed local read bound."""


def build_output_facts(outputs: list[bytes], *, deadline: float) -> dict[str, Any]:
    """Only actual standalone output lines; an echoed RUN program is never execution proof."""
    entered = completed = "NOT_RUN"
    observed_error = "UNKNOWN"
    http_status = None
    for output in outputs:
        if time.monotonic() >= deadline:
            raise TimeoutError("M3 diagnostic budget exhausted")
        for raw_line in output.splitlines():
            if time.monotonic() >= deadline:
                raise TimeoutError("M3 diagnostic budget exhausted")
            raw = raw_line.decode(errors="replace")
            line = re.sub(r"^#[0-9]+ [0-9]+(?:\.[0-9]+)? ", "", raw)
            marker = re.fullmatch(r"M3_IMAGE_STAGE (ENTER|DONE) ([A-Z_]+)", line)
            if marker and marker[2] in STAGES:
                if marker[1] == "ENTER":
                    entered = marker[2]
                else:
                    completed = marker[2]
            if re.fullmatch(r"E: Version '[^'\n]+' for '[^'\n]+' was not found", line):
                observed_error = "APT_PIN_UNAVAILABLE"
            elif line == "E: Unable to correct problems, you have held broken packages.":
                observed_error = "DEPENDENCY_CONFLICT"
            elif re.fullmatch(r"curl: \(6\) .+", line):
                observed_error = "DNS"
            elif re.fullmatch(r"curl: \((?:35|60)\) .+", line):
                observed_error = "TLS"
            elif match := re.fullmatch(
                r"curl: \(22\) The requested URL returned error: ([1-5][0-9]{2})", line
            ):
                observed_error, http_status = "CURL_HTTP_STATUS", int(match[1])
            elif re.fullmatch(
                r"/t[m]p/(?:pg-server-dev.deb|libpq-dev.deb|pgvector.tar.gz): FAILED", line
            ):
                observed_error = "DIGEST"
            elif entered == "COMPILE" and re.fullmatch(r"make(?:\[[0-9]+\])?: \*\*\* .+", line):
                observed_error = "COMPILE"
    if time.monotonic() >= deadline:
        raise TimeoutError("M3 diagnostic budget exhausted")
    return {
        "last_entered": entered,
        "last_completed": completed,
        "observed_error": observed_error,
        "curl_http_status": http_status,
    }


def read_private_log(path: Path, *, deadline: float) -> bytes:
    if time.monotonic() >= deadline:
        raise TimeoutError("M3 diagnostic budget exhausted")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise ValueError("M3 private diagnostic log refused")
        if info.st_size > LOG_LIMIT:
            raise LogTooLargeError("LOG_TOO_LARGE")
        output = stream.read(LOG_LIMIT + 1)
        final_size = os.fstat(stream.fileno()).st_size
        if len(output) > LOG_LIMIT or final_size > LOG_LIMIT:
            raise LogTooLargeError("LOG_TOO_LARGE")
        if final_size != len(output):
            raise ValueError("M3 diagnostic log changed during read")
        if time.monotonic() >= deadline:
            raise TimeoutError("M3 diagnostic budget exhausted")
        return output


def private_log(path: Path) -> BinaryIO:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    info = os.fstat(fd)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        os.close(fd)
        raise ValueError("M3 private diagnostic log refused")
    return os.fdopen(fd, "wb")


def prepare_image(root: Path, stop: datetime, *, diagnostic: dict[str, Any] | None = None) -> None:
    facts: dict[str, Any] = diagnostic if diagnostic is not None else {}
    facts.update(
        stage="ADMISSION",
        code="FAILED",
        returncode="NOT_RUN",
        timedout=False,
        reaped="NOT_RUN",
        source_commit="UNKNOWN",
        source_tree="UNKNOWN",
        inputs={},
    )
    directory: Path | None = None
    logs: list[Path] = []
    try:
        if stop.tzinfo is None:
            raise ValueError("M3 timezone-aware deadline required")
        expires = time.monotonic() + (stop - datetime.now(UTC)).total_seconds()
        duration = min(300, expires - time.monotonic() - 85)
        if duration <= 0:
            raise ValueError("M3 build has no cleanup reserve")
        facts["stage"] = "SOURCE_REVALIDATION"
        inputs, identity = source_hashes(root), source_identity(root, min(5, duration))
        facts.update(inputs=inputs, **identity)
        path = root / RECEIPT
        if path.exists() or path.is_symlink() or (root / ".audit").is_symlink():
            raise ValueError("M3 fresh image receipt required")
        facts["stage"] = "LOGGING"
        audit = root / ".audit"
        audit.mkdir(mode=0o700, exist_ok=True)
        info = audit.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError("M3 private diagnostic directory refused")
        directory = Path(tempfile.mkdtemp(prefix="m3-image-", dir=audit))
        info = directory.lstat()
        if stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.getuid():
            raise ValueError("M3 private diagnostic directory refused")
        logs = [directory / "stdout.private.log", directory / "stderr.private.log"]
        with private_log(logs[0]) as output, private_log(logs[1]) as error:
            duration = min(300, expires - time.monotonic() - 85)
            if duration <= 0:
                raise ValueError("M3 build has no cleanup reserve")
            facts["stage"] = "BUILD"
            child = subprocess.Popen(
                [
                    "docker",
                    "build",
                    "--progress=plain",
                    "-f",
                    str(root / "infrastructure/knowledge_pgvector.Dockerfile"),
                    "-t",
                    IMAGE,
                    str(root),
                ],
                cwd=root,
                stdout=output,
                stderr=error,
                start_new_session=True,
            )
            facts["reaped"] = False
            try:
                child.wait(timeout=duration)
            except subprocess.TimeoutExpired:
                facts["timedout"] = True
                facts["code"] = "BUILD_TIMEOUT"
                raise
            finally:
                facts["stage"] = "BUILD_CLEANUP"
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGTERM)
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait(timeout=5)
                facts.update(returncode=child.returncode, reaped=child.poll() is not None)
                facts["stage"] = "BUILD"
        left = expires - time.monotonic() - 75
        if child.returncode or left <= 0:
            facts["code"] = "BUILD_NONZERO" if child.returncode else "DEADLINE"
            raise ValueError("M3 bounded image build failed")
        facts["stage"] = "SOURCE_REVALIDATION"
        if inputs != source_hashes(root):
            facts["code"] = "SOURCE_CHANGED"
            raise ValueError("M3 bounded image build failed")
        if identity != source_identity(root, min(5, left)):
            facts["code"] = "SOURCE_CHANGED"
            raise ValueError("M3 image build source changed")
        left = expires - time.monotonic() - 75
        if left <= 0:
            raise ValueError("M3 build exhausted preparation window")
        facts["stage"] = "INSPECT_METADATA"
        binding = {**inspect_image(min(5, left)), "inputs": inputs, **identity}
        left = expires - time.monotonic() - 75
        if left <= 0:
            raise ValueError("M3 build exhausted preparation window")
        facts["stage"] = "BINDING"
        validate_binding(root, binding, min(5, left))
        with private_log(path) as stream:
            stream.write(json.dumps(binding, sort_keys=True).encode())
        facts.update(stage="COMPLETE", code="OK")
        print(
            "M3 image built and source/architecture/metadata bound; "
            "SQL extension remains unverified"
        )
    finally:
        if directory is not None:
            facts.pop("logs_sha256", None)
            facts.update(
                diagnostic_stage="UNKNOWN",
                diagnostic_code="NOT_RUN",
                last_entered="UNKNOWN",
                last_completed="UNKNOWN",
                observed_error="UNKNOWN",
                curl_http_status=None,
            )
            now = time.monotonic()
            budget = min(5, expires - now - 75, (stop - datetime.now(UTC)).total_seconds() - 75)
            diagnostic_deadline = now + max(0, budget)
            try:
                if budget <= 0:
                    raise TimeoutError("M3 diagnostic budget exhausted")
                outputs = {p.name: read_private_log(p, deadline=diagnostic_deadline) for p in logs}
                parsed = build_output_facts(list(outputs.values()), deadline=diagnostic_deadline)
                hashes = {}
                for name, data in outputs.items():
                    if time.monotonic() >= diagnostic_deadline:
                        raise TimeoutError("M3 diagnostic budget exhausted")
                    hashes[name] = hashlib.sha256(data).hexdigest()
                if time.monotonic() >= diagnostic_deadline:
                    raise TimeoutError("M3 diagnostic budget exhausted")
                facts.update(parsed, logs_sha256=hashes)
                facts.update(diagnostic_stage="COMPLETE", diagnostic_code="OK")
            except LogTooLargeError:
                facts["diagnostic_code"] = "LOG_TOO_LARGE"
            except TimeoutError:
                facts["diagnostic_code"] = "BUDGET_EXHAUSTED"
            except (OSError, ValueError):
                facts["diagnostic_code"] = "LOG_REFUSED"
            if time.monotonic() < diagnostic_deadline:
                try:
                    with private_log(directory / "diagnostic.safe.json") as stream:
                        stream.write(json.dumps(facts, sort_keys=True).encode())
                except (OSError, ValueError):
                    facts.update(diagnostic_stage="UNKNOWN", diagnostic_code="LOG_WRITE_FAILED")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stop-at-utc", required=True)
    args = parser.parse_args()
    diagnostic: dict[str, Any] = {}
    try:
        prepare_image(ROOT, datetime.fromisoformat(args.stop_at_utc), diagnostic=diagnostic)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        raise SystemExit(
            json.dumps(diagnostic or {"stage": "UNKNOWN", "code": "FAILED"}, sort_keys=True)
        ) from None


if __name__ == "__main__":
    main()
