"""Pure diagnostic redaction tests; never call migration, connect, PG or Docker."""

import ctypes
import hashlib
import json
import os
import subprocess
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


@pytest.mark.parametrize("error_type", [SystemExit, KeyboardInterrupt])
def test_interrupts_stay_nonzero_and_do_not_escape_cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capfd: pytest.CaptureFixture[str],
    error_type: type[BaseException],
) -> None:
    install_public(monkeypatch, tmp_path)

    def interrupt() -> None:
        raise error_type(SENTINEL)

    monkeypatch.setattr(module, "original_migrate", interrupt)
    monkeypatch.setattr(sys, "argv", ["diagnostic", "--public-migration-sha256", "a" * 64])
    with pytest.raises(SystemExit) as stopped:
        module.main()
    output = capfd.readouterr()
    assert stopped.value.code == 1 and output.err == ""
    report = json.loads(output.out)
    assert report["status"] == "FAILED" and report["tests"] == "NOT_RUN"
    assert report["chain"][0]["exception_type"] == error_type.__name__
    assert SENTINEL not in output.out


@pytest.mark.parametrize("stage", ["diagnostic", "serialization"])
def test_diagnostic_and_serializer_errors_have_fixed_failure_shape(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capfd: pytest.CaptureFixture[str],
    stage: str,
) -> None:
    install_public(monkeypatch, tmp_path)

    def fail(*args: object, **kwargs: object) -> None:
        print(SENTINEL, file=sys.stderr)
        raise SystemExit(SENTINEL)

    monkeypatch.setattr(module, "original_migrate", fail)
    if stage == "diagnostic":
        monkeypatch.setattr(module, "diagnostic", fail)
    else:
        monkeypatch.setattr(json, "dumps", fail)
    monkeypatch.setattr(sys, "argv", ["diagnostic", "--public-migration-sha256", "a" * 64])
    with pytest.raises(SystemExit) as stopped:
        module.main()
    output = capfd.readouterr()
    assert stopped.value.code == 1 and output.err == ""
    assert json.loads(output.out) == json.loads(module.FALLBACK)
    assert SENTINEL not in output.out


@pytest.mark.parametrize("interrupt", [False, True])
def test_native_buffer_flushed_while_suppressed_without_losing_caller_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capfd: pytest.CaptureFixture[str],
    interrupt: bool,
) -> None:
    install_public(monkeypatch, tmp_path)
    libc = ctypes.CDLL(None)
    libc.printf.argtypes = [ctypes.c_char_p]
    libc.printf.restype = ctypes.c_int
    libc.fflush.argtypes = [ctypes.c_void_p]
    libc.fflush.restype = ctypes.c_int
    libc.printf(b"OUTER_NATIVE_BUFFER")
    print("OUTER_PYTHON_BUFFER", end="")

    def operation() -> None:
        libc.printf(SENTINEL.encode())  # Deliberately no newline/flush.
        if interrupt:
            raise KeyboardInterrupt(SENTINEL)

    code, encoded = module.render("a" * 64, operation)
    libc.fflush(None)  # Simulate the later flush that exposed MD02.
    output = capfd.readouterr()
    assert code == (1 if interrupt else 0)
    assert SENTINEL not in output.out + output.err + encoded
    assert "OUTER_NATIVE_BUFFER" in output.out and "OUTER_PYTHON_BUFFER" in output.out


def test_bad_cli_arguments_cannot_echo_sensitive_value(
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["diagnostic", "--unrecognized", SENTINEL])
    with pytest.raises(SystemExit) as stopped:
        module.main()
    output = capfd.readouterr()
    assert stopped.value.code == 1 and output.err == ""
    assert json.loads(output.out) == json.loads(module.FALLBACK)
    assert SENTINEL not in output.out


@pytest.mark.parametrize(
    "case",
    [
        "exit",
        "interrupt_context",
        "diagnostic",
        "serialize",
        "native",
        "native_flush_failure",
        "restore_failure",
    ],
)
def test_complete_child_exit_has_no_sentinel_or_traceback(case: str) -> None:
    script = r"""
import ctypes, sys
from pathlib import Path
from tests.e2e.v4 import migration_diagnostic as m
case = sys.argv[1]
marker = "REVIEW_SENTINEL_SYNTHETIC_ONLY"
m.public_sql = lambda expected: (Path("/public.py"), frozenset())
def fail(*args, **kwargs):
    raise OSError(marker)
def operation():
    if case == "native_flush_failure":
        real = real_cdll(None)
        real.printf.argtypes = [ctypes.c_char_p]
        real.printf(marker.encode())
        # Force failure while the real C buffer still contains the marker.
        raise RuntimeError(marker)
    if case == "restore_failure":
        original_dup2 = m.os.dup2
        def refuse_restore(source, target):
            raise OSError(marker)
        m.os.dup2 = refuse_restore
        raise RuntimeError(marker)
    if case == "native":
        libc = ctypes.CDLL(None)
        libc.printf.argtypes = [ctypes.c_char_p]
        libc.printf(marker.encode())
        return
    if case == "exit":
        raise SystemExit(marker)
    try:
        raise RuntimeError(marker)
    except RuntimeError:
        if case == "interrupt_context":
            raise KeyboardInterrupt(marker)
        raise
m.original_migrate = operation
if case == "native_flush_failure":
    real_cdll = m.ctypes.CDLL
    class Flush:
        def __init__(self, original):
            self.original = original
            self.calls = 0
        def __call__(self, value):
            self.calls += 1
            if self.calls >= 2:
                return -1
            return self.original(value)
    class Lib:
        def __init__(self):
            self.fflush = Flush(real_cdll(None).fflush)
    m.ctypes.CDLL = lambda value: Lib()
if case == "diagnostic":
    m.diagnostic = fail
if case == "serialize":
    m.json.dumps = fail
sys.argv = ["diagnostic", "--public-migration-sha256", "a" * 64]
m.main()
"""
    result = subprocess.run(
        [sys.executable, "-c", script, case],
        cwd=module.ROOT,
        env={},
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == (0 if case == "native" else 1)
    assert "REVIEW_SENTINEL" not in result.stdout + result.stderr
    assert "Traceback" not in result.stdout + result.stderr and result.stderr == ""
    report = json.loads(result.stdout)
    assert report["status"] == ("MIGRATED" if case == "native" else "FAILED")
    assert report["tests"] == "NOT_RUN"
