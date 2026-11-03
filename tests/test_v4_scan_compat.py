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
    assert sum(len(x.get("allowlists", [])) for x in original["rules"]) == 96
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
    assert len(v4_preflight_history_findings()) == 109
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


def test_merge_copy_native_convergence_and_rejections(tmp_path: Path) -> None:
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
            (
                "--log-opts=0ca8a657a4eb985175e8642e881f3cf4942b8424.."
                "47a445644d853498b45df33e7bc19d1acac80d94 "
                "--full-history -m --text --no-textconv --no-ext-diff"
            ),
        ],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 1
    findings = json.loads(report.read_text())
    copies = []
    for item in findings:
        if scanner.approved_v4_history_finding("git", item):
            continue
        anchor = scanner.approved_v4_merge_copy("git", item)
        assert anchor is not None, {k: item[k] for k in ("File", "Commit", "StartLine")}
        copies.append(item)
    assert len(copies) == 185
    sample = copies[0]
    assert scanner.approved_v4_merge_copy("dir", sample) is None
    for key in ("File", "StartLine", "EndLine", "StartColumn", "EndColumn", "Match", "Fingerprint"):
        changed = dict(sample)
        changed[key] = (
            changed[key] + 1 if isinstance(changed[key], int) else changed[key] + "changed"
        )
        assert scanner.approved_v4_merge_copy("git", changed) is None
    # Every source author remains ineligible for the copy rule even if its blob is anchored.
    from scripts.vendor_gitleaks_rules import V4_MERGE_COPY_ANCHORS

    for anchor in V4_MERGE_COPY_ANCHORS:
        parents = subprocess.check_output(
            ["git", "show", "-s", "--format=%P", anchor["source_commit"]], cwd=ROOT, text=True
        ).split()
        if len(parents) == 1:
            changed = {**sample, "Commit": anchor["source_commit"], "File": anchor["path"]}
            changed["Fingerprint"] = (
                f"{changed['Commit']}:{changed['File']}:{changed['RuleID']}:{changed['StartLine']}"
            )
            assert scanner.approved_v4_merge_copy("git", changed) is None
    # Use real Git merges below; a whole-file mutation elsewhere also invalidates copying.
    repo = tmp_path / "git"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Synthetic merge")
    git(repo, "config", "user.email", "synthetic@example.invalid")
    source = scanner.approved_v4_merge_copy("git", sample)
    assert source is not None
    target = repo / sample["File"]
    target.parent.mkdir(parents=True)
    target.write_bytes(
        subprocess.check_output(
            ["git", "show", source["source_commit"] + ":" + sample["File"]], cwd=ROOT
        )
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "public file")
    git(repo, "switch", "-c", "side")
    (repo / "side.txt").write_text("side\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "side")
    git(repo, "switch", "main")
    (repo / "main.txt").write_text("main\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "main")
    for mutation in ("unchanged", "other_byte", "secret"):
        if mutation != "unchanged":
            with target.open("a") as stream:
                stream.write(
                    "\n"
                    if mutation == "other_byte"
                    else '\napi_key = "' + secrets.token_urlsafe(32) + '"\n'
                )
            git(repo, "add", ".")
            git(repo, "commit", "-m", "different blob")
        git(repo, "merge", "--no-ff", "side", "-m", "merge") if mutation == "unchanged" else None
        # Keep the real two-parent merge and change its file in another true merge.
        if mutation != "unchanged":
            git(repo, "switch", "side")
            (repo / (mutation + ".txt")).write_text("side\n")
            git(repo, "add", ".")
            git(repo, "commit", "-m", "new side")
            git(repo, "switch", "main")
            git(repo, "merge", "--no-ff", "side", "-m", "new merge")
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
        item = {**sample, "Commit": commit}
        item["Fingerprint"] = f"{commit}:{item['File']}:{item['RuleID']}:{item['StartLine']}"
        # Preserve the immutable anchor Git objects in this synthetic repository.
        git(repo, "fetch", str(ROOT), source["source_commit"])
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(scanner, "ROOT", repo)
            assert bool(scanner.approved_v4_merge_copy("git", item)) == (mutation == "unchanged")
    for field in ("source_commit", "path", "blob"):
        changed_anchor = {
            "source_commit": source["source_commit"],
            "path": sample["File"],
            "blob": source["blob"],
        }
        changed_anchor[field] = "0" * 40 if field != "path" else sample["File"] + ".changed"
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(scanner, "V4_MERGE_COPY_ANCHORS", (changed_anchor,))
            assert scanner.approved_v4_merge_copy("git", sample) is None


@pytest.mark.parametrize("which", range(21, 26))
def test_convergence_new_five_literal_boundaries(tmp_path: Path, which: int) -> None:
    test_preflight_each_span_change_duplicate_and_secret(tmp_path, which)


@pytest.mark.parametrize("which", range(26, 35))
def test_discovery_nine_literal_boundaries(tmp_path: Path, which: int) -> None:
    test_preflight_each_span_change_duplicate_and_secret(tmp_path, which)


def test_discovery_metadata_preserves_exact_history_and_only_moves_fixed_spans() -> None:
    from scripts.vendor_gitleaks_rules import V4_MERGE_COPY_ANCHORS, V4_PREFLIGHT_SNAPSHOTS

    before = json.loads(
        subprocess.check_output(["git", "show", "47bfcba:scripts/gitleaks_rules.json"], cwd=ROOT)
    )
    current = json.loads((ROOT / "scripts/gitleaks_rules.json").read_text())
    for key in (
        "historical_findings",
        "v4_historical_findings",
        "v4_additional_historical_findings",
    ):
        assert current[key] == before[key]
    assert (
        current["v4_preflight_historical_findings"][:94]
        == before["v4_preflight_historical_findings"]
    )
    assert current["v4_merge_copy_anchors"][:12] == before["v4_merge_copy_anchors"]
    assert len(V4_MERGE_COPY_ANCHORS) >= 25
    moved = []
    for old, new in zip(before["exceptions"], current["exceptions"][:84], strict=True):
        if old == new:
            continue
        assert old["source_path"] == new["source_path"]
        assert old["exact_line_sha256"] == new["exact_line_sha256"]
        offset = {"tests/v4/test_demo_sessions_pg.py": 4, "tests/e2e/v4/http_probe.py": 7}[
            old["source_path"]
        ]
        assert new["source_line"] == old["source_line"] + offset
        moved.append(old["source_line"])
    assert sorted(moved) == [147, 151, 170, 197, 259, 364, 394]
    assert len(V4_PREFLIGHT_SNAPSHOTS) == 38


@pytest.mark.parametrize(
    "commit,line",
    [
        ("3a135751011c78f78c80773a049565606371eff0", 540),
        ("2330bca2e657a236ba5355b940e2f641763d026d", 557),
    ],
)
def test_residual_driver_copy_only_bindings_are_exact(
    tmp_path: Path, commit: str, line: int
) -> None:
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
            "--log-opts=" + commit + "^! --full-history -m --text --no-textconv --no-ext-diff",
        ],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 1
    item = next(
        r
        for r in json.loads(report.read_text())
        if r["File"] == "tests/e2e/v4/owned_driver.py" and r["StartLine"] == line
    )
    anchor = scanner.approved_v4_merge_copy("git", item)
    assert anchor is not None and anchor["binding_kind"] == "copy_only"
    assert not scanner.approved_v4_history_finding("git", item)
    for key in ("StartLine", "EndLine", "StartColumn", "EndColumn", "Match"):
        changed = dict(item)
        changed[key] = (
            changed[key] + 1 if isinstance(changed[key], int) else changed[key] + "changed"
        )
        assert scanner.approved_v4_merge_copy("git", changed) is None
    # The whole-blob rule still requires two actual parents.
    for source in (
        "8196e628213a9ec5f8ed8c6542f89c213bf60914",
        "1684e0455978b46ddad607e09d85a1af5657ab1a",
    ):
        changed = {**item, "Commit": source}
        changed["Fingerprint"] = f"{source}:{item['File']}:{item['RuleID']}:{item['StartLine']}"
        assert scanner.approved_v4_merge_copy("git", changed) is None


def test_legacy_single_literal_boundaries(tmp_path: Path) -> None:
    test_preflight_each_span_change_duplicate_and_secret(tmp_path, 35)


@pytest.mark.parametrize(
    "commit,is_merge",
    [
        ("4e267522c353074d583a29c89e9022d4f8d93f33", False),
        ("6e98399fb485d7a852d0e4c92923af0ef005782c", True),
    ],
)
def test_legacy_single_exact_author_or_blob_copy(
    tmp_path: Path, commit: str, is_merge: bool
) -> None:
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
            "--log-opts=" + commit + "^! --full-history -m --text --no-textconv --no-ext-diff",
        ],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 1
    matches = [
        r
        for r in json.loads(report.read_text())
        if r["File"] == "tests/e2e/v4/test_legacy_subnet.py"
    ]
    assert len(matches) == 1
    item = matches[0]
    assert scanner.approved_v4_history_finding("git", item) == (not is_merge)
    assert bool(scanner.approved_v4_merge_copy("git", item)) == is_merge
    for key in ("File", "StartLine", "EndLine", "StartColumn", "EndColumn", "Match", "Fingerprint"):
        changed = dict(item)
        changed[key] = (
            changed[key] + 1 if isinstance(changed[key], int) else changed[key] + "changed"
        )
        assert not scanner.approved_v4_history_finding("git", changed)
        assert scanner.approved_v4_merge_copy("git", changed) is None


