"""New V41 owned execution; public V40 lifecycle helpers, never its Case/0024 Gate."""

import argparse
import hashlib
import json
import socket
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from tests.e2e.v4 import owned_driver as public
from tests.e2e.v4.owned_adapter import OwnedAdapter, compose_environment, owner_run
from tests.e2e.v4.supervisor import Budget, Supervisor

from .owned_manifest import OwnedManifest
from .runner import persist

ROOT = Path(__file__).resolve().parents[3]
HANDOFF = "tests/e2e/v41/runtime_handoff.json"
GRANT_MODULE = (
    "commerceops.entrypoints.v41_database"  # Interface reservation; API owner must align.
)


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
    return [
        directory / "case.json",
        directory / "compose.env",
        *sorted((directory / "owner").glob("*")),
        *sorted((directory / "api").glob("*")),
    ]


def prepare(case: Case) -> None:
    # Only random new inputs from the public helper; it calls this V41 validate override.
    # No V40 Case, execute, migration diagnostic or prior runtime config is used.
    public.prepare(cast(Any, case))
    directory = Path(case.directory)
    public.private(
        directory / "config.seal.json",
        json.dumps({str(p.relative_to(directory)): digest(p) for p in config_files(directory)}),
    )


def runtime_handoff(case: Case) -> None:
    """Block before Docker until API/SQL/probe seams are explicitly committed/aligned."""
    path = ROOT / HANDOFF
    expected = {
        "schema": "v41-qa-runtime-handoff-1",
        "grant_module": GRANT_MODULE,
        "factory": "commerceops.entrypoints.api.create_app",
        "revision": "0025_v41_catalog_operations",
    }
    if not path.is_file() or path.is_symlink() or json.loads(path.read_text()) != expected:
        raise ValueError("V41_RUNTIME_HANDOFF_PENDING")
    for name in [
        "backend/src/commerceops/entrypoints/v41_database.py",
        "tests/e2e/v41/http_recipes.py",
        "tests/e2e/v41/pg_observer.py",
    ]:
        if not (ROOT / name).is_file():
            raise ValueError("V41_RUNTIME_IMPLEMENTATION_PENDING")
    directory = Path(case.directory)
    seal = json.loads((directory / "config.seal.json").read_text())
    if seal != {str(p.relative_to(directory)): digest(p) for p in config_files(directory)}:
        raise ValueError("V41_PRIVATE_INPUT_CHANGED")
    if json.loads((directory / "case.json").read_text()) != asdict(case):
        raise ValueError("V41_CASE_CHANGED")


def execute(case: Case, root_opened_window: bool) -> dict[str, Any]:
    if not root_opened_window:
        raise ValueError("ROOT_EXACT_RUNTIME_WINDOW_REQUIRED")
    case.validate(prepared=True)
    runtime_handoff(case)  # No Docker command or resource creation before this binding.
    directory = Path(case.directory)
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
    command = public.compose(cast(Any, case))
    supervisor: Supervisor | None = None

    def checked(stage: str, argv: list[str], cap: float = 60, cleanup: bool = False) -> bytes:
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
        command = public.compose(cast(Any, case))
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
        owner = list(owner_run(command))
        checked("migrate_0025", [*owner, "commerceops.entrypoints.database", "migrate"], 180)
        for label, module, action in [
            ("checkpointer", "commerceops.entrypoints.database", "setup-checkpointer"),
            ("legacy_grant", "commerceops.entrypoints.database", "grant-runtime"),
            ("new_grant", GRANT_MODULE, "grant-runtime"),
            ("verify_new_grant", GRANT_MODULE, "verify-runtime"),
        ]:
            checked(label, [*owner, module, action])
        for action in ("init-fixture", "grant-runtime", "verify-fixture"):
            extra = ["--directory", "/run/v4_owner/export"] if action == "init-fixture" else []
            checked("seed_" + action, [*owner, "scripts.v4_demo_seed", action, *extra])
        api_argv, api_env = OwnedAdapter(
            command, case.project, budget, evidence=directory / "observers"
        ).launch_spec("api")
        api = supervisor.start("api", api_argv, api_env)
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
        public.ready(case.web + "/v4", budget, web)
        probe = supervisor.start(
            "probe",
            (
                sys.executable,
                "-m",
                "tests.e2e.v41.http_recipes",
                "--case",
                str(directory / "case.json"),
            ),
            compose_environment(),
        )
        native = supervisor.wait(probe, budget.remaining())
        records.append({"stage": "probe", "native_exit": native})
        if native or supervisor.watchdog_errors:
            raise RuntimeError("V41_PROBE_FAILED_OR_UNKNOWN")
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
        if report["information"].get("namespace_initial_empty"):
            try:
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
                checked(
                    "final_facts",
                    [
                        *owner_run(command),
                        "tests.e2e.v41.pg_observer",
                        "schema",
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
