"""固定N01输入/输出边界纯验证；只用自有临时文件，不启PG/网络。"""

import hashlib
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.e2e.web import run_c09_n01 as runner

pytestmark = pytest.mark.offline
OUTPUTS = (
    "frontend/evidence/p4-c09/n01/live-results.json",
    "frontend/evidence/p4-c09/n01/pg-invariants.safe.json",
    "frontend/evidence/p4-c09/n01/resource-stop.safe.json",
    "frontend/evidence/p4-c09/n01/failure-diagnostic.safe.json",
)
OTHER_INPUTS = (
    "tests/e2e/web/phase4/n01.fixture.json",
    "frontend/evidence/p4-c09/contract-results.json",
    "frontend/evidence/p4-c09/n01/cleanup.safe.json",
    "tests/e2e/web/phase4/resource-stop.safe.json",
)


def write(root: Path, name: str, body: bytes) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


@pytest.fixture
def owned_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    for name in (*runner.REQUIRED_SOURCE_FILES, *OTHER_INPUTS):
        write(tmp_path, name, b"deterministic offline source placeholder")
    return tmp_path


def capture() -> dict[str, str]:
    # Git can retain an output path after the CI removes its old sample.
    tracked = "\n".join((*OTHER_INPUTS, *OUTPUTS))
    with patch.object(subprocess, "check_output", return_value=tracked) as git:
        result = runner.source_manifest()
        git.assert_called_once_with(
            ["git", "ls-files", "frontend", "tests/e2e/web"], cwd=runner.ROOT, text=True
        )
        return result


@pytest.mark.parametrize("output", OUTPUTS)
def test_mutable_output_missing_created_changed_and_removed_is_not_input(
    owned_tree: Path, output: str
) -> None:
    before = capture()
    write(owned_tree, output, b"old derived result")
    assert capture() == before
    write(owned_tree, output, b"new derived result")
    assert capture() == before
    (owned_tree / output).unlink()
    assert capture() == before
    assert not set(OUTPUTS).intersection(before)


@pytest.mark.parametrize("source", (*runner.REQUIRED_SOURCE_FILES, *OTHER_INPUTS))
def test_code_fixtures_and_other_evidence_remain_bound_and_changes_detected(
    owned_tree: Path, source: str
) -> None:
    before = capture()
    changed = b"changed real input placeholder"
    write(owned_tree, source, changed)
    after = capture()
    assert source in before and source in after
    assert after[source] == hashlib.sha256(changed).hexdigest()
    assert after[source] != before[source]
    assert {name for name in before if before[name] != after[name]} == {source}


def test_missing_required_source_fails_closed_instead_of_skipping(owned_tree: Path) -> None:
    (owned_tree / "frontend/lib/p4-n01.ts").unlink()
    with pytest.raises(FileNotFoundError):
        capture()
