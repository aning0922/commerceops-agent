"""Private scope/key registry before requests; metadata only, never authority or retry policy."""

import fcntl
import hashlib
import json
import os
import stat
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from uuid import UUID

from .runner import persist

OPERATIONS = frozenset({"preview", "product_tags", "order_fulfillment", "import_confirm"})


def registry(
    directory: Path,
    context: dict[str, Any],
    shop: str,
    *,
    operation: str | None = None,
    key: str | None = None,
    state: str = "ATTEMPT_STARTED",
) -> None:
    info = directory.lstat()
    if (
        directory.resolve() != directory
        or not directory.is_dir()
        or info.st_uid != os.getuid()
        or info.st_mode & 0o777 != 0o700
    ):
        raise ValueError("NEW_PRIVATE_SUBJECT_DIRECTORY_REQUIRED")
    scope = {n: str(UUID(context[n])) for n in ("tenant_id", "organization_id", "principal_id")}
    scope.update(
        shop_id=str(UUID(shop)),
        reset_epoch=context["reset_epoch"],
        auth_generation=context["auth_generation"],
    )
    if operation is not None and (operation not in OPERATIONS or key is None):
        raise ValueError("FIXED_OPERATION_KEY_REQUIRED")
    if key is not None:
        key = str(UUID(key))
    if state not in {
        "ATTEMPT_STARTED",
        "ACK_OK",
        "ACK_COMMITTED",
        "ACK_REJECTED",
        "ACK_UNKNOWN",
        "COMMITTED_READBACK",
        "UNKNOWN_READBACK",
        "SQL_ROLLBACK_VERIFIED",
    }:
        raise ValueError("FIXED_OBSERVATION_STATE_REQUIRED")
    fd = os.open(directory / "subjects.lock", os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = directory / "subjects.private.json"
        value: dict[str, Any] = (
            json.loads(path.read_text())
            if path.exists()
            else {"schema": "v41-subjects-1", "scopes": {}}
        )
        if value.get("schema") != "v41-subjects-1" or not isinstance(value.get("scopes"), dict):
            raise ValueError("SUBJECT_REGISTRY_SCHEMA_MISMATCH")
        identity = hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()
        entry = value["scopes"].setdefault(identity, {"scope": scope, "operations": {}})
        if operation is not None:
            identity_key = operation + ":" + str(key)
            previous = entry["operations"].get(identity_key)
            if previous is None and state in {"COMMITTED_READBACK", "UNKNOWN_READBACK"}:
                return  # A read-only unknown lookup is not a fabricated write attempt.
            history = list(previous.get("observations", [])) if previous else []
            history.append(state)
            if len(history) > 100:
                raise ValueError("BOUNDED_SUBJECT_OBSERVATIONS_REQUIRED")
            entry["operations"][identity_key] = {
                "operation": operation,
                "request_key": key,
                "state": state,
                "observations": history,
            }
        if len(value["scopes"]) > 20 or any(
            len(v["operations"]) > 100 for v in value["scopes"].values()
        ):
            raise ValueError("BOUNDED_SUBJECT_REGISTRY_REQUIRED")
        persist(path, value)


def frozen_subjects(directory: Path) -> bytes:
    """Writers must already be stopped; take a locked, bounded immutable export."""
    from .final_facts import decode_subjects

    fd = os.open(directory / "subjects.lock", os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "r") as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        raw = private_subject_bytes(directory / "subjects.private.json")
        decode_subjects(raw)
        return raw


def private_subject_bytes(path: Path) -> bytes:
    """Same no-follow/owner-private boundary, with the registry's explicit 512KB cap."""
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("PRIVATE_SUBJECT_PATH_REQUIRED")
    with ExitStack() as stack:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        parent = os.open(path.anchor, flags)
        stack.callback(os.close, parent)
        for name in path.parts[1:-1]:
            parent = os.open(name, flags, dir_fd=parent)
            stack.callback(os.close, parent)
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != os.geteuid()
            ):
                raise ValueError("PRIVATE_SUBJECT_FILE_REQUIRED")
            raw = stream.read(512_001)
        if len(raw) > 512_000:
            raise ValueError("SUBJECTS_BOUND_EXCEEDED")
        return raw
