"""Only synthetic small repositories: native probes for the reviewed public-row delta."""

import json
import secrets
import shutil
import subprocess
import sys
from functools import cache
from pathlib import Path

import pytest

from scripts import scan_secrets as scanner
from scripts.vendor_gitleaks_rules import M3_HISTORY_PUBLIC_EXCEPTIONS, m3_public_rows

ROOT = Path(__file__).resolve().parents[1]


@cache
def pinned_rows() -> tuple[tuple[str, str, str, str, str, int], ...]:
    return m3_public_rows(ROOT)[9:]


pytestmark = pytest.mark.offline


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True)


def source(commit: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", commit + ":" + path], cwd=ROOT)


def probe(repo: Path, scope: str, expected: int) -> None:
    report = repo.parent / (repo.name + "-report.json")
    command = [
        str(scanner.SCANNER),
        scope,
        ".",
        "--config",
        str(ROOT / ".gitleaks.toml"),
        "--no-banner",
        "--redact=100",
        "--report-format",
        "json",
        "--report-path",
        str(report),
    ]
    if scope == "git":
        command.append("--log-opts=--all --full-history -m --text --no-textconv --no-ext-diff")
    result = subprocess.run(command, cwd=repo, capture_output=True, timeout=30)
    assert result.returncode == expected, (scope, result.returncode)
    findings = json.loads(report.read_text()) if report.exists() else []
    assert bool(findings) == bool(expected)


def test_current_index_and_two_historical_variants_native(tmp_path: Path) -> None:
    repo = tmp_path / "small"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "synthetic@example.invalid")
    git(repo, "config", "user.name", "Synthetic public-row probe")
    historical = {(x[0], x[1], x[4]) for x in M3_HISTORY_PUBLIC_EXCEPTIONS}
    current = [x for x in pinned_rows() if (x[0], x[1], x[5]) not in historical]
    for commit, path, _, _, _, _ in current:
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source(commit, path))
    paths = [p.relative_to(repo) for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts]
    assert not scanner.woo_public_snapshot_violations(repo, paths)
    git(repo, "add", ".")
    git(repo, "commit", "-m", "current public sources")
    probe(repo, "dir", 0)
    # Build a separate index snapshot from actual staged blobs, never an index path exclusion.
    index = tmp_path / "index"
    index.mkdir()
    for relative in paths:
        target = index / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(
            subprocess.check_output(["git", "show", ":" + relative.as_posix()], cwd=repo)
        )
    assert not scanner.woo_public_snapshot_violations(index, paths)
    probe(index, "dir", 0)
    for commit, path, _, _, _, _ in [x for x in pinned_rows() if (x[0], x[1], x[5]) in historical]:
        target = repo / path
        current_bytes = target.read_bytes()
        target.write_bytes(source(commit, path))
        assert path in scanner.woo_public_snapshot_violations(repo, paths)
        git(repo, "add", ".")
        git(repo, "commit", "-m", "different reviewed historical whole row")
        target.write_bytes(current_bytes)
        assert not scanner.woo_public_snapshot_violations(repo, paths)
        git(repo, "add", ".")
        git(repo, "commit", "-m", "restore current pinned row")
    probe(repo, "git", 0)


@pytest.mark.parametrize("which", range(18))
def test_each_new_whole_row_mutation_still_blocks_native(tmp_path: Path, which: int) -> None:
    commit, path, _, _, _, line = pinned_rows()[which]
    repo = tmp_path / "mutation"
    target = repo / path
    target.parent.mkdir(parents=True)
    content = source(commit, path).decode().splitlines()
    content[line - 1 + pinned_rows()[which][3].count("\n")] += " X"
    target.write_text("\n".join(content) + "\n")
    probe(repo, "dir", 1)


@pytest.mark.parametrize("adjacent", [False, True])
def test_new_public_row_does_not_allow_generated_secret(tmp_path: Path, adjacent: bool) -> None:
    commit, path, _, row, _, line = pinned_rows()[0]
    repo = tmp_path / "generated-secret"
    target = repo / path
    target.parent.mkdir(parents=True)
    content = source(commit, path).decode().splitlines()
    sample = 'api_key = "' + secrets.token_urlsafe(32) + '"'
    if adjacent:
        content.insert(line, sample)
    else:
        content[line - 1] = row + " " + sample
    target.write_text("\n".join(content) + "\n")
    probe(repo, "dir", 1)


def test_new_exact_rows_do_not_allow_nested_paths_native(tmp_path: Path) -> None:
    repo = tmp_path / "nested"
    for commit, path, _, _, _, _ in pinned_rows():
        target = repo / "nested" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source(commit, path))
    probe(repo, "dir", 1)


def test_both_full_span_rows_line_movement_and_truncation_fail_closed(tmp_path: Path) -> None:
    commit, path, _, row, _, line = next(x for x in pinned_rows() if "\n" in x[3])
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    original = source(commit, path).decode().splitlines()
    target.write_text("\n".join(original) + "\n")
    assert not scanner.woo_public_snapshot_violations(tmp_path, [Path(path)])
    for offset in (0, 1):
        mutated = list(original)
        mutated[line - 1 + offset] += " "
        target.write_text("\n".join(mutated) + "\n")
        assert scanner.woo_public_snapshot_violations(tmp_path, [Path(path)]) == [path]
    target.write_text("\n" + "\n".join(original) + "\n")
    assert scanner.woo_public_snapshot_violations(tmp_path, [Path(path)]) == [path]

    target.write_text("\n".join(original[:line]) + "\n")
    assert scanner.woo_public_snapshot_violations(tmp_path, [Path(path)]) == [path]


def test_no_git_integration_collection_does_not_load_offline_git_sources(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    for folder in ("scripts", "tests"):
        (source_root / folder).mkdir(parents=True)
        (source_root / folder / "__init__.py").touch()
    for name in (
        "scripts/scan_secrets.py",
        "scripts/repository_files.py",
        "scripts/vendor_gitleaks_rules.py",
        "tests/test_m3_scan_compat.py",
        "tests/test_m3_scan_public_delta.py",
    ):
        shutil.copyfile(ROOT / name, source_root / name)
    (source_root / "tests/test_integration_sentinel.py").write_text(
        "import pytest\n@pytest.mark.integration\ndef test_sentinel(): pass\n"
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-m", "integration", "--collect-only", "-q"],
        cwd=source_root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert not (source_root / ".git").exists()
    assert result.returncode == 0, (result.returncode, result.stdout[-1500:], result.stderr[-500:])
    assert "test_sentinel" in result.stdout and "deselected" in result.stdout
