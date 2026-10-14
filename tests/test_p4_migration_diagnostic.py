"""最后迁移测试安全分类 pure/Fake；不建立数据库或改变角色/原断言。"""

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import psycopg
import pytest

from tests import test_p4_first_create_negatives_pg as target
from tests.p3_support import P3Fixture
from tests.p4_legacy_c0_d97 import LegacyC0Failure

pytestmark = pytest.mark.offline
HIDDEN = "synthetic-private-text-do-not-output"


def test_wrapped_from_none_keeps_only_class_and_underlying_sqlstate(capsys: Any) -> None:
    try:
        try:
            raise psycopg.errors.UniqueViolation(HIDDEN)
        except psycopg.Error:
            raise RuntimeError(HIDDEN) from None
    except RuntimeError as error:
        target.migration_diag("initialize_p3", error)
    text = capsys.readouterr().out
    data = json.loads(text.removeprefix("PG_DIAG "))
    assert data["stage"] == "initialize_p3" and data["exception_class"] == "RuntimeError"
    assert data["sqlstate"] == "23505" and HIDDEN not in text
    assert set(data) == {"event", "pid", "monotonic", "stage", "exception_class", "sqlstate"}


@pytest.mark.parametrize("state", [None, "2350", "235050", "42p01", HIDDEN, False, 23505])
def test_missing_or_invalid_sqlstate_never_serializes_private_text(state: Any, capsys: Any) -> None:
    error = psycopg.Error(HIDDEN)
    error.sqlstate = state
    target.migration_diag("migrate0012", error)
    text = capsys.readouterr().out
    assert json.loads(text.removeprefix("PG_DIAG "))["sqlstate"] is None
    assert HIDDEN not in text


def test_chain_is_bounded_cycle_safe_and_ignores_message_or_other_sqlstate_attributes() -> None:
    chain = [RuntimeError(HIDDEN) for _ in range(9)]
    for left, right in zip(chain, chain[1:], strict=False):
        left.__cause__ = right
    chain[-1].__context__ = psycopg.errors.CheckViolation(HIDDEN)
    assert target.migration_sqlstate(chain[0]) is None
    loop = RuntimeError(HIDDEN)
    loop.__context__ = loop
    assert target.migration_sqlstate(loop) is None
    assert target.migration_sqlstate(RuntimeError("SQL class 23514 " + HIDDEN)) is None


def test_unsafe_type_name_and_bad_stage_cannot_emit_arbitrary_strings(capsys: Any) -> None:
    error = type(HIDDEN + "/bad", (RuntimeError,), {})(HIDDEN)
    target.migration_diag("cleanup-db", error)
    text = capsys.readouterr().out
    assert json.loads(text.removeprefix("PG_DIAG "))["exception_class"] == "BaseException"
    assert HIDDEN not in text
    with pytest.raises(ValueError, match="INVALID_MIGRATION_DIAGNOSTIC_STAGE"):
        target.migration_diag(cast(target.MigrationStage, HIDDEN), error)
    assert capsys.readouterr().out == ""


def test_introspection_failure_does_not_replace_the_original_error_or_emit_text(
    capsys: Any,
) -> None:
    def broken(_: Any) -> str:
        raise RuntimeError(HIDDEN)

    kind = cast(
        type[psycopg.Error],
        type("BrokenSqlstate", (psycopg.Error,), {"sqlstate": property(broken)}),
    )
    error = kind.__new__(kind)
    BaseException.__init__(error, HIDDEN)  # 不让psycopg构造器先读故意损坏的属性。
    target.migration_diag("migrate0012", error)
    text = capsys.readouterr().out
    data = json.loads(text.removeprefix("PG_DIAG "))
    assert data["exception_class"] == "BrokenSqlstate" and data["sqlstate"] is None
    assert HIDDEN not in text


