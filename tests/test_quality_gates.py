"""临时仓库合成阻断与质量工具失败合同，不提交合成凭据。"""

import hashlib
import json
import secrets
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import tomli_w
from pytest import MonkeyPatch as Patch

from scripts import scan_secrets as secret_scan
from scripts.check_docs import document_errors
from scripts.repository_files import versionable_files
from scripts.scan_secrets import sensitive_path
from scripts.vendor_gitleaks_rules import (
    B_PUBLIC_ROW,
    P3_DOCUMENT_DIGEST,
    P3_PUBLIC_ROW,
    RO_PUBLIC_ROW,
    WOO_PUBLIC_EXCEPTIONS,
)

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.offline


def git(repo: Path, *arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Synthetic check")
    git(tmp_path, "config", "user.email", "synthetic@example.invalid")
    (tmp_path / "baseline.txt").write_text("non-sensitive baseline\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "synthetic baseline")
    return tmp_path


def run_scan(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.scan_secrets", "--repo", str(repo)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.parametrize("scope", ["baseline", "current", "history", "other-ref", "index-only"])
def test_synthetic_scanner_blocks_and_redacts(repository: Path, scope: str) -> None:
    # 运行时才拼出无效合成 token；没有固定 credential-like 字符串入库。
    value = "".join(["gh", "p_"]) + secrets.token_hex(18)
    if scope != "baseline":
        path = repository / "synthetic.txt"
        path.write_text(f"github_token={value} # gitleaks:allow\n")
        if scope == "index-only":
            git(repository, "add", ".")
            path.write_text("sanitized worktree\n")
        if scope in {"history", "other-ref"}:
            if scope == "other-ref":
                git(repository, "switch", "-c", "synthetic-side")
            git(repository, "add", ".")
            git(repository, "commit", "-m", "synthetic historical check")
            if scope == "other-ref":
                git(repository, "switch", "main")
            else:
                path.unlink()
                git(repository, "add", "-u")
                git(repository, "commit", "-m", "remove synthetic current content")
    result = run_scan(repository)
    output = result.stdout + result.stderr
    assert value not in output
    assert "github_token=" not in output
    if scope == "baseline":
        assert result.returncode == 0, output
        assert "dir: findings=0, exit=0" in output
        assert "index: findings=0, exit=0" in output
        assert "git: findings=0, exit=0" in output
    else:
        assert result.returncode == 1, output
        assert '"rule": "github-pat"' in output
        expected_scope = {"current": "dir", "index-only": "index"}.get(scope, "git")
        assert f'"scope": "{expected_scope}"' in output
        if scope in {"history", "other-ref", "index-only"}:
            assert "dir: findings=0, exit=0" in output


def test_sensitive_filename_blocks(repository: Path) -> None:
    (repository / ".env").write_text("NON_SECRET=placeholder\n")
    git(repository, "add", "--force", ".env")
    result = run_scan(repository)
    assert result.returncode == 1
    assert "BLOCK sensitive-file-or-symlink: .env" in result.stdout


def test_shallow_repository_fails_closed(repository: Path, tmp_path: Path) -> None:
    clone = tmp_path / "shallow"
    git(repository, "clone", "--depth", "1", repository.as_uri(), str(clone))
    result = run_scan(clone)
    assert result.returncode == 2
    assert "浅克隆拒绝通过" in result.stdout


def test_sensitive_filename_policy() -> None:
    assert sensitive_path(Path("nested/.env.production"))
    assert sensitive_path(Path("private.key"))
    assert not sensitive_path(Path(".env.example"))
    assert not sensitive_path(Path("docs/RESEARCH.md"))


def test_docs_check_link_and_fence_failures(tmp_path: Path) -> None:
    document = tmp_path / "README.md"
    (tmp_path / "target.md").touch()
    document.write_text("[valid](target.md)\n```text\n[not a link](missing.md)\n```\n")
    assert document_errors(document, tmp_path) == []
    document.write_text("[missing](missing.md)\n~~~text\nunterminated\n")
    errors = document_errors(document, tmp_path)
    assert len(errors) == 2
    assert any("未关闭代码围栏" in error for error in errors)
    assert any("链接不存在" in error for error in errors)


def synthetic_value() -> str:
    return "".join(["gh", "p_"]) + secrets.token_hex(18)


def assert_redacted_block(result: subprocess.CompletedProcess[str], value: str) -> str:
    output = result.stdout + result.stderr
    assert value not in output
    assert "fixture_token=" not in output
    assert result.returncode == 1, output
    return output


@pytest.mark.parametrize("filename", ["package-lock.json", "diagram.svg", "uv.lock"])
@pytest.mark.parametrize("scope", ["current", "index-only", "committed", "history"])
def test_text_paths_are_not_inherited_allowlists(
    repository: Path, filename: str, scope: str
) -> None:
    value = synthetic_value()
    path = repository / filename
    if path.suffix == ".json":
        path.write_text('{"lockfileVersion":3,"fixture_token":"' + value + '"}\n')
    elif path.suffix == ".svg":
        path.write_text('<svg><metadata fixture_token="' + value + '"/></svg>\n')
    else:
        path.write_text(f'fixture_token="{value}"\n')
    if scope != "current":
        git(repository, "add", ".")
    if scope == "index-only":
        path.write_text("sanitized worktree\n")
    if scope in {"committed", "history"}:
        git(repository, "commit", "-m", "synthetic text asset")
    if scope == "history":
        path.unlink()
        git(repository, "add", "-u")
        git(repository, "commit", "-m", "remove current synthetic asset")
    output = assert_redacted_block(run_scan(repository), value)
    scopes = {
        "current": ["dir"],
        "index-only": ["index"],
        "committed": ["dir", "index", "git"],
        "history": ["git"],
    }
    for expected in scopes[scope]:
        assert f'"scope": "{expected}"' in output
    if scope in {"index-only", "history"}:
        assert "dir: findings=0, exit=0" in output


@pytest.mark.parametrize("state", ["untracked", "tracked", "ignored", "index-only"])
def test_fingerprint_ignore_cannot_suppress_history(repository: Path, state: str) -> None:
    value = synthetic_value()
    path = repository / "synthetic.txt"
    path.write_text(f"fixture_token={value}\n")
    git(repository, "add", ".")
    git(repository, "commit", "-m", "synthetic historical credential")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository).decode().strip()
    path.unlink()
    git(repository, "add", "-u")
    git(repository, "commit", "-m", "remove synthetic credential")
    before = assert_redacted_block(run_scan(repository), value)
    assert '"scope": "git"' in before
    ignore = repository / ".gitleaksignore"
    ignore.write_text(f"{commit}:synthetic.txt:github-pat:1\n")
    if state in {"tracked", "index-only"}:
        git(repository, "add", ".gitleaksignore")
    if state == "tracked":
        git(repository, "commit", "-m", "synthetic attempted fingerprint bypass")
    elif state == "index-only":
        ignore.unlink()
    elif state == "ignored":
        (repository / ".git/info/exclude").write_text(".gitleaksignore\n")
        assert not any(p.name == ".gitleaksignore" for p in versionable_files(repository))
    output = assert_redacted_block(run_scan(repository), value)
    assert "BLOCK scanner-ignore-policy" in output
    assert "findings=0" not in output  # 在实际加载文件之前拒绝，不伪称三层扫描成功。


@pytest.mark.parametrize("attribute", ["-diff", "diff=synthetic-mask"])
def test_raw_history_ignores_binary_attributes_and_textconv(
    repository: Path, attribute: str
) -> None:
    value = synthetic_value()
    (repository / ".gitattributes").write_text(f"synthetic.txt {attribute}\n")
    # 若 textconv 被调用，它会完全掩盖凭据并写出可检测 marker。
    converter = repository / "mask.py"
    converter.write_text(
        "from pathlib import Path\n"
        f"Path({str(repository / 'textconv-was-used')!r}).touch()\n"
        "print('sanitized conversion')\n"
    )
    git(
        repository,
        "config",
        "diff.synthetic-mask.textconv",
        shlex.join([sys.executable, str(converter)]),
    )
    path = repository / "synthetic.txt"
    path.write_text(f"fixture_token={value}\n")
    git(repository, "add", ".")
    git(repository, "commit", "-m", "synthetic attributed credential")
    path.unlink()
    git(repository, "add", "-u")
    git(repository, "commit", "-m", "remove attributed credential")
    output = assert_redacted_block(run_scan(repository), value)
    assert "dir: findings=0, exit=0" in output
    assert "index: findings=0, exit=0" in output
    assert '"scope": "git"' in output
    assert not (repository / "textconv-was-used").exists()


@pytest.mark.parametrize("filename", [".gitleaks.toml", "docs/DATA_MODEL.md"])
@pytest.mark.parametrize("inject_secret", [False, True])
def test_exact_line_exceptions_do_not_exclude_same_file(
    repository: Path, filename: str, inject_secret: bool
) -> None:
    value = synthetic_value()
    path = repository / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (ROOT / filename).read_text() + (f"\nfixture_token={value}\n" if inject_secret else "")
    )
    git(repository, "add", ".")
    git(repository, "commit", "-m", "synthetic adjacent to reviewed public context")
    result = run_scan(repository)
    if not inject_secret:
        assert result.returncode == 0, result.stdout
        return
    output = assert_redacted_block(result, value)
    for scope in ["dir", "index", "git"]:
        assert f'"scope": "{scope}"' in output
    assert '"rule": "github-pat"' in output


@pytest.mark.parametrize(
    "rule_id,filename",
    [
        ("generic-api-key", "docs/DATA_MODEL.md"),
        ("aws-amazon-bedrock-api-key-short-lived", ".gitleaks.toml"),
    ],
)
def test_exact_exceptions_still_detect_their_own_rule_elsewhere(
    repository: Path, rule_id: str, filename: str
) -> None:
    rules = tomllib.loads((ROOT / ".gitleaks.toml").read_text())["rules"]
    if rule_id == "generic-api-key":
        value = secrets.token_urlsafe(32)
    else:
        # 固定公开格式前缀来自规则，运行时组合无效随机测试值。
        prefix = next(rule["regex"] for rule in rules if rule["id"] == rule_id)
        value = prefix + secrets.token_urlsafe(32)
    path = repository / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((ROOT / filename).read_text() + f'\napi_key = "{value}"\n')
    git(repository, "add", ".")
    git(repository, "commit", "-m", "synthetic matching the narrowly excepted rule")
    output = assert_redacted_block(run_scan(repository), value)
    assert f'"rule": "{rule_id}"' in output
    for scope in ["dir", "index", "git"]:
        assert f'"scope": "{scope}"' in output


def test_modified_rules_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/gitleaks_rules.json").write_bytes(
        (ROOT / "scripts/gitleaks_rules.json").read_bytes()
    )
    (tmp_path / ".gitleaks.toml").write_text(
        (ROOT / ".gitleaks.toml").read_text() + "\n[extend]\nuseDefault=true\n"
    )
    monkeypatch.setattr(secret_scan, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="invalid scanner rules"):
        secret_scan.validate_rules()


