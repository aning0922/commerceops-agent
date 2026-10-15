"""P3 combined预算分组：完整覆盖、真实collection相等、失败/截止停止后续组。"""

import pytest

from scripts import pg_diag_shutdown, pg_diagnostic

pytestmark = pytest.mark.offline

OLD = ["tests/test_worker_pg.py::test_lock", "tests/test_inventory_pg.py::test_facts"]
P3 = ["tests/test_p3_pg.py::test_session", "tests/test_p3_migration_pg.py::test_preservation"]


def collection(nodes: list[str], **changes: object) -> dict[str, object]:
    return {
        "event": "pytest_progress",
        "data": {"event": "collection", "count": len(nodes), "nodes": nodes, **changes},
    }


def test_all_collected_nodes_run_once_in_serial_bounded_module_commands() -> None:
    records = [collection(OLD + P3)]
    report: dict[str, object] = {}
    commands = []
    actual_nodes = []

    def command(label: str, paths: list[str], cap: float) -> bool:
        commands.append((label, paths, cap))
        selected = [node for node in OLD + P3 if node.split("::")[0] in paths]
        actual_nodes.extend(selected)
        records.append(collection(selected))
        return True

    pg_diagnostic.run_combined(records, report, command)
    assert [label for label, _, _ in commands] == [
        "combined-existing",
        "combined-phase3-batch-1",
    ]
    assert [cap for _, _, cap in commands] == [300, 300]
    assert set(actual_nodes) == set(OLD + P3) and len(actual_nodes) == len(set(actual_nodes))
    assert report["combined_counts"] == {
        "combined-existing": len(OLD),
        "combined-phase3-batch-1": len(P3),
    }
    assert "failed_target" not in report


def test_historical_no_phase3_keeps_one_original_command_and_empty_paths() -> None:
    records = [collection(OLD)]
    commands = []

    def command(label: str, paths: list[str], cap: float) -> bool:
        commands.append((label, paths, cap))
        records.append(collection(OLD))
        return True

    pg_diagnostic.run_combined(records, {}, command)
    assert commands == [("combined", [], 300)]


@pytest.mark.parametrize(
    "bad",
    [
        [],
        [collection([])],
        [collection(OLD, count=True)],
        [collection(OLD, count=99)],
        [collection(OLD + OLD)],
        [collection(["/outside/test.py::test_external"])],
        [collection(["tests/../other.py::test_external"])],
        [collection(OLD), collection(OLD)],
    ],
)
def test_missing_malformed_or_ambiguous_full_collection_fails_before_commands(
    bad: list[dict[str, object]],
) -> None:
    calls = []

    def command(label: str, paths: list[str], cap: float) -> bool:
        calls.append(label)
        return True

    with pytest.raises(RuntimeError):
        pg_diagnostic.run_combined(bad, {}, command)
    assert calls == []


@pytest.mark.parametrize(
    "groups",
    [
        {"combined-existing": OLD},
        {"combined-existing": OLD, "combined-phase3": P3 + [OLD[0]]},
        {"combined-existing": OLD, "combined-phase3": P3 + ["tests/extra.py::test_extra"]},
    ],
)
def test_missing_overlapping_or_extra_partition_fails_before_commands(
    monkeypatch: pytest.MonkeyPatch,
    groups: dict[str, list[str]],
) -> None:
    monkeypatch.setattr(pg_diagnostic, "combined_groups", lambda nodes: groups)
    calls = []

    def command(label: str, paths: list[str], cap: float) -> bool:
        calls.append(label)
        return True

    with pytest.raises(RuntimeError, match="coverage mismatch"):
        pg_diagnostic.run_combined([collection(OLD + P3)], {}, command)
    assert calls == []


