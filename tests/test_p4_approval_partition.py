"""610原approval累计超时的唯一模块两子批；Fake命令不启动PG/平台。"""

import copy
from typing import Any

import pytest

from scripts.pg_ci_evidence import G2_REQUIRED, safe_report, validate
from scripts.pg_diagnostic import combined_groups, run_combined
from tests.test_pg_ci_evidence import META
from tests.test_pg_diag_partition import collection

pytestmark = pytest.mark.offline
APPROVAL = [f"tests/test_p3_approval_pg.py::case_{n:02}" for n in range(28)]
OTHER = ["tests/test_p4_gateway_pg.py::other"]
OLD = ["tests/test_worker_pg.py::old"]
FULL = OLD + APPROVAL + OTHER


def execute(*, fail_part: int = 0, tamper: str = "") -> tuple[dict[str, Any], list[list[str]]]:
    records = [collection(FULL[::-1])]
    raw: dict[str, Any] = {
        "records": records,
        "result": "passed_no_hang_reproduced",
        "cleanup_exit": 0,
        "stopping_confirmed": True,
        "g1_complete": True,
    }
    commands: list[list[str]] = []

    def command(label: str, paths: list[str], cap: float) -> bool:
        assert cap == 300
        nodes = paths if "-part-" in label else [n for n in FULL if n.split("::")[0] in paths]
        commands.append(nodes)
        if tamper == "duplicate" and "-part-" in label:
            nodes = nodes + [nodes[0]]
        elif tamper == "missing" and "-part-" in label:
            nodes = nodes[:-1]
        records.append(collection(nodes))
        for node in nodes:
            records.append(
                {
                    "event": "pytest_progress",
                    "data": {
                        "event": "phase_end",
                        "phase": "call",
                        "nodeid": node,
                        "outcome": "passed",
                    },
                }
            )
        failed = fail_part and label.endswith(f"part-{fail_part}")
        records.append({"event": "command_end", "label": label, "exit": 137 if failed else 0})
        return not failed

    if fail_part or tamper:
        with pytest.raises(RuntimeError):
            run_combined(records, raw, command, "existing")
    else:
        run_combined(records, raw, command, "existing")
        records.extend(
            {"event": "g1_persistence", "kind": "verified", "count_one": True} for _ in range(3)
        )
        records.extend({"event": "g2_evidence", "data": {"scenario": s}} for s in G2_REQUIRED)
    return raw, commands


def test_only_approval_gets_two_fourteen_node_parts_and_complete_original_union() -> None:
    raw, commands = execute()
    assert commands == [OLD, APPROVAL[:14], APPROVAL[14:]]
    evidence = safe_report(raw, META, "existing")
    _, actual = validate(evidence)
    assert actual == sorted(OLD + APPROVAL)
    assert len(actual) == len(set(actual)) == 29
    assert combined_groups(FULL) == combined_groups(FULL[::-1])


@pytest.mark.parametrize("part", [1, 2])
def test_timeout_stops_later_commands_and_safe_evidence_remains_failed(part: int) -> None:
    raw, commands = execute(fail_part=part)
    assert len(commands) == part + 1
    with pytest.raises(ValueError):
        validate(safe_report(raw, META, "existing"))


@pytest.mark.parametrize("change", ["missing", "duplicate"])
def test_actual_subbatch_collection_cannot_drop_or_duplicate_original_nodes(change: str) -> None:
    _, commands = execute(tamper=change)
    assert commands[0] == OLD and len(commands) == 2


@pytest.mark.parametrize("change", ["label", "swap", "merge", "omit"])
def test_equal_union_cannot_forge_unreviewed_subbatch_proof(change: str) -> None:
    raw, _ = execute()
    evidence = safe_report(raw, META, "existing")
    modules = evidence["modules"]
    if change == "label":
        modules[1]["label"] += "-invented"
    elif change == "swap":
        for field in ("expected_node_ids", "actual_node_ids", "passed_node_ids"):
            modules[1][field], modules[2][field] = modules[2][field], modules[1][field]
    elif change == "merge":
        for field in ("expected_node_ids", "actual_node_ids", "passed_node_ids"):
            modules[1][field] += modules[2][field]
        modules.pop(2)
    else:
        modules.pop(2)
    with pytest.raises(ValueError):
        validate(copy.deepcopy(evidence))
