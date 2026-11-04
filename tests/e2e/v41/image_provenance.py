"""Bridge a Root build receipt to measured public source bytes inside an exact image."""

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

# Verbatim Root-approved 490 inside-proof program; raw-file hash differs from manifest hash.
READ_PUBLIC = Path(__file__).with_name("verify_inside.txt").read_text()


def runtime_files(root: Path) -> dict[str, str]:
    paths = subprocess.check_output(
        [
            "git",
            "ls-tree",
            "-r",
            "--name-only",
            "HEAD",
            "--",
            "backend",
            "tests",
            "scripts",
            "pyproject.toml",
            "uv.lock",
            ".python-version",
        ],
        cwd=root,
        text=True,
    ).splitlines()
    if not paths or len(paths) > 5000:
        raise ValueError("PUBLIC_RUNTIME_FILE_SET_REQUIRED")
    result = {}
    for name in paths:
        path = root / name
        if path.resolve() != path or not path.is_file():
            raise ValueError("REGULAR_PUBLIC_RUNTIME_FILE_REQUIRED")
        result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def validate_build(
    receipt: dict[str, Any],
    source: str,
    tree: str,
    image: str,
    expected: dict[str, str],
    raw_expected: bytes,
) -> None:
    from .owner_setup import build_binding

    if (
        build_binding(
            receipt, {"source_sha": source, "source_tree": tree, "test_image": image}, raw_expected
        )
        != expected
    ):
        raise ValueError("ROOT_BUILD_SOURCE_INPUT_BINDING_MISMATCH")


def probe_argv(docker: str, project: str, image: str, cwd: Path, uid: int) -> list[str]:
    if (
        not Path(docker).is_absolute()
        or not re.fullmatch(r"v41qa_[a-z0-9_]{8,32}", project)
        or not re.fullmatch(r"sha256:[a-f0-9]{64}", image)
    ):
        raise ValueError("FIXED_OWNED_IMAGE_PROBE_REQUIRED")
    return [
        docker,
        "run",
        "--rm",
        "--pull",
        "never",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        str(uid),
        "--name",
        project + "-sourcecheck",
        "--label",
        "com.docker.compose.project=" + project,
        "--label",
        "com.docker.compose.service=v41-sourcecheck",
        "--label",
        "com.docker.compose.project.working_dir=" + str(cwd),
        "--workdir",
        "/app",
        "-i",
        "--entrypoint",
        "/app/.venv/bin/python",
        image,
        "-I",
        "-B",
        "-c",
        READ_PUBLIC,
    ]


def validate_measured(raw: bytes, expected: dict[str, str]) -> dict[str, Any]:
    from .owner_setup import installed_expected, manifest_hash, proof_result

    if len(raw) > 2_000_000:
        raise ValueError("ACTUAL_IMAGE_PUBLIC_SOURCE_LIMIT")
    value = json.loads(raw)
    proof_result(value, expected)
    return {**value, "installed_manifest_sha256": manifest_hash(installed_expected(expected))}
