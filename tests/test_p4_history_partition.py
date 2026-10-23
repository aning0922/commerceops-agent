"""history完整collection分片及配对拒绝；不启动PG。"""

import copy

import pytest

from scripts.pg_ci_evidence import safe_report, validate
from scripts.pg_diagnostic import combined_groups
from tests import test_p4_approval_partition as support
from tests.test_pg_ci_evidence import META

pytestmark = pytest.mark.offline
HISTORY = [f"tests/test_p4_history_pg.py::case_{n:02d}" for n in range(14)]
OTHER = ["tests/test_p4_read_reply_parent_pg.py::parent"]
FULL = support.OLD + HISTORY + OTHER + support.OTHER


def test_read_parent_complete_eleven_nodes_run_six_plus_five_and_pair_exactly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = [f"tests/test_p4_read_reply_parent_pg.py::case_{n:02d}" for n in range(11)]
    monkeypatch.setattr(support, "FULL", support.OLD + parent + support.OTHER)
    raw, commands = support.execute()
    assert commands == [support.OLD, parent[6:]]
    evidence = safe_report(raw, META, "existing")
    _, actual = validate(evidence)
    assert actual == sorted(support.OLD + parent[6:])
    merged = copy.deepcopy(evidence)
    for field in ("expected_node_ids", "actual_node_ids", "passed_node_ids"):
        merged["modules"][1][field] = parent
    with pytest.raises(ValueError):
        validate(merged)


def test_history_runs_complete_sorted_seven_node_parts_with_original_pairing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(support, "FULL", FULL)
    raw, commands = support.execute()
    assert commands == [support.OLD, HISTORY[:7], HISTORY[7:]]
    evidence = safe_report(raw, META, "existing")
    _, actual = validate(evidence)
    assert actual == sorted(support.OLD + HISTORY)
    assert combined_groups(FULL) == combined_groups(FULL[::-1])


@pytest.mark.parametrize("count", [1, 7, 8, 14, 15, 21])
def test_history_future_collection_is_complete_disjoint_and_bounded(count: int) -> None:
    nodes = [f"tests/test_p4_history_pg.py::case_{n:02d}" for n in range(count)]
    groups = combined_groups(nodes[::-1])
    assert [node for group in groups.values() for node in group] == nodes
    assert all(1 <= len(group) <= 7 for group in groups.values())


@pytest.mark.parametrize("part", [1, 2])
def test_history_timeout_preserves_failure_and_does_not_start_later_groups(
    monkeypatch: pytest.MonkeyPatch, part: int
) -> None:
    monkeypatch.setattr(support, "FULL", FULL)
    raw, commands = support.execute(fail_part=part)
    assert len(commands) == part + 1
    with pytest.raises(ValueError):
        validate(safe_report(raw, META, "existing"))


@pytest.mark.parametrize("change", ["label", "swap", "merge", "omit"])
def test_history_equal_union_cannot_forge_seven_node_part_evidence(
    monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    monkeypatch.setattr(support, "FULL", FULL)
    raw, _ = support.execute()
    evidence = safe_report(raw, META, "existing")
    modules = evidence["modules"]
    if change == "label":
        modules[1]["label"] += "-unreviewed"
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
