"""V4 exact public spans: native scans and immutable provenance boundaries."""

import hashlib
import json
import secrets
import subprocess
import sys
import tomllib
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import tomli_w

from scripts import scan_secrets as scanner
from scripts.vendor_gitleaks_rules import (
    V4_PUBLIC_EXCEPTIONS,
    V4_SOURCE_COMMIT,
    v4_history_findings,
    v4_public_rows,
)

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.offline


@cache
def public_sources() -> dict[str, bytes]:
    return {
        path: subprocess.check_output(["git", "show", V4_SOURCE_COMMIT + ":" + path], cwd=ROOT)
        for path, *_ in V4_PUBLIC_EXCEPTIONS
    }


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True)


def run_scan(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.scan_secrets", "--repo", str(repo)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Synthetic V4 probe")
    git(tmp_path, "config", "user.email", "synthetic@example.invalid")
    git(tmp_path, "commit", "--allow-empty", "-m", "empty synthetic history")
    for path, value in public_sources().items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    git(tmp_path, "add", ".")
    return tmp_path


def test_exact_dir_index_native_and_history_derivation(repository: Path) -> None:
    result = run_scan(repository)
    assert result.returncode == 0, result.stdout
    assert "dir: findings=0, exit=0" in result.stdout
    assert "index: findings=0, exit=0" in result.stdout
    assert "git: findings=0, exit=0" in result.stdout
    original = tomllib.loads((ROOT / ".gitleaks.toml").read_text())
    derived = tomllib.loads(scanner.history_config().decode())
    baseline = tomllib.loads(
        subprocess.check_output(["git", "show", "7c262fb:.gitleaks.toml"], cwd=ROOT).decode()
    )
    assert derived == baseline
    assert len(derived["rules"]) == len(original["rules"]) == 222
    assert sum(len(x.get("allowlists", [])) for x in derived["rules"]) == 45
    assert sum(len(x.get("allowlists", [])) for x in original["rules"]) == 79
    assert len(scanner.APPROVED_TEST_HISTORY) == 20
    assert len(v4_history_findings()) == 13
    provenance = json.loads((ROOT / "scripts/gitleaks_rules.json").read_text())
    old = json.loads(
        subprocess.check_output(["git", "show", "7c262fb:scripts/gitleaks_rules.json"], cwd=ROOT)
    )
    assert provenance["exceptions"][:45] == old["exceptions"]
    assert provenance["historical_findings"] == old["historical_findings"]


@pytest.mark.parametrize("which", range(13))
@pytest.mark.parametrize("scenario", ["byte", "moved", "duplicate", "index_only", "new_key"])
def test_each_span_change_remains_blocking(repository: Path, which: int, scenario: str) -> None:
    path, _, line, end, *_ = V4_PUBLIC_EXCEPTIONS[which]
    target = repository / path
    rows = target.read_text().splitlines()
    original = target.read_bytes()
    if scenario in {"byte", "index_only"}:
        rows[end - 1] += " "
    elif scenario == "moved":
        rows.insert(0, "")
    elif scenario == "duplicate":
        rows.extend(rows[line - 1 : end])
    else:
        rows[end - 1] += ' api_key = "' + secrets.token_urlsafe(32) + '"'
    target.write_text("\n".join(rows) + "\n")
    if scenario == "index_only":
        git(repository, "add", ".")
        target.write_bytes(original)
    result = run_scan(repository)
    assert result.returncode == 1, result.stdout
    assert "BLOCK reviewed-public-row-changed" in result.stdout
    assert ('"scope": "index"' if scenario == "index_only" else '"scope": "dir"') in result.stdout
    if scenario == "index_only":
        assert '"scope": "dir"' not in result.stdout
    if scenario == "new_key":
        assert '"classification": "blocking"' in result.stdout


@pytest.mark.parametrize(
    "scenario", ["other_path", "nested", "adjacent", "other_rule", "wrong_commit"]
)
def test_unknown_findings_and_sources_native(repository: Path, scenario: str) -> None:
    path = V4_PUBLIC_EXCEPTIONS[0][0]
    target = repository / path
    value = secrets.token_urlsafe(32)
    if scenario in {"other_path", "nested"}:
        other = repository / ("nested/" + path if scenario == "nested" else path + ".other")
        other.parent.mkdir(parents=True, exist_ok=True)
        other.write_bytes(target.read_bytes())
    elif scenario in {"adjacent", "other_rule"}:
        with target.open("a") as stream:
            sample = 'api_key = "' + value + '"'
            if scenario == "other_rule":
                value = "".join(["gh", "p_"]) + secrets.token_hex(18)
                sample = 'github_token = "' + value + '"'
            stream.write(sample + "\n")
    else:
        git(repository, "commit", "-m", "identical bytes in an unapproved source commit")
        for name in public_sources():
            (repository / name).unlink()
        git(repository, "add", "-u")
        git(repository, "commit", "-m", "remove current public bytes")
    result = run_scan(repository)
    assert result.returncode == 1, result.stdout
    assert '"classification": "blocking"' in result.stdout
    assert value not in result.stdout
    if scenario == "wrong_commit":
        assert '"scope": "git"' in result.stdout
        assert "reviewed_public_false_positive" not in result.stdout


