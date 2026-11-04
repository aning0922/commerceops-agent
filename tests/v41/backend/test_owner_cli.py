"""Private manifest/path/source refusal before database IO; no owner operation execution."""

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from commerceops.entrypoints import v41_database as cli
from pydantic import ValidationError

pytestmark = pytest.mark.offline


def spec(**changes: Any) -> cli.Operation:
    value = dict(
        schema_version="v41-owner-operation-v1",
        operation_id=str(uuid4()),
        action="inspect",
        source_root="/not-the-checkout",
        source_commit="a" * 40,
        source_tree="b" * 40,
        schema_revision="0025_v41_catalog_operations",
        database_name="v4_demo_cli",
        owner_config_file="/never-read/owner",
        owner_config_sha256="c" * 64,
        demo_config_file="/never-read/demo",
        demo_config_sha256="d" * 64,
        web_config_sha256="e" * 64,
        deadline=(datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
    )
    value.update(changes)
    return cli.Operation.model_validate_json(json.dumps(value))


def test_wrong_source_precedes_private_config_or_database_access() -> None:
    with pytest.raises(ValueError, match="V41_SOURCE_MISMATCH"):
        cli.execute(spec())
    with pytest.raises(ValueError, match="V41_SOURCE_MISMATCH"):
        cli.source(spec(source_root="relative-checkout"))


@pytest.mark.parametrize(
    "changes",
    [
        dict(action="init-fixture"),
        dict(action="migrate"),
        dict(action="start-api"),
        dict(database_name="existing_m3"),
        dict(role="admin"),
        dict(source_commit="not-a-commit"),
        dict(schema_revision="0024_v4_demo_foundation"),
    ],
)
def test_manifest_rejects_expanded_actions_targets_and_authority(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        spec(**changes)


def test_private_file_hash_mode_and_symlink_guards(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    path = root / "private.json"
    path.write_bytes(b'{"fixed":"value"}')
    path.chmod(0o600)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert cli._read(str(path), digest) == path.read_bytes()
    with pytest.raises(ValueError, match="CONFIGURATION_CHANGED"):
        cli._read(str(path), "0" * 64)
    alias = root / "alias.json"
    alias.symlink_to(path)
    with pytest.raises(OSError):
        cli._read(str(alias), digest)
    path.chmod(0o644)
    with pytest.raises(ValueError):
        cli._read(str(path), digest)


def test_owner_database_mismatch_rejected_before_password_or_demo_read(tmp_path: Path) -> None:
    path = tmp_path.resolve() / "owner.json"
    path.write_text(
        json.dumps(
            dict(
                schema_version="v41-owner-db-v1",
                host="127.0.0.1",
                port=5432,
                name="v4_demo_other",
                user="owned_operator",
                password_file=str(Path("/never-read/owner-file")),
            )
        )
    )
    os.chmod(path, 0o600)
    operation = spec(
        owner_config_file=str(path),
        owner_config_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    with pytest.raises(ValueError, match="OWNER_CONFIGURATION"):
        cli.configuration(operation)
