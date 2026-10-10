"""Issue23 有界诊断 supervisor；只管理本轮创建的随机 Compose 项目。"""

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from scripts.pg_diag_shutdown import container_stop, finish, remaining
from scripts.prepare_pg import prepare

ROOT = Path(__file__).resolve().parents[1]
GROUPS = ("test_postgres", "test_worker_pg", "test_checkpoint_pg", "test_feishu_postgres")


def collected_nodes(records: list[dict[str, object]]) -> list[str]:
    collections = []
    for record in records:
        data = record.get("data")
        if record.get("event") == "pytest_progress" and isinstance(data, dict):
            if data.get("event") == "collection":
                collections.append(data)
    if len(collections) != 1:
        raise RuntimeError("one complete integration collection required")
    data = collections[0]
    nodes = data.get("nodes")
    if not isinstance(nodes, list) or not nodes or type(data.get("count")) is not int:
        raise RuntimeError("invalid integration collection")
    result: list[str] = []
    for node in nodes:
        if not isinstance(node, str):
            raise RuntimeError("invalid integration node")
        path, separator, _ = node.partition("::")
        if (
            not separator
            or not path.startswith("tests/")
            or not path.endswith(".py")
            or ".." in path.split("/")
            or "\\" in path
        ):
            raise RuntimeError("invalid integration node path")
        result.append(node)
    if data["count"] != len(result) or len(set(result)) != len(result):
        raise RuntimeError("integration collection count or uniqueness mismatch")
    return result


def combined_groups(nodes: list[str]) -> dict[str, list[str]]:
    phase3 = [node for node in nodes if node.split("::", 1)[0].startswith("tests/test_p3")]
    if not phase3:
        return {"combined": nodes}  # 历史无P3保持原单条命令、原空paths。
    phase3_set = set(phase3)
    existing = [node for node in nodes if node not in phase3_set]
    return {
        label: group
        for label, group in (("combined-existing", existing), ("combined-phase3", phase3))
        if group
    }


