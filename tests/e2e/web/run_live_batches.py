"""项目专用read/write/items真实Web入口；三固定隔离段，同一绝对截止/75s清理预留。"""

import argparse
import hashlib
import json
import math
import os
import re
import signal
import socket
import stat
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from commerceops.infrastructure.database import DatabaseSettings, connect

from scripts.prepare_pg import prepare
from tests.e2e.web.live_batch_owner import OWNERS, verify

READ_REPORTER = "read-live-results.json"
READ_TITLES = (
    "operator真实登录、22记录分页、报告刷新/20SKU/null与实际配置",
    "approver完整计划无默认确认、指定版本只读、缺缓存解释、events无虚构恢复",
    "admin-only安全落点，无业务导航/编号/计数与强制深链",
    "另一operator同店非本人404与不存在一致，URL actor/role无授权",
    "跨店兼任范围逐角色绑定，不拼operator-A/approver-B",
    "原request_key只读回执、缺CSRF拒绝、真实logout清Cookie",
    "当前scope撤销真实401，刷新后清业务缓存/身份且无Mock回退",
)
LIVE_SOURCE_FILES = (
    "tests/e2e/web/run_live_batches.py",
    "tests/e2e/web/live_batch_owner.py",
    "tests/e2e/web/live_batch_audit.py",
    "tests/e2e/web/live_item_seed.py",
    "tests/e2e/web/live_item_worker.py",
    "tests/e2e/web/live_item_revoke.py",
    "tests/e2e/web/live_write_probe.py",
    "tests/e2e/web/live/read.spec.ts",
    "tests/e2e/web/live/write.spec.ts",
    "tests/e2e/web/live/items.spec.ts",
    "frontend/tooling/live-reporter.ts",
    "frontend/tooling/live-zoom-proof.mjs",
    "frontend/playwright.live.config.ts",
)


class ReadReporterRejected(ValueError):
    """Only a fixed rejection message; never the report's raw content."""


def _unique_report_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ReadReporterRejected("invalid read reporter")
        result[key] = value
    return result


def _duration(value: object) -> bool:
    return (
        type(value) in (int, float)
        and isinstance(value, (int, float))
        and 0 <= value <= 9007199254740991
        and math.isfinite(value)
    )


def read_reporter(directory: Path) -> tuple[str, list[dict[str, str]]]:
    """Reject everything outside this exact seven-read reporter; return canonical fields only."""
    path = directory / READ_REPORTER
    try:
        info = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o777 != 0o600
            or info.st_size > 65536
        ):
            raise ReadReporterRejected("invalid read reporter")
        value = json.loads(path.read_text(), object_pairs_hook=_unique_report_fields)
    except FileNotFoundError as error:
        raise ReadReporterRejected("missing read reporter") from error
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        raise ReadReporterRejected("invalid read reporter") from error
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "status",
            "duration_ms",
            "trace",
            "video",
            "automatic_screenshot",
            "source_mode",
            "commerce_source_mode",
            "identity_mode",
            "tests",
        }
        or value["status"] not in ("passed", "failed", "timedout", "interrupted")
        or not _duration(value["duration_ms"])
        or any(value[key] != "off" for key in ("trace", "video", "automatic_screenshot"))
        or value["source_mode"] != "live-api"
        or value["commerce_source_mode"] != "mock-fixture"
        or value["identity_mode"] != "session"
        or not isinstance(value["tests"], list)
        or len(value["tests"]) > len(READ_TITLES)
    ):
        raise ReadReporterRejected("invalid read reporter")
    rows: dict[str, str] = {}
    for row in value["tests"]:
        if (
            not isinstance(row, dict)
            or set(row) != {"test", "status", "duration_ms", "location"}
            or row["test"] not in READ_TITLES
            or row["test"] in rows
            or row["status"] not in ("passed", "failed", "timedOut", "skipped", "interrupted")
            or not _duration(row["duration_ms"])
            or not isinstance(row["location"], str)
            or not re.fullmatch(r"e2e/web/live/read\.spec\.ts:[1-9][0-9]*", row["location"])
        ):
            raise ReadReporterRejected("invalid read reporter")
        rows[row["test"]] = row["status"]
    return value["status"], [
        {"test": title, "status": rows[title]} for title in READ_TITLES if title in rows
    ]


def _diagnostic_time(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (
        parsed.isoformat()
        if parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0)
        else None
    )


