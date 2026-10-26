"""One bounded M2 owned scenario: source -> dump -> empty target -> explicit continuation.

All nonsecret control flow is here. Private files contain only inputs, credentials and receipts.
Never resumes a failed run, retries an unknown write, or operates on an existing project.
"""

import argparse
import hashlib
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO
from uuid import UUID, uuid4

from commerceops.infrastructure.database import DatabaseSettings
from commerceops.infrastructure.web_config import private_bytes

from scripts.m2_backup import BackupFailure
from scripts.m2_state import save
from scripts.prepare_pg import prepare as prepare_pg
from tests.e2e.web.m1_acceptance_driver import ui_command

ROOT = Path(__file__).resolve().parents[1]
CONSUMER = [
    "npm",
    "exec",
    "--",
    "playwright",
    "test",
    "--config",
    "playwright.live.config.ts",
    "--grep",
]
DATABASE_PHASES = ("source", "restored", "revoked", "expired")
LAB_MODULE = "scripts.woo_lab"
PG_IMAGE = (
    "postgres:17.11-bookworm@sha256:"
    "3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826"
)


def utc() -> str:
    return datetime.now(UTC).isoformat()


def load(path: Path) -> Any:
    from commerceops.adapters.commerce.woocommerce_http import invalid_constant, object_pairs

    return json.loads(
        private_bytes(path), object_pairs_hook=object_pairs, parse_constant=invalid_constant
    )


def private_output(path: Path) -> BinaryIO:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    return os.fdopen(fd, "wb")


def reference(path: Path) -> dict[str, str]:
    from commerceops.adapters.commerce.woocommerce_config import read_private_file

    return {
        "file": path.name,
        "sha256": hashlib.sha256(read_private_file(str(path), 64 * 1024 * 1024)).hexdigest(),
    }


def environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    result = {
        k: os.environ[k]
        for k in (
            "PATH",
            "HOME",
            "TMPDIR",
            "LANG",
            "LC_ALL",
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "DOCKER_CONFIG",
        )
        if k in os.environ
    }
    result["PATH"] = str(ROOT / ".tools/node/bin") + os.pathsep + result.get("PATH", "")
    result.update(LANGSMITH_TRACING="false", NEXT_TELEMETRY_DISABLED="1", PYTHONNOUSERSITE="1")
    result.update(extra or {})
    return result


def selected_one(output: str, phase: str) -> None:
    expected = "M2 " + phase
    if not re.search(r"(?m)^Total: 1 test in 1 file\s*$", output):
        raise BackupFailure("M2_CONSUMER_SELECTION")
    rows = [line for line in output.splitlines() if "m2.spec.ts:" in line]
    if len(rows) != 1 or not rows[0].rstrip().endswith(expected):
        raise BackupFailure("M2_CONSUMER_SELECTION")


def consumer_argv(phase: str) -> list[str]:
    if phase not in ("source", "restored"):
        raise BackupFailure("M2_CONSUMER_PHASE")
    return [*CONSUMER, "M2 " + phase + "$"]


def source_identity() -> tuple[str, str]:
    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, env=environment(), timeout=10
        ).strip()

    if git("status", "--porcelain"):
        raise BackupFailure("M2_SOURCE_NOT_FROZEN")
    return git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")


def pg_overlay(pg: dict[str, Any]) -> dict[str, Any]:
    return dict(
        services=dict(
            postgres=dict(
                image=PG_IMAGE,
                environment={"POSTGRES_DB": pg["database"]},
                ports=[f"127.0.0.1:{pg['port']}:5432"],
                healthcheck=dict(
                    test=["CMD", "pg_isready", "-U", "commerceops_owner", "-d", pg["database"]]
                ),
            )
        )
    )


def verify_pg_overlay(directory: Path, request: dict[str, Any], phase: str) -> None:
    if load(directory / ("pg-" + phase) / "overlay.json") != pg_overlay(
        request["databases"][phase]
    ):
        raise BackupFailure("M2_PG_OVERLAY_CHANGED")