@pytest.mark.parametrize("which", range(13))
@pytest.mark.parametrize("field", ["path", "regex", "condition", "commit", "line", "end", "digest"])
def test_provenance_cannot_broaden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, which: int, field: str
) -> None:
    config = tomllib.loads((ROOT / ".gitleaks.toml").read_text())
    provenance = json.loads((ROOT / "scripts/gitleaks_rules.json").read_text())
    generic = next(x for x in config["rules"] if x["id"] == "generic-api-key")
    allowance = generic["allowlists"][44 + which]
    evidence = provenance["exceptions"][45 + which]
    if field == "path":
        allowance["paths"] = [".*"]
    elif field == "regex":
        allowance["regexes"] = [".*"]
    elif field == "condition":
        allowance["condition"] = "OR"
    elif field == "commit":
        evidence["source_commit"] = "0" * 40
    elif field == "line":
        evidence["source_line"] += 1
    elif field == "end":
        evidence["source_end_line"] += 1
    else:
        evidence["exact_line_sha256"] = "0" * 64
    content = tomli_w.dumps(config).encode()
    provenance["config_sha256"] = hashlib.sha256(content).hexdigest()
    (tmp_path / "scripts").mkdir()
    (tmp_path / ".gitleaks.toml").write_bytes(content)
    (tmp_path / "scripts/gitleaks_rules.json").write_text(json.dumps(provenance))
    # Mutate configuration only; immutable source readers still use the real repository.
    for name in ("m2_public_rows", "m2_consumer_rows", "m3_public_rows", "v4_public_rows"):
        rows = getattr(scanner, name)(ROOT)
        monkeypatch.setattr(scanner, name, lambda _, rows=rows: rows)
    monkeypatch.setattr(scanner, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="invalid V4 scanner rules"):
        scanner.validate_rules()


def test_immutable_source_missing_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid V4 public source"):
        v4_public_rows(tmp_path)


def test_v4_history_metadata_is_exact_git_only() -> None:
    for row in v4_history_findings():
        fake: dict[str, Any] = {
            "RuleID": row["rule"],
            "File": row["path"],
            "Commit": row["source_commit"],
            "StartLine": row["reported_line"],
            "EndLine": row["end_line"],
            "StartColumn": row["start_column"],
            "EndColumn": row["end_column"],
            "Fingerprint": row["fingerprint"],
            "Match": "unapproved",
        }
        assert not scanner.approved_v4_history_finding("git", fake)
        assert not scanner.approved_v4_history_finding("dir", fake)
        assert not scanner.approved_v4_history_finding("index", fake)


@pytest.mark.parametrize("mutation", ["missing", "old_allowance", "rule"])
def test_git_derivation_fails_closed_on_unexpected_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    content = (ROOT / ".gitleaks.toml").read_text()
    if mutation == "missing":
        content = content.replace("V4公开合同/字段/摘要；仅固定来源path与完整行/span", "changed", 1)
    elif mutation == "old_allowance":
        # A V4 marker injected into an old block must not delete an extra table.
        marker = "[[rules.allowlists]]\n"
        at = content.index(marker) + len(marker)
        end = content.index("\n", at)
        content = (
            content[:at]
            + 'description = "V4公开合同/字段/摘要；仅固定来源path与完整行/span"'
            + content[end:]
        )
    else:
        content = content.replace("[[rules]]\nid = ", "[[rules]]\nid_changed = ", 1)
    (tmp_path / ".gitleaks.toml").write_text(content)
    monkeypatch.setattr(scanner, "ROOT", tmp_path)
    with pytest.raises((ValueError, KeyError)):
        scanner.history_config()


def test_both_lines_of_multiline_public_span_are_fixed(repository: Path) -> None:
    path, _, line, end, *_ = next(x for x in V4_PUBLIC_EXCEPTIONS if x[3] > x[2])
    target = repository / path
    original = target.read_text().splitlines()
    for number in range(line, end + 1):
        rows = original.copy()
        rows[number - 1] += " "
        target.write_text("\n".join(rows) + "\n")
        assert path in scanner.woo_public_snapshot_violations(repository, [Path(path)])


