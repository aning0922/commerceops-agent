"""Exact disabled CLI invocations, no Docker/PG/API process or connection."""

import json
import subprocess
import sys
from typing import Any

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


def test_owner_catalog_requires_native_owner_database_and_source_bindings() -> None:
    import copy

    from .pg_observer import SCHEMA_TABLES
    from .sql_probes import validate_owner_catalog

    source, tree, database = "a" * 40, "b" * 40, "v4_demo_v41_metadata_fixture"
    catalog: dict[str, Any] = {
        "native_exit": 0,
        "source_sha": source,
        "source_tree": tree,
        "stdout_sha256": "c" * 64,
        "result": {
            "execution_identity": {"role": "commerceops_owner", "database": database},
            "revision": "0025_v41_catalog_operations",
            "tables": sorted(SCHEMA_TABLES),
            "global_policy_rows": 1,
        },
    }
    validate_owner_catalog(catalog, database, source, tree)
    for field, value in (("native_exit", True), ("native_exit", 1), ("source_sha", "d" * 40)):
        bad = {**catalog, field: value}
        with pytest.raises(ValueError, match="CATALOG_RECEIPT_REQUIRED"):
            validate_owner_catalog(bad, database, source, tree)
    variants: list[tuple[str, Any]] = [
        ("execution_identity", {"role": "commerceops_app", "database": database}),
        ("execution_identity", {"role": "commerceops_owner", "database": "v4_demo_old"}),
        ("tables", []),
        ("global_policy_rows", 0),
    ]
    for field, replacement in variants:
        bad = copy.deepcopy(catalog)
        bad["result"][field] = replacement
        with pytest.raises(ValueError, match="SCHEMA_BINDING_MISMATCH"):
            validate_owner_catalog(bad, database, source, tree)
