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

from scripts.pg_ci_evidence import (
    EXISTING_MODULES,
    EXISTING_REBALANCED_GROUPS,
    environment_identity,
    execution_identity,
    identity,
    partition,
    read_reply_parent_parts,
    require_same_binding,
    safe_report,
    safe_shard_report,
    shard_groups,
    validate_plan,
)
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
    phase3 = [
        node
        for node in nodes
        if node.split("::", 1)[0].startswith(("tests/test_p3", "tests/test_p4"))
    ]
    if not phase3:
        return {"combined": nodes}  # 历史无P3保持原单条命令、原空paths。
    phase3_set = set(phase3)
    existing = [node for node in nodes if node not in phase3_set]
    # 40373408272: all 246 calls passed, but their shared command hit 300s.
    # Move complete P5 natural modules only; every command keeps the same 300s cap.
    p5_paths = sorted(
        {node.split("::", 1)[0] for node in existing if node.startswith("tests/test_p5_")}
    )
    ordinary = [node for node in existing if node.split("::", 1)[0] not in p5_paths]
    groups = {"combined-existing": ordinary} if ordinary else {}
    for path in p5_paths:
        label = "combined-existing-" + path.removeprefix("tests/").removesuffix(".py")
        groups[label] = [node for node in existing if node.split("::", 1)[0] == path]
    # 从实际collection按现有P3模块派生；不硬编码阶段cardinality或挑选test node。
    for path in sorted({node.split("::", 1)[0] for node in phase3}):
        label = "combined-phase3-" + path.removeprefix("tests/").removesuffix(".py").replace(
            "/", "-"
        )
        group = [node for node in phase3 if node.split("::", 1)[0] == path]
        moved = next(
            ((name, paths) for name, paths in EXISTING_REBALANCED_GROUPS.items() if path in paths),
            None,
        )
        if moved is not None:
            name, paths = moved
            if name not in groups:
                complete = [node for node in phase3 if node.split("::", 1)[0] in paths]
                if name == "combined-existing-p4-read-reply-parent":
                    # 39623794226 existing绝对截止耗尽；仅完整前六项移phase3。
                    # 保留原6+5边界、独立命令及300s上限，与证据分区共用排序规则。
                    for index, part in enumerate(read_reply_parent_parts(complete), 1):
                        scope = "phase3" if index == 1 else "existing"
                        groups[f"combined-{scope}-p4-read-reply-parent-part-{index}"] = part
                elif name == "combined-existing-p4-verified-history":
                    # 39154216134完整14节点累计触发300s；仅按完整collection排序分7+7。
                    # 新节点仍自动纳入，保持原existing分区、命令上限和精确配对。
                    width = 7
                    ordered = sorted(complete)
                    for offset in range(0, len(ordered), width):
                        groups[f"{name}-part-{offset // width + 1}"] = ordered[
                            offset : offset + width
                        ]
                else:
                    groups[name] = complete
            continue
        # 610实证此唯一approval模块累计300s；仅其按完整collection规范顺序14节点子批。
        # 不筛选通过节点、改用例或放宽任何命令/总deadline；其余自然模块原样。
        if path == "tests/test_p3_approval_pg.py" and len(group) > 14:
            ordered = sorted(group)
            for offset in range(0, len(ordered), 14):
                groups[f"{label}-part-{offset // 14 + 1}"] = ordered[offset : offset + 14]
        elif path == "tests/test_p4_terminal_recovery_pg.py":
            # 相互独立DB先构造本命令完整失败历史，保留自然30s backoff；
            # 全12节点实测119.071/103.384/108.805s，各四节点独占原300s命令。
            ordered = sorted(group)
            for offset in range(0, len(ordered), 4):
                groups[f"{label}-part-{offset // 4 + 1}"] = ordered[offset : offset + 4]
        elif path == "tests/test_p4_acceptance_pg.py" and any(
            "::test_terminal_native_enrollment_same_anchor_once_and_cold_replay[" in node
            for node in group
        ):
            # 新terminal两schema合计实测337.05s，不能共用原300s命令。
            # 原节点保留一组，各terminal节点独立；覆盖仍由完整collection核对。
            terminal = sorted(
                node
                for node in group
                if "::test_terminal_native_enrollment_same_anchor_once_and_cold_replay[" in node
            )
            original = [node for node in group if node not in terminal]
            parts = ([original] if original else []) + [[node] for node in terminal]
            for index, part in enumerate(parts, 1):
                groups[f"{label}-part-{index}"] = part
        else:
            groups[label] = group
    # Hosted实证：phase3 20次pytest启动/collection前累计215.688s，末Gateway
    # 仅余10.399s而尚未collect。合并同分区完整小模块，避免逐模块重启解释器。
    # 大模块、quality原业务模块及approval 14节点分片保持；单命令仍300s。
    business = {n for n in phase3 if n.split("::", 1)[0] not in EXISTING_MODULES}
    result: dict[str, list[str]] = {}
    pending: list[tuple[str, list[str]]] = []
    batch_number = 0

    def flush() -> None:
        nonlocal batch_number
        if not pending:
            return
        if len(pending) == 1:
            label, group = pending[0]
            result[label] = group
        else:
            batch_number += 1
            result[f"combined-phase3-batch-{batch_number}"] = [
                node for _, group in pending for node in group
            ]
        pending.clear()

    for label, group in groups.items():
        if not set(group) <= business:
            result[label] = group
            continue
        # 验收模块虽仅5节点，single/20项两条原生恢复链已实测约200s；独占原300s预算。
        if len(group) > 20 or label.startswith(
            (
                "combined-phase3-test_p4_acceptance_pg",
                "combined-phase3-test_p4_terminal_recovery_pg",
            )
        ):
            flush()
            result[label] = group
            continue
        if sum(len(part) for _, part in pending) + len(group) > 20:
            flush()
        pending.append((label, group))
    flush()
    return result


