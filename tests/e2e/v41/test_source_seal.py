"""Real temporary Git bytes and executable drift; no runtime resources."""

import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from .owned_manifest import OwnedManifest
from .source_seal import NEXT_ENV_BYTES, NEXT_ENV_PATH, NEXT_ENV_SHA256, matches_source, snapshot
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
    assert not matches_source(before, snapshot(root, [tool]))


def test_new_next_route_is_rejected_but_named_outputs_are_excluded(
    bound: tuple[OwnedManifest, Path, datetime],
) -> None:
    _, root, _ = bound
    before = snapshot(root, [])
    generated = root / "frontend/.next/cache/output.js"
    generated.parent.mkdir(parents=True)
    generated.write_text("generated output")
    assert snapshot(root, []) == before
    added = root / "frontend/app/extra/page.tsx"
    added.parent.mkdir(parents=True)
    added.write_text("new runtime input")
    with pytest.raises(ValueError, match="UNAPPROVED_UNTRACKED_RUNTIME_INPUT"):
        snapshot(root, [])


def test_only_exact_generated_declaration_can_appear_between_seals(
    bound: tuple[OwnedManifest, Path, datetime],
) -> None:
    _, root, _ = bound
    before = snapshot(root, [])
    path = root / NEXT_ENV_PATH
    path.write_bytes(NEXT_ENV_BYTES)
    path.chmod(0o600)
    after = snapshot(root, [])
    assert before["generated_inputs"][NEXT_ENV_PATH] == {"status": "ABSENT", "sha256": None}
    assert after["generated_inputs"][NEXT_ENV_PATH]["sha256"] == NEXT_ENV_SHA256
    assert after["generated_inputs"][NEXT_ENV_PATH]["status"] == "PRESENT_CANONICAL"
    assert before != after and matches_source(before, after)
    assert matches_source(after, snapshot(root, []))
    assert not matches_source(after, before)
    changed = {**after, "head": "f" * 40}
    assert not matches_source(before, changed)
    path.write_bytes(NEXT_ENV_BYTES.replace(b"root-params", b"other-input"))
    with pytest.raises(ValueError, match="CANONICAL_NEXT_ENV"):
        snapshot(root, [])
    path.unlink()
    target = root / "public-declaration.txt"
    target.write_bytes(NEXT_ENV_BYTES)
    path.symlink_to(target)
    with pytest.raises(OSError):
        snapshot(root, [])


def test_generated_declaration_rejects_unsafe_mode_and_does_not_exempt_other_paths(
    bound: tuple[OwnedManifest, Path, datetime],
) -> None:
    _, root, _ = bound
    path = root / NEXT_ENV_PATH
    path.write_bytes(NEXT_ENV_BYTES)
    path.chmod(0o666)
    with pytest.raises(ValueError, match="CANONICAL_NEXT_ENV_FILE"):
        snapshot(root, [])
    path.chmod(0o644)
    before = snapshot(root, [])
    assert matches_source(before, before)
    other = path.with_name("other-next-env.d.ts")
    other.write_bytes(NEXT_ENV_BYTES)
    with pytest.raises(ValueError, match="UNAPPROVED_UNTRACKED_RUNTIME_INPUT"):
        snapshot(root, [])