def read_failure_diagnostic(
    directory: Path, ledger: dict[str, object], *, reporter_current: bool
) -> dict[str, object]:
    """Read failure evidence only; unavailable counts stay unknown, never zero by default."""
    status: str | None = None
    tests: list[dict[str, str]] | None = None
    if reporter_current:
        try:
            status, tests = read_reporter(directory)
        except ReadReporterRejected:
            pass
    counts = (
        None
        if tests is None
        else {
            "actual": len(tests),
            "passed": sum(row["status"] == "passed" for row in tests),
            "failed": sum(row["status"] in ("failed", "timedOut", "interrupted") for row in tests),
            "skipped": sum(row["status"] == "skipped" for row in tests),
            "not_run": len(READ_TITLES) - len(tests),
        }
    )
    category = "unknown"
    if tests:
        statuses = {row["status"] for row in tests}
        if "timedOut" in statuses:
            category = "read_test_timed_out"
        elif "interrupted" in statuses:
            category = "read_test_interrupted"
        elif "failed" in statuses:
            category = "read_test_failed"
        elif "skipped" in statuses or len(tests) < len(READ_TITLES):
            category = "read_tests_incomplete"
    source = ledger.get("source_commit")
    if not isinstance(source, str) or not re.fullmatch(r"[a-f0-9]{40}", source):
        source = None
    hashes = ledger.get("source_files_sha256")
    if (
        not isinstance(hashes, dict)
        or set(hashes) != set(LIVE_SOURCE_FILES)
        or any(
            not isinstance(h, str) or not re.fullmatch(r"[a-f0-9]{64}", h) for h in hashes.values()
        )
    ):
        hashes = None
    return {
        "schema_version": "read-diagnostic-v1",
        "failure_category": category,
        "reporter_valid": tests is not None,
        "reporter_status": status,
        "expected_count": len(READ_TITLES),
        "counts": counts,
        "tests": tests,
        "source_commit": source,
        "source_files_sha256": hashes,
        "stop_at_utc": _diagnostic_time(ledger.get("stop_at_utc")),
        "stopped_at_utc": _diagnostic_time(ledger.get("stopped_at_utc")),
        "resources_stopped": ledger.get("pg_running") is False
        and type(ledger.get("pg_pid")) is int
        and ledger.get("pg_pid") == 0
        and ledger.get("owned_listeners_remaining") is False,
    }


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, default=str))
    path.chmod(0o600)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def listener_output(root: Path, port: int) -> str:
    # Reuse the same readonly Linux socket/PID proof as Web tests and native zoom.
    return subprocess.check_output(
        [
            str(root / ".tools/node/bin/node"),
            "--input-type=module",
            "-e",
            "import {readOwnedListener} from './tests/e2e/web/owned-listeners.ts';"
            "process.stdout.write(readOwnedListener(Number(process.argv[1])));",
            str(port),
        ],
        cwd=root,
        text=True,
        stderr=subprocess.DEVNULL,
        timeout=5,
    )