@dataclass
class Scenario:
    directory: Path
    request: dict[str, Any]
    expires: float
    children: dict[str, subprocess.Popen[bytes]] = field(default_factory=dict)
    command_number: int = 0
    pg_started: set[str] = field(default_factory=set)
    pg_ready: set[str] = field(default_factory=set)
    lab_directory: Path | None = None
    lab_inputs: dict[str, dict[str, str]] = field(default_factory=dict)
    cleanup_expires: float | None = None
    pg_stopped: dict[str, dict[str, Any]] = field(default_factory=dict)
    pg_initialized: set[str] = field(default_factory=set)
    canonical_sha256: str | None = None
    business_facts: dict[str, dict[str, Any]] = field(default_factory=dict)

    def remaining(self, cap: float, *, cleanup: bool = False) -> float:
        deadline = (
            min(self.expires, self.cleanup_expires or self.expires) if cleanup else self.expires
        )
        left = deadline - time.monotonic() - (0 if cleanup else 180)
        if left <= 0:
            raise BackupFailure("M2_DEADLINE")
        return min(cap, left)

    def command(
        self,
        tag: str,
        argv: list[str],
        *,
        cap: float = 60,
        cwd: Path = ROOT,
        env: dict[str, str] | None = None,
        stdin: BinaryIO | None = None,
        stdout: BinaryIO | None = None,
        cleanup: bool = False,
    ) -> bytes:
        duration = self.remaining(cap, cleanup=cleanup)
        self.command_number += 1
        name = f"{self.command_number:03d}-{tag}"
        log = self.directory / "commands" / (name + ".private.log")
        started = time.monotonic()
        code: int | None = None
        timed_out = False
        with private_output(log) as out:
            child = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env or environment(),
                stdin=stdin,
                stdout=stdout or out,
                stderr=out,
                start_new_session=True,
            )
            command_key = "command-" + name
            self.children[command_key] = child
            try:
                code = child.wait(timeout=duration)
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                reaped = self.stop_child(child, cleanup=True)
                if reaped:
                    del self.children[command_key]
                code = child.returncode
                save(
                    self.directory / "commands" / (name + ".safe.json"),
                    dict(
                        tag=tag,
                        native_exit=code,
                        timed_out=timed_out,
                        reaped=reaped,
                        elapsed_seconds=time.monotonic() - started,
                        finished_at_utc=utc(),
                    ),
                )
        if timed_out or not reaped or code != 0:
            raise BackupFailure("M2_COMMAND_FAILED")
        return log.read_bytes() if stdout is None else b""

    def stop_child(
        self, child: subprocess.Popen[bytes], *, cleanup: bool = False, signal_sent: bool = False
    ) -> bool:
        # Never signal a reaped leader: its numeric PID may already have been reused.
        if child.poll() is None:
            if not signal_sent:
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                child.wait(timeout=self.remaining(20, cleanup=cleanup))
            except subprocess.TimeoutExpired:
                if child.poll() is None:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                try:
                    child.wait(timeout=self.remaining(5, cleanup=True))
                except subprocess.TimeoutExpired:
                    return False
        # Query only the group allocated by this parent. Never kill an already-waited group.
        # A surviving descendant fails closed; wait/reap alone is not group-exit proof.
        until = time.monotonic() + self.remaining(3, cleanup=True)
        while time.monotonic() < until:
            try:
                probe = subprocess.run(
                    ["pgrep", "-g", str(child.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=environment(),
                    timeout=self.remaining(1, cleanup=True),
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                return False
            if probe.returncode == 1:
                return child.returncode is not None
            if probe.returncode != 0:
                return False
            time.sleep(0.05)
        return False

    def spawn(
        self, name: str, argv: list[str], env: dict[str, str], *, cwd: Path = ROOT
    ) -> subprocess.Popen[bytes]:
        self.remaining(1)
        if name in self.children:
            raise BackupFailure("M2_CHILD_ALREADY_STARTED")
        path = self.directory / (name + ".private.log")
        with private_output(path) as out:
            child = subprocess.Popen(
                argv, cwd=cwd, env=env, stdout=out, stderr=out, start_new_session=True
            )
        self.children[name] = child
        save(
            self.directory / (name + "-started.safe.json"),
            dict(pid=child.pid, started_at_utc=utc()),
        )
        return child

    def compose(self, phase: str) -> list[str]:
        verify_pg_overlay(self.directory, self.request, phase)
        pg = self.request["databases"][phase]
        return [
            "docker",
            "compose",
            "--env-file",
            os.devnull,
            "-p",
            pg["project"],
            "-f",
            str(ROOT / "compose.yml"),
            "-f",
            str(self.directory / ("pg-" + phase) / "overlay.json"),
        ]

    def pg_environment(self, phase: str) -> dict[str, str]:
        return environment({"COMMERCEOPS_PG_RUNTIME_DIR": str(self.directory / ("pg-" + phase))})

    def inspect_pg(self, phase: str) -> str:
        pg = self.request["databases"][phase]
        found = (
            self.command(
                "pg-id-" + phase,
                [*self.compose(phase), "ps", "-q", "postgres"],
                env=self.pg_environment(phase),
            )
            .decode()
            .strip()
        )
        if re.fullmatch(r"[0-9a-f]{64}", found) is None:
            raise BackupFailure("M2_PG_IDENTITY")
        info = json.loads(self.command("pg-inspect-" + phase, ["docker", "inspect", found]))
        if len(info) != 1:
            raise BackupFailure("M2_PG_IDENTITY")
        row = info[0]
        labels = row["Config"]["Labels"]
        mounts = [m for m in row["Mounts"] if m["Destination"] == "/var/lib/postgresql/data"]
        ports = row["NetworkSettings"]["Ports"].get("5432/tcp")
        if (
            labels.get("com.docker.compose.project") != pg["project"]
            or labels.get("com.docker.compose.service") != "postgres"
            or row["Config"]["Image"] != PG_IMAGE
            or not row["State"]["Running"]
            or ports != [{"HostIp": "127.0.0.1", "HostPort": str(pg["port"])}]
            or len(mounts) != 1
            or mounts[0].get("Name") != pg["volume"]
        ):
            raise BackupFailure("M2_PG_IDENTITY")
        return found

    def start_pg(self, phase: str) -> str:
        verify_pg_overlay(self.directory, self.request, phase)
        pg = self.request["databases"][phase]
        for args in (["ps", "-aq"], ["network", "ls", "-q"], ["volume", "ls", "-q"]):
            if self.command(
                "pg-empty-" + phase,
                ["docker", *args, "--filter", "label=com.docker.compose.project=" + pg["project"]],
            ).strip():
                raise BackupFailure("M2_PG_RESOURCE_ALREADY_EXISTS")
        self.pg_started.add(phase)  # Cleanup owns a partially failed start too.
        self.command(
            "pg-start-" + phase,
            [*self.compose(phase), "up", "-d", "--wait", "--wait-timeout", "60", "postgres"],
            cap=90,
            env=self.pg_environment(phase),
        )
        identity = self.inspect_pg(phase)
        self.pg_ready.add(phase)
        return identity

    def stop_pg(self, phase: str) -> dict[str, Any]:
        self.command(
            "pg-stop-" + phase,
            [*self.compose(phase), "down"],
            cap=60,
            env=self.pg_environment(phase),
            cleanup=True,
        )
        pg = self.request["databases"][phase]
        for args in (["ps", "-aq"], ["network", "ls", "-q"]):
            if self.command(
                "pg-stopped-" + phase,
                ["docker", *args, "--filter", "label=com.docker.compose.project=" + pg["project"]],
                cleanup=True,
            ).strip():
                raise BackupFailure("M2_PG_STOP_UNCONFIRMED")
        volumes = (
            self.command(
                "pg-volume-" + phase,
                [
                    "docker",
                    "volume",
                    "ls",
                    "-q",
                    "--filter",
                    "label=com.docker.compose.project=" + pg["project"],
                ],
                cleanup=True,
            )
            .decode()
            .splitlines()
        )
        if (phase in self.pg_ready and volumes != [pg["volume"]]) or set(volumes) - {pg["volume"]}:
            raise BackupFailure("M2_PG_VOLUME_UNCONFIRMED")
        with socket.socket() as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(("127.0.0.1", pg["port"])) == 0:
                raise BackupFailure("M2_PG_LISTENER_UNCONFIRMED")
        self.pg_started.remove(phase)
        result = dict(
            containers=0,
            networks=0,
            volume_retained=volumes == [pg["volume"]],
            stopped_at_utc=utc(),
        )
        self.pg_stopped[phase] = result
        return result


def database(
    directory: Path, request: dict[str, Any], phase: str, *, app: bool = False
) -> DatabaseSettings:
    pg = request["databases"][phase]
    return DatabaseSettings(
        host="127.0.0.1",
        port=pg["port"],
        name=pg["database"],
        user="commerceops_app" if app else "commerceops_owner",
        password_file=directory / ("pg-" + phase) / ("app_password" if app else "owner_password"),
        runtime_password_file=None if app else directory / ("pg-" + phase) / "app_password",
    )


def prepare_run(deadline: str, anchor: str) -> Path:
    from datetime import date
    from zoneinfo import ZoneInfo

    stop = datetime.fromisoformat(deadline)
    if stop.utcoffset() is None or not 420 <= (stop - datetime.now(UTC)).total_seconds() <= 3600:
        raise BackupFailure("M2_REGISTRATION_DEADLINE")
    if date.fromisoformat(anchor) > datetime.now(ZoneInfo("Asia/Shanghai")).date():
        raise BackupFailure("M2_ANCHOR_DAY")
    sha, tree = source_identity()
    run = uuid4()
    directory = ROOT / "runtime" / ("m2-" + run.hex)
    directory.mkdir(mode=0o700, parents=True)
    (directory / "commands").mkdir(mode=0o700)
    for phase in ("source", "restored", "canonical", *("pg-" + p for p in DATABASE_PHASES)):
        (directory / phase).mkdir(mode=0o700)
    # Reserve all selections together, then release them; readiness must recheck owners.
    sockets = [socket.socket() for _ in range(6)]
    try:
        for sock in sockets:
            sock.bind(("127.0.0.1", 0))
        ports = [s.getsockname()[1] for s in sockets]
    finally:
        for sock in sockets:
            sock.close()
    request: dict[str, Any] = dict(
        schema_version="p5-m2-owned-run-v1",
        run_id=str(run),
        source_sha=sha,
        source_tree=tree,
        anchor_day=anchor,
        started_at_utc=utc(),
        stop_at_utc=stop.isoformat(),
        cleanup_reserve_seconds=180,
        api_origin=f"http://127.0.0.1:{ports[4]}",
        web_origin=f"http://127.0.0.1:{ports[5]}",
        databases={},
    )
    for index, phase in enumerate(DATABASE_PHASES):
        project = "m2-" + phase + "-" + run.hex[:12]
        pg = dict(
            project=project, database="m2_" + phase, volume=project + "_pg_data", port=ports[index]
        )
        request["databases"][phase] = pg
        prepare_pg(directory / ("pg-" + phase))
        save(
            directory / ("pg-" + phase) / "overlay.json",
            pg_overlay(pg),
        )
    save(directory / "request.private.json", request)
    return directory


def open_run(directory: Path) -> Scenario:
    if directory.parent != ROOT / "runtime" or not re.fullmatch(r"m2-[0-9a-f]{32}", directory.name):
        raise BackupFailure("M2_PRIVATE_DIRECTORY")
    if (
        directory.resolve() != directory
        or directory.stat().st_uid != os.geteuid()
        or directory.stat().st_mode & 0o777 != 0o700
    ):
        raise BackupFailure("M2_PRIVATE_DIRECTORY")
    request = load(directory / "request.private.json")
    validate_request(request, directory)
    for phase in DATABASE_PHASES:
        verify_pg_overlay(directory, request, phase)
    sha, tree = source_identity()
    if (request["source_sha"], request["source_tree"]) != (sha, tree):
        raise BackupFailure("M2_SOURCE_CHANGED")
    if UUID(request["run_id"]).hex != directory.name.removeprefix("m2-"):
        raise BackupFailure("M2_RUN_IDENTITY")
    remaining = (datetime.fromisoformat(request["stop_at_utc"]) - datetime.now(UTC)).total_seconds()
    if not 420 <= remaining <= 3600:
        raise BackupFailure("M2_REGISTRATION_DEADLINE")
    save(
        directory / "parent-started.safe.json",
        dict(
            parent_pid=os.getpid(),
            started_at_utc=utc(),
            source_sha=sha,
            source_tree=tree,
            request_sha256=reference(directory / "request.private.json")["sha256"],
        ),
    )
    return Scenario(directory, request, time.monotonic() + remaining)


def child_command(parent: Scenario, action: str) -> None:
    extra = {}
    if action == "bind-source":
        verify_lab_inputs(parent)
        extra["M2_OWNED_LAB_DIRECTORY"] = str(parent.lab_directory)
        extra["M2_OWNED_LAB_CONFIG_SHA"] = parent.lab_inputs["lab.json"]["sha256"]
        if parent.lab_directory is None:
            raise BackupFailure("M2_LAB_REGISTRATION_MISSING")
        verify_lab_probe(parent.lab_directory)
    parent.command(
        action,
        [
            sys.executable,
            "-m",
            "scripts.m2_owned",
            "_child",
            "--directory",
            str(parent.directory),
            "--child-action",
            action,
        ],
        cap=120,
        env=environment(extra),
    )


def run_child(directory: Path, action: str) -> None:
    import asyncio

    from commerceops.entrypoints.database import grant_runtime, migrate, setup_checkpointer
    from commerceops.infrastructure.database import connect
    from psycopg import sql

    from scripts.m2_backup import empty_target, quiescent_snapshot, same_snapshot
    from scripts.m2_state import (
        bind_source,
        completed_receipt,
        pending_checkpoint,
        pending_receipt,
        seed,
        stopped_business_facts,
        web_configuration,
    )

    request = load(directory / "request.private.json")
    parent = load(directory / "parent-started.safe.json")
    validate_request(request, directory)
    if parent["request_sha256"] != reference(directory / "request.private.json")["sha256"]:
        raise BackupFailure("M2_REQUEST_CHANGED")
    if os.getppid() != parent["parent_pid"] or datetime.now(UTC) >= datetime.fromisoformat(
        request["stop_at_utc"]
    ):
        raise BackupFailure("M2_CHILD_OWNER")
    if source_identity() != (request["source_sha"], request["source_tree"]):
        raise BackupFailure("M2_SOURCE_CHANGED")
    source = database(directory, request, "source")
    if action in tuple(phase + "-facts" for phase in DATABASE_PHASES):
        phase = action.removesuffix("-facts")
        path = directory / "canonical/m2-facts.private.json"
        if reference(path)["sha256"] != os.environ.get("M2_CANONICAL_SHA256"):
            raise BackupFailure("M2_CANONICAL_CHANGED")
        with connect(database(directory, request, phase, app=True)) as db:
            facts = stopped_business_facts(db, load(path)["canonical_source"])
        facts.update({k: request[k] for k in ("run_id", "source_sha", "source_tree")})
        facts["canonical_sha256"] = reference(path)["sha256"]
        save(directory / (phase + "-business-facts.safe.json"), facts)
    elif action == "source-init":
        migrate(source)
        asyncio.run(setup_checkpointer(source))
        grant_runtime(source)
        seed(source, directory, request["run_id"])
    elif action == "bind-source":
        reference_data = load(directory / "lab-reference.private.json")
        expected_lab = os.environ.get("M2_OWNED_LAB_DIRECTORY")
        if expected_lab is None or reference_data != dict(directory=expected_lab):
            raise BackupFailure("M2_LAB_REFERENCE_CHANGED")
        lab = Path(expected_lab)
        if reference(lab / "lab.json")["sha256"] != os.environ.get("M2_OWNED_LAB_CONFIG_SHA"):
            raise BackupFailure("M2_LAB_INPUT_CHANGED")
        verify_lab_probe(lab)
        bind_source(source, directory, lab, request["anchor_day"])
        for phase in DATABASE_PHASES:
            save(
                directory / ("configuration-" + phase + ".json"),
                web_configuration(
                    directory, database(directory, request, phase, app=True), request["web_origin"]
                ),
            )
    elif action == "source-pending":
        observed = load(directory / "source/source-observed.private.json")
        with connect(database(directory, request, "source", app=True)) as db:
            receipt = pending_receipt(
                db,
                observed,
                load(directory / "source/source-approval-read.private.json"),
                load(directory / "source/analysis-golden.private.json"),
                load(directory / "seed.private.json"),
                load(directory / "binding.private.json"),
            )
        from commerceops.infrastructure.web_config import WebConfig

        checkpoint = asyncio.run(
            pending_checkpoint(
                WebConfig.from_file(directory / "configuration-source.json"), observed
            )
        )
        receipt["checkpoint"] = checkpoint
        receipt.update({k: request[k] for k in ("run_id", "source_sha", "source_tree")})
        save(directory / "canonical/parent-source-pg.safe.json", receipt)
    elif action in (
        "source-before",
        "source-after",
        "restored-before",
        "revoked-before",
        "expired-before",
    ):
        selected = (
            source
            if action.startswith("source")
            else database(directory, request, action.split("-")[0])
        )
        with connect(selected) as db:
            snapshot = quiescent_snapshot(db)
        save(directory / (action + ".private.json"), snapshot)
        if action != "source-before":
            same_snapshot(load(directory / "source-before.private.json"), snapshot)
        from commerceops.infrastructure.web_config import WebConfig

        phase = action.split("-")[0]
        observed = load(directory / "canonical/m2-facts.private.json")["canonical_source"]
        checkpoint = asyncio.run(
            pending_checkpoint(
                WebConfig.from_file(directory / ("configuration-" + phase + ".json")), observed
            )
        )
        original = load(directory / "canonical/parent-source-pg.safe.json")["checkpoint"]
        if checkpoint != original:
            raise BackupFailure("M2_RESTORE_CHECKPOINT_MISMATCH")
        save(directory / (action + "-checkpoint.safe.json"), checkpoint)
    elif action in ("target-empty", "revoked-empty", "expired-empty"):
        phase = "restored" if action == "target-empty" else action.split("-")[0]
        selected = database(directory, request, phase)
        with connect(selected) as db:
            empty_target(db)
            existing = db.execute(
                "SELECT count(*) AS n FROM pg_roles WHERE rolname='commerceops_app'"
            ).fetchone()
            if existing != {"n": 0}:
                raise BackupFailure("M2_TARGET_ROLE_ALREADY_EXISTS")
            secret = (
                database(directory, request, phase, app=True).bounded_password().get_secret_value()
            )
            db.execute(
                sql.SQL(
                    "CREATE ROLE commerceops_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                    "NOREPLICATION NOBYPASSRLS PASSWORD {}"
                ).format(sql.Literal(secret))
            )
    elif action in (
        "revoked-fixture",
        "expired-clock",
        "revoked-decision",
        "expired-decision",
        "revoked-collect",
        "expired-collect",
    ):
        negative_child(directory, request, action)
    elif action == "restored-completed":
        with connect(database(directory, request, "restored", app=True)) as db:
            receipt = completed_receipt(
                db,
                load(directory / "restored/restored-observed.private.json"),
                load(directory / "restored/analysis-golden.private.json"),
                load(directory / "seed.private.json"),
            )
        receipt.update({k: request[k] for k in ("run_id", "source_sha", "source_tree")})
        save(directory / "restored/parent-completed-pg.safe.json", receipt)
    else:
        raise BackupFailure("M2_CHILD_ACTION")


def validate_request(request: dict[str, Any], directory: Path) -> None:
    from urllib.parse import urlsplit

    if set(request) != {
        "schema_version",
        "run_id",
        "source_sha",
        "source_tree",
        "anchor_day",
        "started_at_utc",
        "stop_at_utc",
        "cleanup_reserve_seconds",
        "api_origin",
        "web_origin",
        "databases",
    }:
        raise BackupFailure("M2_REQUEST_SCHEMA")
    run = UUID(request["run_id"])
    if (
        request["schema_version"] != "p5-m2-owned-run-v1"
        or request["cleanup_reserve_seconds"] != 180
        or directory != ROOT / "runtime" / ("m2-" + run.hex)
        or directory.resolve() != directory
        or directory.stat().st_uid != os.geteuid()
        or directory.stat().st_mode & 0o777 != 0o700
    ):
        raise BackupFailure("M2_REQUEST_SCOPE")
    ports = []
    for origin in (request["api_origin"], request["web_origin"]):
        parsed = urlsplit(origin)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.port is None
            or origin != f"http://127.0.0.1:{parsed.port}"
        ):
            raise BackupFailure("M2_ORIGIN")
        ports.append(parsed.port)
    if set(request["databases"]) != set(DATABASE_PHASES):
        raise BackupFailure("M2_DATABASE_SET")
    for phase, pg in request["databases"].items():
        project = "m2-" + phase + "-" + run.hex[:12]
        if (
            set(pg) != {"project", "database", "volume", "port"}
            or pg["project"] != project
            or pg["database"] != "m2_" + phase
            or pg["volume"] != project + "_pg_data"
            or type(pg["port"]) is not int
            or not 1024 <= pg["port"] <= 65535
        ):
            raise BackupFailure("M2_DATABASE_SCOPE")
        ports.append(pg["port"])
    if len(set(ports)) != 6:
        raise BackupFailure("M2_PORT_COLLISION")
    if any(
        re.fullmatch(r"[0-9a-f]{40}", request[k]) is None for k in ("source_sha", "source_tree")
    ):
        raise BackupFailure("M2_SOURCE_IDENTITY")
    started, stop = (datetime.fromisoformat(request[k]) for k in ("started_at_utc", "stop_at_utc"))
    if (
        started.utcoffset() is None
        or stop.utcoffset() is None
        or not 420 <= (stop - started).total_seconds() <= 3600
    ):
        raise BackupFailure("M2_REGISTRATION_DEADLINE")


def apps_environment(parent: Scenario, phase: str) -> dict[str, str]:
    return environment(
        {
            "COMMERCEOPS_MODE": "test",
            "COMMERCEOPS_HOST": "127.0.0.1",
            "COMMERCEOPS_PORT": parent.request["api_origin"].rsplit(":", 1)[1],
            "COMMERCEOPS_P3_CONFIG_FILE": str(
                parent.directory / ("configuration-" + phase + ".json")
            ),
            "COMMERCEOPS_UI_MODE": "live",
            "COMMERCEOPS_WEB_TRANSPORT": "local_http",
            "COMMERCEOPS_API_ORIGIN": parent.request["api_origin"],
        }
    )


def web_argv(parent: Scenario) -> list[str]:
    return [
        "node",
        str(ROOT / "frontend/node_modules/next/dist/bin/next"),
        "start",
        "--hostname",
        "127.0.0.1",
        "--port",
        parent.request["web_origin"].rsplit(":", 1)[1],
    ]


def expected_service_term(
    parent: Scenario, kind: str, argv: Any, code: int | None, requested: bool
) -> bool:
    if not requested:
        return False
    if code == -signal.SIGTERM:
        return True
    # Locked Next 16.4.2 performs cleanup and exits 128+SIGTERM itself.
    # Only the exact owned Next command may use that convention, never API/Worker or early exit.
    return kind == "web" and code == 128 + signal.SIGTERM and argv == web_argv(parent)


def start_apps(parent: Scenario, phase: str) -> dict[str, int]:
    import httpx

    seed_data = load(parent.directory / "seed.private.json")
    env = apps_environment(parent, phase)
    api = parent.spawn(phase + "-api", [sys.executable, "-m", "commerceops.entrypoints.api"], env)
    web = parent.spawn(
        phase + "-web",
        web_argv(parent),
        env,
        cwd=ROOT / "frontend",
    )
    worker = parent.spawn(
        phase + "-worker",
        [
            sys.executable,
            "-m",
            "commerceops.entrypoints.worker",
            "test-run",
            "--organization",
            seed_data["organization_id"],
        ],
        env,
    )
    until = time.monotonic() + parent.remaining(60)
    while time.monotonic() < until:
        if any(child.poll() is not None for child in (api, web, worker)):
            raise BackupFailure("M2_APP_EXITED_BEFORE_READY")
        try:
            with httpx.Client(timeout=1, trust_env=False, follow_redirects=False) as client:
                api_ready = (
                    client.get(parent.request["api_origin"] + "/health/live").status_code == 200
                )
                web_ready = client.get(parent.request["web_origin"] + "/login").status_code == 200
            worker_ready = (
                b"technical test worker started:"
                in (parent.directory / (phase + "-worker.private.log")).read_bytes()
            )
            if api_ready and web_ready and worker_ready:
                return dict(api_pid=api.pid, web_pid=web.pid, worker_pid=worker.pid)
        except (OSError, TimeoutError, httpx.HTTPError):
            pass
        time.sleep(0.2)
    raise BackupFailure("M2_APP_READY_DEADLINE")


def stop_apps(parent: Scenario, phase: str, *, require_clean_worker: bool = True) -> dict[str, Any]:
    receipts = {}
    requested = {}
    errors = []
    # Signal every still-running owned writer before waiting for any of them.
    for kind in ("worker", "api", "web"):
        child = parent.children.get(phase + "-" + kind)
        if child is None:
            continue
        requested[kind] = False
        if child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
                requested[kind] = True
            except ProcessLookupError:
                pass
    for kind in ("worker", "api", "web"):
        key = phase + "-" + kind
        child = parent.children.get(key)
        if child is None:
            continue
        reaped = False
        try:
            reaped = parent.stop_child(child, cleanup=True, signal_sent=requested[kind])
        except BaseException as error:
            errors.append(dict(process=kind, category=type(error).__name__))
        expected_term = expected_service_term(
            parent, kind, child.args, child.returncode, requested[kind]
        )
        normal = (
            child.returncode == 0
            if kind == "worker"
            else (requested[kind] and (child.returncode == 0 or expected_term))
        )
        receipts[kind] = dict(
            pid=child.pid,
            native_exit=child.returncode,
            parent_requested_stop=requested[kind],
            reaped=reaped,
            expected_owned_term=expected_term,
            accepted_exit=normal and reaped,
        )
        if reaped:
            del parent.children[key]
        if not normal or not reaped:
            errors.append(dict(process=kind, category="UNEXPECTED_EXIT_OR_REAP"))
    if require_clean_worker and receipts.get("worker", {}).get("accepted_exit") is not True:
        errors.append(dict(process="worker", category="WORKER_STOP_UNCONFIRMED"))
    result = dict(stopped_at_utc=utc(), processes=receipts, errors=errors)
    path = parent.directory / (phase + "-apps-stopped.safe.json")
    attempt = 1
    while path.exists():
        attempt += 1
        path = parent.directory / (phase + f"-apps-stopped-{attempt}.safe.json")
    save(path, result)
    if errors:
        raise BackupFailure("M2_APP_UNEXPECTED_EXIT")
    return result


def copy_evidence(source: Path, destination: Path) -> None:
    from commerceops.adapters.commerce.woocommerce_config import read_private_file

    raw = read_private_file(str(source), 2 * 1024 * 1024)
    save(destination, raw)
    if hashlib.sha256(raw).hexdigest() != reference(destination)["sha256"]:
        raise BackupFailure("M2_EVIDENCE_COPY")


def sku_map(lab: Path) -> list[dict[str, Any]]:
    expected = load(lab / "expected.private.json")
    golden = load(lab / "analysis-golden.private.json")
    mapping = load(lab / "seed-result.private.json")["mapping"]["products"]
    spec = load(lab / "seed-spec.private.json")
    definitions = {row["key"]: row for row in spec["products"]}
    rows = {row["sku_key"]: row for row in expected["expected"]["products"]}
    facts = golden["facts"]
    if {f["logical_key"] for f in facts} != {
        "simple_a",
        "simple_b",
        "independent_red",
        "independent_blue",
    } or len(facts) != 4:
        raise BackupFailure("M2_GOLDEN_SKU_SET")
    output = []
    for fact in facts:
        key = fact["logical_key"]
        definition = definitions[key]
        row = rows[fact["sku_key"]]
        pid = (
            str(mapping[definition["parent"]])
            if definition["type"] == "variation"
            else str(mapping[key])
        )
        vid = str(mapping[key]) if definition["type"] == "variation" else None
        if (row["product_id"], row["variant_id"], row["stock_pool_key"]) != (
            pid,
            vid,
            fact["stock_pool_key"],
        ):
            raise BackupFailure("M2_SKU_MAPPING")
        output.append(
            dict(
                logical_key=key,
                product_id=pid,
                variant_id=vid,
                sku_key=fact["sku_key"],
                stock_pool_key=fact["stock_pool_key"],
            )
        )
    if len({x["sku_key"] for x in output}) != 4 or len({x["stock_pool_key"] for x in output}) != 4:
        raise BackupFailure("M2_SKU_MAPPING")
    return output


def outputs(phase: str) -> list[str]:
    if phase == "source":
        return [
            "source-create-request.private.json",
            "source-create-receipt.private.json",
            "source-create-lookup.private.json",
            "source-task-read.private.json",
            "source-report-read.private.json",
            "source-plan-read.private.json",
            "source-approval-read.private.json",
            "source-observed.private.json",
            "source-results.safe.json",
        ]
    return [
        "restored-before-task-read.private.json",
        "restored-before-report-read.private.json",
        "restored-before-plan-read.private.json",
        "restored-before-approval-read.private.json",
        "restored-decision-request.private.json",
        "restored-decision-receipt.private.json",
        "restored-decision-lookup.private.json",
        "restored-after-task-read.private.json",
        "restored-execution-read.private.json",
        "restored-observed.private.json",
        "restored-results.safe.json",
        *[f"restored-replay-{n:02d}.private.json" for n in range(1, 11)],
    ]


def handoff(
    parent: Scenario,
    phase: str,
    pids: dict[str, int],
    *,
    canonical: dict[str, Any] | None = None,
    restore: dict[str, Any] | None = None,
) -> float:
    if parent.lab_directory is None:
        raise BackupFailure("M2_LAB_NOT_BOUND")
    directory = parent.directory / phase
    lab = parent.lab_directory
    r = parent.request
    seed_data = load(parent.directory / "seed.private.json")
    binding = load(parent.directory / "binding.private.json")
    common = {key: r[key] for key in ("run_id", "source_sha", "source_tree")}
    phase_name = "source_ready" if phase == "source" else "restored_pending_verified"
    now = datetime.now(UTC)
    stop = datetime.fromisoformat(r["stop_at_utc"])
    if (stop - now).total_seconds() < 420:
        raise BackupFailure("M2_CONSUMER_CAPACITY")
    original_expiry = None if canonical is None else datetime.fromisoformat(canonical["expires_at"])
    if phase == "restored" and (
        original_expiry is None or (original_expiry - now).total_seconds() < 300
    ):
        raise BackupFailure("M2_ORIGINAL_TTL_CAPACITY")
    duration = min(240, (stop - now).total_seconds() - 180)
    if original_expiry is not None:
        duration = min(duration, (original_expiry - now).total_seconds() - 60)
    from datetime import timedelta

    consumer_stop = now + timedelta(seconds=duration)
    resources = {key: r["databases"][key] for key in ("source", "restored")}
    save(
        directory / "parent-resources.safe.json",
        dict(
            schema_version="p5-m2-resource-receipt-v1",
            **common,
            source=resources["source"],
            target=resources["restored"],
            active_database=phase,
            source_started="source" in parent.pg_ready,
            target_started="restored" in parent.pg_ready,
            **pids,
            observed_at_utc=utc(),
        ),
    )
    save(
        directory / "window.json",
        dict(
            schema_version="p5-m2-live-resource-v1",
            **common,
            owner="phase5-M2-live",
            batch="p5-m2-live",
            phase=phase_name,
            build_id=(ROOT / "frontend/.next/BUILD_ID").read_text().strip(),
            api_origin=r["api_origin"],
            web_origin=r["web_origin"],
            **pids,
            organization_id=seed_data["organization_id"],
            shop_id=seed_data["shop_id"],
            started_at_utc=r["started_at_utc"],
            stop_at_utc=r["stop_at_utc"],
            cleanup_reserve_seconds=180,
            consumer_started_at_utc=now.isoformat(),
            consumer_stop_at_utc=consumer_stop.isoformat(),
            consumer_cap_seconds=240,
            original_expires_at=None if original_expiry is None else original_expiry.isoformat(),
            active_database=phase,
            source_database={k: resources["source"][k] for k in ("project", "database", "volume")},
            target_database=None
            if phase == "source"
            else {k: resources["restored"][k] for k in ("project", "database", "volume")},
            resource_registration_ref=reference(directory / "parent-resources.safe.json"),
            stop_owner="A",
        ),
    )
    save(
        directory / "web-accounts.json",
        dict(schema_version="p5-m2-live-accounts-v1", **common, **seed_data["accounts"]),
    )
    for name in (
        "expected.private.json",
        "analysis-golden.private.json",
        "seed-result.private.json",
    ):
        copy_evidence(lab / name, directory / name)
    metadata = binding["metadata"]
    expected = load(directory / "expected.private.json")
    save(
        directory / "m2-source.private.json",
        dict(
            schema_version="p5-m2-live-source-v1",
            **common,
            organization_id=seed_data["organization_id"],
            shop_id=seed_data["shop_id"],
            binding_id=binding["binding_id"],
            config_ref=metadata["config_ref"],
            source_kind="woocommerce_test",
            source_config_version=binding["source_config_version"],
            registration_digest=binding["registration_digest"],
            profile="positive-v1",
            anchor_day=r["anchor_day"],
            business_now=expected["business_now"],
            window=expected["window"],
            timezone="Asia/Shanghai",
            currency="CNY",
            parameters=dict(L=3, R=7, S=2),
            expected_ref=reference(directory / "expected.private.json"),
            expected_schema_version="woo-local-expectations-v1",
            golden_ref=reference(directory / "analysis-golden.private.json"),
            golden_schema_version="woo-positive-golden-v1",
            seed_result_ref=reference(directory / "seed-result.private.json"),
            sku_map=sku_map(lab),
        ),
    )
    save(
        directory / "m2-facts.private.json",
        dict(
            schema_version="p5-m2-live-facts-v1",
            **common,
            canonical_source=canonical,
            restore_binding=restore,
        ),
    )
    save(
        directory / "consumer.private.json",
        dict(
            schema_version="p5-m2-live-consumer-v1",
            **common,
            phase=phase_name,
            cwd="frontend",
            argv=consumer_argv(phase),
            retries=0,
            cap_seconds=240,
            business_revalidation_seconds=20,
            exit_and_evidence_reserve_seconds=40,
            mutation_reserve_seconds=60,
            restored_min_ttl_at_start_seconds=300,
            allowed_output_files=outputs(phase),
        ),
    )
    return time.monotonic() + max(0, (consumer_stop - datetime.now(UTC)).total_seconds())


def consume(parent: Scenario, phase: str, deadline: float) -> None:
    directory = parent.directory / phase
    for name in outputs(phase):
        if (directory / name).exists():
            raise BackupFailure("M2_CONSUMER_OUTPUT_ALREADY_EXISTS")
    env = environment(
        {
            "COMMERCEOPS_WEB_BATCH": "p5-m2-live",
            "COMMERCEOPS_B02_PRIVATE_DIR": str(directory),
            "COMMERCEOPS_LIVE_WEB_URL": parent.request["web_origin"],
        }
    )
    started = utc()
    clock = time.monotonic()
    result = ui_command(
        consumer_argv(phase),
        cwd=ROOT / "frontend",
        env=env,
        timeout=min(parent.remaining(240), deadline - clock),
    )
    save(directory / (phase + "-consumer.private.log"), result.stdout.encode())
    save(
        directory / (phase + "-parent.safe.json"),
        dict(
            schema_version="p5-m2-consumer-parent-v1",
            run_id=parent.request["run_id"],
            source_sha=parent.request["source_sha"],
            source_tree=parent.request["source_tree"],
            phase=phase,
            native_exit=result.code,
            process_cleanup_confirmed=result.error_code is None,
            error_code=result.error_code,
            started_at_utc=started,
            finished_at_utc=utc(),
            elapsed_seconds=time.monotonic() - clock,
        ),
    )
    if result.code != 0 or result.error_code is not None:
        raise BackupFailure("M2_CONSUMER_FAILED")
    logical = load(directory / (phase + "-results.safe.json"))
    if (
        logical["logical_outcome"] != "passed"
        or logical["error_code"] is not None
        or any(logical[k] != parent.request[k] for k in ("run_id", "source_sha", "source_tree"))
    ):
        raise BackupFailure("M2_CONSUMER_RESULT")
    for ref in logical["artifact_refs"]:
        if (
            set(ref) != {"file", "sha256"}
            or ref["file"] not in outputs(phase)
            or reference(directory / ref["file"]) != ref
        ):
            raise BackupFailure("M2_CONSUMER_ARTIFACT")
    if phase == "restored":
        key = load(directory / "restored-observed.private.json")["decision_request_key"]
        for n in range(1, 11):
            replay = load(directory / f"restored-replay-{n:02d}.private.json")
            if (
                replay["request_key"] != key
                or replay["outcome"] != "confirmed"
                or replay["http_status"] != 200
                or replay["via"] != "post"
                or replay["operation"] != "decision"
            ):
                raise BackupFailure("M2_ORIGINAL_KEY_REPLAY")


def canonical_source(parent: Scenario) -> dict[str, Any]:
    r = parent.request
    source = parent.directory / "source"
    canonical = parent.directory / "canonical"
    observed = load(source / "source-observed.private.json")
    binding = load(parent.directory / "binding.private.json")
    value = {
        k: observed[k]
        for k in (
            "organization_id",
            "shop_id",
            "create_request_key",
            "task_id",
            "source_task_id",
            "report_id",
            "snapshot_id",
            "facts_hash",
            "plan_id",
            "plan_version",
            "plan_hash",
            "approval_id",
            "expires_at",
            "required_assumption_keys",
        )
    }
    value.update(
        source_binding_id=binding["binding_id"],
        source_config_version=binding["source_config_version"],
    )
    for key, name in {
        "source_observed_ref": "source-observed.private.json",
        "source_create_request_ref": "source-create-request.private.json",
        "source_create_receipt_ref": "source-create-receipt.private.json",
        "source_approval_read_ref": "source-approval-read.private.json",
    }.items():
        copy_evidence(source / name, canonical / name)
        value[key] = reference(canonical / name)
    value["pg_source_receipt_ref"] = reference(canonical / "parent-source-pg.safe.json")
    save(
        canonical / "m2-facts.private.json",
        dict(
            schema_version="p5-m2-live-facts-v1",
            **{k: r[k] for k in ("run_id", "source_sha", "source_tree")},
            canonical_source=value,
            restore_binding=None,
        ),
    )
    return value


def verify_lab_probe(directory: Path) -> None:
    config = load(directory / "lab.json")
    probe = load(directory / "probe-config.private.json")
    expected = dict(
        base_url=config["url"],
        consumer_key_file=str(directory / "consumer_key"),
        consumer_secret_file=str(directory / "consumer_secret"),
        ca_file=str(directory / "ca.crt"),
    )
    if any(probe.get(field) != value for field, value in expected.items()):
        raise BackupFailure("M2_LAB_PROBE_REFERENCE_CHANGED")


def verify_lab_inputs(parent: Scenario) -> None:
    directory = parent.lab_directory
    if directory is None or load(parent.directory / "lab-reference.private.json") != dict(
        directory=str(directory)
    ):
        raise BackupFailure("M2_LAB_REFERENCE_CHANGED")
    if set(parent.lab_inputs) != {"lab.json", "compose.env"}:
        raise BackupFailure("M2_LAB_REGISTRATION_MISSING")
    for name, expected in parent.lab_inputs.items():
        if reference(directory / name) != expected:
            raise BackupFailure("M2_LAB_INPUT_CHANGED")


def start_lab(parent: Scenario) -> Path:
    seed_data = load(parent.directory / "seed.private.json")
    raw = parent.command(
        "lab-prepare",
        [
            sys.executable,
            "-m",
            LAB_MODULE,
            "prepare",
            "--profile",
            "positive-v1",
            "--anchor-day",
            parent.request["anchor_day"],
            "--shop-id",
            seed_data["shop_id"],
        ],
        cap=90,
    ).decode()
    candidates = [
        Path(line.strip())
        for line in raw.splitlines()
        if line.strip().startswith(str(ROOT / "runtime/woolab-"))
    ]
    if len(candidates) != 1:
        raise BackupFailure("M2_LAB_DIRECTORY")
    directory = candidates[0]
    parent.lab_directory = directory
    parent.lab_inputs = {name: reference(directory / name) for name in ("lab.json", "compose.env")}
    save(parent.directory / "lab-reference.private.json", dict(directory=str(directory)))
    save(parent.directory / "lab-inputs.safe.json", parent.lab_inputs)
    verify_lab_inputs(parent)
    # Reuse B's existing image build and lifecycle; no second lab driver or reseed.
    parent.command(
        "lab-build",
        [sys.executable, "-m", LAB_MODULE, "build", "--directory", str(directory)],
        cap=600,
    )
    seconds = int(parent.remaining(3600, cleanup=True))
    if seconds < 600:
        raise BackupFailure("M2_LAB_CAPACITY")
    verify_lab_inputs(parent)
    child = parent.spawn(
        "lab-serve",
        [
            sys.executable,
            "-m",
            LAB_MODULE,
            "serve",
            "--directory",
            str(directory),
            "--seconds",
            str(seconds),
        ],
        environment(),
    )
    until = time.monotonic() + parent.remaining(240)
    while time.monotonic() < until:
        if child.poll() is not None:
            raise BackupFailure("M2_LAB_EXITED")
        lines = (parent.directory / "lab-serve.private.log").read_bytes().splitlines()
        for line in lines:
            if b'"readonly_key_file"' in line:
                ready = json.loads(line)
                if ready["readonly_key_file"] != str(directory / "runtime-auth.json") or ready[
                    "ca_file"
                ] != str(directory / "ca.crt"):
                    raise BackupFailure("M2_LAB_READY_BINDING")
                return directory
        time.sleep(0.2)
    raise BackupFailure("M2_LAB_READY_DEADLINE")


def full_action(parent: Scenario) -> None:
    r = parent.request
    directory = parent.directory
    # Both exact selectors must be available before any resource or business TTL begins.
    for phase in ("source", "restored"):
        env = environment(
            {
                "COMMERCEOPS_WEB_BATCH": "p5-m2-live",
                "COMMERCEOPS_B02_PRIVATE_DIR": str(directory / phase),
                "COMMERCEOPS_LIVE_WEB_URL": r["web_origin"],
            }
        )
        listed = parent.command(
            "list-" + phase,
            [*consumer_argv(phase), "--list", "--reporter=list"],
            cwd=ROOT / "frontend",
            env=env,
            cap=30,
        )
        selected_one(listed.decode(), phase)
    parent.command(
        "frontend-build",
        ["npm", "run", "build"],
        cwd=ROOT / "frontend",
        env=apps_environment(parent, "source"),
        cap=300,
    )
    source_id = parent.start_pg("source")
    child_command(parent, "source-init")
    parent.pg_initialized.add("source")
    lab = start_lab(parent)
    verify_lab_inputs(parent)
    verify_lab_probe(lab)
    parent.command(
        "woo-probe",
        [
            sys.executable,
            "-m",
            "scripts.woo_readonly_probe",
            "--config",
            str(lab / "probe-config.private.json"),
            "--expected",
            str(lab / "expected.private.json"),
            "--output",
            str(directory / "woo-probe.private.json"),
        ],
        cap=200,
    )
    probe = load(directory / "woo-probe.private.json")
    if probe.get("status") != "MATCHED" or not probe.get("complete"):
        raise BackupFailure("M2_POSITIVE_PROBE")
    child_command(parent, "bind-source")
    pids = start_apps(parent, "source")
    consume(parent, "source", handoff(parent, "source", pids))
    writers = stop_apps(parent, "source")
    child_command(parent, "source-pending")
    canonical = canonical_source(parent)
    parent.canonical_sha256 = reference(directory / "canonical/m2-facts.private.json")["sha256"]
    collect_stopped_facts(parent, "source")
    child_command(parent, "source-before")
    dump = directory / "source-dump.private.bin"
    fd = os.open(dump, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as output:
        parent.command(
            "pg-dump",
            [
                "docker",
                "exec",
                source_id,
                "pg_dump",
                "-U",
                "commerceops_owner",
                "-d",
                r["databases"]["source"]["database"],
                "--format=custom",
                "--no-owner",
            ],
            stdout=output,
            cap=90,
        )
        output.flush()
        os.fsync(output.fileno())
    if dump.stat().st_size == 0:
        raise BackupFailure("M2_DUMP_EMPTY")
    child_command(parent, "source-after")
    source_stop = parent.stop_pg("source")
    target_id = parent.start_pg("restored")
    child_command(parent, "target-empty")
    # Plain dump stream is private; no SQL or credentials enter argv/logs/public receipts.
    with dump.open("rb") as stream:
        parent.command(
            "pg-restore",
            [
                "docker",
                "exec",
                "-i",
                target_id,
                "pg_restore",
                "-U",
                "commerceops_owner",
                "-d",
                r["databases"]["restored"]["database"],
                "--exit-on-error",
                "--single-transaction",
                "--no-owner",
            ],
            stdin=stream,
            cap=90,
        )
    parent.pg_initialized.add("restored")
    child_command(parent, "restored-before")
    receipt = dict(
        schema_version="p5-m2-restore-receipt-v1",
        **{k: r[k] for k in ("run_id", "source_sha", "source_tree")},
        source_writers_reaped=True,
        source_pg_stopped=True,
        target_initially_empty=True,
        snapshot_identical=True,
        source_target_distinct=True,
        dump_sha256=reference(dump)["sha256"],
        dump_bytes=dump.stat().st_size,
        verified_at_utc=utc(),
    )
    save(directory / "restored/parent-restore.safe.json", receipt)
    for name in (
        "source-observed.private.json",
        "source-create-request.private.json",
        "source-create-receipt.private.json",
        "source-approval-read.private.json",
        "parent-source-pg.safe.json",
    ):
        copy_evidence(directory / "canonical" / name, directory / "restored" / name)
    restore = dict(
        source_writers_stopped_at_utc=writers["stopped_at_utc"],
        source_pg_stopped_at_utc=source_stop["stopped_at_utc"],
        target_verified_at_utc=receipt["verified_at_utc"],
        dump_sha256=receipt["dump_sha256"],
        schema_revision="0018_p5_commerce_sources",
        restore_receipt_ref=reference(directory / "restored/parent-restore.safe.json"),
    )
    pids = start_apps(parent, "restored")
    consume(
        parent, "restored", handoff(parent, "restored", pids, canonical=canonical, restore=restore)
    )
    stop_apps(parent, "restored")
    collect_stopped_facts(parent, "restored")
    child_command(parent, "restored-completed")
    parent.stop_pg("restored")
    negative_restores(parent, dump)


def lab_stop_classification(code: int | None, requested: bool, log: Path) -> str:
    if code == 0:
        return "normal_zero"
    if code == 1 and requested:
        try:
            footer = json.loads(private_bytes(log).splitlines()[-1])
        except (OSError, ValueError, IndexError):
            return "unexpected_exit"
        if footer == {"status": "failed", "category": "KeyboardInterrupt"}:
            return "expected_parent_requested_keyboard_interrupt"
    return "unexpected_exit"


def collect_stopped_facts(parent: Scenario, phase: str, *, cleanup: bool = False) -> None:
    """Bounded observation in the existing child, independent of resource cleanup."""
    if phase in parent.business_facts:
        return
    reason = None
    if phase not in parent.pg_initialized:
        reason = "not_initialized"
    elif parent.canonical_sha256 is None:
        reason = "no_trusted_canonical"
    elif phase not in parent.pg_started:
        reason = "database_already_stopped"
    elif any(name.startswith((phase + "-", "command-")) for name in parent.children):
        reason = "writers_not_confirmed_stopped"
    elif cleanup and parent.remaining(180, cleanup=True) < 75:
        reason = "cleanup_reserve"
    if reason is not None:
        parent.business_facts[phase] = dict(observation="not_run", reason=reason)
        if not cleanup:
            raise BackupFailure("M2_FACTS_NOT_CAPTURED")
        return
    parent.business_facts[phase] = dict(observation="unknown", reason="collection_failed")
    try:
        if (
            reference(parent.directory / "canonical/m2-facts.private.json")["sha256"]
            != parent.canonical_sha256
        ):
            raise BackupFailure("M2_CANONICAL_CHANGED")
        parent.command(
            phase + "-facts",
            [
                sys.executable,
                "-m",
                "scripts.m2_owned",
                "_child",
                "--directory",
                str(parent.directory),
                "--child-action",
                phase + "-facts",
            ],
            cap=15,
            cleanup=cleanup,
            env=environment({"M2_CANONICAL_SHA256": parent.canonical_sha256}),
        )
        path = parent.directory / (phase + "-business-facts.safe.json")
        parent.business_facts[phase] = dict(observation="captured", receipt=reference(path))
    except BaseException as error:
        parent.business_facts[phase]["category"] = type(error).__name__
        if not cleanup:
            raise


def cleanup(parent: Scenario) -> dict[str, Any]:
    parent.cleanup_expires = min(parent.expires, time.monotonic() + 180)
    errors = []
    apps = {}
    lab_receipt = None
    for phase in DATABASE_PHASES:
        if any(name.startswith(phase + "-") for name in parent.children):
            try:
                apps[phase] = stop_apps(
                    parent, phase, require_clean_worker=phase + "-worker" in parent.children
                )
            except BaseException as error:
                errors.append(dict(stage="stop-" + phase, category=type(error).__name__))
    # Retry reaping only already owned command processes, never rerun their action.
    for name, pending_child in tuple(parent.children.items()):
        if not name.startswith("command-"):
            continue
        try:
            if not parent.stop_child(pending_child, cleanup=True):
                raise BackupFailure("M2_COMMAND_REAP_UNCONFIRMED")
            del parent.children[name]
        except BaseException as error:
            errors.append(dict(stage="command-reap", category=type(error).__name__))
    for phase in DATABASE_PHASES:
        try:
            collect_stopped_facts(parent, phase, cleanup=True)
        except BaseException as error:
            parent.business_facts[phase] = dict(
                observation="unknown", category=type(error).__name__
            )
    for phase in tuple(parent.pg_started):
        try:
            parent.stop_pg(phase)
        except BaseException as error:
            errors.append(dict(stage="pg-stop-" + phase, category=type(error).__name__))
    if parent.lab_directory is not None:
        child = parent.children.get("lab-serve")
        requested = False
        exit_classification = "not_started"
        try:
            if child is not None:
                requested = child.poll() is None
                if requested:
                    os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=parent.remaining(90, cleanup=True))
                except subprocess.TimeoutExpired:
                    pass
                reaped = parent.stop_child(child, cleanup=True)
                if not reaped:
                    raise BackupFailure("M2_LAB_REAP_UNCONFIRMED")
                del parent.children["lab-serve"]
                exit_classification = lab_stop_classification(
                    child.returncode, requested, parent.directory / "lab-serve.private.log"
                )
                if exit_classification == "unexpected_exit":
                    errors.append(dict(stage="lab-exit", category="UNEXPECTED_NATIVE_EXIT"))
            # Successful serve cleanup is immutable evidence; verify it independently.
            # Only a missing receipt permits a bounded stop of the same owned project.
            if not (parent.lab_directory / "cleanup.safe.json").exists():
                verify_lab_inputs(parent)
                parent.command(
                    "lab-stop-fallback",
                    [
                        sys.executable,
                        "-m",
                        LAB_MODULE,
                        "stop",
                        "--directory",
                        str(parent.lab_directory),
                    ],
                    cap=90,
                    cleanup=True,
                )
            actual = load(parent.lab_directory / "cleanup.safe.json")
            if (
                actual.get("containers") != 0
                or actual.get("networks") != 0
                or actual.get("listener_absent") is not True
            ):
                raise BackupFailure("M2_LAB_CLEANUP_UNCONFIRMED")
            lab_config = load(parent.lab_directory / "lab.json")
            for args in (["ps", "-aq"], ["network", "ls", "-q"]):
                if parent.command(
                    "lab-independent-inventory",
                    [
                        "docker",
                        *args,
                        "--filter",
                        "label=com.docker.compose.project=" + parent.lab_directory.name,
                    ],
                    cap=10,
                    cleanup=True,
                ).strip():
                    raise BackupFailure("M2_LAB_CLEANUP_UNCONFIRMED")
            volumes = (
                parent.command(
                    "lab-independent-volumes",
                    [
                        "docker",
                        "volume",
                        "ls",
                        "-q",
                        "--filter",
                        "label=com.docker.compose.project=" + parent.lab_directory.name,
                    ],
                    cap=10,
                    cleanup=True,
                )
                .decode()
                .splitlines()
            )
            if sorted(volumes) != sorted(actual["volumes_retained"]):
                raise BackupFailure("M2_LAB_CLEANUP_UNCONFIRMED")
            with socket.socket() as sock:
                sock.settimeout(0.5)
                if sock.connect_ex(("127.0.0.1", lab_config["port"])) == 0:
                    raise BackupFailure("M2_LAB_CLEANUP_UNCONFIRMED")
            lab_receipt = dict(
                parent_requested_stop=requested,
                native_exit=None if child is None else child.returncode,
                exit_classification=exit_classification,
                actual_cleanup=actual,
            )
        except BaseException as error:
            errors.append(dict(stage="lab-cleanup", category=type(error).__name__))
    ports = []
    for origin in (parent.request["api_origin"], parent.request["web_origin"]):
        ports.append(int(origin.rsplit(":", 1)[1]))
    ports.extend(pg["port"] for pg in parent.request["databases"].values())
    listeners = {}
    for port in ports:
        with socket.socket() as sock:
            sock.settimeout(0.5)
            listeners[str(port)] = sock.connect_ex(("127.0.0.1", port)) == 0
    if any(listeners.values()) or parent.children or parent.pg_started:
        errors.append(dict(stage="final-inventory", category="RESOURCE_STOP_UNCONFIRMED"))
    result = dict(
        schema_version="p5-m2-cleanup-v1",
        finished_at_utc=utc(),
        errors=errors,
        apps=apps,
        postgres=parent.pg_stopped,
        business_facts=parent.business_facts,
        lab=lab_receipt,
        listeners=listeners,
        stopping_confirmed=not errors,
    )
    save(parent.directory / "cleanup.safe.json", result)
    return result


def run(directory: Path) -> int:
    parent = open_run(directory)
    primary = None

    def timeout_signal(*_: Any) -> None:
        raise BackupFailure("M2_DEADLINE")

    previous = signal.signal(signal.SIGALRM, timeout_signal)
    signal.setitimer(signal.ITIMER_REAL, parent.remaining(3600))
    try:
        full_action(parent)
    except BaseException as error:
        primary = dict(
            category=type(error).__name__,
            code=str(error) if isinstance(error, BackupFailure) else None,
        )
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    try:
        signal.setitimer(signal.ITIMER_REAL, parent.remaining(180, cleanup=True))
        stopped = cleanup(parent)
    except BaseException as error:
        stopped = dict(stopping_confirmed=False, category=type(error).__name__)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    passed = primary is None and stopped.get("stopping_confirmed") is True
    save(
        directory / "result.safe.json",
        dict(
            schema_version="p5-m2-owned-result-v1",
            **{k: parent.request[k] for k in ("run_id", "source_sha", "source_tree")},
            logical_result="passed" if passed else "failed",
            primary=primary,
            cleanup_confirmed=stopped.get("stopping_confirmed") is True,
            gate_scope="positive-source-original-pending-restore-revoked-and-expired-clones",
            finished_at_utc=utc(),
        ),
    )
    return 0 if passed else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "_child"))
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--deadline")
    parser.add_argument("--anchor-day")
    parser.add_argument("--child-action")
    args = parser.parse_args()
    os.umask(0o077)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        if args.action == "prepare":
            if (
                args.directory is not None
                or args.deadline is None
                or args.anchor_day is None
                or args.child_action is not None
            ):
                raise BackupFailure("M2_PREPARE_ARGUMENTS")
            print(prepare_run(args.deadline, args.anchor_day))
        else:
            if args.directory is None or args.deadline is not None or args.anchor_day is not None:
                raise BackupFailure("M2_RUN_ARGUMENTS")
            if args.action == "run":
                if args.child_action is not None:
                    raise BackupFailure("M2_RUN_ARGUMENTS")
                raise SystemExit(run(args.directory))
            if args.child_action is None:
                raise BackupFailure("M2_CHILD_ACTION")
            run_child(args.directory, args.child_action)
    except (Exception, KeyboardInterrupt) as error:
        print(
            json.dumps(
                dict(
                    status="failed",
                    category=type(error).__name__,
                    code=str(error) if isinstance(error, BackupFailure) else None,
                )
            )
        )
        raise SystemExit(1) from None


