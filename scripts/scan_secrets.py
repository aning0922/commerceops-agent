"""当前可提交内容 + 全部可达 Git 历史；只输出命中位置，丢弃扫描器原始输出。"""

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from scripts.repository_files import indexed_files, versionable_files

ROOT = Path(__file__).resolve().parents[1]
SCANNER = ROOT / ".tools/gitleaks"


def sensitive_path(path: Path) -> bool:
    name = path.name.lower()
    return (
        (name == ".env" or name.startswith(".env."))
        and not name.endswith(".example")
        or path.suffix.lower() in {".pem", ".key", ".p12", ".pfx", ".jks"}
        or name in {"id_rsa", "id_ed25519", ".netrc", ".npmrc.credentials"}
        or bool({"runtime", "backups"}.intersection(path.parts))
    )


def scan(root: Path) -> int:
    if not SCANNER.is_file():
        print("ERROR: 先执行 python -m scripts.bootstrap_tools")
        return 2
    version = subprocess.run([str(SCANNER), "version"], capture_output=True, text=True)
    if version.returncode or version.stdout.strip() != "8.30.1":
        print("ERROR: 扫描器版本不符")
        return 2
    shallow = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if shallow.returncode or shallow.stdout.strip() != "false":
        print("ERROR: 需要完整 Git 历史；浅克隆拒绝通过")
        return 2
    files = versionable_files(root)
    index = indexed_files(root)
    blocked = [str(p) for p in files if sensitive_path(p) or (root / p).is_symlink()]
    blocked += [str(path) for mode, _, path in index if mode not in {"100644", "100755"}]
    for blocked_path in sorted(set(blocked)):
        print(f"BLOCK sensitive-file-or-symlink: {blocked_path}")
    result_code = int(bool(blocked))
    with tempfile.TemporaryDirectory(prefix="commerceops-scan-") as temp:
        staging = Path(temp)
        snapshot = staging / "current"
        snapshot.mkdir()
        for path in files:
            source = root / path
            if source.is_file() and not source.is_symlink():
                destination = snapshot / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
        indexed = staging / "index"
        indexed.mkdir()
        for mode, oid, path in index:
            if mode not in {"100644", "100755"}:
                continue
            blob = subprocess.run(
                ["git", "cat-file", "blob", oid], cwd=root, capture_output=True, check=True
            )
            destination = indexed / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(blob.stdout)
        ignore = staging / "empty-ignore"
        ignore.touch()
        for scope, mode, source in [
            ("dir", "dir", snapshot),
            ("index", "dir", indexed),
            ("git", "git", root),
        ]:
            report = staging / f"{scope}.json"
            command = [
                str(SCANNER),
                mode,
                str(source),
                "--config",
                str(ROOT / ".gitleaks.toml"),
                "--redact=100",
                "--no-banner",
                "--log-level=error",
                "--exit-code=1",
                "--report-format=json",
                "--report-path",
                str(report),
                "--ignore-gitleaks-allow",
                "--gitleaks-ignore-path",
                str(ignore),
            ]
            if mode == "git":
                command += ["--log-opts=--all --full-history -m"]
            process = subprocess.run(command, capture_output=True)
            if process.returncode not in (0, 1) or not report.exists():
                print(f"ERROR {scope}: 扫描器未成功完成（原始输出已抑制）")
                return 2
            findings = json.loads(report.read_text()) or []
            if findings and process.returncode == 0:
                print(f"ERROR {scope}: 命中与退出码不一致")
                return 2
            for item in findings:
                # 永远不输出 Secret/Match/整条报告，也不输出原始 stdout/stderr。
                print(
                    json.dumps(
                        {
                            "scope": scope,
                            "rule": item["RuleID"],
                            "file": item["File"],
                            "line": item["StartLine"],
                            "commit": item.get("Commit", ""),
                        },
                        ensure_ascii=False,
                    )
                )
            result_code = max(result_code, process.returncode)
            print(f"{scope}: findings={len(findings)}, exit={process.returncode}")
    return result_code


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        code = scan(args.repo.resolve())
    except (OSError, ValueError, subprocess.SubprocessError):
        # 工具错误也 fail closed，避免异常包含输入秘密。
        print("ERROR: 敏感检查未完成（异常内容已抑制）")
        code = 2
    raise SystemExit(code)


if __name__ == "__main__":
    main()
