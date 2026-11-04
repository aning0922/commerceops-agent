"""Owner binding and ACL verdict components. No owner SQL, services or runtime acceptance."""

import copy
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pytest import MonkeyPatch

from . import owner_setup as setup

pytestmark = pytest.mark.offline


def authorization() -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "schema_version": "v41-root-runtime-authorization-v1",
        "authorization_id": str(uuid4()),
        "authority": "_".join(("ROOT", "EXACT", "REVIEWED", "WINDOW")),
        "source_sha": "a" * 40,
        "source_tree": "b" * 40,
        "test_image": "sha256:" + "c" * 64,
        "pg_image": "sha256:" + "d" * 64,
        "project": "v41qa_owner_fixture01",
        "database": "v4_demo_v41_owner_fixture",
        "case_directory": "/new/private/case",
        "scenario": "catalog_orders",
        "uid": os.geteuid(),
        "api_port": 18501,
        "web_port": 13501,
        "starts_at": (now - timedelta(seconds=1)).isoformat(),
        "deadline": (now + timedelta(minutes=10)).isoformat(),
        "parent_deadline": (now + timedelta(minutes=15)).isoformat(),
        "owner_actions": list(setup.ACTIONS),
    }


def build_fixture(
    expected: dict[str, str],
    source: str = "a" * 40,
    tree: str = "b" * 40,
    image: str = "sha256:" + "c" * 64,
) -> tuple[dict[str, Any], bytes]:
    raw = json.dumps(expected, sort_keys=True, indent=2).encode()
    receipt = {
        "status": "BUILD_AND_INSIDE_SOURCE_PROOF_PASS",
        "source_binding": {
            "source": source,
            "tree": tree,
            "artifacts": {
                "expected-runtime.json": setup.sha(raw),
                "verify_inside.py": setup.PROGRAM_SHA256,
            },
        },
        "expected_manifest_sha256": setup.sha(raw),
        "image": {"id": image},
        "commands": [
            {"label": name, "native_exit": 0, "timed_out": False}
            for name in ("build", "sourcecheck")
        ],
        "inside_verification": {
            "status": "EXACT_SOURCE_AND_NONEDITABLE_PACKAGE_MATCH",
            "runtime_files": len(expected),
            "installed_python_files": len(setup.installed_expected(expected)),
            "manifest_sha256": setup.manifest_hash(expected),
        },
    }
    return receipt, raw


def spec(action: str = "activate-policy") -> dict[str, Any]:
    auth = authorization()
    return {
        "schema_version": "v41-owned-owner-operation-v1",
        "operation_id": str(uuid4()),
        "action": action,
        "source_sha": auth["source_sha"],
        "source_tree": auth["source_tree"],
        "image_id": auth["test_image"],
        "database": auth["database"],
        "project": auth["project"],
        "authorization_id": auth["authorization_id"],
        "uid": auth["uid"],
        "starts_at": auth["starts_at"],
        "parent_deadline": auth["parent_deadline"],
        "attempt_status": "REGISTERED_NOT_ATTEMPTED",
        "authorization_sha256": "a" * 64,
        "build_receipt_sha256": "b" * 64,
        "expected_file_sha256": "c" * 64,
        "runtime_manifest_sha256": "d" * 64,
        "installed_manifest_sha256": "e" * 64,
        "config_files_sha256": {p: "f" * 64 for p in setup.CONFIG_PATHS},
        "deadline": (datetime.now(UTC) + timedelta(minutes=2)).isoformat(),
        "prior_receipt": None,
    }


def test_exact_three_actions_and_root_window_have_no_ready_bypass() -> None:
    value = authorization()
    setup.authorization(value)
    for changes in (
        {"owner_actions": ["bootstrap"]},
        {"authority": "READY"},
        {"database": "existing_m3"},
        {"deadline": datetime.now(UTC).isoformat()},
        {"uid": True},
    ):
        with pytest.raises(ValueError):
            setup.authorization({**value, **changes})
    with pytest.raises(ValueError, match="FINITE_JSON"):
        setup.decode(b'{"value":NaN}')
    with pytest.raises(ValueError, match="DUPLICATE"):
        setup.decode(b'{"value":1,"value":2}')
    setup.operation(spec())
    with pytest.raises(ValueError):
        setup.operation(spec("bootstrap"))
    bad = spec()
    bad["config_files_sha256"].pop(setup.CONFIG_PATHS[0])
    with pytest.raises(ValueError, match="ALL_OWNER_CONFIG"):
        setup.operation(bad)


