"""当前可提交内容 + 全部可达 Git 历史；只输出命中位置，丢弃扫描器原始输出。"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path
from typing import Any

from scripts.repository_files import indexed_files, versionable_files
from scripts.vendor_gitleaks_rules import (
    B_PUBLIC_PATH,
    B_PUBLIC_ROW,
    B_ROW_DIGEST,
    P3_PUBLIC_PATH,
    P3_PUBLIC_ROW,
    P3_ROW_DIGEST,
    RO_PUBLIC_PATH,
    RO_PUBLIC_ROW,
    RO_ROW_DIGEST,
    RO_SOURCE_COMMIT,
)

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


APPROVED_TEST_HISTORY: tuple[dict[str, Any], ...] = (
    {
        "rule": "generic-api-key",
        "path": "tests/test_p4_queued_start.py",
        "source_commit": "72bc597a1978f5dd78853e678ca57e68f0586ab6",
        "declaration_line": 445,
        "reported_line": 446,
        "declaration_sha256": "0e616f2f1e514fb1f6a4f553c3fc314d69384f4a8481ec98614d217a9b3c0017",
        "reported_line_sha256": "552256c040cb6f95fc625b89b82f08c722790b022a9bf7e8502031d725c59729",
        "fingerprint": (
            "72bc597a1978f5dd78853e678ca57e68f0586ab6:"
            "tests/test_p4_queued_start.py:generic-api-key:446"
        ),
        "match_sha256": "617581412b474fb36e60639d980eddc44cbfa5a220bf98433eac96cd8e59f7e4",
    },
    {
        "rule": "generic-api-key",
        "path": "tests/test_p4_queued_start.py",
        "source_commit": "be1b79380be3eac042a04f5cd75bb980044cb770",
        "declaration_line": 445,
        "reported_line": 446,
        "declaration_sha256": "0e616f2f1e514fb1f6a4f553c3fc314d69384f4a8481ec98614d217a9b3c0017",
        "reported_line_sha256": "552256c040cb6f95fc625b89b82f08c722790b022a9bf7e8502031d725c59729",
        "fingerprint": (
            "be1b79380be3eac042a04f5cd75bb980044cb770:"
            "tests/test_p4_queued_start.py:generic-api-key:446"
        ),
        "match_sha256": "617581412b474fb36e60639d980eddc44cbfa5a220bf98433eac96cd8e59f7e4",
    },
    {
        "declaration_line": 932,
        "declaration_sha256": "ac094857ba462db6538609bdbce945d7c3a5d7bb7556c3355345e90c5230f6a8",
        "fingerprint": (
            "7499f7cf08b4058951783a78a9e89ff076cd2ae5:scripts/p4_acceptance.py:generic-api-key:932"
        ),
        "match_sha256": "b122fc8bcb1fed4197e23a043989ac031736a4b8bd62e923c60c69f755fb69f3",
        "path": "scripts/p4_acceptance.py",
        "reported_line": 932,
        "reported_line_sha256": "ac094857ba462db6538609bdbce945d7c3a5d7bb7556c3355345e90c5230f6a8",
        "rule": "generic-api-key",
        "source_commit": "7499f7cf08b4058951783a78a9e89ff076cd2ae5",
    },
)


def validate_rules() -> None:
    """不能依靠覆盖 extend 的空 allowlist；校验完整配置及五处精确行豁免。"""
    content = (ROOT / ".gitleaks.toml").read_bytes()
    provenance = json.loads((ROOT / "scripts/gitleaks_rules.json").read_text())
    config = tomllib.loads(content.decode())
    rules = config["rules"]
    inventory = "\n".join(sorted(rule["id"] for rule in rules)).encode()
    if (
        hashlib.sha256(content).hexdigest() != provenance["config_sha256"]
        or len(rules) != provenance["rule_count"]
        or hashlib.sha256(inventory).hexdigest() != provenance["rule_ids_sha256"]
        or any(key in config for key in {"extend", "allowlist", "allowlists"})
        or any("allowlist" in rule for rule in rules)
        or sum(len(rule.get("allowlists", [])) for rule in rules) != 5
        or {rule["id"] for rule in rules if rule.get("allowlists")}
        != {
            "generic-api-key",
            "aws-amazon-bedrock-api-key-short-lived",
        }
        or len(provenance["exceptions"]) != 5
    ):
        raise ValueError("invalid scanner rules")
    generic = next(rule for rule in rules if rule["id"] == "generic-api-key")
    if len(generic.get("allowlists", [])) != 4:
        raise ValueError("invalid scanner rules")
    public_line = generic["allowlists"][1]
    evidence = provenance["exceptions"][2]
    if (
        len(generic["allowlists"]) != 4
        or public_line["condition"] != "AND"
        or public_line["regexTarget"] != "line"
        or public_line["paths"] != [P3_PUBLIC_PATH]
        or public_line["regexes"] != [r"^(?:\r?\n)?" + re.escape(P3_PUBLIC_ROW) + "$"]
        or hashlib.sha256(P3_PUBLIC_ROW.encode()).hexdigest() != P3_ROW_DIGEST
        or evidence["rule"] != "generic-api-key"
        or evidence["path"] != P3_PUBLIC_PATH
        or evidence["exact_line_sha256"] != P3_ROW_DIGEST
    ):
        raise ValueError("invalid scanner rules")
    b_line = generic["allowlists"][2]
    b_evidence = provenance["exceptions"][3]
    if (
        b_line["condition"] != "AND"
        or b_line["regexTarget"] != "line"
        or b_line["paths"] != [B_PUBLIC_PATH]
        or b_line["regexes"] != [r"^(?:\r?\n)?" + re.escape(B_PUBLIC_ROW) + "$"]
        or hashlib.sha256(B_PUBLIC_ROW.encode()).hexdigest() != B_ROW_DIGEST
        or b_evidence["rule"] != "generic-api-key"
        or b_evidence["path"] != B_PUBLIC_PATH
        or b_evidence["exact_line_sha256"] != B_ROW_DIGEST
        or b_evidence.get("source_commit") != "973bf6447211f084355d61b9d58adfd95dfa2788"
        or b_evidence.get("source_line") != 27
    ):
        raise ValueError("invalid scanner rules")

    ro_line = generic["allowlists"][3]
    ro_evidence = provenance["exceptions"][4]
    if (
        ro_line["condition"] != "AND"
        or ro_line["regexTarget"] != "line"
        or ro_line["paths"] != [RO_PUBLIC_PATH]
        or ro_line["regexes"] != [r"^(?:\r?\n)?" + re.escape(RO_PUBLIC_ROW) + "$"]
        or hashlib.sha256(RO_PUBLIC_ROW.encode()).hexdigest() != RO_ROW_DIGEST
        or ro_evidence["rule"] != "generic-api-key"
        or ro_evidence["path"] != RO_PUBLIC_PATH
        or ro_evidence["exact_line_sha256"] != RO_ROW_DIGEST
        or ro_evidence.get("source_commit") != RO_SOURCE_COMMIT
        or ro_evidence.get("source_line") != 3936
    ):
        raise ValueError("invalid scanner rules")

    if provenance.get("historical_findings") != list(APPROVED_TEST_HISTORY):
        raise ValueError("invalid historical scanner finding")


def approved_history_finding(scope: str, item: dict[str, Any]) -> bool:
    """Exact independently reviewed public findings; all raw findings remain visible."""
    if scope != "git":
        return False
    for row in APPROVED_TEST_HISTORY:
        if any(
            item.get(key) != row[field]
            for key, field in (
                ("RuleID", "rule"),
                ("File", "path"),
                ("StartLine", "reported_line"),
                ("Commit", "source_commit"),
                ("Fingerprint", "fingerprint"),
            )
        ):
            continue
        match = item.get("Match")
        if (
            not isinstance(match, str)
            or hashlib.sha256(match.encode()).hexdigest() != row["match_sha256"]
        ):
            return False
        result = subprocess.run(
            ["git", "show", row["source_commit"] + ":" + row["path"]],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            return False
        lines = result.stdout.splitlines()
        return all(
            len(lines) >= row[line]
            and hashlib.sha256(lines[row[line] - 1]).hexdigest() == row[digest]
            for line, digest in (
                ("declaration_line", "declaration_sha256"),
                ("reported_line", "reported_line_sha256"),
            )
        )
    return False


def scan(root: Path) -> int:
    validate_rules()
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
    # Gitleaks 会另读 source/.gitleaksignore；检查包含 ignored/untracked 的根路径。
    ignore_path = root / ".gitleaksignore"
    if (
        ignore_path.exists()
        or ignore_path.is_symlink()
        or any(path.name == ".gitleaksignore" for path in files)
        or any(path.name == ".gitleaksignore" for _, _, path in index)
    ):
        print("BLOCK scanner-ignore-policy: .gitleaksignore 不允许参与扫描")
        return 1
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
        # 扫描器 source 使用隔离入口；原仓库根文件不会被自动读取。
        history = staging / "history"
        history.mkdir()
        gitdir = subprocess.run(
            ["git", "rev-parse", "--absolute-git-dir"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        (history / ".git").write_text(f"gitdir: {gitdir}\n")
        ignore = staging / "empty-ignore"
        ignore.touch()
        for scope, mode, source in [
            ("dir", "dir", snapshot),
            ("index", "dir", indexed),
            ("git", "git", history),
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
                command += ["--log-opts=--all --full-history -m --text --no-textconv --no-ext-diff"]
            process = subprocess.run(command, cwd=staging, capture_output=True)
            if process.returncode not in (0, 1) or not report.exists():
                print(f"ERROR {scope}: 扫描器未成功完成（原始输出已抑制）")
                return 2
            findings = json.loads(report.read_text()) or []
            if not isinstance(findings, list) or bool(findings) != bool(process.returncode):
                print(f"ERROR {scope}: 命中与退出码不一致")
                return 2
            reviewed = 0
            for item in findings:
                approved = approved_history_finding(scope, item)
                reviewed += int(approved)
                # 永远不输出 Secret/Match/整条报告，也不输出原始 stdout/stderr。
                print(
                    json.dumps(
                        {
                            "scope": scope,
                            "rule": item["RuleID"],
                            "file": item["File"],
                            "line": item["StartLine"],
                            "commit": item.get("Commit", ""),
                            "fingerprint": item.get("Fingerprint", ""),
                            "classification": "reviewed_public_false_positive"
                            if approved
                            else "blocking",
                        },
                        ensure_ascii=False,
                    )
                )
            scope_code = int(len(findings) > reviewed)
            result_code = max(result_code, scope_code)
            print(f"{scope}: findings={len(findings)}, exit={scope_code}")
            if reviewed:
                print(
                    f"{scope}: native_exit={process.returncode}, "
                    f"reviewed_false_positives={reviewed}, "
                    f"blocking_findings={len(findings) - reviewed}"
                )
    return result_code


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        code = scan(args.repo.resolve())
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        # 工具错误也 fail closed，避免异常包含输入秘密。
        print("ERROR: 敏感检查未完成（异常内容已抑制）")
        code = 2
    raise SystemExit(code)


if __name__ == "__main__":
    main()