@pytest.mark.parametrize(
    "commit",
    [
        V4_SOURCE_COMMIT,
        "c5f4d101339fed02c463c6dc8058bb92b15881ca",
        "75dc6d55e386d85713943df0fb7a0b3ba5fef053",
        "772f95927546dc3c648b58cd3906f91cae64c2f4",
        "46e44e5548d720bdb735e2a0f4673bdc73854de4",
        "48c30d224529319d5a9ff203429eeff86060fc00",
    ],
)
def test_additional_history_native_exact_fields_only(tmp_path: Path, commit: str) -> None:
    config = tmp_path / "history.toml"
    config.write_bytes(scanner.history_config())
    report = tmp_path / "report.json"
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
            "--log-opts=" + commit + "^! --full-history -m --text --no-textconv --no-ext-diff",
        ],
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 1
    findings = json.loads(report.read_text())
    assert len(findings) == (13 if commit == V4_SOURCE_COMMIT else 2)
    for finding in findings:
        assert scanner.approved_v4_history_finding("git", finding)
        assert not scanner.approved_v4_history_finding("dir", finding)
        assert not scanner.approved_v4_history_finding("index", finding)
        assert not scanner.approved_history_finding("git", finding)
        for key in (
            "RuleID",
            "File",
            "Commit",
            "StartLine",
            "EndLine",
            "StartColumn",
            "EndColumn",
            "Fingerprint",
            "Match",
        ):
            changed = dict(finding)
            changed[key] = (
                changed[key] + 1 if isinstance(changed[key], int) else changed[key] + "changed"
            )
            assert not scanner.approved_v4_history_finding("git", changed)
        # Identical report and fingerprint cannot pass when immutable source cannot be read.
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(scanner, "ROOT", tmp_path)
            assert not scanner.approved_v4_history_finding("git", finding)


@pytest.mark.parametrize(
    "field",
    [
        "source_commit",
        "path",
        "reported_line",
        "end_line",
        "exact_span_sha256",
        "match_sha256",
        "fingerprint",
    ],
)
def test_additional_history_provenance_rejects_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    provenance = json.loads((ROOT / "scripts/gitleaks_rules.json").read_text())
    for row in provenance["v4_additional_historical_findings"]:
        row[field] = row[field] + 1 if isinstance(row[field], int) else row[field] + "changed"
    (tmp_path / "scripts").mkdir()
    (tmp_path / ".gitleaks.toml").write_bytes((ROOT / ".gitleaks.toml").read_bytes())
    (tmp_path / "scripts/gitleaks_rules.json").write_text(json.dumps(provenance))
    for name in ("m2_public_rows", "m2_consumer_rows", "m3_public_rows"):
        rows = getattr(scanner, name)(ROOT)
        monkeypatch.setattr(scanner, name, lambda _, rows=rows: rows)
    monkeypatch.setattr(scanner, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="invalid V4 additional historical scanner finding"):
        scanner.validate_rules()


@cache
def preflight_sources() -> dict[str, bytes]:
    from scripts.vendor_gitleaks_rules import V4_PREFLIGHT_SNAPSHOTS

    return {
        row["path"]: subprocess.check_output(
            ["git", "show", row["source_commit"] + ":" + row["path"]], cwd=ROOT
        )
        for row in V4_PREFLIGHT_SNAPSHOTS
    }


