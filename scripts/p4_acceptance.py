"""P4专用验收的来源、阶段、SQL和结果合同；没有CLI或真实平台默认入口。"""

import ast
import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import io
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
from datetime import UTC, datetime, timedelta
from importlib.resources.abc import ResourceReader
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
    "MATRIX",
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
        error = AcceptanceFailure(code)
        if code in ("P4A_ROLE", "P4A_BOOTSTRAP_ROLE"):
            mark_stage(error, "ROLE")
        raise error


def failure_stage(error: BaseException, fallback: str) -> str:
    value = getattr(error, "p4a_stage", None)
    return value if isinstance(value, str) and value in STAGES else fallback


def mark_stage(error: BaseException, stage: str) -> None:
    require(stage in STAGES, "P4A_STAGE_UNKNOWN")
    if getattr(error, "p4a_stage", None) not in STAGES:
        cast(Any, error).p4a_stage = stage


@contextmanager
def stage_boundary(stage: str) -> Iterator[None]:
    try:
        yield
    except BaseException as error:
        mark_stage(error, stage)
        raise


def safe_child_detail(value: Any, fallback: str) -> dict[str, Any]:
    """只重建既有child诊断合同；不复制未知键或递归异常数据。"""
    from tests.e2e.web.m1_acceptance_driver import safe_dto_errors

    detail = value if isinstance(value, dict) else {}

    def fixed(name: str, pattern: str, default: Any = None) -> Any:
        item = detail.get(name)
        return item if isinstance(item, str) and re.fullmatch(pattern, item) else default

    stage = detail.get("stage")
    result = dict(
        stage=stage if isinstance(stage, str) and stage in STAGES else fallback,
        code=fixed("code", r"[A-Z][A-Z0-9_]{0,79}", "P4A_INTERNAL"),
        category=fixed("category", r"[A-Za-z][A-Za-z0-9_]{0,63}", "ChildFailure"),
        query_id=fixed("query_id", r"(?:[A-Z][A-Z0-9_]{0,79}|AQ-[0-9a-f]{16})"),
        sqlstate=fixed("sqlstate", r"[A-Z0-9]{5}"),
    )
    for key in ("dto", "dto_errors"):
        if key in detail:
            result[key] = safe_dto_errors(detail[key])
    return result


def raise_child_failure(result: Mapping[str, Any], fallback: str) -> None:
    detail = result.get("failure")
    if not isinstance(detail, dict):
        detail = next(
            (
                r.get("failure", {})
                for r in result.get("stages", {}).values()
                if r.get("state") == "FAILED"
            ),
            {},
        )
    raw_detail = detail if isinstance(detail, dict) else {}
    detail = safe_child_detail(detail, fallback)
    code = detail["code"]
    error = AcceptanceFailure(
        code, query_id=detail.get("query_id"), sqlstate=detail.get("sqlstate")
    )
    # C的固定安全码不带P4A前缀；已校验闭合字符集，不将其降为INTERNAL。
    error.code = code
    error.p4a_category = detail["category"]  # type: ignore[attr-defined]
    for key in ("dto", "dto_errors"):
        if key in detail:
            setattr(error, "p4a_" + key, detail[key])
    if isinstance(raw_detail.get("cleanup_failure"), dict):
        error.p4a_cleanup_failure = safe_child_detail(  # type: ignore[attr-defined]
            raw_detail["cleanup_failure"], "STOP"
        )
    mark_stage(error, detail["stage"])
    raise error


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


def exception_query_id(error: BaseException) -> str | None:
    trace = error.__traceback__
    frames = []
    while trace is not None:
        frames.append(trace)
        trace = trace.tb_next
    for frame in reversed(frames):
        module = frame.tb_frame.f_globals.get("__name__", "")
        if not module.startswith(("commerceops.", "scripts.")):
            continue
        path = Path(frame.tb_frame.f_code.co_filename)
        try:
            tree = ast.parse(bound_bytes(path))
        except (AcceptanceFailure, SyntaxError):
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("execute", "executemany")
                and node.args
                and node.lineno <= frame.tb_lineno <= (node.end_lineno or node.lineno)
            ):
                source = module + ":" + frame.tb_frame.f_code.co_name + ":" + ast.dump(node.args[0])
                return "AQ-" + digest(source.encode())[:16]
    return None


