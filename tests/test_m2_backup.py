"""Offline restore guards; these do not claim an actual dump/restore or PG pass."""

from copy import deepcopy
from typing import Any

import pytest

from scripts.m2_backup import BackupFailure, empty_target, no_other_clients, same_snapshot

pytestmark = pytest.mark.offline


class Answers:
    def __init__(self, values: list[int]):
        self.values = iter(values)
        self.commands: list[str] = []

    def execute(self, command: str) -> Any:
        self.commands.append(command)
        assert command.startswith("SELECT ")
        return self

    def fetchone(self) -> dict[str, int]:
        return {"n": next(self.values)}


@pytest.mark.parametrize("active", [1, 2])
def test_active_source_client_blocks_backup(active: int) -> None:
    with pytest.raises(BackupFailure, match="M2_DATABASE_CLIENTS_REMAIN"):
        no_other_clients(Answers([active]))  # type: ignore[arg-type]


@pytest.mark.parametrize("schemas,objects", [(1, 0), (0, 1), (2, 3)])
def test_existing_target_never_becomes_restore_candidate(schemas: int, objects: int) -> None:
    db = Answers([0, schemas, objects])
    with pytest.raises(BackupFailure, match="M2_RESTORE_TARGET_NOT_EMPTY"):
        empty_target(db)  # type: ignore[arg-type]
    assert len(db.commands) == 3


def test_empty_target_check_does_not_seed_or_migrate() -> None:
    db = Answers([0, 0, 0])
    empty_target(db)  # type: ignore[arg-type]
    assert len(db.commands) == 3


@pytest.mark.parametrize("key", ["checkpoint", "approval", "role", "schema"])
def test_restore_requires_exact_checkpoint_business_role_and_schema(key: str) -> None:
    before: dict[str, Any] = {
        "checkpoint": {"count": 1, "sha256": "old"},
        "approval": {"expires_at": "original", "nonce": "original"},
        "role": {"rolsuper": False},
        "schema": "0018",
    }
    same_snapshot(before, deepcopy(before))
    after = deepcopy(before)
    after[key] = "changed"
    with pytest.raises(BackupFailure, match="M2_RESTORE_SNAPSHOT_MISMATCH"):
        same_snapshot(before, after)
