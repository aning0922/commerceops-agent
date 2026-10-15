"""P4专用验收的来源、阶段、SQL和结果合同；没有CLI或真实平台默认入口。"""

import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Literal, cast

CONTRACT = "p4-acceptance-preparation-v1"
CP_DATA_TABLES = ("checkpoints", "checkpoint_blobs", "checkpoint_writes")
BUSINESS_0015 = frozenset(
    """alembic_version analysis_reports approval_resumes approvals audit_events
business_tasks commerce_snapshots conversations executions explanation_links
explanation_task_results identities inbox_events inventory_intent_requests
inventory_intent_results jobs model_call_observations
model_calls model_explanations model_stage_budgets organizations outbox outbox_reconciliations
p3_observations p3_revalidation_failures p3_revalidation_transitions
p3_task_sources p3_template_results
p4_base_deliveries p4_base_links p4_card_bindings p4_clarification_replies p4_im_deliveries
p4_inbox_receipts p4_read_replies p4_sdk_calls p4_sdk_windows p4_sender_state
principal_role_shop_grants principal_shop_scopes principals replenishment_items
replenishment_plans shops snapshot_order_lines snapshot_products snapshot_refunds
web_credentials web_login_attempts web_requests web_sessions""".split()
)
STAGES = (
    "SOURCE",
    "RESOURCE",
    "SCHEMA",
    "ROLE",
    "PREPARE",
    "PREFLIGHT",
    "ARM",
    "AUTHORIZE",
    "CALL",
    "PERSIST",
    "REPLAY",
    "T6",
    "V2",
    "RESTART",
    "PAGE",
    "COLLECT",
    "STOP",
    "CLEANUP",
)
PREFIXES = ("commerceops", "scripts", "tests")


class AcceptanceFailure(RuntimeError):
    """仅固定代码，禁止将底层参数或message放进公共诊断。"""

    def __init__(self, code: str, *, query_id: str | None = None, sqlstate: str | None = None):
        if not re.fullmatch(r"P4A_[A-Z0-9_]+", code):
            code = "P4A_INTERNAL"
        super().__init__(code)
        self.code, self.query_id = code, query_id
        self.sqlstate = sqlstate


def require(condition: bool, code: str) -> None:
    if not condition:
        raise AcceptanceFailure(code)


def digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def binary_digest(path: Path) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode), "P4A_FILE_TYPE")
        result = hashlib.file_digest(stream, "sha256").hexdigest()
        after = os.fstat(stream.fileno())
        require(
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
            "P4A_FILE_CHANGED",
        )
        return result


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def bound_bytes(path: Path, expected: str | None = None, *, private: bool = False) -> bytes:
    """同一个nofollow fd校验并读取；拒绝FIFO、symlink和过大文件。"""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode), "P4A_FILE_TYPE")
            if private:
                require(
                    before.st_uid == os.geteuid() and stat.S_IMODE(before.st_mode) == 0o600,
                    "P4A_PRIVATE_MODE",
                )
            require(before.st_size <= 16 * 1024 * 1024, "P4A_FILE_SIZE")
            body = stream.read(16 * 1024 * 1024 + 1)
            after = os.fstat(stream.fileno())
            current = os.lstat(path)
            require(
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                and (current.st_dev, current.st_ino) == (after.st_dev, after.st_ino)
                and len(body) == before.st_size,
                "P4A_FILE_CHANGED",
            )
            require(expected is None or digest(body) == expected, "P4A_SOURCE_HASH")
            return body
    except OSError:
        raise AcceptanceFailure("P4A_FILE_OPEN") from None


def write_private(path: Path, value: Any) -> None:
    """新/已有本轮私有普通文件的原子替换；不接受未知模式或symlink。"""
    require(path.parent.is_dir(), "P4A_PRIVATE_PARENT")
    parent = os.lstat(path.parent)
    require(
        stat.S_ISDIR(parent.st_mode)
        and stat.S_IMODE(parent.st_mode) == 0o700
        and parent.st_uid == os.geteuid(),
        "P4A_PRIVATE_PARENT",
    )
    if path.exists() or path.is_symlink():
        bound_bytes(path, private=True)
    import secrets

    temporary = path.with_name("." + secrets.token_hex(12))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def safe_failure(error: BaseException, stage: str, query_id: str | None = None) -> dict[str, Any]:
    require(stage in STAGES, "P4A_STAGE_UNKNOWN")
    state = getattr(error, "sqlstate", None)
    result: dict[str, Any] = {
        "stage": stage,
        "code": error.code if isinstance(error, AcceptanceFailure) else "P4A_OPERATION_FAILED",
        "category": type(error).__name__,
        "query_id": query_id
        or getattr(error, "p4a_query_id", None)
        or (error.query_id if isinstance(error, AcceptanceFailure) else None),
        "sqlstate": state
        if isinstance(state, str) and re.fullmatch(r"[0-9A-Z]{5}", state)
        else None,
    }
    trace = error.__traceback__
    locations = []
    while trace is not None:
        locations.append(
            {
                "file": Path(trace.tb_frame.f_code.co_filename).name,
                "function": trace.tb_frame.f_code.co_name,
                "line": trace.tb_lineno,
            }
        )
        trace = trace.tb_next
    result["locations"] = locations
    if type(error).__module__ == "tests.e2e.web.m1_acceptance_capture":
        value = error.safe()  # type: ignore[attr-defined]
        if isinstance(value, dict):
            result.update({k: value[k] for k in ("code", "query_id", "sqlstate")})
    # Pydantic原始input/ctx/msg不进入输出。loc仅合同字段名或整数下标。
    from pydantic import BaseModel, ValidationError

    if isinstance(error, ValidationError):
        classes = list(BaseModel.__subclasses__())
        fields: set[str] = set()
        while classes:
            model = classes.pop()
            fields.update(model.model_fields)
            classes.extend(model.__subclasses__())
        result["dto_errors"] = [
            {
                "loc": [
                    p if isinstance(p, int) else p if p in fields else "<field>" for p in e["loc"]
                ],
                "type": e["type"],
            }
            for e in error.errors(include_url=False, include_context=False, include_input=False)
        ]
    return result


