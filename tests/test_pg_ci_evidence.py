"""双job实际集合/元数据/完整性负例；纯离线，不启动PG或Docker。"""

import copy
from pathlib import Path
from typing import Any

import pytest

from scripts.pg_ci_evidence import (
    EXISTING_BUSINESS_MODULES,
    FIELDS,
    G2_REQUIRED,
    LOCK_FILES,
    canonical_nodes,
    nodes_hash,
    partition,
    safe_report,
    verify_pair,
)
from scripts.pg_diagnostic import run_combined
from tests.test_pg_diag_partition import collection

pytestmark = pytest.mark.offline
OLD = ["tests/test_worker_pg.py::worker", "tests/test_inventory_pg.py::facts"]
P3 = ["tests/test_p3_future_pg.py::future", "tests/test_p3_other_pg.py::other"]
FULL = OLD + P3
META = {
    "source_sha": "a" * 40,
    "source_tree": "b" * 40,
    "fingerprints": {
        "files": {p: "c" * 64 for p in LOCK_FILES},
        "binaries": {p: "c" * 64 for p in ("uv", "node", "gitleaks")},
        "runtime": {
            "python": "3.12.13",
            "uv": "uv 0.11.25",
            "node": "v24.21.0",
            "gitleaks": "8.30.1",
        },
    },
}


def report(scope: str) -> dict[str, Any]:
    records = [collection(FULL[::-1])]
    raw: dict[str, Any] = {
        "records": records,
        "result": "passed_no_hang_reproduced",
        "cleanup_exit": 0,
        "stopping_confirmed": True,
        "g1_complete": scope == "existing",
        "unexpected_raw": "not-exported",
    }

    def command(label: str, paths: list[str], cap: float) -> bool:
        assert cap == 300
        selected = [n for n in FULL if n.split("::")[0] in paths or n in paths]
        records.append(collection(selected))
        for node in selected:
            for phase in ["setup", "call", "teardown"]:
                records.append(
                    {
                        "event": "pytest_progress",
                        "data": {
                            "event": "phase_end",
                            "phase": phase,
                            "nodeid": node,
                            "outcome": "passed",
                        },
                    }
                )
        records.append({"event": "command_end", "label": label, "exit": 0})
        return True

    run_combined(records, raw, command, scope)
    if scope == "existing":
        records.extend(
            {"event": "g1_persistence", "kind": "verified", "count_one": True} for _ in range(3)
        )
        records.extend({"event": "g2_evidence", "data": {"scenario": s}} for s in G2_REQUIRED)
    return safe_report(raw, META, scope)


def test_complete_dynamic_partitions_pair_and_export_only_closed_metadata() -> None:
    a, b = report("existing"), report("phase3")
    assert set(a) == FIELDS and "records" not in a and "unexpected_raw" not in a
    assert a["full_node_ids"] == b["full_node_ids"] == sorted(FULL)
    assert a["actual_node_ids"] == sorted(OLD) and b["actual_node_ids"] == sorted(P3)
    assert len(b["modules"]) == 1  # 完整小模块合批，仍核每个实际node。
    verify_pair(a, b)


@pytest.mark.parametrize("scope", ["existing", "phase3"])
def test_selected_job_executes_its_exact_partition_once(scope: str) -> None:
    raw: dict[str, object] = {}
    records = [collection(FULL)]
    actual = []

    def command(label: str, paths: list[str], cap: float) -> bool:
        selected = [n for n in FULL if n.split("::")[0] in paths]
        actual.extend(selected)
        records.append(collection(selected))
        return True

    run_combined(records, raw, command, scope)
    assert sorted(actual) == partition(FULL, scope) and len(actual) == len(set(actual))


@pytest.mark.parametrize(
    "field", ["source_sha", "source_tree", "fingerprints", "full_node_ids_sha256"]
)
def test_mismatched_exact_source_or_tool_lock_or_full_digest_fails(field: str) -> None:
    a, b = report("existing"), report("phase3")
    if field == "fingerprints":
        b[field]["files"]["uv.lock"] = "d" * 64
    else:
        b[field] = "d" * (40 if field in ("source_sha", "source_tree") else 64)
    with pytest.raises(ValueError):
        verify_pair(a, b)


def test_same_count_different_complete_node_set_and_hash_cannot_pair() -> None:
    a, b = report("existing"), report("phase3")
    b["full_node_ids"] = sorted([*OLD, "tests/test_p3_approval_pg.py::different", P3[1]])
    b["full_node_ids_sha256"] = nodes_hash(b["full_node_ids"])
    b["selected_node_ids"] = b["actual_node_ids"] = sorted(
        ["tests/test_p3_approval_pg.py::different", P3[1]]
    )
    # 即使同时更新单job选择/模块，两个job的完整集合仍必须完全相同。
    for module in b["modules"]:
        if module["label"] == "combined-phase3-test_p3_approval_pg":
            for key in ("expected_node_ids", "actual_node_ids", "passed_node_ids"):
                module[key] = ["tests/test_p3_approval_pg.py::different"]
    with pytest.raises(ValueError):
        verify_pair(a, b)


