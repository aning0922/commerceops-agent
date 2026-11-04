"""Actual SQLAlchemy/Alembic compilation, without PostgreSQL or a rendered-SQL substitute."""

import importlib.util
from pathlib import Path
from typing import Any, cast

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_mock_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.sql.compiler import Compiled

pytestmark = pytest.mark.offline


def test_complete_upgrade_does_not_invent_json_bind_parameters() -> None:
    path = (
        Path(__file__).resolve().parents[3]
        / "backend/migrations/versions/0025_v41_catalog_operations.py"
    )
    module_spec = importlib.util.spec_from_file_location("v41_transport_subject", path)
    assert module_spec is not None and module_spec.loader is not None
    migration = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(migration)
    compiled: list[Compiled] = []

    def execute(statement: Any, *args: Any, **kwargs: Any) -> None:
        compiled.append(statement.compile(dialect=connection.dialect))

    connection = create_mock_engine("postgresql+psycopg://", execute)
    context = MigrationContext.configure(connection=cast(Connection, connection))
    # This invokes the real upgrade/op.execute/_exec/TextClause path for every statement.
    # Only the DBAPI transport is absent. It does not prove that PostgreSQL accepts the DDL.
    with Operations.context(context):
        migration.upgrade()
    assert len(compiled) > 20
    assert all(statement.params == {} for statement in compiled)
    assert all(
        not text(getattr(migration, name))._bindparams
        for name in ("DDL", "FUNCTIONS", "ACTION_FUNCTIONS", "GUARDS", "PARSE_FUNCTIONS")
    )
    # Preserve the original transport failure as a real compiler counterexample.
    assert tuple(text("SELECT '{\"reaped\":true}'::jsonb")._bindparams) == ("true",)
    assert not text("SELECT '{\"reaped\": true}'::jsonb")._bindparams