def native_preflight_dir(repo: Path, report: Path, expected: int) -> None:
    result = subprocess.run(
        [
            str(scanner.SCANNER),
            "dir",
            ".",
            "--config",
            str(ROOT / ".gitleaks.toml"),
            "--redact=100",
            "--no-banner",
            "--log-level=error",
            "--report-format=json",
            "--report-path",
            str(report),
            "--ignore-gitleaks-allow",
            "--gitleaks-ignore-path",
            "/dev/null",
        ],
        cwd=repo,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == expected
    findings = json.loads(report.read_text())
    assert bool(findings) == bool(expected)


def test_preflight_all_exact_snapshots_and_preserved_config(tmp_path: Path) -> None:
    from scripts.vendor_gitleaks_rules import v4_preflight_history_findings

    for path, content in preflight_sources().items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    assert not scanner.woo_public_snapshot_violations(
        tmp_path, [Path(p) for p in preflight_sources()]
    )
    native_preflight_dir(tmp_path, tmp_path.parent / "exact.json", 0)
    old = json.loads(
        subprocess.check_output(["git", "show", "0ca8a65:scripts/gitleaks_rules.json"], cwd=ROOT)
    )
    current = json.loads((ROOT / "scripts/gitleaks_rules.json").read_text())
    assert current["exceptions"][:58] == old["exceptions"]
    for key in (
        "historical_findings",
        "v4_historical_findings",
        "v4_additional_historical_findings",
    ):
        assert current[key] == old[key]
    assert len(v4_preflight_history_findings()) == 89
    config = tomllib.loads(scanner.history_config().decode())
    baseline = tomllib.loads(
        subprocess.check_output(["git", "show", "7c262fb:.gitleaks.toml"], cwd=ROOT).decode()
    )
    assert config == baseline


@pytest.mark.parametrize("which", range(21))
def test_preflight_each_span_change_duplicate_and_secret(tmp_path: Path, which: int) -> None:
    from scripts.vendor_gitleaks_rules import V4_PREFLIGHT_SNAPSHOTS

    record = V4_PREFLIGHT_SNAPSHOTS[which]
    path = record["path"]
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    original = preflight_sources()[path].decode().splitlines()
    line, end = record["reported_line"], record["end_line"]
    for scenario in ("byte", "duplicate", "moved", "secret"):
        rows = original.copy()
        if scenario == "byte":
            rows[end - 1] += " "
        elif scenario == "duplicate":
            rows.extend(original[line - 1 : end])
        elif scenario == "moved":
            rows.insert(0, "")
        else:
            rows[end - 1] += ' api_key = "' + secrets.token_urlsafe(32) + '"'
        target.write_text("\n".join(rows) + "\n")
        assert path in scanner.woo_public_snapshot_violations(tmp_path, [Path(path)])
        if scenario == "secret":
            native_preflight_dir(tmp_path, tmp_path.parent / (str(which) + ".json"), 1)


@pytest.mark.parametrize("label", ["root", "web"])
def test_preflight_native_exact_history_and_source_mutation(tmp_path: Path, label: str) -> None:
    old, new = (
        ("0ca8a657a4eb985175e8642e881f3cf4942b8424", "ea48a13943d269484a4ebe59ca75803bcafe429f")
        if label == "root"
        else (
            "eb82c9d626c210e8e982ba3d8889a4ffdd088c99",
            "63a5a4f08bad6b98fe95942598291e0714bc09da",
        )
    )
    config = tmp_path / "history.toml"
    config.write_bytes(scanner.history_config())
    report = tmp_path / "native.json"
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
            "--log-opts="
            + old
            + ".."
            + new
            + " --full-history -m --text --no-textconv --no-ext-diff",
        ],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 1
    findings = json.loads(report.read_text())
    assert len(findings) == (90 if label == "root" else 9)
    for item in findings:
        assert scanner.approved_v4_history_finding("git", item)
        assert not scanner.approved_v4_history_finding("dir", item)
        for key in (
            "Commit",
            "File",
            "StartLine",
            "EndLine",
            "StartColumn",
            "EndColumn",
            "Fingerprint",
            "Match",
        ):
            changed = dict(item)
            changed[key] = (
                changed[key] + 1 if isinstance(changed[key], int) else changed[key] + "changed"
            )
            assert not scanner.approved_v4_history_finding("git", changed)
    # A matching scanner report still rejects altered immutable source bytes.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            subprocess,
            "run",
            lambda *a, **kw: subprocess.CompletedProcess([], 0, stdout=b"altered source\n"),
        )
        assert not scanner.approved_v4_history_finding("git", findings[0])


@pytest.mark.parametrize(
    "field", ["source_commit", "source_line", "start_column", "end_column", "exact_line_sha256"]
)
def test_preflight_provenance_refuses_source_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    provenance = json.loads((ROOT / "scripts/gitleaks_rules.json").read_text())
    row = provenance["exceptions"][58]
    row[field] = row[field] + 1 if isinstance(row[field], int) else row[field] + "changed"
    (tmp_path / "scripts").mkdir()
    (tmp_path / ".gitleaks.toml").write_bytes((ROOT / ".gitleaks.toml").read_bytes())
    (tmp_path / "scripts/gitleaks_rules.json").write_text(json.dumps(provenance))
    for name in (
        "m2_public_rows",
        "m2_consumer_rows",
        "m3_public_rows",
        "v4_public_rows",
        "v4_preflight_public_rows",
    ):
        rows = getattr(scanner, name)(ROOT)
        monkeypatch.setattr(scanner, name, lambda _, rows=rows: rows)
    monkeypatch.setattr(scanner, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="invalid V4 preflight scanner rules"):
        scanner.validate_rules()