@pytest.mark.parametrize(
    "change", ["missing", "extra", "duplicate", "overlap", "same_count_change"]
)
def test_wrong_actual_execution_union_is_rejected(change: str) -> None:
    a, b = report("existing"), report("phase3")
    if change == "missing":
        b["actual_node_ids"] = b["actual_node_ids"][:1]
    elif change == "extra":
        b["actual_node_ids"].append("tests/test_p3_extra_pg.py::extra")
    elif change == "duplicate":
        b["actual_node_ids"].append(P3[0])
    elif change == "overlap":
        b["actual_node_ids"].append(OLD[0])
    else:
        b["actual_node_ids"][0] = "tests/test_p3_approval_pg.py::different"
    with pytest.raises(ValueError):
        verify_pair(a, b)


@pytest.mark.parametrize(
    "change",
    [
        "failed",
        "unconfirmed",
        "cleanup",
        "bool_exit",
        "missing_module",
        "failed_module",
        "unexecuted",
        "wrong_label",
        "raw_field",
        "module_field",
    ],
)
def test_failures_and_untrusted_extra_fields_cannot_be_paired(change: str) -> None:
    a, b = report("existing"), report("phase3")
    if change == "failed":
        b["result"] = False
    elif change == "unconfirmed":
        b["stopping_confirmed"] = False
    elif change == "cleanup":
        b["cleanup_exit"] = 1
    elif change == "bool_exit":
        b["cleanup_exit"] = False
    elif change == "missing_module":
        b["modules"].pop()
    elif change == "failed_module":
        b["modules"][0]["exit_code"] = 137
    elif change == "unexecuted":
        b["modules"][0]["passed_node_ids"] = []
    elif change == "wrong_label":
        b["modules"][0]["label"] = "combined-other"
    elif change == "raw_field":
        b["unexpected"] = "must-reject"
    else:
        b["modules"][0]["unexpected"] = "must-reject"
    with pytest.raises(ValueError):
        verify_pair(a, b)


@pytest.mark.parametrize(
    "field,value", [("g1_complete", False), ("g1_verified_count", 2), ("g2_scenarios", [])]
)
def test_existing_complete_g1_g2_required(field: str, value: object) -> None:
    a, b = report("existing"), report("phase3")
    a[field] = value
    with pytest.raises(ValueError):
        verify_pair(a, b)


def test_phase3_cannot_claim_existing_smoke_or_reuse_same_scope() -> None:
    a, b = report("existing"), report("phase3")
    b["g1_complete"] = True
    with pytest.raises(ValueError):
        verify_pair(a, b)
    with pytest.raises(ValueError):
        verify_pair(a, copy.deepcopy(a))


@pytest.mark.parametrize("nodes", [[], OLD, P3, FULL + [FULL[0]]])
def test_invalid_empty_or_duplicate_scope_partition_fails(nodes: list[str]) -> None:
    with pytest.raises(ValueError):
        partition(nodes, "phase3")


def test_scope_enum_is_closed_and_node_order_is_canonical() -> None:
    assert canonical_nodes(FULL[::-1]) == sorted(FULL)
    with pytest.raises(ValueError):
        partition(FULL, "invented")


def test_artifact_nested_raw_module_fields_are_not_exported() -> None:
    raw = {
        "full_node_ids": FULL,
        "combined_modules": [
            {
                "label": "combined-existing",
                "expected_node_ids": OLD,
                "actual_node_ids": OLD,
                "passed_node_ids": OLD,
                "exit_code": 0,
                "result": True,
                "unexpected": "never-export",
            }
        ],
    }
    exported = safe_report(raw, META, "existing")
    assert set(exported) == FIELDS and "unexpected" not in exported["modules"][0]


def test_cli_rejects_mutually_consistent_artifacts_from_another_checkout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    from scripts import pg_ci_evidence

    a = tmp_path / "existing.json"
    b = tmp_path / "phase3.json"
    a.write_text(json.dumps(report("existing")))
    b.write_text(json.dumps(report("phase3")))
    monkeypatch.setattr("sys.argv", ["pair", str(a), str(b)])
    with pytest.raises(ValueError, match="checker exact checkout"):
        pg_ci_evidence.main()


def test_runtime_binary_digest_drift_is_rejected_even_when_versions_agree() -> None:
    a, b = report("existing"), report("phase3")
    b["fingerprints"]["binaries"]["uv"] = "d" * 64
    with pytest.raises(ValueError, match="mismatch"):
        verify_pair(a, b)


