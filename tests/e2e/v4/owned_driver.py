"""One explicit new-owned V4 case, not a reusable deployment manager.

prepare only creates new private files; execute requires Root's exact source,
images, ports, UTC manifest and an explicit window flag. Never discovers secrets.
"""

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

from .http_probe import run_scenario
from .owned_adapter import OwnedAdapter, compose_environment
from .owned_negatives import run_owned_negative
from .preflight import ROOT, git, utc
from .supervisor import Budget, OwnedProcess, Supervisor

SCENARIOS = {
    "lifecycle",
    "capacity",
    "ack_body",
    "ack_headers",
    "security",
    "same_key_reset",
    "persona_stale",
    "bootstrap_restart",
    "identity_scopes",
    "credential_revoke",
    "grant_revoke",
}


@dataclass(frozen=True)
class Case:
    project: str
    database: str
    directory: str
    source_sha: str
    source_tree: str
    pg_image: str
    test_image: str
    api_port: int
    web_port: int
    starts_at: str
    deadline: str
    scenario: str
    migration_sha256: str
    uid: int

    def validate(self) -> None:
        if not re.fullmatch(r"v4qa_[a-z0-9_]{8,32}", self.project):
            raise ValueError("new QA project required")
        if not re.fullmatch(r"v4_demo_[a-z0-9_]{1,48}", self.database):
            raise ValueError("new V4 database required")
        for value in (self.source_sha, self.source_tree):
            if not re.fullmatch(r"[a-f0-9]{40}", value):
                raise ValueError("exact source required")
        for image in (self.pg_image, self.test_image):
            if not re.fullmatch(r"sha256:[a-f0-9]{64}", image):
                raise ValueError("Root-bound local image ID required; no pulls")
        if not re.fullmatch(r"[a-f0-9]{64}", self.migration_sha256):
            raise ValueError("public migration fingerprint required")
        migration = ROOT / "backend/migrations/versions/0024_v4_demo_foundation.py"
        if hashlib.sha256(migration.read_bytes()).hexdigest() != self.migration_sha256:
            raise ValueError("actual committed migration bytes differ")
        ports = (self.api_port, self.web_port)
        if any(type(p) is not int or not 1024 <= p <= 65535 for p in ports) or ports[0] == ports[1]:
            raise ValueError("distinct explicit loopback ports required")
        start, end = utc(self.starts_at), utc(self.deadline)
        if not 180 < (end - start).total_seconds() <= 1800:
            raise ValueError("case window must include 180s cleanup, max 1800s")
        if self.scenario not in SCENARIOS or type(self.uid) is not int or self.uid != os.getuid():
            raise ValueError("explicit scenario and current owner UID required")
        path = Path(self.directory)
        if not path.is_absolute() or path.resolve() != path or not path.parent.is_dir():
            raise ValueError("canonical new directory with existing parent required")
        if (self.source_sha, self.source_tree) != (
            git("rev-parse", "HEAD"),
            git("rev-parse", "HEAD^{tree}"),
        ):
            raise ValueError("Root source/tree does not equal this worktree")
        if git("status", "--porcelain"):
            raise ValueError("committed clean source required")

    @property
    def api(self) -> str:
        return f"http://127.0.0.1:{self.api_port}"

    @property
    def web(self) -> str:
        return f"http://127.0.0.1:{self.web_port}"


