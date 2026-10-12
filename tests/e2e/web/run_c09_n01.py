"""一个新自有 C09 PG/API/Web 段，固定 <=30 分钟截止并保留停止后的卷。"""

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from scripts.prepare_pg import prepare
from tests.e2e.web.run_live_batches import free_port, listener_output, save

ROOT = Path(__file__).resolve().parents[3]
MUTABLE_N01_OUTPUTS = frozenset(
    {
        "frontend/evidence/p4-c09/n01/live-results.json",
        "frontend/evidence/p4-c09/n01/pg-invariants.safe.json",
        "frontend/evidence/p4-c09/n01/resource-stop.safe.json",
        "frontend/evidence/p4-c09/n01/failure-diagnostic.safe.json",
    }
)
REQUIRED_SOURCE_FILES = (
    "frontend/components/inventory-request-text.tsx",
    "frontend/lib/p4-n01.ts",
    "frontend/lib/p4-n01-schema.generated.json",
    "tests/e2e/web/c09_fixture.py",
    "tests/e2e/web/run_c09_n01.py",
    "tests/e2e/web/live/n01.spec.ts",
)


def source_manifest() -> dict[str, str]:
    """仅排除三个本段派生输出；其他tracked/关键源缺失仍失败。"""
    tracked = subprocess.check_output(
        ["git", "ls-files", "frontend", "tests/e2e/web"], cwd=ROOT, text=True
    ).splitlines()
    sources = (set(tracked) | set(REQUIRED_SOURCE_FILES)) - MUTABLE_N01_OUTPUTS
    return {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sorted(sources)
    }


def clear_n01_failure_sample() -> None:
    """本段开始前只清固定N01失败sample；无宽泛路径清理。"""
    (ROOT / "frontend/evidence/p4-c09/n01/failure-diagnostic.safe.json").unlink(missing_ok=True)


