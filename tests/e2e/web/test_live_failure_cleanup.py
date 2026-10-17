"""四固定失败sink清理的自有tmp纯验证；不启资源，不删除非目标历史。"""

from pathlib import Path

import pytest

from tests.e2e.web import run_c09_n01 as n01
from tests.e2e.web.run_live_batches import LIVE_FAILURE_SINKS, clear_live_failure_sample

pytestmark = pytest.mark.offline


@pytest.mark.parametrize("stage", ("read", "write", "items", "n01"))
def test_only_selected_failure_sink_removed_and_repeat_is_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    sinks = {
        **LIVE_FAILURE_SINKS,
        "n01": "frontend/evidence/p4-c09/n01/failure-diagnostic.safe.json",
    }
    histories = (
        "frontend/evidence/b04-live/read/live-results.json",
        "frontend/evidence/p4-c09/n01/resource-stop.safe.json",
        "frontend/evidence/b02-read/failure-diagnostic.safe.json",
        "frontend/evidence/b03/failure-diagnostic.safe.json",
        "tests/e2e/web/phase4/failure-diagnostic.safe.json",
    )
    for name in (*sinks.values(), *histories):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"offline preserved placeholder")
    monkeypatch.setattr(n01, "ROOT", tmp_path)
    if stage == "n01":
        n01.clear_n01_failure_sample()
        n01.clear_n01_failure_sample()
    else:
        clear_live_failure_sample(tmp_path, stage)
        clear_live_failure_sample(tmp_path, stage)
    assert not (tmp_path / sinks[stage]).exists()
    for key, name in sinks.items():
        if key != stage:
            assert (tmp_path / name).read_bytes() == b"offline preserved placeholder"
    for name in histories:
        assert (tmp_path / name).read_bytes() == b"offline preserved placeholder"


def test_unknown_stage_and_directory_cannot_trigger_broad_cleanup(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="closed"):
        clear_live_failure_sample(tmp_path, "../other")
    directory = tmp_path / LIVE_FAILURE_SINKS["read"]
    directory.mkdir(parents=True)
    # Linux reports EISDIR; Darwin reports EPERM for unlinking a directory.
    with pytest.raises((IsADirectoryError, PermissionError)):
        clear_live_failure_sample(tmp_path, "read")
    assert directory.is_dir()
