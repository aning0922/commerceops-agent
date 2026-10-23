"""仅0012→0013→current保留测试使用的固定d97源码入口；不依赖Git或网络。"""

import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import traceback
from pathlib import Path

from commerceops.infrastructure.database import DatabaseSettings

SOURCE_SHA = "d97c6ae8007eb5b69024e514210860f42359673d"
ARCHIVE_SHA = "daaefa581ada95e448c340da326a0ff0cfa6d88a274894d36f3c9b520a09f2d6"
MANIFEST_SHA = "8fcdfe5391dc1d512806ec3228a840c15946b08f8d51e48df50cca25b420ed6f"
FIXTURE = Path(__file__).parent / "fixtures/p4_legacy_c0_d97"


class LegacyC0Failure(RuntimeError):
    """原历史子进程已经输出安全stage分类，外层不重复替换分类。"""


def extract_legacy(destination: Path) -> Path:
    manifest_bytes = (FIXTURE / "manifest.json").read_bytes()
    archive = (FIXTURE / "source.tar.gz").read_bytes()
    if (
        hashlib.sha256(manifest_bytes).hexdigest() != MANIFEST_SHA
        or hashlib.sha256(archive).hexdigest() != ARCHIVE_SHA
    ):
        raise ValueError("LEGACY_C0_SOURCE_HASH_MISMATCH")
    manifest = json.loads(manifest_bytes)
    if manifest["source_sha"] != SOURCE_SHA or manifest["archive_sha256"] != ARCHIVE_SHA:
        raise ValueError("LEGACY_C0_SOURCE_IDENTITY_MISMATCH")
    files = {entry["path"]: entry["sha256"] for entry in manifest["files"]}
    if len(files) != len(manifest["files"]):
        raise ValueError("LEGACY_C0_DUPLICATE_MANIFEST_PATH")
    destination.mkdir(mode=0o700)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        members = bundle.getmembers()
        if {m.name for m in members} != set(files) or len(members) != len(files):
            raise ValueError("LEGACY_C0_SOURCE_SET_MISMATCH")
        for member in members:
            path = Path(member.name)
            if not member.isfile() or path.is_absolute() or ".." in path.parts:
                raise ValueError("LEGACY_C0_UNSAFE_MEMBER")
            stream = bundle.extractfile(member)
            if stream is None:
                raise ValueError("LEGACY_C0_MISSING_MEMBER")
            body = stream.read()
            if hashlib.sha256(body).hexdigest() != files[member.name]:
                raise ValueError("LEGACY_C0_MEMBER_HASH_MISMATCH")
            target = destination / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
    return destination


def run_legacy_c0(
    owner: DatabaseSettings, app: DatabaseSettings, private: Path, source: Path
) -> None:
    private.mkdir(mode=0o700)
    request = private / "legacy-request.json"
    request.write_text(
        json.dumps(
            {
                "owner": owner.model_dump(mode="json"),
                "app": app.model_dump(mode="json"),
                "private": str(private),
                "source": str(source),
            }
        )
    )
    request.chmod(0o600)
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "HOME", "TMPDIR", "LANG", "LC_ALL"}
    }
    environment.update(
        PYTHONPATH=os.pathsep.join((str(source / "backend/src"), str(source))),
        PYTHONNOUSERSITE="1",
        LANGSMITH_TRACING="false",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import runpy,sys; sys.path[:0]=[sys.argv[1]+'/backend/src',sys.argv[1]]; "
            "runpy.run_path(sys.argv[2],run_name='__main__')",
            str(source),
            str(Path(__file__).resolve()),
            str(request),
        ],
        cwd=source,
        env=environment,
        capture_output=True,
        timeout=90,
    )
    for line in result.stdout.decode().splitlines():
        if line.startswith("PG_DIAG "):
            print(line, flush=True)
    output = private / "legacy-child.private.log"
    output.write_bytes(result.stdout + result.stderr)
    output.chmod(0o600)
    if result.returncode:
        raise LegacyC0Failure("LEGACY_C0_CHILD_FAILED_PRIVATE_TRACE_RETAINED")
    proof = json.loads((private / "legacy-source-proof.json").read_text())
    if proof["source_sha"] != SOURCE_SHA or not proof["all_local_imports_pinned"]:
        raise ValueError("LEGACY_C0_IMPORTED_SOURCE_MISMATCH")
    from tests.diagnostic_plugin import emit

    emit(
        "c0_legacy_source_verified",
        source_sha=SOURCE_SHA,
        archive_sha256=ARCHIVE_SHA,
        imported_files=len(proof["imports"]),
        all_local_imports_pinned=True,
        imports_sha256=hashlib.sha256(
            json.dumps(proof["imports"], sort_keys=True).encode()
        ).hexdigest(),
    )