def safe_failure(error: BaseException, stage: str, query_id: str | None = None) -> dict[str, Any]:
    stage = failure_stage(error, stage)
    require(stage in STAGES, "P4A_STAGE_UNKNOWN")
    state = getattr(error, "sqlstate", None)
    result: dict[str, Any] = {
        "stage": stage,
        "code": error.code if isinstance(error, AcceptanceFailure) else "P4A_OPERATION_FAILED",
        "category": type(error).__name__,
        "query_id": query_id
        or getattr(error, "p4a_query_id", None)
        or (error.query_id if isinstance(error, AcceptanceFailure) else None)
        or exception_query_id(error),
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
    cleanup_failure = getattr(error, "p4a_cleanup_failure", None)
    if isinstance(cleanup_failure, dict):
        result["cleanup_failure"] = safe_child_detail(cleanup_failure, "STOP")
    category = getattr(error, "p4a_category", None)
    if isinstance(category, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", category):
        result["category"] = category
    from tests.e2e.web.m1_acceptance_driver import safe_dto_errors

    for key in ("dto", "dto_errors"):
        value = getattr(error, "p4a_" + key, None)
        if value is not None:
            result[key] = safe_dto_errors(value)
    if type(error).__module__ == "tests.e2e.web.m1_acceptance_capture":
        value = error.safe()  # type: ignore[attr-defined]
        if isinstance(value, dict):
            result.update({k: value[k] for k in ("code", "query_id", "sqlstate")})
    if type(error).__module__ == "tests.e2e.web.m1_acceptance_driver":
        from tests.e2e.web.m1_acceptance_driver import safe_failure as consumer_failure

        value = consumer_failure(cast(Exception, error), stage)
        result.update({k: value[k] for k in ("code", "query_id", "sqlstate", "dto")})
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
            mark_stage(error, stage)
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


class _VerifiedResources(ResourceReader):
    """原importlib.resources接口读取启动时已校验的同一份资源bytes。"""

    def __init__(self, resources: Mapping[str, bytes]):
        self.resources = resources

    def open_resource(self, resource: str) -> io.BytesIO:
        if resource not in self.resources:
            raise FileNotFoundError("P4A_RESOURCE_UNKNOWN")
        return io.BytesIO(self.resources[resource])

    def resource_path(self, resource: str) -> str:
        raise FileNotFoundError("P4A_RESOURCE_MEMORY_ONLY")

    def is_resource(self, name: str) -> bool:
        return name in self.resources

    def contents(self) -> Iterator[str]:
        return iter(self.resources)


class _VerifiedLoader(importlib.abc.Loader):
    def __init__(self, path: Path, body: bytes, resources: Mapping[str, bytes]):
        self.path, self.body, self.resources = path, body, resources

    def get_resource_reader(self, fullname: str) -> _VerifiedResources:
        return _VerifiedResources(self.resources)

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
        self.resources: dict[str, dict[str, bytes]] = {}
        for relative, expected in manifest["files"].items():
            rel = Path(relative)
            require(not rel.is_absolute() and ".." not in rel.parts, "P4A_SOURCE_PATH")
            path = self.root / rel
            if relative.startswith("backend/src/commerceops/"):
                path = self.package / rel.relative_to("backend/src")
                if rel.suffix != ".py":
                    parent = ".".join(rel.relative_to("backend/src").parent.parts)
                    self.resources.setdefault(parent, {})[rel.name] = bound_bytes(path, expected)
                    continue
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
            loader=_VerifiedLoader(filename, body, self.resources.get(fullname, {})),
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
    for base in (
        "backend/migrations",
        "backend/src/commerceops/assets",
        "tests/fixtures/commerce/inventory-v1",
    ):
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


_APP_OWNERS: dict[tuple[str, str], dict[str, str]] = {}


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
    host_manifest = json.loads(
        bound_bytes(Path(candidate["manifest_file"]), candidate["manifest_sha256"], private=True)
    )
    runner_manifest = json.loads(private_ref(runner["manifest_ref"]))
    require(
        host_manifest["files"] == runner_manifest["files"]
        and host_manifest["entry_sha256"] == runner_manifest["entry_sha256"]
        and host_manifest["candidate"]
        == runner_manifest["candidate"]
        == {"source_sha": candidate["source_sha"], "tree": candidate["tree"]},
        "P4A_CONTEXT_SOURCE_MISMATCH",
    )
    if not cleanup:
        verify_full_resources(handoff)
    return cast(Mapping[str, Any], runner)


def verify_full_resources(handoff: Mapping[str, Any]) -> None:
    """外入口核冻结的env/mount/network/command闭包，不接受额外原资产挂载。"""
    resource, candidate = handoff["resource"], handoff["candidate"]
    registration = json.loads(private_ref(resource["registration_ref"]))
    require(
        registration["run_id"] == resource["run_id"]
        and registration["project"] == resource["project"]
        and registration["volume"] == resource["volume"]
        and registration["deadline_utc"] == resource["deadline_utc"]
        and registration["cleanup_reserve_seconds"] == resource["cleanup_reserve_seconds"]
        and registration["PG_published_ports"] is False,
        "P4A_REGISTRATION_BINDING",
    )
    require(registration["databases"] == resource["databases"], "P4A_DATABASE_PLAN")
    require(set(resource["container_ids"]) == {"postgres", "runner", "web"}, "P4A_RESOURCE_SET")
    for name, cid in resource["container_ids"].items():
        actual = json.loads(_docker(["inspect", cid]).stdout)[0]
        expected = resource["constraints"][name]
        labels = actual["Config"]["Labels"]
        require(
            actual["Id"] == cid
            and actual["State"]["Running"] is True
            and actual["Image"] == candidate["actual_images"][name]["id"]
            and labels.get("p4.acceptance.run") == resource["run_id"]
            and labels.get("p4.acceptance.owner") == resource["owner_label"]
            and labels.get("com.docker.compose.project") == resource["project"],
            "P4A_RESOURCE_OWNER",
        )
        image = candidate["actual_images"][name]
        if name != "postgres":
            require(
                image["source_sha"] == candidate["source_sha"]
                and image["source_tree"] == candidate["tree"],
                "P4A_IMAGE_SOURCE_BINDING",
            )
        mounts = sorted(
            (m["Type"], m["Source"], m["Destination"], m["RW"]) for m in actual["Mounts"]
        )
        require(
            mounts == sorted(tuple(m) for m in expected["mounts"])
            and sorted(actual["Config"]["Env"]) == sorted(expected["environment"])
            and actual["Config"]["Cmd"] == expected["command"]
            and actual["Config"]["Entrypoint"] == expected["entrypoint"]
            and actual["Config"]["User"] == expected["user"]
            and actual["HostConfig"]["Privileged"] is False
            and not actual["HostConfig"]["CapAdd"],
            "P4A_RESOURCE_ALLOWLIST",
        )
        networks = actual["NetworkSettings"]["Networks"]
        require(
            len(networks) == 1
            and next(iter(networks.values()))["NetworkID"] == resource["network_id"],
            "P4A_RESOURCE_NETWORK",
        )
        ports = actual["HostConfig"]["PortBindings"] or {}
        require(ports == expected["published_ports"], "P4A_RESOURCE_PORTS")
        require(
            not ports
            if name == "postgres"
            else all(p["HostIp"] == "127.0.0.1" for entries in ports.values() for p in entries),
            "P4A_RESOURCE_PORTS",
        )
        if name == "postgres":
            require(actual["State"]["Health"]["Status"] == "healthy", "P4A_PG_HEALTH")


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

    cleanup = request["action"] in (
        "signal_process",
        "confirm_process",
        "process_probe",
        "database_inventory",
    ) or (request["action"] == "capture" and request.get("kind") == "worker")
    runner = _verified_runner(handoff, cleanup=cleanup)
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
        "/usr/bin/env",
        "-i",
        "PATH=/app/.venv/bin:/usr/local/bin:/usr/bin:/bin",
        "HOME=" + runner["container_private_dir"],
        "TMPDIR=" + runner["container_private_dir"],
        "LANG=C.UTF-8",
        "LANGSMITH_TRACING=false",
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
    child: RunnerChild,
    handoff: Mapping[str, Any],
    *,
    cleanup: bool = False,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    require(0 < timeout_seconds <= 300, "P4A_COMMAND_CAP")
    timeout = min(
        timeout_seconds, _runtime(handoff["resource"]["runtime"]).remaining(cleanup=cleanup)
    )
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
        raise_child_failure(result, "COLLECT")
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
    owner_ref = None
    if kind == "worker":
        require(
            isinstance(owner, str) and (handoff["resource"]["run_id"], owner) in _APP_OWNERS,
            "P4A_APP_OWNER_UNBOUND",
        )
        owner_ref = _APP_OWNERS[(handoff["resource"]["run_id"], str(owner))]
        receipt = json.loads(private_ref(owner_ref))
        require(
            receipt["owner"] == owner
            and receipt["organization"] == handoff["fixture"]["organization_id"],
            "P4A_APP_OWNER_UNBOUND",
        )
    runner = _verified_runner(handoff, cleanup=kind == "worker")
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
    if owner_ref is not None:
        request["owner_receipt_ref"] = _inside_ref(owner_ref, runner)
    value = _runner_result(_runner_start(handoff, request), handoff, cleanup=kind == "worker")
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
    if request["kind"] == "worker":
        from commerceops.infrastructure.worker_lock import process_namespace

        receipt = json.loads(private_ref(request["owner_receipt_ref"]))
        require(
            receipt["owner"] == request["owner"]
            and receipt["organization"] == context.organization_id
            and receipt["pid_namespace"] == process_namespace(),
            "P4A_APP_OWNER_UNBOUND",
        )
    with connect(settings) as db:
        if request.get("fault_probe") == "call_signature":
            with stage_boundary("CALL"):
                callback: Any = capture.capture_snapshot
                callback(db)  # 实际版本化callee拒绝缺必需context，不伪造返回或业务状态。
        if request["kind"] == "worker":
            result = capture.capture_worker(db, context.organization_id, request["owner"])
        else:
            result = capture.capture_snapshot(db, context)
    return {"value": result, "exit_code": 0, "stage_result": "COMPLETE", "suite_PASS": False}


def _process_identity(pid: int) -> dict[str, str]:
    """实际OS启动标识；host用ps，不把PID存在本身当作同一进程。"""
    require(type(pid) is int and pid > 1, "P4A_PROCESS_PID")
    if sys.platform == "linux":
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
        return {
            "start_ticks": fields[19],
            "cmdline_sha256": digest(Path(f"/proc/{pid}/cmdline").read_bytes()),
        }
    require(sys.platform == "darwin", "P4A_PROCESS_PLATFORM")
    row = subprocess.run(
        ["/bin/ps", "-ww", "-p", str(pid), "-o", "lstart=", "-o", "command="],
        capture_output=True,
        check=True,
        timeout=5,
    ).stdout.strip()
    require(bool(row), "P4A_PROCESS_ABSENT")
    return {"host_start_command_sha256": digest(row)}


def _process_receipt() -> dict[str, Any]:
    import socket

    from commerceops.infrastructure.worker_lock import process_namespace

    return {
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "pid_namespace": process_namespace(),
        **_process_identity(os.getpid()),
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
        original_close = session.close

        async def observed_close(*args: Any, **kwargs: Any) -> Any:
            with stage_boundary("STOP"):
                return await original_close(*args, **kwargs)

        cast(Any, session).close = observed_close
        with stage_boundary("AUTHORIZE"):
            await session.start()
        running = False
        try:
            with stage_boundary("PERSIST"):
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
            with stage_boundary("CALL"):
                await Worker(
                    session, TechnicalRunner(), dispatch_jobs=False, task_ids=frozenset({task})
                ).run(stop)
        finally:
            timer.cancel()
            if not running:
                with stage_boundary("STOP"):
                    await session.close(clean=True)
            cast(Any, session).close = original_close

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
        @contextmanager
        def capture_signals(self) -> Iterator[None]:
            # 本工具由asyncio loop持有固定stop handler；不在正常serve后重抛SIGTERM。
            yield

        async def startup(self, sockets: Any = None) -> None:
            with stage_boundary("PREPARE"):
                await super().startup(sockets)
                require(self.started, "P4A_API_START")
            with stage_boundary("PERSIST"):
                write_private(
                    Path(request["ready_file"]), {"api_ready": True, **_process_receipt()}
                )

        async def main_loop(self) -> None:
            with stage_boundary("CALL"):
                await super().main_loop()

        async def shutdown(self, sockets: Any = None) -> None:
            with stage_boundary("STOP"):
                await super().shutdown(sockets)

    port = request["api_port"]
    require(type(port) is int and 1024 <= port <= 65535, "P4A_API_PORT")
    server = ObservedServer(
        uvicorn.Config(app, host="0.0.0.0", port=port, access_log=False, log_level="critical")  # noqa: S104
    )

    async def serve() -> None:
        import signal

        def stop() -> None:
            server.should_exit = True

        loop = asyncio.get_running_loop()
        for signum in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(signum, stop)
        timer = loop.call_later(_runtime(request["runtime"]).remaining(), stop)
        try:
            await server.serve()
        finally:
            timer.cancel()
            for signum in (signal.SIGTERM, signal.SIGINT):
                loop.remove_signal_handler(signum)

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
        import socket

        from commerceops.infrastructure.worker_lock import process_namespace

        identity = _process_identity(pid)
        require(
            receipt["host"] == socket.gethostname()
            and receipt["pid_namespace"] == process_namespace()
            and all(receipt.get(k) == v for k, v in identity.items()),
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


def process_probe_stage(request: Mapping[str, Any]) -> dict[str, Any]:
    """同namespace独立OS探针；只读本轮私有入口argv，排除探针自身。"""
    private = Path(request["private_root"])
    require(private.is_absolute() and private.is_dir(), "P4A_PRIVATE_ROOT")
    if "absent_receipts" in request:
        from commerceops.infrastructure.worker_lock import require_process_absent

        receipts = json.loads(private_ref(request["absent_receipts"]))
        require(type(receipts) is list and bool(receipts), "P4A_PROCESS_RECEIPTS")
        for receipt in receipts:
            require_process_absent({k: receipt[k] for k in ("pid", "host", "pid_namespace")})
        return dict(
            exit_code=0,
            stage_result="COMPLETE",
            suite_PASS=False,
            owned_entry_processes=0,
            actual_absence_checks=len(receipts),
        )
    live = 0
    if sys.platform != "linux":
        require(sys.platform == "darwin", "P4A_PROCESS_PLATFORM")
        rows = (
            subprocess.run(
                ["/bin/ps", "-Aww", "-o", "pid=", "-o", "command="],
                capture_output=True,
                check=True,
                timeout=5,
            )
            .stdout.decode()
            .splitlines()
        )
        for row in rows:
            parts = row.strip().split(None, 1)
            if len(parts) == 2 and int(parts[0]) != os.getpid():
                if str(private) + "/" in parts[1] and "/run_once.py" in parts[1]:
                    live += 1
        return dict(
            exit_code=int(live != 0),
            owned_entry_processes=live,
            stage_result="COMPLETE" if live == 0 else "FAILED",
            suite_PASS=False,
        )
    for process in Path("/proc").iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            arguments = (process / "cmdline").read_bytes().split(b"\0")
            for argument in arguments:
                if not argument.endswith(b"/run_once.py"):
                    continue
                path = Path(os.fsdecode(argument))
                if path.is_relative_to(private):
                    live += 1
                    break
        except (FileNotFoundError, ProcessLookupError):
            continue
    return dict(
        exit_code=0 if live == 0 else 1,
        stage_result="COMPLETE" if live == 0 else "FAILED",
        owned_entry_processes=live,
        suite_PASS=False,
    )


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
        _APP_OWNERS[(run_id, epoch["owner"])] = {
            "path": str(children["worker"].ready),
            "sha256": digest(bound_bytes(children["worker"].ready, private=True)),
        }
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
    original_dispatch = native_module.BaseDeliveryStore.dispatch_one
    original_close = native_module.WorkerSession.close
    native_errors: list[dict[str, Any]] = []
    factory_initialized = False

    async def observed_close(*args: Any, **kwargs: Any) -> Any:
        with stage_boundary("STOP"):
            return await original_close(*args, **kwargs)

    async def observed_scope(*args: Any, **kwargs: Any) -> Any:
        with report.enter("AUTHORIZE"):
            return await original_scope(*args, **kwargs)

    async def observed_target(*args: Any, **kwargs: Any) -> Any:
        nonlocal factory_initialized
        try:
            with report.enter("PREFLIGHT"):
                return await original_target(*args, **kwargs)
        finally:
            factory_initialized = args[0].client is not None

    async def observed_dispatch(store: Any) -> Any:
        try:
            return await original_dispatch(store)
        except Exception as error:
            mark_stage(error, "CALL")
            failure = safe_failure(error, "CALL")
            native_errors.append(failure)
            report.stages["CALL"].update(state="FAILED", failure=failure)
            raise

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
            mark_stage(error, "CALL")
            row.update(state="FAILED", failure=safe_failure(error, "CALL"))
            raise

    native_module.trusted_scope, native_module.verified_target = observed_scope, observed_target
    native_module.BusinessBaseAdapter.project = observed_project
    native_module.BaseDeliveryStore.dispatch_one = observed_dispatch
    native_module.WorkerSession.close = observed_close
    transport: Any = None
    summary: dict[str, Any] = {}
    try:
        if request.get("ready_file"):
            write_private(Path(request["ready_file"]), _process_receipt())
        if request["transport"] == "fake":
            from tests.p4_acceptance_support import FakeHTTPTransport

            private_ref(refs["external_records"])
            for path in (
                settings.app_secret_file,
                settings.base_app_token_file,
                settings.base_table_id_file,
            ):
                if path is not None:
                    require(
                        path.parent == Path(refs["business"]["path"]).parent,
                        "P4A_SYNTHETIC_PRIVATE_ROOT",
                    )
                    bound_bytes(path, private=True)
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
            if "lab_http" in refs:
                from tests.p4_acceptance_support import FakeHTTPTransport

                lab = json.loads(private_ref(refs["lab_http"]))
                require(
                    config.database.name.startswith("p4_ro_lab_")
                    and lab["database"] == config.database.name
                    and lab["organization_id"] == str(window.organization_id)
                    and "dummy-app-material" == settings.app_secret_file.name
                    and "dummy-base-material" == settings.base_app_token_file.name
                    and settings.app_secret_file.parent == Path(refs["business"]["path"]).parent,
                    "P4A_LAB_SCOPE",
                )
                transport = FakeHTTPTransport(Path(lab["external_ref"]["path"]), settings)
                private_ref(lab["external_ref"])
                with transport.installed():
                    summary = asyncio.run(
                        native.controlled_work(settings, window, config, M1DemoFactory())
                    )
            else:
                summary = asyncio.run(
                    native.controlled_work(settings, window, config, M1DemoFactory())
                )
    finally:
        native_module.trusted_scope, native_module.verified_target = original_scope, original_target
        native_module.BusinessBaseAdapter.project = original_project
        native_module.BaseDeliveryStore.dispatch_one = original_dispatch
        native_module.WorkerSession.close = original_close
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
        "failure": next(
            (r["failure"] for r in report.stages.values() if r["state"] == "FAILED"), None
        ),
        "native_summary": summary,
        "native_errors": native_errors,
        "witnesses": witnesses,
        "pg_proof": proof,
        "counts": {
            "native_factory_invocations": int(report.stages["PREFLIGHT"]["state"] != "NOT_RUN"),
            "official_sdk_objects_constructed": 1
            if factory_initialized
            else 0
            if report.stages["PREFLIGHT"]["state"] == "NOT_RUN"
            else "not_separately_observed",
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

    real_control = request["transport"] == "real"
    require(
        not real_control
        or (
            request.get("root_real_release") is True
            and request.get("control_mode") == "native_no_ws"
        ),
        "P4A_REAL_PLATFORM_HOLD",
    )
    refs = request["private_refs"]
    settings = BusinessSettings.model_validate_json(private_ref(refs["business"]))
    window = GatewayWindow.model_validate_json(private_ref(refs["window"]))
    private_ref(refs["web_config"])
    config = WebConfig.from_file(Path(refs["web_config"]["path"]))
    if real_control:
        require(
            window.max_workflows == 0
            and window.max_callbacks == 1
            and not settings.f02_enabled
            and not settings.external_sender_enabled,
            "P4A_REAL_SCOPE",
        )
    stopped = False

    def stop(signum: int, frame: Any) -> None:
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, stop)
    # 原App lease是session advisory lock，必须与真实child生命周期同长。
    with stage_boundary("ROLE"):
        connection = connect(config.database)
    with stage_boundary("STOP"), connection as db:
        with stage_boundary("AUTHORIZE"):
            claim_gateway(db, settings, window)
        with stage_boundary("PERSIST"):
            gateway_process_started(db, window)
            write_private(
                Path(request["ready_file"]),
                {
                    "claimed": True,
                    **_process_receipt(),
                    "native_no_ws_control": real_control,
                    "SDK_Secret_WS": 0,
                },
            )
        with stage_boundary("STOP"):
            while not stopped and window.active():
                time.sleep(0.05)
    return {"stage_result": "COMPLETE", "exit_code": 0, "suite_PASS": False}


def prepare_case_stage(request: Mapping[str, Any]) -> dict[str, Any]:
    """同一outer内准备新PG fixture、原生RO及实际C快照；只返回阶段证据。"""

    import psycopg
    from commerceops.infrastructure.database import DatabaseSettings, connect
    from commerceops.infrastructure.worker_lock import process_namespace
    from psycopg import sql

    from tests.e2e.web import m1_acceptance_capture as capture
    from tests.p4_acceptance_support import AcceptanceFixture, prepare_batch_ro, prepare_single_ro
    from tests.test_p4_acceptance_pg import initialize_schema

    owner = DatabaseSettings.model_validate_json(private_ref(request["owner_database_ref"]))
    require(owner.user == "commerceops_owner" and owner.host == "postgres", "P4A_BOOTSTRAP_ROLE")
    require(owner.runtime_password_file is not None, "P4A_BOOTSTRAP_ROLE")
    private = Path(request["private_directory"])
    require(
        private.is_dir() and private.parent == Path(request["private_root"]), "P4A_PRIVATE_ROOT"
    )
    name = database_plan_name(request)
    with stage_boundary("SCHEMA"), psycopg.connect(**owner.kwargs(), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    database_created(request, name)
    owner = owner.model_copy(update={"name": name})
    app = owner.model_copy(
        update={
            "user": "commerceops_app",
            "password_file": owner.runtime_password_file,
            "runtime_password_file": None,
        }
    )
    revision = request["revision"]
    with stage_boundary("SCHEMA"):
        initialize_schema(owner, revision)
        schema = schema_contract(owner, app, revision)
    if request["action"] == "schema_case":
        app_file = private / "app-database.json"
        write_private(app_file, app.model_dump(mode="json"))
        return dict(
            exit_code=0,
            stage_result="COMPLETE",
            schema=schema,
            suite_PASS=False,
            app_database_ref={
                "path": str(app_file),
                "sha256": digest(bound_bytes(app_file, private=True)),
            },
        )
    require(revision == "0016", "P4A_SCHEMA_REVISION")
    a = AcceptanceFixture.prepare(
        owner,
        app,
        private,
        _runtime(request["runtime"]),
        case_kind=request["case_kind"],
        entry_manifest_ref=request["source_manifest_ref"],
    )
    try:
        result = (
            prepare_single_ro(a, concurrent_once=True)
            if a.case_kind == "recover_single_item"
            else prepare_batch_ro(a)
        )
        f = a.fixture
        # 仅本轮新私配增加已登记的实际loopback origins；审批/SDK/会话TTL不变。
        config_value = json.loads(bound_bytes(f.config_file, private=True))
        config_value["origins"] = list(dict.fromkeys(request["origins"]))
        write_private(f.config_file, config_value)
        from commerceops.infrastructure.web_config import WebConfig

        f.config = WebConfig.from_file(f.config_file)
        task_id = next(iter(result["window"].task_ids))
        delivery = result["delivery"]
        worker_owner = result["verified"]["pg_proof"]["worker_owner"]
        with connect(app) as db:
            task = db.execute(
                "SELECT t.thread_id,s.source_task_id FROM business.business_tasks t "
                "JOIN business.p3_task_sources s ON s.task_id=t.id WHERE t.id=%s",
                (task_id,),
            ).fetchone()
            if task is None:
                raise AcceptanceFailure("P4A_HANDOFF_HISTORY")
            source = db.execute(
                "SELECT thread_id FROM business.business_tasks WHERE id=%s",
                (task["source_task_id"],),
            ).fetchone()
            approval = db.execute(
                "SELECT id,plan_id,decision_id FROM business.approvals WHERE task_id=%s",
                (task_id,),
            ).fetchone()
            execution = db.execute(
                "SELECT id FROM business.executions WHERE task_id=%s", (task_id,)
            ).fetchone()
            identity = db.execute(
                "SELECT r.identity_id FROM business.p4_inbox_receipts r "
                "JOIN business.inbox_events i ON i.id=r.inbox_id WHERE i.task_id=%s "
                "AND i.sanitized_payload->>'event_type'='im.message.receive_v1'",
                (task_id,),
            ).fetchone()
            items = QUERIES["ITEMS"].execute(db, (task_id,), revision="0016", role="app")
            proof = db.execute(
                "SELECT * FROM business.p4_base_deliveries WHERE outbox_id=%s",
                (delivery["outbox_id"],),
            ).fetchone()
            starts = db.execute(
                "SELECT id,after_state FROM business.audit_events WHERE source='worker' "
                "AND action='started' AND entity_id=%s",
                (worker_owner,),
            ).fetchall()
            ends = db.execute(
                "SELECT id FROM business.audit_events WHERE source='worker' "
                "AND action='termination_confirmed' AND entity_id=%s",
                (worker_owner,),
            ).fetchall()
            claim = db.execute(
                "SELECT after_state FROM business.audit_events WHERE id=%s",
                (result["window"].window_id,),
            ).fetchone()
        require(
            bool(source and approval and execution and identity and proof and claim)
            and len(starts) == len(ends) == 1,
            "P4A_HANDOFF_HISTORY",
        )
        if not (source and approval and execution and identity and proof and claim):
            raise AcceptanceFailure("P4A_HANDOFF_HISTORY")
        threads = tuple(dict.fromkeys([task["thread_id"], source["thread_id"]]))
        context = capture.CaptureContext(
            "0016_p4_clarification_requests",
            str(f.actor.organization_id),
            str(f.inventory.data.shop),
            str(task_id),
            str(delivery["item_id"]),
            str(f.actor.principal_id),
            str(f.actor.identity_id),
            f.actor.auth_version,
            threads,
            sdk_window_id=str(result["window"].window_id),
            sdk_subject_ids=(str(delivery["outbox_id"]),),
            case_kind=a.case_kind,
            expected_item_count=a.expected_item_count,
            expected_quantity_total=a.expected_quantity_total,
        )
        with stage_boundary("COLLECT"):
            with connect(app) as db:
                snapshot = capture.capture_snapshot(db, context)
            capture.validate_business(snapshot, context, closed=False)
            capture.validate_base_readback(
                snapshot,
                context,
                version=1,
                target_key=proof["target_key"],
                external_id=proof["external_id"],
                verification_mode=proof["verification_mode"],
                native_projection_hash=proof["projection_hash"],
            )
        start = starts[0]
        continuation = a.save_continuation(result)
        external_snapshot = private / "external-records-v1.json"
        write_private(external_snapshot, json.loads(bound_bytes(a.external, private=True)))
        return dict(
            exit_code=0,
            stage_result="COMPLETE",
            suite_PASS=False,
            schema=schema,
            continuation_ref=continuation,
            native_recovery_evidence={
                "case_kind": a.case_kind,
                "concurrent_once": result.get("concurrent_once"),
                "cold_replay": result.get("replay_proof"),
                "native_factory_and_transport": result["verified"]["counts"],
                "current_method_counts": result["verified"]["pg_proof"]["method_counts"],
                "child_lifecycles": [
                    {
                        "action": c.request["action"],
                        "actual_exit": c.process.returncode,
                        "OS_waited": c.process.returncode is not None,
                        "native_confirmed": c.confirmed,
                        "verified_no_native_start": c.lifecycle_not_started,
                    }
                    for c in a.processes
                ],
            },
            private_refs={
                "web_config": {
                    "path": str(f.config_file),
                    "sha256": digest(bound_bytes(f.config_file, private=True)),
                },
                **{
                    k: {"path": str(p), "sha256": digest(bound_bytes(p, private=True))}
                    for k, p in (
                        ("app_database_config", private / "app-database.json"),
                        ("web_credentials", private / "web-credentials.json"),
                        ("external_records", external_snapshot),
                    )
                },
            },
            fixture=dict(
                case_kind=a.case_kind,
                item_count=a.expected_item_count,
                quantity_total=a.expected_quantity_total,
                organization_id=str(f.actor.organization_id),
                shop_id=str(f.inventory.data.shop),
                principal_id=str(f.actor.principal_id),
                feishu_identity_id=str(identity["identity_id"]),
                web_identity_id=str(f.actor.identity_id),
                auth_version=f.actor.auth_version,
                task_id=str(task_id),
                source_task_id=str(task["source_task_id"]),
                plan_id=str(approval["plan_id"]),
                approval_id=str(approval["id"]),
                decision_id=str(approval["decision_id"]),
                execution_id=str(execution["id"]),
                item_ids=[str(r["id"]) for r in items],
                target_item_id=str(delivery["item_id"]),
                checkpoint_threads=list(threads),
                schema_revision=context.revision,
            ),
            baseline=dict(
                schema_revision=context.revision,
                core=capture.immutable_business(snapshot),
                checkpoints=capture.checkpoint_fingerprint(snapshot),
            ),
            base_ro=dict(
                typed_result=result["verified"]["witnesses"][0]["result"],
                window_id=str(result["window"].window_id),
                **{k: str(delivery[k]) for k in ("outbox_id", "item_id", "client_token")},
                version=1,
                projection_hash=proof["projection_hash"],
                request_hash=delivery["request_hash"],
                pg_proof=capture.normalized(proof),
            ),
            worker=dict(
                epoch="base_ro",
                owner=worker_owner,
                pid=start["after_state"]["pid"],
                namespace=process_namespace(),
                process_started_id=str(start["id"]),
                termination_id=str(ends[0]["id"]),
                claim_id=str(result["window"].window_id),
                claim_hash=digest(canonical(claim["after_state"])),
                reaped=True,
            ),
        )
    finally:
        primary = sys.exception()
        try:
            with stage_boundary("STOP"):
                require(a.cleanup(), "P4A_PREPARE_CLEANUP_FAILED")
        except Exception as cleanup_error:
            if primary is None:
                raise
            cast(Any, primary).p4a_cleanup_failure = safe_failure(cleanup_error, "STOP")


def negative_matrix_stage(request: Mapping[str, Any]) -> dict[str, Any]:

    import psycopg
    from commerceops.infrastructure.database import DatabaseSettings
    from psycopg import sql

    from tests.p4_acceptance_support import native_negative_matrix
    from tests.test_p4_acceptance_pg import initialize_schema

    owner = DatabaseSettings.model_validate_json(private_ref(request["owner_database_ref"]))
    require(
        owner.user == "commerceops_owner"
        and owner.host == "postgres"
        and owner.runtime_password_file is not None,
        "P4A_BOOTSTRAP_ROLE",
    )
    name = database_plan_name(request)
    with stage_boundary("SCHEMA"), psycopg.connect(**owner.kwargs(), autocommit=True) as db:
        db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    database_created(request, name)
    owner = owner.model_copy(update={"name": name})
    app = owner.model_copy(
        update={
            "user": "commerceops_app",
            "password_file": owner.runtime_password_file,
            "runtime_password_file": None,
        }
    )
    with stage_boundary("SCHEMA"):
        initialize_schema(owner, "0016")
        schema = schema_contract(owner, app, "0016")
    result = native_negative_matrix(
        owner,
        app,
        Path(request["private_directory"]),
        _runtime(request["runtime"]),
        request["source_manifest_ref"],
    )
    result["diagnostic_faults"] = diagnostic_faults(request)
    return dict(exit_code=0, stage_result="COMPLETE", value=result, schema=schema, suite_PASS=False)


def diagnostic_faults(request: Mapping[str, Any]) -> dict[str, Any]:
    """同entry的固定诊断负例；只用新legacy库，独立关闭连接和wait/reap。"""
    from uuid import uuid4

    from commerceops.infrastructure.database import DatabaseSettings, connect

    from tests.p4_acceptance_support import PinnedProcess

    directory = Path(request["private_directory"]) / "diagnostic"
    directory.mkdir(mode=0o700)
    manifest_ref = request["source_manifest_ref"]
    manifest = json.loads(private_ref(manifest_ref))
    entry = Path(manifest["entry"])
    records: dict[str, Any] = {}

    def invoke(label: str, value: dict[str, Any]) -> dict[str, Any]:
        value.update(
            contract=CONTRACT,
            runtime=request["runtime"],
            output_file=str(directory / (label + ".json")),
        )
        if "expected_namespace" in request:
            value["expected_namespace"] = request["expected_namespace"]
        child = PinnedProcess.start(entry, Path(manifest_ref["path"]), value)
        result = child.wait(timeout=min(30, _runtime(request["runtime"]).remaining()))
        require(child.process.returncode == result["exit_code"], "P4A_CHILD_EXIT_DISAGREEMENT")
        records[label] = dict(
            actual_outer_exit=child.process.returncode,
            reaped=child.process.returncode is not None,
            failure=result.get("failure"),
            result_ref={
                "path": value["output_file"],
                "sha256": digest(bound_bytes(Path(value["output_file"]), private=True)),
            },
        )
        return result

    corrupted = dict(manifest)
    corrupted["files"] = {**manifest["files"], "scripts/p4_acceptance.py": "0" * 64}
    bad_manifest = directory / "wrong-source-manifest.json"
    write_private(bad_manifest, corrupted)
    source = PinnedProcess.start(
        entry,
        bad_manifest,
        dict(
            contract=CONTRACT,
            action="source_probe",
            output_file=str(directory / "unused-source.json"),
        ),
    )
    try:
        stdout, _ = source.process.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        source.terminate()
        raise AcceptanceFailure("P4A_SOURCE_FAULT_TIMEOUT") from None
    load_failure = json.loads(stdout)
    require(
        source.process.returncode == 1 and load_failure["code"] == "P4A_BOOTSTRAP",
        "P4A_SOURCE_FAULT",
    )
    records["load"] = dict(
        actual_outer_exit=1, reaped=True, failure=load_failure, PG_SDK_not_run=True
    )
    legacy = request["legacy_app_database_ref"]
    context = dict(
        revision="0016_p4_clarification_requests",
        organization_id=str(uuid4()),
        shop_id=str(uuid4()),
        task_id=str(uuid4()),
        item_id=str(uuid4()),
        principal_id=str(uuid4()),
        identity_id=str(uuid4()),
        auth_version=1,
        checkpoint_threads=["p4a-diagnostic"],
        request_key=None,
        sdk_window_id=None,
        sdk_subject_ids=[],
        case_kind="recover_single_item",
        expected_item_count=1,
        expected_quantity_total="70",
    )
    for label, fault in (("call", "call_signature"), ("capture", None)):
        value = dict(
            action="capture",
            kind="snapshot",
            private_refs={"app_database_config": legacy},
            capture_context=context,
        )
        if fault is not None:
            value["fault_probe"] = fault
        result = invoke(label, value)
        require(result["exit_code"] == 1, "P4A_DIAGNOSTIC_REJECT_REQUIRED")
        require(
            result["failure"]["stage"] == ("CALL" if fault else "COLLECT"), "P4A_DIAGNOSTIC_STAGE"
        )
        if label == "capture":
            require(result["failure"]["sqlstate"] == "42P01", "P4A_DIAGNOSTIC_SQLSTATE")
    timeout = invoke(
        "timeout",
        dict(
            action="sql_denial",
            app_database_ref=legacy,
            fault_probe="statement_timeout",
        ),
    )
    require(
        timeout["exit_code"] == 1 and timeout["failure"]["sqlstate"] == "57014", "P4A_TIMEOUT_FAULT"
    )
    inventory_request = dict(
        action="database_inventory",
        run_id=request["run_id"],
        private_root=request["private_root"],
        owner_database_ref=request["owner_database_ref"],
        databases=request["databases"],
    )
    app = DatabaseSettings.model_validate_json(private_ref(legacy))
    with connect(app) as held:
        held.execute("SET TRANSACTION READ ONLY")
        held.execute("SELECT 1").fetchone()
        closure = invoke("cleanup_connection_fault", dict(inventory_request))
        require(
            closure["exit_code"] == 1
            and bool(closure["value"]["active_business_connections"])
            and closure["value"]["inventory_connection_closed"] is True,
            "P4A_CLOSURE_FAULT_NOT_DETECTED",
        )
    require(held.closed, "P4A_DIAGNOSTIC_CONNECTION_REMAINS")
    repaired = invoke("cleanup_connection_released", dict(inventory_request))
    require(
        repaired["exit_code"] == 0 and repaired["value"]["verified"], "P4A_CLOSURE_RECOVERY_FAILED"
    )
    return dict(records=records, held_connection_closed=held.closed, whole_PASS=False)


def database_plan_name(request: Mapping[str, Any]) -> str:
    from uuid import UUID

    plan = request["database_plan"]
    require(
        plan["id"] == request["database_id"]
        and plan["name"] == "p4a_" + UUID(plan["id"]).hex
        and plan["owner"] == "commerceops_owner"
        and plan["registration_file"] == "database-" + UUID(plan["id"]).hex + ".json",
        "P4A_DATABASE_PLAN",
    )
    return str(plan["name"])


def database_created(request: Mapping[str, Any], name: str) -> None:
    plan = request["database_plan"]
    require(database_plan_name(request) == name, "P4A_DATABASE_PLAN")
    path = Path(request["private_root"]) / plan["registration_file"]
    with stage_boundary("PERSIST"):
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(
                canonical(
                    {
                        **plan,
                        "created": True,
                        "created_utc": datetime.now(UTC).isoformat(),
                        "run_id": request["run_id"],
                    }
                )
                + b"\n"
            )
            stream.flush()
            os.fsync(stream.fileno())


def database_inventory_stage(request: Mapping[str, Any]) -> dict[str, Any]:
    """仅owner元数据：保留库逐项闭合，排除且关闭本检查自身连接。"""
    from commerceops.infrastructure.database import DatabaseSettings, connect

    settings = DatabaseSettings.model_validate_json(private_ref(request["owner_database_ref"]))
    require(settings.user == "commerceops_owner" and settings.host == "postgres", "P4A_ROLE")
    plans = request["databases"]
    require(len(plans) == 4 and len({p["name"] for p in plans}) == 4, "P4A_DATABASE_PLAN")
    declared: dict[str, Any] = {}
    for plan in plans:
        path = Path(request["private_root"]) / plan["registration_file"]
        if not path.exists():
            continue  # 未进入的已登记步骤不会被倒填成created。
        receipt = json.loads(bound_bytes(path, private=True))
        require(
            all(receipt[k] == v for k, v in plan.items())
            and receipt["created"] is True
            and receipt["run_id"] == request["run_id"],
            "P4A_DATABASE_REGISTRATION",
        )
        declared[plan["name"]] = receipt
    with stage_boundary("CLEANUP"), connect(settings) as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        db.execute("SET LOCAL statement_timeout='5000ms'")
        db.execute("SET LOCAL lock_timeout='3000ms'")
        role = db.execute("SELECT current_user::text AS role,pg_backend_pid() AS pid").fetchone()
        require(role is not None and role["role"] == "commerceops_owner", "P4A_ROLE")
        observed = db.execute(
            "SELECT datname::text AS name,pg_get_userbyid(datdba)::text AS owner "
            "FROM pg_database ORDER BY datname"
        ).fetchall()
        clients = db.execute(
            "SELECT datname::text AS database,usename::text AS role,pid,state::text AS state "
            "FROM pg_stat_activity WHERE backend_type='client backend' AND pid<>pg_backend_pid() "
            "AND (datname=ANY(%s::text[]) OR usename='commerceops_app') ORDER BY datname,pid",
            ([p["name"] for p in plans],),
        ).fetchall()
        actual = {r["name"]: r["owner"] for r in observed}
        defaults = {"template0", "template1", "postgres", "commerceops"}
        expected = defaults | set(declared)
        verified = (
            set(actual) == expected
            and all(actual[n] == receipt["owner"] for n, receipt in declared.items())
            and not clients
        )
    closed = db.closed
    value = dict(
        verified=verified and closed,
        plans=plans,
        created_receipts=list(declared.values()),
        observed=observed,
        unregistered=sorted(set(actual) - expected),
        missing=sorted(expected - set(actual)),
        active_business_connections=clients,
        excluded_inventory_connection_pid=role["pid"] if role is not None else None,
        inventory_connection_closed=closed,
        connection_scope="registered DBs + all app clients; inventory PID excluded",
        retained_for="same-volume replay and evidence; no DROP/no down-v",
    )
    return dict(
        exit_code=0 if value["verified"] else 1,
        stage_result="COMPLETE" if value["verified"] else "FAILED",
        value=value,
        suite_PASS=False,
        failure=None
        if value["verified"]
        else safe_failure(AcceptanceFailure("P4A_DATABASE_CLOSURE"), "CLEANUP"),
    )


def sql_denial_stage(request: Mapping[str, Any]) -> dict[str, Any]:
    from commerceops.infrastructure.database import DatabaseSettings, connect

    app = DatabaseSettings.model_validate_json(private_ref(request["app_database_ref"]))
    require(app.user == "commerceops_app" and app.runtime_password_file is None, "P4A_ROLE")
    with connect(app) as db:
        if request.get("fault_probe") == "statement_timeout":
            with stage_boundary("CALL"):
                db.execute("SET LOCAL statement_timeout='25ms'")
                db.execute("SELECT pg_sleep(1)").fetchone()
        db.execute("SELECT version_num FROM business.alembic_version").fetchall()
    raise AcceptanceFailure("P4A_APP_METADATA_PERMISSION")


def project_v2_stage(request: Mapping[str, Any]) -> dict[str, Any]:
    """原workflow恢复作用域投影原生T6新outbox；不造claim或delivery。"""
    from uuid import UUID

    from commerceops.infrastructure.database import connect

    from tests.p4_acceptance_support import AcceptanceFixture
    from tests.test_p4_a09_workflow_pg import manifest

    with stage_boundary("PREPARE"):
        a, history = AcceptanceFixture.restore(
            request["continuation_ref"], _runtime(request["runtime"])
        )
    gateway = child = None
    try:
        t6 = json.loads(private_ref(request["t6_result_ref"]))
        outbox_id = UUID(t6["v2_outbox"]["id"])
        task_id = UUID(t6["task_id"])
        require(a.case_kind == "recover_single_item", "P4A_V2_CASE")
        with connect(a.fixture.config.database) as db:
            pending = db.execute(
                "SELECT id,aggregate_id,aggregate_version,provider_idempotency_key,request_hash "
                "FROM business.outbox WHERE id=%s AND task_id=%s AND operation='item_projection'",
                (outbox_id, task_id),
            ).fetchone()
            jobs = db.execute(
                "SELECT status FROM business.jobs WHERE task_id=%s OR task_id="
                "(SELECT source_task_id FROM business.p3_task_sources WHERE task_id=%s)",
                (task_id, task_id),
            ).fetchall()
            anchor = db.execute(
                "SELECT external_id FROM business.p4_base_links WHERE item_id=%s",
                (UUID(t6["item_id"]),),
            ).fetchone()
        if pending is None or anchor is None:
            raise AcceptanceFailure("P4A_V2_NATIVE_OUTBOX_REQUIRED")
        require(
            bool(jobs)
            and all(j["status"] == "done" for j in jobs)
            and pending["aggregate_version"] == 2
            and str(pending["aggregate_id"]) == t6["item_id"]
            and str(pending["provider_idempotency_key"])
            == t6["v2_outbox"]["provider_idempotency_key"],
            "P4A_V2_NATIVE_OUTBOX_REQUIRED",
        )
        gateway, child = a.gateway()
        window = manifest(
            a.fixture,
            history["origin_gateway"],
            gateway,
            task_id,
            history["origin_owner"],
            history["origin_window"].window_id,
        )
        # 原single SDK只有known70额度；恢复不得借通用group20模板抬高IM/create cap。
        window = window.model_copy(update={"caps": dict(history["origin_window"].caps)})
        a.external_behavior("normal")
        with stage_boundary("CALL"):
            _, result = a.worker(window, stop_after_verified=outbox_id)
        if result["exit_code"] != 0:
            raise_child_failure(result, "PERSIST")
        witnesses = result["witnesses"]
        require(
            len(witnesses) == 1
            and witnesses[0]["request"]["outbox_id"] == str(outbox_id)
            and witnesses[0]["request"]["operation"] == "update"
            and witnesses[0]["result"]["external_id"] == anchor["external_id"],
            "P4A_V2_RECORD_CHANGED",
        )
        return dict(exit_code=0, stage_result="COMPLETE", value=result, suite_PASS=False)
    finally:
        primary = sys.exception()
        try:
            with stage_boundary("STOP"):
                try:
                    if gateway is not None and child is not None and not child.confirmed:
                        a.stop_gateway(gateway, child)
                finally:
                    require(a.cleanup(), "P4A_V2_CLEANUP_FAILED")
        except Exception as cleanup_error:
            if primary is None:
                raise
            cast(Any, primary).p4a_cleanup_failure = safe_failure(cleanup_error, "STOP")


def _outside_ref(ref: Mapping[str, str], runner: Mapping[str, Any]) -> dict[str, str]:
    try:
        relative = Path(ref["path"]).relative_to(Path(runner["container_private_dir"]))
    except ValueError:
        raise AcceptanceFailure("P4A_REF_MOUNT") from None
    require(".." not in relative.parts, "P4A_REF_MOUNT")
    value = {"path": str(Path(runner["host_private_dir"]) / relative), "sha256": ref["sha256"]}
    private_ref(value)
    return value


def resource_cleanup(handoff: Mapping[str, Any]) -> dict[str, Any]:
    """独立于业务快照与SDK结果，只处置登记的本轮不可变资源；卷保留。"""
    resource = handoff["resource"]
    errors: list[dict[str, Any]] = []
    exits: dict[str, int] = {}
    classifications: dict[str, str] = {}
    signals: dict[str, Any] = {}
    ids = resource["container_ids"]
    require(isinstance(ids, dict) and bool(ids), "P4A_RESOURCE_IDS")
    require(len(set(ids.values())) == len(ids), "P4A_RESOURCE_IDS")
    # 先核所有归属，拒绝混入任何未登记实例，然后才可停止。
    for name, cid in ids.items():
        value = json.loads(_docker(["inspect", cid]).stdout)[0]
        labels = value["Config"]["Labels"]
        require(
            value["Id"] == cid
            and labels.get("p4.acceptance.run") == resource["run_id"]
            and labels.get("p4.acceptance.owner") == resource["owner_label"]
            and labels.get("com.docker.compose.project") == resource["project"]
            and value["Image"] == handoff["candidate"]["actual_images"][name]["id"],
            "P4A_CLEANUP_OWNER",
        )
    for name in sorted(ids, key=lambda n: n == "postgres"):
        cid = ids[name]
        try:
            before = json.loads(_docker(["inspect", cid]).stdout)[0]
            started = time.monotonic()
            _docker(["stop", "--signal", "SIGTERM", "--time", "15", cid], timeout=25)
            signals[name] = dict(
                requested_signal="SIGTERM",
                immutable_container_id=cid,
                running_before_signal=before["State"]["Running"],
                command_exit=0,
                command_seconds=round(time.monotonic() - started, 6),
            )
            value = json.loads(_docker(["inspect", cid]).stdout)[0]
            require(value["State"]["Running"] is False, "P4A_CONTAINER_STILL_RUNNING")
            exits[name] = value["State"]["ExitCode"]
            expected_term = (
                name == "web"
                and exits[name] == 143
                and before["State"]["Running"] is True
                and value["State"]["OOMKilled"] is False
                and not value["State"]["Error"]
            )
            classifications[name] = (
                "normal_exit"
                if exits[name] == 0
                else "expected_owned_SIGTERM"
                if expected_term
                else "unexpected_exit"
            )
            if exits[name] != 0 and not expected_term:
                errors.append(
                    safe_failure(AcceptanceFailure("P4A_CONTAINER_UNCLEAN_EXIT"), "CLEANUP")
                )
            _docker(["rm", cid])
        except Exception as error:
            errors.append(safe_failure(error, "CLEANUP"))
    try:
        network = json.loads(_docker(["network", "inspect", resource["network_id"]]).stdout)[0]
        require(
            network["Id"] == resource["network_id"]
            and network["Labels"].get("p4.acceptance.run") == resource["run_id"]
            and network["Labels"].get("p4.acceptance.owner") == resource["owner_label"]
            and not network["Containers"],
            "P4A_NETWORK_OWNER",
        )
        _docker(["network", "rm", resource["network_id"]])
    except Exception as error:
        errors.append(safe_failure(error, "CLEANUP"))
    containers = _docker(
        ["ps", "-aq", "--filter", "label=com.docker.compose.project=" + resource["project"]]
    ).stdout.split()
    networks = _docker(
        [
            "network",
            "ls",
            "-q",
            "--filter",
            "label=com.docker.compose.project=" + resource["project"],
        ]
    ).stdout.split()
    volume = json.loads(_docker(["volume", "inspect", resource["volume"]]).stdout)[0]
    kept = (
        volume["Name"] == resource["volume"]
        and volume["Labels"].get("p4.acceptance.run") == resource["run_id"]
        and volume["Labels"].get("p4.acceptance.owner") == resource["owner_label"]
    )
    from urllib.parse import urlsplit

    from tests.e2e.web.m1_acceptance_driver import listener_open

    closed_ports = []
    for name in ("api_origin", "web_origin"):
        url = urlsplit(handoff["web"][name])
        require(url.hostname == "127.0.0.1" and url.port is not None, "P4A_RESOURCE_PORTS")
        closed_ports.append(listener_open(cast(int, url.port)) is False)
    return dict(
        verified=not errors and not containers and not networks and kept and all(closed_ports),
        all_containers_reaped=len(exits) == len(ids) and not containers,
        container_exit_codes=exits,
        container_exit_classification=classifications,
        signal_receipts=signals,
        containers=len(containers),
        networks=len(networks),
        own_volume_preserved=kept,
        registered_listeners_closed=all(closed_ports),
        errors=errors,
    )


def run_stage(request: Mapping[str, Any], binding: SourceBinding) -> dict[str, Any]:
    """唯一outer的完整合成正向；C只是阶段consumer，结束后才可整体判定。"""

    import commerceops

    from tests.e2e.web.m1_acceptance_driver import consume_stage

    report = StageReport(
        (
            "SOURCE",
            "RESOURCE",
            "SCHEMA",
            "MATRIX",
            "PREPARE",
            "T6",
            "V2",
            "RESTART",
            "PAGE",
            "COLLECT",
            "STOP",
            "CLEANUP",
        )
    )
    handoff = load_handoff(request["resource_handoff_ref"])
    candidate, resource = handoff["candidate"], handoff["resource"]
    root = Path(resource["runner"]["host_private_dir"])
    results: dict[str, Any] = {}
    stop_good = False
    cleanup: dict[str, Any] = {}
    owned = False
    current_ref: dict[str, str] | None = None
    current: dict[str, Any] | None = None
    try:
        with report.enter("SOURCE"):
            require(commerceops.__file__ is not None, "P4A_IMPORT_REQUIRED")
            binding.check_loaded()
            require(
                binding.manifest["candidate"]
                == {"source_sha": candidate["source_sha"], "tree": candidate["tree"]},
                "P4A_CANDIDATE_SOURCE",
            )
            require(
                json.loads(
                    bound_bytes(
                        Path(candidate["manifest_file"]), candidate["manifest_sha256"], private=True
                    )
                )
                == binding.manifest,
                "P4A_CANDIDATE_MANIFEST",
            )
        with report.enter("RESOURCE"):
            runner = _verified_runner(handoff)
            owned = True
            require(request["transport"] == "fake", "P4A_REAL_PLATFORM_HOLD")
            require(resource["container_ids"]["runner"] == runner["container_id"], "P4A_RUNNER_ID")
            database_plans = {p["purpose"]: p for p in resource["databases"]}
            require(
                len(resource["databases"]) == 4
                and set(database_plans)
                == {
                    "legacy_schema_probe",
                    "negative_matrix",
                    "batch_twenty_items",
                    "recover_single_item",
                },
                "P4A_DATABASE_PLAN",
            )
        base_request = dict(
            owner_database_ref=_inside_ref(request["owner_database_ref"], runner),
            source_manifest_ref=_inside_ref(runner["manifest_ref"], runner),
            private_root=runner["container_private_dir"],
            run_id=resource["run_id"],
            databases=resource["databases"],
        )
        with report.enter("SCHEMA"):
            legacy = root / "legacy"
            legacy.mkdir(mode=0o700)
            results["legacy"] = _runner_result(
                _runner_start(
                    handoff,
                    {
                        **base_request,
                        "action": "schema_case",
                        "revision": "0015",
                        "database_id": database_plans["legacy_schema_probe"]["id"],
                        "database_plan": database_plans["legacy_schema_probe"],
                        "private_directory": str(
                            Path(runner["container_private_dir"]) / legacy.name
                        ),
                    },
                ),
                handoff,
                timeout_seconds=120,
            )
        legacy_app = _outside_ref(results["legacy"]["app_database_ref"], runner)
        base_request["legacy_app_database_ref"] = _inside_ref(legacy_app, runner)
        with report.enter("MATRIX"):
            matrix = root / "matrix"
            matrix.mkdir(mode=0o700)
            results["matrix"] = _runner_result(
                _runner_start(
                    handoff,
                    {
                        **base_request,
                        "action": "negative_matrix",
                        "database_id": database_plans["negative_matrix"]["id"],
                        "database_plan": database_plans["negative_matrix"],
                        "private_directory": str(
                            Path(runner["container_private_dir"]) / matrix.name
                        ),
                    },
                ),
                handoff,
                timeout_seconds=300,
            )
        with report.enter("PREPARE"):
            for kind in ("batch_twenty_items", "recover_single_item"):
                directory = root / kind
                directory.mkdir(mode=0o700)
                prepared = _runner_result(
                    _runner_start(
                        handoff,
                        {
                            **base_request,
                            "action": "prepare_case",
                            "revision": "0016",
                            "database_id": database_plans[kind]["id"],
                            "database_plan": database_plans[kind],
                            "case_kind": kind,
                            "private_directory": str(Path(runner["container_private_dir"]) / kind),
                            "origins": [handoff["web"]["api_origin"], handoff["web"]["web_origin"]],
                        },
                    ),
                    handoff,
                    timeout_seconds=300,
                )
                prepared["private_refs"] = {
                    k: _outside_ref(v, runner) for k, v in prepared["private_refs"].items()
                }
                continuation = _outside_ref(prepared["continuation_ref"], runner)
                prepared["continuation_ref"] = continuation
                results[kind] = prepared
                if kind == "recover_single_item":
                    current = {
                        **handoff,
                        **{
                            k: prepared[k]
                            for k in ("private_refs", "fixture", "baseline", "base_ro", "worker")
                        },
                        "t6": dict(
                            action="close",
                            expected_version=1,
                            request_phase="unprepared",
                            request_key=None,
                            reason="LAB synthetic acceptance",
                        ),
                    }
                    handoff_file = root / "handoff-single.json"
                    write_private(handoff_file, current)
                    current_ref = {
                        "path": str(handoff_file),
                        "sha256": digest(bound_bytes(handoff_file, private=True)),
                    }
        require(current is not None and current_ref is not None, "P4A_HANDOFF_REQUIRED")
        # 上方require为运行时合同；cast仅收窄静态类型，不补任何数据。
        current = cast(dict[str, Any], current)
        current_ref = cast(dict[str, str], current_ref)
        with report.enter("T6"):
            results["t6"] = consume_stage("t6", current, handoff_ref=current_ref)
        with report.enter("V2"):
            t6_ref = root / "C" / "recover_single_item" / "t6-result.json"
            ref = {"path": str(t6_ref), "sha256": digest(bound_bytes(t6_ref, private=True))}
            results["v2"] = _runner_result(
                _runner_start(
                    current,
                    {
                        "action": "project_v2",
                        "continuation_ref": _inside_ref(
                            results["recover_single_item"]["continuation_ref"], runner
                        ),
                        "t6_result_ref": _inside_ref(ref, runner),
                    },
                ),
                current,
                timeout_seconds=120,
            )
        with report.enter("RESTART"):
            results["restart"] = consume_stage("restart", current, handoff_ref=current_ref)
        with report.enter("PAGE"):
            results["page"] = consume_stage("page", current, handoff_ref=current_ref)
        with report.enter("COLLECT"):
            final = capture_bridge(
                "snapshot",
                current,
                handoff_ref=current_ref,
                phase="final-v2",
                request_key=results["t6"]["request_key"],
            )
            from commerceops.domain.commerce_values import facts_hash

            from tests.e2e.web import m1_acceptance_capture as capture

            fixture = current["fixture"]
            context = capture.CaptureContext(
                fixture["schema_revision"],
                fixture["organization_id"],
                fixture["shop_id"],
                fixture["task_id"],
                fixture["target_item_id"],
                fixture["principal_id"],
                fixture["web_identity_id"],
                fixture["auth_version"],
                tuple(fixture["checkpoint_threads"]),
                request_key=results["t6"]["request_key"],
                case_kind=fixture["case_kind"],
                expected_item_count=fixture["item_count"],
                expected_quantity_total=fixture["quantity_total"],
            )
            capture.validate_business(final, context, closed=True)
            witness = results["v2"]["value"]["witnesses"][0]
            capture.validate_base_readback(
                final,
                context,
                version=2,
                target_key=current["base_ro"]["pg_proof"]["target_key"],
                external_id=current["base_ro"]["pg_proof"]["external_id"],
                verification_mode=current["base_ro"]["pg_proof"]["verification_mode"],
                native_projection_hash=facts_hash(witness["request"]["projection"]),
            )
            require(
                capture.immutable_business(final) == current["baseline"]["core"]
                and capture.checkpoint_fingerprint(final) == current["baseline"]["checkpoints"],
                "P4A_BASELINE_CHANGED",
            )
            results["final_snapshot"] = final
    except Exception as error:
        failed_stage = next(
            (name for name, row in report.stages.items() if row["state"] == "FAILED"), "PREPARE"
        )
        results["failure"] = safe_failure(error, failed_stage)
    finally:
        try:
            with report.enter("STOP"):
                if (
                    resource["run_id"] in _APP_EPOCHS
                    and current is not None
                    and current_ref is not None
                ):
                    app_lifecycle("stop", current, handoff_ref=current_ref)
                stop_good = resource["run_id"] not in _APP_EPOCHS
                require(stop_good, "P4A_APP_STOP_FAILED")
                probe = _runner_result(
                    _runner_start(
                        handoff,
                        {
                            "action": "process_probe",
                            "private_root": resource["runner"]["container_private_dir"],
                        },
                    ),
                    handoff,
                    cleanup=True,
                )
                require(probe["owned_entry_processes"] == 0, "P4A_ENTRY_PROCESS_REMAINS")
                results["independent_process_probe"] = probe
        except Exception as error:
            results["stop_failure"] = safe_failure(error, "STOP")
        try:
            with report.enter("CLEANUP"):
                inventory = None
                try:
                    inventory = _runner_result(
                        _runner_start(
                            handoff,
                            {
                                "action": "database_inventory",
                                "run_id": resource["run_id"],
                                "owner_database_ref": _inside_ref(
                                    request["owner_database_ref"], resource["runner"]
                                ),
                                "databases": resource["databases"],
                                "private_root": resource["runner"]["container_private_dir"],
                            },
                        ),
                        handoff,
                        cleanup=True,
                    )
                    results["database_inventory"] = inventory
                except Exception as error:
                    results["database_inventory_failure"] = safe_failure(error, "CLEANUP")
                cleanup = resource_cleanup(handoff)
                cleanup["physical_cleanup_verified"] = cleanup["verified"]
                cleanup["database_inventory_verified"] = (
                    inventory is not None
                    and inventory["value"]["verified"] is True
                    and inventory["value"]["inventory_connection_closed"] is True
                )
                cleanup["verified"] = cleanup["verified"] and cleanup["database_inventory_verified"]
                require(cleanup["verified"], "P4A_RESOURCE_CLEANUP_FAILED")
        except Exception as error:
            results["cleanup_failure"] = safe_failure(error, "CLEANUP")
    return {
        **report.terminal(
            cleanup=cleanup.get("verified") is True,
            reaped=stop_good and cleanup.get("all_containers_reaped") is True,
            owned=owned,
        ),
        "evidence": results,
        "resource_cleanup": cleanup,
        "real_platform_pass": False,
        "preparation_only": True,
    }


# 原键非消费准入：只读SQL与确定性谓词，最终原native claim仍完整重核。
def _ro_cap_limits_native(caps: Any, cap_upper: Any) -> bool:
    return all((1 <= cap <= cap_upper[method] for method, cap in caps.items()))


def _ro_low_role_predicate(role: Any) -> bool:
    return role["role"] == "commerceops_app" and (
        not any(role[key] for key in role if key != "role")
    )


def _ro_task_plan_approval_predicate(
    task: Any, a: Any, e: Any, pl: Any, r: Any, projection: Any
) -> bool:
    return bool(
        task
        and a
        and e
        and pl
        and (task["state"] == "completed")
        and (task["version"] == r.task_version == 4)
        and (task["kind"] == "inventory_replenishment")
        and (task["workflow_version"] == "p3-inventory-replenishment-v1")
        and (task["active_plan_id"] == r.plan_id == a["plan_id"] == e["plan_id"])
        and (pl["version"] == a["plan_version"] == r.plan_version)
        and (pl["plan_hash"] == a["plan_hash"] == e["plan_hash"] == r.plan_hash)
        and (pl["status"] == "executed")
        and (a["status"] == "approved")
        and (a["consumed_at"] is not None)
        and (a["decision_id"] == r.decision_id)
        and (a["decision_action"] in ("approve", "approve_with_assumptions"))
        and (e["status"] == "completed")
        and (e["item_ids"] == [projection.item_id])
    )


def _ro_current_A_identity_predicate(
    receipt: Any,
    identity: Any,
    actor: Any,
    grants: Any,
    scopes: Any,
    task: Any,
    r: Any,
    settings: Any,
    receipt_hash: Any,
) -> bool:
    return bool(
        receipt_hash(receipt) == r.receipt_hash
        and identity["provider"] == "feishu"
        and (identity["principal_id"] == task["requester_id"])
        and (
            (identity["app_id"], identity["tenant_key"])
            == (settings.app_id, settings.tenant_key)
            == (receipt["app_id"], receipt["tenant_key"])
        )
        and (identity["external_subject"] in settings.allowed_open_ids)
        and actor["enabled"]
        and (actor["auth_version"] == r.operator_auth_version)
        and ({"operator", "approver"} <= set(actor["roles"]))
        and ({grant["role"] for grant in grants if grant["enabled"]} == {"operator", "approver"})
        and (len(scopes) == 1)
        and scopes[0]["enabled"]
        and (task["normalized_request"]["identity_id"] == str(receipt["identity_id"]))
        and (receipt["sanitized_payload"]["principal_id"] == str(task["requester_id"]))
        and (receipt["result"]["task_id"] == str(r.task_id))
    )


def _ro_chat_scope_predicate(
    conversation: Any, task: Any, receipt: Any, org: Any, settings: Any
) -> bool:
    return bool(
        conversation["organization_id"] == org
        and conversation["actor_id"] == task["requester_id"]
        and (conversation["channel"] == "feishu")
        and (receipt["sanitized_payload"]["chat_type"] in ("p2p", "group"))
        and (
            receipt["sanitized_payload"]["chat_type"] == "p2p"
            or conversation["chat_id"] in settings.allowed_group_chat_ids
        )
    )


def _ro_current_approver_predicate(approver: Any, a: Any, r: Any, settings: Any) -> bool:
    return bool(
        len(approver) == 1
        and approver[0]["enabled"]
        and approver[0]["scope_enabled"]
        and approver[0]["grant_enabled"]
        and ("approver" in approver[0]["roles"])
        and (approver[0]["provider"] == "feishu")
        and (approver[0]["auth_version"] == a["decided_auth_version"] == r.approver_auth_version)
        and (a["decided_by"] in a["eligible_principal_ids"])
        and (
            (approver[0]["app_id"], approver[0]["tenant_key"])
            == (settings.app_id, settings.tenant_key)
        )
        and (approver[0]["external_subject"] in settings.allowed_open_ids)
    )


def _ro_gateway_claim_predicate(claim: Any, expected_hash: Any, facts_hash: Any) -> bool:
    return bool(claim and facts_hash(claim["after_state"]) == expected_hash)


def _ro_gateway_scope_predicate(
    origin: Any, origin_gw: Any, org: Any, shop: Any, task: Any, receipt: Any, claimed_state: Any
) -> bool:
    return bool(
        origin["after_state"] == claimed_state(origin_gw)
        and (origin_gw.organization_id, origin_gw.shop_id) == (org, shop)
        and (origin_gw.parameters.model_dump(mode="json") == task["parameters"])
        and (origin["occurred_at"] <= receipt["receipt_at"] < origin_gw.expires_at)
    )


def _ro_sender_gateway_scope_predicate(
    sender: Any,
    sender_gw: Any,
    org: Any,
    shop: Any,
    origin_gw: Any,
    origin_end: Any,
    claimed_state: Any,
) -> bool:
    return bool(
        sender["after_state"] == claimed_state(sender_gw)
        and (sender_gw.organization_id, sender_gw.shop_id) == (org, shop)
        and (sender_gw.parameters == origin_gw.parameters)
        and (sender_gw.max_workflows == 0)
        and (origin_end["occurred_at"] < sender["occurred_at"])
    )


def _ro_lifecycle_unique_time_predicate(
    starts: Any, terms: Any, now: Any, full_process_receipt: Any
) -> bool:
    return bool(
        len(starts) == len(terms) == 1
        and full_process_receipt(starts[0]["after_state"])
        and (starts[0]["occurred_at"] <= terms[0]["occurred_at"] < now)
    )


def _ro_gateway_reap_predicate(starts: Any, terms: Any) -> bool:
    return bool(
        terms[0]["after_state"].get("process") == starts[0]["after_state"]
        and terms[0]["after_state"].get("child_reaped") is True
        and (type(terms[0]["after_state"].get("child_exit")) is int)
    )


def _ro_worker_stop_predicate(
    starts: Any, stops: Any, terms: Any, full_process_receipt: Any
) -> bool:
    return bool(
        len(stops) == 1
        and stops[0]["after_state"] == starts[0]["after_state"]
        and full_process_receipt(terms[0]["after_state"])
        and bool(terms[0]["reason"])
        and all(
            terms[0]["after_state"][key] == starts[0]["after_state"][key]
            for key in ("host", "pid_namespace")
        )
        and (starts[0]["occurred_at"] <= stops[0]["occurred_at"] <= terms[0]["occurred_at"])
    )


def _ro_process_absence_check(process: Any, require_process_absent: Any) -> bool:
    require_process_absent(process)
    return True


def _ro_sender_SDK_claim_predicate(sdk: Any, claim: Any, r: Any, sdk_window_hash: Any) -> bool:
    return bool(sdk and claim and (sdk_window_hash(sdk) == r.original_sdk_window_hash))


def _ro_sender_auth_predicate(auth: Any, sdk: Any, worker_end: Any) -> bool:
    return bool(
        len(auth) == 1
        and (auth[0]["status"], auth[0]["http_status"], auth[0]["provider_code"])
        == ("returned", 200, 0)
        and (sdk["created_at"] <= auth[0]["started_at"] <= worker_end["occurred_at"])
    )


def _ro_fixed_native_sender_predicates(
    sw: Any,
    projection: Any,
    sdk: Any,
    sender_gw: Any,
    org: Any,
    shop: Any,
    r: Any,
    a: Any,
    task: Any,
    sender: Any,
    sender_start: Any,
    worker_start: Any,
    claim: Any,
    worker_end: Any,
    sender_end: Any,
    FIRST_CREATE_CAPS: Any,
    task_binding_hash: Any,
    approval_binding_hash: Any,
) -> Any:
    wf = sw.workflow_recovery
    result = {}
    result["SENDER_FIXED_PREDICATE_01"] = bool(sw.profile == "approved_first_create")
    if not result["SENDER_FIXED_PREDICATE_01"]:
        return result
    result["SENDER_FIXED_PREDICATE_02"] = bool(sw.enabled)
    if not result["SENDER_FIXED_PREDICATE_02"]:
        return result
    result["SENDER_FIXED_PREDICATE_03"] = bool(sw.first_create == projection)
    if not result["SENDER_FIXED_PREDICATE_03"]:
        return result
    result["SENDER_FIXED_PREDICATE_04"] = bool(sw.window_id == sdk["id"])
    if not result["SENDER_FIXED_PREDICATE_04"]:
        return result
    result["SENDER_FIXED_PREDICATE_05"] = bool(sw.gateway_window_id == sender_gw.window_id)
    if not result["SENDER_FIXED_PREDICATE_05"]:
        return result
    result["SENDER_FIXED_PREDICATE_06"] = bool((sw.organization_id, sw.shop_id) == (org, shop))
    if not result["SENDER_FIXED_PREDICATE_06"]:
        return result
    result["SENDER_FIXED_PREDICATE_07"] = bool(sw.task_ids == frozenset({r.task_id}))
    if not result["SENDER_FIXED_PREDICATE_07"]:
        return result
    result["SENDER_FIXED_PREDICATE_08"] = bool(sw.expires_at == sdk["expires_at"])
    if not result["SENDER_FIXED_PREDICATE_08"]:
        return result
    result["SENDER_FIXED_PREDICATE_09"] = bool(sw.caps == sdk["method_caps"])
    if not result["SENDER_FIXED_PREDICATE_09"]:
        return result
    result["SENDER_FIXED_PREDICATE_10"] = bool(not set(sw.caps) - set(FIRST_CREATE_CAPS))
    if not result["SENDER_FIXED_PREDICATE_10"]:
        return result
    result["SENDER_FIXED_PREDICATE_11"] = bool(_ro_cap_limits_native(sw.caps, FIRST_CREATE_CAPS))
    if not result["SENDER_FIXED_PREDICATE_11"]:
        return result
    result["SENDER_FIXED_PREDICATE_12"] = bool(wf is not None)
    if not result["SENDER_FIXED_PREDICATE_12"]:
        return result
    result["SENDER_FIXED_PREDICATE_13"] = bool(wf.worker_window_id == sw.window_id)
    if not result["SENDER_FIXED_PREDICATE_13"]:
        return result
    result["SENDER_FIXED_PREDICATE_14"] = bool(wf.gateway_window_id == sw.gateway_window_id)
    if not result["SENDER_FIXED_PREDICATE_14"]:
        return result
    result["SENDER_FIXED_PREDICATE_15"] = bool(wf.expires_at == sw.expires_at)
    if not result["SENDER_FIXED_PREDICATE_15"]:
        return result
    result["SENDER_FIXED_PREDICATE_16"] = bool(wf.worker_owner != r.worker_owner)
    if not result["SENDER_FIXED_PREDICATE_16"]:
        return result
    result["SENDER_FIXED_PREDICATE_17"] = bool(wf.original_gateway_id == r.original_gateway_id)
    if not result["SENDER_FIXED_PREDICATE_17"]:
        return result
    result["SENDER_FIXED_PREDICATE_18"] = bool(wf.original_gateway_hash == r.original_gateway_hash)
    if not result["SENDER_FIXED_PREDICATE_18"]:
        return result
    result["SENDER_FIXED_PREDICATE_19"] = bool(
        wf.gateway_termination_id == r.gateway_termination_id
    )
    if not result["SENDER_FIXED_PREDICATE_19"]:
        return result
    result["SENDER_FIXED_PREDICATE_20"] = bool(wf.task_id == r.task_id)
    if not result["SENDER_FIXED_PREDICATE_20"]:
        return result
    result["SENDER_FIXED_PREDICATE_21"] = bool(wf.task_version == r.task_version)
    if not result["SENDER_FIXED_PREDICATE_21"]:
        return result
    result["SENDER_FIXED_PREDICATE_22"] = bool(wf.inbox_id == r.inbox_id)
    if not result["SENDER_FIXED_PREDICATE_22"]:
        return result
    result["SENDER_FIXED_PREDICATE_23"] = bool(wf.receipt_hash == r.receipt_hash)
    if not result["SENDER_FIXED_PREDICATE_23"]:
        return result
    result["SENDER_FIXED_PREDICATE_24"] = bool(wf.approval_id == r.approval_id)
    if not result["SENDER_FIXED_PREDICATE_24"]:
        return result
    result["SENDER_FIXED_PREDICATE_25"] = bool(wf.decision_id == r.decision_id)
    if not result["SENDER_FIXED_PREDICATE_25"]:
        return result
    result["SENDER_FIXED_PREDICATE_26"] = bool(
        wf.decision_payload_hash == a["decision_payload_hash"]
    )
    if not result["SENDER_FIXED_PREDICATE_26"]:
        return result
    result["SENDER_FIXED_PREDICATE_27"] = bool(wf.execution_id == r.execution_id)
    if not result["SENDER_FIXED_PREDICATE_27"]:
        return result
    result["SENDER_FIXED_PREDICATE_28"] = bool(wf.operator_auth_version == r.operator_auth_version)
    if not result["SENDER_FIXED_PREDICATE_28"]:
        return result
    result["SENDER_FIXED_PREDICATE_29"] = bool(wf.target_key == r.target_key)
    if not result["SENDER_FIXED_PREDICATE_29"]:
        return result
    result["SENDER_FIXED_PREDICATE_30"] = bool(wf.task_binding_hash == task_binding_hash(task))
    if not result["SENDER_FIXED_PREDICATE_30"]:
        return result
    result["SENDER_FIXED_PREDICATE_31"] = bool(wf.approval_binding_hash == approval_binding_hash(a))
    if not result["SENDER_FIXED_PREDICATE_31"]:
        return result
    result["SENDER_FIXED_PREDICATE_32"] = bool(sdk["configured_enabled"])
    if not result["SENDER_FIXED_PREDICATE_32"]:
        return result
    result["SENDER_FIXED_PREDICATE_33"] = bool(sdk["verification_mode"] == "controlled_sdk")
    if not result["SENDER_FIXED_PREDICATE_33"]:
        return result
    result["SENDER_FIXED_PREDICATE_34"] = bool(
        (sdk["organization_id"], sdk["shop_id"]) == (org, shop)
    )
    if not result["SENDER_FIXED_PREDICATE_34"]:
        return result
    result["SENDER_FIXED_PREDICATE_35"] = bool(
        sender["occurred_at"]
        <= sender_start["occurred_at"]
        <= worker_start["occurred_at"]
        <= claim["occurred_at"]
        <= sdk["created_at"]
        <= worker_end["occurred_at"]
    )
    if not result["SENDER_FIXED_PREDICATE_35"]:
        return result
    result["SENDER_FIXED_PREDICATE_36"] = bool(sdk["created_at"] < sender_end["occurred_at"])
    if not result["SENDER_FIXED_PREDICATE_36"]:
        return result
    result["SENDER_FIXED_PREDICATE_37"] = bool(
        sdk["created_at"] < sdk["expires_at"] <= sender_gw.expires_at
    )
    if not result["SENDER_FIXED_PREDICATE_37"]:
        return result
    return result


def _ro_actor_sender(db: Any, settings: Any, window: Any) -> None:
    from commerceops.application.feishu_business.gateway_window import GatewayWindow
    from commerceops.application.feishu_business.worker_window import (
        FIRST_CREATE_CAPS,
        ControlledWorkerWindow,
    )
    from commerceops.domain.commerce_values import facts_hash
    from commerceops.infrastructure.feishu_gateway_window import claimed_state
    from commerceops.infrastructure.feishu_outbox_recovery import (
        full_process_receipt,
        receipt_hash,
        sdk_window_hash,
    )
    from commerceops.infrastructure.feishu_workflow_recovery import (
        approval_binding_hash,
        task_binding_hash,
    )
    from commerceops.infrastructure.worker_lock import require_process_absent

    r = window.recovery
    org, shop = (window.organization_id, window.shop_id)
    p = r.projections[0]
    role = db.execute(
        "SELECT current_user AS "
        "role,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles "
        "WHERE rolname=current_user"
    ).fetchone()
    require(_ro_low_role_predicate(role), "P4A_" + "BIND_CURRENT_LOW_ROLE")
    task = db.execute(
        (
            "SELECT t.*,s.source_task_id,s.parameters,s.config_version FROM "
            "business.business_tasks t JOIN business.p3_task_sources s ON s.task_id=t.id WHERE "
            "t.id=%s AND t.organization_id=%s AND t.shop_id=%s"
        ),
        (r.task_id, org, shop),
    ).fetchone()
    a = db.execute(
        "SELECT * FROM business.approvals WHERE id=%s AND task_id=%s", (r.approval_id, r.task_id)
    ).fetchone()
    e = db.execute(
        "SELECT * FROM business.executions WHERE id=%s AND task_id=%s", (r.execution_id, r.task_id)
    ).fetchone()
    pl = db.execute(
        "SELECT * FROM business.replenishment_plans WHERE id=%s", (r.plan_id,)
    ).fetchone()
    require(
        _ro_task_plan_approval_predicate(task, a, e, pl, r, p),
        "P4A_" + "BIND_CURRENT_TASK_PLAN_APPROVAL",
    )
    receipt = db.execute(
        (
            "SELECT i.*,r.inbox_id,r.identity_id,r.result,r.created_at AS receipt_at FROM "
            "business.inbox_events i JOIN business.p4_inbox_receipts r ON r.inbox_id=i.id WHERE "
            "i.id=%s AND i.task_id=%s AND i.organization_id=%s AND i.shop_id=%s AND "
            "i.source='feishu_business'"
        ),
        (r.inbox_id, r.task_id, org, shop),
    ).fetchone()
    identity = db.execute(
        "SELECT * FROM business.identities WHERE id=%s", (receipt["identity_id"],)
    ).fetchone()
    actor = db.execute(
        "SELECT * FROM business.principals WHERE id=%s AND organization_id=%s",
        (task["requester_id"], org),
    ).fetchone()
    grants = db.execute(
        (
            "SELECT role,enabled FROM business.principal_role_shop_grants WHERE principal_id=%s "
            "AND organization_id=%s AND shop_id=%s"
        ),
        (task["requester_id"], org, shop),
    ).fetchall()
    scopes = db.execute(
        (
            "SELECT enabled FROM business.principal_shop_scopes WHERE principal_id=%s AND "
            "organization_id=%s AND shop_id=%s"
        ),
        (task["requester_id"], org, shop),
    ).fetchall()
    require(
        _ro_current_A_identity_predicate(
            receipt, identity, actor, grants, scopes, task, r, settings, receipt_hash
        ),
        "P4A_" + "BIND_CURRENT_A_SCOPE_AUTH",
    )
    conversation = db.execute(
        "SELECT * FROM business.conversations WHERE id=%s", (task["conversation_id"],)
    ).fetchone()
    require(
        _ro_chat_scope_predicate(conversation, task, receipt, org, settings),
        "P4A_" + "BIND_CURRENT_CHAT_SCOPE",
    )
    approver = db.execute(
        (
            "SELECT "
            "p.enabled,p.roles,p.auth_version,i.provider,i.principal_id,i.app_id,i.tenant_key,i.external_subject,s.enabled"
            " AS scope_enabled,g.enabled AS grant_enabled FROM business.principals p JOIN "
            "business.identities i ON i.principal_id=p.id JOIN business.principal_shop_scopes s "
            "ON s.principal_id=p.id AND s.organization_id=p.organization_id AND s.shop_id=%s JOIN"
            " business.principal_role_shop_grants g ON g.principal_id=p.id AND "
            "g.organization_id=p.organization_id AND g.shop_id=s.shop_id AND g.role='approver' "
            "WHERE p.id=%s AND p.organization_id=%s AND i.id=%s"
        ),
        (shop, a["decided_by"], org, a["decided_identity_id"]),
    ).fetchall()
    require(
        _ro_current_approver_predicate(approver, a, r, settings), "P4A_" + "BIND_CURRENT_APPROVER"
    )

    def lifecycle(source: str, kind: str, entity: Any, term_id: Any, label: str) -> tuple[Any, Any]:
        rows = db.execute(
            (
                "SELECT * FROM business.audit_events WHERE organization_id=%s AND source=%s AND "
                "entity_type=%s AND entity_id=%s AND action IN "
                "('started','stopped','termination_confirmed')"
            ),
            (org, source, kind, str(entity)),
        ).fetchall()
        starts = [x for x in rows if x["action"] == "started"]
        terms = [x for x in rows if x["action"] == "termination_confirmed" and x["id"] == term_id]
        require(
            _ro_lifecycle_unique_time_predicate(
                starts, terms, datetime.now(UTC), full_process_receipt
            ),
            "P4A_" + (label + "_PAIR_TIME"),
        )
        require(
            _ro_process_absence_check(starts[0]["after_state"], require_process_absent),
            "P4A_" + (label + "_OS_ABSENT"),
        )
        if source == "feishu_gateway":
            require(_ro_gateway_reap_predicate(starts, terms), "P4A_" + (label + "_REAPED"))
        else:
            stops = [x for x in rows if x["action"] == "stopped"]
            require(
                _ro_worker_stop_predicate(starts, stops, terms, full_process_receipt),
                "P4A_" + (label + "_STOPPED"),
            )
            require(
                _ro_process_absence_check(terms[0]["after_state"], require_process_absent),
                "P4A_" + (label + "_PARENT_ABSENT"),
            )
        return (starts[0], terms[0])

    origin = db.execute(
        (
            "SELECT * FROM business.audit_events WHERE id=%s AND organization_id=%s AND "
            "source='feishu_gateway' AND action='gateway_start_claimed' AND "
            "entity_type='gateway_window'"
        ),
        (r.original_gateway_id, org),
    ).fetchone()
    require(
        _ro_gateway_claim_predicate(origin, r.original_gateway_hash, facts_hash),
        "P4A_" + "BIND_ORIGIN_HASH",
    )
    ogw = GatewayWindow.model_validate_json(
        json.dumps({k: origin["after_state"].get(k) for k in GatewayWindow.model_fields})
    )
    require(
        _ro_gateway_scope_predicate(origin, ogw, org, shop, task, receipt, claimed_state),
        "P4A_" + "BIND_ORIGIN_SCOPE",
    )
    _, origin_end = lifecycle(
        "feishu_gateway",
        "gateway_runtime",
        r.original_gateway_id,
        r.gateway_termination_id,
        "BIND_ORIGIN",
    )
    sender = db.execute(
        (
            "SELECT * FROM business.audit_events WHERE id=%s AND organization_id=%s AND "
            "source='feishu_gateway' AND action='gateway_start_claimed' AND "
            "entity_type='gateway_window'"
        ),
        (r.sender_gateway.gateway_id, org),
    ).fetchone()
    require(
        _ro_gateway_claim_predicate(sender, r.sender_gateway.gateway_hash, facts_hash),
        "P4A_" + "BIND_SENDER_HASH",
    )
    sgw = GatewayWindow.model_validate_json(
        json.dumps({k: sender["after_state"].get(k) for k in GatewayWindow.model_fields})
    )
    require(
        _ro_sender_gateway_scope_predicate(sender, sgw, org, shop, ogw, origin_end, claimed_state),
        "P4A_" + "BIND_SENDER_SCOPE",
    )
    sender_start, sender_end = lifecycle(
        "feishu_gateway",
        "gateway_runtime",
        r.sender_gateway.gateway_id,
        r.sender_gateway.termination_id,
        "BIND_SENDER_GATEWAY",
    )
    worker_start, worker_end = lifecycle(
        "worker", "worker_runtime", r.worker_owner, r.worker_termination_id, "BIND_SENDER_WORKER"
    )
    sdk = db.execute(
        "SELECT * FROM business.p4_sdk_windows WHERE id=%s", (r.original_sdk_window_id,)
    ).fetchone()
    claim = db.execute(
        (
            "SELECT * FROM business.audit_events WHERE id=%s AND organization_id=%s AND "
            "source='feishu_recovery' AND action='approved_workflow_claimed' AND "
            "entity_type='sdk_window'"
        ),
        (r.original_sdk_window_id, org),
    ).fetchone()
    require(
        _ro_sender_SDK_claim_predicate(sdk, claim, r, sdk_window_hash),
        "P4A_" + "BIND_SENDER_SDK_HASH",
    )
    sw = ControlledWorkerWindow.model_validate_json(json.dumps(claim["after_state"]))
    values = _ro_fixed_native_sender_predicates(
        sw,
        p,
        sdk,
        sgw,
        org,
        shop,
        r,
        a,
        task,
        sender,
        sender_start,
        worker_start,
        claim,
        worker_end,
        sender_end,
        FIRST_CREATE_CAPS,
        task_binding_hash,
        approval_binding_hash,
    )
    for label, value in values.items():
        require(value, "P4A_" + label)
    require(len(values) == 37, "P4A_" + "BIND_ALL_37_SENDER_PREDICATES")
    auth = db.execute(
        (
            "SELECT * FROM business.p4_sdk_calls WHERE window_id=%s AND subject_id=%s AND task_id"
            " IS NULL AND scope_kind='preflight' AND "
            "method='auth.v3.tenant_access_token.internal'"
        ),
        (sdk["id"], sdk["id"]),
    ).fetchall()
    require(_ro_sender_auth_predicate(auth, sdk, worker_end), "P4A_" + "BIND_SENDER_AUTH_LEDGER")


def _ro_delivery_preflight(db: Any, window: Any) -> None:
    from commerceops.domain.commerce_values import facts_hash
    from commerceops.infrastructure.feishu_outbox_recovery import full_process_receipt
    from commerceops.infrastructure.worker_lock import require_process_absent

    recovery = window.recovery
    projection = recovery.projections[0]
    recheck = recovery.explicit_ro_recheck
    rows = db.execute(
        (
            "SELECT d.*,o.request_hash,o.payload AS original_payload,o.provider_idempotency_key,"
            "\n            t.state AS task_state,t.version AS task_version,e.status AS "
            "execution_status,\n            a.status AS approval_status,a.consumed_at,i.version AS"
            " current_version,\n            i.status AS item_status FROM "
            "business.p4_base_deliveries d\n            JOIN business.outbox o ON o.id=d.outbox_id"
            "\n            JOIN business.business_tasks t ON t.id=d.task_id\n            JOIN "
            "business.replenishment_items i ON i.id=d.item_id\n            JOIN "
            "business.executions e ON e.id=i.execution_id\n            JOIN business.approvals a "
            "ON a.id=e.approval_id\n            WHERE d.outbox_id=%s AND d.task_id=%s AND "
            "d.organization_id=%s AND d.shop_id=%s"
        ),
        (projection.outbox_id, recovery.task_id, window.organization_id, window.shop_id),
    ).fetchall()
    require(len(rows) == 1, "P4A_RO_ORIGINAL_BINDING")
    row = rows[0]
    require(
        row["status"] == "unknown"
        and row["attempts"] == (2 if recheck is None else 3)
        and (
            row["claimed_by"]
            == str(recovery.worker_owner if recheck is None else recheck.reader_owner)
        )
        and (
            recheck is None
            or (row["last_operation"] == "reconcile" and row["last_error"] == "INCOMPLETE_READBACK")
        )
        and (row["external_id"] is None)
        and (row["version"] == 1)
        and (row["item_id"] == projection.item_id)
        and (row["current_version"] == 1)
        and (row["item_status"] == "open")
        and (row["task_state"] == "completed")
        and (row["task_version"] == recovery.task_version)
        and (row["execution_status"] == "completed")
        and (row["approval_status"] == "approved")
        and (row["consumed_at"] is not None)
        and (row["client_token"] == row["provider_idempotency_key"] == projection.client_token)
        and (row["request_hash"] == facts_hash(row["original_payload"]) == projection.request_hash)
        and (row["projection_hash"] == facts_hash(row["projection"]) == projection.projection_hash),
        "P4A_RO_ORIGINAL_BINDING",
    )
    history = db.execute(
        (
            "SELECT window_id,status,http_status,provider_code FROM business.p4_sdk_calls"
            "\n            WHERE subject_id=%s AND method='bitable.v1.app_table_record.create'"
        ),
        (projection.outbox_id,),
    ).fetchall()
    anchor = db.execute(
        "SELECT count(*) AS n FROM business.p4_base_links WHERE item_id=%s", (projection.item_id,)
    ).fetchone()["n"]
    require(
        history
        == [
            {
                "window_id": recovery.original_sdk_window_id,
                "status": "returned",
                "http_status": 200,
                "provider_code": 0,
            }
        ]
        and anchor == 0,
        "P4A_RO_ORIGINAL_BINDING",
    )
    ends = db.execute(
        (
            "SELECT action,after_state,reason FROM business.audit_events WHERE organization_id=%s"
            "\n            AND entity_id=%s AND source='worker' AND entity_type='worker_runtime'"
            "\n            AND action IN ('started','stopped','termination_confirmed')"
        ),
        (window.organization_id, str(recovery.worker_owner)),
    ).fetchall()
    starts = [e for e in ends if e["action"] == "started"]
    stops = [e for e in ends if e["action"] == "stopped"]
    terms = [e for e in ends if e["action"] == "termination_confirmed"]
    require(
        len(starts) == len(stops) == len(terms) == 1
        and starts[0]["after_state"] == stops[0]["after_state"]
        and full_process_receipt(starts[0]["after_state"])
        and full_process_receipt(terms[0]["after_state"])
        and bool(terms[0]["reason"])
        and all(
            starts[0]["after_state"][key] == terms[0]["after_state"][key]
            for key in ("host", "pid_namespace")
        ),
        "P4A_RO_ORIGINAL_BINDING",
    )
    require_process_absent(starts[0]["after_state"])
    if recheck is not None:
        from commerceops.infrastructure.feishu_outbox_recovery import recheck_audit_id

        occupied = db.execute(
            "SELECT count(*) AS n FROM business.audit_events WHERE id=ANY(%s)",
            (
                [
                    recheck_audit_id(projection.outbox_id),
                    recheck_audit_id(projection.outbox_id, dispatched=True),
                ],
            ),
        ).fetchone()["n"]
        require(occupied == 0, "P4A_RO_ONCE_SPENT")


def _ro_reference(path: Path) -> dict[str, str]:
    return {"path": str(path.absolute()), "sha256": digest(bound_bytes(path, private=True))}


def _ro_schema(owner: Any, app: Any, revision: str) -> dict[str, Any]:
    """原库只读元数据；不复用schema_case的建库/迁移路径。"""
    from commerceops.infrastructure.database import connect

    require(
        revision in ("0015", "0016")
        and owner.user == "commerceops_owner"
        and app.user == "commerceops_app"
        and app.runtime_password_file is None
        and (owner.host, owner.port, owner.name) == (app.host, app.port, app.name),
        "P4A_RO_DATABASE_BINDING",
    )
    with connect(owner) as db:
        db.execute("SET TRANSACTION READ ONLY")
        db.execute("SET LOCAL statement_timeout='5s'")
        actual = QUERIES["REVISION"].execute(db, revision=revision, role="owner")
        tables = QUERIES["TABLES"].execute(db, revision=revision, role="owner")
        columns = QUERIES["COLUMNS"].execute(db, revision=revision, role="owner")
    expected = {"business." + t for t in BUSINESS_0015}
    expected |= {"checkpoints." + t for t in (*CP_DATA_TABLES, "checkpoint_migrations")}
    if revision == "0016":
        expected.add("business.p4_clarification_requests")
    require(
        actual
        == [
            {
                "revision": {
                    "0015": "0015_p4_read_replies",
                    "0016": "0016_p4_clarification_requests",
                }[revision]
            }
        ]
        and {r["schema"] + "." + r["name"] for r in tables} == expected,
        "P4A_SCHEMA_REVISION",
    )
    with connect(app) as db:
        db.execute("SET TRANSACTION READ ONLY")
        role = db.execute(
            "SELECT current_user::text AS role,rolsuper,rolcreatedb,rolcreaterole,"
            "rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user"
        ).fetchone()
        require(role is not None and _ro_low_role_predicate(role), "P4A_ROLE")
        owners = db.execute(
            "SELECT count(*) AS n FROM pg_stat_activity "
            "WHERE datname=current_database() AND usename='commerceops_owner'"
        ).fetchone()
        require(owners is not None and owners["n"] == 0, "P4A_RO_OWNER_OPEN")
    return dict(
        revision=revision,
        exact_table_count=len(expected),
        columns_sha256=digest(canonical(columns)),
        owner_connection_closed=True,
        app_role=role,
    )


def _ro_prepare(request: Mapping[str, Any]) -> dict[str, Any]:
    """从实际原PG派生reader；所有连接READ ONLY，绝不消费once。"""
    import asyncio

    from commerceops.adapters.feishu.business_config import BusinessSettings
    from commerceops.application.feishu_business.worker_window import (
        READONLY_RECOVERY_CAPS,
        ControlledWorkerWindow,
    )
    from commerceops.domain.commerce_values import facts_hash
    from commerceops.infrastructure.database import DatabaseSettings, connect
    from commerceops.infrastructure.feishu_outbox_recovery import sdk_window_hash, trusted_reader
    from commerceops.infrastructure.web_config import WebConfig
    from commerceops.infrastructure.worker_lock import open_async

    refs = request["private_refs"]
    settings = BusinessSettings.model_validate_json(private_ref(refs["business"]))
    private_ref(refs["web_config"])
    require(settings.web_config_file == Path(refs["web_config"]["path"]), "P4A_CONFIG_BINDING")
    web = WebConfig.from_file(settings.web_config_file)
    owner = DatabaseSettings.model_validate_json(private_ref(refs["owner_database"]))
    schema = _ro_schema(owner, web.database, request["revision"])
    template = ControlledWorkerWindow.model_validate_json(private_ref(refs["template"]))
    r = template.recovery
    require(
        not template.enabled
        and template.profile == "approved_outbox"
        and r is not None
        and r.explicit_ro_recheck is None
        and r.sender_gateway is not None
        and template.caps == dict(READONLY_RECOVERY_CAPS)
        and template.workflow_recovery is None
        and template.first_create is None
        and len(r.projections) == 1
        and r.projections[0].version == 1
        and (template.organization_id, template.shop_id)
        == (settings.organization_id, settings.shop_id)
        and r.target_key == settings.base_target_key
        and not settings.f02_enabled
        and not settings.external_sender_enabled,
        "P4A_RO_TEMPLATE",
    )
    if r is None:
        raise AcceptanceFailure("P4A_RO_TEMPLATE")
    with connect(web.database) as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        db.execute("SET LOCAL statement_timeout='5s'")
        delivery = db.execute(
            "SELECT * FROM business.p4_base_deliveries WHERE outbox_id=%s "
            "AND task_id=%s AND organization_id=%s AND shop_id=%s",
            (r.projections[0].outbox_id, r.task_id, template.organization_id, template.shop_id),
        ).fetchone()
        require(
            delivery is not None
            and delivery["status"] == "unknown"
            and delivery["attempts"] == 3
            and delivery["last_operation"] == "reconcile"
            and delivery["last_error"] == "INCOMPLETE_READBACK"
            and delivery["external_id"] is None,
            "P4A_RO_LAST_READER",
        )
        if delivery is None:
            raise AcceptanceFailure("P4A_RO_LAST_READER")
        runs = db.execute(
            "SELECT id,action,occurred_at FROM business.audit_events "
            "WHERE organization_id=%s AND source='worker' "
            "AND entity_type='worker_runtime' AND entity_id=%s",
            (template.organization_id, delivery["claimed_by"]),
        ).fetchall()
        starts = [x for x in runs if x["action"] == "started"]
        stops = [x for x in runs if x["action"] == "stopped"]
        ends = [x for x in runs if x["action"] == "termination_confirmed"]
        require(len(starts) == len(stops) == len(ends) == 1, "P4A_RO_READER_LIFECYCLE")
        claims = db.execute(
            "SELECT id,after_state FROM business.audit_events WHERE "
            "organization_id=%s AND task_id=%s AND source='feishu_recovery' "
            "AND action='approved_outbox_claimed' AND entity_type='sdk_window' "
            "AND occurred_at BETWEEN %s AND %s",
            (
                template.organization_id,
                r.task_id,
                starts[0]["occurred_at"],
                stops[0]["occurred_at"],
            ),
        ).fetchall()
        require(len(claims) == 1, "P4A_RO_READER_CLAIM")
        prior = ControlledWorkerWindow.model_validate_json(json.dumps(claims[0]["after_state"]))
        require(
            prior.window_id == claims[0]["id"]
            and prior.recovery is not None
            and prior.recovery.explicit_ro_recheck is None,
            "P4A_RO_READER_CLAIM",
        )
        sdk = db.execute(
            "SELECT * FROM business.p4_sdk_windows WHERE id=%s", (prior.window_id,)
        ).fetchone()
        gw = db.execute(
            "SELECT after_state FROM business.audit_events WHERE id=%s "
            "AND organization_id=%s AND source='feishu_gateway' "
            "AND action='gateway_start_claimed' AND entity_type='gateway_window'",
            (prior.gateway_window_id, template.organization_id),
        ).fetchone()
        terms = db.execute(
            "SELECT id FROM business.audit_events WHERE organization_id=%s "
            "AND entity_id=%s AND source='feishu_gateway' "
            "AND entity_type='gateway_runtime' AND action='termination_confirmed'",
            (template.organization_id, str(prior.gateway_window_id)),
        ).fetchall()
        require(sdk is not None and gw is not None and len(terms) == 1, "P4A_RO_READER_INPUT")
        if sdk is None or gw is None:
            raise AcceptanceFailure("P4A_RO_READER_INPUT")
        payload = template.model_dump(mode="json")
        payload["recovery"]["explicit_ro_recheck"] = dict(
            recheck_count=1,
            reader_window_id=str(prior.window_id),
            reader_window_hash=sdk_window_hash(sdk),
            reader_claim_hash=facts_hash(claims[0]["after_state"]),
            reader_owner=delivery["claimed_by"],
            reader_termination_id=str(ends[0]["id"]),
            reader_gateway=dict(
                gateway_id=str(prior.gateway_window_id),
                gateway_hash=facts_hash(gw["after_state"]),
                termination_id=str(terms[0]["id"]),
            ),
        )
        candidate = ControlledWorkerWindow.model_validate_json(json.dumps(payload))
        _ro_actor_sender(db, settings, candidate)
        _ro_delivery_preflight(db, candidate)
        active = db.execute(
            "SELECT count(*) AS n FROM business.p4_sdk_windows "
            "WHERE configured_enabled AND expires_at>clock_timestamp()"
        ).fetchone()
        locks = db.execute(
            "SELECT count(*) AS n FROM pg_locks WHERE locktype='advisory' AND granted"
        ).fetchone()
        clients = db.execute(
            "SELECT count(*) AS n FROM pg_stat_activity WHERE "
            "datname=current_database() AND backend_type='client backend' "
            "AND pid<>pg_backend_pid()"
        ).fetchone()
        require(
            bool(active and locks and clients and active["n"] == locks["n"] == clients["n"] == 0),
            "P4A_RO_OTHER_PRODUCER",
        )
        origin = db.execute(
            "SELECT after_state FROM business.audit_events WHERE id=%s", (r.original_gateway_id,)
        ).fetchone()

    async def check_reader() -> None:
        async with await open_async(web.database) as connection, connection.transaction():
            await connection.execute("SET TRANSACTION READ ONLY")
            await trusted_reader(connection, candidate, datetime.now(UTC))

    asyncio.run(check_reader())
    if origin is None:
        raise AcceptanceFailure("P4A_RO_ORIGIN")
    return dict(
        schema=schema,
        prepared_window=payload,
        origin=origin["after_state"],
        nonconsuming=True,
        manual_unconsumed=True,
        attempts=3,
        C=1,
        anchor=0,
    )


def _ro_context(request: Mapping[str, Any], binding: SourceBinding) -> None:
    require(
        request["transport"] == "real" and request.get("root_real_release") is True,
        "P4A_REAL_PLATFORM_HOLD",
    )
    candidate = binding.manifest["candidate"]
    actual = (
        subprocess.run(
            ["git", "rev-parse", "HEAD", "HEAD^{tree}"],
            cwd=binding.root,
            capture_output=True,
            check=True,
            timeout=5,
        )
        .stdout.decode()
        .splitlines()
    )
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=binding.root,
        capture_output=True,
        check=True,
        timeout=5,
    ).stdout
    require(
        actual == [candidate["source_sha"], candidate["tree"]] and not dirty, "P4A_RO_SOURCE_CLEAN"
    )
    require(set(request["images"]) == {"postgres", "runner", "web"}, "P4A_RESOURCE_SET")
    for name, expected in request["images"].items():
        require(
            re.fullmatch(r"sha256:[0-9a-f]{64}", expected["id"]) is not None, "P4A_RUNNER_IMAGE"
        )
        value = json.loads(_docker(["image", "inspect", expected["id"]]).stdout)[0]
        require(value["Id"] == expected["id"], "P4A_RUNNER_IMAGE")
        if name != "postgres":
            require(
                expected["source_sha"] == candidate["source_sha"]
                and expected["source_tree"] == candidate["tree"]
                and value["Config"]["Labels"].get("p4.acceptance.source_sha")
                == candidate["source_sha"]
                and value["Config"]["Labels"].get("p4.acceptance.source_tree") == candidate["tree"],
                "P4A_CONTEXT_SOURCE_MISMATCH",
            )
    require(
        request["images"]["postgres"]["id"] == request["pg_resource"]["image"], "P4A_PG_RESOURCE"
    )


def _ro_state(request: Mapping[str, Any]) -> dict[str, Any]:
    """独立app只读账本/业务指纹；冷重放和失败同样记录，不补写历史。"""
    from commerceops.application.feishu_business.worker_window import ControlledWorkerWindow
    from commerceops.infrastructure.database import connect
    from commerceops.infrastructure.web_config import WebConfig
    from psycopg import sql

    refs = request["private_refs"]
    private_ref(refs["web_config"])
    config = WebConfig.from_file(Path(refs["web_config"]["path"]))
    require(config.database.user == "commerceops_app", "P4A_ROLE")
    template = ControlledWorkerWindow.model_validate_json(private_ref(refs["template"]))
    r = template.recovery
    if r is None:
        raise AcceptanceFailure("P4A_RO_TEMPLATE")
    fingerprints = {}
    with connect(config.database) as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        db.execute("SET LOCAL statement_timeout='5s'")
        for name in (
            "business_tasks",
            "approvals",
            "executions",
            "replenishment_items",
            "replenishment_plans",
            "jobs",
            "inbox_events",
            "p4_inbox_receipts",
            "principals",
            "identities",
            "principal_shop_scopes",
            "principal_role_shop_grants",
        ):
            data = db.execute(
                sql.SQL("SELECT row_to_json(t)::text AS body FROM business.{} t").format(
                    sql.Identifier(name)
                )
            ).fetchall()
            fingerprints[name] = digest("\n".join(sorted(x["body"] for x in data)).encode())
        for name in (*CP_DATA_TABLES, "checkpoint_migrations"):
            data = db.execute(
                sql.SQL("SELECT row_to_json(t)::text AS body FROM checkpoints.{} t").format(
                    sql.Identifier(name)
                )
            ).fetchall()
            fingerprints["checkpoints." + name] = digest(
                "\n".join(sorted(x["body"] for x in data)).encode()
            )
        ledger = db.execute(
            "SELECT method,status,http_status,provider_code,count(*) AS n "
            "FROM business.p4_sdk_calls GROUP BY method,status,http_status,provider_code "
            "ORDER BY method,status,http_status,provider_code"
        ).fetchall()
        once = db.execute(
            "SELECT action,count(*) AS n FROM business.audit_events WHERE "
            "source='feishu_recovery' AND entity_id=%s AND action=ANY(%s) "
            "GROUP BY action ORDER BY action",
            (
                str(r.projections[0].outbox_id),
                ["explicit_ro_recheck_authorized", "explicit_ro_recheck_dispatched"],
            ),
        ).fetchall()
        delivery = db.execute(
            "SELECT status,attempts,version,observed_version,"
            "complete_unique_verified,external_id IS NOT NULL AS has_external_id "
            "FROM business.p4_base_deliveries WHERE outbox_id=%s",
            (r.projections[0].outbox_id,),
        ).fetchone()
    return dict(
        immutable_business=fingerprints, sdk_ledger=ledger, manual_once=once, delivery=delivery
    )


def _ro_resource(request: Mapping[str, Any], *, start: bool) -> dict[str, Any]:
    """只管理Root精确登记的一个PG；无volume删除，失败不扩大清理范围。"""
    import socket

    r = request["pg_resource"]
    require(re.fullmatch(r"[a-z][a-z0-9-]{2,63}", r["project"]) is not None, "P4A_RESOURCE_OWNER")
    private_ref(r["compose_ref"])
    from commerceops.infrastructure.database import DatabaseSettings

    owner = DatabaseSettings.model_validate_json(
        private_ref(request["private_refs"]["owner_database"])
    )
    require(
        owner.host == "127.0.0.1"
        and owner.port == r["port"]
        and str(owner.password_file) == r["owner_secret_file"],
        "P4A_RO_DATABASE_BINDING",
    )
    volume = json.loads(_docker(["volume", "inspect", r["volume"]]).stdout)[0]
    require(
        volume["Name"] == r["volume"]
        and all(volume.get("Labels", {}).get(k) == v for k, v in r["volume_labels"].items())
        and bool(r["volume_labels"]),
        "P4A_RESOURCE_OWNER",
    )

    def ids(kind: str) -> list[str]:
        args = ["ps", "-aq"] if kind == "container" else ["network", "ls", "-q"]
        return (
            _docker([*args, "--filter", "label=com.docker.compose.project=" + r["project"]])
            .stdout.decode()
            .split()
        )

    containers = ids("container")
    if start:
        require(not containers and not ids("network"), "P4A_RESOURCE_ALREADY_RUNNING")
        compose = ["compose", "--project-name", r["project"], "-f", r["compose_ref"]["path"]]
        config = json.loads(_docker([*compose, "config", "--format", "json"]).stdout)
        require(set(config["services"]) == {"postgres"}, "P4A_RO_COMPOSE_SCOPE")
        service = config["services"]["postgres"]
        ports = service.get("ports", [])
        require(
            service["image"] == r["image"]
            and len(ports) == 1
            and ports[0]["host_ip"] == "127.0.0.1"
            and ports[0]["target"] == 5432
            and str(ports[0]["published"]) == str(r["port"])
            and not service.get("privileged")
            and not service.get("network_mode")
            and not service.get("build")
            and not service.get("entrypoint")
            and not service.get("devices")
            and not service.get("cap_add")
            and service.get("environment")
            == {
                "POSTGRES_USER": "commerceops_owner",
                "POSTGRES_DB": owner.name,
                "POSTGRES_PASSWORD_FILE": "/run/secrets/owner_password",
            }
            and service.get("command")
            == [
                "postgres",
                "-c",
                "log_statement=none",
                "-c",
                "log_min_error_statement=panic",
                "-c",
                "log_parameter_max_length_on_error=0",
            ]
            and set(config.get("secrets", {})) == {"owner_password"}
            and config["secrets"]["owner_password"]["file"] == r["owner_secret_file"]
            and service.get("secrets") == [{"source": "owner_password", "target": "owner_password"}]
            and len(service["volumes"]) == 1
            and service["volumes"][0]["type"] == "volume"
            and service["volumes"][0]["target"] == "/var/lib/postgresql/data"
            and config["volumes"][service["volumes"][0]["source"]]["name"] == r["volume"]
            and service.get("labels", {}).get("p4.ro.run") == r["run_id"],
            "P4A_RO_COMPOSE_SCOPE",
        )
        _docker([*compose, "up", "-d", "postgres"], timeout=45)
        end = time.monotonic() + min(45, _runtime(request["runtime"]).remaining())
        while True:
            containers = ids("container")
            require(len(containers) == 1, "P4A_RESOURCE_SET")
            actual = json.loads(_docker(["inspect", containers[0]]).stdout)[0]
            require(
                actual["Image"] == r["image"]
                and actual["Config"]["Labels"].get("p4.ro.run") == r["run_id"]
                and len(actual["Mounts"]) == 2
                and any(m.get("Name") == r["volume"] for m in actual["Mounts"])
                and any(
                    m.get("Source") == r["owner_secret_file"]
                    and m.get("Destination") == "/run/secrets/owner_password"
                    and m.get("RW") is False
                    for m in actual["Mounts"]
                )
                and actual["HostConfig"]["PortBindings"]
                == {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(r["port"])}]},
                "P4A_RESOURCE_OWNER",
            )
            if actual["State"].get("Health", {}).get("Status") == "healthy":
                break
            require(time.monotonic() < end and actual["State"]["Running"], "P4A_PG_START")
            time.sleep(0.2)
        return dict(container_id=actual["Id"], image=actual["Image"], port=r["port"])
    exits = []
    for cid in containers:
        actual = json.loads(_docker(["inspect", cid]).stdout)[0]
        require(
            actual["Image"] == r["image"]
            and actual["Config"]["Labels"].get("p4.ro.run") == r["run_id"]
            and any(m.get("Name") == r["volume"] for m in actual["Mounts"]),
            "P4A_RESOURCE_OWNER",
        )
        if actual["State"]["Running"]:
            _docker(["stop", "--time", "15", cid], timeout=25)
        actual = json.loads(_docker(["inspect", cid]).stdout)[0]
        require(
            not actual["State"]["Running"]
            and not actual["State"]["OOMKilled"]
            and not actual["State"]["Error"],
            "P4A_CONTAINER_UNCLEAN_EXIT",
        )
        exits.append(actual["State"]["ExitCode"])
        _docker(["rm", cid])
    for network in ids("network"):
        actual = json.loads(_docker(["network", "inspect", network]).stdout)[0]
        require(not actual["Containers"], "P4A_NETWORK_OWNER")
        _docker(["network", "rm", network])
    with socket.socket() as probe:
        probe.settimeout(1)
        closed = probe.connect_ex(("127.0.0.1", int(r["port"]))) != 0
    kept = json.loads(_docker(["volume", "inspect", r["volume"]]).stdout)[0]["Name"] == r["volume"]
    require(
        not ids("container")
        and not ids("network")
        and kept
        and closed
        and all(e == 0 for e in exits),
        "P4A_RO_RESOURCE_CLEANUP",
    )
    return dict(
        verified=True,
        containers=0,
        networks=0,
        volume_preserved=kept,
        listener_closed=closed,
        container_exits=exits,
    )


def original_ro_lab_history(request: Mapping[str, Any], binding: SourceBinding) -> dict[str, Any]:
    """仅空白新LAB库；实际原生C0/sender/reader历史，进程退出后才可做真实分支预演。"""
    from uuid import uuid4

    from commerceops.infrastructure.database import DatabaseSettings, connect

    from tests.p4_acceptance_support import AcceptanceFixture, prepare_single_ro
    from tests.test_p4_acceptance_pg import initialize_schema

    owner = DatabaseSettings.model_validate_json(private_ref(request["owner_database_ref"]))
    app = DatabaseSettings.model_validate_json(private_ref(request["app_database_ref"]))
    require(
        owner.name.startswith("p4_ro_lab_")
        and owner.name == app.name
        and owner.host == app.host == "127.0.0.1"
        and app.user == "commerceops_app",
        "P4A_LAB_SCOPE",
    )
    with connect(owner) as db:
        row = db.execute(
            "SELECT count(*) AS n FROM information_schema.tables "
            "WHERE table_schema IN ('business','checkpoints')"
        ).fetchone()
        require(row is not None and row["n"] == 0, "P4A_LAB_EMPTY_REQUIRED")
    initialize_schema(owner, request["revision"])
    private = Path(request["private_directory"])
    manifest = json.loads(private_ref(request["manifest_ref"]))
    require(manifest == binding.manifest, "P4A_CONTEXT_SOURCE_MISMATCH")
    a = AcceptanceFixture.prepare(
        owner,
        app,
        private,
        _runtime(request["runtime"]),
        case_kind="recover_single_item",
        entry_manifest_ref=request["manifest_ref"],
    )
    try:
        result = prepare_single_ro(a, defer_explicit=True)
        template = result["prior_reader"].model_dump(mode="json")
        template.update(enabled=False, window_id=str(uuid4()), gateway_window_id=str(uuid4()))
        template["recovery"].update(
            worker_window_id=template["window_id"], gateway_window_id=template["gateway_window_id"]
        )
        write_private(private / "template.disabled.json", template)
        write_private(private / "business.json", a.business.model_dump(mode="json"))
        a.external_behavior("normal")
        write_private(
            private / "lab-http.json",
            dict(
                database=owner.name,
                organization_id=str(a.business.organization_id),
                external_ref=_ro_reference(a.external),
            ),
        )
        # 保持原no active SDK检查；不删除或缩短历史窗口，只等其原expiry。
        while True:
            with connect(app) as db:
                active = db.execute(
                    "SELECT count(*) AS n FROM business.p4_sdk_windows "
                    "WHERE configured_enabled AND expires_at>clock_timestamp()"
                ).fetchone()
            if active and active["n"] == 0:
                break
            _runtime(request["runtime"]).remaining()
            time.sleep(0.2)
        return dict(
            exit_code=0,
            stage_result="COMPLETE",
            suite_PASS=False,
            private_refs=dict(
                business=_ro_reference(private / "business.json"),
                web_config=_ro_reference(a.fixture.config_file),
                template=_ro_reference(private / "template.disabled.json"),
                owner_database=request["owner_database_ref"],
                lab_http=_ro_reference(private / "lab-http.json"),
            ),
            manual_consumed=False,
            native_history=True,
            sdk_real_network=0,
            prior_history_parent_must_exit=True,
        )
    finally:
        require(a.cleanup(), "P4A_LAB_HISTORY_CLEANUP")


def original_ro_stage(request: Mapping[str, Any], binding: SourceBinding) -> dict[str, Any]:
    """同canonical outer：真实原键RO协调、PG生命周期、完整子进程退出；默认HOLD。"""
    import asyncio
    import signal
    from uuid import UUID, uuid4

    from commerceops.application.feishu_business.worker_window import ControlledWorkerWindow
    from commerceops.entrypoints.feishu_business import confirm_gateway_child, confirm_worker_child
    from commerceops.infrastructure.database import connect
    from commerceops.infrastructure.web_config import WebConfig

    from tests.p4_acceptance_support import PinnedProcess

    report = StageReport(
        (
            "SOURCE",
            "RESOURCE",
            "SCHEMA",
            "PREPARE",
            "PREFLIGHT",
            "ARM",
            "AUTHORIZE",
            "CALL",
            "PERSIST",
            "STOP",
            "CLEANUP",
        )
    )
    lease = _runtime(request["runtime"])
    require(lease.remaining(cleanup=True) <= 600, "P4A_RO_PG_CAP")
    private = Path(request["private_directory"])
    require(private.is_absolute() and private.is_dir(), "P4A_PRIVATE_ROOT")
    manifest_ref = request["manifest_ref"]
    require(
        json.loads(private_ref(manifest_ref)) == binding.manifest, "P4A_CONTEXT_SOURCE_MISMATCH"
    )
    children: list[PinnedProcess] = []
    receipts: list[dict[str, Any]] = []
    confirmation: list[dict[str, Any]] = []
    gateway: PinnedProcess | None = None
    worker: PinnedProcess | None = None
    window: Any = None
    web: Any = None
    prepared: dict[str, Any] = {}
    native: dict[str, Any] = {}
    cleanup: dict[str, Any] = {}
    resource_attempted = False
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    def interrupted(signum: int, frame: Any) -> None:
        raise KeyboardInterrupt

    previous = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGTERM, signal.SIGINT)}

    def start(action: str, refs: Mapping[str, Any], **extra: Any) -> PinnedProcess:
        lease.remaining()
        child = PinnedProcess.start(
            Path(binding.manifest["entry"]),
            Path(manifest_ref["path"]),
            dict(
                contract=CONTRACT,
                action=action,
                transport="real",
                root_real_release=True,
                private_refs=refs,
                runtime=request["runtime"],
                **extra,
                output_file=str(private / (action + "-" + uuid4().hex + ".json")),
            ),
        )
        children.append(child)
        return child

    try:
        with report.enter("SOURCE"):
            _ro_context(request, binding)
        with report.enter("RESOURCE"):
            resource_attempted = True
            resource = _ro_resource(request, start=True)
            private_ref(request["private_refs"]["web_config"])
            web = WebConfig.from_file(Path(request["private_refs"]["web_config"]["path"]))
            require(
                web.database.host == "127.0.0.1" and web.database.port == resource["port"],
                "P4A_RO_DATABASE_BINDING",
            )
            before = _ro_state(request)
        with report.enter("SCHEMA"):
            # _ro_prepare先owner只读元数据并关闭，随后所有原数据均低权只读。
            prepared = _ro_prepare(request)
        with report.enter("PREPARE"):
            write_private(private / "prepared.private.json", prepared)
        with report.enter("PREFLIGHT"):
            # 第二次独立非消费检查，防止metadata/prepare之间发生变化。
            require(_ro_prepare(request) == prepared, "P4A_RO_PREFLIGHT_CHANGED")
        with report.enter("ARM"):
            seconds = request.get("sdk_seconds", 300)
            require(
                type(seconds) is int
                and 15 < seconds <= 300
                and lease.remaining(cleanup=True) >= seconds + 180,
                "P4A_RO_ARM_CAPACITY",
            )
            expiry = datetime.now(UTC) + timedelta(seconds=seconds)
            payload = prepared["prepared_window"]
            payload.update(
                enabled=True,
                window_id=str(uuid4()),
                gateway_window_id=str(uuid4()),
                expires_at=expiry.isoformat(),
            )
            payload["recovery"].update(
                worker_window_id=payload["window_id"],
                gateway_window_id=payload["gateway_window_id"],
                expires_at=payload["expires_at"],
            )
            window = ControlledWorkerWindow.model_validate_json(json.dumps(payload))
            window.window(
                __import__(
                    "commerceops.adapters.feishu.business_config", fromlist=["BusinessSettings"]
                ).BusinessSettings.model_validate_json(
                    private_ref(request["private_refs"]["business"])
                )
            )
            gw = {
                k: prepared["origin"][k]
                for k in ("schema_version", "organization_id", "shop_id", "parameters")
            }
            gw.update(
                window_id=payload["gateway_window_id"],
                expires_at=payload["expires_at"],
                enabled=True,
                max_callbacks=1,
                max_workflows=0,
            )
            worker_file, gateway_file = (
                private / "current-worker.json",
                private / "current-gateway.json",
            )
            write_private(worker_file, payload)
            write_private(gateway_file, gw)
            refs = {k: request["private_refs"][k] for k in ("business", "web_config")}
            gateway = start(
                "gateway",
                {**refs, "window": _ro_reference(gateway_file)},
                control_mode="native_no_ws",
                ready_file=str(private / "gateway-ready.json"),
            )
            end = time.monotonic() + min(15, lease.remaining())
            while not (private / "gateway-ready.json").exists():
                require(
                    gateway.process.poll() is None and time.monotonic() < end, "P4A_GATEWAY_READY"
                )
                time.sleep(0.02)
            receipts.append(json.loads(bound_bytes(private / "gateway-ready.json", private=True)))
            require(receipts[-1]["pid"] == gateway.process.pid, "P4A_PROCESS_PID")
        with report.enter("AUTHORIZE"):
            worker_refs = {**refs, "window": _ro_reference(worker_file)}
            if "lab_http" in request["private_refs"]:
                worker_refs["lab_http"] = request["private_refs"]["lab_http"]
            worker = start("worker", worker_refs, ready_file=str(private / "worker-ready.json"))
            native = worker.wait(timeout=min(seconds, lease.remaining()))
            if (private / "worker-ready.json").exists():
                receipts.append(
                    json.loads(bound_bytes(private / "worker-ready.json", private=True))
                )
                require(receipts[-1]["pid"] == worker.process.pid, "P4A_PROCESS_PID")
            require(native["stages"]["AUTHORIZE"]["state"] == "PASSED", "P4A_RO_AUTHORIZATION")
        with report.enter("CALL"):
            require(
                native["exit_code"] == 0 and native["stage_result"] == "COMPLETE",
                "P4A_RO_NATIVE_FAILED",
            )
            require(gateway.process.poll() is None, "P4A_GATEWAY_EARLY_EXIT")
        with report.enter("PERSIST"):
            with connect(web.database) as db:
                db.execute("SET TRANSACTION READ ONLY")
                r = window.recovery
                p = r.projections[0]
                row = db.execute(
                    "SELECT d.*,l.external_id AS anchor_external,l.original_outbox_id "
                    "FROM business.p4_base_deliveries d JOIN business.p4_base_links l "
                    "ON l.item_id=d.item_id WHERE d.outbox_id=%s",
                    (p.outbox_id,),
                ).fetchall()
                require(
                    len(row) == 1
                    and row[0]["status"] == "verified"
                    and row[0]["complete_unique_verified"] is True
                    and row[0]["attempts"] == 3
                    and row[0]["version"] == row[0]["observed_version"] == 1
                    and row[0]["external_id"] == row[0]["anchor_external"]
                    and row[0]["original_outbox_id"] == p.outbox_id,
                    "P4A_RO_PERSISTENCE",
                )
                once = db.execute(
                    "SELECT action,count(*) AS n FROM business.audit_events "
                    "WHERE source='feishu_recovery' AND entity_id=%s AND action IN (%s,%s) "
                    "GROUP BY action",
                    (
                        str(p.outbox_id),
                        "explicit_ro_recheck_authorized",
                        "explicit_ro_recheck_dispatched",
                    ),
                ).fetchall()
                require(len(once) == 2 and all(x["n"] == 1 for x in once), "P4A_ONCE_COUNT")
                counts = QUERIES["SDK_COUNTS"].execute(
                    db, (window.window_id,), revision=request["revision"], role="app"
                )
                require(
                    all(
                        x["method"] in window.caps
                        and x["n"] <= window.caps[x["method"]]
                        and (x["status"], x["http_status"], x["provider_code"])
                        == ("returned", 200, 0)
                        for x in counts
                    ),
                    "P4A_RO_LEDGER",
                )
                write_private(
                    private / "persisted.private.json",
                    dict(delivery=row, once=once, method_counts=counts),
                )
                # 只读消费接口；不产生request key、不调用consume_stage(t6)或任何UI动作。
                from tests.e2e.web.m1_acceptance_capture import CaptureContext, capture_snapshot

                actors = db.execute(
                    "SELECT p.id,p.auth_version,i.id AS identity_id "
                    "FROM business.business_tasks t JOIN business.principals p "
                    "ON p.id=t.requester_id JOIN business.identities i ON i.principal_id=p.id "
                    "AND i.organization_id=p.organization_id AND i.provider='web' "
                    "WHERE t.id=%s",
                    (r.task_id,),
                ).fetchall()
                threads = db.execute(
                    "SELECT thread_id FROM business.business_tasks WHERE id=%s "
                    "OR id=(SELECT source_task_id FROM business.p3_task_sources WHERE task_id=%s) "
                    "ORDER BY id",
                    (r.task_id, r.task_id),
                ).fetchall()
                quantity = db.execute(
                    "SELECT count(*) AS n,sum(quantity)::text AS total "
                    "FROM business.replenishment_items WHERE task_id=%s",
                    (r.task_id,),
                ).fetchone()
                require(
                    len(actors) == 1 and quantity is not None and quantity["n"] == 1,
                    "P4A_RO_CAPTURE_CONTEXT",
                )
                if quantity is None:
                    raise AcceptanceFailure("P4A_RO_CAPTURE_CONTEXT")
                context = dict(
                    revision=prepared["schema"]["revision"]
                    + {"0015": "_p4_read_replies", "0016": "_p4_clarification_requests"}[
                        prepared["schema"]["revision"]
                    ],
                    organization_id=str(window.organization_id),
                    shop_id=str(window.shop_id),
                    task_id=str(r.task_id),
                    item_id=str(p.item_id),
                    principal_id=str(actors[0]["id"]),
                    identity_id=str(actors[0]["identity_id"]),
                    auth_version=actors[0]["auth_version"],
                    checkpoint_threads=tuple(x["thread_id"] for x in threads),
                    sdk_window_id=str(window.window_id),
                    sdk_subject_ids=(str(p.outbox_id),),
                    request_key=None,
                    case_kind="recover_single_item",
                    expected_item_count=1,
                    expected_quantity_total=quantity["total"],
                )
                with connect(web.database) as capture_db:
                    snapshot = capture_snapshot(capture_db, CaptureContext(**context))
                write_private(
                    private / "human-handoff.private.json",
                    dict(
                        capture_context=context,
                        before_T6=snapshot,
                        source=binding.manifest["candidate"],
                        images=request["images"],
                        human_action_required=True,
                        automatic_T6_authorized=False,
                        original_key_generated_only_by_native_UI=True,
                        release="HOLD until outer STOP/CLEANUP/exit and Root real-object approval",
                    ),
                )
    except BaseException as error:
        if not isinstance(error, Exception):
            mark_stage(error, "STOP")
        native["outer_failure"] = safe_failure(error, "PREPARE")
    finally:
        try:
            with report.enter("STOP"):
                for child in reversed(children):
                    child.terminate()
                    if child.request["action"] == "worker":
                        with connect(web.database) as db:
                            starts = db.execute(
                                "SELECT entity_id FROM business.audit_events "
                                "WHERE source='worker' AND action='started' AND "
                                "organization_id=%s AND (after_state->>'pid')::bigint=%s",
                                (window.organization_id, child.process.pid),
                            ).fetchall()
                        if starts:
                            require(len(starts) == 1, "P4A_WORKER_STARTED")
                            asyncio.run(
                                confirm_worker_child(web, window.organization_id, child.process.pid)
                            )
                            confirmation.append(dict(kind="worker", termination_confirmed=True))
                    else:
                        require(child.process.returncode == 0, "P4A_GATEWAY_EXIT")
                        asyncio.run(
                            confirm_gateway_child(
                                web,
                                window.organization_id,
                                UUID(str(window.gateway_window_id)),
                                child.process.pid,
                                child.process.returncode,
                            )
                        )
                        confirmation.append(dict(kind="gateway", termination_confirmed=True))
                if receipts:
                    write_private(private / "absent-receipts.json", receipts)
                    probe = dict(
                        contract=CONTRACT,
                        action="process_probe",
                        runtime=request["runtime"],
                        private_root=str(private),
                        absent_receipts=_ro_reference(private / "absent-receipts.json"),
                        output_file=str(private / "independent-process-probe.json"),
                    )
                    independent = PinnedProcess.start(
                        Path(binding.manifest["entry"]), Path(manifest_ref["path"]), probe
                    )
                    require(independent.wait(timeout=10)["exit_code"] == 0, "P4A_PROCESS_ALIVE")
                require(all(c.process.poll() is not None for c in children), "P4A_PROCESS_ALIVE")
                if before:
                    after = _ro_state(request)
                    require(
                        before["immutable_business"] == after["immutable_business"],
                        "P4A_RO_BUSINESS_CHANGED",
                    )
        except BaseException as error:
            native["stop_failure"] = safe_failure(error, "STOP")
        try:
            with report.enter("CLEANUP"):
                if resource_attempted:
                    cleanup = _ro_resource(request, start=False)
        except BaseException as error:
            native["cleanup_failure"] = safe_failure(error, "CLEANUP")
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    result = report.terminal(
        cleanup=cleanup.get("verified") is True,
        reaped=all(c.process.poll() is not None for c in children),
        owned=True,
    )
    return dict(
        **result,
        stage_result="COMPLETE" if result["exit_code"] == 0 else "FAILED",
        prepared=prepared,
        native=native,
        cleanup=cleanup,
        lifecycle=confirmation,
        before_state=before,
        after_state=after,
        child_exits=[
            dict(
                action=c.request["action"],
                exit=c.process.returncode,
                reaped=c.process.poll() is not None,
            )
            for c in children
        ],
        real_platform_PASS=False,
        real_RO_verified=result["exit_code"] == 0 and "lab_http" not in request["private_refs"],
        lab_http="lab_http" in request["private_refs"],
        human_T6="HOLD until real RO and separate human native UI",
        suite_PASS=False,
    )