def private(path: Path, value: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def prepare(case: Case) -> None:
    case.validate()
    directory = Path(case.directory)
    directory.mkdir(mode=0o700, exist_ok=False)
    owner, api = directory / "owner", directory / "api"
    owner.mkdir(mode=0o700)
    api.mkdir(mode=0o700)
    for name in ("owner_password", "app_password"):
        private(owner / name, secrets.token_urlsafe(48))
    private(api / "runtime-password", (owner / "app_password").read_text())
    private(api / "csrf-key", secrets.token_urlsafe(48))
    private(api / "nonce-key", secrets.token_urlsafe(48))
    web = {
        "database": {
            "host": "postgres",
            "port": 5432,
            "name": case.database,
            "user": "commerceops_app",
            "password_file": "/run/v4_api/runtime-password",
            "runtime_password_file": None,
        },
        "csrf_secret_file": "/run/v4_api/csrf-key",
        "nonce_secret_file": "/run/v4_api/nonce-key",
        "origins": [case.web, case.api],
        "transport_mode": "local_http",
    }
    private(api / "web.json", json.dumps(web))
    private(
        api / "demo.json",
        json.dumps(
            dict(
                schema_version="v4-demo-deployment-v1",
                web_config_file="/run/v4_api/web.json",
                api_origin=case.api,
                enabled=True,
                allow_non_browser_get=False,
            )
        ),
    )
    env = dict(
        COMMERCEOPS_PG_RUNTIME_DIR=str(owner),
        V4_OWNER_DIR=str(owner),
        V4_API_DIR=str(api),
        V4_DATABASE=case.database,
        V4_API_PORT=str(case.api_port),
        V4_UID=str(case.uid),
        V4_PG_IMAGE=case.pg_image,
        V4_TEST_IMAGE=case.test_image,
    )
    # Reject env-file metacharacters in owner-provided paths, never shell interpolate.
    if any(re.search(r"[\s#$'\"\\]", value) for value in env.values()):
        raise ValueError("compose env paths contain unsupported characters; preserve partial prep")
    private(directory / "compose.env", "".join(f"{k}={v}\n" for k, v in env.items()))
    private(directory / "case.json", json.dumps(asdict(case)))


def compose(case: Case) -> tuple[str, ...]:
    docker = shutil.which("docker", path=compose_environment()["PATH"])
    if not docker:
        raise ValueError("Root local Docker tool unavailable")
    return (
        docker,
        "compose",
        "--project-name",
        case.project,
        "--env-file",
        str(Path(case.directory) / "compose.env"),
        "-f",
        str(ROOT / "compose.yml"),
        "-f",
        str(ROOT / "compose.m3.yml"),
        "-f",
        str(Path(__file__).with_name("owned.compose.yml")),
    )


def checked(
    command: list[str],
    budget: Budget,
    records: list[dict[str, Any]],
    stage: str,
    *,
    cap: float = 90,
    cleanup: bool = False,
    evidence: Path | None = None,
) -> bytes:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=compose_environment(),
            capture_output=True,
            timeout=budget.timeout(cap, cleanup=cleanup),
            check=False,
        )
    except subprocess.TimeoutExpired:
        records.append(dict(stage=stage, native_exit=None, result="TIMEOUT_UNKNOWN"))
        raise
    records.append(dict(stage=stage, native_exit=result.returncode))
    if evidence is not None:
        try:
            payload = json.loads(result.stdout)
        except (ValueError, UnicodeError):
            payload = {"status": "DIAGNOSTIC_OUTPUT_INVALID", "native_exit": result.returncode}
        private(evidence, json.dumps(payload))
    if result.returncode:
        raise RuntimeError("owned command failed; no retry")
    return result.stdout


def ready(url: str, budget: Budget, owned: OwnedProcess) -> None:
    until = time.monotonic() + budget.timeout(90)
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=2) as client:
        while time.monotonic() < until:
            if owned.process.poll() is not None:
                raise RuntimeError("owned service exited; do not probe an unrelated listener")
            try:
                if client.get(url, timeout=budget.timeout(2)).status_code == 200:
                    if owned.process.poll() is not None:
                        raise RuntimeError("owned service exited during readiness")
                    return
            except httpx.TransportError:
                pass
            time.sleep(min(0.2, budget.timeout(0.2)))
    raise TimeoutError("read-only startup readiness failed")