def historical_main(request: Path) -> None:
    # -I父子隔离入口的本地commerceops/tests都来自已验hash的d97闭包。
    from commerceops.entrypoints.database import grant_runtime

    from tests.diagnostic_plugin import emit
    from tests.p3_support import initialize_p3
    from tests.test_p4_first_create_pg import original_c0

    value = json.loads(request.read_text())
    private, source = Path(value["private"]), Path(value["source"])
    owner = DatabaseSettings.model_validate(value["owner"])
    app = DatabaseSettings.model_validate(value["app"])
    stage = "grant-runtime"
    fixture = None
    try:
        emit("c0_migration_stage", stage=stage, exception_class=None, sqlstate=None)
        grant_runtime(owner)  # d97的明确表名单；0012存在，未触碰0014/0015。
        stage = "initialize_p3"
        emit("c0_migration_stage", stage=stage, exception_class=None, sqlstate=None)
        fixture = initialize_p3(owner, app, private)
        stage = "original_c0"
        emit("c0_migration_stage", stage=stage, exception_class=None, sqlstate=None)
        with original_c0(fixture) as window:
            assert window.first_create is not None  # 原API/Graph/C0与children完整执行。
        imported = {}
        for name, module in tuple(sys.modules.items()):
            if (
                name == "commerceops"
                or name == "tests"
                or name.startswith(("commerceops.", "tests."))
            ):
                filename = getattr(module, "__file__", None)
                if filename is not None:
                    relative = Path(filename).resolve().relative_to(source.resolve())
                    imported[str(relative)] = hashlib.sha256(
                        Path(filename).read_bytes()
                    ).hexdigest()
        manifest = json.loads((FIXTURE / "manifest.json").read_text())
        files = {entry["path"]: entry["sha256"] for entry in manifest["files"]}
        assert imported and all(files.get(k) == v for k, v in imported.items())
        proof = private / "legacy-source-proof.json"
        proof.write_text(
            json.dumps(
                {"source_sha": SOURCE_SHA, "all_local_imports_pinned": True, "imports": imported}
            )
        )
        proof.chmod(0o600)
    except BaseException as error:
        import psycopg

        state = None
        current: BaseException | None = error
        seen: set[int] = set()
        while current is not None and id(current) not in seen and len(seen) < 8:
            seen.add(id(current))
            if isinstance(current, psycopg.Error) and re.fullmatch(
                r"[0-9A-Z]{5}", current.sqlstate or ""
            ):
                state = current.sqlstate
                break
            current = current.__cause__ or current.__context__
        emit(
            "c0_migration_stage", stage=stage, exception_class=type(error).__name__, sqlstate=state
        )
        emit(
            "c0_legacy_failure_frames",
            stage=stage,
            frames=[
                {"file": Path(frame.filename).name, "function": frame.name, "line": frame.lineno}
                for frame in traceback.extract_tb(error.__traceback__)[-12:]
            ],
        )
        raw = private / "legacy-exception.private.txt"
        raw.write_text(traceback.format_exc())
        raw.chmod(0o600)
        raise SystemExit(1) from None
    finally:
        if fixture is not None:
            emit("c0_migration_stage", stage="cleanup-client", exception_class=None, sqlstate=None)
            try:
                fixture.client.close()
            except BaseException as error:
                emit(
                    "c0_migration_stage",
                    stage="cleanup-client",
                    exception_class=type(error).__name__,
                    sqlstate=None,
                )
                raw = private / "legacy-cleanup-exception.private.txt"
                raw.write_text(traceback.format_exc())
                raw.chmod(0o600)
                raise SystemExit(1) from None


if __name__ == "__main__":
    historical_main(Path(sys.argv[3]))