@pytest.mark.parametrize("scope", ["existing", "phase3"])
def test_mixed_group_cannot_drop_selected_scope_before_any_command(
    scope: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import pg_diagnostic

    monkeypatch.setattr(pg_diagnostic, "combined_groups", lambda nodes: {"mixed": FULL})
    calls = []

    def command(label: str, paths: list[str], cap: float) -> bool:
        calls.append(label)
        return True

    with pytest.raises(RuntimeError, match="selected scope coverage mismatch"):
        run_combined([collection(FULL)], {}, command, scope)
    assert calls == []


def test_p4_modules_are_in_the_paired_business_partition_without_losing_old_nodes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p4 = ["tests/test_p4_gateway_pg.py::message", "tests/test_p4_base_future_pg.py::unknown"]
    nodes = FULL + p4
    existing = partition(nodes, "existing")
    business = partition(nodes, "phase3")
    assert existing == sorted(OLD)
    assert business == sorted(P3 + p4)
    assert not set(existing).intersection(business)
    assert sorted(existing + business) == sorted(nodes)
    assert nodes_hash(sorted(nodes)) != nodes_hash(FULL)
    monkeypatch.setitem(globals(), "FULL", nodes)
    a, b = report("existing"), report("phase3")
    verify_pair(a, b)
    assert a["actual_node_ids"] == sorted(OLD)
    assert b["actual_node_ids"] == sorted(P3 + p4)
    assert len(b["modules"]) == 1


def test_rebalanced_fixed_groups_still_require_exact_paired_actual_and_passed_nodes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    measured = {
        "tests/test_p4_a08_recovery_pg.py": 10,
        "tests/test_p4_a08_scope_pg.py": 1,
        "tests/test_p4_a08_workflow_pg.py": 5,
        "tests/test_p4_clarification_pg.py": 9,
        "tests/test_p4_controlled_worker_pg.py": 2,
        "tests/test_p4_delivery_pg.py": 5,
        "tests/test_p4_explicit_ro_pg.py": 3,
        "tests/test_p4_history_pg.py": 14,
        "tests/test_p4_read_reply_parent_pg.py": 9,
    }
    moved = [f"{path}::case_{n}" for path, count in measured.items() for n in range(count)]
    monkeypatch.setitem(globals(), "FULL", FULL + moved)
    a, b = report("existing"), report("phase3")
    assert a["actual_node_ids"] == sorted(OLD + moved)
    assert b["actual_node_ids"] == sorted(P3)
    assert [(m["label"], len(m["expected_node_ids"])) for m in a["modules"]][1:] == [
        ("combined-existing-p4-a08-recovery", 16),
        ("combined-existing-p4-clarification-delivery", 19),
        ("combined-existing-p4-verified-history", 14),
        ("combined-existing-p4-read-reply-parent", 9),
    ]
    verify_pair(a, b)
    missing = copy.deepcopy(a)
    missing["modules"][1]["passed_node_ids"].pop()
    with pytest.raises(ValueError):
        verify_pair(missing, b)
    crossed = copy.deepcopy(b)
    crossed["actual_node_ids"].append(moved[0])
    with pytest.raises(ValueError):
        verify_pair(a, crossed)


def test_six_complete_business_modules_move_with_approval_shards_and_exact_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    moved = [f"tests/test_p3_approval_pg.py::case_{n:02d}" for n in range(28)]
    moved += [f"tests/test_p3_execution_authority_pg.py::case_{n:02d}" for n in range(9)]
    moved += [f"tests/test_p3_execution_recovery_pg.py::case_{n:02d}" for n in range(8)]
    moved += [f"tests/test_p4_first_create_pg.py::case_{n:02d}" for n in range(3)]
    moved += [f"tests/test_p4_first_create_negatives_pg.py::case_{n:02d}" for n in range(7)]
    moved += [f"tests/test_p4_template_results_pg.py::case_{n:02d}" for n in range(9)]
    assert {node.split("::")[0] for node in moved} == EXISTING_BUSINESS_MODULES
    monkeypatch.setitem(globals(), "FULL", FULL + moved)
    a, b = report("existing"), report("phase3")
    assert a["actual_node_ids"] == sorted(OLD + moved)
    assert b["actual_node_ids"] == sorted(P3)
    assert len(a["modules"]) == 6
    approval = [m for m in a["modules"] if "approval_pg-part-" in m["label"]]
    assert [len(m["expected_node_ids"]) for m in approval] == [14, 14]
    verify_pair(a, b)
    for change in ("omit", "wrong_label", "failed", "unpassed", "duplicate"):
        bad = copy.deepcopy(a)
        if change == "omit":
            bad["modules"].pop()
        elif change == "wrong_label":
            bad["modules"][1]["label"] = "combined-phase3-test_p3_approval_pg-part-9"
        elif change == "failed":
            bad["modules"][1]["exit_code"] = 137
        elif change == "unpassed":
            bad["modules"][1]["passed_node_ids"].pop()
        else:
            bad["modules"].append(copy.deepcopy(bad["modules"][1]))
        with pytest.raises(ValueError):
            verify_pair(bad, b)