@dataclass
class StageReport:
    required: tuple[str, ...]
    stages: dict[str, dict[str, Any]] = field(init=False)

    def __post_init__(self) -> None:
        require(len(set(self.required)) == len(self.required), "P4A_STAGE_DUPLICATE")
        require(all(s in STAGES for s in self.required), "P4A_STAGE_UNKNOWN")
        self.stages = {s: {"state": "NOT_RUN"} for s in self.required}

    @contextmanager
    def enter(self, stage: str) -> Iterator[dict[str, Any]]:
        require(
            stage in self.stages and self.stages[stage]["state"] == "NOT_RUN", "P4A_STAGE_ORDER"
        )
        row: dict[str, Any] = {"state": "ENTERED"}
        self.stages[stage] = row
        try:
            yield row
        except BaseException as error:
            row.update(state="FAILED", failure=safe_failure(error, stage))
            raise
        else:
            row["state"] = "PASSED"

    def terminal(self, *, cleanup: bool, reaped: bool, owned: bool) -> dict[str, Any]:
        passed = all(self.stages[s]["state"] == "PASSED" for s in self.required)
        passed = passed and cleanup is True and reaped is True and owned is True
        return {
            "contract": CONTRACT,
            "stages": self.stages,
            "result": "PASS" if passed else "FAIL",
            "exit_code": 0 if passed else 1,
            "cleanup_verified": cleanup,
            "reap_verified": reaped,
            "ownership_verified": owned,
        }


@dataclass(frozen=True)
class Deadline:
    expires_at: datetime
    monotonic_end: float
    reserve: int = 180

    @classmethod
    def register(
        cls, expires_at: datetime, *, seconds_cap: int = 1200, reserve: int = 180
    ) -> "Deadline":
        require(expires_at.utcoffset() is not None, "P4A_UTC_REQUIRED")
        remaining = (expires_at - datetime.now(UTC)).total_seconds()
        require(180 <= reserve < remaining <= seconds_cap <= 1800, "P4A_DEADLINE")
        return cls(expires_at, time.monotonic() + remaining, reserve)

    def remaining(self, *, cleanup: bool = False) -> float:
        value = min(
            self.monotonic_end - time.monotonic(),
            (self.expires_at - datetime.now(UTC)).total_seconds(),
        ) - (0 if cleanup else self.reserve)
        require(value > 0, "P4A_DEADLINE")
        return value


class _VerifiedLoader(importlib.abc.Loader):
    def __init__(self, path: Path, body: bytes):
        self.path, self.body = path, body

    def create_module(self, spec: Any) -> None:
        return None

    def exec_module(self, module: ModuleType) -> None:
        exec(compile(self.body, str(self.path), "exec"), module.__dict__)  # noqa: S102


class _VerifiedNamespace(importlib.abc.Loader):
    def create_module(self, spec: Any) -> None:
        return None

    def exec_module(self, module: ModuleType) -> None:
        return None


class SourceBinding(importlib.abc.MetaPathFinder):
    """只为本验收父/子解释器绑定三类本库模块；执行已hash的同一份内存bytes。"""

    def __init__(self, manifest: Mapping[str, Any]):
        self.manifest = manifest
        self.root = Path(manifest["root"])
        self.package = Path(manifest["package_root"])
        require(Path.cwd() == self.root, "P4A_CWD")
        require(Path(sys.executable).absolute() == Path(manifest["python"]), "P4A_INTERPRETER")
        require(
            binary_digest(Path(sys.executable).resolve()) == manifest["python_binary_sha256"],
            "P4A_INTERPRETER",
        )
        require(sys.version_info[:2] == (3, 12), "P4A_PYTHON_VERSION")
        require(sys.flags.isolated == 1 and sys.flags.no_user_site == 1, "P4A_ISOLATION")
        require(not os.environ.get("PYTHONPATH") and not os.environ.get("PYTHONHOME"), "P4A_ENV")
        self.modules: dict[str, tuple[Path, bytes, bool]] = {}
        self.namespaces: dict[str, Path] = {}
        for relative, expected in manifest["files"].items():
            rel = Path(relative)
            require(not rel.is_absolute() and ".." not in rel.parts, "P4A_SOURCE_PATH")
            path = self.root / rel
            if relative.startswith("backend/src/commerceops/"):
                path = self.package / rel.relative_to("backend/src")
                mod = rel.relative_to("backend/src").with_suffix("").parts
            elif rel.parts[0] in ("scripts", "tests") and rel.suffix == ".py":
                mod = rel.with_suffix("").parts
            else:
                bound_bytes(path, expected)
                continue
            package = mod[-1] == "__init__"
            name = ".".join(mod[:-1] if package else mod)
            self.modules[name] = (path, bound_bytes(path, expected), package)
        for name in self.modules:
            parts = name.split(".")
            for number in range(1, len(parts)):
                parent = ".".join(parts[:number])
                if parent not in self.modules:
                    self.namespaces[parent] = self.root.joinpath(*parts[:number])
        self.check_loaded(allow_empty=True)

    def check_loaded(self, *, allow_empty: bool = False) -> None:
        for name, module in tuple(sys.modules.items()):
            if name.split(".")[0] not in PREFIXES or module is None:
                continue
            if name in self.namespaces:
                loader = getattr(getattr(module, "__spec__", None), "loader", None)
                paths = getattr(module, "__path__", ())
                require(
                    isinstance(loader, _VerifiedNamespace)
                    and list(paths) == [str(self.namespaces[name])],
                    "P4A_IMPORT_CACHE",
                )
                continue
            require(name in self.modules, "P4A_IMPORT_UNKNOWN")
            path, body, _ = self.modules[name]
            require(getattr(module, "__file__", None) == str(path), "P4A_IMPORT_ORIGIN")
            loader = getattr(getattr(module, "__spec__", None), "loader", None)
            require(isinstance(loader, _VerifiedLoader), "P4A_IMPORT_CACHE")
            require(cast(_VerifiedLoader, loader).body == body, "P4A_IMPORT_CACHE")
        if not allow_empty:
            require("commerceops" in sys.modules, "P4A_IMPORT_REQUIRED")

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> Any:
        if fullname.split(".")[0] not in PREFIXES:
            return None
        if fullname in self.namespaces:
            spec = importlib.machinery.ModuleSpec(fullname, _VerifiedNamespace(), is_package=True)
            spec.submodule_search_locations = [str(self.namespaces[fullname])]
            return spec
        require(fullname in self.modules, "P4A_IMPORT_UNKNOWN")
        filename, body, package = self.modules[fullname]
        return importlib.util.spec_from_file_location(
            fullname,
            filename,
            loader=_VerifiedLoader(filename, body),
            submodule_search_locations=[str(filename.parent)] if package else None,
        )

    @contextmanager
    def installed(self) -> Iterator["SourceBinding"]:
        sys.meta_path.insert(0, self)
        try:
            yield self
            self.check_loaded()
        finally:
            sys.meta_path.remove(self)


