"""最后迁移测试安全分类 pure/Fake；不建立数据库或改变角色/原断言。"""

import json
import shutil
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import psycopg
import pytest

from tests import test_p4_first_create_negatives_pg as target
from tests.p3_support import P3Fixture

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

        def execute(self, statement: Any) -> Any:
            nonlocal snapshots
            text = statement if isinstance(statement, str) else statement.as_string()
            if "pg_tables" in text:
                snapshots += 1
                run("snapshot-before" if snapshots == 1 else "snapshot-after")
                return SimpleNamespace(
                    fetchall=lambda: [{"schemaname": "business", "tablename": "fake"}]
                )
            if "row_to_json" in text:
                body = "different" if failure_stage == "compare" and snapshots == 2 else "same"
                return SimpleNamespace(fetchall=lambda: [{"body": body}])
            run("revision-check")
            return SimpleNamespace(fetchone=lambda: {"version_num": "0013_p4_first_create"})

    def copy(_: str, destination: Path) -> None:
        (destination / "versions").mkdir(parents=True)
        (destination / "versions/0013_p4_first_create.py").write_text("fake copy only")

    async def checkpoint(_: Any) -> None:
        run("checkpointer")

    def migrate(_: Any, **kwargs: Any) -> None:
        run("migrate0012" if kwargs else "migrate0013")

    def initialize(*_: Any) -> Any:
        run("initialize_p3")
        return SimpleNamespace(client=SimpleNamespace(close=lambda: run("cleanup-client")))

    @contextmanager
    def original(_: Any) -> Any:
        run("original_c0")
        yield None

    monkeypatch.setattr(shutil, "copytree", copy)
    monkeypatch.setattr(psycopg, "connect", lambda **_: Admin())
    monkeypatch.setattr(target, "connect", lambda _: Read())
    monkeypatch.setattr(target, "migrate", migrate)
    monkeypatch.setattr(target, "setup_checkpointer", checkpoint)
    monkeypatch.setattr(target, "grant_runtime", lambda _: run("grant-runtime"))
    monkeypatch.setattr(target, "initialize_p3", initialize)
    monkeypatch.setattr(target, "original_c0", original)
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
        with pytest.raises(AssertionError if failure_stage == "compare" else RuntimeError) as found:
            target.test_forward_0012_upgrade_preserves_original_c0_rows_and_checkpoint_bytes(
                fixture, tmp_path
            )
        if failure_stage != "compare":
            assert found.value is error
    output = capsys.readouterr().out
    assert (
        HIDDEN not in output and "CREATE DATABASE" not in output and "DROP DATABASE" not in output
    )
    events = [json.loads(line.removeprefix("PG_DIAG ")) for line in output.splitlines()]
    failures = [event for event in events if event["exception_class"] is not None]
    assert len(failures) == (0 if failure_stage is None else 1)
    if failure_stage:
        assert failures[0]["stage"] == failure_stage
        assert failures[0]["sqlstate"] == ("23514" if failure_stage == "initialize_p3" else None)
    if "create-db" in operations and failure_stage != "create-db":
        assert "cleanup-db" in operations
    if "original_c0" in operations:
        assert "cleanup-client" in operations