def test_legacy_single_delta_preserves_all_existing_bindings() -> None:
    previous = json.loads(
        subprocess.check_output(["git", "show", "73e0a58:scripts/gitleaks_rules.json"], cwd=ROOT)
    )
    current = json.loads((ROOT / "scripts/gitleaks_rules.json").read_text())
    for old, new in zip(previous["exceptions"], current["exceptions"][:93], strict=True):
        if old != new:
            assert old["source_path"] == new["source_path"]
            assert old["exact_line_sha256"] == new["exact_line_sha256"]
            offset = {"tests/e2e/v4/http_probe.py": 7, "tests/e2e/v4/owned_negatives.py": -3}[
                old["source_path"]
            ]
            assert new["source_line"] == old["source_line"] + offset
    for field in (
        "historical_findings",
        "v4_historical_findings",
        "v4_additional_historical_findings",
    ):
        assert current[field] == previous[field]
    assert current["v4_merge_copy_bindings"][:2] == previous["v4_merge_copy_bindings"]
    assert (
        current["v4_preflight_historical_findings"][:103]
        == previous["v4_preflight_historical_findings"]
    )
    assert current["v4_merge_copy_anchors"][:27] == previous["v4_merge_copy_anchors"]
    assert len(current["exceptions"]) == 96
    assert len(current["v4_merge_copy_anchors"]) == 34