def source_manifest(root: Path, entry: Path, *, package_root: Path | None = None) -> dict[str, Any]:
    """准备阶段生成；调用者冻结本文件sha，再把sha作为外入口必填参数。"""
    files = {
        str(path.relative_to(root)): digest(bound_bytes(path))
        for base in ("backend/src/commerceops", "scripts", "tests")
        for path in sorted((root / base).rglob("*.py"))
    }
    files.update({name: digest(bound_bytes(root / name)) for name in ("uv.lock", "pyproject.toml")})
    for base in ("backend/migrations", "tests/fixtures/commerce/inventory-v1"):
        for path in sorted((root / base).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                files[str(path.relative_to(root))] = digest(bound_bytes(path))
    for path in sorted((root / "tests/e2e/web").glob("m1_acceptance_*.cjs")):
        files[str(path.relative_to(root))] = digest(bound_bytes(path))
    return {
        "contract": CONTRACT,
        "root": str(root),
        "package_root": str(package_root or root / "backend/src"),
        "python": str(Path(sys.executable).absolute()),
        "python_binary_sha256": binary_digest(Path(sys.executable).resolve()),
        "entry": str(entry),
        "entry_sha256": digest(bound_bytes(entry)),
        "files": files,
    }


@dataclass(frozen=True)
class Query:
    id: str
    statement: str
    columns: tuple[tuple[str, int], ...]
    role: Literal["owner", "app"] = "app"
    revisions: tuple[str, ...] = ("0015", "0016")

    def execute(
        self, db: Any, parameters: Sequence[Any] = (), *, revision: str, role: str
    ) -> list[dict[str, Any]]:
        if revision not in self.revisions or role != self.role:
            raise AcceptanceFailure("P4A_QUERY_CONTEXT", query_id=self.id)
        try:
            cursor = db.execute(self.statement, parameters)
            description = tuple((c.name, c.type_code) for c in cursor.description or ())
            if description != self.columns:
                raise AcceptanceFailure("P4A_QUERY_SHAPE", query_id=self.id)
            return list(cursor.fetchall())
        except BaseException as error:
            # SQLSTATE保留在原exception；固定queryID不包含SQL或参数。
            if not isinstance(error, AcceptanceFailure):
                try:
                    error.p4a_query_id = self.id  # type: ignore[attr-defined]
                except AttributeError:
                    pass
            raise


# PostgreSQL固定内建OID；精确返回列/类型在真实app连接核对。
QUERIES = {
    q.id: q
    for q in (
        Query(
            "ROLE",
            "SELECT current_user::text AS role, r.rolsuper, r.rolcreatedb, r.rolcreaterole "
            "FROM pg_roles r WHERE r.rolname=current_user",
            (("role", 25), ("rolsuper", 16), ("rolcreatedb", 16), ("rolcreaterole", 16)),
        ),
        Query(
            "REVISION",
            "SELECT version_num::text AS revision FROM business.alembic_version",
            (("revision", 25),),
            role="owner",
        ),
        Query(
            "TABLES",
            "SELECT table_schema::text AS schema,table_name::text AS name "
            "FROM information_schema.tables WHERE table_schema IN ('business','checkpoints') "
            "AND table_type='BASE TABLE' ORDER BY table_schema,table_name",
            (("schema", 25), ("name", 25)),
            role="owner",
        ),
        Query(
            "COLUMNS",
            "SELECT table_schema::text AS schema,table_name::text AS table_name,"
            "column_name::text AS column_name,udt_name::text AS udt_name,"
            "is_nullable::text AS nullable "
            "FROM information_schema.columns WHERE table_schema IN ('business','checkpoints') "
            "ORDER BY table_schema,table_name,ordinal_position",
            (
                ("schema", 25),
                ("table_name", 25),
                ("column_name", 25),
                ("udt_name", 25),
                ("nullable", 25),
            ),
            role="owner",
        ),
        Query(
            "ITEMS",
            "SELECT id,version,status,quantity::text AS quantity,execution_id "
            "FROM business.replenishment_items WHERE task_id=%s ORDER BY id",
            (
                ("id", 2950),
                ("version", 23),
                ("status", 25),
                ("quantity", 25),
                ("execution_id", 2950),
            ),
        ),
        Query(
            "DELIVERIES",
            "SELECT outbox_id,item_id,version,status,attempts,observed_version,external_id "
            "FROM business.p4_base_deliveries WHERE task_id=%s ORDER BY item_id,version",
            (
                ("outbox_id", 2950),
                ("item_id", 2950),
                ("version", 23),
                ("status", 25),
                ("attempts", 23),
                ("observed_version", 23),
                ("external_id", 25),
            ),
        ),
        Query(
            "SDK_COUNTS",
            "SELECT method,status,http_status,provider_code,count(*) AS n "
            "FROM business.p4_sdk_calls WHERE window_id=%s "
            "GROUP BY method,status,http_status,provider_code ORDER BY method,status",
            (("method", 25), ("status", 25), ("http_status", 23), ("provider_code", 23), ("n", 20)),
        ),
        Query(
            "LINKS",
            "SELECT item_id,external_id,original_outbox_id FROM business.p4_base_links "
            "WHERE item_id=%s",
            (("item_id", 2950), ("external_id", 25), ("original_outbox_id", 2950)),
        ),
        Query(
            "TASKS",
            "SELECT id,state,version FROM business.business_tasks WHERE id=ANY(%s) ORDER BY id",
            (("id", 2950), ("state", 25), ("version", 23)),
        ),
        Query(
            "JOBS",
            "SELECT id,status,attempts FROM business.jobs WHERE task_id=ANY(%s) ORDER BY id",
            (("id", 2950), ("status", 25), ("attempts", 23)),
        ),
        Query(
            "LIFECYCLE",
            "SELECT source,action,entity_id,after_state FROM business.audit_events "
            "WHERE organization_id=%s AND source IN ('worker','feishu_gateway') "
            "ORDER BY occurred_at,id",
            (("source", 25), ("action", 25), ("entity_id", 25), ("after_state", 3802)),
        ),
    )
}


def schema_contract(owner: Any, app: Any, revision: str) -> dict[str, Any]:
    """owner仅元数据并先关闭；所有工具数据query以实际app执行。"""
    from commerceops.infrastructure.database import connect

    require(revision in ("0015", "0016"), "P4A_SCHEMA_REVISION")
    with connect(owner) as db:
        actual_revision = QUERIES["REVISION"].execute(db, revision=revision, role="owner")
        tables = QUERIES["TABLES"].execute(db, revision=revision, role="owner")
        columns = QUERIES["COLUMNS"].execute(db, revision=revision, role="owner")
    expected = {"business." + t for t in BUSINESS_0015}
    expected |= {"checkpoints." + t for t in (*CP_DATA_TABLES, "checkpoint_migrations")}
    if revision == "0016":
        expected.add("business.p4_clarification_requests")
    expected_revision = {"0015": "0015_p4_read_replies", "0016": "0016_p4_clarification_requests"}
    require(actual_revision == [{"revision": expected_revision[revision]}], "P4A_SCHEMA_REVISION")
    require({r["schema"] + "." + r["name"] for r in tables} == expected, "P4A_SCHEMA_TABLES")
    with connect(app) as db:
        role = QUERIES["ROLE"].execute(db, revision=revision, role="app")
        require(
            role
            == [
                {
                    "role": "commerceops_app",
                    "rolsuper": False,
                    "rolcreatedb": False,
                    "rolcreaterole": False,
                }
            ],
            "P4A_ROLE",
        )
        probes = {
            "ITEMS": ("00000000-0000-4000-8000-000000000001",),
            "DELIVERIES": ("00000000-0000-4000-8000-000000000001",),
            "SDK_COUNTS": ("00000000-0000-4000-8000-000000000001",),
            "LINKS": ("00000000-0000-4000-8000-000000000001",),
            "TASKS": ([],),
            "JOBS": ([],),
            "LIFECYCLE": ("00000000-0000-4000-8000-000000000001",),
        }
        for name, parameters in probes.items():
            QUERIES[name].execute(db, parameters, revision=revision, role="app")
    denied = False
    try:
        with connect(app) as db:
            db.execute("SELECT version_num FROM business.alembic_version").fetchall()
    except Exception as error:
        require(getattr(error, "sqlstate", None) == "42501", "P4A_ALEMBIC_DENIAL")
        denied = True
    require(denied, "P4A_APP_METADATA_PERMISSION")
    return {
        "revision": revision,
        "exact_table_count": len(expected),
        "role": role,
        "columns_digest": digest(canonical(columns)),
        "app_queries_verified": list(probes),
        "alembic_read_denied_sqlstate": "42501",
    }


def private_ref(value: Mapping[str, Any]) -> bytes:
    require(set(value) == {"path", "sha256"}, "P4A_REF_SHAPE")
    require(isinstance(value["path"], str) and Path(value["path"]).is_absolute(), "P4A_REF_PATH")
    return bound_bytes(Path(value["path"]), value["sha256"], private=True)


def load_handoff(handoff_ref: Mapping[str, str]) -> dict[str, Any]:
    value: dict[str, Any] = json.loads(private_ref(handoff_ref))
    require(value.get("contract") == CONTRACT, "P4A_CONTRACT")
    return value


def _verified_handoff(value: Mapping[str, Any], ref: Mapping[str, str]) -> None:
    require(load_handoff(ref) == value, "P4A_HANDOFF_CHANGED")


def _runtime(value: Mapping[str, Any]) -> Deadline:
    require(
        type(value["cleanup_reserve_seconds"]) is int and value["cleanup_reserve_seconds"] >= 180,
        "P4A_CLEANUP_RESERVE",
    )
    return Deadline(
        datetime.fromisoformat(value["deadline_utc"]),
        float(value["monotonic_end"]),
        value["cleanup_reserve_seconds"],
    )


def _docker(arguments: list[str], *, timeout: float = 10) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(["docker", *arguments], capture_output=True, timeout=timeout)
    require(result.returncode == 0, "P4A_DOCKER_OPERATION")
    return result


def _verified_runner(handoff: Mapping[str, Any], *, cleanup: bool = False) -> Mapping[str, Any]:
    resource, candidate = handoff["resource"], handoff["candidate"]
    runner = resource["runner"]
    _runtime(resource["runtime"]).remaining(cleanup=cleanup)
    value = json.loads(_docker(["inspect", runner["container_id"]]).stdout)[0]
    require(
        value["Id"] == runner["container_id"] and value["State"]["Running"] is True, "P4A_RUNNER_ID"
    )
    labels = value["Config"]["Labels"]
    require(
        labels.get("p4.acceptance.run") == resource["run_id"]
        and labels.get("p4.acceptance.owner") == resource["owner_label"]
        and labels.get("com.docker.compose.project") == resource["project"],
        "P4A_RUNNER_OWNER",
    )
    require(value["Image"] == candidate["actual_images"]["runner"]["id"], "P4A_RUNNER_IMAGE")
    require(
        any(
            m["Source"] == runner["host_private_dir"]
            and m["Destination"] == runner["container_private_dir"]
            and m["RW"] is True
            for m in value["Mounts"]
        ),
        "P4A_RUNNER_MOUNT",
    )
    pg = json.loads(_docker(["inspect", resource["postgres_container_id"]]).stdout)[0]
    require(
        not pg["HostConfig"]["PortBindings"]
        and pg["Config"]["Labels"].get("p4.acceptance.run") == resource["run_id"]
        and pg["Image"] == candidate["actual_images"]["postgres"]["id"]
        and any(m.get("Name") == resource["volume"] for m in pg["Mounts"]),
        "P4A_PG_RESOURCE",
    )
    return cast(Mapping[str, Any], runner)


def _inside_ref(ref: Mapping[str, str], runner: Mapping[str, Any]) -> dict[str, str]:
    private_ref(ref)
    try:
        relative = Path(ref["path"]).relative_to(Path(runner["host_private_dir"]))
    except ValueError:
        raise AcceptanceFailure("P4A_REF_MOUNT") from None
    require(".." not in relative.parts, "P4A_REF_MOUNT")
    return {"path": str(Path(runner["container_private_dir"]) / relative), "sha256": ref["sha256"]}


@dataclass
class RunnerChild:
    process: subprocess.Popen[bytes]
    output: Path
    ready: Path
    request_file: Path


def _runner_start(handoff: Mapping[str, Any], request: dict[str, Any]) -> RunnerChild:
    import secrets

    runner = _verified_runner(
        handoff, cleanup=request["action"] in ("signal_process", "confirm_process")
    )
    directory = Path(runner["host_private_dir"])
    key = secrets.token_hex(12)
    output, ready, request_file = (
        directory / (prefix + "-" + key + ".json") for prefix in ("result", "ready", "request")
    )
    request.update(
        contract=CONTRACT,
        runtime=runner["runtime"],
        expected_namespace=runner["namespace"],
        output_file=str(Path(runner["container_private_dir"]) / output.name),
        ready_file=str(Path(runner["container_private_dir"]) / ready.name),
    )
    write_private(request_file, request)
    manifest = runner["manifest_ref"]
    inside_manifest = _inside_ref(manifest, runner)
    args = [
        "docker",
        "exec",
        "--workdir",
        "/app",
        "--user",
        f"{runner['uid']}:{runner['gid']}",
        runner["container_id"],
        runner["python"],
        "-I",
        runner["entry"],
        "--manifest",
        inside_manifest["path"],
        "--manifest-sha256",
        manifest["sha256"],
        "--request",
        str(Path(runner["container_private_dir"]) / request_file.name),
        "--request-sha256",
        digest(bound_bytes(request_file, private=True)),
    ]
    child = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return RunnerChild(child, output, ready, request_file)


def _runner_result(
    child: RunnerChild, handoff: Mapping[str, Any], *, cleanup: bool = False
) -> dict[str, Any]:
    timeout = min(30, _runtime(handoff["resource"]["runtime"]).remaining(cleanup=cleanup))
    try:
        child.process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # docker exec CLI的超时不是container child停止证据，交独立cleanup处理。
        child.process.kill()
        child.process.communicate(timeout=5)
        raise AcceptanceFailure("P4A_RUNNER_TIMEOUT") from None
    require(child.output.exists(), "P4A_RUNNER_RESULT")
    result: dict[str, Any] = json.loads(bound_bytes(child.output, private=True))
    require(child.process.returncode == result["exit_code"], "P4A_CHILD_EXIT_DISAGREEMENT")
    if result["exit_code"] != 0:
        failure = result.get("failure", {})
        raise AcceptanceFailure(
            "P4A_CAPTURE_FAILED", query_id=failure.get("query_id"), sqlstate=failure.get("sqlstate")
        )
    return result


def capture_bridge(
    kind: str,
    handoff: Mapping[str, Any],
    *,
    handoff_ref: Mapping[str, str],
    phase: str,
    owner: str | None = None,
    request_key: str | None = None,
    sdk_window_id: str | None = None,
    sdk_subject_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    _verified_handoff(handoff, handoff_ref)
    require(kind in ("snapshot", "worker"), "P4A_CAPTURE_KIND")
    require(kind != "worker" or owner is not None, "P4A_APP_EPOCH_REQUIRED")
    runner = _verified_runner(handoff)
    fixture = handoff["fixture"]
    context = {
        "revision": fixture["schema_revision"],
        "organization_id": fixture["organization_id"],
        "shop_id": fixture["shop_id"],
        "task_id": fixture["task_id"],
        "item_id": fixture["target_item_id"],
        "principal_id": fixture["principal_id"],
        "identity_id": fixture["web_identity_id"],
        "auth_version": fixture["auth_version"],
        "checkpoint_threads": fixture["checkpoint_threads"],
        "request_key": request_key,
        "sdk_window_id": sdk_window_id,
        "sdk_subject_ids": list(sdk_subject_ids),
        "case_kind": fixture["case_kind"],
        "expected_item_count": fixture["item_count"],
        "expected_quantity_total": fixture["quantity_total"],
    }
    request = {
        "action": "capture",
        "kind": kind,
        "phase": phase,
        "owner": owner,
        "capture_context": context,
        "private_refs": {
            "app_database_config": _inside_ref(
                handoff["private_refs"]["app_database_config"], runner
            )
        },
    }
    value = _runner_result(_runner_start(handoff, request), handoff)
    result: dict[str, Any] = value["value"]
    return {**result, "phase": phase}


def capture_stage(request: Mapping[str, Any]) -> dict[str, Any]:
    import importlib

    from commerceops.infrastructure.database import DatabaseSettings, connect

    capture = importlib.import_module("tests.e2e.web.m1_acceptance_capture")
    settings = DatabaseSettings.model_validate_json(
        private_ref(request["private_refs"]["app_database_config"])
    )
    require(
        settings.user == "commerceops_app" and settings.runtime_password_file is None, "P4A_ROLE"
    )
    value = dict(request["capture_context"])
    value["checkpoint_threads"] = tuple(value["checkpoint_threads"])
    value["sdk_subject_ids"] = tuple(value["sdk_subject_ids"])
    context = capture.CaptureContext(**value)
    with connect(settings) as db:
        if request["kind"] == "worker":
            result = capture.capture_worker(db, context.organization_id, request["owner"])
        else:
            result = capture.capture_snapshot(db, context)
    return {"value": result, "exit_code": 0, "stage_result": "COMPLETE", "suite_PASS": False}


def _process_receipt() -> dict[str, Any]:
    import socket

    from commerceops.infrastructure.worker_lock import process_namespace

    fields = Path("/proc/self/stat").read_text().rsplit(") ", 1)[1].split()
    return {
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "pid_namespace": process_namespace(),
        "start_ticks": fields[19],
        "cmdline_sha256": digest(Path("/proc/self/cmdline").read_bytes()),
    }


def _active_workers(db: Any) -> int:
    row = db.execute(
        "SELECT count(*) AS n FROM business.audit_events s "
        "WHERE s.source='worker' AND s.entity_type='worker_runtime' AND s.action='started' "
        "AND NOT EXISTS(SELECT 1 FROM business.audit_events e WHERE e.source='worker' "
        "AND e.entity_type='worker_runtime' AND e.entity_id=s.entity_id "
        "AND e.action='termination_confirmed')"
    ).fetchone()
    if row is None or type(row["n"]) is not int:
        raise AcceptanceFailure("P4A_WORKER_COUNT")
    return int(row["n"])


def app_worker_stage(request: Mapping[str, Any]) -> dict[str, Any]:
    import asyncio
    import signal
    from uuid import UUID

    from commerceops.entrypoints.worker import TechnicalRunner
    from commerceops.infrastructure.database import DatabaseSettings, connect
    from commerceops.infrastructure.worker import Worker
    from commerceops.infrastructure.worker_lock import WorkerSession

    settings = DatabaseSettings.model_validate_json(
        private_ref(request["private_refs"]["app_database_config"])
    )
    require(
        settings.user == "commerceops_app" and settings.runtime_password_file is None, "P4A_ROLE"
    )
    organization, task = UUID(request["organization_id"]), UUID(request["task_id"])

    async def serve() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for signum in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(signum, stop.set)
        timer = loop.call_later(_runtime(request["runtime"]).remaining(), stop.set)
        session = WorkerSession(settings, organization)
        await session.start()
        running = False
        try:
            with connect(settings) as db:
                start = db.execute(
                    "SELECT id FROM business.audit_events WHERE source='worker' "
                    "AND action='started' AND entity_id=%s",
                    (session.owner,),
                ).fetchall()
                active = _active_workers(db)
            require(len(start) == 1, "P4A_WORKER_STARTED")
            require(active == 1, "P4A_WORKER_COUNT")
            write_private(
                Path(request["ready_file"]),
                {
                    "epoch": "app",
                    "organization": str(organization),
                    "owner": session.owner,
                    "process_started_id": str(start[0]["id"]),
                    "active_workers": active,
                    "reaped": False,
                    **_process_receipt(),
                },
            )
            running = True
            await Worker(
                session, TechnicalRunner(), dispatch_jobs=False, task_ids=frozenset({task})
            ).run(stop)
        finally:
            timer.cancel()
            if not running:
                await session.close(clean=True)

    asyncio.run(serve())
    return {"exit_code": 0, "stage_result": "COMPLETE", "suite_PASS": False}


def api_stage(request: Mapping[str, Any]) -> dict[str, Any]:
    import asyncio

    import uvicorn
    from commerceops.entrypoints.api import create_app
    from commerceops.infrastructure.replenishment_repository import ReplenishmentStore
    from commerceops.infrastructure.web_config import WebConfig

    ref = request["private_refs"]["web_config"]
    private_ref(ref)
    config = WebConfig.from_file(Path(ref["path"]))
    require(config.database.user == "commerceops_app", "P4A_ROLE")
    app = create_app(
        web_config=config,
        replenishment_store=ReplenishmentStore(
            config, Path("tests/fixtures/commerce/inventory-v1")
        ),
    )

    class ObservedServer(uvicorn.Server):
        async def startup(self, sockets: Any = None) -> None:
            await super().startup(sockets)
            require(self.started, "P4A_API_START")
            write_private(Path(request["ready_file"]), {"api_ready": True, **_process_receipt()})

    port = request["api_port"]
    require(type(port) is int and 1024 <= port <= 65535, "P4A_API_PORT")
    server = ObservedServer(
        uvicorn.Config(app, host="0.0.0.0", port=port, access_log=False, log_level="critical")  # noqa: S104
    )

    async def serve() -> None:
        def stop() -> None:
            server.should_exit = True

        timer = asyncio.get_running_loop().call_later(
            _runtime(request["runtime"]).remaining(), stop
        )
        try:
            await server.serve()
        finally:
            timer.cancel()

    asyncio.run(serve())
    return {"exit_code": 0, "stage_result": "COMPLETE", "suite_PASS": False}


def process_control_stage(request: Mapping[str, Any]) -> dict[str, Any]:
    import asyncio
    import signal
    from uuid import UUID

    from commerceops.entrypoints.feishu_business import confirm_worker_child
    from commerceops.infrastructure.database import DatabaseSettings, connect
    from commerceops.infrastructure.web_config import WebConfig

    receipt = json.loads(private_ref(request["receipt_ref"]))
    pid = receipt["pid"]
    require(type(pid) is int and pid > 1 and pid != os.getpid(), "P4A_PROCESS_PID")
    if request["action"] == "signal_process":
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
        require(
            fields[19] == receipt["start_ticks"]
            and digest(Path(f"/proc/{pid}/cmdline").read_bytes()) == receipt["cmdline_sha256"],
            "P4A_PROCESS_REUSED",
        )
        os.kill(pid, signal.SIGTERM)
        return {"exit_code": 0, "stage_result": "COMPLETE", "suite_PASS": False}
    settings = DatabaseSettings.model_validate_json(
        private_ref(request["private_refs"]["app_database_config"])
    )
    require(
        settings.user == "commerceops_app" and settings.runtime_password_file is None, "P4A_ROLE"
    )
    # 原确认器只需WebConfig.database；新合成Web配置提供其余原字段，不伪造config类。
    web_ref = request["private_refs"]["web_config"]
    private_ref(web_ref)
    web = WebConfig.from_file(Path(web_ref["path"]))
    require(web.database == settings, "P4A_CONFIG_BINDING")
    asyncio.run(confirm_worker_child(web, UUID(receipt["organization"]), pid))
    with connect(settings) as db:
        end = db.execute(
            "SELECT id FROM business.audit_events WHERE source='worker' "
            "AND action='termination_confirmed' AND entity_id=%s",
            (receipt["owner"],),
        ).fetchall()
        active = _active_workers(db)
    require(len(end) == 1, "P4A_WORKER_TERMINATION")
    return {
        "exit_code": 0,
        "stage_result": "COMPLETE",
        "suite_PASS": False,
        "termination_id": str(end[0]["id"]),
        "active_workers": active,
    }


_APP_EPOCHS: dict[str, dict[str, Any]] = {}


def app_lifecycle(
    action: str, handoff: Mapping[str, Any], *, handoff_ref: Mapping[str, str]
) -> dict[str, Any]:
    _verified_handoff(handoff, handoff_ref)
    require(action in ("start", "stop", "restart"), "P4A_APP_ACTION")
    runner = _verified_runner(handoff, cleanup=action == "stop")
    run_id = handoff["resource"]["run_id"]
    refs = {
        name: _inside_ref(handoff["private_refs"][name], runner)
        for name in ("web_config", "app_database_config")
    }
    stopped: dict[str, Any] | None = None
    if action in ("stop", "restart"):
        require(run_id in _APP_EPOCHS, "P4A_APP_EPOCH_REQUIRED")
        old = _APP_EPOCHS[run_id]
        errors = []
        for name in ("worker", "api"):
            if name not in old:
                continue
            child: RunnerChild = old[name]
            try:
                receipt_ref = {
                    "path": str(child.ready),
                    "sha256": digest(bound_bytes(child.ready, private=True)),
                }
                if child.process.poll() is None:
                    control = {
                        "action": "signal_process",
                        "receipt_ref": _inside_ref(receipt_ref, runner),
                    }
                    _runner_result(_runner_start(handoff, control), handoff, cleanup=True)
                _runner_result(child, handoff, cleanup=True)
                if name == "worker":
                    confirmation = _runner_result(
                        _runner_start(
                            handoff,
                            {
                                "action": "confirm_process",
                                "receipt_ref": _inside_ref(receipt_ref, runner),
                                "private_refs": refs,
                            },
                        ),
                        handoff,
                        cleanup=True,
                    )
                    require(confirmation["active_workers"] == 0, "P4A_WORKER_COUNT")
                    stopped = {
                        **old["epoch"],
                        "termination_id": confirmation["termination_id"],
                        "reaped": True,
                    }
            except Exception as error:
                errors.append({"component": name, "failure": safe_failure(error, "STOP")})
        if errors:
            write_private(Path(runner["host_private_dir"]) / "app-stop-failures.safe.json", errors)
            raise AcceptanceFailure("P4A_APP_STOP_FAILED")
        del _APP_EPOCHS[run_id]
    if action in ("start", "restart"):
        require(run_id not in _APP_EPOCHS, "P4A_APP_ALREADY_ACTIVE")
        children: dict[str, Any] = {}
        _APP_EPOCHS[run_id] = children  # 部分启动失败时保留句柄供finally cleanup，不丢活进程。
        for name, request in (
            (
                "api",
                {
                    "action": "api",
                    "api_port": handoff["web"]["api_internal_port"],
                    "private_refs": refs,
                },
            ),
            (
                "worker",
                {
                    "action": "app_worker",
                    "private_refs": refs,
                    "organization_id": handoff["fixture"]["organization_id"],
                    "task_id": handoff["fixture"]["task_id"],
                },
            ),
        ):
            child = _runner_start(handoff, request)
            children[name] = child
            end = time.monotonic() + min(25, _runtime(handoff["resource"]["runtime"]).remaining())
            while not child.ready.exists():
                require(child.process.poll() is None and time.monotonic() < end, "P4A_APP_READY")
                time.sleep(0.05)
        epoch = json.loads(bound_bytes(children["worker"].ready, private=True))
        api = json.loads(bound_bytes(children["api"].ready, private=True))
        require(api["api_ready"] is True and epoch["active_workers"] == 1, "P4A_APP_READY")
        require(
            all(children[name].process.poll() is None for name in ("api", "worker")),
            "P4A_APP_EXITED",
        )
        children["epoch"] = epoch
        return {
            "epoch": epoch,
            "active_workers": epoch["active_workers"],
            "reaped": stopped is not None,
            "api_ready": api["api_ready"],
            "volume": handoff["resource"]["volume"],
            "container_ids": handoff["resource"]["container_ids"],
            "stopped_epoch": stopped,
            "restart_scope": "native API and single Worker processes; same runner and PG volume",
        }
    require(stopped is not None, "P4A_APP_STOP_EVIDENCE")
    return {
        "epoch": stopped,
        "active_workers": 0,
        "reaped": True,
        "api_ready": False,
        "volume": handoff["resource"]["volume"],
        "container_ids": handoff["resource"]["container_ids"],
    }


def worker_stage(request: Mapping[str, Any]) -> dict[str, Any]:
    """原controlled_work完整调用；观测包装只记录，不替换业务判断或返回结果。"""
    import asyncio

    from commerceops.adapters.feishu.business_config import BusinessSettings
    from commerceops.application.feishu_business.worker_window import ControlledWorkerWindow
    from commerceops.entrypoints import feishu_worker_child as native
    from commerceops.infrastructure.database import connect
    from commerceops.infrastructure.web_config import WebConfig

    from tests.p4_demo_factory import M1DemoFactory

    native_module: Any = native
    refs = request["private_refs"]
    settings = BusinessSettings.model_validate_json(private_ref(refs["business"]))
    window = ControlledWorkerWindow.model_validate_json(private_ref(refs["window"]))
    private_ref(refs["web_config"])
    config = WebConfig.from_file(Path(refs["web_config"]["path"]))
    require(settings.web_config_file == Path(refs["web_config"]["path"]), "P4A_CONFIG_BINDING")
    report = StageReport(("ROLE", "AUTHORIZE", "PREFLIGHT", "CALL", "PERSIST", "STOP"))
    with report.enter("ROLE"):
        with connect(config.database) as db:
            role = QUERIES["ROLE"].execute(db, revision="0016", role="app")
        require(
            role
            == [
                {
                    "role": "commerceops_app",
                    "rolsuper": False,
                    "rolcreatedb": False,
                    "rolcreaterole": False,
                }
            ],
            "P4A_ROLE",
        )
    witnesses: list[dict[str, Any]] = []
    original_scope, original_target = native.trusted_scope, native_module.verified_target
    original_project = native_module.BusinessBaseAdapter.project

    async def observed_scope(*args: Any, **kwargs: Any) -> Any:
        with report.enter("AUTHORIZE"):
            return await original_scope(*args, **kwargs)

    async def observed_target(*args: Any, **kwargs: Any) -> Any:
        with report.enter("PREFLIGHT"):
            return await original_target(*args, **kwargs)

    async def observed_project(adapter: Any, value: Any) -> Any:
        # 同窗口可能包含多投影，CALL状态只在完整native返回后汇总。
        row = report.stages["CALL"]
        require(row["state"] != "FAILED", "P4A_CALL_AFTER_FAILURE")
        row["state"] = "ENTERED"
        try:
            result = await original_project(adapter, value)
            witnesses.append(
                {"request": value.model_dump(mode="json"), "result": result.model_dump(mode="json")}
            )
            row.update(state="PASSED", calls=len(witnesses))
            return result
        except BaseException as error:
            row.update(state="FAILED", failure=safe_failure(error, "CALL"))
            raise

    native_module.trusted_scope, native_module.verified_target = observed_scope, observed_target
    native_module.BusinessBaseAdapter.project = observed_project
    transport: Any = None
    summary: dict[str, Any] = {}
    try:
        if request["transport"] == "fake":
            from tests.p4_acceptance_support import FakeHTTPTransport

            private_ref(refs["external_records"])
            transport = FakeHTTPTransport(Path(refs["external_records"]["path"]), settings)
            with transport.installed():
                summary = asyncio.run(
                    native.controlled_work(
                        settings,
                        window,
                        config,
                        M1DemoFactory(),
                    )
                )
        else:
            require(request.get("root_real_release") is True, "P4A_REAL_PLATFORM_HOLD")
            require(request["action"] == "worker" and window.recovery is not None, "P4A_REAL_SCOPE")
            summary = asyncio.run(
                native.controlled_work(
                    settings,
                    window,
                    config,
                    M1DemoFactory(),
                )
            )
    finally:
        native_module.trusted_scope, native_module.verified_target = original_scope, original_target
        native_module.BusinessBaseAdapter.project = original_project
    proof: dict[str, Any] = {}
    try:
        with report.enter("PERSIST"):
            with connect(config.database) as db:
                deliveries = QUERIES["DELIVERIES"].execute(
                    db, (next(iter(window.task_ids)),), revision="0016", role="app"
                )
                calls = QUERIES["SDK_COUNTS"].execute(
                    db, (window.window_id,), revision="0016", role="app"
                )
            proof.update(deliveries=deliveries, method_counts=calls)
            require(
                bool(witnesses) and all(w["result"]["outcome"] == "verified" for w in witnesses),
                "P4A_READBACK_UNVERIFIED",
            )
            require(not summary.get("failure_category"), "P4A_NATIVE_FAILED")
    except Exception:
        proof["persist_stage_failed"] = True  # 固定FAILED仍继续独立STOP查询，子进程非零。
    try:
        with report.enter("STOP"):
            with connect(config.database) as db:
                lifecycle = QUERIES["LIFECYCLE"].execute(
                    db, (window.organization_id,), revision="0016", role="app"
                )
            starts = [
                r
                for r in lifecycle
                if r["source"] == "worker"
                and r["action"] == "started"
                and r["after_state"].get("pid") == os.getpid()
            ]
            require(len(starts) == 1, "P4A_WORKER_STARTED")
            stopped = [
                r
                for r in lifecycle
                if r["source"] == "worker"
                and r["entity_id"] == starts[0]["entity_id"]
                and r["action"] == "stopped"
            ]
            require(len(stopped) == 1, "P4A_WORKER_STOPPED")
            proof["worker_owner"] = starts[0]["entity_id"]
    except Exception:
        proof["stop_stage_failed"] = True
    passed = all(s["state"] == "PASSED" for s in report.stages.values())
    return {
        "contract": CONTRACT,
        "stage_result": "COMPLETE" if passed else "FAILED",
        "exit_code": 0 if passed else 1,
        "stages": report.stages,
        "native_summary": summary,
        "witnesses": witnesses,
        "pg_proof": proof,
        "counts": {
            "native_factory_invocations": int(report.stages["PREFLIGHT"]["state"] != "NOT_RUN"),
            "official_sdk_objects_constructed": int(
                report.stages["PREFLIGHT"]["state"] != "NOT_RUN"
            ),
            "fake_transport_calls": 0 if transport is None else transport.calls,
            "real_network_egress": 0 if transport is not None else "not_measured",
            "original_secret_read": 0 if transport is not None else "Root_release_only",
            "provider_call": 0,
        },
        "child_reaped": False,
        "suite_PASS": False,
    }


def gateway_stage(request: Mapping[str, Any]) -> dict[str, Any]:
    """无WS/认证：本轮合成gateway的原claim/process_started及有界OS进程。"""
    import signal

    from commerceops.adapters.feishu.business_config import BusinessSettings
    from commerceops.application.feishu_business.gateway_window import GatewayWindow
    from commerceops.infrastructure.database import connect
    from commerceops.infrastructure.feishu_gateway_window import (
        claim_gateway,
        gateway_process_started,
    )
    from commerceops.infrastructure.web_config import WebConfig

    require(request["transport"] == "fake", "P4A_REAL_PLATFORM_HOLD")
    refs = request["private_refs"]
    settings = BusinessSettings.model_validate_json(private_ref(refs["business"]))
    window = GatewayWindow.model_validate_json(private_ref(refs["window"]))
    private_ref(refs["web_config"])
    config = WebConfig.from_file(Path(refs["web_config"]["path"]))
    with connect(config.database) as db:
        claim_gateway(db, settings, window)
        gateway_process_started(db, window)
    stopped = False

    def stop(signum: int, frame: Any) -> None:
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, stop)
    write_private(Path(request["ready_file"]), {"claimed": True, "pid": os.getpid()})
    while not stopped and window.active():
        time.sleep(0.05)
    return {"stage_result": "COMPLETE", "exit_code": 0, "suite_PASS": False}


def outer_request(request: Mapping[str, Any], binding: SourceBinding) -> int:
    require(request.get("contract") == CONTRACT, "P4A_CONTRACT")
    if request.get("action") == "source_probe":
        import commerceops

        require(commerceops.__file__ is not None, "P4A_IMPORT_REQUIRED")
        binding.check_loaded()
        return 0
    action = request.get("action")
    require(
        action
        in (
            "worker",
            "gateway",
            "capture",
            "api",
            "app_worker",
            "signal_process",
            "confirm_process",
        ),
        "P4A_ACTION",
    )
    lease = _runtime(request["runtime"])
    lease.remaining(cleanup=action in ("signal_process", "confirm_process"))
    from commerceops.infrastructure.worker_lock import process_namespace

    if "expected_namespace" in request:
        require(process_namespace() == request["expected_namespace"], "P4A_RUNNER_NAMESPACE")
    if action in ("worker", "gateway"):
        require(request.get("transport") in ("fake", "real"), "P4A_TRANSPORT")
        require(
            request.get("transport") == "fake" or request.get("root_real_release") is True,
            "P4A_REAL_PLATFORM_HOLD",
        )
    try:
        if action == "worker":
            result = worker_stage(request)
        elif action == "gateway":
            result = gateway_stage(request)
        elif action == "capture":
            result = capture_stage(request)
        elif action == "api":
            result = api_stage(request)
        elif action == "app_worker":
            result = app_worker_stage(request)
        else:
            result = process_control_stage(request)
    except Exception as error:
        result = {
            "stage_result": "FAILED",
            "exit_code": 1,
            "failure": safe_failure(
                error,
                "COLLECT"
                if action == "capture"
                else "STOP"
                if action in ("signal_process", "confirm_process")
                else "PREPARE",
            ),
            "suite_PASS": False,
        }
    binding.check_loaded()
    write_private(Path(request["output_file"]), result)
    return int(result["exit_code"])


# 此固定小入口仅materialize为本轮受保护私有文件；没有第二public CLI。
OUTER_ENTRY = '''"""P4 purpose-specific acceptance outer entry; isolated and hash-bound."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys

def read(path, expected):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 16777216:
            raise RuntimeError("P4A_BOOTSTRAP")
        body = stream.read(16777217)
        if hashlib.sha256(body).hexdigest() != expected:
            raise RuntimeError("P4A_BOOTSTRAP")
        return body

def main():
    parser = argparse.ArgumentParser()
    for name in ("manifest", "manifest-sha256", "request", "request-sha256"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    try:
        manifest = json.loads(read(args.manifest, args.manifest_sha256))
        if Path(manifest["entry"]) != Path(__file__).absolute():
            raise RuntimeError("P4A_BOOTSTRAP")
        read(Path(__file__), manifest["entry_sha256"])
        helper = Path(manifest["root"]) / "scripts/p4_acceptance.py"
        body = read(helper, manifest["files"]["scripts/p4_acceptance.py"])
        spec = importlib.util.spec_from_file_location("_p4_acceptance_bound", helper)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        exec(compile(body, str(helper), "exec"), module.__dict__)
        binding = module.SourceBinding(manifest)
        request_body = module.bound_bytes(Path(args.request), args.request_sha256, private=True)
        request = json.loads(request_body)
        with binding.installed():
            from scripts.p4_acceptance import outer_request
            code = outer_request(request, binding)
        return code
    except Exception:
        print(json.dumps({"stage_result":"FAILED", "stage":"SOURCE",
                          "code":"P4A_BOOTSTRAP", "exit_code":1}))
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
'''


def materialize_entry(directory: Path) -> Path:
    path = directory / "run_once.py"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(OUTER_ENTRY.encode())
    return path
