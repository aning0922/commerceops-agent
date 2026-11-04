"""Fixed archive owner assembly. Standalone -I script: stdlib only until source proof passes.

Only activate-policy, grant-runtime, verify-runtime; no CLI source spoofing, bootstrap or retry.
"""

import argparse
import hashlib
import importlib
import json
import os
import re
import stat
import subprocess
import sys
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

ACTIONS = ("activate-policy", "grant-runtime", "verify-runtime")
PROFILE = Path("/run/v4_owner/v41")
APP = Path("/app")
PROGRAM_SHA256 = "20718b7cb02763253c453f6703687d45ceeb666f3d93b9149318a3822c24636e"
PUBLIC_POLICY = (
    "singleton",
    "active_version",
    "config_digest",
    "generation",
    "activated_at",
    "retired_versions",
)
CONFIG_PATHS = (
    "/run/v4_owner/owner_password",
    "/run/v4_owner/app_password",
    "/run/v4_owner/v41/csrf-key",
    "/run/v4_owner/v41/nonce-key",
    "/run/v4_owner/v41/owner.json",
    "/run/v4_owner/v41/web.json",
    "/run/v4_owner/v41/demo.json",
)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("DUPLICATE_OWNER_INPUT_FIELD")
        result[name] = value
    return result


def decode(raw: bytes) -> dict[str, Any]:
    value = json.loads(raw, object_pairs_hook=strict_object)
    if not isinstance(value, dict):
        raise ValueError("OWNER_OBJECT_REQUIRED")
    return value


def private_bytes(path: Path, limit: int = 2_000_000) -> bytes:
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("OWNER_PRIVATE_ABSOLUTE_PATH_REQUIRED")
    with ExitStack() as stack:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        parent = os.open(path.anchor, flags)
        stack.callback(os.close, parent)
        for part in path.parts[1:-1]:
            parent = os.open(part, flags, dir_fd=parent)
            stack.callback(os.close, parent)
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != os.geteuid()
            ):
                raise ValueError("OWNER_PRIVATE_600_UID_FILE_REQUIRED")
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("OWNER_INPUT_LIMIT")
        return raw


