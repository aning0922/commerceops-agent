"""M3 pinned public rows: real scanner boundaries in isolated synthetic repositories."""

import hashlib
import json
import re
import secrets
import subprocess
import sys
import tomllib
from functools import cache
from pathlib import Path

import pytest
import tomli_w

from scripts import scan_secrets as scanner
from scripts.vendor_gitleaks_rules import (
    M3_HISTORY_PUBLIC_EXCEPTIONS,
    M3_PUBLIC_EXCEPTIONS,
    M3_SPAN_PUBLIC_EXCEPTIONS,
    m2_consumer_rows,
    m2_public_rows,
    m3_public_line_regex,
    m3_public_rows,
)

ROOT = Path(__file__).resolve().parents[1]


@cache
def pinned_rows() -> tuple[tuple[str, str, str, str, str, int], ...]:
    return m3_public_rows(ROOT)


pytestmark = pytest.mark.offline


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Synthetic M3 check")
    git(tmp_path, "config", "user.email", "synthetic@example.invalid")
    return tmp_path


@pytest.mark.parametrize("which", range(9))
@pytest.mark.parametrize(
    "scenario",
    [
        "exact",
        "byte",
        "index_only",
        "moved_line",
        "other_path",
        "nested_path",
        "history_byte",
        "history_nested",
        "adjacent_generic",
        "same_line_generic",
        "other_rule",
        "merge_exact",
    ],
)
def test_m3_exact_rows_remain_scoped(repository: Path, which: int, scenario: str) -> None:
    _, filename, _, original, _, line = pinned_rows()[which]
    relative = filename
    if scenario == "other_path":
        relative += ".other"
    if scenario in {"nested_path", "history_nested"}:
        relative = "nested/" + filename
    path = repository / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    # Include both independently pinned rows when they share a file.
    rows = [""] * max(item[5] for item in pinned_rows() if item[1] == filename)
    for _, name, _, row, _, number in pinned_rows():
        if name == filename:
            rows[number - 1] = row
    if scenario in {"byte", "index_only", "history_byte"}:
        rows[line - 1] += " "
    if scenario == "moved_line":
        rows.insert(0, "")
    value = ""
    if scenario in {"adjacent_generic", "same_line_generic", "other_rule"}:
        value = secrets.token_urlsafe(32)
        extra = f'api_key = "{value}"'
        if scenario == "other_rule":
            value = "".join(["gh", "p_"]) + secrets.token_hex(18)
            extra = f'github_token = "{value}"'
        if scenario == "same_line_generic":
            rows[line - 1] += " " + extra
        else:
            rows.append(extra)
    path.write_text("\n".join(rows) + "\n")
    git(repository, "add", ".")
    git(repository, "commit", "-m", "synthetic pinned-row boundary")
    if scenario in {"index_only", "history_byte"}:
        rows[line - 1] = original
        path.write_text("\n".join(rows) + "\n")
        if scenario == "history_byte":
            git(repository, "add", ".")
            git(repository, "commit", "-m", "restore current row")
    if scenario == "history_nested":
        path.unlink()
        git(repository, "add", "-u")
        git(repository, "commit", "-m", "remove current nested row")
    if scenario == "merge_exact":
        git(repository, "switch", "-c", "side")
        (repository / "side.txt").write_text("public side\n")
        git(repository, "add", ".")
        git(repository, "commit", "-m", "public side")
        git(repository, "switch", "main")
        (repository / "main.txt").write_text("public main\n")
        git(repository, "add", ".")
        git(repository, "commit", "-m", "public main")
        git(repository, "merge", "--no-ff", "side", "-m", "synthetic merge")
    result = subprocess.run(
        [sys.executable, "-m", "scripts.scan_secrets", "--repo", str(repository)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = result.stdout + result.stderr
    assert original not in output
    if value:
        assert value not in output
    if scenario in {"exact", "merge_exact"}:
        assert result.returncode == 0, output
        assert "git: findings=0, exit=0" in output
    else:
        assert result.returncode == 1, output
        if scenario in {"byte", "index_only", "moved_line", "same_line_generic"}:
            assert "BLOCK reviewed-public-row-changed" in output
        if scenario in {"history_byte", "history_nested"}:
            assert '"scope": "git"' in output
        if scenario == "index_only":
            assert '"scope": "index"' in output
            assert '"scope": "dir"' not in output
        if scenario == "other_rule":
            assert '"rule": "github-pat"' in output


@pytest.mark.parametrize("which", range(9))
@pytest.mark.parametrize(
    "mutation", ["path", "regex", "condition", "target", "commit", "line", "digest", "source_path"]
)
def test_m3_provenance_cannot_be_broadened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, which: int, mutation: str
) -> None:
    (tmp_path / "scripts").mkdir()
    config = tomllib.loads((ROOT / ".gitleaks.toml").read_text())
    generic = next(rule for rule in config["rules"] if rule["id"] == "generic-api-key")
    allowance = generic["allowlists"][16 + which]
    provenance = json.loads((ROOT / "scripts/gitleaks_rules.json").read_text())
    evidence = provenance["exceptions"][17 + which]
    if mutation == "path":
        allowance["paths"] = [".*"]
    elif mutation == "regex":
        allowance["regexes"] = [".*"]
    elif mutation == "condition":
        allowance["condition"] = "OR"
    elif mutation == "target":
        allowance["regexTarget"] = "secret"
    elif mutation == "commit":
        evidence["source_commit"] = "0" * 40
    elif mutation == "line":
        evidence["source_line"] += 1
    elif mutation == "source_path":
        evidence["source_path"] += ".other"
    else:
        evidence["exact_line_sha256"] = "0" * 64
    content = tomli_w.dumps(config).encode()
    provenance["config_sha256"] = hashlib.sha256(content).hexdigest()
    (tmp_path / ".gitleaks.toml").write_bytes(content)
    (tmp_path / "scripts/gitleaks_rules.json").write_text(json.dumps(provenance))
    # Keep immutable source retrieval on the real repository; mutate only the config under test.
    m2_rows = m2_public_rows(ROOT)
    consumer_rows = m2_consumer_rows(ROOT)
    monkeypatch.setattr(scanner, "m2_public_rows", lambda _: m2_rows)
    monkeypatch.setattr(scanner, "m2_consumer_rows", lambda _: consumer_rows)
    monkeypatch.setattr(scanner, "m3_public_rows", lambda _: pinned_rows())
    monkeypatch.setattr(scanner, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="invalid scanner rules"):
        scanner.validate_rules()


def test_m3_sources_are_pinned_and_missing_source_fails_closed(tmp_path: Path) -> None:
    assert len(M3_PUBLIC_EXCEPTIONS) == 25
    assert len(M3_HISTORY_PUBLIC_EXCEPTIONS) == 2
    assert len(M3_SPAN_PUBLIC_EXCEPTIONS) == 1
    assert len(pinned_rows()) == 28
    assert len(scanner.APPROVED_TEST_HISTORY) == 20
    for _, _, _, row, digest, _ in pinned_rows():
        assert hashlib.sha256(row.encode()).hexdigest() == digest
    git(tmp_path, "init", "-b", "main")
    with pytest.raises(ValueError, match="invalid M3 public source"):
        m3_public_rows(tmp_path)


@pytest.mark.parametrize("which", range(9))
def test_m3_encoded_regex_matches_only_unchanged_source_bytes(which: int) -> None:
    row = pinned_rows()[which][3]
    pattern = m3_public_line_regex(row)
    assert re.fullmatch(pattern, row)
    assert re.fullmatch(pattern, "\n" + row)
    assert re.fullmatch(pattern, "\r\n" + row)
    for position in range(len(row)):
        replacement = "X" if row[position] != "X" else "Y"
        assert not re.fullmatch(pattern, row[:position] + replacement + row[position + 1 :])
    assert not re.fullmatch(pattern, row + " ")