@pytest.mark.parametrize(
    "failure_stage",
    [
        None,
        "create-db",
        "migrate0012",
        "checkpointer",
        "grant-runtime",
        "initialize_p3",
        "original_c0",
        "snapshot-before",
        "migrate0013",
        "snapshot-after",
        "compare",
        "revision-check",
        "migrate-current",
        "snapshot-current",
        "compare-current",
        "grant-current",
        "current-grant-check",
        "current-revision-check",
        "cleanup-client",
        "cleanup-db",
        "cleanup-admin",
    ],
)
def test_last_test_stages_cleanup_and_original_failures_with_fake_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Any,
    failure_stage: str | None,
) -> None:
    operations: list[str] = []
    error = RuntimeError(HIDDEN)
    if failure_stage == "initialize_p3":
        error.__context__ = psycopg.errors.CheckViolation(HIDDEN)
        error.__suppress_context__ = True
    snapshots = 0

    def run(stage: str) -> None:
        operations.append(stage)
        if failure_stage == stage:
            raise error

    class Settings:
        def model_copy(self, **_: Any) -> "Settings":
            return self

        def kwargs(self) -> dict[str, Any]:
            return {}

    class Admin:
        def __enter__(self) -> "Admin":
            return self

        def __exit__(self, *_: Any) -> None:
            run("cleanup-admin")

        def execute(self, statement: Any) -> None:
            run("create-db" if statement.as_string().startswith("CREATE") else "cleanup-db")

    class Read:
        def __enter__(self) -> "Read":
            return self

        def __exit__(self, *_: Any) -> None:
            pass

        def execute(self, statement: Any, params: Any = None) -> Any:
            nonlocal snapshots
            self.params = params
            text = statement if isinstance(statement, str) else statement.as_string()
            if "pg_tables" in text:
                snapshots += 1
                run({1: "snapshot-before", 2: "snapshot-after", 3: "snapshot-current"}[snapshots])
                names = [
                    {"schemaname": "business", "tablename": "fake"},
                    {"schemaname": "checkpoints", "tablename": "checkpoints"},
                ]
                if snapshots == 3:
                    names += [
                        {"schemaname": "business", "tablename": "p3_template_results"},
                        {"schemaname": "business", "tablename": "p4_read_replies"},
                    ]
                return SimpleNamespace(fetchall=lambda: names)
            if "row_to_json" in text:
                if "p3_template_results" in text or "p4_read_replies" in text:
                    return SimpleNamespace(fetchall=lambda: [])
                body = (
                    "different"
                    if (
                        (failure_stage == "compare" and snapshots == 2)
                        or (failure_stage == "compare-current" and snapshots == 3)
                    )
                    else "same"
                )
                return SimpleNamespace(fetchall=lambda: [{"body": body}])
            if "has_table_privilege" in text or "has_column_privilege" in text:
                run("current-grant-check")
                if "has_column_privilege" in text:
                    allowed = "payload" not in text
                else:
                    allowed = self.params[1] in ("SELECT", "INSERT")
                return SimpleNamespace(fetchone=lambda: {"allowed": allowed})
            if "rolsuper" in text:
                return SimpleNamespace(
                    fetchone=lambda: {
                        "rolsuper": False,
                        "rolcreatedb": False,
                        "rolcreaterole": False,
                    }
                )
            run("revision-check" if snapshots == 2 else "current-revision-check")
            return SimpleNamespace(
                fetchone=lambda: {
                    "version_num": (
                        "0013_p4_first_create" if snapshots == 2 else "0015_p4_read_replies"
                    )
                }
            )

    def copy(_: str, destination: Path) -> None:
        (destination / "versions").mkdir(parents=True)
        (destination / "versions/0013_p4_first_create.py").write_text("fake copy only")

    async def checkpoint(_: Any) -> None:
        run("checkpointer")

    def migrate(_: Any, **kwargs: Any) -> None:
        run(
            "migrate-current"
            if not kwargs
            else ("migrate0012" if kwargs["migrations"].name == "schema-0012" else "migrate0013")
        )

    def legacy(*_: Any) -> None:
        initialized = False
        for child_stage in ("grant-runtime", "initialize_p3", "original_c0"):
            target.migration_diag(child_stage)
            try:
                run(child_stage)
                if child_stage == "initialize_p3":
                    initialized = True
            except RuntimeError as fault:
                target.migration_diag(child_stage, fault)
                if initialized:
                    target.migration_diag("cleanup-client")
                    run("cleanup-client")
                raise LegacyC0Failure("fixed child failure") from fault
        target.migration_diag("cleanup-client")
        try:
            run("cleanup-client")
        except RuntimeError as fault:
            target.migration_diag("cleanup-client", fault)
            raise LegacyC0Failure("fixed child cleanup failure") from fault

    monkeypatch.setattr(shutil, "copytree", copy)
    monkeypatch.setattr(psycopg, "connect", lambda **_: Admin())
    monkeypatch.setattr(target, "connect", lambda _: Read())
    monkeypatch.setattr(target, "migrate", migrate)
    monkeypatch.setattr(target, "setup_checkpointer", checkpoint)
    monkeypatch.setattr(target, "grant_runtime", lambda _: run("grant-current"))
    monkeypatch.setattr(target, "extract_legacy", lambda path: path)
    monkeypatch.setattr(target, "run_legacy_c0", legacy)
    fixture = cast(
        P3Fixture,
        SimpleNamespace(
            inventory=SimpleNamespace(owner=Settings()),
            config=SimpleNamespace(database=Settings()),
        ),
    )
    if failure_stage is None:
        target.test_forward_0012_upgrade_preserves_original_c0_rows_and_checkpoint_bytes(
            fixture, tmp_path
        )
    else:
        with pytest.raises(
            AssertionError if failure_stage in ("compare", "compare-current") else RuntimeError
        ) as found:
            target.test_forward_0012_upgrade_preserves_original_c0_rows_and_checkpoint_bytes(
                fixture, tmp_path
            )
        if failure_stage in ("grant-runtime", "initialize_p3", "original_c0", "cleanup-client"):
            assert isinstance(found.value, LegacyC0Failure)
            assert found.value.__cause__ is error
        elif failure_stage not in ("compare", "compare-current"):
            assert found.value is error
    output = capsys.readouterr().out
    assert (
        HIDDEN not in output and "CREATE DATABASE" not in output and "DROP DATABASE" not in output
    )
    events = [json.loads(line.removeprefix("PG_DIAG ")) for line in output.splitlines()]
    failures = [
        event
        for event in events
        if event["event"] == "c0_migration_stage" and event["exception_class"] is not None
    ]
    assert len(failures) == (0 if failure_stage is None else 1)
    if failure_stage:
        assert failures[0]["stage"] == failure_stage
        assert failures[0]["sqlstate"] == ("23514" if failure_stage == "initialize_p3" else None)
    if "create-db" in operations and failure_stage != "create-db":
        assert "cleanup-db" in operations
    if "original_c0" in operations:
        assert "cleanup-client" in operations