def main(private: Path, deadline: datetime) -> None:
    now = datetime.now(UTC)
    if deadline.tzinfo is None or not now + timedelta(seconds=75) < deadline <= now + timedelta(
        minutes=30
    ):
        raise ValueError("fixed C09 deadline required")
    if private.exists():
        raise ValueError("new private directory required")
    clear_n01_failure_sample()
    prepare(private)
    ports: set[int] = set()
    while len(ports) < 3:
        ports.add(free_port())
    pg_port, api_port, web_port = sorted(ports)
    project = "p4c09-n01-" + uuid4().hex[:10]
    env = {
        **os.environ,
        "PATH": str(ROOT / ".tools/node/bin") + ":" + os.environ["PATH"],
        "PYTHONPATH": str(ROOT / "backend/src") + ":" + str(ROOT),
        "COMMERCEOPS_PG_RUNTIME_DIR": str(private),
        "COMMERCEOPS_DB_HOST": "127.0.0.1",
        "COMMERCEOPS_DB_PORT": str(pg_port),
        "COMMERCEOPS_DB_NAME": "commerceops",
        "COMMERCEOPS_DB_USER": "commerceops_owner",
        "COMMERCEOPS_DB_PASSWORD_FILE": str(private / "owner_password"),
        "COMMERCEOPS_DB_RUNTIME_PASSWORD_FILE": str(private / "app_password"),
        "COMMERCEOPS_P3_CONFIG_FILE": str(private / "configuration.json"),
        "LANGSMITH_TRACING": "false",
        "NEXT_TELEMETRY_DISABLED": "1",
        "COMMERCEOPS_MODE": "test",
    }
    empty = private / "compose-input.conf"
    empty.write_text("")
    empty.chmod(0o600)
    override = private / "compose-port.json"
    save(override, {"services": {"postgres": {"ports": [f"127.0.0.1:{pg_port}:5432"]}}})
    compose = [
        "docker",
        "compose",
        "--env-file",
        str(empty),
        "-p",
        project,
        "-f",
        str(ROOT / "compose.yml"),
        "-f",
        str(override),
    ]
    manifest = source_manifest()
    save(private / "source-files.safe.json", manifest)
    window = {
        "owner": "phase4-C09-Web",
        "owner_uid": os.getuid(),
        "checkout": str(ROOT),
        "private_directory": str(private),
        "project": project,
        "started_at_utc": now.isoformat(),
        "stop_at_utc": deadline.isoformat(),
        "pg_port": pg_port,
        "api_origin": f"http://127.0.0.1:{api_port}",
        "web_origin": f"http://127.0.0.1:{web_port}",
        "build_id": (ROOT / "frontend/.next/BUILD_ID").read_text().strip(),
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_manifest_sha256": hashlib.sha256(
            (private / "source-files.safe.json").read_bytes()
        ).hexdigest(),
        "status": "registered-before-start",
        "worker_started": False,
        "sdk_provider_started": False,
        "max_new_cycle_requests": 1,
    }
    save(private / "window.json", window)
    print(
        json.dumps({"event": "registered", "project": project, "deadline": deadline.isoformat()}),
        flush=True,
    )
    children: list[subprocess.Popen[bytes]] = []

    def remaining() -> float:
        value = (deadline - datetime.now(UTC)).total_seconds() - 75
        if value <= 0:
            raise TimeoutError("C09 cleanup reserve reached")
        return value

    def spawn(
        command: list[str], process_env: dict[str, str], cwd: Path = ROOT
    ) -> subprocess.Popen[bytes]:
        child = subprocess.Popen(
            command,
            cwd=cwd,
            env=process_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        children.append(child)
        return child

    def run(command: list[str], limit: int) -> None:
        if command[0] == "docker":
            child = subprocess.Popen(
                command,
                cwd=ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            children.append(child)
            stdout, stderr = child.communicate(timeout=min(limit, remaining()))
            log = private / "compose-start.private.log"
            log.write_bytes(stdout + stderr)
            log.chmod(0o600)
        else:
            child = spawn(command, env)
            child.wait(timeout=min(limit, remaining()))
        if child.returncode:
            raise RuntimeError("C09 owned command failed")

    passed = False
    try:
        window["stage"] = "compose_start"
        save(private / "window.json", window)
        run(compose + ["up", "-d", "postgres"], 60)
        for _ in range(60):
            ready = subprocess.run(
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
                cwd=ROOT,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=min(5, remaining()),
            )
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("C09 PG readiness failed")
        window["stage"] = "seed"
        save(private / "window.json", window)
        run([sys.executable, str(ROOT / "tests/e2e/web/c09_fixture.py"), str(private), "seed"], 180)
        api = spawn(
            [sys.executable, str(ROOT / "tests/e2e/web/c09_fixture.py"), str(private), "api"],
            {
                **env,
                "COMMERCEOPS_HOST": "127.0.0.1",
                "COMMERCEOPS_PORT": str(api_port),
                "COMMERCEOPS_LOG_LEVEL": "error",
            },
        )
        web = spawn(
            [
                str(ROOT / ".tools/node/bin/node"),
                str(ROOT / "frontend/node_modules/next/dist/bin/next"),
                "start",
                "--hostname",
                "127.0.0.1",
                "--port",
                str(web_port),
            ],
            {
                **env,
                "COMMERCEOPS_UI_MODE": "live",
                "COMMERCEOPS_API_ORIGIN": str(window["api_origin"]),
                "COMMERCEOPS_WEB_TRANSPORT": "local_http",
            },
            ROOT / "frontend",
        )
        window.update(api_pid=api.pid, web_pid=web.pid)
        save(private / "window.json", window)
        for _ in range(60):
            remaining()
            if api.poll() is not None or web.poll() is not None:
                raise RuntimeError("C09 process exited")
            try:
                if set(listener_output(ROOT, api_port).split()) == {str(api.pid)} and set(
                    listener_output(ROOT, web_port).split()
                ) == {str(web.pid)}:
                    break
            except subprocess.CalledProcessError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("C09 listener ownership failed")
        window["status"] = "running"
        save(private / "window.json", window)
        tester = spawn(
            [
                str(ROOT / ".tools/node/bin/node"),
                str(ROOT / "frontend/node_modules/@playwright/test/cli.js"),
                "test",
                "--config",
                "playwright.live.config.ts",
            ],
            {
                **env,
                "COMMERCEOPS_WEB_BATCH": "p4-c09-n01",
                "COMMERCEOPS_B02_PRIVATE_DIR": str(private),
                "COMMERCEOPS_LIVE_WEB_URL": str(window["web_origin"]),
            },
            ROOT / "frontend",
        )
        tester.wait(timeout=remaining())
        window["test_exit"] = tester.returncode
        report = json.loads((ROOT / "frontend/evidence/p4-c09/n01/live-results.json").read_text())
        passed = (
            tester.returncode == 0 and report["status"] == "passed" and len(report["tests"]) == 6
        )
    except Exception as error:
        window["failure_category"] = type(error).__name__
        save(private / "window.json", window)
    finally:
        for child in reversed(children):
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=5)
        subprocess.run(
            compose + ["stop", "-t", "5"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=True,
        )
        container = subprocess.check_output(
            compose + ["ps", "-a", "-q", "postgres"], cwd=ROOT, env=env, text=True
        ).strip()
        state = (
            json.loads(subprocess.check_output(["docker", "inspect", container], text=True))[0][
                "State"
            ]
            if container
            else {"Running": False, "Pid": 0}
        )
        window["pg_container_created"] = bool(container)
        listeners = False
        for port in (api_port, web_port, pg_port):
            if sys.platform == "darwin":
                check = subprocess.run(
                    ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
                    capture_output=True,
                    timeout=5,
                )
                listeners |= check.returncode != 1 or bool(check.stdout)
            else:
                try:
                    listeners |= bool(listener_output(ROOT, port).strip())
                except subprocess.CalledProcessError:
                    pass
        passed &= not state["Running"] and state["Pid"] == 0 and not listeners
        window.update(
            status="stopped",
            passed=passed,
            stopped_at_utc=datetime.now(UTC).isoformat(),
            pg_running=state["Running"],
            pg_pid=state["Pid"],
            owned_listeners_remaining=listeners,
            volume_preserved=True,
            child_exit_codes=[child.returncode for child in children],
        )
        save(private / "window.json", window)
        summary = {
            key: window.get(key)
            for key in (
                "passed",
                "source_commit",
                "build_id",
                "test_exit",
                "failure_category",
                "pg_running",
                "pg_pid",
                "owned_listeners_remaining",
                "volume_preserved",
                "worker_started",
                "sdk_provider_started",
                "started_at_utc",
                "stop_at_utc",
                "stopped_at_utc",
            )
        }
        output = ROOT / "frontend/evidence/p4-c09/n01"
        output.mkdir(parents=True, exist_ok=True)
        save(output / "resource-stop.safe.json", summary)
        print(json.dumps(summary), flush=True)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-directory", type=Path, required=True)
    parser.add_argument("--stop-at-utc", required=True)
    args = parser.parse_args()
    main(
        args.private_directory.resolve(),
        datetime.fromisoformat(args.stop_at_utc.replace("Z", "+00:00")),
    )
