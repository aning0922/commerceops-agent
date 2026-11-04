"""Bind actual tracked bytes, locks and the exact host executables before/after a run."""

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from .fixed_daemon import file_hash


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
    pins = {
        str(p.resolve(strict=True)): {
            "sha256": file_hash(p.resolve(strict=True)),
            "mode": p.resolve(strict=True).stat().st_mode & 0o777,
        }
        for p in tools
    }
    return {"head": head, "tree": tree, "tracked_sha256": files, "tool_sha256": pins}
