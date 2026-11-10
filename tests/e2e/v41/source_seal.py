"""Bind actual tracked bytes, locks and the exact host executables before/after a run."""

import hashlib
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

from .fixed_daemon import file_hash

# These are generated output or already separately bound dependency/tool environments.
EXCLUDED_PATHS = {"frontend/node_modules", "frontend/.next"}

# Exact public output read from Root's failed r2, never a filename-only exception.
NEXT_ENV_PATH = "frontend/next-env.d.ts"
NEXT_ENV_SHA256 = "0f70629890b72a0a82e91972cc032c04b658b26c265373cb711cf576bfbf8fcc"
NEXT_ENV_BYTES = (
    b'/// <reference types="next" />\n'
    b'/// <reference types="next/image-types/global" />\n'
    b'import "./.next/dev/types/routes.d.ts";\n'
    b'import "./.next/dev/types/root-params.d.ts";\n'
    b"\n"
    b"// NOTE: This file should not be edited\n"
    b"// see https://nextjs.org/docs/app/api-reference/config/typescript for more information.\n"
)


def generated_next_env(root: Path) -> dict[str, Any]:
    parent = root / "frontend"
    if root.resolve() != root or parent.resolve() != parent:
        raise ValueError("CANONICAL_NEXT_ENV_PARENT_REQUIRED")
    try:
        descriptor = os.open(parent / "next-env.d.ts", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return {"status": "ABSENT", "sha256": None}
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        mode = stat.S_IMODE(info.st_mode)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or mode not in {0o600, 0o644}
            or info.st_size != len(NEXT_ENV_BYTES)
        ):
            raise ValueError("CANONICAL_NEXT_ENV_FILE_REQUIRED")
        raw = stream.read(1025)
        if raw != NEXT_ENV_BYTES or hashlib.sha256(raw).hexdigest() != NEXT_ENV_SHA256:
            raise ValueError("CANONICAL_NEXT_ENV_BYTES_REQUIRED")
        return {
            "status": "PRESENT_CANONICAL",
            "sha256": NEXT_ENV_SHA256,
            "uid": info.st_uid,
            "mode": mode,
            "bytes": len(raw),
        }


def matches_source(before: dict[str, Any], after: dict[str, Any]) -> bool:
    """Only absent -> this validated declaration may differ; every other seal field stays exact."""
    absent = {"status": "ABSENT", "sha256": None}
    records = []
    for snapshot in (before, after):
        generated = snapshot.get("generated_inputs")
        if not isinstance(generated, dict) or set(generated) != {NEXT_ENV_PATH}:
            return False
        record = generated[NEXT_ENV_PATH]
        if record != absent and record not in [
            {
                "status": "PRESENT_CANONICAL",
                "sha256": NEXT_ENV_SHA256,
                "uid": os.getuid(),
                "mode": mode,
                "bytes": len(NEXT_ENV_BYTES),
            }
            for mode in (0o600, 0o644)
        ]:
            return False
        records.append(record)
    if {k: v for k, v in before.items() if k != "generated_inputs"} != {
        k: v for k, v in after.items() if k != "generated_inputs"
    }:
        return False
    return bool(records[0] == records[1] or records[0] == absent)


def reject_new_inputs(root: Path, tracked: dict[str, str]) -> None:
    for relative in ("frontend", "backend", "tests", "scripts"):
        directory = root / relative
        if not directory.exists():
            continue
        for parent, directories, names in os.walk(directory, followlinks=False):
            directories[:] = [
                n
                for n in directories
                if n != "__pycache__"
                and (Path(parent) / n).relative_to(root).as_posix() not in EXCLUDED_PATHS
            ]
            for name in directories:
                if (Path(parent) / name).is_symlink():
                    raise ValueError("UNAPPROVED_SOURCE_DIRECTORY_SYMLINK")
            for name in names:
                path = Path(parent) / name
                relative_name = path.relative_to(root).as_posix()
                if relative_name == "frontend/tsconfig.tsbuildinfo":
                    continue
                if relative_name not in tracked:
                    if relative_name == NEXT_ENV_PATH:
                        generated_next_env(
                            root
                        )  # Validate contents/metadata, never ignore by name.
                    else:
                        raise ValueError("UNAPPROVED_UNTRACKED_RUNTIME_INPUT")


def snapshot(root: Path, tools: list[Path]) -> dict[str, Any]:
    def git(*args: str) -> bytes:
        return subprocess.check_output(["git", *args], cwd=root)

    head = git("rev-parse", "HEAD").decode().strip()
    tree = git("rev-parse", "HEAD^{tree}").decode().strip()
    entries = git("ls-tree", "-rz", "HEAD").split(b"\0")
    files = {}
    for entry in entries:
        if not entry:
            continue
        metadata, raw_name = entry.split(b"\t", 1)
        mode, kind, oid = metadata.decode().split()
        name = raw_name.decode()
        path = root / name
        if (
            kind != "blob"
            or mode not in ("100644", "100755")
            or path.resolve() != path
            or not path.is_file()
        ):
            raise ValueError("TRACKED_REGULAR_FILE_REQUIRED")
        raw = path.read_bytes()
        blob = b"blob " + str(len(raw)).encode() + b"\0" + raw
        measured_oid = (
            hashlib.sha1(blob, usedforsecurity=False).hexdigest()
            if len(oid) == 40
            else hashlib.sha256(blob).hexdigest()
        )
        executable = bool(path.stat().st_mode & 0o111)
        if measured_oid != oid or executable != (mode == "100755"):
            raise ValueError("ACTUAL_TRACKED_BYTES_DIFFER_FROM_HEAD")
        files[name] = hashlib.sha256(raw).hexdigest()
    if not files or git("diff", "--name-only", "--cached", "HEAD").strip():
        raise ValueError("CLEAN_TRACKED_SOURCE_REQUIRED")
    reject_new_inputs(root, files)
    pins = {
        str(p.resolve(strict=True)): {
            "sha256": file_hash(p.resolve(strict=True)),
            "mode": p.resolve(strict=True).stat().st_mode & 0o777,
        }
        for p in tools
    }
    return {
        "head": head,
        "tree": tree,
        "tracked_sha256": files,
        "tool_sha256": pins,
        "generated_inputs": {NEXT_ENV_PATH: generated_next_env(root)},
    }
