"""同一真实 PG smoke 供本地/CI；独立项目/随机卷，仅清理本次创建资源。"""

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from scripts.prepare_pg import prepare

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    project = "p102-" + uuid4().hex[:12]
    directory = ROOT / "runtime" / project
    prepare(directory)
    environment = os.environ.copy()
    environment["COMMERCEOPS_PG_RUNTIME_DIR"] = str(directory)
    compose = ["docker", "compose", "-p", project, "-f", str(ROOT / "compose.yml")]
    evidence: dict[str, object] = {
        "project": project,
        "started_at": datetime.now(UTC).isoformat(),
        "source_mode": "postgres_technical",
        "model_mode": "not_used",
        "approval_mode": "not_applicable",
        "checks": [],
        "named_volume": f"{project}_pg_data",
    }
    checks: list[str] = []

    def run(label: str, args: list[str], *, failure: bool = False) -> None:
        print(f"PG CHECK: {label}", flush=True)
        result = subprocess.run(
            compose + args, cwd=ROOT, env=environment, capture_output=True, text=True
        )
        if failure:
            if result.returncode == 0:
                raise RuntimeError(f"{label}: unexpected success")
            # 故障输出不包含环境/DSN/密码；只保留可见失败分类。
            print(f"{label}: expected nonzero exit")
        else:
            print(result.stdout, end="", flush=True)
            if result.returncode:
                # Docker/pytest 诊断不使用秘密参数，仍不打印环境或完整配置。
                print(result.stderr, flush=True)
                raise RuntimeError(f"{label}: exit {result.returncode}")
        checks.append(label)

    def init(action: str) -> list[str]:
        return [
            "run",
            "--rm",
            "--no-deps",
            "db-init",
            "python",
            "-m",
            "commerceops.entrypoints.database",
            action,
        ]

    def probe(action: str) -> list[str]:
        return [
            "run",
            "--rm",
            "--no-deps",
            "pg-test",
            "python",
            "-m",
            "scripts.pg_persistence",
            action,
        ]

    try:
        run("build locked init and real PG test images", ["build", "db-init", "pg-test"])
        run("empty PG healthy", ["up", "-d", "--wait", "--wait-timeout", "90", "postgres"])
        run(
            "PG actual version database role",
            [
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "commerceops_owner",
                "-d",
                "commerceops",
                "-At",
                "-c",
                "SELECT version(),current_database(),current_user",
            ],
        )
        run("PG health state", ["ps", "--format", "json", "postgres"])
        for repeat in range(2):
            for action in ("migrate", "setup-checkpointer", "grant-runtime", "revision"):
                run(f"initialize {repeat + 1}: {action}", init(action))
        run("real PG constraints and failure recovery", ["run", "--rm", "--no-deps", "pg-test"])
        run("commit stable persistence fixture", probe("seed"))
        run("restart PostgreSQL", ["restart", "postgres"])
        run("restart healthy", ["up", "-d", "--wait", "postgres"])
        run("data/checkpoint after restart", probe("verify"))
        run(
            "recreate container preserving named volume",
            ["up", "-d", "--force-recreate", "--wait", "postgres"],
        )
        run("data/checkpoint after container recreation", probe("verify"))
        run("stop PG for unavailable failure", ["stop", "postgres"])
        run("DB unavailable init visibly fails", init("revision"), failure=True)
        run("recover PG healthy", ["up", "-d", "--wait", "postgres"])
        run("data/checkpoint after outage", probe("verify"))
        evidence["result"] = "passed"
    finally:
        evidence["checks"] = checks
        evidence["finished_at"] = datetime.now(UTC).isoformat()
        # 明确指定刚创建的随机项目；不清理别人的卷，也不使用 prune。
        cleanup = subprocess.run(
            compose + ["down", "--volumes", "--remove-orphans", "--rmi", "local"],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
        )
        evidence["cleanup_exit"] = cleanup.returncode
        (ROOT / ".audit").mkdir(exist_ok=True)
        (ROOT / ".audit" / "pg-smoke.json").write_text(json.dumps(evidence, indent=2))
        if cleanup.returncode:
            raise RuntimeError(f"test resource cleanup failed: project={project}")
        for name in ("owner_password", "app_password"):
            (directory / name).unlink()
        directory.rmdir()
    print(f"PG smoke passed; owned project removed: {project}")


if __name__ == "__main__":
    main()
