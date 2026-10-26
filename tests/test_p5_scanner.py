"""双审M2公开行的精确例外；相邻/历史/索引秘密仍阻断且脱敏。"""

import hashlib
import json
import secrets
from pathlib import Path

import pytest
import tomli_w

from scripts import scan_secrets as scanner
from scripts.vendor_gitleaks_rules import m2_public_rows
from tests.test_quality_gates import ROOT, git, run_scan
from tests.test_quality_gates import repository as repository

pytestmark = pytest.mark.offline


@pytest.mark.parametrize("which", [0, 1])
@pytest.mark.parametrize(
    "scenario",
    [
        "exact",
        "changed_low_entropy",
        "moved_line",
        "other_path",
        "nested_same_suffix",
        "adjacent_generic",
        "same_line_generic",
        "index_only",
        "history",
    ],
)
def test_m2_public_exception_is_one_reviewed_row_not_a_file_exclusion(
    repository: Path,
    which: int,
    scenario: str,
) -> None:
    filename, _, original, _, line = m2_public_rows(ROOT)[which]
    relative = filename + ".other" if scenario == "other_path" else filename
    if scenario == "nested_same_suffix":
        relative = "nested/" + filename
    path = repository / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    row = original
    value = ""
    if scenario in {"changed_low_entropy", "index_only"}:
        row = row.replace("p3-openapi.json", "p3-openapi.jsox").replace(
            "source_task_id", "source_task_ix"
        )
        assert row != original
    if scenario in {"adjacent_generic", "same_line_generic", "history"}:
        value = secrets.token_urlsafe(32)
        row += (" " if scenario == "same_line_generic" else "\n") + f'api_key = "{value}"'
    path.write_text("\n" * (line - 1 + (scenario == "moved_line")) + row + "\n")
    git(repository, "add", ".")
    if scenario == "index_only":
        path.write_text("\n" * (line - 1) + original + "\n")
    else:
        git(repository, "commit", "-m", "synthetic M2 public boundary")
    if scenario == "history":
        path.write_text("\n" * (line - 1) + original + "\n")
        git(repository, "add", ".")
        git(repository, "commit", "-m", "retain historical synthetic credential")
    result = run_scan(repository)
    output = result.stdout + result.stderr
    assert not value or value not in output
    assert original not in output and row not in output
    assert result.returncode == (0 if scenario == "exact" else 1), output
    if scenario in {
        "changed_low_entropy",
        "moved_line",
        "nested_same_suffix",
        "same_line_generic",
        "index_only",
    }:
        assert "BLOCK reviewed-public-row-changed" in output


@pytest.mark.parametrize("which", [0, 1])
@pytest.mark.parametrize(
    "field",
    ["source_commit", "source_line", "source_path", "exact_line_sha256", "condition", "path"],
)
def test_m2_exception_provenance_and_and_scope_cannot_be_changed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    which: int,
    field: str,
) -> None:
    import tomllib

    config = tomllib.loads((ROOT / ".gitleaks.toml").read_text())
    provenance = json.loads((ROOT / "scripts/gitleaks_rules.json").read_text())
    rule = next(r for r in config["rules"] if r["id"] == "generic-api-key")
    if field == "condition":
        rule["allowlists"][6 + which]["condition"] = "OR"
    elif field == "path":
        rule["allowlists"][6 + which]["paths"] = [".*"]
    else:
        entry = provenance["exceptions"][7 + which]
        entry[field] = 1 if field == "source_line" else "changed"
    encoded = tomli_w.dumps(config).encode()
    provenance["config_sha256"] = hashlib.sha256(encoded).hexdigest()
    (tmp_path / ".gitleaks.toml").write_bytes(encoded)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/gitleaks_rules.json").write_text(json.dumps(provenance))
    monkeypatch.setattr(scanner, "ROOT", tmp_path)
    monkeypatch.setattr(scanner, "m2_public_rows", lambda _: m2_public_rows(ROOT))
    with pytest.raises(ValueError, match="invalid scanner rules"):
        scanner.validate_rules()


def test_m2_allowance_requires_the_actual_reviewed_commit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid M2 public source"):
        m2_public_rows(tmp_path)
