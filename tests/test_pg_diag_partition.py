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
        "combined-phase3-test_p3_migration_pg",
        "combined-phase3-test_p3_pg",
    ]
    assert [cap for _, _, cap in commands] == [300, 300, 300]
    assert set(actual_nodes) == set(OLD + P3) and len(actual_nodes) == len(set(actual_nodes))
    assert report["combined_counts"] == {
        "combined-existing": len(OLD),
        "combined-phase3-test_p3_migration_pg": 1,
        "combined-phase3-test_p3_pg": 1,
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
    assert calls == ["combined-existing", "combined-phase3-test_p3_migration_pg"]
    assert report["failed_target"] == "combined-phase3-test_p3_migration_pg"


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
        "combined-phase3-test_p3_execution_pg",
        "combined-phase3-test_p3_migration_pg",
        "combined-phase3-test_p3_pg",
    ]
    flattened = [node for group in groups.values() for node in group]
    assert len(flattened) == len(nodes) and set(flattened) == set(nodes)
    assert all(
        len({node.split("::")[0] for node in group}) == 1
        for label, group in groups.items()
        if label.startswith("combined-phase3-")
    )


def test_real_ci_collection_partition_has_no_hardcoded_cardinality() -> None:
    # 大小变化和顺序不影响覆盖；不把某次271/35写成永久契约。
    nodes = [f"tests/test_inventory_pg.py::case_{n}" for n in range(7)] + P3[:1]
    groups = pg_diagnostic.combined_groups(nodes)
    flattened = [node for group in groups.values() for node in group]
    assert len(flattened) == len(nodes) and set(flattened) == set(nodes)
