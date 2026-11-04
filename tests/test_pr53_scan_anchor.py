"""One reviewed V41 blob copied into the actual PR53 merge; no scope expansion."""

import hashlib
import json
import subprocess
from pathlib import Path
from typing import cast

import pytest

from scripts import scan_secrets as scanner

ROOT = Path(__file__).resolve().parents[1]
MERGE = "98ce4a1e523de5bae3eac683728d43f5c6a1c694"
SOURCE = "261f39904d8cd5a3d6ae070cdca4a7ae5cde4d6e"
PAGE = "frontend/app/v4/[[...path]]/page.tsx"
BLOB = "7e2b1229c4544eb751925f38df0ffd5a658cb060"
pytestmark = pytest.mark.offline


@pytest.fixture(scope="module")
def finding(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    directory = tmp_path_factory.mktemp("pr53-native")
    config = directory / "history.toml"
    config.write_bytes(scanner.history_config())
    report = directory / "native.json"
    result = subprocess.run(
        [
            str(scanner.SCANNER),
            "git",
            str(ROOT),
            "--config",
            str(config),
            "--redact=100",
            "--no-banner",
            "--log-level=error",
            "--report-format=json",
            "--report-path",
            str(report),
            "--ignore-gitleaks-allow",
            "--gitleaks-ignore-path",
            "/dev/null",
            f"--log-opts={MERGE}^! --full-history -m --text --no-textconv --no-ext-diff",
        ],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 1
    items = [row for row in json.loads(report.read_text()) if row["File"] == PAGE]
    assert len(items) == 1
    return cast(dict[str, object], items[0])


def test_actual_pr53_merge_reuses_exact_old_line_binding(finding: dict[str, object]) -> None:
    anchor = scanner.approved_v4_merge_copy("git", finding)
    assert anchor is not None
    assert anchor["source_commit"] == SOURCE and anchor["blob"] == BLOB
    assert anchor["finding_source"] == "63a5a4f08bad6b98fe95942598291e0714bc09da"
    assert finding["Commit"] == MERGE and finding["File"] == PAGE
    assert finding["RuleID"] == "generic-api-key"
    assert finding["Fingerprint"] == f"{MERGE}:{PAGE}:generic-api-key:9"
    assert hashlib.sha256(str(finding["Match"]).encode()).hexdigest() == (
        "896d3957535652b65e2eb532731f764c8b1d7f6eafe0bbc90df606658c4b367b"
    )
    assert finding["StartLine"] == finding["EndLine"] == 9
    assert (finding["StartColumn"], finding["EndColumn"]) == (43, 116)
    source = subprocess.check_output(["git", "show", SOURCE + ":" + PAGE], cwd=ROOT)
    prior = subprocess.check_output(["git", "show", "17f9698:" + PAGE], cwd=ROOT)
    assert source.splitlines()[8] == prior.splitlines()[8]
    assert hashlib.sha256(source.splitlines()[8]).hexdigest() == (
        "87405b72cf4ecad5f2e883918142fa6809f7b0c973fc89881eb429f190a5b64b"
    )


@pytest.mark.parametrize(
    "field", ["StartLine", "EndLine", "StartColumn", "EndColumn", "Match", "Fingerprint"]
)
def test_pr53_finding_mutation_rejected(finding: dict[str, object], field: str) -> None:
    changed = dict(finding)
    value = changed[field]
    changed[field] = value + 1 if isinstance(value, int) else str(value) + "changed"
    assert scanner.approved_v4_merge_copy("git", changed) is None


@pytest.mark.parametrize("scope", ["dir", "index"])
def test_pr53_other_scopes_rejected(finding: dict[str, object], scope: str) -> None:
    assert scanner.approved_v4_merge_copy(scope, finding) is None


def test_pr53_nonmerge_rejected(finding: dict[str, object]) -> None:
    changed = {**finding, "Commit": SOURCE}
    changed["Fingerprint"] = f"{SOURCE}:{PAGE}:generic-api-key:9"
    assert scanner.approved_v4_merge_copy("git", changed) is None


def test_pr53_whole_blob_mutation_rejected(finding: dict[str, object], tmp_path: Path) -> None:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()

    git("init", "-b", "main")
    git("config", "user.name", "Public fixture")
    git("config", "user.email", "fixture@example.invalid")
    objects = subprocess.check_output(
        ["git", "rev-parse", "--path-format=absolute", "--git-path", "objects"],
        cwd=ROOT,
        text=True,
    ).strip()
    info = tmp_path / ".git/objects/info"
    info.mkdir(exist_ok=True)
    (info / "alternates").write_text(objects + "\n")
    target = tmp_path / PAGE
    target.parent.mkdir(parents=True)
    target.write_bytes(subprocess.check_output(["git", "show", SOURCE + ":" + PAGE], cwd=ROOT))
    git("add", ".")
    git("commit", "-m", "public page")
    git("switch", "-c", "side")
    (tmp_path / "side.txt").write_text("public fixture\n")
    git("add", ".")
    git("commit", "-m", "side")
    git("switch", "main")
    target.write_bytes(target.read_bytes() + b"\n")
    git("add", ".")
    git("commit", "-m", "whole blob differs, approved span unchanged")
    git("merge", "--no-ff", "side", "-m", "true merge")
    commit = git("rev-parse", "HEAD")
    assert len(git("show", "-s", "--format=%P", "HEAD").split()) == 2
    assert git("rev-parse", "HEAD:" + PAGE) != BLOB
    changed = {**finding, "Commit": commit}
    changed["Fingerprint"] = f"{commit}:{PAGE}:generic-api-key:9"
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(scanner, "ROOT", tmp_path)
        assert scanner.approved_v4_merge_copy("git", changed) is None


def test_pr53_metadata_is_one_anchor_only() -> None:
    before = json.loads(
        subprocess.check_output(
            ["git", "show", "a1fc837:scripts/gitleaks_rules.json"],
            cwd=ROOT,
        )
    )
    after = json.loads((ROOT / "scripts/gitleaks_rules.json").read_text())
    expected = before.pop("v4_merge_copy_anchors")
    assert after.pop("v4_merge_copy_anchors") == expected + [
        {"source_commit": SOURCE, "path": PAGE, "blob": BLOB}
    ]
    assert after == before
    assert (ROOT / ".gitleaks.toml").read_bytes() == subprocess.check_output(
        ["git", "show", "a1fc837:.gitleaks.toml"],
        cwd=ROOT,
    )