def outer_request(request: Mapping[str, Any], binding: SourceBinding) -> int:
    require(request.get("contract") == CONTRACT, "P4A_CONTRACT")
    if request.get("action") == "source_probe":
        import commerceops
        from commerceops.entrypoints.web_openapi import export_web

        require(commerceops.__file__ is not None, "P4A_IMPORT_REQUIRED")
        # 原生产函数实际读取两份包内JSON；不启动API/PG/SDK。
        require(bool(export_web({"paths": {}})["components"]["schemas"]), "P4A_ASSETS_REQUIRED")
        binding.check_loaded()
        return 0
    action = request.get("action")
    require(
        action
        in (
            "original_ro",
            "original_ro_lab_history",
            "worker",
            "gateway",
            "capture",
            "api",
            "app_worker",
            "signal_process",
            "confirm_process",
            "process_probe",
            "prepare_case",
            "schema_case",
            "project_v2",
            "run",
            "negative_matrix",
            "sql_denial",
            "database_inventory",
        ),
        "P4A_ACTION",
    )
    lease = _runtime(request["runtime"])
    lease.remaining(
        cleanup=action
        in ("signal_process", "confirm_process", "process_probe", "database_inventory")
        or (action == "capture" and request.get("kind") == "worker")
    )
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
        if action == "original_ro_lab_history":
            result = original_ro_lab_history(request, binding)
        elif action == "original_ro":
            result = original_ro_stage(request, binding)
        elif action == "run":
            result = run_stage(request, binding)
        elif action == "worker":
            result = worker_stage(request)
        elif action == "gateway":
            result = gateway_stage(request)
        elif action == "capture":
            result = capture_stage(request)
        elif action == "api":
            result = api_stage(request)
        elif action == "app_worker":
            result = app_worker_stage(request)
        elif action in ("prepare_case", "schema_case"):
            result = prepare_case_stage(request)
        elif action == "project_v2":
            result = project_v2_stage(request)
        elif action == "negative_matrix":
            result = negative_matrix_stage(request)
        elif action == "sql_denial":
            result = sql_denial_stage(request)
        elif action == "database_inventory":
            result = database_inventory_stage(request)
        elif action == "process_probe":
            result = process_probe_stage(request)
        else:
            result = process_control_stage(request)
    except Exception as error:
        result = {
            "stage_result": "FAILED",
            "exit_code": 1,
            "failure": safe_failure(
                error,
                {
                    "capture": "COLLECT",
                    "sql_denial": "COLLECT",
                    "signal_process": "STOP",
                    "confirm_process": "STOP",
                    "process_probe": "STOP",
                    "project_v2": "V2",
                    "negative_matrix": "MATRIX",
                    "schema_case": "SCHEMA",
                    "database_inventory": "CLEANUP",
                }.get(str(action), "PREPARE"),
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