def negative_child(directory: Path, request: dict[str, Any], action: str) -> None:
    """Only predeclared fresh clones. Revoke a grant as a negative fixture, never repair data."""
    import httpx
    from commerceops.application.replenishment.contracts import DecisionInput
    from commerceops.application.replenishment.security import digest as nonce_digest
    from commerceops.infrastructure.database import connect

    phase = action.split("-", 1)[0]
    if phase not in ("revoked", "expired"):
        raise BackupFailure("M2_NEGATIVE_PHASE")
    if action.endswith("-decision"):
        save(
            directory / (phase + "-http-preflight.safe.json"),
            dict(
                schema_version="p5-m2-negative-http-observation-v1",
                phase=phase,
                step="preflight",
                http_status=None,
                transport="not_run",
                structure="not_received",
                known_error_code=None,
                not_run_steps=["csrf", "login", "session", "decision", "stopped_collection"],
                success_asserted=False,
            ),
        )
    owner = database(directory, request, phase)
    canonical = load(directory / "canonical/m2-facts.private.json")["canonical_source"]
    seed_data = load(directory / "seed.private.json")
    account = seed_data["accounts"]["approver"]
    common = {k: request[k] for k in ("run_id", "source_sha", "source_tree")}
    with connect(owner) as db:
        row = db.execute(
            "SELECT id,status,expires_at,nonce_hash,clock_timestamp() AS now "
            "FROM business.approvals WHERE id=%s AND task_id=%s",
            (UUID(canonical["approval_id"]), UUID(canonical["task_id"])),
        ).fetchone()
        if (
            row is None
            or row["status"] != "pending"
            or row["expires_at"] != datetime.fromisoformat(canonical["expires_at"])
        ):
            raise BackupFailure("M2_NEGATIVE_ORIGINAL_BINDING")
        if action == "expired-clock":
            save(
                directory / "expired-clock.safe.json",
                dict(
                    schema_version="p5-m2-expiry-clock-v1",
                    **common,
                    remaining_seconds=max(0, (row["expires_at"] - row["now"]).total_seconds()),
                    observed_at_utc=row["now"].isoformat(),
                ),
            )
            return
        if action == "revoked-fixture":
            if (row["expires_at"] - row["now"]).total_seconds() < 60:
                raise BackupFailure("M2_REVOCATION_EXPIRY_MARGIN")
            changed = db.execute(
                "UPDATE business.principal_role_shop_grants SET enabled=false "
                "WHERE principal_id=%s AND organization_id=%s AND shop_id=%s "
                "AND role='approver' AND enabled RETURNING principal_id",
                (
                    UUID(account["expected_principal_id"]),
                    UUID(canonical["organization_id"]),
                    UUID(canonical["shop_id"]),
                ),
            ).fetchall()
            if len(changed) != 1:
                raise BackupFailure("M2_REVOCATION_FIXTURE")
            return
        if phase == "expired" and row["now"] <= row["expires_at"]:
            raise BackupFailure("M2_NOT_ACTUALLY_EXPIRED")
        raw = private_bytes(directory / "restored/restored-decision-request.private.json")
        DecisionInput.model_validate_json(raw)
        body = json.loads(raw)
        observed = load(directory / "restored/restored-observed.private.json")
        if (
            body["action"] != "approve_with_assumptions"
            or set(body["acknowledged_assumption_keys"])
            != set(canonical["required_assumption_keys"])
            or body["request_key"] != observed["decision_request_key"]
            or body["approval_id"] != canonical["approval_id"]
            or body["plan_id"] != canonical["plan_id"]
            or body["plan_hash"] != canonical["plan_hash"]
            or body["plan_version"] != canonical["plan_version"]
            or nonce_digest(body["nonce"]) != row["nonce_hash"]
        ):
            raise BackupFailure("M2_NEGATIVE_ORIGINAL_REQUEST")
    if phase == "revoked" and row["now"] >= row["expires_at"]:
        raise BackupFailure("M2_REVOCATION_EXPIRY_CONFOUNDED")
    expected_status, expected_code = (
        (403, "ACCESS_DENIED") if phase == "revoked" else (410, "APPROVAL_EXPIRED")
    )
    if action.endswith("-decision"):
        steps = ("csrf", "login", "session", "decision", "stopped_collection")
        known_codes = {
            "ACCESS_DENIED",
            "APPROVAL_EXPIRED",
            "CSRF_INVALID",
            "SESSION_INVALID",
            "IDENTITY_DENIED",
            "LOGIN_FAILED",
            "ORIGIN_DENIED",
            "RESOURCE_NOT_FOUND",
            "INVALID_REQUEST",
            "INVALID_JSON",
            "SERVICE_UNAVAILABLE",
            "RATE_LIMITED",
            "APPROVAL_SUPERSEDED",
            "UNSUPPORTED_MEDIA_TYPE",
        }

        def observed_http(step: str, send: Any) -> tuple[int | None, Any, dict[str, Any]]:
            status = None
            value = None
            shape = "not_received"
            transport = "received"
            code = None
            try:
                response = send()
                status = response.status_code
                if (
                    not response.headers.get("content-type", "")
                    .lower()
                    .startswith("application/json")
                ):
                    shape = "non_json"
                elif len(response.content) > 65536:
                    shape = "oversized"
                else:
                    try:
                        value = response.json()
                        shape = "json_object" if isinstance(value, dict) else "json_other"
                    except (ValueError, RecursionError):
                        shape = "invalid_json"
            except httpx.TimeoutException:
                transport = "timeout"
            except httpx.HTTPError:
                transport = "transport_error"
            if isinstance(value, dict) and isinstance(value.get("error"), dict):
                error = value["error"]
                candidate = error.get("code")
                code = (
                    candidate if isinstance(candidate, str) and candidate in known_codes else None
                )
                shape = "error_invalid_shape"
                if (
                    set(value) == {"schema_version", "server_time", "trace_id", "error"}
                    and value["schema_version"] == "p3-web-v1"
                    and isinstance(value["trace_id"], str)
                    and (value["server_time"] is None or isinstance(value["server_time"], str))
                    and set(error) == {"code", "safe_message", "retryable", "receipt"}
                    and isinstance(error["safe_message"], str)
                    and error["retryable"] is False
                    and error["receipt"] is None
                    and code is not None
                ):
                    shape = "known_error_envelope"
            principal = value.get("principal") if isinstance(value, dict) else None
            identity_matches = (
                isinstance(value, dict)
                and isinstance(principal, dict)
                and value.get("schema_version") == "p3-web-v1"
                and value.get("identity_mode") == "session"
                and principal.get("principal_id") == account["expected_principal_id"]
                and principal.get("organization_id") == canonical["organization_id"]
            )
            token = value.get("csrf_token") if isinstance(value, dict) else None
            csrf_valid = (
                isinstance(token, str) and re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is not None
            )
            receipt = dict(
                schema_version="p5-m2-negative-http-observation-v1",
                phase=phase,
                step=step,
                http_status=status,
                transport=transport,
                structure=shape,
                known_error_code=code,
                identity_matches=identity_matches,
                csrf_shape_valid=csrf_valid,
                not_run_steps=list(steps[steps.index(step) + 1 :]),
                success_asserted=False,
            )
            # Immutable safe facts before every status/body/identity assertion; no raw data.
            save(directory / (phase + "-http-" + step + ".safe.json"), receipt)
            return status, value, receipt

        origin = request["api_origin"]
        with httpx.Client(
            base_url=origin, timeout=5, trust_env=False, follow_redirects=False
        ) as client:
            status, csrf, evidence = observed_http("csrf", lambda: client.get("/api/v1/auth/csrf"))
            if (
                status != 200
                or not evidence["csrf_shape_valid"]
                or csrf.get("schema_version") != "p3-web-v1"
                or csrf.get("identity_mode") != "anonymous_bootstrap"
            ):
                raise BackupFailure("M2_NEGATIVE_AUTH")
            status, _, evidence = observed_http(
                "login",
                lambda: client.post(
                    "/api/v1/auth/login",
                    headers={"Origin": request["web_origin"], "X-CSRF-Token": csrf["csrf_token"]},
                    json=dict(
                        schema_version="p3-web-v1",
                        login=account["login"],
                        password=account["password"],
                    ),
                ),
            )
            if (
                status != 200
                or not evidence["identity_matches"]
                or not evidence["csrf_shape_valid"]
            ):
                raise BackupFailure("M2_NEGATIVE_AUTH")
            status, session, evidence = observed_http(
                "session", lambda: client.get("/api/v1/auth/session")
            )
            if (
                status != 200
                or not evidence["identity_matches"]
                or not evidence["csrf_shape_valid"]
            ):
                raise BackupFailure("M2_NEGATIVE_AUTH")
            # Exactly one original POST; timeout/unknown remains spent, without retry or lookup.
            status, _, evidence = observed_http(
                "decision",
                lambda: client.post(
                    f"/api/v1/approvals/{canonical['approval_id']}/decision",
                    content=raw,
                    headers={
                        "Origin": request["web_origin"],
                        "X-CSRF-Token": session["csrf_token"],
                        "Content-Type": "application/json",
                    },
                ),
            )
            if (
                status != expected_status
                or evidence["known_error_code"] != expected_code
                or evidence["structure"] != "known_error_envelope"
            ):
                raise BackupFailure("M2_NEGATIVE_DECISION_NOT_REJECTED")
    with connect(database(directory, request, phase, app=True)) as db:
        if action.endswith("-collect"):
            from scripts.m2_backup import no_other_clients

            no_other_clients(db)
            prior = load(directory / (phase + "-decision.safe.json"))
            if prior["http_status"] != expected_status or prior["error_code"] != expected_code:
                raise BackupFailure("M2_NEGATIVE_DECISION_RECEIPT")
        for table in ("executions", "replenishment_items", "approval_resumes"):
            from psycopg import sql

            count = db.execute(
                sql.SQL("SELECT count(*) AS n FROM business.{} WHERE task_id=%s").format(
                    sql.Identifier(table)
                ),
                (UUID(canonical["task_id"]),),
            ).fetchone()
            if count != {"n": 0}:
                raise BackupFailure("M2_NEGATIVE_BUSINESS_WRITE")
        count = db.execute(
            "SELECT count(*) AS n FROM business.web_requests "
            "WHERE task_id=%s AND operation='decision'",
            (UUID(canonical["task_id"]),),
        ).fetchone()
        if count != {"n": 0}:
            raise BackupFailure("M2_NEGATIVE_BUSINESS_WRITE")
        actual = db.execute(
            "SELECT expires_at,nonce_hash,clock_timestamp() AS now "
            "FROM business.approvals WHERE id=%s",
            (UUID(canonical["approval_id"]),),
        ).fetchone()
        if (
            actual is None
            or actual["expires_at"] != row["expires_at"]
            or actual["nonce_hash"] != row["nonce_hash"]
        ):
            raise BackupFailure("M2_NEGATIVE_ORIGINAL_BINDING")
        if phase == "revoked" and actual["now"] >= actual["expires_at"]:
            raise BackupFailure("M2_REVOCATION_EXPIRY_CONFOUNDED")
        if phase == "expired" and actual["now"] <= actual["expires_at"]:
            raise BackupFailure("M2_NOT_ACTUALLY_EXPIRED")
    save(
        directory / (action + ".safe.json"),
        dict(
            schema_version="p5-m2-negative-decision-v1",
            **common,
            phase=phase,
            writers_stopped=action.endswith("-collect"),
            http_status=expected_status,
            error_code=expected_code,
            original_request_preserved=True,
            original_expiry_preserved=True,
            original_nonce_preserved=True,
            execution_count=0,
            item_count=0,
            decision_receipt_count=0,
            observed_db_utc=actual["now"].isoformat(),
        ),
    )


