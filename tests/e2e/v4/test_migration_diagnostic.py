"""Pure diagnostic redaction tests; never call migration, connect, PG or Docker."""

import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from . import migration_diagnostic as module

pytestmark = pytest.mark.offline
PUBLIC_SQL = "CREATE TABLE business.public_example (id integer);"
SENTINEL = "SENTINEL_NEVER_EMIT_password_DSN_sql_parameter"


def install_public(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        module, "public_sql", lambda expected: (tmp_path / "public.py", frozenset({PUBLIC_SQL}))
    )


def test_raw_library_messages_native_output_and_parameters_suppressed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capfd: pytest.CaptureFixture[str],
) -> None:
    install_public(monkeypatch, tmp_path)

    def fail() -> None:
        print(SENTINEL)
        print(SENTINEL, file=sys.stderr)
        os.write(1, SENTINEL.encode())
        os.write(2, SENTINEL.encode())
        error = RuntimeError(SENTINEL)
        error.statement = "CREATE TABLE " + SENTINEL  # type: ignore[attr-defined]
        error.params = {"password": SENTINEL}  # type: ignore[attr-defined]
        error.sqlstate = "42601"  # type: ignore[attr-defined]
        error.diag = SimpleNamespace(  # type: ignore[attr-defined]
            statement_position="14",
            message_detail=SENTINEL,
            context=SENTINEL,
            internal_query=SENTINEL,
            schema_name=SENTINEL,
        )
        raise error

    code, report = module.run("a" * 64, fail)
    captured = capfd.readouterr()
    assert code == 1 and report["tests"] == "NOT_RUN"
    assert SENTINEL not in captured.out + captured.err + json.dumps(report)
    assert report["chain"][0]["sqlstate"] == "42601"
    assert report["chain"][0]["statement_position"] == 14
    assert report["chain"][0]["public_sql_excerpt"] is None


def test_only_exact_approved_static_sql_and_chain_metadata_are_emitted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    install_public(monkeypatch, tmp_path)

    def fail() -> None:
        inner = ValueError(SENTINEL)
        inner.sqlstate = "42601"  # type: ignore[attr-defined]
        inner.diag = SimpleNamespace(statement_position="14")  # type: ignore[attr-defined]
        outer = RuntimeError(SENTINEL)
        outer.statement = PUBLIC_SQL  # type: ignore[attr-defined]
        outer.orig = inner  # type: ignore[attr-defined]
        raise outer from inner

    code, report = module.run("a" * 64, fail)
    assert code == 1 and len(report["chain"]) == 2
    assert report["chain"][0]["public_sql_excerpt"] == PUBLIC_SQL
    assert report["chain"][1]["sqlstate"] == "42601"
    assert SENTINEL not in json.dumps(report)


def test_invalid_metadata_is_not_echoed() -> None:
    error = RuntimeError(SENTINEL)
    error.sqlstate = SENTINEL  # type: ignore[attr-defined]
    error.diag = SimpleNamespace(statement_position=SENTINEL)  # type: ignore[attr-defined]
    error.statement = PUBLIC_SQL + SENTINEL  # type: ignore[attr-defined]
    error.__cause__ = error
    report = module.diagnostic(error, Path("/public.py"), frozenset({PUBLIC_SQL}))
    assert len(report) == 1
    assert report[0]["sqlstate"] is None and report[0]["statement_position"] is None
    assert report[0]["public_sql_excerpt"] is None
    assert SENTINEL not in json.dumps(report)


def test_public_fingerprint_failure_does_not_call_migrate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def reject(expected: str) -> tuple[Path, frozenset[str]]:
        raise ValueError(SENTINEL)

    monkeypatch.setattr(module, "public_sql", reject)
    called: list[bool] = []
    code, report = module.run("a" * 64, lambda: called.append(True))
    assert code == 1 and not called and report["stage"] == "PUBLIC_SOURCE_CHECK"
    assert SENTINEL not in json.dumps(report)


def test_success_is_only_migrated_not_test_gate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    install_public(monkeypatch, tmp_path)
    code, report = module.run("a" * 64, lambda: None)
    assert code == 0
    assert report == {"status": "MIGRATED", "stage": "ORIGINAL_MIGRATE", "tests": "NOT_RUN"}


def test_allowlist_comes_from_hashed_public_file_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "public.py"
    raw = ('DDL = "' + PUBLIC_SQL + '"\nOTHER = "not SQL"\n').encode()
    path.write_bytes(raw)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "PUBLIC", "public.py")
    actual_path, strings = module.public_sql(hashlib.sha256(raw).hexdigest())
    assert actual_path == path and strings == frozenset({PUBLIC_SQL})
    with pytest.raises(ValueError):
        module.public_sql("0" * 64)


def test_cli_target_delegates_only_to_original_migrate(monkeypatch: pytest.MonkeyPatch) -> None:
    from commerceops.entrypoints import database

    marker = object()
    settings_calls: list[bool] = []
    migrate_calls: list[object] = []

    def settings() -> object:
        settings_calls.append(True)
        return marker

    monkeypatch.setattr("commerceops.infrastructure.database.DatabaseSettings", settings)
    monkeypatch.setattr(database, "migrate", lambda settings: migrate_calls.append(settings))
    module.original_migrate()
    assert settings_calls == [True] and migrate_calls == [marker]
