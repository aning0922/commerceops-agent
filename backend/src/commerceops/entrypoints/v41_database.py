"""Explicit owner policy/ACL operations bound to a frozen checkout and private UTC manifest.

This command never migrates, creates a database, seeds a fixture, starts an API, or retries.
Each invocation executes one selected action in one owner transaction and reports after commit.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field

from commerceops.application.v4_demo.contracts import Contract, Timestamp
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.v4_demo_sessions import DemoConfig, bounded
from commerceops.infrastructure.v41_runtime import grant_runtime
from commerceops.infrastructure.v41_security import _owner, activate_policy, config_fingerprint
from commerceops.infrastructure.web_config import WebConfig, private_bytes
from commerceops.infrastructure.web_sessions import now

Sha = Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
OwnedName = Annotated[str, Field(pattern=r"^v4_demo_[a-z0-9_]{1,48}$")]


class OwnerFile(Contract):
    schema_version: Literal["v41-owner-db-v1"]
    host: Annotated[str, Field(min_length=1, max_length=255)]
    port: Annotated[int, Field(ge=1, le=65535)]
    name: OwnedName
    user: Annotated[str, Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")]
    password_file: str


class DemoFile(Contract):
    schema_version: Literal["v4-demo-deployment-v1"]
    web_config_file: str
    api_origin: str
    enabled: bool = False
    allow_non_browser_get: bool = False


class Operation(Contract):
    schema_version: Literal["v41-owner-operation-v1"]
    operation_id: UUID
    action: Literal["inspect", "activate-policy", "grant-runtime"]
    source_root: str
    source_commit: Sha
    source_tree: Sha
    schema_revision: Literal["0025_v41_catalog_operations"]
    database_name: OwnedName
    owner_config_file: str
    owner_config_sha256: Digest
    demo_config_file: str
    demo_config_sha256: Digest
    web_config_sha256: Digest
    deadline: Timestamp


def _read(path: str, digest: str) -> bytes:
    raw = private_bytes(Path(path))
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("V41_CONFIGURATION_CHANGED")
    return raw


def source(spec: Operation) -> None:
    root = Path(__file__).resolve().parents[4]
    if not Path(spec.source_root).is_absolute() or Path(spec.source_root).resolve() != root:
        raise ValueError("V41_SOURCE_MISMATCH")
    git = shutil.which("git")
    if git is None:
        raise ValueError("V41_GIT_REQUIRED")
    result = subprocess.run(  # noqa: S603 - fixed git arguments; checkout identity is data
        [git, "-C", str(root), "rev-parse", "--show-toplevel", "HEAD", "HEAD^{tree}"],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    lines = result.stdout.splitlines()
    if lines != [str(root), spec.source_commit, spec.source_tree]:
        raise ValueError("V41_SOURCE_MISMATCH")
    status = subprocess.run(  # noqa: S603 - fixed read-only git status
        [git, "-C", str(root), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if status.stdout:
        raise ValueError("V41_SOURCE_DIRTY")


def configuration(spec: Operation) -> tuple[DatabaseSettings, DemoConfig]:
    owner = OwnerFile.model_validate_json(_read(spec.owner_config_file, spec.owner_config_sha256))
    if owner.name != spec.database_name or owner.user == "commerceops_app":
        raise ValueError("V41_OWNER_CONFIGURATION")
    settings = DatabaseSettings(
        host=owner.host,
        port=owner.port,
        name=owner.name,
        user=owner.user,
        password_file=Path(owner.password_file),
        runtime_password_file=None,
    )
    settings.bounded_password()  # Validate the exact private 0600 regular file before connecting.
    deployment = DemoFile.model_validate_json(_read(spec.demo_config_file, spec.demo_config_sha256))
    web = WebConfig.from_file(
        Path(deployment.web_config_file), expected_sha256=spec.web_config_sha256
    )
    config = DemoConfig(
        web, deployment.api_origin, deployment.enabled, deployment.allow_non_browser_get
    )
    config_fingerprint(config)
    runtime = config.web.database
    if (runtime.host, runtime.port, runtime.name) != (
        owner.host,
        owner.port,
        owner.name,
    ) or runtime.user != "commerceops_app":
        raise ValueError("V41_CONFIGURATION_TARGET")
    return settings, config


def execute(spec: Operation) -> dict[str, Any]:
    source(spec)
    if datetime.now(UTC) >= spec.deadline:
        raise ValueError("V41_DEADLINE")
    settings, config = configuration(spec)
    with connect(settings) as db:
        bounded(db)
        _owner(db)  # Exact 0025 / v4_demo namespace / PG17.11+vector0.8.7 / actual table owner.
        target = db.execute("SELECT current_database() AS name,current_user AS role").fetchone()
        if target != dict(name=settings.name, role=settings.user):
            raise ValueError("V41_OWNER_TARGET")
        if now(db) >= spec.deadline:
            raise ValueError("V41_DEADLINE")
        if spec.action == "activate-policy":
            result = activate_policy(db, config)
        elif spec.action == "grant-runtime":
            grant_runtime(db, config)
            result = dict(runtime_grants_applied=True)
        else:
            row = db.execute(
                "SELECT active_version,generation FROM business.v41_security_policy WHERE singleton"
            ).fetchone()
            result = dict(
                policy_initialized=row is not None,
                active_version=row["active_version"] if row else None,
                generation=row["generation"] if row else None,
            )
        source(spec)
        if now(db) >= spec.deadline or datetime.now(UTC) >= spec.deadline:
            raise ValueError("V41_DEADLINE")
    # Successful context exit has COMMITted. A lost commit response instead raises to UNKNOWN.
    return dict(
        schema_version="v41-owner-receipt-v1",
        operation_id=str(spec.operation_id),
        action=spec.action,
        source_commit=spec.source_commit,
        source_tree=spec.source_tree,
        database_name=spec.database_name,
        status="COMMITTED" if spec.action != "inspect" else "VERIFIED",
        result=result,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="V41 explicit reviewed owner policy/ACL operation")
    parser.add_argument("--operation-file", required=True, type=Path)
    args = parser.parse_args()
    try:
        spec = Operation.model_validate_json(private_bytes(args.operation_file))
        result = execute(spec)
    except Exception:
        # Never expose database errors, private filenames, key columns, MACs or config input.
        print(
            json.dumps(
                dict(
                    schema_version="v41-owner-receipt-v1",
                    status="UNKNOWN",
                    error="V41_OWNER_OPERATION_FAILED",
                    retryable=False,
                )
            )
        )
        raise SystemExit(1) from None
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