@pytest.mark.parametrize("actual", [[], OLD[:1], [OLD[0], "tests/extra.py::test_extra"]])
def test_success_exit_cannot_hide_missing_or_changed_actual_group_collection(
    actual: list[str],
) -> None:
    records = [collection(OLD + P3)]
    calls = []
    report: dict[str, object] = {}

    def command(label: str, paths: list[str], cap: float) -> bool:
        calls.append(label)
        if actual:
            records.append(collection(actual))
        return True

    with pytest.raises(RuntimeError):
        pg_diagnostic.run_combined(records, report, command)
    assert calls == ["combined-existing"] and report["failed_target"] == "combined-existing"


def test_failed_group_stops_without_running_phase3() -> None:
    calls = []
    report: dict[str, object] = {}

    def command(label: str, paths: list[str], cap: float) -> bool:
        calls.append(label)
        return False

    with pytest.raises(RuntimeError, match="group failed"):
        pg_diagnostic.run_combined([collection(OLD + P3)], report, command)
    assert calls == ["combined-existing"] and report["failed_target"] == "combined-existing"


def test_second_group_cannot_reset_shared_absolute_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [100.0]
    cutoff = 450.0 - 75.0
    monkeypatch.setattr("scripts.pg_diag_shutdown.time.monotonic", lambda: clock[0])
    records = [collection(OLD + P3)]
    report: dict[str, object] = {}
    budgets = []
    calls = []

    def command(label: str, paths: list[str], cap: float) -> bool:
        calls.append(label)
        budgets.append(pg_diag_shutdown.remaining(cutoff, cap))
        records.append(collection(OLD))
        clock[0] = cutoff + 1
        return True

    with pytest.raises(TimeoutError, match="absolute diagnostic deadline expired"):
        pg_diagnostic.run_combined(records, report, command)
    assert budgets == [275.0]
    assert calls == ["combined-existing", "combined-phase3-batch-1"]
    assert report["failed_target"] == "combined-phase3-batch-1"


def test_approval_and_future_execution_modules_follow_actual_collection_without_skips() -> None:
    additions = [
        "tests/test_p3_approval_pg.py::approval_case",
        "tests/test_p3_execution_pg.py::execution_case",
    ]
    nodes = OLD + P3 + additions
    groups = pg_diagnostic.combined_groups(nodes[::-1])
    assert list(groups) == [
        "combined-existing",
        "combined-phase3-test_p3_approval_pg",
        "combined-phase3-batch-1",
    ]
    flattened = [node for group in groups.values() for node in group]
    assert len(flattened) == len(nodes) and set(flattened) == set(nodes)
    assert all(
        len({node.split("::")[0] for node in group}) == 1
        for label, group in groups.items()
        if label.startswith("combined-phase3-") and "batch-" not in label
    )


def test_real_ci_collection_partition_has_no_hardcoded_cardinality() -> None:
    # 大小变化和顺序不影响覆盖；不把某次271/35写成永久契约。
    nodes = [f"tests/test_inventory_pg.py::case_{n}" for n in range(7)] + P3[:1]
    groups = pg_diagnostic.combined_groups(nodes)
    flattened = [node for group in groups.values() for node in group]
    assert len(flattened) == len(nodes) and set(flattened) == set(nodes)


def test_p4_gateway_base_and_future_pg_modules_use_business_partition_with_original_caps() -> None:
    from scripts.pg_ci_evidence import partition

    p4 = ["tests/test_p4_gateway_pg.py::intake", "tests/test_p4_base_future_pg.py::projection"]
    full = OLD + P3 + p4
    assert partition(full, "existing") == sorted(OLD)
    assert partition(full, "phase3") == sorted(P3 + p4)
    records = [collection(full)]
    calls = []
    actual = []

    def command(label: str, paths: list[str], cap: float) -> bool:
        assert cap == 300
        selected = [n for n in full if n.split("::", 1)[0] in paths]
        calls.append((label, paths))
        actual.extend(selected)
        records.append(collection(selected))
        return True

    pg_diagnostic.run_combined(records, {}, command, "phase3")
    assert len(calls) == 1
    assert sorted(actual) == sorted(P3 + p4)
    assert len(actual) == len(set(actual))
    assert calls[0][0] == "combined-phase3-batch-1" and len(calls[0][1]) == 4


