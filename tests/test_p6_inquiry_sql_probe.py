"""Offline diagnostic output-policy checks; never call run()/diagnose() or PG."""

import io
import json
import secrets
import sys

import psycopg
import pytest
from commerceops.application.commerce.readonly_inquiry_service_contracts import ResultPayload

from tests import p6_inquiry_sql_probe as probe

pytestmark = pytest.mark.offline


def test_diagnostic_reads_exact_frozen_schema_without_sql_execution() -> None:
    assert probe.frozen_result_schema() == ResultPayload.model_json_schema()


def test_raw_database_error_never_enters_diagnostic_output() -> None:
    private = secrets.token_urlsafe(32)
    output = io.StringIO()
    probe.emit(
        output,
        "table_check",
        False,
        psycopg.errors.CheckViolation(private),
        "readonly_inquiries_check1",
    )
    encoded = output.getvalue()
    assert private not in encoded
    assert json.loads(encoded) == {
        "stage": "table_check",
        "ok": False,
        "sqlstate": "23514",
        "constraint": "readonly_inquiries_check1",
    }


@pytest.mark.parametrize("name", ["other_table_constraint", "readonly_inquiries_';SQL", "x" * 80])
def test_constraint_identifier_is_restricted_to_known_business_table(name: str) -> None:
    output = io.StringIO()
    probe.emit(output, "finish", False, constraint=name)
    assert json.loads(output.getvalue())["constraint"] is None


def test_main_suppresses_bootstrap_exception_text_and_library_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private = secrets.token_urlsafe(32)

    def fail(*_: object) -> int:
        print(private)
        raise OSError(private)

    monkeypatch.setattr(probe, "run", fail)
    monkeypatch.setattr(sys, "argv", ["owned-probe"])
    assert probe.main() == 1
    captured = capsys.readouterr()
    assert private not in captured.out and captured.err == ""
    assert json.loads(captured.out) == {
        "stage": "bootstrap",
        "ok": False,
        "sqlstate": None,
        "constraint": None,
    }