def run_combined(
    records: list[dict[str, object]],
    report: dict[str, object],
    test_command: Callable[[str, list[str], float], bool],
) -> None:
    expected = collected_nodes(records)
    groups = combined_groups(expected)
    flattened = [node for group in groups.values() for node in group]
    if (
        not groups
        or any(not group for group in groups.values())
        or len(flattened) != len(set(flattened))
        or set(flattened) != set(expected)
    ):
        raise RuntimeError("combined integration coverage mismatch")
    report["combined_counts"] = {label: len(group) for label, group in groups.items()}
    for label, group in groups.items():
        report["failed_target"] = label
        start = len(records)
        paths = [] if label == "combined" else sorted({node.split("::", 1)[0] for node in group})
        # 仍使用main的同一expires-75预算；不重置absolute deadline或放宽单命令300s。
        if not test_command(label, paths, 300):
            raise RuntimeError("combined integration group failed")
        if set(collected_nodes(records[start:])) != set(group):
            raise RuntimeError("actual integration group collection mismatch")
    report.pop("failed_target", None)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deadline", required=True)
    parser.add_argument("--round", type=int, choices=(1, 2, 3), required=True)
    parser.add_argument("--node", action="append", default=[])
    parser.add_argument("--combined", action="store_true")
    parser.add_argument("--no-child-trace", action="store_true")
    parser.add_argument("--session", choices=("initial", "followup", "ci"), default="initial")
    parser.add_argument("--fault-probe", action="store_true")
    parser.add_argument("--full-smoke", action="store_true")
    args = parser.parse_args()
    if (args.session == "followup" and args.round > 2) or (
        args.session == "ci" and args.round != 1
    ):
        raise SystemExit("session round limit exceeded")
    deadline = datetime.fromisoformat(args.deadline).timestamp()
    expires = time.monotonic() + max(0, deadline - time.time())
    try:
        remaining(expires - 75, 1)
    except TimeoutError:
        raise SystemExit("diagnostic deadline expired before resource registration") from None
    cleanup_deadline: float | None = None
    stopping_confirmed = True
    audit = (
        ROOT / ".audit" / ("issue23" if args.session == "initial" else "issue23-" + args.session)
    )
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
        "session": args.session,
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
        if cleanup:
            return remaining(cleanup_until(), seconds)
        return remaining(expires - 75, seconds)

    def cleanup_until() -> float:
        nonlocal cleanup_deadline
        if cleanup_deadline is None:
            cleanup_deadline = min(expires, time.monotonic() + 60)
        return cleanup_deadline

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
                cleanup=True,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.startswith("["):
                        emit({"event": "pg_wait_sample", "rows": json.loads(line)})
            else:
                emit({"event": "pg_sample_failed", "exit": result.returncode})
        except subprocess.TimeoutExpired:
            emit({"event": "pg_sample_timeout"})

    def stop_container(name: str, until: float) -> bool:
        return container_stop(
            name,
            project,
            lambda command, seconds: subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=remaining(until, seconds),
            ),
            emit,
        )

    def run(
        label: str,
        arguments: list[str],
        limit: float,
        *,
        name: str | None = None,
        expect_failure: bool = False,
        fault: bool = False,
    ) -> bool:
        nonlocal stopping_confirmed
        emit({"event": "command_start", "label": label, "limit_seconds": limit})
        duration = budget(limit)
        command = compose + arguments
        if fault:
            # 仅诊断注入：自有 CLI wrapper 故意忽略 TERM，即使容器退出也等待。
            command = [
                sys.executable,
                "-u",
                "-c",
                "import signal,subprocess,sys,threading; "
                "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                "subprocess.Popen(sys.argv[1:]).wait(); threading.Event().wait()",
                *command,
            ]
        process = subprocess.Popen(
            command,
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
                elif line.startswith("persistence fixture committed: task=") or line.startswith(
                    "persistence verified: task="
                ):
                    match = re.fullmatch(
                        r"persistence (fixture committed|verified): task=([0-9a-f-]{36}), "
                        r"thread=([0-9a-f-]{36})(, inbox/jobs/audit=1)?",
                        line.strip(),
                    )
                    if match:
                        emit(
                            {
                                "event": "g1_persistence",
                                "kind": match[1],
                                "task": match[2],
                                "thread": match[3],
                                "count_one": match[4] is not None,
                            }
                        )
                elif line.startswith("G2 EVIDENCE: "):
                    data = json.loads(line.removeprefix("G2 EVIDENCE: "))
                    if (
                        data.get("source_mode"),
                        data.get("model_mode"),
                        data.get("approval_mode"),
                    ) == ("postgres_technical", "not_used", "simulated"):
                        emit({"event": "g2_evidence", "data": data})
                # 其他 stdout/stderr 不保留，不输出原始数据库/SDK错误。

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        timed_out = False
        observed_error = False
        try:
            process.wait(timeout=duration)
        except subprocess.TimeoutExpired:
            timed_out = True
            emit({"event": "command_timeout", "label": label, "cli_pid": process.pid})
        finally:
            until = cleanup_until() if timed_out else min(expires, time.monotonic() + 30)

            def observe() -> bool:
                nonlocal observed_error
                if timed_out:
                    try:
                        if fault:
                            raise RuntimeError("controlled sample failure")
                        sample()
                    except Exception as error:
                        observed_error = True
                        emit(
                            {
                                "event": "sample_error",
                                "code": type(error).__name__,
                                "injected": fault,
                            }
                        )
                return True if name is None else stop_container(name, until)

            ended = finish(process, reader, until, observe, emit)
            stopping_confirmed = stopping_confirmed and ended.confirmed
            if not ended.confirmed:
                emit({"event": "shutdown_unconfirmed", "label": label})
        emit(
            {
                "event": "command_end",
                "label": label,
                "exit": process.returncode,
                "timed_out": timed_out,
                "stopping_confirmed": ended.confirmed,
                "sample_error": observed_error,
            }
        )
        return (
            not timed_out
            and ended.confirmed
            and ((process.returncode != 0) if expect_failure else process.returncode == 0)
        )

    def tests(label: str, paths: list[str], limit: float, *, collect: bool = False) -> bool:
        name = project + "-" + label
        containers.append(name)
        save()
        arguments = [
            "run",
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
        actions = ("migrate", "setup-checkpointer", "grant-runtime", "revision")
        for index, action in enumerate(actions * (2 if args.full_smoke else 1)):
            name = project + "-init-" + str(index)
            containers.append(name)
            save()
            if not run(
                action,
                [
                    "run",
                    "--no-deps",
                    "--name",
                    name,
                    "db-init",
                    "python",
                    "-m",
                    "commerceops.entrypoints.database",
                    action,
                ],
                30,
                name=name,
            ):
                raise RuntimeError("bounded initialization failed")
        if args.fault_probe:
            name = project + "-fault"
            containers.append(name)
            save()
            run(
                "fault-probe",
                [
                    "run",
                    "--no-deps",
                    "--name",
                    name,
                    "pg-test",
                    "python",
                    "-u",
                    "-c",
                    "import signal,threading; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                    "threading.Event().wait()",
                ],
                2,
                name=name,
                fault=True,
            )
            required = {
                "command_timeout",
                "sample_error",
                "cli_term",
                "cli_kill",
                "cli_os_wait",
                "container_wait",
                "reader_end",
            }
            found = {record["event"] for record in records}
            if not required.issubset(found) or not stopping_confirmed:
                raise RuntimeError("fault probe shutdown evidence incomplete")
            report["result"] = "expected_diagnostic_timeout_confirmed"
            return
        paths = [] if args.combined else [f"tests/{group}.py" for group in GROUPS]
        if not tests("collection", paths, 30, collect=True):
            raise RuntimeError("collection failed")
        if args.combined:
            run_combined(records, report, tests)
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
        if args.full_smoke:
            g2: set[str] = set()
            for record in records:
                data = record.get("data")
                if record["event"] == "g2_evidence" and isinstance(data, dict):
                    scenario = data.get("scenario")
                    if isinstance(scenario, str):
                        g2.add(scenario)
            required = {
                "cross_process_resume",
                "receipt_commit_checkpoint_gap",
                "graph_lock_loss_cancel",
                "graph_noncooperative_exit",
                "checkpoint_db_failure_recovered",
            }
            if not required.issubset(g2):
                raise RuntimeError("required G2 evidence missing")
            for label, command, failure in (
                (
                    "seed",
                    [
                        "run",
                        "--rm",
                        "--no-deps",
                        "pg-test",
                        "python",
                        "-m",
                        "scripts.pg_persistence",
                        "seed",
                    ],
                    False,
                ),
                ("restart", ["restart", "postgres"], False),
                ("restart-healthy", ["up", "-d", "--wait", "postgres"], False),
                (
                    "verify-restart",
                    [
                        "run",
                        "--rm",
                        "--no-deps",
                        "pg-test",
                        "python",
                        "-m",
                        "scripts.pg_persistence",
                        "verify",
                    ],
                    False,
                ),
                ("recreate", ["up", "-d", "--force-recreate", "--wait", "postgres"], False),
                (
                    "verify-recreate",
                    [
                        "run",
                        "--rm",
                        "--no-deps",
                        "pg-test",
                        "python",
                        "-m",
                        "scripts.pg_persistence",
                        "verify",
                    ],
                    False,
                ),
                ("stop-db", ["stop", "postgres"], False),
                (
                    "unavailable",
                    [
                        "run",
                        "--rm",
                        "--no-deps",
                        "db-init",
                        "python",
                        "-m",
                        "commerceops.entrypoints.database",
                        "revision",
                    ],
                    True,
                ),
                ("recover", ["up", "-d", "--wait", "postgres"], False),
                (
                    "verify-outage",
                    [
                        "run",
                        "--rm",
                        "--no-deps",
                        "pg-test",
                        "python",
                        "-m",
                        "scripts.pg_persistence",
                        "verify",
                    ],
                    False,
                ),
            ):
                if not run(label, command, 60, expect_failure=failure):
                    raise RuntimeError("G1 lifecycle failed")
            report["g1_complete"] = True
        report["result"] = "passed_no_hang_reproduced"
    except Exception as error:
        report["result"] = "failed"
        report["error_class"] = type(error).__name__
        emit({"event": "diagnostic_failed", "code": type(error).__name__})
    finally:
        try:
            for name in containers:
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
                if checked.returncode == 0 and checked.stdout.strip() == project:
                    removed = capture(["docker", "rm", name], 5, cleanup=True)
                    if removed.returncode:
                        raise RuntimeError("owned container removal unconfirmed")
                elif checked.returncode == 0:
                    stopping_confirmed = False
            cleanup = capture(
                compose + ["down", "--volumes", "--remove-orphans", "--rmi", "local"],
                60,
                cleanup=True,
            )
            report["cleanup_exit"] = cleanup.returncode
            report["stopping_confirmed"] = stopping_confirmed
            if not stopping_confirmed:
                report["cleanup_exit"] = "unconfirmed"
            if cleanup.returncode == 0 and stopping_confirmed:
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
        if report["cleanup_exit"] != 0:
            raise SystemExit(1)
    if report["result"] not in (
        "passed_no_hang_reproduced",
        "expected_diagnostic_timeout_confirmed",
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
