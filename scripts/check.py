"""统一真实检查入口；工具链先 bootstrap，漏洞查询失败会阻断。"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    environment = os.environ.copy()
    environment["PATH"] = str(ROOT / ".tools/node/bin") + os.pathsep + environment["PATH"]
    checks = [
        ("当前内容与完整可达历史敏感扫描", [sys.executable, "-m", "scripts.scan_secrets"]),
        ("锁文件一致性", ["uv", "lock", "--check"]),
        ("文档检查", [sys.executable, "-m", "scripts.check_docs"]),
        ("Python lint", ["ruff", "check", "."]),
        ("Python format", ["ruff", "format", "--check", "."]),
        ("Python typecheck", ["mypy"]),
        ("离线技术 smoke 与合成阻断", [sys.executable, "-m", "pytest", "-m", "offline"]),
        ("Node 锁文件安装", ["npm", "--prefix", "frontend", "ci", "--ignore-scripts"]),
        ("Node 工具链校验", ["npm", "--prefix", "frontend", "run", "check:toolchain"]),
        ("Frontend tooling typecheck", ["npm", "--prefix", "frontend", "run", "typecheck"]),
        (
            "Frontend tooling 漏洞查询",
            ["npm", "--prefix", "frontend", "audit", "--audit-level=low"],
        ),
    ]
    for label, command in checks:
        print(f"CHECK: {label}", flush=True)
        process = subprocess.run(command, cwd=ROOT, env=environment)
        if process.returncode:
            raise SystemExit(process.returncode)
    audit = ROOT / ".audit"
    audit.mkdir(exist_ok=True)
    export = subprocess.run(
        [
            "uv",
            "export",
            "--frozen",
            "--all-groups",
            "--no-emit-project",
            "--output-file",
            str(audit / "requirements.txt"),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
    )
    if export.returncode:
        raise SystemExit("锁依赖导出失败")
    print("CHECK: Python runtime/dev/build 锁依赖漏洞查询", flush=True)
    subprocess.run(
        [
            "pip-audit",
            "-r",
            str(audit / "requirements.txt"),
            "--require-hashes",
            "--disable-pip",
            "--strict",
            "--format=json",
            "--output",
            str(audit / "python.json"),
        ],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    report = json.loads((audit / "python.json").read_text())
    dependencies = report["dependencies"]
    if any(dependency.get("vulns") or dependency.get("skip_reason") for dependency in dependencies):
        raise SystemExit("漏洞查询含命中或跳过，拒绝通过")
    print(f"Python audit: {len(dependencies)} packages, known vulnerabilities=0")
    print("检查完成：仅工程底座技术证据；业务与 G1–G3 尚未验收。")


if __name__ == "__main__":
    main()
