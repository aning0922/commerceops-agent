"""临时仓库合成阻断与质量工具失败合同，不提交合成凭据。"""

import secrets
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_docs import document_errors
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