@pytest.mark.parametrize(
    "scenario",
    [
        "exact",
        "one_character",
        "same_digest_other_path",
        "adjacent_generic",
        "adjacent_pat",
        "history",
    ],
)
def test_p3_public_digest_exception_is_exact(repository: Path, scenario: str) -> None:
    filename = (
        "docs/contracts/p3-other.json"
        if scenario == "same_digest_other_path"
        else "docs/contracts/p3-checks.json"
    )
    path = repository / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    row = P3_PUBLIC_ROW
    value = ""
    if scenario == "one_character":
        value = ("b" if P3_DOCUMENT_DIGEST[0] != "b" else "a") + P3_DOCUMENT_DIGEST[1:]
        row = row.replace(P3_DOCUMENT_DIGEST, value)
    if scenario == "same_digest_other_path":
        value = P3_DOCUMENT_DIGEST
    if scenario in {"adjacent_generic", "history"}:
        value = secrets.token_urlsafe(32)
        row += f'\napi_key = "{value}"'
    if scenario == "adjacent_pat":
        value = synthetic_value()
        row += f'\ngithub_token = "{value}"'
    path.write_text(row + "\n")
    git(repository, "add", ".")
    git(repository, "commit", "-m", "synthetic public digest boundary")
    if scenario == "history":
        path.write_text(P3_PUBLIC_ROW + "\n")
        git(repository, "add", ".")
        git(repository, "commit", "-m", "remove current synthetic credential, retain history")
    result = run_scan(repository)
    if scenario == "exact":
        assert result.returncode == 0, result.stdout
        assert "git: findings=0, exit=0" in result.stdout
        return
    output = assert_redacted_block(result, value)
    assert (
        f'"rule": "{"github-pat" if scenario == "adjacent_pat" else "generic-api-key"}"' in output
    )
    scopes = ["git"] if scenario == "history" else ["dir", "index", "git"]
    for scope in scopes:
        assert f'"scope": "{scope}"' in output


