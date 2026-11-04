"""Host assembly for the three fixed owner actions; no daemon/DB calls during preparation."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from tests.e2e.v4.owned_driver import private

from .owner_setup import (
    ACTIONS,
    CONFIG_PATHS,
    authorization,
    decode,
    installed_expected,
    manifest_hash,
    private_bytes,
    sha,
)

PROFILE = "/run/v4_owner/v41"


def config_paths(directory: Path) -> list[Path]:
    return [
        directory / "owner" / Path(name).relative_to("/run/v4_owner")
        for name in CONFIG_PATHS
        if name not in {"/run/v4_owner/owner_password", "/run/v4_owner/app_password"}
    ]


def prepare(directory: Path, database: str) -> None:
    profile = directory / "owner/v41"
    profile.mkdir(mode=0o700)
    for name in ("operations", "attempts", "receipts"):
        (profile / name).mkdir(mode=0o700)
    for name in ("csrf-key", "nonce-key"):
        private(profile / name, private_bytes(directory / "api" / name).decode())
    web = json.loads(private_bytes(directory / "api/web.json"))
    web["database"]["password_file"] = str(Path("/run/v4_owner") / "app_password")
    web["csrf_secret_file"] = PROFILE + "/csrf-key"
    web["nonce_secret_file"] = PROFILE + "/nonce-key"
    private(profile / "web.json", json.dumps(web))
    deployment = json.loads(private_bytes(directory / "api/demo.json"))
    deployment["web_config_file"] = PROFILE + "/web.json"
    private(profile / "demo.json", json.dumps(deployment))
    private(
        profile / "owner.json",
        json.dumps(
            {
                "schema_version": "v41-owner-db-v1",
                "host": "postgres",
                "port": 5432,
                "name": database,
                "user": "commerceops_owner",
                "password_file": "/run/v4_owner/owner_password",
            }
        ),
    )


def authorize_case(case: Any, *, final: bool = False) -> dict[str, Any]:
    path = Path(case.directory) / "runtime-authorization.json"
    if not path.is_file():
        raise ValueError("V41_RUNTIME_HANDOFF_PENDING")
    auth = decode(private_bytes(path, 32768))
    authorization(auth, cleanup=final)
    fields = {
        "source_sha": case.source_sha,
        "source_tree": case.source_tree,
        "test_image": case.test_image,
        "pg_image": case.pg_image,
        "project": case.project,
        "database": case.database,
        "case_directory": case.directory,
        "scenario": case.scenario,
        "starts_at": case.starts_at,
        "deadline": case.deadline,
        "parent_deadline": case.parent_deadline,
        "uid": case.uid,
        "api_port": case.api_port,
        "web_port": case.web_port,
    }
    if any(auth.get(n) != v for n, v in fields.items()):
        raise ValueError("ROOT_RUNTIME_AUTHORIZATION_CASE_MISMATCH")
    return dict(auth)


def bind_inputs(directory: Path, auth: dict[str, Any]) -> None:
    profile = directory / "owner/v41"
    for target, source in (
        ("authorization.json", "runtime-" + "authorization.json"),
        ("build-receipt.json", "image-build.safe.json"),
        ("expected-runtime.json", "expected-runtime.json"),
    ):
        private(profile / target, private_bytes(directory / source).decode())
    private(directory / "api/runtime-authorization.json", json.dumps(auth))


def operation_file(
    case: Any, auth: dict[str, Any], action: str, prior: dict[str, Any] | None
) -> tuple[Path, dict[str, Any]]:
    if action not in ACTIONS:
        raise ValueError("FIXED_OWNER_ACTION_REQUIRED")
    directory = Path(case.directory)
    profile = directory / "owner/v41"
    expected = json.loads(private_bytes(profile / "expected-runtime.json"))
    value: dict[str, Any] = {
        "schema_version": "v41-owned-owner-operation-v1",
        "operation_id": str(uuid4()),
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
        "action": action,
        "authorization_sha256": sha(private_bytes(profile / "authorization.json")),
        "build_receipt_sha256": sha(private_bytes(profile / "build-receipt.json")),
        "expected_file_sha256": sha(private_bytes(profile / "expected-runtime.json")),
        "runtime_manifest_sha256": manifest_hash(expected),
        "installed_manifest_sha256": manifest_hash(installed_expected(expected)),
        "config_files_sha256": {
            name: sha(
                private_bytes(directory / "owner" / Path(name).relative_to("/run/v4_owner"), 32768)
            )
            for name in CONFIG_PATHS
        },
        "deadline": (datetime.fromisoformat(auth["deadline"]) - timedelta(seconds=180)).isoformat(),
        "prior_receipt": None,
    }
    if prior is not None:
        previous = profile / "receipts" / (prior["operation_id"] + ".json")
        value["prior_receipt"] = {
            "operation_id": prior["operation_id"],
            "sha256": sha(private_bytes(previous)),
        }
    path = profile / "operations" / (value["operation_id"] + ".json")
    private(path, json.dumps(value))
    # Host intent exists before any owner SQL attempt; no replacement key on failure.
    private(
        profile / (value["operation_id"] + ".intent.json"),
        json.dumps(
            {
                "operation_id": value["operation_id"],
                "action": action,
                "manifest_sha256": sha(private_bytes(path)),
                "state": "REGISTERED_NOT_ATTEMPTED",
            }
        ),
    )
    return path, value


def argv(compose: tuple[str, ...], case: Any, value: dict[str, Any]) -> list[str]:
    return [
        *compose,
        "run",
        "--rm",
        "--no-deps",
        "--pull",
        "never",
        "-T",
        "--name",
        case.project + "-owner-" + value["operation_id"],
        "pg-test",
        "/app/.venv/bin/python",
        "-I",
        "-B",
        "/app/tests/e2e/v41/owner_setup.py",
        "--operation-file",
        PROFILE + "/operations/" + value["operation_id"] + ".json",
    ]


def receipt(
    directory: Path, auth: dict[str, Any], spec: dict[str, Any], stdout: bytes
) -> dict[str, Any]:
    raw = private_bytes(directory / "owner/v41/receipts" / (spec["operation_id"] + ".json"))
    result = json.loads(raw)
    if (
        result != json.loads(stdout)
        or result.get("operation_id") != spec["operation_id"]
        or result.get("action") != spec["action"]
        or result.get("status")
        != ("VERIFIED" if spec["action"] == "verify-runtime" else "COMMITTED")
        or any(
            result.get(n) != auth[n]
            for n in ("source_sha", "source_tree", "database", "project", "authorization_id")
        )
        or result.get("image_id") != auth["test_image"]
    ):
        raise ValueError("ACTUAL_OWNER_RECEIPT_MISSING_OR_MISMATCH")
    if spec["action"] == "verify-runtime":
        private(directory / "api/owner-setup-verification.json", raw.decode())
    return dict(result)