@pytest.mark.parametrize("scope", ["existing", "phase3"])
def test_rebalanced_complete_modules_run_once_with_original_serial_300_cap(scope: str) -> None:
    from scripts.pg_ci_evidence import partition

    moved = [f"tests/test_p3_approval_pg.py::approval_{n:02d}" for n in range(28)]
    moved += [f"tests/test_p3_execution_authority_pg.py::authority_{n}" for n in range(9)]
    moved += [f"tests/test_p3_execution_recovery_pg.py::recovery_{n}" for n in range(8)]
    moved += [f"tests/test_p4_first_create_pg.py::first_create_{n}" for n in range(3)]
    moved += [f"tests/test_p4_first_create_negatives_pg.py::negative_{n}" for n in range(7)]
    nodes = OLD + P3 + moved
    assert partition(nodes, "existing") == sorted(OLD + moved)
    assert partition(nodes, "phase3") == sorted(P3)
    records = [collection(nodes)]
    actual = []
    calls = []

    def command(label: str, paths: list[str], cap: float) -> bool:
        assert cap == 300
        # 原approval14节点命令仍传完整该分片node，不以路径重复全28。
        selected = (
            paths
            if "approval_pg-part-" in label
            else [node for node in nodes if node.split("::")[0] in paths]
        )
        actual.extend(selected)
        calls.append(label)
        records.append(collection(selected))
        return True

    pg_diagnostic.run_combined(records, {}, command, scope)
    assert sorted(actual) == partition(nodes, scope)
    assert len(actual) == len(set(actual))
    assert len(calls) == (7 if scope == "existing" else 1)


def test_small_complete_modules_batch_at_20_without_splitting_large_or_quality_modules() -> None:
    from scripts.pg_ci_evidence import partition

    modules = {
        "tests/test_p3_a_pg.py": 8,
        "tests/test_p3_b_pg.py": 12,
        "tests/test_p3_c_pg.py": 1,
        "tests/test_p3_d_pg.py": 21,
        "tests/test_p4_a_pg.py": 3,
    }
    nodes = OLD + [f"{path}::case_{n}" for path, count in modules.items() for n in range(count)]
    nodes += [f"tests/test_p3_approval_pg.py::case_{n:02d}" for n in range(28)]
    groups = pg_diagnostic.combined_groups(nodes[::-1])
    assert sorted(groups["combined-existing"]) == sorted(OLD)
    assert [len(v) for k, v in groups.items() if "approval_pg-part-" in k] == [14, 14]
    assert len(groups["combined-phase3-batch-1"]) == 20
    assert {n.split("::")[0] for n in groups["combined-phase3-batch-1"]} == set(list(modules)[:2])
    assert len(groups["combined-phase3-test_p3_d_pg"]) == 21
    assert sorted(n for v in groups.values() for n in v) == sorted(nodes)
    for group in groups.values():
        assert set(group) <= set(partition(nodes, "existing")) or set(group) <= set(
            partition(nodes, "phase3")
        )