def run_combined(
    records: list[dict[str, object]],
    report: dict[str, object],
    test_command: Callable[[str, list[str], float], bool],
    scope: str = "all",
    *,
    history_read_regression: bool = False,
    shard_plan: dict[str, object] | None = None,
    shard_id: int | None = None,
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
    selected = partition(expected, scope)
    if scope != "all":
        groups = {label: group for label, group in groups.items() if set(group) <= set(selected)}
    if shard_plan is not None:
        if scope != "all" or history_read_regression or shard_id is None:
            raise ValueError("shard selection cannot mix legacy scopes or history regression")
        groups = shard_groups(shard_plan, shard_id, expected)
        selected = sorted(node for group in groups.values() for node in group)
    elif shard_id is not None:
        raise ValueError("shard ID requires plan")
    if history_read_regression:
        required = {
            "combined-existing-p4-verified-history-part-1": 7,
            "combined-existing-p4-verified-history-part-2": 7,
            "combined-existing-p4-read-reply-parent-part-2": 5,
        }
        if scope != "all" or any(
            len(groups.get(label, [])) != count for label, count in required.items()
        ):
            raise RuntimeError("history/read regression requires exact existing 7+7+5 groups")
        groups = {label: groups[label] for label in required}
        selected = [node for group in groups.values() for node in group]
        report["validation_scope"] = "local_history_read_regression_only"
        report["full_gate"] = False
    chosen = [node for group in groups.values() for node in group]
    if not groups or len(chosen) != len(set(chosen)) or set(chosen) != set(selected):
        raise RuntimeError("selected scope coverage mismatch")
    report["full_node_ids"] = sorted(expected)
    modules: list[dict[str, object]] = []
    report["combined_modules"] = modules
    report["combined_counts"] = {label: len(group) for label, group in groups.items()}
    for label, group in groups.items():
        report["failed_target"] = label
        start = len(records)
        paths = (
            []
            if label == "combined"
            else group
            if label.startswith(
                (
                    "combined-phase3-test_p3_approval_pg-part-",
                    "combined-phase3-test_p4_acceptance_pg-part-",
                    "combined-phase3-test_p4_terminal_recovery_pg-part-",
                    "combined-existing-p4-verified-history-part-",
                    "combined-existing-p4-read-reply-parent-part-",
                    "combined-phase3-p4-read-reply-parent-part-",
                )
            )
            else sorted({node.split("::", 1)[0] for node in group})
        )
        # 仍使用main的同一expires-75预算；不重置absolute deadline或放宽单命令300s。
        completed = test_command(label, paths, 300)
        if completed:
            observed = collected_nodes(records[start:])
        else:
            try:
                observed = collected_nodes(records[start:])
            except RuntimeError:
                observed = []
        calls = [
            r["data"]
            for r in records[start:]
            if r.get("event") == "pytest_progress" and isinstance(r.get("data"), dict)
        ]
        passed = [
            d["nodeid"]
            for d in calls
            if isinstance(d, dict)
            and d.get("event") == "phase_end"
            and d.get("phase") == "call"
            and d.get("outcome") == "passed"
        ]
        ends = [
            r
            for r in records[start:]
            if r.get("event") == "command_end" and r.get("label") == label
        ]
        exit_code = ends[-1]["exit"] if ends else (0 if completed else 1)
        modules.append(
            {
                "label": label,
                "expected_node_ids": sorted(group),
                "actual_node_ids": sorted(observed),
                "passed_node_ids": sorted(passed),
                "exit_code": exit_code,
                "result": completed,
            }
        )
        if not completed:
            raise RuntimeError("combined integration group failed")
        if set(collected_nodes(records[start:])) != set(group):
            raise RuntimeError("actual integration group collection mismatch")
    report.pop("failed_target", None)


def cleanup_registered_containers(
    names: list[str],
    project: str,
    capture: Callable[[list[str], float], subprocess.CompletedProcess[str]],
    stage: Callable[[str, int, int], None],
) -> int:
    """只按已登记名称一次核全owner/停止状态，按不可变ID删除；不force。"""
    stage("inspect-registered", 0, 0)
    if not names:
        return 0
    if len(names) != len(set(names)):
        raise RuntimeError("duplicate registered cleanup container")
    checked = capture(["docker", "inspect", *names], 5)
    if checked.returncode:
        raise RuntimeError("registered cleanup ownership unconfirmed")
    records = json.loads(checked.stdout)
    if not isinstance(records, list) or len(records) != len(names):
        raise RuntimeError("registered cleanup set unconfirmed")
    ids: list[str] = []
    observed: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise RuntimeError("registered cleanup metadata unconfirmed")
        name = record.get("Name")
        identifier = record.get("Id")
        config, state = record.get("Config"), record.get("State")
        labels = config.get("Labels") if isinstance(config, dict) else None
        if (
            not isinstance(name, str)
            or name.removeprefix("/") not in names
            or name.removeprefix("/") in observed
            or not isinstance(identifier, str)
            or re.fullmatch(r"[0-9a-f]{64}", identifier) is None
            or identifier in ids
            or not isinstance(labels, dict)
            or labels.get("com.docker.compose.project") != project
            or not isinstance(state, dict)
            or state.get("Running") is not False
            or type(state.get("Pid")) is not int
            or state["Pid"] != 0
            or state.get("Status") != "exited"
        ):
            stage("verify-registered", len(ids), 0)
            raise RuntimeError("registered cleanup owner or stopped state unconfirmed")
        observed.add(name.removeprefix("/"))
        ids.append(identifier)
    if observed != set(names):
        raise RuntimeError("registered cleanup set unconfirmed")
    stage("remove-registered", len(ids), 0)
    # 批量删除使用原cleanup剩余预算；capture仍取固定cleanup/总截止的较小值。
    removed = capture(["docker", "rm", *ids], 60)
    confirmed = removed.stdout.splitlines()
    if len(confirmed) != len(set(confirmed)) or not set(confirmed) <= set(ids):
        raise RuntimeError("registered cleanup removal receipt unconfirmed")
    if removed.returncode or set(confirmed) != set(ids):
        stage("partial-removal", len(ids), len(confirmed))
        raise RuntimeError("registered cleanup removal unconfirmed")
    stage("removed-registered", len(ids), len(ids))
    return len(ids)


def owned_pg_image_id(
    compose: list[str],
    project: str,
    capture: Callable[[list[str]], subprocess.CompletedProcess[str]],
) -> str:
    """Read the native image config ID from the single owned, running PG container."""
    if not re.fullmatch(r"p123-[0-9a-f]{12}", project) or compose[:4] != [
        "docker",
        "compose",
        "-p",
        project,
    ]:
        raise RuntimeError("owned PostgreSQL project required")
    selected = capture(compose + ["ps", "--quiet", "postgres"])
    container = selected.stdout.strip()
    if selected.returncode != 0 or not re.fullmatch(r"[0-9a-f]{64}", container):
        raise RuntimeError("one owned PostgreSQL container required")
    template = (
        "{{.Id}}|{{.Image}}|{{.State.Running}}|"
        '{{index .Config.Labels "com.docker.compose.project"}}|'
        '{{index .Config.Labels "com.docker.compose.service"}}'
    )
    observed = capture(["docker", "container", "inspect", "--format", template, container])
    fields = observed.stdout.strip().split("|")
    if (
        observed.returncode != 0
        or len(fields) != 5
        or fields[0] != container
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", fields[1])
        or fields[2:] != ["true", project, "postgres"]
    ):
        raise RuntimeError("actual owned PostgreSQL image identity required")
    return fields[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deadline", required=True)
    parser.add_argument("--round", type=int, choices=(1, 2, 3), required=True)
    parser.add_argument("--node", action="append", default=[])
    parser.add_argument("--combined", action="store_true")
    parser.add_argument("--history-read-regression", action="store_true")
    parser.add_argument("--no-child-trace", action="store_true")
    parser.add_argument("--session", choices=("initial", "followup", "ci"), default="initial")
    parser.add_argument("--fault-probe", action="store_true")
    parser.add_argument("--full-smoke", action="store_true")
    parser.add_argument("--ci-scope", choices=("all", "existing", "phase3"), default="all")
    parser.add_argument("--shard-plan", type=Path)
    parser.add_argument("--shard-id", type=int)
    args = parser.parse_args()
    shard_plan = None
    if args.shard_plan is not None or args.shard_id is not None:
        if (
            args.shard_plan is None
            or args.shard_id is None
            or args.session != "ci"
            or not args.combined
            or args.ci_scope != "all"
            or args.node
            or args.fault_probe
            or args.history_read_regression
        ):
            parser.error("shard mode requires CI combined with only a plan and declared ID")
        shard_plan = json.loads(args.shard_plan.read_text())
        validate_plan(shard_plan)
        shard_groups(shard_plan, args.shard_id, shard_plan["full_node_ids"])
        if args.full_smoke != (args.shard_id == 0):
            parser.error("only designated shard zero requires full smoke")
    if args.history_read_regression and (
        args.session != "initial"
        or not args.combined
        or args.ci_scope != "all"
        or args.node
        or args.full_smoke
        or args.fault_probe
    ):
        parser.error("history/read regression is local combined 7+7+5 only, never a CI/full gate")
    if args.ci_scope != "all" and (
        args.session != "ci"
        or not args.combined
        or args.node
        or args.fault_probe
        or (args.ci_scope == "existing" and not args.full_smoke)
        or (args.ci_scope == "phase3" and args.full_smoke)
    ):
        parser.error("scoped CI requires combined and correct full-smoke scope")
    ci_identity = identity(ROOT) if args.ci_scope != "all" or shard_plan is not None else None
    shard_binding = None
    if shard_plan is not None:
        shard_binding = {
            **(ci_identity or {}),
            "execution": execution_identity(),
            "environment": environment_identity(ROOT),
        }
        require_same_binding(
            shard_plan["binding"],
            shard_binding,
            "shard plan differs from exact checkout/tools/run/environment",
        )
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
            "faulthandler_timeout=0",  # Existing plugin supplies the real 45s GIL-held dump.
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
        if shard_plan is not None:
            report["failure_stage"] = "pg-image-identity"
            report["pg_image_id"] = owned_pg_image_id(compose, project, capture)
            report.pop("failure_stage")
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
            run_combined(
                records,
                report,
                tests,
                args.ci_scope,
                history_read_regression=args.history_read_regression,
                shard_plan=shard_plan,
                shard_id=args.shard_id,
            )
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
        failure_record: dict[str, object] = {
            "event": "diagnostic_failed",
            "code": type(error).__name__,
        }
        if "failure_stage" in report:
            failure_record["stage"] = report["failure_stage"]
        emit(failure_record)
    finally:
        cleanup_started = time.monotonic()
        cleanup_stage = "inspect-registered"
        owned_verified = owned_removed = 0

        def cleanup_note(stage: str, verified: int, removed: int) -> None:
            nonlocal cleanup_stage, owned_verified, owned_removed
            cleanup_stage, owned_verified, owned_removed = stage, verified, removed
            emit(
                {
                    "event": "cleanup_stage",
                    "stage": stage,
                    "elapsed_seconds": round(time.monotonic() - cleanup_started, 3),
                    "remaining_seconds": round(max(0, cleanup_until() - time.monotonic()), 3),
                    "owned_verified": verified,
                    "owned_removed": removed,
                }
            )

        try:
            cleanup_registered_containers(
                containers,
                project,
                lambda command, seconds: capture(command, seconds, cleanup=True),
                cleanup_note,
            )
            cleanup_note("compose-down", owned_verified, owned_removed)
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
                if shard_plan is not None:
                    inventory = {}
                    for resource, command in (
                        ("containers", ["docker", "ps", "-a", "-q"]),
                        ("networks", ["docker", "network", "ls", "-q"]),
                        ("volumes", ["docker", "volume", "ls", "-q"]),
                    ):
                        probe = capture(
                            command + ["--filter", "label=com.docker.compose.project=" + project],
                            10,
                            cleanup=True,
                        )
                        if probe.returncode != 0:
                            raise RuntimeError("owned resource inventory unconfirmed")
                        inventory[resource] = len(probe.stdout.split())
                    report["remaining_resources"] = inventory
                    if any(inventory.values()):
                        raise RuntimeError("owned resources remain after cleanup")
                cleanup_note("credential-files", owned_verified, owned_removed)
                for filename in ("owner_password", "app_password"):
                    (directory / filename).unlink()
                directory.rmdir()
                cleanup_note("complete", owned_verified, owned_removed)
        except Exception as error:
            report["cleanup_exit"] = "unconfirmed"
            report["cleanup_error_class"] = type(error).__name__
            emit(
                {
                    "event": "cleanup_failure",
                    "stage": cleanup_stage,
                    "exception_class": type(error).__name__,
                    "elapsed_seconds": round(time.monotonic() - cleanup_started, 3),
                    "remaining_seconds": round(max(0, cleanup_until() - time.monotonic()), 3),
                    "owned_verified": owned_verified,
                    "owned_removed": owned_removed,
                }
            )
        report["cleanup_stage"] = cleanup_stage
        report["cleanup_elapsed_seconds"] = round(time.monotonic() - cleanup_started, 3)
        report["cleanup_remaining_seconds"] = round(max(0, cleanup_until() - time.monotonic()), 3)
        report["cleanup_owned_verified"] = owned_verified
        report["cleanup_owned_removed"] = owned_removed
        report["finished_at"] = datetime.now(UTC).isoformat()
        save()
        if shard_plan is not None and shard_binding is not None and args.shard_id is not None:
            # Failed collection can emit no v2 artifact; upload/aggregate must fail closed.
            if report.get("full_node_ids"):
                evidence = safe_shard_report(report, shard_binding, shard_plan, args.shard_id)
                artifact = ROOT / ".audit" / f"ci-evidence-shard-{args.shard_id}.json"
                artifact.write_text(json.dumps(evidence, indent=2) + "\n")
            else:
                emit({"event": "shard_evidence_unavailable", "reason": "no_actual_collection"})
        elif ci_identity is not None:
            evidence = safe_report(report, ci_identity, args.ci_scope)
            artifact = ROOT / ".audit" / f"ci-evidence-{args.ci_scope}.json"
            artifact.write_text(json.dumps(evidence, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "project": project,
                    "result": report["result"],
                    "cleanup_exit": report["cleanup_exit"],
                    "cleanup_stage": report["cleanup_stage"],
                    "cleanup_error_class": report.get("cleanup_error_class"),
                    "cleanup_elapsed_seconds": report["cleanup_elapsed_seconds"],
                    "cleanup_remaining_seconds": report["cleanup_remaining_seconds"],
                    "cleanup_owned_verified": owned_verified,
                    "cleanup_owned_removed": owned_removed,
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
