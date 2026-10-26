"""PG bind-secret policy stays separate from Woo/Web private-file ownership."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from commerceops.infrastructure.database import DatabaseSettings
from commerceops.infrastructure.web_config import private_bytes

pytestmark = pytest.mark.offline


def settings(path: Path) -> DatabaseSettings:
    return DatabaseSettings(host="127.0.0.1", name="offline", user="offline", password_file=path)


def test_pg_mount_uid_is_not_woo_private_file_uid(tmp_path: Path, monkeypatch: Any) -> None:
    target = tmp_path / "owned-pg-secret"
    target.write_text("synthetic-pg-only\n")
    target.chmod(0o600)
    monkeypatch.setattr(os, "geteuid", lambda: target.stat().st_uid + 1)
    assert settings(target).bounded_password().get_secret_value() == "synthetic-pg-only"
    with pytest.raises(ValueError, match="INVALID_WEB_CONFIGURATION"):
        private_bytes(target)
    assert target.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("case", ["empty", "large", "encoding", "mode", "symlink", "directory"])
def test_pg_bounded_secret_rejects_unsafe_inputs(tmp_path: Path, case: str) -> None:
    target = tmp_path / "owned-pg-secret"
    target.write_bytes(
        {"empty": b" \n", "large": b"x" * 32769, "encoding": b"\xff"}.get(case, b"synthetic")
    )
    target.chmod(0o644 if case == "mode" else 0o600)
    if case == "symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(target)
        target = alias
    elif case == "directory":
        target = tmp_path
    with pytest.raises((ValueError, OSError)):
        settings(target).bounded_password()


def test_pg_native_fifo_fails_without_wait_or_fd_leak(tmp_path: Path) -> None:
    fifo = tmp_path / "owned-fifo"
    os.mkfifo(fifo, 0o600)
    code = """import json,os,sys,time
from pathlib import Path
from commerceops.infrastructure.database import DatabaseSettings
fds='/proc/self/fd' if os.path.isdir('/proc/self/fd') else '/dev/fd'
before=len(os.listdir(fds)); start=time.monotonic()
s=DatabaseSettings(host='127.0.0.1',name='offline',user='offline',password_file=Path(sys.argv[1]))
try:
    s.bounded_password()
except ValueError:
    assert len(os.listdir(fds))==before
    print(json.dumps({'rejected':True,'elapsed':time.monotonic()-start}))
else:
    raise AssertionError('FIFO accepted')
"""
    r = subprocess.run(
        [sys.executable, "-c", code, str(fifo)], capture_output=True, text=True, timeout=2
    )
    assert r.returncode == 0
    result = json.loads(r.stdout)
    assert result["rejected"] and result["elapsed"] < 0.25


@pytest.mark.parametrize("kind", ["value", "sql", "unsafe_name"])
def test_failure_diagnostic_never_prints_message_or_locals(kind: str, capsys: Any) -> None:
    from types import SimpleNamespace

    import psycopg

    from tests.diagnostic_plugin import pytest_runtest_makereport

    hidden = "synthetic-private-value-do-not-emit"
    error: BaseException
    if kind == "sql":
        error = psycopg.errors.QueryCanceled(hidden)
    elif kind == "unsafe_name":
        error = type(hidden, (ValueError,), {})(hidden)
    else:
        error = ValueError(hidden)
    item = SimpleNamespace(nodeid="tests/test_p5_sources_pg.py::test_safe", funcargs={})
    call = SimpleNamespace(excinfo=SimpleNamespace(value=error), when="call")
    report = object()
    hook = pytest_runtest_makereport(item, call)
    next(hook)
    with pytest.raises(StopIteration) as stopped:
        hook.send(report)
    assert stopped.value.value is report
    output = capsys.readouterr().out
    assert hidden not in output
    result = json.loads(output.removeprefix("PG_DIAG "))
    assert result["sqlstate"] == ("57014" if kind == "sql" else None)
    assert (
        result["exception_class"]
        == {"value": "ValueError", "sql": "QueryCanceled", "unsafe_name": "BaseException"}[kind]
    )
    assert result["frames"] == [] and result["database_file_metadata"] is None
