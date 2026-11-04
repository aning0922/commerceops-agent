"""New V41 owned execution; public V40 lifecycle helpers, never its Case/0024 Gate."""

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from tests.e2e.v4 import owned_driver as public
from tests.e2e.v4.owned_adapter import OwnedAdapter, compose_environment, owner_run
from tests.e2e.v4.supervisor import Budget, Supervisor

from . import browser_shell, owner_bridge
from .fixed_daemon import freeze as freeze_daemon
from .fixed_daemon import load as load_daemon
from .image_provenance import probe_argv, runtime_files, validate_build, validate_measured
from .owned_manifest import OwnedManifest
from .owner_setup import ACTIONS, PROGRAM_SHA256, private_bytes
from .runner import persist
from .runtime_checks import (
    reject_implicit_env,
    reserve_ports,
    verify_api_record,
    verify_web_listener,
)
from .source_seal import matches_source, snapshot
from .subjects import frozen_subjects

ROOT = Path(__file__).resolve().parents[3]
HANDOFF = "tests/e2e/v41/owner_recipe.json"
DEFINITION = "tests/e2e/v41/runtime_definition.json"


@dataclass(frozen=True)
class Case(OwnedManifest):
    @property
    def api(self) -> str:
        return f"http://127.0.0.1:{self.api_port}"

    @property
    def web(self) -> str:
        return f"http://127.0.0.1:{self.web_port}"

    def validate(
        self, root: Path | None = None, now: datetime | None = None, *, prepared: bool = False
    ) -> None:
        super().validate(root or ROOT, now or datetime.now(UTC), prepared=prepared)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def config_files(directory: Path) -> list[Path]:
    names = [
        "case.json",
        "compose.env",
        "owner/owner_password",
        "owner/app_password",
        "api/runtime-password",
        "api/csrf-key",
        "api/nonce-key",
        "api/web.json",
        "api/demo.json",
    ]
    return [directory / name for name in names] + owner_bridge.config_paths(directory)


def prepare(case: Case) -> None:
    # Only random new inputs from the public helper; it calls this V41 validate override.
    # No V40 Case, execute, migration diagnostic or prior runtime config is used.
    public.prepare(cast(Any, case))
    directory = Path(case.directory)
    owner_bridge.prepare(directory, case.database)
    public.private(
        directory / "config.seal.json",
        json.dumps({str(p.relative_to(directory)): digest(p) for p in config_files(directory)}),
    )


def runtime_handoff(case: Case, *, final: bool = False) -> dict[str, Any]:
    """Require a concrete recipe plus Root's exact private window; no READY bypass."""
    path = ROOT / HANDOFF
    expected = {
        "schema_version": "v41-fixed-owner-recipe-v1",
        "helper": "tests/e2e/v41/owner_setup.py",
        "actions": list(ACTIONS),
        "inside_program_sha256": PROGRAM_SHA256,
        "factory": "commerceops.entrypoints.api.create_app",
        "revision": "0025_v41_catalog_operations",
    }
    if not path.is_file() or path.is_symlink() or json.loads(path.read_text()) != expected:
        raise ValueError("V41_RUNTIME_HANDOFF_PENDING")
    for name in (
        "backend/src/commerceops/infrastructure/v41_runtime.py",
        "backend/src/commerceops/infrastructure/v41_security.py",
        "tests/e2e/v41/owner_setup.py",
        "tests/e2e/v41/verify_inside.txt",
    ):
        if not (ROOT / name).is_file():
            raise ValueError("V41_RUNTIME_IMPLEMENTATION_PENDING")
    directory = Path(case.directory)
    seal = json.loads(private_bytes(directory / "config.seal.json"))
    if seal != {str(p.relative_to(directory)): digest(p) for p in config_files(directory)}:
        raise ValueError("V41_PRIVATE_INPUT_CHANGED")
    if json.loads(private_bytes(directory / "case.json")) != asdict(case):
        raise ValueError("V41_CASE_CHANGED")
    return owner_bridge.authorize_case(case, final=final)


def fixed_compose(case: Case) -> tuple[str, ...]:
    # public.compose resolves paths only; it never queries a daemon.
    command = public.compose(cast(Any, case))
    return (str(load_daemon(Path(case.directory))), *command[1:])


