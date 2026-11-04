"""Bridge a Root build receipt to measured public source bytes inside an exact image."""

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

# Fixed read-only program; no image-authored verifier, network, host mounts or secrets.
READ_PUBLIC = (
    "import hashlib,json,pathlib,sys; paths=json.load(sys.stdin); "
    "root=pathlib.Path('/app'); "
    "assert len(paths)<=5000; "
    "assert all(isinstance(p,str) and not p.startswith('/') "
    "and '..' not in p.split('/') for p in paths); "
    "assert all((root/p).is_file() and (root/p).resolve().is_relative_to(root) for p in paths); "
    "print(json.dumps({p:hashlib.sha256((root/p).read_bytes()).hexdigest() "
    "for p in paths},sort_keys=True))"
)


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
    receipt: dict[str, Any], source: str, tree: str, image: str, expected: dict[str, str]
) -> None:
    required = {
        "source_sha": source,
        "source_tree": tree,
        "test_image_id": image,
        "test_build_native_exit": 0,
        "runtime_files_sha256": expected,
    }
    if any(receipt.get(k) != v for k, v in required.items()):
        raise ValueError("ROOT_BUILD_SOURCE_INPUT_BINDING_MISMATCH")
    if type(receipt.get("test_build_native_exit")) is not int:
        raise ValueError("ROOT_BUILD_NATIVE_REQUIRED")


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
        image,
        "/app/.venv/bin/python",
        "-I",
        "-c",
        READ_PUBLIC,
    ]


def validate_measured(raw: bytes, expected: dict[str, str]) -> dict[str, object]:
    if len(raw) > 2_000_000 or json.loads(raw) != expected:
        raise ValueError("ACTUAL_IMAGE_PUBLIC_SOURCE_DIFFERS")
    return {
        "status": "IMAGE_RUNTIME_BYTES_MATCH",
        "files": len(expected),
        "manifest_sha256": hashlib.sha256(
            json.dumps(expected, sort_keys=True).encode()
        ).hexdigest(),
    }
