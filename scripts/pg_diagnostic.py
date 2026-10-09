"""Issue23 有界诊断 supervisor；只管理本轮创建的随机 Compose 项目。"""

import argparse
import json
import os
import re
import signal
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from scripts.prepare_pg import prepare

ROOT = Path(__file__).resolve().parents[1]
GROUPS = ("test_postgres", "test_worker_pg", "test_checkpoint_pg", "test_feishu_postgres")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deadline", required=True)
    parser.add_argument("--round", type=int, choices=(1, 2, 3), required=True)
    parser.add_argument("--node", action="append", default=[])
    parser.add_argument("--combined", action="store_true")
    parser.add_argument("--no-child-trace", action="store_true")
    args = parser.parse_args()
    deadline = datetime.fromisoformat(args.deadline).timestamp()
    audit = ROOT / ".audit" / "issue23"
    audit.mkdir(mode=0o700, parents=True, exist_ok=True)
    report_path = audit / f"round-{args.round}.json"
    if report_path.exists():
        raise SystemExit("diagnostic round already registered")
    project = "p123-" + uuid4().hex[:12]
    directory = ROOT / "runtime" / project
    records: list[dict[str, object]] = []
    record_lock = threading.RLock()
    containers: list[str] = []
    report: dict[str, object] = {
        "project": project,
        "round": args.round,
        "started_at": datetime.now(UTC).isoformat(),
        "deadline": args.deadline,
        "records": records,
        "containers": containers,
        "volume": project + "_pg_data",
        "result": "running",
        "source_mode": "postgres_technical",
        "model_mode": "not_used",
        "approval_mode": "simulated",
    }

    def save() -> None:
        with record_lock:
            report_path.write_text(json.dumps(report, indent=2) + "\n")
            report_path.chmod(0o600)

    def emit(record: dict[str, object]) -> None:
        with record_lock:
            record["at"] = datetime.now(UTC).isoformat()
            records.append(record)
            save()
            print(json.dumps(record), flush=True)

    save()  # 创建任何 Docker 资源前登记身份。
    prepare(directory)
    environment = {
        k: v
        for k, v in os.environ.items()
        if k
        in {
            "PATH",
            "HOME",
            "TMPDIR",
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "DOCKER_CONFIG",
        }
    }
    environment["COMMERCEOPS_PG_RUNTIME_DIR"] = str(directory)
    compose = ["docker", "compose", "-p", project, "-f", str(ROOT / "compose.yml")]

    def budget(seconds: float, *, cleanup: bool = False) -> float:
        available = deadline - time.time()
        if cleanup:
            return max(1, min(seconds, available))
        if available < 70:
            raise TimeoutError("diagnostic deadline reached; cleanup reserve")
        return min(seconds, available - 60)

    def capture(
        command: list[str], seconds: float = 10, *, cleanup: bool = False
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=budget(seconds, cleanup=cleanup),
        )

    def sample() -> None:
        # 全新自有 PG cluster；只读取安全列，不取 query/参数/env/DSN。
        query = """SET statement_timeout=1000; SELECT coalesce(json_agg(x),'[]') FROM
        (SELECT pid,datname,state,wait_event_type,wait_event,
        extract(epoch FROM clock_timestamp()-xact_start) AS transaction_age_seconds,
        pg_blocking_pids(pid) AS blocking_pids FROM pg_stat_activity
        WHERE backend_type='client backend' AND pid<>pg_backend_pid()) x"""
        try:
            result = capture(
                compose
                + [
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
                    query,
                ],
                5,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.startswith("["):
                        emit({"event": "pg_wait_sample", "rows": json.loads(line)})
            else:
                emit({"event": "pg_sample_failed", "exit": result.returncode})
        except subprocess.TimeoutExpired:
            emit({"event": "pg_sample_timeout"})

    def stop_container(name: str) -> None:
        # 只对事先登记且 label 相符的本轮容器操作；不使用完整 inspect。
        checked = capture(
            [
                "docker",
                "inspect",
                "--format",
                '{{index .Config.Labels "com.docker.compose.project"}}',
                name,
            ],
            5,
            cleanup=True,
        )
        if checked.returncode:
            return
        if checked.stdout.strip() != project:
            raise RuntimeError("owned container label mismatch")
        for action in (["stop", "-t", "3"], ["kill"], ["wait"]):
            try:
                result = capture(["docker", *action, name], 8, cleanup=True)
                emit(
                    {
                        "event": "container_termination",
                        "container": name,
                        "action": action[0],
                        "exit": result.returncode,
                    }
                )
            except subprocess.TimeoutExpired:
                emit(
                    {
                        "event": "container_termination_timeout",
                        "container": name,
                        "action": action[0],
                    }
                )

    def run(label: str, arguments: list[str], limit: float, *, name: str | None = None) -> bool:
        emit({"event": "command_start", "label": label, "limit_seconds": limit})
        duration = budget(limit)
        process = subprocess.Popen(
            compose + arguments,
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
            bufsize=1,
        )
        if process.stdout is None:
            raise RuntimeError("diagnostic stdout pipe missing")

        def read() -> None:
            if process.stdout is None:
                return
            for line in process.stdout:
                position = line.find("PG_DIAG ")
                if position >= 0:
                    try:
                        emit({"event": "pytest_progress", "data": json.loads(line[position + 8 :])})
                    except ValueError:
                        emit({"event": "diagnostic_decode_failed"})
                elif re.search(r"\d+ passed|\d+ failed|collected \d+", line):
                    emit({"event": "pytest_summary", "line": line.strip()[:200]})
                elif re.match(r'\s*(Timeout \(|Thread 0x|Current thread|File ")', line):
                    emit({"event": "stack_frame", "frame": line.strip()[:400]})
                # 其他 stdout/stderr 不保留，不输出原始数据库/SDK错误。

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        timed_out = False
        try:
            process.wait(timeout=duration)
        except subprocess.TimeoutExpired:
            timed_out = True
            emit({"event": "command_timeout", "label": label, "cli_pid": process.pid})
            sample()
            if name is not None:
                stop_container(name)
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        finally:
            reader.join(timeout=3)
            process.stdout.close()
        emit(
            {
                "event": "command_end",
                "label": label,
                "exit": process.returncode,
                "timed_out": timed_out,
            }
        )
        return not timed_out and process.returncode == 0

    def tests(label: str, paths: list[str], limit: float, *, collect: bool = False) -> bool:
        name = project + "-" + label
        containers.append(name)
        save()
        arguments = [
            "run",
            "--rm",
            "--no-deps",
            "--name",
            name,
            "-e",
            "P123_DIAG=1",
            "-e",
            "P123_TRACE_CHILD=" + ("0" if args.no_child_trace else "1"),
            "pg-test",
            "python",
            "-u",
            "-m",
            "pytest",
            "-p",
            "tests.diagnostic_plugin",
            "-m",
            "integration",
            "-vv",
            "-s",
            "--tb=no",
            "-o",
            "faulthandler_timeout=45",
            *paths,
        ]
        if collect:
            arguments.append("--collect-only")
        return run(label, arguments, limit, name=name)

    try:
        if not run("build", ["build", "db-init", "pg-test"], 120):
            raise RuntimeError("bounded build failed")
        if not run("healthy", ["up", "-d", "--wait", "--wait-timeout", "60", "postgres"], 75):
            raise RuntimeError("bounded PG startup failed")
        for action in ("migrate", "setup-checkpointer", "grant-runtime", "revision"):
            if not run(
                action,
                [
                    "run",
                    "--rm",
                    "--no-deps",
                    "db-init",
                    "python",
                    "-m",
                    "commerceops.entrypoints.database",
                    action,
                ],
                30,
            ):
                raise RuntimeError("bounded initialization failed")
        paths = [] if args.combined else [f"tests/{group}.py" for group in GROUPS]
        if not tests("collection", paths, 30, collect=True):
            raise RuntimeError("collection failed")
        if args.combined:
            if not tests("combined", [], 300):
                report["failed_target"] = "combined"
                raise RuntimeError("combined failed")
        elif args.node:
            for index, node in enumerate(args.node):
                if not tests("node-" + str(index), [node], 90):
                    report["failed_target"] = node
                    raise RuntimeError("node failed")
        else:
            for group in GROUPS:
                if not tests(group, ["tests/" + group + ".py"], 300):
                    report["failed_target"] = group
                    raise RuntimeError("group failed")
        report["result"] = "passed_no_hang_reproduced"
    except Exception as error:
        report["result"] = "failed"
        report["error_class"] = type(error).__name__
        emit({"event": "diagnostic_failed", "code": type(error).__name__})
    finally:
        try:
            cleanup = capture(
                compose + ["down", "--volumes", "--remove-orphans", "--rmi", "local"],
                60,
                cleanup=True,
            )
            report["cleanup_exit"] = cleanup.returncode
            if cleanup.returncode == 0:
                for filename in ("owner_password", "app_password"):
                    (directory / filename).unlink()
                directory.rmdir()
        except Exception as error:
            report["cleanup_exit"] = "unconfirmed"
            report["cleanup_error_class"] = type(error).__name__
        report["finished_at"] = datetime.now(UTC).isoformat()
        save()
        print(
            json.dumps(
                {
                    "project": project,
                    "result": report["result"],
                    "cleanup_exit": report["cleanup_exit"],
                }
            ),
            flush=True,
        )
    if report["result"] != "passed_no_hang_reproduced" or report["cleanup_exit"] != 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