def main(
    root: Path,
    private: Path,
    deadline: datetime,
    stages: str = "read,write,items",
    owner: str = "b",
) -> None:
    if root != Path(__file__).resolve().parents[3] or owner not in OWNERS:
        raise ValueError("current exact checkout and closed test owner required")
    if not root.joinpath("frontend/.next/BUILD_ID").is_file():
        raise ValueError("exact production build required")
    if deadline.tzinfo is None or not datetime.now(UTC) + timedelta(
        seconds=75
    ) < deadline <= datetime.now(UTC) + timedelta(minutes=90):
        raise ValueError("bounded immutable deadline required")
    if private.exists():
        if (
            private.is_symlink()
            or any(private.iterdir())
            or private.stat().st_mode & 0o777 != 0o700
        ):
            raise ValueError("new empty private 0700 directory required")
    else:
        private.mkdir(mode=0o700, parents=True)
    outcomes = []
    selected = stages.split(",")
    if not selected or any(stage not in ("read", "write", "items") for stage in selected):
        raise ValueError("fixed project stages required")
    for stage, seeder in [
        ("read", "live_seed.py"),
        ("write", "live_write_seed.py"),
        ("items", "live_item_seed.py"),
    ]:
        if stage not in selected:
            continue
        project = "p3b04-" + stage + "-" + uuid4().hex[:10]
        directory = private / stage
        prepare(directory)
        pg_port, web_port, api_port = free_port(), free_port(), free_port()
        env = {
            **os.environ,
            "PYTHONPATH": str(root),
            "COMMERCEOPS_PG_RUNTIME_DIR": str(directory),
            "NEXT_TELEMETRY_DISABLED": "1",
            "LANGSMITH_TRACING": "false",
        }
        empty, override = directory / "compose-input.conf", directory / "compose-port.json"
        empty.write_text("")
        empty.chmod(0o600)
        save(override, {"services": {"postgres": {"ports": [f"127.0.0.1:{pg_port}:5432"]}}})
        compose = [
            "docker",
            "compose",
            "--env-file",
            str(empty),
            "-p",
            project,
            "-f",
            str(root / "compose.yml"),
            "-f",
            str(override),
        ]
        ledger = {
            "project": project,
            "owner": OWNERS[owner],
            "owner_uid": os.getuid(),
            "checkout": str(root),
            "private_directory": str(directory),
            "stage": stage,
            "started_at_utc": datetime.now(UTC).isoformat(),
            "stop_at_utc": deadline.isoformat(),
            "pg_port": pg_port,
            "web_origin": f"http://127.0.0.1:{web_port}",
            "api_origin": f"http://127.0.0.1:{api_port}",
            "build_id": root.joinpath("frontend/.next/BUILD_ID").read_text().strip(),
            "source_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip(),
            "status": "registered-before-start",
            "source_files_sha256": {
                path: hashlib.sha256((root / path).read_bytes()).hexdigest()
                for path in LIVE_SOURCE_FILES
            },
        }
        verify(directory, ledger, stage)
        children: list[subprocess.Popen[bytes]] = []

        def remaining() -> float:
            seconds = (deadline - datetime.now(UTC)).total_seconds() - 75
            if seconds <= 0:
                raise TimeoutError("common deadline reached; cleanup reserved")
            return seconds

        def run(
            command: list[str],
            limit: int,
            command_env: dict[str, str] = env,
            owned_children: list[subprocess.Popen[bytes]] = children,
        ) -> None:
            command_process = subprocess.Popen(
                command,
                cwd=root,
                env=command_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            owned_children.append(command_process)
            command_process.wait(timeout=min(limit, remaining()))
            if command_process.returncode:
                raise RuntimeError("owned stage command failed")

        save(directory / "window.json", ledger)
        print(
            json.dumps(
                {
                    "event": "registered",
                    "stage": stage,
                    "project": project,
                    "deadline": deadline.isoformat(),
                }
            ),
            flush=True,
        )
        passed = False
        read_reporter_current = False
        try:
            run(compose + ["up", "-d", "postgres"], 60)
            for _ in range(60):
                result = subprocess.run(
                    compose
                    + [
                        "exec",
                        "-T",
                        "postgres",
                        "pg_isready",
                        "-U",
                        "commerceops_owner",
                        "-d",
                        "commerceops",
                    ],
                    cwd=root,
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=min(5, remaining()),
                )
                if result.returncode == 0:
                    break
                time.sleep(1)
            else:
                raise RuntimeError("owned PG readiness failed")
            env.update(
                COMMERCEOPS_DB_HOST="127.0.0.1",
                COMMERCEOPS_DB_PORT=str(pg_port),
                COMMERCEOPS_DB_NAME="commerceops",
                COMMERCEOPS_DB_USER="commerceops_owner",
                COMMERCEOPS_DB_PASSWORD_FILE=str(directory / "owner_password"),
                COMMERCEOPS_DB_RUNTIME_PASSWORD_FILE=str(directory / "app_password"),
            )
            # A separate OS seed process is completed/reaped before any continuous Worker.
            seed = subprocess.Popen(
                [sys.executable, str(root / "tests/e2e/web" / seeder), str(directory)],
                cwd=root,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            children.append(seed)
            ledger.update(seed_pid=seed.pid, status="seeding")
            save(directory / "window.json", ledger)
            seed.wait(timeout=min(300, remaining()))
            ledger["seed_exit"] = seed.returncode
            if seed.returncode:
                raise RuntimeError("owned seed failed")
            settings = DatabaseSettings.model_validate_json(
                (directory / "owner-settings.json").read_text()
            )
            with connect(settings) as db:
                organization = db.execute(
                    "SELECT organization_id FROM business.principals WHERE id=%s",
                    (
                        json.loads((directory / "web-accounts.json").read_text())["operator"][
                            "principal"
                        ],
                    ),
                ).fetchone()
            assert organization
            worker_env = {
                **env,
                "COMMERCEOPS_P3_CONFIG_FILE": str(directory / "configuration.json"),
                "COMMERCEOPS_MODE": "test",
            }
            worker_command = (
                [sys.executable, str(root / "tests/e2e/web/live_item_worker.py"), str(directory)]
                if stage == "items"
                else [
                    sys.executable,
                    "-m",
                    "commerceops.entrypoints.worker",
                    "inventory-test-run",
                    "--organization",
                    str(organization["organization_id"]),
                    "--fixture-directory",
                    str(root / "tests/fixtures/commerce/inventory-v1"),
                ]
            )
            worker = subprocess.Popen(
                worker_command,
                cwd=root,
                env=worker_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            children.append(worker)
            api = subprocess.Popen(
                [sys.executable, "-m", "commerceops.entrypoints.api"],
                cwd=root,
                env={
                    **worker_env,
                    "COMMERCEOPS_HOST": "127.0.0.1",
                    "COMMERCEOPS_PORT": str(api_port),
                    "COMMERCEOPS_LOG_LEVEL": "error",
                },
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            children.append(api)
            web = subprocess.Popen(
                [
                    str(root / ".tools/node/bin/node"),
                    str(root / "frontend/node_modules/next/dist/bin/next"),
                    "start",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    str(web_port),
                ],
                cwd=root / "frontend",
                env={
                    **env,
                    "COMMERCEOPS_UI_MODE": "live",
                    "COMMERCEOPS_API_ORIGIN": str(ledger["api_origin"]),
                    "COMMERCEOPS_WEB_TRANSPORT": "local_http",
                },
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            children.append(web)
            ledger.update(worker_pid=worker.pid, api_pid=api.pid, web_pid=web.pid)
            save(directory / "window.json", ledger)
            for _ in range(60):
                remaining()
                if any(child.poll() is not None for child in (worker, api, web)):
                    raise RuntimeError("owned process exited")
                try:
                    a = listener_output(root, api_port).split()
                    w = listener_output(root, web_port).split()
                    if set(a) == {str(api.pid)} and set(w) == {str(web.pid)}:
                        break
                except subprocess.CalledProcessError:
                    pass
                time.sleep(1)
            else:
                raise RuntimeError("owned listener failed")
            ledger["status"] = "running"
            save(directory / "window.json", ledger)
            if stage == "items":
                facts = json.loads((directory / "b04-facts.json").read_text())
                for _ in range(90):
                    remaining()
                    with connect(settings) as db:
                        items = db.execute(
                            "SELECT id,quantity FROM business.replenishment_items "
                            "WHERE task_id=%s ORDER BY id",
                            (facts["completed_task"],),
                        ).fetchall()
                        task = db.execute(
                            "SELECT state FROM business.business_tasks WHERE id=%s",
                            (facts["completed_task"],),
                        ).fetchone()
                        job = db.execute(
                            "SELECT status FROM business.jobs WHERE id=%s", (facts["template_job"],)
                        ).fetchone()
                    if (
                        task
                        and task["state"] == "completed"
                        and len(items) == 20
                        and job
                        and job["status"] == "done"
                    ):
                        break
                    time.sleep(1)
                else:
                    raise RuntimeError("owned 20 T4/template not ready")
                facts.update(
                    resolve_item=str(items[0]["id"]),
                    hidden_source_item=str(items[1]["id"]),
                    operator_item=str(items[2]["id"]),
                    unknown_item=str(items[3]["id"]),
                    concurrent_item=str(items[4]["id"]),
                    revoke_item=str(items[5]["id"]),
                    item_ids=[str(row["id"]) for row in items],
                    total_units=sum(int(row["quantity"]) for row in items),
                )
                save(directory / "b04-facts.json", facts)
            batch = {"read": "b04-read", "write": "b04-write", "items": "b04"}[stage]
            live_env = {
                **env,
                "PATH": str(root / ".tools/node/bin") + os.pathsep + os.environ["PATH"],
                "COMMERCEOPS_WEB_BATCH": batch,
                "COMMERCEOPS_B02_PRIVATE_DIR": str(directory),
                "COMMERCEOPS_LIVE_WEB_URL": str(ledger["web_origin"]),
            }
            if stage == "read" and (
                (directory / READ_REPORTER).exists() or (directory / READ_REPORTER).is_symlink()
            ):
                raise RuntimeError("owned read reporter already present")
            test_process = subprocess.Popen(
                [str(root / ".tools/node/bin/npm"), "run", "test:live"],
                cwd=root / "frontend",
                env=live_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            children.append(test_process)
            read_reporter_current = stage == "read"
            ledger["test_pid"] = test_process.pid
            save(directory / "window.json", ledger)
            test_process.wait(timeout=remaining())
            ledger["test_exit"] = test_process.returncode
            if stage == "items" and test_process.returncode == 0:
                run(
                    [
                        str(root / ".tools/node/bin/node"),
                        str(root / "frontend/tooling/live-zoom-proof.mjs"),
                    ],
                    90,
                    live_env,
                )
                ledger["native_zoom"] = "passed"
            audit = subprocess.run(
                [
                    sys.executable,
                    str(root / "tests/e2e/web/live_batch_audit.py"),
                    str(directory),
                    stage,
                ],
                cwd=root,
                env=env,
                capture_output=True,
                timeout=min(30, remaining()),
            )
            if audit.returncode:
                raise RuntimeError("owned invariant audit failed")
            invariants = json.loads(audit.stdout)
            ledger["invariants"] = invariants
            with connect(settings) as db:
                calls = db.execute("SELECT count(*) AS n FROM business.model_calls").fetchone()
                actual = db.execute(
                    "SELECT count(*) AS n FROM business.model_calls "
                    "WHERE evidence_mode='actual_provider'"
                ).fetchone()
            ledger.update(
                model_calls=calls["n"] if calls else None,
                actual_provider_calls=actual["n"] if actual else None,
                test_exit=test_process.returncode,
            )
            passed = test_process.returncode == 0 and actual == {"n": 0} and invariants["passed"]
        except Exception as error:
            ledger["failure_category"] = type(error).__name__
        finally:
            ledger["status"] = "stopping"
            save(directory / "window.json", ledger)
            # Every owned child has its own new process group; never touch foreign PIDs.
            cleanup_stop = time.monotonic() + 15
            for child in children:
                if child.poll() is None:
                    try:
                        os.killpg(child.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
            for child in reversed(children):
                if child.poll() is None:
                    try:
                        child.wait(timeout=max(0.1, cleanup_stop - time.monotonic()))
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(child.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        child.wait(timeout=5)
            subprocess.run(
                compose + ["stop", "postgres"],
                cwd=root,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=45,
                check=True,
            )
            cid = subprocess.check_output(
                compose + ["ps", "-aq", "postgres"], cwd=root, env=env, text=True
            ).strip()
            state = json.loads(
                subprocess.check_output(
                    ["docker", "inspect", "--format", "{{json .State}}", cid], text=True
                )
            )
            owned_listeners_remaining = False
            for port, pid in ((api_port, ledger.get("api_pid")), (web_port, ledger.get("web_pid"))):
                try:
                    observed = listener_output(root, port).split()
                except subprocess.CalledProcessError:
                    observed = []
                owned_listeners_remaining |= str(pid) in observed
            passed &= not state["Running"] and state["Pid"] == 0 and not owned_listeners_remaining
            ledger.update(
                status="stopped",
                stopped_at_utc=datetime.now(UTC).isoformat(),
                pg_running=state["Running"],
                pg_pid=state["Pid"],
                child_exit_codes=[child.returncode for child in children],
                volume_preserved=True,
                owned_listeners_remaining=owned_listeners_remaining,
            )
            if stage == "read" and not passed:
                diagnostic = read_failure_diagnostic(
                    directory, ledger, reporter_current=read_reporter_current
                )
                ledger["failure_category"] = diagnostic["failure_category"]
            save(directory / "window.json", ledger)
            outcomes.append(
                {
                    "stage": stage,
                    "passed": passed,
                    "project": project,
                    "actual_provider_calls": ledger.get("actual_provider_calls"),
                    "test_exit": ledger.get("test_exit"),
                    "pg_running": state["Running"],
                    "pg_pid": state["Pid"],
                    "failure_category": ledger.get("failure_category"),
                    "invariants_passed": bool(ledger.get("invariants") and invariants["passed"]),
                    "native_zoom": ledger.get("native_zoom"),
                    **({"read_diagnostic": diagnostic} if stage == "read" and not passed else {}),
                }
            )
            save(private / "result.json", {"stop_at_utc": deadline.isoformat(), "stages": outcomes})
            print(json.dumps(outcomes[-1]), flush=True)
        if not passed:
            raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--private-directory", type=Path, required=True)
    parser.add_argument("--stop-at-utc", required=True)
    parser.add_argument("--stages", default="read,write,items")
    parser.add_argument("--owner", choices=tuple(OWNERS), default="b")
    args = parser.parse_args()
    main(
        args.checkout.resolve(),
        args.private_directory.resolve(),
        datetime.fromisoformat(args.stop_at_utc.replace("Z", "+00:00")),
        args.stages,
        args.owner,
    )