def negative_restores(parent: Scenario, dump: Path) -> None:
    """Each rejection uses a separate registered empty volume; never mutates the positive target."""
    import httpx

    for phase in ("revoked", "expired"):
        identifier = parent.start_pg(phase)
        child_command(parent, phase + "-empty")
        with dump.open("rb") as stream:
            parent.command(
                "pg-restore-" + phase,
                [
                    "docker",
                    "exec",
                    "-i",
                    identifier,
                    "pg_restore",
                    "-U",
                    "commerceops_owner",
                    "-d",
                    parent.request["databases"][phase]["database"],
                    "--exit-on-error",
                    "--single-transaction",
                    "--no-owner",
                ],
                stdin=stream,
                cap=90,
            )
        parent.pg_initialized.add(phase)
        child_command(parent, phase + "-before")
        if phase == "revoked":
            child_command(parent, "revoked-fixture")
        else:
            child_command(parent, "expired-clock")
            delay = load(parent.directory / "expired-clock.safe.json")["remaining_seconds"] + 1
            if parent.remaining(3600) < delay + 90:
                raise BackupFailure("M2_EXPIRY_WAIT_CAPACITY")
            until = time.monotonic() + delay
            while time.monotonic() < until:
                time.sleep(min(5, until - time.monotonic()))
        child = parent.spawn(
            phase + "-api",
            [sys.executable, "-m", "commerceops.entrypoints.api"],
            apps_environment(parent, phase),
        )
        until = time.monotonic() + parent.remaining(30)
        while time.monotonic() < until:
            if child.poll() is not None:
                raise BackupFailure("M2_NEGATIVE_API_EXITED")
            try:
                with httpx.Client(timeout=1, trust_env=False, follow_redirects=False) as client:
                    if client.get(parent.request["api_origin"] + "/health/live").status_code == 200:
                        break
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        else:
            raise BackupFailure("M2_NEGATIVE_API_READY")
        child_command(parent, phase + "-decision")
        stop_apps(parent, phase, require_clean_worker=False)
        collect_stopped_facts(parent, phase)
        child_command(parent, phase + "-collect")
        parent.stop_pg(phase)


if __name__ == "__main__":
    main()