def test_root_build_raw_file_hash_and_sorted_manifest_hash_are_distinct() -> None:
    expected = {"backend/src/commerceops/__init__.py": "a" * 64, "uv.lock": "b" * 64}
    receipt, raw = build_fixture(expected)
    assert setup.sha(raw) != setup.manifest_hash(expected)
    auth = authorization()
    assert setup.build_binding(receipt, auth, raw) == expected
    for mutation in ("raw", "native", "installed"):
        bad = copy.deepcopy(receipt)
        if mutation == "raw":
            bad["expected_manifest_sha256"] = setup.manifest_hash(expected)
        elif mutation == "native":
            bad["commands"][0]["native_exit"] = True
        else:
            bad["inside_verification"]["installed_python_files"] = 0
        with pytest.raises(ValueError):
            setup.build_binding(bad, auth, raw)


def test_private_inputs_and_receipts_never_follow_aliases_or_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    setup.persist(path, {"original": "receipt"})
    before = path.read_bytes()
    assert setup.private_bytes(path) == before
    alias = tmp_path / "alias"
    alias.symlink_to(path)
    with pytest.raises(OSError):
        setup.private_bytes(alias)
    with pytest.raises(FileExistsError):
        setup.persist(path, {"replacement": "refused"})
    assert path.read_bytes() == before
    path.chmod(0o644)
    with pytest.raises(ValueError, match="600_UID"):
        setup.private_bytes(path)


def test_first_attempt_failure_stays_spent_before_any_database_io(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    (tmp_path / "operations").mkdir(mode=0o700)
    (tmp_path / "attempts").mkdir(mode=0o700)
    (tmp_path / "receipts").mkdir(mode=0o700)
    monkeypatch.setattr(setup, "PROFILE", tmp_path)

    def denied(_spec: dict[str, Any]) -> Any:
        raise ValueError("BOUND_SOURCE_REFUSED_BEFORE_DB")

    monkeypatch.setattr(setup, "seals", denied)
    value = spec()
    raw = json.dumps(value).encode()
    path = tmp_path / "operations" / (value["operation_id"] + ".json")
    path.write_bytes(raw)
    path.chmod(0o600)
    with pytest.raises(ValueError, match="SOURCE_REFUSED"):
        setup.execute(value, setup.sha(raw))
    original = (tmp_path / "attempts" / value["operation_id"]).read_bytes()
    with pytest.raises(setup.AttemptSpent):
        setup.execute(value, setup.sha(raw))
    assert (tmp_path / "attempts" / value["operation_id"]).read_bytes() == original
    changed_key = {**value, "operation_id": str(uuid4())}
    with pytest.raises(setup.AttemptSpent, match="ACTION_ALREADY"):
        setup.execute(changed_key, "0" * 64)


def test_observed_commit_survives_receipt_write_failure(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: Any
) -> None:
    profile = tmp_path
    (profile / "operations").mkdir(mode=0o700)
    value = spec()
    path = profile / "operations" / (value["operation_id"] + ".json")
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    monkeypatch.setattr(setup, "PROFILE", profile)
    monkeypatch.setattr(
        setup,
        "execute",
        lambda _value, _digest: {"status": "COMMITTED", "operation_id": value["operation_id"]},
    )

    def failed_write(*_args: Any) -> None:
        raise OSError("public fixture failure")

    monkeypatch.setattr(setup, "persist", failed_write)
    monkeypatch.setattr(sys, "argv", ["owner_setup.py", "--operation-file", str(path)])
    with pytest.raises(SystemExit) as caught:
        setup.main()
    assert caught.value.code == 1
    assert json.loads(capsys.readouterr().out) == {
        "status": "COMMITTED",
        "operation_id": value["operation_id"],
        "receipt_persist_error_type": "OSError",
    }


@pytest.mark.parametrize(
    ("row_index", "privilege"),
    ((0, "delegate"), (1, "delegate"), (0, "public"), (1, "public"), (1, "app")),
)
def test_function_acl_rejects_extra_privilege_on_runtime_or_private_function(
    row_index: int, privilege: str
) -> None:
    # Catalog-row components only: this is the predicate used by verify_acl,
    # not evidence of an actual PostgreSQL GRANT or owner action.
    ordinary = [
        {"id": 101, "app": True, "public": False, "delegate": False},
        {"id": 202, "app": False, "public": False, "delegate": False},
    ]
    setup.verify_function_privileges(ordinary, {101})
    excessive = copy.deepcopy(ordinary)
    excessive[row_index][privilege] = True
    with pytest.raises(ValueError, match="FUNCTION_ACL_MISMATCH"):
        setup.verify_function_privileges(excessive, {101})
    setup.verify_function_privileges(ordinary, {101})


def test_function_acl_requires_every_runtime_oid_and_its_execute_permission() -> None:
    with pytest.raises(ValueError, match="FUNCTION_ACL_MISMATCH"):
        setup.verify_function_privileges([], {101})
    with pytest.raises(ValueError, match="FUNCTION_ACL_MISMATCH"):
        setup.verify_function_privileges(
            [{"id": 101, "app": False, "public": False, "delegate": False}], {101}
        )