@pytest.mark.parametrize("which", [2, 3, 4, 5, 36, 37])
def test_r2_exact_span_negative_boundaries(tmp_path: Path, which: int) -> None:
    test_preflight_each_span_change_duplicate_and_secret(tmp_path, which)


@pytest.mark.parametrize(
    "commit",
    [
        "ee1dab651b1b42b99f602a02205a3d8710bb6fd9",
        "8dedb22016bcbd8d66c20c23adc899b6b0c43559",
        "c6abe0528f05b458331f270d758317c1d7b38843",
    ],
)
def test_r2_native_doc_authors_and_fixed_blob_copy(tmp_path: Path, commit: str) -> None:
    paths = {
        "docs/v4/acceptance/v4-0/TTL_F1.json",
        "docs/v4/review/SCAN_f341.md",
        "tests/e2e/v4/http_probe.py",
    }
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
            "--log-opts=" + commit + "^! --full-history -m --text --no-textconv --no-ext-diff",
        ],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 1
    items = [r for r in json.loads(report.read_text()) if r["File"] in paths]
    assert len(items) == (5 if commit.startswith("c6abe") else 1)
    for item in items:
        if commit.startswith("c6abe"):
            assert scanner.approved_v4_merge_copy("git", item)
        else:
            assert scanner.approved_v4_history_finding("git", item)
            assert scanner.approved_v4_merge_copy("git", item) is None
        for key in (
            "File",
            "StartLine",
            "EndLine",
            "StartColumn",
            "EndColumn",
            "Match",
            "Fingerprint",
        ):
            changed = dict(item)
            changed[key] = (
                changed[key] + 1 if isinstance(changed[key], int) else changed[key] + "changed"
            )
            assert not scanner.approved_v4_history_finding("git", changed)
            assert scanner.approved_v4_merge_copy("git", changed) is None