def execute(case: Case) -> dict[str, Any]:
    case.validate()
    budget = Budget.bind(utc(case.starts_at), utc(case.deadline))
    directory = Path(case.directory)
    private(directory / "execution.once", "Root-opened case; never reuse\n")
    command = compose(case)
    records: list[dict[str, Any]] = []
    docker = command[0]
    # Initial emptiness is essential: subsequent cleanup is restricted to this
    # exact project. Refuse any previous labelled object, even a stopped one.
    for kind, args in (
        ("container", ["ps", "-aq"]),
        ("network", ["network", "ls", "-q"]),
        ("volume", ["volume", "ls", "-q"]),
    ):
        old = checked(
            [docker, *args, "--filter", f"label=com.docker.compose.project={case.project}"],
            budget,
            records,
            "empty_" + kind,
            cap=5,
        )
        if old.strip():
            raise ValueError("project not empty; no cleanup of preexisting resources")
    supervisor = Supervisor(budget, ROOT, directory / "processes")
    status = "FAILED"
    cleanup_ok = False
    try:
        sockets: list[socket.socket] = []
        try:
            for port in (case.api_port, case.web_port):
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sockets.append(sock)
                sock.bind(("127.0.0.1", port))
        finally:
            for sock in sockets:
                sock.close()
        checked(
            [
                *command,
                "up",
                "-d",
                "--wait",
                "--wait-timeout",
                "60",
                "--no-build",
                "--pull",
                "never",
                "postgres",
            ],
            budget,
            records,
            "pg_start",
        )
        owner = [*command, "run", "--rm", "--no-deps", "pg-test", "python", "-m"]
        checked(
            [
                *owner,
                "tests.e2e.v4.migration_diagnostic",
                "--public-migration-sha256",
                case.migration_sha256,
            ],
            budget,
            records,
            "migrate",
            cap=180,
            evidence=directory / "migration.safe.json",
        )
        for action in ("setup-checkpointer", "grant-runtime"):
            checked([*owner, "commerceops.entrypoints.database", action], budget, records, action)
        for action in ("init-fixture", "grant-runtime", "verify-fixture"):
            extra = ["--directory", "/run/v4_owner/export"] if action == "init-fixture" else []
            checked(
                [*owner, "scripts.v4_demo_seed", action, *extra], budget, records, "v4_" + action
            )
        adapter = OwnedAdapter(command, case.project, budget)
        argv, environment = adapter.launch_spec("api")
        api_process = supervisor.start("api", argv, environment)
        ready(case.api + "/health/live", budget, api_process)
        node = ROOT / ".tools/node/bin/node"
        web_process = supervisor.start(
            "web",
            (
                str(node),
                str(ROOT / "frontend/node_modules/next/dist/bin/next"),
                "dev",
                str(ROOT / "frontend"),
                "--hostname",
                "127.0.0.1",
                "--port",
                str(case.web_port),
            ),
            {
                "PATH": str(node.parent) + ":/usr/bin:/bin",
                "COMMERCEOPS_API_ORIGIN": case.api,
                "NEXT_TELEMETRY_DISABLED": "1",
            },
        )
        ready(case.web + "/v4", budget, web_process)
        child = supervisor.start(
            "probe",
            (
                sys.executable,
                "-m",
                "tests.e2e.v4.owned_driver",
                "probe",
                "--case",
                str(directory / "case.json"),
            ),
            compose_environment(),
        )
        code = supervisor.wait(child, budget.remaining())
        records.append(dict(stage="scenario", native_exit=code))
        if code != 0 or supervisor.watchdog_errors:
            raise RuntimeError("scenario failed or watchdog used; preserve evidence")
        budget.timeout(1)
        status = "SCENARIO_COMPLETED_PENDING_REVIEW"
    except BaseException:
        status = "FAILED_OR_UNKNOWN"
    finally:
        try:
            stopped = supervisor.stop_writers()
            records.append(dict(stage="writers_stopped", native_exits=stopped))
            checked(
                [*command, "stop", "--timeout", "5", "v4-api"],
                budget,
                records,
                "api_container_stopped",
                cleanup=True,
                cap=15,
            )
            # Killing a compose/run CLI does not prove its container stopped.
            # Stop this project's previously registered owner one-offs before
            # final collection, including a timed-out fixture mutation.
            oneoffs = (
                checked(
                    [
                        docker,
                        "ps",
                        "-q",
                        "--filter",
                        f"label=com.docker.compose.project={case.project}",
                        "--filter",
                        "label=com.docker.compose.service=pg-test",
                    ],
                    budget,
                    records,
                    "owner_oneoffs_inventory",
                    cleanup=True,
                    cap=5,
                )
                .decode()
                .split()
            )
            if oneoffs:
                if any(not re.fullmatch(r"[a-f0-9]{12,64}", cid) for cid in oneoffs):
                    raise ValueError("invalid owned container ID")
                checked(
                    [docker, "stop", "--time", "5", *oneoffs],
                    budget,
                    records,
                    "owner_oneoffs_stopped",
                    cleanup=True,
                    cap=20,
                )
            adapter = OwnedAdapter(command, case.project, budget)
            snapshots = [
                asdict(adapter.snapshot(tenant, final_collection=True))
                for tenant in adapter.tenant_ids(final=True)
            ]
            private(directory / "final_pg.safe.json", json.dumps(snapshots))
            records.append(dict(stage="final_pg_read_only", tenants=len(snapshots)))
        except BaseException:
            status = "WRITER_OR_FINAL_COLLECTION_FAILED"
        try:
            checked(
                [*command, "down", "--remove-orphans", "--timeout", "5"],
                budget,
                records,
                "owned_down_keep_volume",
                cleanup=True,
                cap=60,
            )
            remaining = checked(
                [
                    docker,
                    "ps",
                    "-aq",
                    "--filter",
                    f"label=com.docker.compose.project={case.project}",
                ],
                budget,
                records,
                "containers_gone",
                cleanup=True,
                cap=5,
            )
            networks = checked(
                [
                    docker,
                    "network",
                    "ls",
                    "-q",
                    "--filter",
                    f"label=com.docker.compose.project={case.project}",
                ],
                budget,
                records,
                "networks_gone",
                cleanup=True,
                cap=5,
            )
            cleanup_ok = not remaining.strip() and not networks.strip()
            volumes = (
                checked(
                    [
                        docker,
                        "volume",
                        "ls",
                        "-q",
                        "--filter",
                        f"label=com.docker.compose.project={case.project}",
                    ],
                    budget,
                    records,
                    "retained_volume_inventory",
                    cleanup=True,
                    cap=5,
                )
                .decode()
                .split()
            )
            records.append(dict(stage="retained_volumes", names=volumes))
        except BaseException:
            cleanup_ok = False
        try:
            supervisor.close_pg()
        except BaseException:
            cleanup_ok = False
    return dict(
        status=status if cleanup_ok else "CLEANUP_FAILED",
        records=records,
        volume="PRESERVED_NOT_DELETED",
        pg_api="SEE_ACTUAL_COMMAND_RECORDS",
        browser="NOT_RUN",
        full="NOT_RUN",
        hosted="NOT_RUN",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "execute", "probe"))
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--root-opened-window", action="store_true")
    args = parser.parse_args()
    try:
        case = Case(**json.loads(args.case.read_text()))
        if args.action == "prepare":
            prepare(case)
            report: dict[str, Any] = dict(status="PREPARED_ONLY", runtime="NOT_RUN")
        else:
            if args.action == "execute" and not args.root_opened_window:
                raise ValueError("Root must open exact new window")
            if args.action == "probe":
                case.validate()
                budget = Budget.bind(utc(case.starts_at), utc(case.deadline))
                adapter = OwnedAdapter(compose(case), case.project, budget)
                if case.scenario in {
                    "bootstrap_restart",
                    "identity_scopes",
                    "credential_revoke",
                    "grant_revoke",
                }:
                    run_owned_negative(case.scenario, case.api, case.web, budget, adapter)
                else:
                    run_scenario(case.scenario, case.api, case.web, budget, adapter)
                report = dict(status="PROBE_COMPLETED_PENDING_REVIEW")
            else:
                report = execute(case)
    except BaseException:
        report = dict(status="FAILED_OR_UNKNOWN", full="NOT_RUN", hosted="NOT_RUN")
    print(json.dumps(report))
    if report["status"] not in {
        "PREPARED_ONLY",
        "PROBE_COMPLETED_PENDING_REVIEW",
        "SCENARIO_COMPLETED_PENDING_REVIEW",
    }:
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
