"""Exact disabled CLI invocations, no Docker/PG/API process or connection."""

import json
import subprocess
import sys

import pytest

from .sql_probes import ROOT

pytestmark = pytest.mark.offline


@pytest.mark.parametrize("action", ["binding-stop-attack", "forced-action-rollback"])
@pytest.mark.parametrize("opened", [False, True])
def test_actual_probe_cli_stops_at_authority_before_config_or_db(action: str, opened: bool) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.e2e.v41.sql_probes",
            action,
            *(["--root-opened-window"] if opened else []),
        ],
        cwd=ROOT,
        env={},
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 1 and result.stderr == ""
    reply = json.loads(result.stdout)
    assert reply == {
        "status": "FAILED_OR_UNKNOWN",
        "error_type": "ValueError",
        "code": "V41_SQL_PROBE_RUNTIME_HOLD" if opened else "ROOT_EXACT_SQL_PROBE_WINDOW_REQUIRED",
        "sqlstate": None,
    }
