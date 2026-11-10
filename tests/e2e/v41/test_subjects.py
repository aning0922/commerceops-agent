"""Concurrent local registry persistence, not concurrent business/PG acceptance."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest

from .subjects import registry

pytestmark = pytest.mark.offline


def test_new_subjects_and_parallel_keys_are_not_lost(tmp_path: Path) -> None:
    context = {
        "tenant_id": str(uuid4()),
        "organization_id": str(uuid4()),
        "principal_id": str(uuid4()),
        "reset_epoch": 0,
        "auth_generation": 0,
    }
    shop = str(uuid4())
    keys = [str(uuid4()) for _ in range(16)]
    registry(tmp_path, context, shop)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(
            pool.map(
                lambda k: registry(tmp_path, context, shop, operation="import_confirm", key=k), keys
            )
        )
    path = tmp_path / "subjects.private.json"
    value = json.loads(path.read_text())
    entry = next(iter(value["scopes"].values()))
    assert len(entry["operations"]) == 16
    registry(
        tmp_path, context, shop, operation="import_confirm", key=keys[0], state="COMMITTED_READBACK"
    )
    assert (
        next(iter(json.loads(path.read_text())["scopes"].values()))["operations"][
            "import_confirm:" + keys[0]
        ]["state"]
        == "COMMITTED_READBACK"
    )
    registry(
        tmp_path, context, shop, operation="preview", key=str(uuid4()), state="UNKNOWN_READBACK"
    )
    assert len(next(iter(json.loads(path.read_text())["scopes"].values()))["operations"]) == 16
    assert path.stat().st_mode & 0o777 == 0o600


def test_global_policy_is_not_a_business_operation(tmp_path: Path) -> None:
    context = {
        "tenant_id": str(uuid4()),
        "organization_id": str(uuid4()),
        "principal_id": str(uuid4()),
        "reset_epoch": 0,
        "auth_generation": 0,
    }
    with pytest.raises(ValueError, match="FIXED_OPERATION"):
        registry(tmp_path, context, str(uuid4()), operation="policy_rotate", key=str(uuid4()))