def test_fixed_d97_closure_hashes_and_isolated_imports_are_offline(tmp_path: Path) -> None:
    import hashlib
    import subprocess
    import sys

    from tests.p4_legacy_c0_d97 import FIXTURE, SOURCE_SHA, extract_legacy

    source = extract_legacy(tmp_path / "d97")
    manifest = json.loads((FIXTURE / "manifest.json").read_text())
    assert manifest["source_sha"] == SOURCE_SHA
    assert all(
        hashlib.sha256((source / entry["path"]).read_bytes()).hexdigest() == entry["sha256"]
        for entry in manifest["files"]
    )
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys; sys.path[:0]=[sys.argv[1]+'/backend/src',sys.argv[1]]; "
            "import tests.p3_process,tests.test_p4_first_create_pg; "
            "from commerceops.infrastructure.replenishment_repository import ApprovalStore; "
            "assert str(ApprovalStore.prepare.__code__.co_filename).startswith(sys.argv[1]); "
            "from pathlib import Path; "
            "from commerceops.entrypoints.api import create_app; "
            "from commerceops.infrastructure.database import DatabaseSettings; "
            "from commerceops.infrastructure.web_config import WebConfig; "
            "from commerceops.infrastructure.replenishment_repository import ReplenishmentStore; "
            "from commerceops.workflows.report_explanation import ProviderFactory; "
            "from commerceops.adapters.commerce.mock import Fixture; "
            "data=Path(sys.argv[1])/'tests/fixtures/commerce/inventory-v1'; "
            "database=DatabaseSettings(host='127.0.0.1',name='offline_only',"
            "user='commerceops_app',password_file=Path('/never-read/offline-password')); "
            "config=WebConfig(database,b'a'*32,b'b'*32,"
            "('http://127.0.0.1',),transport_mode='local_http'); "
            "app=create_app(web_config=config,"
            "replenishment_store=ReplenishmentStore(config,data)); "
            "assert '/api/v1/tasks' in app.openapi()['paths']; "
            "provider=ProviderFactory(); "
            "assert not provider.allow_actual and provider.key_file is None; "
            "Fixture.load(data,'baseline'); Fixture.load(data,'known_inbound'); "
            "print('pinned historical imports verified')",
            str(source),
        ],
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout == b"pinned historical imports verified\n"
    assert {p.name for p in (source / "backend/migrations/versions").glob("*.py")} == {
        p.name
        for p in Path("backend/migrations/versions").glob("*.py")
        if not p.name.startswith(("0014_", "0015_"))
    }
