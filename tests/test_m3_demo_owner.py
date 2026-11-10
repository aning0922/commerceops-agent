"""Actual-connection identity doubles only; no PG, services, or real initializer."""

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from commerceops.infrastructure.database import DatabaseSettings

from scripts import m3_daily_demo, m3_inquiry_demo
from tests import p3_support

pytestmark = pytest.mark.offline


@pytest.mark.parametrize("kind", ["daily", "inquiry"])
@pytest.mark.parametrize(
    "case", ["runtime", "database", "missing_owner", "missing_table", "nonempty", "owner"]
)
def test_seeds_check_actual_owner_and_database_before_directory_or_initializer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    case: str,
) -> None:
    module = m3_daily_demo if kind == "daily" else m3_inquiry_demo
    directory = tmp_path.resolve() / "new-private"
    settings = DatabaseSettings(
        host="127.0.0.1",
        name=f"m3_{kind}_demo_owned",
        user="synthetic_owner",
        password_file=tmp_path / "not-read",
        runtime_password_file=tmp_path / "not-read-app",
    )
    monkeypatch.setenv("COMMERCEOPS_MODE", "m3-inquiry-demo")
    identity: dict[str, Any] = {
        "database_name": settings.name,
        "connected_user": "synthetic_owner",
        "table_owner": "synthetic_owner",
    }
    if case == "runtime":
        identity["connected_user"] = "commerceops_app"
    elif case == "database":
        identity["database_name"] = "different_database"
    elif case == "missing_owner":
        identity["table_owner"] = None
    statements: list[str] = []
    initialized: list[bool] = []

    class Connection:
        result: dict[str, Any] | None = None

        def __enter__(self) -> "Connection":
            return self

        def __exit__(self, *_: Any) -> None:
            pass

        def execute(self, statement: str) -> "Connection":
            statements.append(statement)
            if "pg_catalog.pg_class" in statement:
                assert "current_database()" in statement and "current_user" in statement
                assert "pg_get_userbyid(c.relowner)" in statement
                self.result = None if case == "missing_table" else identity
            elif "count(*)" in statement:
                self.result = {"n": 1 if case == "nonempty" else 0}
            elif "clock_timestamp()" in statement:
                self.result = {"time": datetime.now(UTC)}
            else:
                raise AssertionError("unexpected database statement")
            return self

        def fetchone(self) -> dict[str, Any] | None:
            return self.result

    def initializer(*_: Any) -> Any:
        initialized.append(True)
        raise RuntimeError("initializer boundary reached; no fixture writes performed")

    monkeypatch.setattr(module, "connect", lambda _: Connection())
    monkeypatch.setattr(p3_support, "initialize_p3", initializer)
    if kind == "daily":
        monkeypatch.setattr(module, "DatabaseSettings", lambda: settings)
        monkeypatch.setattr(sys, "argv", ["daily-demo", "--directory", str(directory)])
        with pytest.raises(SystemExit) as caught:
            m3_daily_demo.main()
        assert str(caught.value) == "本地日报种子失败；保留新owned资源供核实，不自动重试"
    elif case == "owner":
        with pytest.raises(RuntimeError, match="initializer boundary reached"):
            m3_inquiry_demo.seed(settings, directory)
    else:
        expected = (
            "EMPTY_OWNED_DATABASE_REQUIRED"
            if case == "nonempty"
            else "OWNED_DATABASE_OWNER_REQUIRED"
        )
        with pytest.raises(ValueError, match=f"^{expected}$"):
            m3_inquiry_demo.seed(settings, directory)
    assert bool(initialized) == (case == "owner")
    assert directory.exists() == (case == "owner")
    if case not in ("owner", "nonempty"):
        assert len(statements) == 1
