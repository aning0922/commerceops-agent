"""Six fixed local failure simulations; not a V41 API/PG/browser runner yet."""

import argparse
import hashlib
import json
import os
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .process import ROOT, command, stamp, stop_registered

RECIPES = frozenset(
    {"normal", "nonzero", "timeout", "observer_missing", "cleanup_fail", "summary_fail"}
)


def persist(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(".pending")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def binding() -> dict[str, Any]:
    def git(name: str) -> str:
        return subprocess.check_output(["git", "rev-parse", name], cwd=ROOT, text=True).strip()

    paths = [ROOT / "uv.lock", *sorted(Path(__file__).parent.glob("*.py"))]
    return {
        "source_sha": git("HEAD"),
        "source_tree": git("HEAD^{tree}"),
        "input_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
        },
        "python_sha256": hashlib.sha256(Path(sys.executable).resolve().read_bytes()).hexdigest(),
        "binding_scope": "Source identity plus working input bytes; simulation only",
    }


def worker(directory: Path, recipe: str) -> int:
    info = directory.lstat()
    if (
        directory.resolve() != directory
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise ValueError("new owner-private simulation directory required")
    required: dict[str, Any] = {}
    before = binding()
    receipt: dict[str, Any] = {
        "scope": "LOCAL_PROCESS_SIMULATION_ONLY",
        "recipe": recipe,
        "started_utc": stamp(),
        "binding_before": before,
        "required": required,
        "information": {"refs_equal": False},
        "remaining_registered_resources": [],
    }
    try:
        required["probe"] = command(
            directory,
            "required",
            "fail" if recipe == "nonzero" else "sleep" if recipe == "timeout" else "ok",
            0.3 if recipe == "timeout" else 5,
        )
        if required["probe"]["passed"]:
            observer = command(
                directory,
                "observer",
                "observer_missing" if recipe == "observer_missing" else "observer",
                5,
            )
            observed = directory / "observation.json"
            valid = observed.is_file() and json.loads(observed.read_text()) == {
                "status": "SIMULATION_OBSERVED"
            }
            required["observer"] = {
                **observer,
                "observation_present": valid,
                "passed": observer["passed"] and valid,
            }
    finally:
        receipt["cleanup"] = command(
            directory, "cleanup", "cleanup_fail" if recipe == "cleanup_fail" else "ok", 5
        )
        receipt["remaining_registered_resources"] = [
            r["pid"] for r in [*required.values(), receipt["cleanup"]] if not r["group_absent"]
        ]
        receipt["binding_after"] = binding()
        receipt["binding_unchanged"] = before == receipt["binding_after"]
        receipt["checks_pass"] = set(required) == {"probe", "observer"} and all(
            r["passed"] for r in required.values()
        )
        receipt["finished_utc"] = stamp()
        persist(directory / "checks.json", receipt)
    summary: dict[str, Any] = {"status": "NOT_WRITTEN"}
    try:
        if recipe == "summary_fail":
            raise KeyError("simulated information ref has no check result")
        print(
            json.dumps(
                {"checks_pass": receipt["checks_pass"], "information": receipt["information"]}
            )
        )
        summary["status"] = "WRITTEN"
    except Exception as error:
        summary = {"status": "FAILED", "error_type": type(error).__name__}
    persist(directory / "stdout_summary.json", summary)
    return int(
        not (
            receipt["checks_pass"]
            and receipt["cleanup"]["passed"]
            and receipt["binding_unchanged"]
            and not receipt["remaining_registered_resources"]
            and summary["status"] == "WRITTEN"
        )
    )


def run(directory: Path, recipe: str) -> dict[str, Any]:
    if recipe not in RECIPES or not directory.is_absolute() or directory.resolve() != directory:
        raise ValueError("fixed recipe and new canonical absolute directory required")
    directory.mkdir(mode=0o700, exist_ok=False)
    fd = os.open(
        directory / "worker.private.log",
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
        0o600,
    )
    start = time.monotonic()
    argv = [
        sys.executable,
        "-m",
        "tests.e2e.v41.runner",
        "worker",
        "--recipe",
        recipe,
        "--directory",
        str(directory),
    ]
    with os.fdopen(fd, "wb") as log:
        process = subprocess.Popen(
            argv, cwd=ROOT, env={}, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
        )
        # Fixed recipes have bounded children, including their cleanup; wait/reap actual worker.
        timed_out = False
        remaining: list[int] = []
        try:
            native = process.wait(timeout=25)
        except subprocess.TimeoutExpired:
            timed_out = True
            for sig in (signal.SIGTERM, signal.SIGKILL):
                if process.poll() is not None:
                    break
                os.killpg(process.pid, sig)
                try:
                    process.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    pass
        finally:
            native = process.wait(timeout=1)
            remaining = stop_registered(directory)
    result: dict[str, Any] = {
        "scope": "LOCAL_PROCESS_SIMULATION_ONLY",
        "recipe": recipe,
        "worker_pid": process.pid,
        "worker_native_exit": native,
        "worker_reaped": process.poll() is not None,
        "outer_timed_out": timed_out,
        "remaining_registered_resources": remaining,
        "elapsed_seconds": time.monotonic() - start,
        "ended_utc": stamp(),
        "checks_receipt": {
            "path": str(directory / "checks.json"),
            "sha256": hashlib.sha256((directory / "checks.json").read_bytes()).hexdigest()
            if (directory / "checks.json").is_file()
            else None,
        },
        "stdout_summary_receipt": {
            "path": str(directory / "stdout_summary.json"),
            "sha256": hashlib.sha256((directory / "stdout_summary.json").read_bytes()).hexdigest()
            if (directory / "stdout_summary.json").is_file()
            else None,
        },
        "worker_log": {
            "path": str(directory / "worker.private.log"),
            "sha256": hashlib.sha256((directory / "worker.private.log").read_bytes()).hexdigest(),
        },
        "stage_gate": "NOT_RUN",
    }
    persist(directory / "outer.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "worker"))
    parser.add_argument("--recipe", choices=sorted(RECIPES), required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "worker":
        raise SystemExit(worker(args.directory, args.recipe))
    result = run(args.directory, args.recipe)
    print(json.dumps(result))
    raise SystemExit(
        result["worker_native_exit"]
        or int(result["outer_timed_out"] or bool(result["remaining_registered_resources"]))
    )


if __name__ == "__main__":
    main()
