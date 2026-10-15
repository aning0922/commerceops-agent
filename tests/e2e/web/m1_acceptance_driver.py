"""M1 stage consumer for the shared p4_acceptance entry, never a second launcher.

Only fixed acceptance stages and owned-resource cleanup live here. Business
bootstrap, native authority/once coordination and source binding belong to the
shared entry. No product state is patched by this consumer.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tests.e2e.web.m1_acceptance_capture import (
    CASE_COUNTS,
    CaptureContext,
    CaptureFailure,
    checkpoint_fingerprint,
    immutable_business,
    rows,
    validate_base_readback,
    validate_business,
    validate_worker,
    verify_t6_association,
    verify_t6_outbox,
)

STAGES = (
    "source",
    "resources",
    "schema",
    "base_v1",
    "before_t6",
    "arm_t6",
    "ui_submit",
    "original_get",
    "after_t6",
    "base_v2",
    "normal_stop",
    "restart",
    "page_read",
    "post_restart",
    "replay",
    "final_worker",
    "cleanup",
)
ENV_KEYS = frozenset(
    {
        "PATH",
        "HOME",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "PYTHONPATH",
        "PYTHONNOUSERSITE",
        "LANGSMITH_TRACING",
        "NEXT_TELEMETRY_DISABLED",
        "COMPOSE_PROJECT_NAME",
        "COMMERCEOPS_PG_RUNTIME_DIR",
        "COMMERCEOPS_DEMO_PRIVATE_DIR",
        "COMMERCEOPS_DEMO_UID",
        "COMMERCEOPS_DEMO_GID",
        "COMMERCEOPS_DEMO_API_PORT",
        "COMMERCEOPS_DEMO_WEB_PORT",
    }
)
ZERO_REAL_COUNTERS = (
    "real_sdk_client_starts",
    "real_ws_starts",
    "platform_http_egress",
    "appsecret_reads",
    "real_environment_reads",
    "provider_calls",
    "original_manual_consumptions",
)
NATIVE_COUNTERS = ("native_factory_invocations", "native_ledger_rows", "fake_transport_calls")


class StageFailure(Exception):
    def __init__(
        self,
        stage: str,
        code: str,
        *,
        query_id: str | None = None,
        sqlstate: str | None = None,
        dto: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(code)
        self.stage, self.code, self.query_id = stage, code, query_id
        self.sqlstate, self.dto = sqlstate, dto


def safe_dto_errors(errors: Any) -> list[dict[str, Any]] | None:
    if not isinstance(errors, list):
        return None
    result = []
    for row in errors[:8]:
        if not isinstance(row, dict) or not isinstance(row.get("loc"), (list, tuple)):
            continue
        result.append(
            {
                "loc": [
                    v
                    if type(v) is int and 0 <= v <= 1000
                    else v
                    if isinstance(v, str) and re.fullmatch(r"[a-z_]{1,40}", v)
                    else "_field"
                    for v in row["loc"][:8]
                ],
                "type": row["type"]
                if isinstance(row.get("type"), str) and re.fullmatch(r"[a-z_]{1,50}", row["type"])
                else "validation_error",
            }
        )
    return result


def safe_failure(error: Exception, stage: str) -> dict[str, Any]:
    """Do not serialize str(error), input, context, URLs, SQL or arbitrary attributes."""
    value: dict[str, Any] = {
        "stage": stage,
        "code": "UNEXPECTED_FAILURE",
        "query_id": None,
        "sqlstate": None,
        "dto": None,
    }
    if isinstance(error, CaptureFailure):
        value.update(error.safe())
    elif isinstance(error, StageFailure):
        for key in ("code", "query_id", "sqlstate"):
            field_value = getattr(error, key)
            pattern = r"[0-9A-Z]{5}" if key == "sqlstate" else r"[A-Z0-9_]{1,64}"
            if field_value is None or (
                isinstance(field_value, str) and re.fullmatch(pattern, field_value)
            ):
                value[key] = field_value
        value["dto"] = safe_dto_errors(error.dto)
    elif isinstance(error, subprocess.TimeoutExpired) or isinstance(error, TimeoutError):
        value["code"] = "COMMAND_TIMEOUT"
    elif isinstance(error, OSError):
        value.update(code="OS_ERROR", errno=error.errno if type(error.errno) is int else None)
    elif isinstance(error, ImportError):
        value["code"] = "MODULE_LOAD_FAILED"
    elif isinstance(error, TypeError):
        value["code"] = "CALL_FAILED"
    elif type(error).__name__ == "ValidationError":
        value["code"] = "DTO_INVALID"
        try:
            # Native Pydantic validation; only field locations/types, no input or context.
            errors = error.errors(include_url=False, include_context=False, include_input=False)  # type: ignore[attr-defined]
            value["dto"] = safe_dto_errors(errors)
        except Exception:
            value["dto"] = None
    return value


@dataclass(frozen=True)
class CleanupPlan:
    project: str
    expected_volume: str
    compose: tuple[str, ...]
    docker: tuple[str, ...]
    cwd: Path
    environment: Mapping[str, str]
    labels: Mapping[str, str]
    ports: tuple[int, int]
    services: tuple[str, str, str] = ("m1-worker", "m1-api", "m1-web")
    postgres_service: str = "postgres"

    def validate(self) -> None:
        if (
            not re.fullmatch(r"[a-z][a-z0-9-]{9,63}", self.project)
            or self.labels.get("com.docker.compose.project") != self.project
            or len(self.labels) < 2
            or self.expected_volume != self.project + "_pg_data"
            or "-p" not in self.compose
            or self.compose[self.compose.index("-p") + 1] != self.project
            or any(
                not re.fullmatch(r"[a-z0-9_-]{1,40}", s)
                for s in (*self.services, self.postgres_service)
            )
        ):
            raise StageFailure("cleanup", "RESOURCE_SCOPE_INVALID")


def write_private_json(path: Path, value: Any) -> None:
    """Atomic private result; never follow an existing result symlink."""
    directory = path.parent
    if (
        directory.is_symlink()
        or directory.stat().st_uid != os.getuid()
        or directory.stat().st_mode & 0o777 != 0o700
        or path.is_symlink()
    ):
        raise StageFailure("cleanup", "UNSAFE_RESULT_PATH")
    descriptor, name = tempfile.mkstemp(prefix=".m1-result-", dir=directory)
    temporary = Path(name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass
class Ledger:
    directory: Path
    run_id: str
    source_sha: str
    source_tree: str
    manifest_sha256: str
    stages: dict[str, dict[str, Any]] = field(init=False)
    failures: list[dict[str, Any]] = field(default_factory=list)
    finalized: bool = False

    def __post_init__(self) -> None:
        if (
            not re.fullmatch(r"[a-z0-9-]{10,80}", self.run_id)
            or not re.fullmatch(r"[a-f0-9]{40}", self.source_sha)
            or not re.fullmatch(r"[a-f0-9]{40}", self.source_tree)
            or not re.fullmatch(r"[a-f0-9]{64}", self.manifest_sha256)
        ):
            raise StageFailure("source", "REGISTRATION_INVALID")
        self.stages = {name: {"status": "NOT_RUN", "evidence": None} for name in STAGES}

    def enter(self, stage: str) -> None:
        if (
            self.finalized
            or stage not in self.stages
            or self.stages[stage]["status"] != "NOT_RUN"
            or any(s["status"] == "ENTERED" for s in self.stages.values())
        ):
            raise StageFailure("cleanup", "STAGE_TRANSITION_INVALID")
        self.stages[stage] = {"status": "ENTERED", "evidence": None}
        self.progress()

    def record(self, stage: str, evidence: str) -> None:
        if self.finalized or stage not in self.stages or self.stages[stage]["status"] != "ENTERED":
            raise StageFailure("cleanup", "STAGE_TRANSITION_INVALID")
        reference = Path(evidence)
        if (
            reference.is_absolute()
            or ".." in reference.parts
            or reference.suffix not in (".json", ".png")
        ):
            raise StageFailure(stage, "EVIDENCE_REFERENCE_INVALID")
        actual = self.directory / reference
        if not actual.is_file() or actual.is_symlink() or actual.stat().st_mode & 0o777 != 0o600:
            raise StageFailure(stage, "EVIDENCE_REFERENCE_INVALID")
        self.stages[stage] = {"status": "PASSED", "evidence": evidence}
        self.progress()

    def fail(self, stage: str, error: Exception) -> None:
        diagnostic = safe_failure(error, stage)
        self.failures.append(diagnostic)
        if stage in self.stages:
            self.stages[stage] = {"status": "FAILED", "evidence": None}
        self.progress()

    def payload(self, status: str) -> dict[str, Any]:
        return {
            "schema_version": "p4-m1-stage-result-v1",
            "run_id": self.run_id,
            "source_sha": self.source_sha,
            "source_tree": self.source_tree,
            "manifest_sha256": self.manifest_sha256,
            "status": status,
            "business_pass": status == "PASSED",
            "stages": self.stages,
            "scope": "C stage evidence only",
            "whole_candidate_pass": False,
            "failures": self.failures,
            "real_platform_pass": False,
            "real_platform_frames": "R0-R5 NOT_CAPTURED",
        }

    def progress(self) -> None:
        write_private_json(self.directory / "stages.in-progress.json", self.payload("RUNNING"))

    def finish(self, cleanup: CleanupResult) -> int:
        if self.finalized:
            raise StageFailure("cleanup", "RESULT_ALREADY_FINAL")
        if not cleanup.success:
            self.failures.append(
                {
                    "stage": "cleanup",
                    "code": "CLEANUP_INCOMPLETE",
                    "query_id": None,
                    "sqlstate": None,
                    "dto": None,
                }
            )
            self.stages["cleanup"] = {"status": "FAILED", "evidence": "cleanup.json"}
        else:
            write_private_json(self.directory / "cleanup.json", cleanup.safe())
            self.stages["cleanup"] = {"status": "PASSED", "evidence": "cleanup.json"}
        passed = not self.failures and all(s["status"] == "PASSED" for s in self.stages.values())
        result = self.payload("PASSED" if passed else "FAILED")
        result["cleanup"] = cleanup.safe()
        result["exit_code"] = 0 if passed else 1
        result["finalized_at_utc"] = datetime.now(UTC).isoformat()
        write_private_json(self.directory / "result.json", result)
        self.finalized = True
        return 0 if passed else 1


@dataclass(frozen=True)
class CommandResult:
    code: int | None
    stdout: str = ""
    error_code: str | None = None
    errno: int | None = None
    diagnostic: dict[str, Any] | None = None

    def safe(self, stage: str) -> dict[str, Any]:
        return {
            "stage": stage,
            "exit_code": self.code,
            "error_code": self.error_code,
            "errno": self.errno,
        }


def controlled_environment(extra: Mapping[str, str]) -> dict[str, str]:
    if set(extra) - ENV_KEYS:
        raise StageFailure("source", "ENVIRONMENT_KEY_REJECTED")
    # Select keys before looking up values; never iterate/record app-secret environment.
    result = {
        k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL") if k in os.environ
    }
    result.update(extra)
    result["LANGSMITH_TRACING"] = "false"
    result["NEXT_TELEMETRY_DISABLED"] = "1"
    result["PYTHONNOUSERSITE"] = "1"
    return result


def command(
    argv: Sequence[str], *, cwd: Path, env: Mapping[str, str], timeout: float
) -> CommandResult:
    if timeout <= 0:
        return CommandResult(None, error_code="DEADLINE_REACHED")
    try:
        result = subprocess.run(
            list(argv),
            cwd=cwd,
            env=dict(env),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return CommandResult(result.returncode, result.stdout)
    except subprocess.TimeoutExpired:
        return CommandResult(None, error_code="COMMAND_TIMEOUT")
    except OSError as error:
        return CommandResult(None, error_code="OS_ERROR", errno=error.errno)


def ui_command(
    argv: Sequence[str], *, cwd: Path, env: Mapping[str, str], timeout: float
) -> CommandResult:
    """Own the new UI process group, including its children on timeout/failed exit."""
    if timeout <= 0:
        return CommandResult(None, error_code="DEADLINE_REACHED")
    try:
        child = subprocess.Popen(
            list(argv),
            cwd=cwd,
            env=dict(env),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except OSError as error:
        return CommandResult(None, error_code="OS_ERROR", errno=error.errno)
    failure = None
    stdout, stderr = "", ""
    try:
        stdout, stderr = child.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        failure = "COMMAND_TIMEOUT"
    finally:
        # This PID was allocated above with a new session; never accept a caller PID.
        try:
            os.killpg(child.pid, 0)
            failure = failure or "UI_DESCENDANTS_REMAIN"
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError:
            failure = failure or "UI_PROCESS_CLEANUP_FAILED"
        try:
            child.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            failure = failure or "UI_PROCESS_CLEANUP_FAILED"
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            failure = failure or "UI_PROCESS_CLEANUP_FAILED"
        try:
            child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            failure = failure or "UI_PROCESS_CLEANUP_FAILED"
    diagnostic = None
    if child.returncode and not failure:
        try:
            value = json.loads(stderr)
            if value.get("status") == "FAILED" and re.fullmatch(r"[A-Z_]{1,64}", value["code"]):
                diagnostic = {"code": value["code"], "dto": safe_dto_errors(value.get("dto"))}
        except (ValueError, TypeError, KeyError, AttributeError):
            diagnostic = None
    return CommandResult(
        None if failure else child.returncode, stdout, failure, diagnostic=diagnostic
    )


@dataclass
class CleanupResult:
    commands: list[dict[str, Any]] = field(default_factory=list)
    worker_confirmed: bool | None = None
    processes_reaped: bool | None = None
    pg_running: bool | None = None
    pg_pid: int | None = None
    containers: list[str] | None = None
    networks: list[str] | None = None
    volumes: list[str] | None = None
    listeners: dict[str, bool | None] = field(default_factory=dict)
    expected_volume: str = ""
    down_attempted: bool = False
    down_completed_no_v: bool | None = None

    @property
    def success(self) -> bool:
        return (
            bool(self.commands)
            and all(c["exit_code"] == 0 for c in self.commands)
            and self.worker_confirmed is True
            and self.processes_reaped is True
            and self.pg_running is False
            and type(self.pg_pid) is int
            and self.pg_pid == 0
            and self.containers == []
            and self.networks == []
            and self.volumes == [self.expected_volume]
            and bool(self.listeners)
            and all(v is False for v in self.listeners.values())
            and self.down_completed_no_v is True
        )

    def safe(self) -> dict[str, Any]:
        return {
            "commands": self.commands,
            "worker_confirmed": self.worker_confirmed,
            "processes_reaped": self.processes_reaped,
            "pg_running": self.pg_running,
            "pg_pid": self.pg_pid,
            "containers_remaining": self.containers,
            "networks_remaining": self.networks,
            "retained_volumes": self.volumes,
            "listeners": self.listeners,
            "expected_volume": self.expected_volume,
            "down_attempted": self.down_attempted,
            "down_completed_no_v": self.down_completed_no_v,
            "complete": self.success,
        }


def reap_owned_processes(children: Sequence[subprocess.Popen[bytes]], deadline: float) -> bool:
    clean = True
    for child in children:
        if child.poll() is None:
            try:
                if os.getpgid(child.pid) != child.pid:
                    clean = False
                    continue
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except OSError:
                clean = False
    for child in children:
        try:
            child.wait(timeout=max(0.01, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            clean = False
            try:
                if os.getpgid(child.pid) == child.pid:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                pass
        except OSError:
            clean = False
        clean &= child.poll() is not None
    return clean


def validate_transport_counters(value: Mapping[str, Any]) -> None:
    if any(type(value.get(k)) is not int or value[k] != 0 for k in ZERO_REAL_COUNTERS) or any(
        type(value.get(k)) is not int or value[k] < 0 for k in NATIVE_COUNTERS
    ):
        raise StageFailure("base_v1", "TRANSPORT_COUNTERS_INVALID")


def verify_container(
    actual: Mapping[str, Any], *, image_id: str, labels: Mapping[str, str], no_host_ports: bool
) -> None:
    if actual.get("Image") != image_id:
        raise StageFailure("resources", "CONTAINER_IMAGE_MISMATCH")
    config, network = actual.get("Config"), actual.get("NetworkSettings")
    if not isinstance(config, Mapping) or not isinstance(network, Mapping):
        raise StageFailure("resources", "CONTAINER_SHAPE_INVALID")
    observed = config.get("Labels")
    if not isinstance(observed, Mapping):
        raise StageFailure("resources", "CONTAINER_SHAPE_INVALID")
    if any(observed.get(k) != v for k, v in labels.items()):
        raise StageFailure("resources", "CONTAINER_LABEL_MISMATCH")
    bindings = network.get("Ports")
    if not isinstance(bindings, Mapping) or any(
        entries is not None
        and (not isinstance(entries, list) or any(not isinstance(p, Mapping) for p in entries))
        for entries in bindings.values()
    ):
        raise StageFailure("resources", "CONTAINER_SHAPE_INVALID")
    published = [p for entries in bindings.values() if entries for p in entries]
    if (no_host_ports and published) or any(p.get("HostIp") != "127.0.0.1" for p in published):
        raise StageFailure("resources", "CONTAINER_PORT_MISMATCH")


def listener_open(port: int) -> bool | None:
    if type(port) is not int or not 1024 <= port <= 65535:
        return None
    try:
        with socket.socket() as stream:
            stream.settimeout(0.5)
            result = stream.connect_ex(("127.0.0.1", port))
        if result == 0:
            return True
        # A timeout or network error is not proof of a stopped listener.
        import errno

        return False if result == errno.ECONNREFUSED else None
    except OSError:
        return None


def cleanup_owned(
    plan: CleanupPlan,
    audit_current_worker: Callable[[], bool],
    *,
    children: Sequence[subprocess.Popen[bytes]] = (),
    deadline_monotonic: float,
    execute: Callable[..., CommandResult] = command,
) -> CleanupResult:
    """Fixed best-effort cleanup; business snapshot is deliberately not an argument.

    Any failed probe remains unknown. An unexpected owner label prevents project
    stop/down, rather than touching a foreign container under a colliding name.
    """
    plan.validate()
    result = CleanupResult(expected_volume=plan.expected_volume)

    def call(stage: str, argv: Sequence[str], limit: float = 20) -> CommandResult:
        try:
            out = execute(
                argv,
                cwd=plan.cwd,
                env=plan.environment,
                timeout=min(limit, max(0, deadline_monotonic - time.monotonic())),
            )
        except OSError as error:
            out = CommandResult(None, error_code="OS_ERROR", errno=error.errno)
        except Exception:
            out = CommandResult(None, error_code="CLEANUP_COMMAND_FAILED")
        result.commands.append(out.safe(stage))
        return out

    def ids(stage: str, kind: str) -> list[str] | None:
        argv = (
            (*plan.docker, "ps", "-a", "-q")
            if kind == "container"
            else (*plan.docker, kind, "ls", "-q")
        )
        out = call(stage, (*argv, "--filter", "label=com.docker.compose.project=" + plan.project))
        if out.code != 0:
            return None
        values = out.stdout.splitlines()
        if any(not re.fullmatch(r"[a-zA-Z0-9_.-]{1,128}", x) for x in values):
            result.commands.append(
                CommandResult(None, error_code="RETURN_SHAPE_INVALID").safe(stage)
            )
            return None
        return sorted(values)

    before = ids("cleanup_scope", "container")
    scope_ok = before is not None
    pg_ids: list[str] = []
    for cid in before or []:
        out = call("cleanup_scope_inspect", (*plan.docker, "inspect", cid))
        try:
            objects = json.loads(out.stdout) if out.code == 0 else []
            if len(objects) != 1:
                raise ValueError
            labels = objects[0]["Config"]["Labels"]
            if any(labels.get(k) != v for k, v in plan.labels.items()):
                raise ValueError
            if labels.get("com.docker.compose.service") == plan.postgres_service:
                pg_ids.append(cid)
        except (ValueError, KeyError, TypeError):
            scope_ok = False
            result.commands.append(
                CommandResult(None, error_code="OWNERSHIP_UNPROVED").safe("cleanup_scope")
            )
    if scope_ok:
        call("cleanup_stop_apps", (*plan.compose, "stop", "--timeout", "30", *plan.services), 40)
    if scope_ok and len(pg_ids) == 1:
        try:
            result.worker_confirmed = audit_current_worker()
            if result.worker_confirmed is not True:
                result.worker_confirmed = None
                result.commands.append(
                    CommandResult(None, error_code="WORKER_STOP_UNPROVED").safe("cleanup_worker")
                )
        except Exception:
            result.worker_confirmed = None
            result.commands.append(
                CommandResult(None, error_code="WORKER_AUDIT_FAILED").safe("cleanup_worker")
            )
    result.processes_reaped = reap_owned_processes(
        children, min(deadline_monotonic, time.monotonic() + 10)
    )
    if scope_ok:
        call(
            "cleanup_stop_pg", (*plan.compose, "stop", "--timeout", "20", plan.postgres_service), 25
        )
    states: list[dict[str, Any]] = []
    for cid in pg_ids:
        out = call(
            "cleanup_pg_state", (*plan.docker, "inspect", cid, "--format", "{{json .State}}")
        )
        try:
            state = json.loads(out.stdout) if out.code == 0 else None
            if (
                not isinstance(state, dict)
                or type(state["Running"]) is not bool
                or type(state["Pid"]) is not int
            ):
                raise ValueError
            states.append(state)
        except (ValueError, KeyError, TypeError):
            result.commands.append(
                CommandResult(None, error_code="PG_STATE_UNKNOWN").safe("cleanup_pg_state")
            )
    if len(states) == 1:
        result.pg_running, result.pg_pid = states[0]["Running"], states[0]["Pid"]
    if scope_ok:
        result.down_attempted = True
        down = call("cleanup_down", (*plan.compose, "down", "--timeout", "20"), 25)
        result.down_completed_no_v = down.code == 0
    result.containers = ids("cleanup_containers", "container")
    result.networks = ids("cleanup_networks", "network")
    result.volumes = ids("cleanup_volumes", "volume")
    result.listeners = {str(p): listener_open(p) for p in plan.ports}
    return result


def run_consumer(
    ledger: Ledger, action: Callable[[], None], cleanup: Callable[[], CleanupResult]
) -> int:
    """Used by the shared entry: cleanup independent of action success, exit never swallowed."""
    try:
        action()
    except Exception as error:
        try:
            active = next(
                (s for s in STAGES if ledger.stages[s]["status"] == "ENTERED"),
                next((s for s in STAGES if ledger.stages[s]["status"] == "NOT_RUN"), "cleanup"),
            )
            ledger.fail(active, error)
        except Exception:
            # A write failure still cannot prevent owned cleanup or turn into PASS.
            ledger.failures.append(safe_failure(error, "cleanup"))
    try:
        result = cleanup()
    except Exception as error:
        ledger.failures.append(safe_failure(error, "cleanup"))
        result = CleanupResult()
    try:
        return ledger.finish(result)
    except Exception:
        return 2


def _unique_json(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StageFailure("source", "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _private_reference(ref: Mapping[str, str], root: Path) -> tuple[Any, bytes]:
    path = Path(ref["path"])
    if (
        not path.is_absolute()
        or path.resolve() != path
        or not path.is_relative_to(root)
        or path == root
        or not re.fullmatch(r"[a-f0-9]{64}", ref["sha256"])
    ):
        raise StageFailure("source", "PRIVATE_REFERENCE_INVALID")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        file_stat = os.fstat(descriptor)
        if (
            not stat.S_ISREG(file_stat.st_mode)
            or file_stat.st_uid != os.getuid()
            or file_stat.st_mode & 0o777 != 0o600
            or file_stat.st_size > 4_194_304
        ):
            raise StageFailure("source", "PRIVATE_REFERENCE_INVALID")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(4_194_305)
        if hashlib.sha256(data).hexdigest() != ref["sha256"]:
            raise StageFailure("source", "PRIVATE_HASH_MISMATCH")
        return json.loads(data, object_pairs_hook=_unique_json), data
    finally:
        os.close(descriptor)


def _file_ref(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _exclusive_json(path: Path, value: Any) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


def _shared_helpers() -> Any:
    # The outer verified-bytes loader owns this import's provenance. No WIP path or
    # alternate launcher is installed here; both modules belong to one frozen tree.
    return importlib.import_module("scripts.p4_acceptance")


@dataclass
class _Consumer:
    stage: str
    handoff: Mapping[str, Any]
    handoff_ref: Mapping[str, str]
    root: Path = field(init=False)
    directory: Path = field(init=False)
    binding: dict[str, Any] = field(init=False)
    deadline_monotonic: float = field(init=False)

    def __post_init__(self) -> None:
        if self.stage not in ("t6", "restart", "page"):
            raise StageFailure("source", "STAGE_INVALID")
        h = self.handoff
        if h["contract"] != "p4-acceptance-preparation-v1":
            raise StageFailure("source", "CONTRACT_INVALID")
        self.root = Path(h["resource"]["runner"]["host_private_dir"])
        if (
            not self.root.is_absolute()
            or self.root.resolve() != self.root
            or self.root.stat().st_uid != os.getuid()
            or self.root.stat().st_mode & 0o777 != 0o700
        ):
            raise StageFailure("source", "PRIVATE_ROOT_INVALID")
        loaded, _ = _private_reference(self.handoff_ref, self.root)
        if loaded != h:
            raise StageFailure("source", "HANDOFF_BYTES_MISMATCH")
        candidate, resource, fixture = (h[k] for k in ("candidate", "resource", "fixture"))
        if (
            not re.fullmatch(r"[a-f0-9]{40}", candidate["source_sha"])
            or not re.fullmatch(r"[a-f0-9]{40}", candidate["tree"])
            or not re.fullmatch(r"[a-f0-9]{64}", candidate["manifest_sha256"])
            or type(resource["cleanup_reserve_seconds"]) is not int
            or resource["cleanup_reserve_seconds"] < 180
            or fixture["case_kind"] not in CASE_COUNTS
            or type(fixture["item_count"]) is not int
            or fixture["item_count"] != CASE_COUNTS[fixture["case_kind"]]
            or len(fixture["item_ids"]) != fixture["item_count"]
            or len(set(fixture["item_ids"])) != fixture["item_count"]
            or fixture["target_item_id"] not in fixture["item_ids"]
            or h["worker"]["epoch"] != "base_ro"
            or h["worker"]["reaped"] is not True
        ):
            raise StageFailure("source", "HANDOFF_CONTEXT_INVALID")
        for name in ("web_config", "app_database_config", "web_credentials", "external_records"):
            value, _ = _private_reference(h["private_refs"][name], self.root)
            if name == "app_database_config" and (
                value["user"] != "commerceops_app"
                or value["runtime_password_file"] is not None
                or value["host"] != "postgres"
            ):
                raise StageFailure("source", "APP_DATABASE_CONFIG_INVALID")
        deadline = datetime.fromisoformat(resource["deadline_utc"].replace("Z", "+00:00"))
        remaining = (deadline - datetime.now(UTC)).total_seconds() - resource[
            "cleanup_reserve_seconds"
        ]
        if not 0 < remaining <= 1800:
            raise StageFailure("source", "WINDOW_CLOSED")
        self.deadline_monotonic = time.monotonic() + remaining
        self.binding = {
            "contract": h["contract"],
            "source_sha": candidate["source_sha"],
            "source_tree": candidate["tree"],
            "manifest_sha256": candidate["manifest_sha256"],
            "run_id": resource["run_id"],
            "project": resource["project"],
            "item_id": fixture["target_item_id"],
            "task_id": fixture["task_id"],
            "parent_handoff_sha256": self.handoff_ref["sha256"],
            "case_kind": fixture["case_kind"],
            "item_count": fixture["item_count"],
            "quantity_total": fixture["quantity_total"],
        }
        self.context({"schema_revision": h["baseline"]["schema_revision"]}, None)
        parent = self.root / "C"
        parent.mkdir(mode=0o700, exist_ok=True)
        if parent.resolve() != parent or parent.stat().st_mode & 0o777 != 0o700:
            raise StageFailure("source", "PRIVATE_ROOT_INVALID")
        self.directory = parent / fixture["case_kind"]
        self.directory.mkdir(mode=0o700, exist_ok=True)
        if (
            self.directory.resolve() != self.directory
            or self.directory.stat().st_mode & 0o777 != 0o700
        ):
            raise StageFailure("source", "PRIVATE_ROOT_INVALID")

    def context(self, snapshot: dict[str, Any], key: str | None) -> CaptureContext:
        f = self.handoff["fixture"]
        return CaptureContext(
            snapshot["schema_revision"],
            f["organization_id"],
            f["shop_id"],
            f["task_id"],
            f["target_item_id"],
            f["principal_id"],
            f["web_identity_id"],
            f["auth_version"],
            tuple(f["checkpoint_threads"]),
            request_key=key,
            case_kind=f["case_kind"],
            expected_item_count=f["item_count"],
            expected_quantity_total=f["quantity_total"],
        )

    def save(self, name: str, value: Any) -> dict[str, str]:
        path = self.directory / (name + ".json")
        _exclusive_json(path, value)
        return _file_ref(path)

    def state(self, stage: str) -> dict[str, Any]:
        value, _ = _private_reference(
            _file_ref(self.directory / (stage + "-result.json")), self.root
        )
        if (
            any(value.get(k) != v for k, v in self.binding.items())
            or value.get("status") != "PASSED_STAGE_ONLY"
        ):
            raise StageFailure(self.stage, "PREVIOUS_STAGE_INVALID")
        return dict(value)

    def snapshot(self, phase: str, key: str | None, *, closed: bool) -> dict[str, Any]:
        value: dict[str, Any] = _shared_helpers().capture_bridge(
            "snapshot",
            self.handoff,
            handoff_ref=self.handoff_ref,
            phase=phase,
            request_key=key,
            sdk_window_id=self.handoff["base_ro"]["window_id"],
            sdk_subject_ids=(self.handoff["base_ro"]["outbox_id"],),
        )
        if value["phase"] != phase:
            raise StageFailure(self.stage, "CAPTURE_PHASE_MISMATCH")
        context = self.context(value, key)
        if value["scope"] != context.scope():
            raise StageFailure(self.stage, "CAPTURE_SCOPE_MISMATCH")
        validate_business(value, context, closed=closed)
        f = self.handoff["fixture"]
        if (
            set(f["item_ids"]) != {r["id"] for r in rows(value, "ITEMS")}
            or rows(value, "EXECUTIONS")[0]["id"] != f["execution_id"]
        ):
            raise StageFailure(self.stage, "FIXTURE_BINDING_INVALID")
        baseline = self.handoff["baseline"]
        if (
            value["schema_revision"] != baseline["schema_revision"]
            or immutable_business(value) != baseline["core"]
            or checkpoint_fingerprint(value) != baseline["checkpoints"]
        ):
            raise StageFailure(self.stage, "BASELINE_CHANGED")
        calls = rows(value, "MODEL_CALLS")
        if (
            len(calls) != 1
            or calls[0]["provider_calls"] != 0
            or type(calls[0]["n"]) is not int
            or calls[0]["n"] < 0
        ):
            raise StageFailure(self.stage, "MODEL_CALLS_PRESENT")
        self.save(phase, value)
        return value

    def lifecycle(self, action: str) -> dict[str, Any]:
        value: dict[str, Any] = _shared_helpers().app_lifecycle(
            action, self.handoff, handoff_ref=self.handoff_ref
        )
        live = action != "stop"
        if (
            type(value["active_workers"]) is not int
            or value["active_workers"] != int(live)
            or value["volume"] != self.handoff["resource"]["volume"]
            or value["reaped"] is not (not live)
            or value["api_ready"] is not live
            or value["epoch"]["organization"] != self.handoff["fixture"]["organization_id"]
            or value["epoch"]["owner"] == self.handoff["worker"]["owner"]
        ):
            raise StageFailure(self.stage, "APP_LIFECYCLE_INVALID")
        self.worker(value["epoch"], action + "-worker-" + self.stage, stopped=not live)
        self.save(action + "-lifecycle-" + self.stage, value)
        return value

    def worker(self, epoch: dict[str, Any], phase: str, *, stopped: bool) -> None:
        value = _shared_helpers().capture_bridge(
            "worker", self.handoff, handoff_ref=self.handoff_ref, phase=phase, owner=epoch["owner"]
        )
        if value["phase"] != phase:
            raise StageFailure(self.stage, "CAPTURE_PHASE_MISMATCH")
        validate_worker(value, epoch, stopped=stopped)
        self.save(phase, value)

    def ui(self, stage: str, key: str | None, screenshot: str | None) -> dict[str, Any]:
        h = self.handoff
        deadline = datetime.now(UTC).timestamp() + max(
            0, self.deadline_monotonic - time.monotonic()
        )
        value = {
            **self.binding,
            "stage": stage,
            "private_root": str(self.root),
            "output_directory": str(self.directory),
            "api_origin": h["web"]["api_origin"],
            "web_origin": h["web"]["web_origin"],
            "credentials_ref": h["private_refs"]["web_credentials"],
            "work_deadline_utc": datetime.fromtimestamp(deadline, UTC).isoformat(),
            "toolchain": h["candidate"]["toolchain"],
            "request_key": key,
            "request_phase": h["t6"]["request_phase"],
            "reason": h["t6"]["reason"],
            "screenshot_name": screenshot,
        }
        ref = self.save(stage + "-ui-input", value)
        node = h["candidate"]["toolchain"]["node_executable"]
        helper = Path(__file__).with_name("m1_acceptance_ui.cjs")
        if (
            hashlib.sha256(helper.read_bytes()).hexdigest()
            != h["candidate"]["toolchain"]["ui_helper_sha256"]
        ):
            raise StageFailure(self.stage, "UI_SOURCE_MISMATCH")
        result = ui_command(
            (node, str(helper), ref["path"], ref["sha256"]),
            cwd=Path(__file__).resolve().parents[3],
            env=controlled_environment({}),
            timeout=min(120, max(0, self.deadline_monotonic - time.monotonic())),
        )
        if result.code != 0:
            diagnostic = result.diagnostic or {}
            raise StageFailure(
                self.stage,
                result.error_code or diagnostic.get("code", "UI_COMMAND_FAILED"),
                dto=diagnostic.get("dto"),
            )
        output, _ = _private_reference(
            _file_ref(self.directory / (stage + "-ui-result.json")), self.root
        )
        if (
            any(
                output.get(k) != v
                for k, v in self.binding.items()
                if k not in ("manifest_sha256", "parent_handoff_sha256")
            )
            or output["status"] != "PASSED_STAGE_ONLY"
            or output["external_origin_attempts"] != 0
            or output["business_posts"] != int(stage == "t6")
            or output["original_key_gets"] != 1
            or output["browser_closed"] is not True
        ):
            raise StageFailure(self.stage, "UI_RESULT_BINDING_INVALID")
        return dict(output)

    def t6(self) -> dict[str, Any]:
        h = self.handoff
        if h["t6"] != {
            "action": "close",
            "expected_version": 1,
            "request_phase": "unprepared",
            "request_key": None,
            "reason": h["t6"]["reason"],
        }:
            raise StageFailure("arm_t6", "T6_CONTEXT_INVALID")
        self.lifecycle("start")
        try:
            before = self.snapshot("before-t6", None, closed=False)
            proof = h["base_ro"]["pg_proof"]
            validate_base_readback(
                before,
                self.context(before, None),
                version=1,
                target_key=proof["target_key"],
                external_id=proof["external_id"],
                verification_mode=proof["verification_mode"],
                native_projection_hash=h["base_ro"]["projection_hash"],
            )
            ui = self.ui("t6", None, "t6-closed-v2.png")
            prepared, _ = _private_reference(ui["prepared_receipt"], self.root)
            if any(prepared.get(k) != v for k, v in self.binding.items() if k != "manifest_sha256"):
                raise StageFailure("arm_t6", "PREPARED_BINDING_INVALID")
            # These are the original production DTO and semantic hash, loaded by the
            # common candidate guard. The wire-body digest remains a separate field.
            from commerceops.application.replenishment.contracts import ResolveInput
            from commerceops.application.replenishment.execution import resolution_hash
            from commerceops.domain.commerce_values import facts_hash

            request = ResolveInput.model_validate_json(json.dumps(prepared["input"]))
            key = str(request.request_key)
            semantic_hash = resolution_hash(self.binding["item_id"], request)
            after = self.snapshot("after-t6", key, closed=True)
            outbox = verify_t6_outbox(
                before,
                after,
                self.context(after, key),
                facts_hash(
                    {
                        "schema_version": "p3-web-v1",
                        "item_id": self.binding["item_id"],
                        "version": 2,
                        "state": "closed",
                    }
                ),
            )
            verify_t6_association(
                after,
                self.context(after, key),
                ui["typed_response"],
                h["t6"]["reason"],
                semantic_hash,
            )
            if ui["original_get"]["receipt"]["result"] != ui["typed_response"]:
                raise StageFailure("original_get", "ORIGINAL_RECEIPT_MISMATCH")
            return {
                "request_key": key,
                "semantic_payload_hash": semantic_hash,
                "typed_response": ui["typed_response"],
                "receipt_ref": ui["prepared_receipt"],
                "snapshot_ref": _file_ref(self.directory / "after-t6.json"),
                "v2_outbox": outbox,
                "item_count": self.handoff["fixture"]["item_count"],
                "quantity_total": self.handoff["fixture"]["quantity_total"],
                "closed_count": 1,
                "open_count": self.handoff["fixture"]["item_count"] - 1,
            }
        finally:
            self.stop_preserving_failure(sys.exception())

    def stop_preserving_failure(self, primary: BaseException | None) -> None:
        try:
            self.lifecycle("stop")
        except Exception as error:
            if primary is None:
                raise
            try:
                self.save(self.stage + "-stop-failed", safe_failure(error, "final_worker"))
            except Exception:
                primary.add_note("C_STOP_EVIDENCE_WRITE_FAILED")

    def restart(self) -> dict[str, Any]:
        previous = self.state("t6")
        first = self.lifecycle("start")
        self.snapshot("before-restart", previous["request_key"], closed=True)
        restarted = self.lifecycle("restart")
        if (
            restarted["stopped_epoch"] != first["epoch"]
            or restarted["stopped_reaped"] is not True
            or restarted["epoch"]["owner"] == first["epoch"]["owner"]
        ):
            raise StageFailure("restart", "RESTART_EPOCH_INVALID")
        self.worker(first["epoch"], "stopped-before-restart", stopped=True)
        self.snapshot("after-restart", previous["request_key"], closed=True)
        return {
            "request_key": previous["request_key"],
            "epoch": restarted["epoch"],
            "same_volume": True,
            "old_epoch_stopped_reaped": True,
        }

    def page(self) -> dict[str, Any]:
        previous, t6 = self.state("restart"), self.state("t6")
        try:
            self.worker(previous["epoch"], "page-live-worker", stopped=False)
            ui = self.ui("page", t6["request_key"], "page-after-restart.png")
            self.snapshot("post-restart", t6["request_key"], closed=True)
            replay = self.ui("replay", t6["request_key"], None)
            if (
                ui["original_get"]["receipt"] != replay["original_get"]["receipt"]
                or ui["original_get"]["receipt"]["result"] != t6["typed_response"]
            ):
                raise StageFailure("replay", "ORIGINAL_RECEIPT_MISMATCH")
            self.snapshot("after-replay", t6["request_key"], closed=True)
            return {
                "request_key": t6["request_key"],
                "business_posts": 0,
                "original_key_gets": 2,
                "same_volume": True,
                "checkpoint_core_unchanged": True,
            }
        finally:
            self.stop_preserving_failure(sys.exception())


def consume_stage(
    stage: str, handoff: Mapping[str, Any], *, handoff_ref: Mapping[str, str]
) -> dict[str, Any]:
    """Only the common verified entry calls this fixed stage consumer.

    Failure propagates to that entry's nonzero exit and independent cleanup. A
    returned result is local evidence; it cannot sign the whole candidate PASS.
    """
    consumer = _Consumer(stage, handoff, handoff_ref)
    consumer.save(stage + "-entered", {**consumer.binding, "stage": stage, "status": "ENTERED"})
    try:
        detail = {"t6": consumer.t6, "restart": consumer.restart, "page": consumer.page}[stage]()
    except Exception as error:
        consumer.save(stage + "-failed", safe_failure(error, stage))
        raise
    result = {
        **consumer.binding,
        **detail,
        "stage": stage,
        "status": "PASSED_STAGE_ONLY",
        "whole_candidate_pass": False,
        "real_platform_pass": False,
    }
    ref = consumer.save(stage + "-result", result)
    return {**result, "evidence_ref": ref}