def persist(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(".pending")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.link(temporary, path, follow_symlinks=False)
    temporary.unlink()


def utc(raw: str) -> datetime:
    value = datetime.fromisoformat(raw)
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("OWNER_UTC_REQUIRED")
    return value


def authorization(
    value: dict[str, Any], now: datetime | None = None, *, cleanup: bool = False
) -> None:
    expected = {
        "schema_version",
        "authorization_id",
        "authority",
        "source_sha",
        "source_tree",
        "test_image",
        "pg_image",
        "api_port",
        "web_port",
        "uid",
        "project",
        "database",
        "case_directory",
        "scenario",
        "starts_at",
        "deadline",
        "parent_deadline",
        "owner_actions",
    }
    if (
        set(value) != expected
        or value["schema_version"] != "v41-root-runtime-authorization-v1"
        or value["authority"] != "ROOT_EXACT_REVIEWED_WINDOW"
    ):
        raise ValueError("ROOT_EXACT_REVIEWED_AUTHORIZATION_REQUIRED")
    UUID(value["authorization_id"])
    if (
        not Path(value["case_directory"]).is_absolute()
        or ".." in Path(value["case_directory"]).parts
    ):
        raise ValueError("ROOT_CASE_DIRECTORY_REQUIRED")
    if value["owner_actions"] != list(ACTIONS):
        raise ValueError("OWNER_ACTION_SET_REQUIRED")
    if (
        any(re.fullmatch(r"[a-f0-9]{40}", value[n]) is None for n in ("source_sha", "source_tree"))
        or re.fullmatch(r"sha256:[a-f0-9]{64}", value["test_image"]) is None
    ):
        raise ValueError("ROOT_SOURCE_IMAGE_REQUIRED")
    if (
        re.fullmatch(r"v41qa_[a-z0-9_]{8,32}", value["project"]) is None
        or re.fullmatch(r"v4_demo_v41_[a-z0-9_]{1,40}", value["database"]) is None
    ):
        raise ValueError("ROOT_NEW_OWNED_NAMESPACE_REQUIRED")
    if (
        re.fullmatch(r"sha256:[a-f0-9]{64}", value["pg_image"]) is None
        or type(value["uid"]) is not int
        or value["uid"] != os.geteuid()
    ):
        raise ValueError("ROOT_OWNER_IMAGE_OR_UID_REQUIRED")
    for name in ("api_port", "web_port"):
        if type(value[name]) is not int or not 1024 <= value[name] <= 65535:
            raise ValueError("ROOT_LOOPBACK_PORT_REQUIRED")
    if value["api_port"] == value["web_port"] or value["scenario"] not in {
        "shell_navigation",
        "dashboard_same_source",
        "catalog_orders",
        "import_csv",
        "import_xlsx",
    }:
        raise ValueError("ROOT_FIXED_SCENARIO_OR_PORTS_REQUIRED")
    start, end, parent = (utc(value[n]) for n in ("starts_at", "deadline", "parent_deadline"))
    if (
        not start <= (now or datetime.now(UTC)) < end - timedelta(seconds=0 if cleanup else 180)
        or end > parent
        or (end - start).total_seconds() > 1800
    ):
        raise ValueError("ROOT_RUNTIME_WINDOW_OR_RESERVE_INVALID")


def operation(value: dict[str, Any]) -> None:
    expected = {
        "schema_version",
        "operation_id",
        "source_sha",
        "source_tree",
        "image_id",
        "database",
        "project",
        "authorization_id",
        "uid",
        "starts_at",
        "parent_deadline",
        "attempt_status",
        "action",
        "authorization_sha256",
        "build_receipt_sha256",
        "expected_file_sha256",
        "runtime_manifest_sha256",
        "installed_manifest_sha256",
        "config_files_sha256",
        "deadline",
        "prior_receipt",
    }
    if (
        set(value) != expected
        or value["schema_version"] != "v41-owned-owner-operation-v1"
        or value["action"] not in ACTIONS
    ):
        raise ValueError("FIXED_OWNER_OPERATION_REQUIRED")
    if str(UUID(value["operation_id"])) != value["operation_id"]:
        raise ValueError("OWNER_OPERATION_UUID_REQUIRED")
    if value["attempt_status"] != "REGISTERED_NOT_ATTEMPTED" or type(value["uid"]) is not int:
        raise ValueError("ORIGINAL_OWNER_ATTEMPT_REQUIRED")
    for name in (
        "authorization_sha256",
        "build_receipt_sha256",
        "expected_file_sha256",
        "runtime_manifest_sha256",
        "installed_manifest_sha256",
    ):
        if re.fullmatch(r"[a-f0-9]{64}", value[name]) is None:
            raise ValueError("OWNER_BOUND_INPUT_HASH_REQUIRED")
    if set(value["config_files_sha256"]) != set(CONFIG_PATHS) or any(
        re.fullmatch(r"[a-f0-9]{64}", v) is None for v in value["config_files_sha256"].values()
    ):
        raise ValueError("ALL_OWNER_CONFIG_AND_SECRET_HASHES_REQUIRED")


def installed_expected(expected: dict[str, str]) -> dict[str, str]:
    prefix = "backend/src/commerceops/"
    return {
        name[len(prefix) :]: digest
        for name, digest in expected.items()
        if name.startswith(prefix) and name.endswith(".py")
    }


def manifest_hash(expected: dict[str, str]) -> str:
    return sha(json.dumps(expected, sort_keys=True).encode())


def proof_result(value: dict[str, Any], expected: dict[str, str]) -> None:
    if value != {
        "status": "EXACT_SOURCE_AND_NONEDITABLE_PACKAGE_MATCH",
        "runtime_files": len(expected),
        "installed_python_files": len(installed_expected(expected)),
        "manifest_sha256": manifest_hash(expected),
    } or not installed_expected(expected):
        raise ValueError("ROOT_INSIDE_INSTALLED_PROOF_REQUIRED")


def build_binding(
    receipt: dict[str, Any], auth: dict[str, Any], raw_expected: bytes
) -> dict[str, str]:
    expected = decode(raw_expected)
    binding = receipt["source_binding"]
    if (
        receipt.get("status") != "BUILD_AND_INSIDE_SOURCE_PROOF_PASS"
        or binding["source"] != auth["source_sha"]
        or binding["tree"] != auth["source_tree"]
        or receipt["image"]["id"] != auth["test_image"]
    ):
        raise ValueError("ROOT_BUILD_SOURCE_IMAGE_MISMATCH")
    if (
        receipt["expected_manifest_sha256"] != sha(raw_expected)
        or binding["artifacts"]["expected-runtime.json"] != sha(raw_expected)
        or binding["artifacts"]["verify_inside.py"] != PROGRAM_SHA256
    ):
        raise ValueError("ROOT_BUILD_EXPECTED_FILE_OR_PROGRAM_MISMATCH")
    for stage in ("build", "sourcecheck"):
        rows = [r for r in receipt["commands"] if r["label"] == stage]
        if (
            len(rows) != 1
            or type(rows[0]["native_exit"]) is not int
            or rows[0]["native_exit"] != 0
            or rows[0]["timed_out"] is not False
        ):
            raise ValueError("ROOT_BUILD_NATIVE_PROOF_REQUIRED")
    proof_result(receipt["inside_verification"], expected)
    return expected


def seals(spec: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    raw_auth = private_bytes(PROFILE / "authorization.json")
    if sha(raw_auth) != spec["authorization_sha256"]:
        raise ValueError("OWNER_AUTHORIZATION_CHANGED")
    auth = decode(raw_auth)
    authorization(auth)
    if (
        any(
            spec[n] != auth[n]
            for n in (
                "source_sha",
                "source_tree",
                "database",
                "project",
                "authorization_id",
                "uid",
                "starts_at",
                "parent_deadline",
            )
        )
        or spec["image_id"] != auth["test_image"]
    ):
        raise ValueError("OWNER_OPERATION_ROOT_BINDING_MISMATCH")
    end = utc(spec["deadline"])
    if not datetime.now(UTC) < end <= utc(auth["deadline"]) - timedelta(seconds=180):
        raise ValueError("OWNER_OPERATION_DEADLINE")
    raw_build, raw_expected = (
        private_bytes(PROFILE / "build-receipt.json"),
        private_bytes(PROFILE / "expected-runtime.json"),
    )
    if (
        sha(raw_build) != spec["build_receipt_sha256"]
        or sha(raw_expected) != spec["expected_file_sha256"]
    ):
        raise ValueError("OWNER_BUILD_INPUT_CHANGED")
    expected = build_binding(decode(raw_build), auth, raw_expected)
    if (
        manifest_hash(expected) != spec["runtime_manifest_sha256"]
        or manifest_hash(installed_expected(expected)) != spec["installed_manifest_sha256"]
    ):
        raise ValueError("OWNER_MANIFEST_BINDING_CHANGED")
    for name, digest in spec["config_files_sha256"].items():
        if sha(private_bytes(Path(name), 32768)) != digest:
            raise ValueError("OWNER_CONFIG_OR_SECRET_CHANGED")
    return auth, expected


def source_proof(expected: dict[str, str], deadline: datetime) -> None:
    program = APP / "tests/e2e/v41/verify_inside.txt"
    raw = program.read_bytes()
    if program.is_symlink() or sha(raw) != PROGRAM_SHA256:
        raise ValueError("ROOT_FIXED_INSIDE_PROGRAM_CHANGED")
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", raw.decode()],
        input=json.dumps(expected, sort_keys=True).encode(),
        capture_output=True,
        env={"PATH": os.defpath},
        timeout=min(30, max(0.001, (deadline - datetime.now(UTC)).total_seconds())),
        check=False,
    )
    if result.returncode:
        raise ValueError("OWNER_ACTUAL_SOURCE_OR_INSTALLED_BYTES_DIFFER")
    proof_result(decode(result.stdout), expected)


def configuration(auth: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    # Production imports happen only after copied+installed source has actually passed.
    database = importlib.import_module("commerceops.infrastructure.database")
    sessions = importlib.import_module("commerceops.infrastructure.v4_demo_sessions")
    security = importlib.import_module("commerceops.infrastructure.v41_security")
    runtime = importlib.import_module("commerceops.infrastructure.v41_runtime")
    owner = decode(private_bytes(PROFILE / "owner.json", 32768))
    if owner != {
        "schema_version": "v41-owner-db-v1",
        "host": "postgres",
        "port": 5432,
        "name": auth["database"],
        "user": "commerceops_owner",
        "password_file": "/run/v4_owner/owner_password",
    }:
        raise ValueError("FIXED_NEW_OWNER_CONFIGURATION_REQUIRED")
    settings = database.DatabaseSettings(
        **{k: v for k, v in owner.items() if k != "schema_version"}, runtime_password_file=None
    )
    settings.bounded_password()
    deployment = decode(private_bytes(PROFILE / "demo.json", 32768))
    web = decode(private_bytes(PROFILE / "web.json", 32768))
    if (
        deployment.get("web_config_file") != str(PROFILE / "web.json")
        or web.get("csrf_secret_file") != str(PROFILE / "csrf-key")
        or web.get("nonce_secret_file") != str(PROFILE / "nonce-key")
        or web.get("commerce_sources") is not None
    ):
        raise ValueError("FIXED_NEW_OWNER_CONFIG_PATHS_REQUIRED")
    raw_database = web.get("database", {})
    if raw_database != {
        "host": "postgres",
        "port": 5432,
        "name": auth["database"],
        "user": "commerceops_app",
        "password_file": "/run/v4_owner/app_password",
        "runtime_password_file": None,
    }:
        raise ValueError("FIXED_NEW_RUNTIME_CONFIG_PATHS_REQUIRED")
    config = sessions.DemoConfig.load(PROFILE / "demo.json")
    origins = {"http://127.0.0.1:" + str(auth[n]) for n in ("api_port", "web_port")}
    if (
        set(config.web.origins) != origins
        or config.api_origin != "http://127.0.0.1:" + str(auth["api_port"])
        or config.web.transport_mode != "local_http"
        or not config.enabled
        or config.allow_non_browser_get
    ):
        raise ValueError("FIXED_NEW_OWNER_ORIGINS_REQUIRED")
    if (
        config.web.database.host,
        config.web.database.port,
        config.web.database.name,
        config.web.database.user,
    ) != (
        "postgres",
        5432,
        auth["database"],
        "commerceops_app",
    ) or config.web.database.password_file != Path("/run/v4_owner/app_password"):
        raise ValueError("OWNER_RUNTIME_DATABASE_MISMATCH")
    security.config_fingerprint(config)
    return settings, config, security, runtime


def target(db: Any, auth: dict[str, Any], security: Any, deadline: datetime) -> None:
    security._owner(db)
    row = db.execute(
        "SELECT current_database() AS name,current_user AS role,clock_timestamp() AS stamp"
    ).fetchone()
    if (
        row is None
        or row["name"] != auth["database"]
        or row["role"] != "commerceops_owner"
        or row["stamp"] >= deadline
    ):
        raise ValueError("OWNER_ACTUAL_TARGET_OR_DB_DEADLINE")


def verify_acl(db: Any, config: Any, security: Any, runtime: Any) -> dict[str, Any]:
    tables = ["v41_" + suffix for suffix in runtime.TABLES] + ["v41_security_policy"]
    for table in tables:
        owner = db.execute(
            "SELECT current_user=pg_get_userbyid(relowner) AS allowed "
            "FROM pg_class WHERE oid=to_regclass(%s)",
            ("business." + table,),
        ).fetchone()
        if owner != {"allowed": True}:
            raise ValueError("OWNER_TABLE_OWNERSHIP_MISMATCH")
        exposed = db.execute(
            "SELECT EXISTS(SELECT 1 FROM pg_class c,"
            "LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a "
            "WHERE c.oid=to_regclass(%s) AND a.grantee=0) AS allowed",
            ("business." + table,),
        ).fetchone()
        if exposed != {"allowed": False}:
            raise ValueError("V41_PUBLIC_TABLE_PRIVILEGE_EXPOSED")
        columns = db.execute(
            "SELECT has_any_column_privilege('commerceops_app',%s,'INSERT,UPDATE,REFERENCES') "
            "AS write,has_any_column_privilege('commerceops_app',%s,'SELECT WITH GRANT OPTION') "
            "AS delegate,EXISTS(SELECT 1 FROM pg_attribute a,LATERAL aclexplode(a.attacl) p "
            "WHERE a.attrelid=to_regclass(%s) AND p.grantee=0) AS public",
            ("business." + table,) * 3,
        ).fetchone()
        if columns != {"write": False, "delegate": False, "public": False}:
            raise ValueError("V41_RUNTIME_COLUMN_OR_DELEGATION_ACL_MISMATCH")
        row = db.execute(
            "SELECT has_table_privilege('commerceops_app',%s,'SELECT') AS read,"
            "has_table_privilege('commerceops_app',%s,"
            "'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') AS write",
            ("business." + table,) * 2,
        ).fetchone()
        if row != {"read": table != "v41_security_policy", "write": False}:
            raise ValueError("V41_RUNTIME_TABLE_ACL_MISMATCH")
    for column in (*PUBLIC_POLICY, "invocation_verifier"):
        row = db.execute(
            "SELECT has_column_privilege('commerceops_app',"
            "'business.v41_security_policy',%s,'SELECT') AS allowed",
            (column,),
        ).fetchone()
        if row != {"allowed": column in PUBLIC_POLICY}:
            raise ValueError("V41_POLICY_COLUMN_ACL_MISMATCH")
        public_column = db.execute(
            "SELECT EXISTS(SELECT 1 FROM pg_attribute a, LATERAL aclexplode(a.attacl) c "
            "WHERE a.attrelid='business.v41_security_policy'::regclass "
            "AND a.attname=%s AND c.grantee=0) AS allowed",
            (column,),
        ).fetchone()
        if public_column != {"allowed": False}:
            raise ValueError("V41_PUBLIC_POLICY_COLUMN_EXPOSED")
    oids = set()
    for signature in runtime.RUNTIME:
        row = db.execute(
            "SELECT to_regprocedure(%s)::oid AS id", ("business." + signature,)
        ).fetchone()
        if row is None or row["id"] is None or row["id"] in oids:
            raise ValueError("V41_RUNTIME_SIGNATURE_MISMATCH")
        oids.add(row["id"])
    functions = db.execute(
        "SELECT p.oid AS id,p.proname AS name,"
        "has_function_privilege('commerceops_app',p.oid,'EXECUTE') AS app,"
        "EXISTS(SELECT 1 FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a "
        "WHERE a.grantee=0 AND a.privilege_type='EXECUTE') AS public "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "WHERE n.nspname='business' AND left(p.proname,4)='v41_' ORDER BY p.oid"
    ).fetchall()
    if not oids.issubset({r["id"] for r in functions}) or any(
        r["app"] != (r["id"] in oids) or r["public"] for r in functions
    ):
        raise ValueError("V41_RUNTIME_PRIVATE_FUNCTION_ACL_MISMATCH")
    persona = db.execute(
        "SELECT has_table_privilege('commerceops_app','business.v4_demo_personas',"
        "'INSERT,UPDATE,DELETE,TRUNCATE') AS write"
    ).fetchone()
    if persona != {"write": False}:
        raise ValueError("V41_LIVE_PERSONA_DML_EXPOSED")
    policy = db.execute(
        "SELECT active_version,config_digest,invocation_verifier,generation "
        "FROM business.v41_security_policy WHERE singleton"
    ).fetchone()
    if (
        policy is None
        or not security.policy_matches(policy, config)
        or bytes(policy["invocation_verifier"]) != security.invocation_key(config)
    ):
        raise ValueError("V41_CURRENT_POLICY_FINGERPRINT_MISMATCH")
    return {
        "tables_verified": len(tables),
        "runtime_signatures": list(runtime.RUNTIME),
        "private_functions_verified": len(functions) - len(oids),
        "policy_version": policy["active_version"],
        "policy_generation": policy["generation"],
        "fingerprint_matches": True,
        "private_verifier_app_read": False,
    }


class AttemptSpent(ValueError):
    """The original attempt/receipt stays untouched; no new operation is performed."""


def prior_receipt(spec: dict[str, Any], auth: dict[str, Any]) -> dict[str, Any] | None:
    prior = spec["prior_receipt"]
    if spec["action"] == ACTIONS[0]:
        if prior is not None:
            raise ValueError("FIRST_OWNER_ACTION_HAS_NO_PREDECESSOR")
        return None
    if not isinstance(prior, dict) or set(prior) != {"operation_id", "sha256"}:
        raise ValueError("COMMITTED_OWNER_PREDECESSOR_REQUIRED")
    prior_id = str(UUID(prior["operation_id"]))
    if prior_id != prior["operation_id"] or prior_id == spec["operation_id"]:
        raise ValueError("DISTINCT_OWNER_PREDECESSOR_REQUIRED")
    raw = private_bytes(PROFILE / "receipts" / (prior_id + ".json"))
    result = decode(raw)
    if (
        sha(raw) != prior["sha256"]
        or result.get("status") != "COMMITTED"
        or result.get("action") != ACTIONS[ACTIONS.index(spec["action"]) - 1]
        or any(
            result.get(n) != auth[n]
            for n in ("source_sha", "source_tree", "project", "database", "authorization_id")
        )
        or result.get("image_id") != auth["test_image"]
    ):
        raise ValueError("OWNER_PREDECESSOR_BINDING_MISMATCH")
    return result


def legacy_acl(db: Any) -> str:
    relations = db.execute(
        "SELECT c.oid,c.relname,c.relacl::text AS acl FROM pg_class c "
        "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='business' "
        "AND left(c.relname,4)<>'v41_' ORDER BY c.oid"
    ).fetchall()
    columns = db.execute(
        "SELECT a.attrelid,a.attnum,a.attacl::text AS acl FROM pg_attribute a "
        "JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='business' AND left(c.relname,4)<>'v41_' "
        "AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attrelid,a.attnum"
    ).fetchall()
    functions = db.execute(
        "SELECT p.oid,p.proacl::text AS acl FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='business' "
        "AND left(p.proname,4)<>'v41_' ORDER BY p.oid"
    ).fetchall()
    return sha(json.dumps([relations, columns, functions], sort_keys=True).encode())


def execute(spec: dict[str, Any], manifest_sha256: str) -> dict[str, Any]:
    operation(spec)
    operation_id = spec["operation_id"]
    for path in (PROFILE, PROFILE / "operations", PROFILE / "attempts", PROFILE / "receipts"):
        info = path.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o700
            or info.st_uid != os.geteuid()
            or path.resolve() != path
        ):
            raise ValueError("OWNER_PRIVATE_PROFILE_DIRECTORY_REQUIRED")
    marker = PROFILE / "attempts" / operation_id
    try:
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        raise AttemptSpent("OWNER_ATTEMPT_ALREADY_STARTED") from None
    with os.fdopen(fd, "w") as stream:
        json.dump(
            {
                "operation_id": operation_id,
                "action": spec["action"],
                "manifest_sha256": manifest_sha256,
                "state": "ATTEMPT_STARTED",
            },
            stream,
        )
        stream.flush()
        os.fsync(stream.fileno())
    manifest_path = PROFILE / "operations" / (operation_id + ".json")
    if sha(private_bytes(manifest_path, 32768)) != manifest_sha256:
        raise ValueError("OWNER_OPERATION_FILE_CHANGED")
    auth, expected = seals(spec)
    deadline = utc(spec["deadline"])
    source_proof(expected, deadline)
    prior = prior_receipt(spec, auth)
    settings, config, security, runtime = configuration(auth)
    database = importlib.import_module("commerceops.infrastructure.database")
    with database.connect(settings) as db:
        if spec["action"] == "verify-runtime":
            db.execute("BEGIN READ ONLY")
        db.execute("SET LOCAL statement_timeout='5s'")
        db.execute("SET LOCAL lock_timeout='1s'")
        target(db, auth, security, deadline)
        baseline = legacy_acl(db)
        if prior is not None and prior.get("legacy_acl_sha256") != baseline:
            raise ValueError("LEGACY_ACL_CHANGED_BETWEEN_OWNER_ACTIONS")
        if spec["action"] == "activate-policy":
            result = security.activate_policy(db, config)
        elif spec["action"] == "grant-runtime":
            runtime.grant_runtime(db, config)
            result = {"runtime_grants_applied": True}
        else:
            result = verify_acl(db, config, security, runtime)
        if sha(private_bytes(manifest_path, 32768)) != manifest_sha256:
            raise ValueError("OWNER_OPERATION_FILE_CHANGED_BEFORE_COMMIT")
        again, again_expected = seals(spec)
        if again != auth or again_expected != expected:
            raise ValueError("OWNER_INPUT_CHANGED_DURING_TRANSACTION")
        source_proof(expected, deadline)
        target(db, auth, security, deadline)
        if legacy_acl(db) != baseline:
            raise ValueError("OWNER_OPERATION_WIDENED_LEGACY_ACL")
    return {
        "schema_version": "v41-owned-owner-receipt-v1",
        "operation_id": operation_id,
        "action": spec["action"],
        "authorization_id": auth["authorization_id"],
        "manifest_sha256": manifest_sha256,
        "project": auth["project"],
        "legacy_acl_sha256": baseline,
        "source_sha": auth["source_sha"],
        "source_tree": auth["source_tree"],
        "image_id": auth["test_image"],
        "database": auth["database"],
        "status": "VERIFIED" if spec["action"] == "verify-runtime" else "COMMITTED",
        "result": result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation-file", required=True, type=Path)
    args = parser.parse_args()
    spec: dict[str, Any] = {}
    result: dict[str, Any] | None = None
    try:
        raw = private_bytes(args.operation_file, 32768)
        spec = decode(raw)
        operation(spec)
        if args.operation_file != PROFILE / "operations" / (spec["operation_id"] + ".json"):
            raise ValueError("FIXED_OWNER_OPERATION_PATH_REQUIRED")
        result = execute(spec, sha(raw))
        persist(PROFILE / "receipts" / (spec["operation_id"] + ".json"), result)
    except Exception as error:
        if result is None:
            result = {
                "schema_version": "v41-owned-owner-receipt-v1",
                "operation_id": spec.get("operation_id")
                if isinstance(spec.get("operation_id"), str)
                and re.fullmatch(r"[a-f0-9-]{36}", spec["operation_id"])
                else None,
                "action": spec.get("action") if spec.get("action") in ACTIONS else None,
                "status": "UNKNOWN",
                "retryable": False,
                "error_type": type(error).__name__,
                "sqlstate": getattr(error, "sqlstate", None),
            }
            if (
                not isinstance(error, AttemptSpent)
                and isinstance(spec.get("operation_id"), str)
                and re.fullmatch(r"[a-f0-9-]{36}", spec["operation_id"])
            ):
                try:
                    persist(PROFILE / "receipts" / (spec["operation_id"] + ".json"), result)
                except Exception as write_error:
                    result["receipt_persist_error_type"] = type(write_error).__name__
        else:
            # COMMIT was observed; a subsequent evidence write failure cannot rewrite that fact.
            result["receipt_persist_error_type"] = type(error).__name__
        print(json.dumps(result))
        raise SystemExit(1) from None
    print(json.dumps(result))


if __name__ == "__main__":
    main()