def test_r2_old_exact_metadata_and_copy_bindings_preserved() -> None:
    old = json.loads(
        subprocess.check_output(["git", "show", "f341a89:scripts/gitleaks_rules.json"], cwd=ROOT)
    )
    new = json.loads((ROOT / "scripts/gitleaks_rules.json").read_text())
    for key in (
        "historical_findings",
        "v4_historical_findings",
        "v4_additional_historical_findings",
    ):
        assert new[key] == old[key]
    assert new["v4_preflight_historical_findings"][:104] == old["v4_preflight_historical_findings"]
    assert new["v4_merge_copy_anchors"][:28] == old["v4_merge_copy_anchors"]
    assert new["v4_merge_copy_bindings"][:2] == old["v4_merge_copy_bindings"]
    moved = []
    for previous, current in zip(old["exceptions"], new["exceptions"][:94], strict=True):
        if previous != current:
            assert previous["source_path"] == current["source_path"]
            assert previous["exact_line_sha256"] == current["exact_line_sha256"]
            offset = {"tests/e2e/v4/http_probe.py": 7, "tests/e2e/v4/owned_negatives.py": -3}[
                previous["source_path"]
            ]
            assert current["source_line"] == previous["source_line"] + offset
            moved.append(previous["source_line"])
    assert moved == [147, 259, 364, 394, 44]
    assert len(new["v4_merge_copy_bindings"]) == 7


def test_9727_existing_literal_negative_boundaries(tmp_path: Path) -> None:
    from scripts.vendor_gitleaks_rules import V4_PREFLIGHT_SNAPSHOTS

    which = next(
        i
        for i, r in enumerate(V4_PREFLIGHT_SNAPSHOTS)
        if r["path"] == "tests/e2e/v4/owned_negatives.py"
    )
    test_preflight_each_span_change_duplicate_and_secret(tmp_path, which)


def test_9727_author_has_no_native_findings_and_no_new_approval(tmp_path: Path) -> None:
    commit = "9727cf15aba3d2b2fa27bba6b82682c403903187"
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
            "--log-opts=" + commit + "^! --full-history -m --text --no-textconv --no-ext-diff",
        ],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert not json.loads(report.read_text())
    from scripts.vendor_gitleaks_rules import V4_PREFLIGHT_SNAPSHOTS

    row = next(r for r in V4_PREFLIGHT_SNAPSHOTS if r["path"] == "tests/e2e/v4/owned_negatives.py")
    fake = {
        "RuleID": row["rule"],
        "File": row["path"],
        "StartLine": 41,
        "EndLine": 41,
        "StartColumn": 43,
        "EndColumn": 64,
        "Commit": commit,
        "Fingerprint": f"{commit}:{row['path']}:generic-api-key:41",
        "Match": "unapproved",
    }
    assert not scanner.approved_v4_history_finding("git", fake)
    assert scanner.approved_v4_merge_copy("git", fake) is None


