"""临时仓库合成阻断与质量工具失败合同，不提交合成凭据。"""

import secrets
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from scripts import scan_secrets as secret_scan
from scripts.check_docs import document_errors
from scripts.repository_files import versionable_files
from scripts.scan_secrets import sensitive_path

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
