"""Real temporary Git bytes and executable drift; no runtime resources."""

import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from .owned_manifest import OwnedManifest
from .source_seal import snapshot
from .test_owned_manifest import bound as bound

pytestmark = pytest.mark.offline


def test_all_tracked_frontend_compose_locks_and_actual_tools_are_bound(
    bound: tuple[OwnedManifest, Path, datetime], tmp_path: Path
) -> None:
    _, root, _ = bound
    for name in ["frontend/app/page.tsx", "compose.yml", "frontend/package-lock.json"]:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("public fixture\n")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.name=QA", "-c", "user.email=qa@localhost", "commit", "-qm", "files"],
        cwd=root,
        check=True,
    )
    tool = tmp_path / "public-executable"
    tool.write_text("version one")
    before = snapshot(root, [tool])
    for name in ["frontend/app/page.tsx", "compose.yml", "frontend/package-lock.json"]:
        path = root / name
        old = path.read_bytes()
        path.write_text("dirty bytes with identical HEAD/tree\n")
        with pytest.raises(ValueError, match="ACTUAL_TRACKED_BYTES"):
            snapshot(root, [tool])
        path.write_bytes(old)
    assert snapshot(root, [tool]) == before
    tool.write_text("version two")
    assert snapshot(root, [tool]) != before