def test_9727_metadata_is_one_position_and_one_blob_only() -> None:
    old = json.loads(
        subprocess.check_output(["git", "show", "e096a59:scripts/gitleaks_rules.json"], cwd=ROOT)
    )
    new = json.loads((ROOT / "scripts/gitleaks_rules.json").read_text())
    for key in (
        "historical_findings",
        "v4_historical_findings",
        "v4_additional_historical_findings",
    ):
        assert new[key] == old[key]
    assert new["v4_preflight_historical_findings"][:106] == old["v4_preflight_historical_findings"]
    changed = []
    for previous, current in zip(old["exceptions"], new["exceptions"], strict=True):
        if previous != current:
            assert (
                previous["source_path"]
                == current["source_path"]
                == "tests/e2e/v4/owned_negatives.py"
            )
            assert previous["exact_line_sha256"] == current["exact_line_sha256"]
            assert previous["source_line"] == 44 and current["source_line"] == 41
            assert current["source_commit"] == "9727cf15aba3d2b2fa27bba6b82682c403903187"
            changed.append(current)
    assert len(changed) == 1
    assert new["v4_merge_copy_anchors"][:31] == old["v4_merge_copy_anchors"]
    assert new["v4_merge_copy_bindings"][:-1] == old["v4_merge_copy_bindings"]
    assert new["v4_merge_copy_bindings"][-1]["reported_line"] == 44
    assert len(new["exceptions"]) == len(old["exceptions"]) == 96


@pytest.mark.parametrize(
    "commit,is_merge",
    [
        ("42acf36571134ccb8ca277088098b05af395ba04", False),
        ("107630e4f28ea0fb2c9306fb3e6594989c130bdc", True),
        ("cf9c739594af69a430ab94c58b32bb564cb43a97", True),
        ("495d1de4f335b29cc13debfd09810150d37e2ad0", True),
    ],
)
def test_final_enum_exact_native_author_and_copies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, commit: str, is_merge: bool
) -> None:
    path = "docs/v4/acceptance/v4-0/ROOT_LEDGER.json"
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
            "--log-opts=" + commit + "^! --full-history -m --text --no-textconv --no-ext-diff",
        ],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 1
    items = [r for r in json.loads(report.read_text()) if r["File"] == path]
    assert len(items) == 1
    item = items[0]
    assert scanner.approved_v4_history_finding("git", item) == (not is_merge)
    assert bool(scanner.approved_v4_merge_copy("git", item)) == is_merge
    for scope in ("dir", "index"):
        assert not scanner.approved_v4_history_finding(scope, item)
        assert scanner.approved_v4_merge_copy(scope, item) is None
    for key in (
        "File",
        "RuleID",
        "StartLine",
        "EndLine",
        "StartColumn",
        "EndColumn",
        "Match",
        "Fingerprint",
        "Commit",
    ):
        changed = dict(item)
        changed[key] = changed[key] + 1 if isinstance(changed[key], int) else changed[key] + "x"
        assert not scanner.approved_v4_history_finding("git", changed)
        assert scanner.approved_v4_merge_copy("git", changed) is None
    # Real single-parent snapshots cannot be treated as merge copies, even with the same blob.
    for author in (
        "42acf36571134ccb8ca277088098b05af395ba04",
        "667cbbc5dde82c25c50ec4fa4f60e0c6f0e366c1",
    ):
        changed = dict(item, Commit=author)
        changed["Fingerprint"] = f"{author}:{path}:{item['RuleID']}:{item['StartLine']}"
        assert scanner.approved_v4_merge_copy("git", changed) is None
        if author.startswith("667"):
            assert not scanner.approved_v4_history_finding("git", changed)
    original_run = subprocess.run

    def tampered_span(command: list[str], *args: Any, **kwargs: Any) -> Any:
        response = original_run(command, *args, **kwargs)
        if command[:2] == ["git", "show"] and command[-1].endswith(":" + path):
            rows = response.stdout.splitlines()
            rows[3] += b" "
            response.stdout = b"\n".join(rows)
        return response

    monkeypatch.setattr(subprocess, "run", tampered_span)
    assert not scanner.approved_v4_history_finding("git", item)
    assert scanner.approved_v4_merge_copy("git", item) is None