def execute(case: Case, root_opened_window: bool) -> dict[str, Any]:
    if not root_opened_window:
        raise ValueError("ROOT_EXACT_RUNTIME_WINDOW_REQUIRED")
    case.validate(prepared=True)
    auth = runtime_handoff(case)  # No Docker/resource work before a concrete Root authorization.
    directory = Path(case.directory)
    browser_binding: dict[str, Any] | None = None
    browser_runtime_digest: str | None = None
    if case.scenario == "shell_navigation":
        browser_shell.verify_source(ROOT)
        browser_binding = browser_shell.runtime(case, auth["authorization_id"])
        browser_runtime_digest = digest(directory / "browser-runtime.safe.json")
    reject_implicit_env(ROOT)
    reserve_ports(case.api_port, case.web_port)
    expected_runtime = runtime_files(ROOT)
    build_receipt_path = directory / "image-build.safe.json"
    info = build_receipt_path.lstat()
    if (
        build_receipt_path.is_symlink()
        or not build_receipt_path.is_file()
        or info.st_uid != os.getuid()
        or info.st_mode & 0o777 != 0o600
    ):
        raise ValueError("ROOT_PRIVATE_IMAGE_BUILD_RECEIPT_REQUIRED")
    build_receipt = json.loads(private_bytes(build_receipt_path))
    raw_expected = private_bytes(directory / "expected-runtime.json")
    host_path = directory / "docker-host.safe.json"
    host_binding = json.loads(private_bytes(host_path, 32768))
    host_digest = digest(host_path)
    expected_file_digest = digest(directory / "expected-runtime.json")
    validate_build(
        build_receipt,
        case.source_sha,
        case.source_tree,
        case.test_image,
        expected_runtime,
        raw_expected,
    )
    build_receipt_digest = digest(build_receipt_path)
    original = public.compose(cast(Any, case))
    # Static binding failure exits before the try/finally or any daemon query.
    freeze_daemon(directory, original[0], host_binding)
    tool_paths = [
        Path(sys.executable).resolve(),
        ROOT / ".tools/node/bin/node",
        ROOT / "frontend/node_modules/next/dist/bin/next",
        Path(original[0]).resolve(),
        Path(host_binding["compose_plugin_path"]).resolve(),
    ]
    if browser_binding is not None:
        tool_paths.extend(
            [
                ROOT / "frontend/node_modules/@playwright/test/cli.js",
                *[Path(name) for name in browser_shell.runtime_tools(browser_binding)],
            ]
        )
    source_before = snapshot(ROOT, tool_paths)
    persist(directory / "source-before.json", source_before)
    public.private(directory / "execution.once", "V41 one new attempt; no replay\n")
    budget = Budget.bind(
        datetime.fromisoformat(case.starts_at), datetime.fromisoformat(case.deadline)
    )
    records: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "scope": "V41_OWNED_RUNTIME",
        "source_sha": case.source_sha,
        "source_tree": case.source_tree,
        "scenario": case.scenario,
        "required": records,
        "information": {},
        "status": "FAILED_OR_UNKNOWN",
        "cleanup": {},
        "summary": "NOT_WRITTEN",
    }
    command = fixed_compose(case)
    supervisor: Supervisor | None = None
    volume_format = (
        '{"name":{{json .Name}},"driver":{{json .Driver}},'
        '"created_at":{{json .CreatedAt}},"labels":{{json .Labels}}}'
    )

    def checked(
        stage: str,
        argv: list[str],
        cap: float = 60,
        cleanup: bool = False,
        stdin: bytes | None = None,
    ) -> bytes:
        start = datetime.now(UTC).isoformat()
        stdout, stderr = (
            directory / (stage + ".stdout.private.log"),
            directory / (stage + ".stderr.private.log"),
        )
        row: dict[str, Any] = {
            "stage": stage,
            "started_utc": start,
            "native_exit": None,
            "timed_out": False,
        }
        try:
            with stdout.open("xb") as output, stderr.open("xb") as error:
                stdout.chmod(0o600)
                stderr.chmod(0o600)
                # subprocess.run kills and waits its direct child on timeout; finally also
                # inventories/stops exact owned Docker objects, not just the compose CLI.
                result = subprocess.run(
                    argv,
                    cwd=ROOT,
                    env=compose_environment(),
                    stdout=output,
                    stderr=error,
                    input=stdin,
                    timeout=budget.timeout(cap, cleanup=cleanup),
                    check=False,
                )
            row["native_exit"] = result.returncode
            if result.returncode:
                raise RuntimeError("V41_COMMAND_NONZERO")
            return stdout.read_bytes()
        except subprocess.TimeoutExpired:
            row["timed_out"] = True
            raise
        finally:
            row.update(
                finished_utc=datetime.now(UTC).isoformat(),
                logs=[
                    {"path": str(p), "sha256": digest(p)} for p in (stdout, stderr) if p.is_file()
                ],
            )
            records.append(row)
            persist(directory / "execution.json", report)

    try:
        # The first daemon query is identity only; cleanup is not armed until
        # this fixed endpoint/server and the empty project have both passed.
        server = checked("docker_server", [command[0], "info", "--format", "{{.ID}}"], 5)
        if server.decode().strip() != host_binding["docker_server_id"]:
            raise ValueError("ROOT_DOCKER_SERVER_MISMATCH")
        report["information"]["fixed_daemon"] = {
            "endpoint": host_binding["docker_endpoint"],
            "server_id": server.decode().strip(),
        }
        public.verify_images(cast(Any, case), command[0], budget, records)
        report["information"]["ipam"] = public.verify_existing_subnets(
            cast(Any, case), command[0], budget, records
        )
        model = public.no_build_model(
            json.loads(
                checked(
                    "compose_config", [*command, "--profile", "test", "config", "--format", "json"]
                )
            ),
            cast(Any, case),
        )
        public.private(directory / "no-build.compose.json", json.dumps(model))
        public.private(
            directory / "no-build.compose.sha256", digest(directory / "no-build.compose.json")
        )
        command = fixed_compose(case)
        for kind, args in [
            ("container", ["ps", "-aq"]),
            ("network", ["network", "ls", "-q"]),
            ("volume", ["volume", "ls", "-q"]),
        ]:
            if checked(
                "empty_" + kind,
                [command[0], *args, "--filter", "label=com.docker.compose.project=" + case.project],
                5,
            ).strip():
                raise ValueError("V41_NAMESPACE_NOT_EMPTY")
        report["information"]["namespace_initial_empty"] = True
        actual_source = checked(
            "image_source",
            probe_argv(command[0], case.project, case.test_image, ROOT, case.uid),
            30,
            stdin=raw_expected,
        )
        report["information"]["image_source"] = validate_measured(actual_source, expected_runtime)
        owner_bridge.bind_inputs(directory, auth)
        volumes = model.get("volumes", {})
        if (
            set(volumes) != {"pg_data"}
            or volumes["pg_data"].get("name") != case.project + "_pg_data"
            or volumes["pg_data"].get("external")
            or volumes["pg_data"].get("driver_opts")
        ):
            raise ValueError("NEW_OWNED_VOLUME_MODEL_REQUIRED")
        if checked(
            "empty_volume_name",
            [
                command[0],
                "volume",
                "ls",
                "--quiet",
                "--filter",
                "name=^" + case.project + "_pg_data$",
            ],
            5,
        ).strip():
            raise ValueError("OWNED_VOLUME_NAME_PREEXISTS")
        supervisor = Supervisor(budget, ROOT, directory / "processes")
        checked(
            "pg_start",
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
            90,
        )
        expected_volume = json.loads(
            checked(
                "volume_created",
                [
                    command[0],
                    "volume",
                    "inspect",
                    case.project + "_pg_data",
                    "--format",
                    volume_format,
                ],
                5,
            )
        )
        if (
            expected_volume["name"] != case.project + "_pg_data"
            or expected_volume["labels"].get("com.docker.compose.project") != case.project
        ):
            raise ValueError("CREATED_VOLUME_OWNERSHIP_UNPROVEN")
        report["information"]["created_volume"] = expected_volume
        owner = list(owner_run(command))
        checked("migrate_0025", [*owner, "commerceops.entrypoints.database", "migrate"], 180)
        for label, module, action in [
            ("checkpointer", "commerceops.entrypoints.database", "setup-checkpointer"),
            ("legacy_grant", "commerceops.entrypoints.database", "grant-runtime"),
        ]:
            checked(label, [*owner, module, action])
        for action in ("init-fixture", "grant-runtime", "verify-fixture"):
            extra = ["--directory", "/run/v4_owner/export"] if action == "init-fixture" else []
            checked("seed_" + action, [*owner, "scripts.v4_demo_seed", action, *extra])
        previous: dict[str, Any] | None = None
        report["information"]["owner_setup"] = []
        for action in ACTIONS:
            _, spec = owner_bridge.operation_file(case, auth, action, previous)
            output = checked("owner_" + action, owner_bridge.argv(command, case, spec), 60)
            previous = owner_bridge.receipt(directory, auth, spec, output)
            report["information"]["owner_setup"].append(previous)
        api_argv, api_env = OwnedAdapter(
            command, case.project, budget, evidence=directory / "observers"
        ).launch_spec("api")
        api = supervisor.start("api", api_argv, api_env)
        api_format = (
            '{"running":{{.State.Running}},"image":{{json .Image}},"project":{{js'
            'on (index .Config.Labels "com.docker.compose.project")}},"service":{'
            '{json (index .Config.Labels "com.docker.compose.service")}},"user":{'
            '{json .Config.User}},"ports":{{json .NetworkSettings.Ports}},"mounts'
            '":{{json .Mounts}}}'
        )
        for attempt in range(100):
            if api.process.poll() is not None:
                raise RuntimeError("OWNED_API_EXITED")
            ids = (
                checked(
                    "api_owned_id_" + str(attempt),
                    [*command, "ps", "--all", "--quiet", "v4-api"],
                    5,
                )
                .decode()
                .split()
            )
            if len(ids) == 1:
                record = json.loads(
                    checked(
                        "api_owned_state_" + str(attempt),
                        [command[0], "inspect", "--format", api_format, ids[0]],
                        5,
                    )
                )
                if record["running"]:
                    verify_api_record(
                        record, case.project, case.test_image, case.uid, case.api_port, directory
                    )
                    report["information"]["api_listener_ownership"] = record
                    break
            time.sleep(min(0.1, budget.timeout(0.1)))
        else:
            raise RuntimeError("API_LISTENER_OWNERSHIP_UNPROVEN")
        public.ready(case.api + "/health/live", budget, api)
        node = ROOT / ".tools/node/bin/node"
        web = supervisor.start(
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
            public.web_environment(cast(Any, case), node),
        )
        for attempt in range(100):
            if web.process.poll() is not None:
                raise RuntimeError("OWNED_WEB_EXITED")
            observed = subprocess.run(
                [
                    "/usr/sbin/lsof",
                    "-nP",
                    "-iTCP:" + str(case.web_port),
                    "-sTCP:LISTEN",
                    "-F",
                    "pn",
                ],
                capture_output=True,
                text=True,
                timeout=budget.timeout(2),
                check=False,
            )
            if observed.stderr or observed.returncode not in (0, 1):
                raise RuntimeError("WEB_LISTENER_PROBE_FAILED")
            listeners = []
            pid = None
            for line in observed.stdout.splitlines():
                if line.startswith("p"):
                    pid = int(line[1:])
                if line.startswith("n") and pid is not None:
                    group = int(
                        checked(
                            "web_group_" + str(attempt) + "_" + str(pid),
                            ["/bin/ps", "-p", str(pid), "-o", "pgid="],
                            2,
                        )
                        .decode()
                        .strip()
                    )
                    listeners.append({"pid": pid, "pgid": group, "endpoint": line[1:]})
            if listeners:
                verify_web_listener(listeners, web.process.pid, case.web_port)
                report["information"]["web_listener_ownership"] = listeners
                break
            time.sleep(min(0.1, budget.timeout(0.1)))
        else:
            raise RuntimeError("WEB_LISTENER_OWNERSHIP_UNPROVEN")
        public.ready(case.web + "/v4", budget, web)
        probe = supervisor.start(
            "probe",
            (
                sys.executable,
                "-m",
                "tests.e2e.v41.browser_shell"
                if case.scenario == "shell_navigation"
                else "tests.e2e.v41.http_recipes",
                "--case",
                str(directory / "case.json"),
            ),
            compose_environment(),
        )
        native = supervisor.wait(probe, budget.remaining())
        records.append({"stage": "probe", "native_exit": native})
        if native or supervisor.watchdog_errors:
            raise RuntimeError("V41_PROBE_FAILED_OR_UNKNOWN")
        if case.scenario == "shell_navigation":
            browser_shell.validate_report(
                json.loads((directory / "processes/probe.raw.log").read_bytes())
            )
            report["information"]["browser_receipts"] = browser_shell.validate_receipts(
                case, browser_binding or {}
            )
            records.append(
                {"stage": "browser", "selected": 2, "passed": 2, "skipped": 0, "retries": 0}
            )
        report["status"] = "SCENARIO_COMPLETED_PENDING_CLEANUP"
    except Exception as error:
        report["failure"] = {"type": type(error).__name__, "errno": getattr(error, "errno", None)}
    finally:
        failures: list[dict[str, str]] = []
        writers_stopped = supervisor is None
        try:
            if supervisor is not None:
                report["cleanup"]["writers"] = supervisor.stop_writers()
                writers_stopped = not supervisor.watchdog_errors
        except Exception as error:
            failures.append({"stage": "writers", "type": type(error).__name__})
        if browser_binding is not None and supervisor is not None:
            try:
                browser_probe = next((p for p in supervisor.owned if p.role == "probe"), None)
                if browser_probe is None:
                    residuals = {
                        "forced": [],
                        "remaining": [],
                        "clean_exit": True,
                        "not_started": True,
                    }
                else:
                    residuals = browser_shell.stop_residuals(
                        case, browser_binding, budget, browser_probe.process.pid
                    )
                report["cleanup"]["browser"] = residuals
                if not residuals["clean_exit"]:
                    failures.append({"stage": "browser_residuals", "type": "ForcedStopOrRemaining"})
                writers_stopped = writers_stopped and not residuals["remaining"]
            except Exception as error:
                writers_stopped = False
                failures.append({"stage": "browser_residuals", "type": type(error).__name__})
            if writers_stopped and any(p.role == "probe" for p in supervisor.owned):
                journals = browser_shell.import_journals(case)
                report["information"]["browser_subjects"] = journals
                if journals["errors"]:
                    failures.append(
                        {"stage": "browser_subjects", "type": "IncompleteOrInvalidJournal"}
                    )
        if report["information"].get("namespace_initial_empty"):
            try:
                check_ids = (
                    checked(
                        "sourcecheck_remaining",
                        [
                            command[0],
                            "ps",
                            "-aq",
                            "--filter",
                            "label=com.docker.compose.project=" + case.project,
                            "--filter",
                            "label=com.docker.compose.service=v41-sourcecheck",
                        ],
                        5,
                        True,
                    )
                    .decode()
                    .split()
                )
                for index, cid in enumerate(check_ids):
                    checked(
                        "sourcecheck_stop_" + str(index),
                        [command[0], "stop", "--time", "5", cid],
                        10,
                        True,
                    )
                    checked("sourcecheck_rm_" + str(index), [command[0], "rm", cid], 5, True)
                checked("api_stop", [*command, "stop", "--timeout", "5", "v4-api"], 15, True)
                ids = (
                    checked(
                        "oneoffs",
                        [
                            command[0],
                            "ps",
                            "-q",
                            "--filter",
                            "label=com.docker.compose.project=" + case.project,
                            "--filter",
                            "label=com.docker.compose.service=pg-test",
                        ],
                        5,
                        True,
                    )
                    .decode()
                    .split()
                )
                for index, cid in enumerate(ids):
                    checked(
                        "owner_stop_" + str(index),
                        [command[0], "stop", "--time", "5", cid],
                        10,
                        True,
                    )
                if not writers_stopped:
                    raise RuntimeError("WRITERS_NOT_CONFIRMED_STOPPED")
                subject_export = directory / "owner/export/v41-subjects.private.json"
                public.private(subject_export, frozen_subjects(directory).decode())
                report["information"]["final_subject_export_sha256"] = digest(subject_export)
                checked(
                    "final_facts",
                    [
                        *owner_run(command),
                        "tests.e2e.v41.pg_observer",
                        "subjects",
                        "--subjects-file",
                        "/run/v4_owner/export/v41-subjects.private.json",
                        "--deadline",
                        case.deadline,
                        "--final",
                    ],
                    15,
                    True,
                )
            except Exception as error:
                failures.append({"stage": "stop_and_final_facts", "type": type(error).__name__})
            finally:
                # Final facts/stop failures must never suppress scoped down/inventory.
                try:
                    checked("down", [*command, "down", "--timeout", "5"], 45, True)
                except Exception as error:
                    failures.append({"stage": "down", "type": type(error).__name__})
                try:
                    for kind, args in [
                        ("containers", ["ps", "-aq"]),
                        ("networks", ["network", "ls", "-q"]),
                    ]:
                        report["cleanup"][kind] = (
                            checked(
                                "remaining_" + kind,
                                [
                                    command[0],
                                    *args,
                                    "--filter",
                                    "label=com.docker.compose.project=" + case.project,
                                ],
                                5,
                                True,
                            )
                            .decode()
                            .strip()
                        )
                    report["cleanup"]["volumes_preserved"] = (
                        checked(
                            "volumes",
                            [
                                command[0],
                                "volume",
                                "ls",
                                "-q",
                                "--filter",
                                "label=com.docker.compose.project=" + case.project,
                            ],
                            5,
                            True,
                        )
                        .decode()
                        .split()
                    )
                    final_volume = json.loads(
                        checked(
                            "volume_preserved_identity",
                            [
                                command[0],
                                "volume",
                                "inspect",
                                case.project + "_pg_data",
                                "--format",
                                volume_format,
                            ],
                            5,
                            True,
                        )
                    )
                    if final_volume != report["information"].get("created_volume") or report[
                        "cleanup"
                    ]["volumes_preserved"] != [case.project + "_pg_data"]:
                        raise ValueError("EXPECTED_CREATED_VOLUME_NOT_PRESERVED")
                    ports = {}
                    for port in (case.api_port, case.web_port):
                        with socket.socket() as sock:
                            sock.settimeout(0.2)
                            ports[str(port)] = sock.connect_ex(("127.0.0.1", port)) != 0
                    report["cleanup"]["ports_closed"] = ports
                except Exception as error:
                    failures.append({"stage": "final_inventory", "type": type(error).__name__})
        try:
            if supervisor is not None:
                supervisor.close_pg()
        except Exception as error:
            failures.append({"stage": "close_pg", "type": type(error).__name__})
        try:
            current_source = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip()
            current_tree = subprocess.check_output(
                ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True
            ).strip()
            if (
                (current_source, current_tree) != (case.source_sha, case.source_tree)
                or runtime_files(ROOT) != expected_runtime
                or digest(build_receipt_path) != build_receipt_digest
            ):
                raise ValueError("TERMINAL_SOURCE_OR_BUILD_BINDING_CHANGED")
            if any(digest(ROOT / name) != value for name, value in case.inputs.items()):
                raise ValueError("TERMINAL_PUBLIC_INPUT_CHANGED")
            reject_implicit_env(ROOT)
            runtime_handoff(case, final=True)
            if (
                digest(host_path) != host_digest
                or digest(directory / "expected-runtime.json") != expected_file_digest
            ):
                raise ValueError("TERMINAL_ROOT_BUILD_OR_DAEMON_INPUT_CHANGED")
            if browser_binding is not None and (
                digest(directory / "browser-runtime.safe.json") != browser_runtime_digest
                or browser_shell.runtime(case, auth["authorization_id"]) != browser_binding
            ):
                raise ValueError("TERMINAL_BROWSER_RUNTIME_CHANGED")
            load_daemon(directory)
            source_after = snapshot(ROOT, tool_paths)
            persist(directory / "source-after.json", source_after)
            if not matches_source(source_before, source_after):
                raise ValueError("TERMINAL_TRACKED_SOURCE_OR_TOOL_CHANGED")
            report["information"]["terminal_source_seal"] = "TRACKED_SOURCE_AND_TOOLS_UNCHANGED"
        except Exception as error:
            failures.append({"stage": "terminal_source_seal", "type": type(error).__name__})
        report["cleanup"]["failures"] = failures
        report["cleanup"]["confirmed"] = bool(
            report["information"].get("namespace_initial_empty")
            and writers_stopped
            and not failures
            and report["cleanup"].get("containers") == ""
            and report["cleanup"].get("networks") == ""
            and all(report["cleanup"].get("ports_closed", {}).values())
        )
        persist(directory / "execution.json", report)
    if report["status"] == "SCENARIO_COMPLETED_PENDING_CLEANUP" and report["cleanup"].get(
        "confirmed"
    ):
        report["status"] = "SCENARIO_COMPLETED_PENDING_REVIEW"
    persist(directory / "execution.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "execute"))
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--root-opened-window", action="store_true")
    args = parser.parse_args()
    case = Case(**json.loads(args.case.read_text()))
    if args.action == "prepare":
        prepare(case)
        print(json.dumps({"status": "PREPARED_ONLY", "runtime": "NOT_RUN"}))
    else:
        report = execute(case, args.root_opened_window)
        print(json.dumps({"status": report["status"]}))
        raise SystemExit(0 if report["status"] == "SCENARIO_COMPLETED_PENDING_REVIEW" else 1)


if __name__ == "__main__":
    main()