def test_acceptance_five_nodes_keep_complete_independent_300s_command() -> None:
    acceptance = [
        "tests/test_p4_acceptance_pg.py::test_exact_schema_app_queries_and_expected_metadata_denial[0015]",
        "tests/test_p4_acceptance_pg.py::test_exact_schema_app_queries_and_expected_metadata_denial[0016]",
        "tests/test_p4_acceptance_pg.py::test_same_outer_native_full_RO_once_and_fresh_process_original_key_replay",
        "tests/test_p4_acceptance_pg.py::test_twenty_items_ordinary_ro_is_separate_from_explicit_single_recovery",
        "tests/test_p4_acceptance_pg.py::test_gateway_session_lock_held_until_actual_child_reap",
    ]
    before = [f"tests/test_p4_a09_workflow_pg.py::case_{n}" for n in range(6)]
    after = [f"tests/test_p4_clarification_pg.py::case_{n}" for n in range(9)]
    nodes = OLD + before + acceptance + after
    records = [collection(nodes)]
    commands: list[tuple[str, list[str], float]] = []
    actual: list[str] = []

    def command(label: str, paths: list[str], cap: float) -> bool:
        selected = [node for node in nodes if node.split("::", 1)[0] in paths]
        commands.append((label, paths, cap))
        actual.extend(selected)
        records.append(collection(selected))
        return True

    pg_diagnostic.run_combined(records, {}, command)
    assert commands == [
        ("combined-existing", sorted({n.split("::", 1)[0] for n in OLD}), 300),
        ("combined-phase3-test_p4_a09_workflow_pg", ["tests/test_p4_a09_workflow_pg.py"], 300),
        ("combined-phase3-test_p4_acceptance_pg", ["tests/test_p4_acceptance_pg.py"], 300),
        ("combined-phase3-test_p4_clarification_pg", ["tests/test_p4_clarification_pg.py"], 300),
    ]
    assert actual == nodes and len(actual) == len(set(actual))
    group = pg_diagnostic.combined_groups(nodes)["combined-phase3-test_p4_acceptance_pg"]
    assert group == acceptance


def test_later_phase3_batch_still_consumes_same_absolute_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nodes = OLD + [f"tests/test_p3_large_pg.py::case_{n}" for n in range(21)] + P3
    records = [collection(nodes)]
    cutoff, clock = 375.0, [100.0]
    monkeypatch.setattr("scripts.pg_diag_shutdown.time.monotonic", lambda: clock[0])
    budgets: list[float] = []
    calls: list[str] = []

    def command(label: str, paths: list[str], cap: float) -> bool:
        calls.append(label)
        budgets.append(pg_diag_shutdown.remaining(cutoff, cap))
        records.append(collection([n for n in nodes if n.split("::")[0] in paths]))
        if label != "combined-existing":
            clock[0] = cutoff + 1
        return True

    with pytest.raises(TimeoutError):
        pg_diagnostic.run_combined(records, {}, command)
    assert budgets == [275.0, 275.0]
    assert calls == [
        "combined-existing",
        "combined-phase3-test_p3_large_pg",
        "combined-phase3-batch-1",
    ]


def test_terminal_schema_nodes_are_separate_commands_without_recollecting_whole_module() -> None:
    path = "tests/test_p4_acceptance_pg.py"
    original = [f"{path}::original_{n}" for n in range(5)]
    terminal = [
        f"{path}::test_terminal_native_enrollment_same_anchor_once_and_cold_replay[{revision}]"
        for revision in ("0015", "0016")
    ]
    nearby = ["tests/test_p4_a_pg.py::before", "tests/test_p4_z_pg.py::after"]
    nodes = OLD + nearby + original + terminal[::-1]
    records = [collection(nodes)]
    commands: list[tuple[str, list[str], float]] = []
    actual: list[str] = []

    def command(label: str, paths: list[str], cap: float) -> bool:
        selected = [node for node in nodes if node in paths or node.split("::")[0] in paths]
        commands.append((label, paths, cap))
        actual.extend(selected)
        records.append(collection(selected))
        return True

    pg_diagnostic.run_combined(records, {}, command, scope="phase3")
    parts = [entry for entry in commands if "test_p4_acceptance_pg" in entry[0]]
    assert [paths for _, paths, _ in parts] == [original, terminal[:1], terminal[1:]]
    assert all(cap == 300 and path not in paths for _, paths, cap in parts)
    assert sorted(actual) == sorted(nearby + original + terminal)
    assert len(actual) == len(set(actual))
    assert not any("combined-existing" == label for label, _, _ in commands)