def test_final_enum_preserves_rules_and_all_previous_approvals() -> None:
    base = "5f103e6b28ac6fe1486431b8a142b4227ca5a443"
    for path in (".gitleaks.toml", "scripts/scan_secrets.py"):
        assert (ROOT / path).read_bytes() == subprocess.check_output(
            ["git", "show", base + ":" + path], cwd=ROOT
        )
    old = json.loads(
        subprocess.check_output(["git", "show", base + ":scripts/gitleaks_rules.json"], cwd=ROOT)
    )
    new = json.loads((ROOT / "scripts/gitleaks_rules.json").read_text())
    for field in old:
        if field == "v4_preflight_historical_findings":
            assert new[field][:-3] == old[field]
            assert len(new[field]) == 109
        elif field == "v4_merge_copy_anchors":
            assert new[field][:-2] == old[field]
            assert len(new[field]) == 34
        else:
            assert new[field] == old[field]
    native = tomllib.loads(scanner.history_config().decode())
    assert len(native["rules"]) == 222
    assert sum(len(r.get("allowlists", [])) for r in native["rules"]) == 45
    assert len(new["exceptions"]) == 96
    assert (
        json.loads((ROOT / "docs/v4/acceptance/v4-0/ROOT_LEDGER.json").read_text())["authorization"]
        == "B / local"
    )


def test_final_enum_fix_boundaries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    commit = "44633302af915358771c32875d27a1b8ac3e7860"
    path = "tests/test_v4_scan_compat.py"
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
            "--log-opts=" + commit + "^! --full-history -m --text --no-textconv --no-ext-diff",
        ],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 1
    items = json.loads(report.read_text())
    assert len(items) == 2
    for item in items:
        assert item["File"] == path
        assert scanner.approved_v4_history_finding("git", item)
        assert scanner.approved_v4_merge_copy("git", item) is None
        for scope in ("dir", "index"):
            assert not scanner.approved_v4_history_finding(scope, item)
            assert scanner.approved_v4_merge_copy(scope, item) is None
        for field in (
            "File",
            "RuleID",
            "StartLine",
            "EndLine",
            "StartColumn",
            "EndColumn",
            "Match",
            "Fingerprint",
            "Commit",
        ):
            changed = dict(item)
            changed[field] = (
                changed[field] + 1 if isinstance(changed[field], int) else changed[field] + "x"
            )
            assert not scanner.approved_v4_history_finding("git", changed)
            assert scanner.approved_v4_merge_copy("git", changed) is None
        changed = dict(item, Commit="5f103e6b28ac6fe1486431b8a142b4227ca5a443")
        changed["Fingerprint"] = f"{changed['Commit']}:{path}:{item['RuleID']}:{item['StartLine']}"
        assert not scanner.approved_v4_history_finding("git", changed)
        assert scanner.approved_v4_merge_copy("git", changed) is None
    original_run = subprocess.run

    def tampered_spans(command: list[str], *args: Any, **kwargs: Any) -> Any:
        response = original_run(command, *args, **kwargs)
        if command == ["git", "show", commit + ":" + path]:
            rows = response.stdout.splitlines()
            for item in items:
                rows[item["StartLine"] - 1] += b" "
            response.stdout = b"\n".join(rows)
        return response

    monkeypatch.setattr(subprocess, "run", tampered_spans)
    for item in items:
        assert not scanner.approved_v4_history_finding("git", item)
        assert scanner.approved_v4_merge_copy("git", item) is None
