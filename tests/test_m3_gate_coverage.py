"""Complete M3 module grouping and strict Node contract coverage, without PG or browsers."""

import ast
import copy
import re
from pathlib import Path
from typing import Any

import pytest

from scripts.check_m3_contracts import FILES, validate_reports
from scripts.pg_ci_evidence import partition
from scripts.pg_diagnostic import combined_groups, run_combined
from tests.test_pg_diag_partition import collection

pytestmark = pytest.mark.offline
ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    "tests/test_daily_pg.py",
    "tests/test_daily_operations_pg.py",
    "tests/test_daily_receipts_pg.py",
    "tests/test_p6_knowledge_copy_pg.py",
    "tests/test_p6_inquiry_pg.py",
    "tests/test_p6_copy_pg.py",
    "tests/test_m3_copy_app_pg.py",
    "tests/test_p6_future_pg.py",
)
LEGACY = [
    "tests/test_worker_pg.py::old",
    "tests/test_p5_woo_pg.py::old",
    "tests/test_p3_future_pg.py::old",
    "tests/test_p4_history_pg.py::old",
]


@pytest.mark.parametrize("size", [1, 3, 31])
@pytest.mark.parametrize("scope", ["all", "existing", "phase3"])
def test_complete_m3_modules_future_nodes_and_legacy_partition_once(size: int, scope: str) -> None:
    additions = [path + "::case_" + str(n) for path in MODULES for n in range(size)]
    nodes = LEGACY + additions
    groups = combined_groups(nodes)
    original = combined_groups(LEGACY)
    assert {
        label: group for label, group in groups.items() if not set(group) & set(additions)
    } == original
    assert set(partition(nodes, "existing")) == set(partition(LEGACY, "existing")) | set(additions)
    assert partition(nodes, "phase3") == partition(LEGACY, "phase3")
    records = [collection(nodes)]
    actual: list[str] = []
    commands: list[list[str]] = []

    def command(label: str, paths: list[str], cap: float) -> bool:
        assert cap == 300
        selected = [n for n in nodes if n.split("::")[0] in paths or n in paths]
        if set(selected) & set(additions):
            assert len(paths) == 1 and paths[0] in MODULES
        commands.append(paths)
        actual.extend(selected)
        records.append(collection(selected))
        return True

    run_combined(records, {}, command, scope)
    assert sorted(actual) == partition(nodes, scope)
    assert len(actual) == len(set(actual))
    assert len([paths for paths in commands if paths and paths[0] in MODULES]) == (
        len(MODULES) if scope != "phase3" else 0
    )


def test_m3_only_collection_still_splits_complete_modules() -> None:
    nodes = [path + "::one" for path in MODULES]
    assert list(combined_groups(nodes).values()) == [[node] for node in sorted(nodes)]


def reports() -> tuple[dict[str, Any], dict[str, Any]]:
    specs = [
        {
            "file": file,
            "id": file,
            "title": file,
            "tests": [
                {
                    "expectedStatus": "passed",
                    "annotations": [],
                    "projectName": "",
                    "status": "expected",
                    "results": [{"status": "passed", "retry": 0}],
                }
            ],
        }
        for file in sorted(FILES)
    ]
    executed: dict[str, Any] = {
        "errors": [],
        "suites": [{"specs": specs}],
        "stats": {"expected": len(specs), "skipped": 0, "unexpected": 0, "flaky": 0},
    }
    listed = copy.deepcopy(executed)
    for spec in listed["suites"][0]["specs"]:
        spec["tests"][0]["results"] = []
    return listed, executed


@pytest.mark.parametrize(
    "damage",
    [
        None,
        "missing_file",
        "unknown_file",
        "skip",
        "expected_fail",
        "retry",
        "duplicate",
        "error",
        "missing_result",
        "stats",
        "within_file_missing",
        "bool_stats",
        "bool_retry",
    ],
)
def test_node_gate_rejects_partial_skip_retry_and_unplanned_cases(damage: str | None) -> None:
    listed, executed = reports()
    specs = executed["suites"][0]["specs"]
    test = specs[0]["tests"][0]
    if damage == "missing_file":
        specs.pop()
    if damage == "unknown_file":
        specs[0]["file"] = "daily-ui.spec.ts"
    if damage == "skip":
        test["results"][0]["status"] = "skipped"
    if damage == "expected_fail":
        test["expectedStatus"] = "failed"
    if damage == "retry":
        test["results"][0]["retry"] = 1
    if damage == "duplicate":
        specs.append(copy.deepcopy(specs[0]))
    if damage == "error":
        executed["errors"] = [{"message": "synthetic"}]
    if damage == "missing_result":
        test["results"] = []
    if damage == "stats":
        executed["stats"]["skipped"] = 1
    if damage == "bool_stats":
        executed["stats"]["skipped"] = False
    if damage == "bool_retry":
        test["results"][0]["retry"] = False
    if damage == "within_file_missing":
        extra = copy.deepcopy(listed["suites"][0]["specs"][0])
        extra["id"] = "extra-case-in-already-covered-file"
        listed["suites"][0]["specs"].append(extra)
    if damage:
        with pytest.raises(ValueError):
            validate_reports(listed, executed)
    else:
        assert validate_reports(listed, executed) == len(FILES)


def test_foundation_wires_strict_checks_after_locked_node_install_and_keeps_legacy() -> None:
    source = (ROOT / "scripts/check.py").read_text()
    tree = ast.parse(source)
    commands = next(
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "checks" for t in n.targets)
    )
    assert isinstance(commands, ast.List)
    rows = [ast.unparse(n) for n in commands.elts]
    install = next(i for i, row in enumerate(rows) if "ci" in row and "--ignore-scripts" in row)
    for module in ("scripts.check_copy_schema", "scripts.check_m3_contracts"):
        assert len([row for row in rows if module in row]) == 1
        assert next(i for i, row in enumerate(rows) if module in row) > install
    for original in ("scripts.scan_secrets", "scripts.check_docs", "offline", "typecheck", "audit"):
        assert any(original in row for row in rows)
    config = (ROOT / "frontend/playwright.m3.noserver.config.ts").read_text()
    assert set(re.findall(r'"([a-z0-9-]+\.spec\.ts)"', config)) == FILES
    assert "webServer" not in config and "process.env" not in config
    assert "forbidOnly: true" in config and "retries: 0" in config
    for name in FILES:
        text = (ROOT / "frontend/m3-tests" / name).read_text()
        assert not re.search(r"test\.(?:skip|fixme|only)\s*\(", text)
        assert not re.search(r"async\s*\(\s*\{\s*(?:page|browser|context)\b", text)