def test_p3_wider_exception_fails_even_with_updated_config_digest(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    (tmp_path / "scripts").mkdir()
    config = tomllib.loads((ROOT / ".gitleaks.toml").read_text())
    generic = next(rule for rule in config["rules"] if rule["id"] == "generic-api-key")
    generic["allowlists"][1]["paths"] = [r"(?:^|/)docs/.*"]
    content = tomli_w.dumps(config).encode()
    provenance = json.loads((ROOT / "scripts/gitleaks_rules.json").read_text())
    provenance["config_sha256"] = hashlib.sha256(content).hexdigest()
    (tmp_path / ".gitleaks.toml").write_bytes(content)
    (tmp_path / "scripts/gitleaks_rules.json").write_text(json.dumps(provenance))
    patcher: pytest.MonkeyPatch = request.getfixturevalue("monkeypatch")
    patcher.setattr(secret_scan, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="invalid scanner rules"):
        secret_scan.validate_rules()


def test_secret_gate_runs_before_dependency_installation(repository: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-S", "-m", "scripts.scan_secrets", "--repo", str(repository)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "git: findings=0, exit=0" in result.stdout


@pytest.mark.parametrize(
    "scenario",
    ["exact", "one_character", "other_path", "adjacent_generic", "adjacent_pat", "history"],
)
def test_b_public_metadata_exception_is_one_exact_line(repository: Path, scenario: str) -> None:
    filename = (
        "frontend/evidence/b02-read/validation.json"
        if scenario != "other_path"
        else "frontend/evidence/b02-read/other.json"
    )
    path = repository / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    row = B_PUBLIC_ROW
    value = ""
    if scenario == "one_character":
        row = row.replace("final stage", "final stagh")
    if scenario in ("adjacent_generic", "history"):
        value = secrets.token_urlsafe(32)
        row += f'\napi_key = "{value}"'
    if scenario == "adjacent_pat":
        value = synthetic_value()
        row += f'\ngithub_token = "{value}"'
    path.write_text(row + "\n")
    git(repository, "add", ".")
    git(repository, "commit", "-m", "synthetic reviewed B metadata boundary")
    if scenario == "history":
        path.write_text(B_PUBLIC_ROW + "\n")
        git(repository, "add", ".")
        git(repository, "commit", "-m", "remove current synthetic value and retain history")
    result = run_scan(repository)
    if scenario == "exact":
        assert result.returncode == 0, result.stdout
        assert "git: findings=0, exit=0" in result.stdout
        return
    output = assert_redacted_block(result, value or row)
    assert (
        f'"rule": "{"github-pat" if scenario == "adjacent_pat" else "generic-api-key"}"' in output
    )
    for scope in ["git"] if scenario == "history" else ["dir", "index", "git"]:
        assert f'"scope": "{scope}"' in output


def test_b_wider_path_rejected_without_losing_p3_validation(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    (tmp_path / "scripts").mkdir()
    config = tomllib.loads((ROOT / ".gitleaks.toml").read_text())
    generic = next(rule for rule in config["rules"] if rule["id"] == "generic-api-key")
    generic["allowlists"][2]["paths"] = [r"(?:^|/)frontend/.*"]
    content = tomli_w.dumps(config).encode()
    provenance = json.loads((ROOT / "scripts/gitleaks_rules.json").read_text())
    provenance["config_sha256"] = hashlib.sha256(content).hexdigest()
    (tmp_path / ".gitleaks.toml").write_bytes(content)
    (tmp_path / "scripts/gitleaks_rules.json").write_text(json.dumps(provenance))
    patcher: pytest.MonkeyPatch = request.getfixturevalue("monkeypatch")
    patcher.setattr(secret_scan, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="invalid scanner rules"):
        secret_scan.validate_rules()


@pytest.mark.parametrize(
    "scenario",
    ["exact", "one_character", "other_path", "adjacent_generic", "adjacent_pat", "history"],
)
def test_ro_historical_action_exception_is_one_exact_line(repository: Path, scenario: str) -> None:
    filename = "scripts/p4_acceptance.py" if scenario != "other_path" else "scripts/p4_other.py"
    path = repository / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    row = RO_PUBLIC_ROW
    value = ""
    if scenario == "one_character":
        row = row.replace("recheck_authorized", "recheck_authorizee")
    if scenario in ("adjacent_generic", "history"):
        value = secrets.token_urlsafe(32)
        row += f'\napi_key = "{value}"'
    if scenario == "adjacent_pat":
        value = synthetic_value()
        row += f'\ngithub_token = "{value}"'
    path.write_text(row + "\n")
    git(repository, "add", ".")
    git(repository, "commit", "-m", "synthetic reviewed RO public action boundary")
    if scenario == "history":
        path.write_text(RO_PUBLIC_ROW + "\n")
        git(repository, "add", ".")
        git(repository, "commit", "-m", "remove current synthetic value and retain history")
    result = run_scan(repository)
    if scenario == "exact":
        assert result.returncode == 0, result.stdout
        assert "git: findings=0, exit=0" in result.stdout
        return
    output = assert_redacted_block(result, value or row)
    assert (
        f'"rule": "{"github-pat" if scenario == "adjacent_pat" else "generic-api-key"}"' in output
    )
    for scope in ["git"] if scenario == "history" else ["dir", "index", "git"]:
        assert f'"scope": "{scope}"' in output


@pytest.mark.parametrize("mutation", ["path", "regex", "commit", "line", "digest"])
def test_ro_exception_cannot_be_broadened_by_updated_config_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    (tmp_path / "scripts").mkdir()
    config = tomllib.loads((ROOT / ".gitleaks.toml").read_text())
    generic = next(rule for rule in config["rules"] if rule["id"] == "generic-api-key")
    provenance = json.loads((ROOT / "scripts/gitleaks_rules.json").read_text())
    if mutation == "path":
        generic["allowlists"][3]["paths"] = [r"(?:^|/)scripts/.*"]
    elif mutation == "regex":
        generic["allowlists"][3]["regexes"] = [".*"]
    elif mutation == "commit":
        provenance["exceptions"][4]["source_commit"] = "0" * 40
    elif mutation == "line":
        provenance["exceptions"][4]["source_line"] = 3937
    else:
        provenance["exceptions"][4]["exact_line_sha256"] = "0" * 64
    content = tomli_w.dumps(config).encode()
    provenance["config_sha256"] = hashlib.sha256(content).hexdigest()
    (tmp_path / ".gitleaks.toml").write_bytes(content)
    (tmp_path / "scripts/gitleaks_rules.json").write_text(json.dumps(provenance))
    monkeypatch.setattr(secret_scan, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="invalid scanner rules"):
        secret_scan.validate_rules()


@pytest.mark.parametrize(
    "field",
    [
        "path",
        "source_commit",
        "reported_line",
        "fingerprint",
        "declaration_sha256",
        "reported_line_sha256",
        "match_sha256",
    ],
)
def test_history_finding_provenance_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / ".gitleaks.toml").write_bytes((ROOT / ".gitleaks.toml").read_bytes())
    provenance = json.loads((ROOT / "scripts/gitleaks_rules.json").read_text())
    record = provenance["historical_findings"][0]
    record[field] = (
        record[field] + 1 if isinstance(record[field], int) else str(record[field]) + "changed"
    )
    (tmp_path / "scripts/gitleaks_rules.json").write_text(json.dumps(provenance))
    monkeypatch.setattr(secret_scan, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="historical scanner finding"):
        secret_scan.validate_rules()


def test_public_test_declaration_in_another_commit_is_not_approved(repository: Path) -> None:
    target = repository / "tests/test_p4_queued_start.py"
    target.parent.mkdir()
    declaration = "def test_group_option_" + "incomplete_or_mixed_rejects_before_inputs("
    target.write_text(
        "\n" * 444
        + declaration
        + "\n    options: dict[str, Any], monkeypatch: pytest."
        + "MonkeyPatch\n) -> None:\n    pass\n"
    )
    git(repository, "add", ".")
    git(repository, "commit", "-m", "synthetic unapproved public declaration")
    target.unlink()
    git(repository, "add", "-u")
    git(repository, "commit", "-m", "remove current declaration")
    result = run_scan(repository)
    assert result.returncode == 1
    assert '"scope": "git"' in result.stdout
    assert '"rule": "generic-api-key"' in result.stdout


def test_three_actual_history_findings_are_exact_and_git_only(tmp_path: Path) -> None:
    report = tmp_path / "native-report.json"
    result = subprocess.run(
        [
            str(ROOT / ".tools/gitleaks"),
            "git",
            str(ROOT),
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
            "--log-opts=--all --full-history -m --text --no-textconv --no-ext-diff",
        ],
        capture_output=True,
    )
    assert result.returncode == 1
    rows = json.loads(report.read_text())
    assert len(rows) == 3
    for row in rows:
        assert secret_scan.approved_history_finding("git", row)
        assert not secret_scan.approved_history_finding("dir", row)
        assert not secret_scan.approved_history_finding("index", row)
        for field in ("RuleID", "File", "StartLine", "Commit", "Fingerprint", "Match"):
            changed = dict(row)
            changed[field] = (
                changed[field] + 1
                if isinstance(changed[field], int)
                else changed[field] + "changed"
            )
            assert not secret_scan.approved_history_finding("git", changed)


@pytest.mark.parametrize("which", [0, 1])
@pytest.mark.parametrize(
    "scenario",
    [
        "exact",
        "changed_low_entropy",
        "changed_field",
        "moved_line",
        "other_path",
        "nested_same_suffix",
        "adjacent_generic",
        "same_line_generic",
        "index_only",
        "history",
    ],
)
def test_woo_public_exceptions_are_exact_and_scoped(
    repository: Path, which: int, scenario: str
) -> None:
    filename, _, original, _, line = WOO_PUBLIC_EXCEPTIONS[which]
    relative = filename + ".other" if scenario == "other_path" else filename
    if scenario == "nested_same_suffix":
        relative = "nested/" + filename
    path = repository / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    row = original
    value = ""
    if scenario in {"changed_low_entropy", "index_only"}:
        mark = "_commerceops_lab_"
        row = row.replace("partial_refund", "partial_refune").replace(mark + "key", mark + "kez")
    if scenario == "changed_field":
        row = row.replace("meta_key", "meta_token").replace('"key"', '"token"')
    if scenario in {"adjacent_generic", "same_line_generic", "history"}:
        value = secrets.token_urlsafe(32)
        row += (" " if scenario == "same_line_generic" else "\n") + f'api_key = "{value}"'
    prefix = "\n" * (line - 1 + (scenario == "moved_line"))
    path.write_text(prefix + row + "\n")
    git(repository, "add", ".")
    if scenario == "index_only":
        path.write_text("\n" * (line - 1) + original + "\n")
    else:
        git(repository, "commit", "-m", "synthetic Woo marker boundary")
    if scenario == "history":
        path.write_text("\n" * (line - 1) + original + "\n")
        git(repository, "add", ".")
        git(repository, "commit", "-m", "retain historical synthetic credential")
    result = run_scan(repository)
    output = result.stdout + result.stderr
    if value:
        assert value not in output
    assert original not in output and row not in output
    if scenario == "exact":
        assert result.returncode == 0, output
        assert "git: findings=0, exit=0" in output
    else:
        assert result.returncode == 1, output
        if scenario in {
            "changed_low_entropy",
            "changed_field",
            "moved_line",
            "nested_same_suffix",
            "same_line_generic",
            "index_only",
        }:
            assert "BLOCK reviewed-public-row-changed" in output
        if scenario in {"adjacent_generic", "same_line_generic", "history", "other_path"}:
            assert '"rule": "generic-api-key"' in output
        if scenario == "index_only":
            assert '"scope": "index"' in output


@pytest.mark.parametrize("which", [0, 1])
@pytest.mark.parametrize(
    "mutation", ["path", "regex", "condition", "target", "commit", "line", "digest", "source_path"]
)
def test_woo_exception_provenance_cannot_be_broadened(
    tmp_path: Path, monkeypatch: Patch, which: int, mutation: str
) -> None:
    (tmp_path / "scripts").mkdir()
    config = tomllib.loads((ROOT / ".gitleaks.toml").read_text())
    generic = next(rule for rule in config["rules"] if rule["id"] == "generic-api-key")
    allowance = generic["allowlists"][4 + which]
    provenance = json.loads((ROOT / "scripts/gitleaks_rules.json").read_text())
    evidence = provenance["exceptions"][5 + which]
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
    monkeypatch.setattr(secret_scan, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="invalid scanner rules"):
        secret_scan.validate_rules()


def test_woo_public_source_requires_actual_committed_row(tmp_path: Path) -> None:
    from scripts.vendor_gitleaks_rules import validate_woo_public_sources

    with pytest.raises(ValueError, match="invalid Woo public source"):
        validate_woo_public_sources(tmp_path)
