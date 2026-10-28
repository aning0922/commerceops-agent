"""Local Fast/Impacted feedback. Never runs or replaces the existing Full required gates."""

import argparse
import ast
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from types import FrameType

from scripts.harness_contract import TaskSpec, safe_scope

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = "6d3a8f7bf3d36c6c1dcfd5072a3297be4cc88265"
H1_PYTHON = {"scripts/harness_contract.py", "scripts/current_state.py", "scripts/verify.py"}
H1_TESTS = {"tests/test_harness_contract.py", "tests/test_harness_verify.py"}


class Interrupted(Exception):
    def __init__(self, signum: int):
        self.signum = signum


def interrupt(signum: int, _frame: FrameType | None) -> None:
    raise Interrupted(signum)


@dataclass
class CheckResult:
    name: str
    command: list[str]
    status: str = "NOT_RUN"
    exit_code: int | None = None
    wall_seconds: float = 0.0
    output_sha256: str | None = None
    reason: str | None = None


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def changed_paths(base: str) -> list[str]:
    """Include committed, staged, unstaged, deleted and nonignored untracked paths."""
    if re.fullmatch(r"[0-9a-f]{40}", base) is None:
        raise ValueError("base must be a full frozen commit SHA")
    git("rev-parse", "--verify", f"{base}^{{commit}}")
    paths: set[str] = set()
    for arguments in (
        ("diff", "--name-only", "--no-renames", "-z", base, "--"),
        ("ls-files", "--others", "--exclude-standard", "-z"),
    ):
        result = subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True, check=True)
        paths.update(part.decode() for part in result.stdout.split(b"\0") if part)
    return sorted(paths)


def known_h1(path: str) -> bool:
    return (
        path in H1_PYTHON | H1_TESTS
        or path in {"AGENTS.md", "AGENTS.history-20261028.md", "CURRENT_STATE.md"}
        or path.startswith("docs/harness/")
    )


def full_reasons(paths: list[str], risk: str) -> list[str]:
    reasons = []
    if risk in {"high", "critical", "unknown"}:
        reasons.append(f"task risk: {risk}")
    for path in paths:
        if not known_h1(path):
            reasons.append(f"unmapped/high-risk path: {path}")
        elif path.startswith("scripts/") or path.startswith("tests/"):
            reasons.append(f"verification/control code: {path}")
    return reasons


def stop_child(child: subprocess.Popen[bytes]) -> None:
    """Only the new process group owned by this verifier; wait/reap after TERM/KILL."""
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        child.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    # A group may outlive its leader; kill any owned descendant before returning.
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    child.wait()


def run_check(check: CheckResult, timeout: int) -> None:
    started = time.monotonic()
    child: subprocess.Popen[bytes] | None = None
    try:
        child = subprocess.Popen(
            check.command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        output, _ = child.communicate(timeout=timeout)
        if child.returncode < 0:
            check.exit_code = 128 - child.returncode
            check.status = "INTERRUPTED"
            check.reason = f"child {signal.Signals(-child.returncode).name}"
        else:
            check.exit_code = child.returncode
            check.status = "PASSED" if child.returncode == 0 else "FAILED"
        check.output_sha256 = hashlib.sha256(output).hexdigest()
    except Interrupted as error:
        check.status = "INTERRUPTED"
        check.exit_code = 128 + error.signum
        check.reason = signal.Signals(error.signum).name
        raise
    except subprocess.TimeoutExpired:
        check.status = "FAILED"
        check.exit_code = 124
        check.reason = "check timeout"
    except OSError:
        check.status = "FAILED"
        check.exit_code = 127
        check.reason = "check executable unavailable"
    finally:
        if child is not None:
            stop_child(child)
        check.wall_seconds = round(time.monotonic() - started, 6)


def syntax_checks(paths: list[str]) -> list[str]:
    errors = []
    for name in paths:
        safe_scope(name)
        path = ROOT / name
        if not path.exists():
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            errors.append(f"symlink/outside path refused: {name}")
            continue
        if path.suffix == ".py":
            try:
                ast.parse(path.read_text(), filename=name)
            except (SyntaxError, UnicodeError, OSError):
                errors.append(f"Python syntax/read failure: {name}")
        elif path.suffix == ".json" and name.startswith("docs/harness/"):
            try:
                json.loads(path.read_text())
            except (ValueError, OSError):
                errors.append(f"JSON syntax/read failure: {name}")
    return errors


def plan(
    mode: str, paths: list[str], base: str = DEFAULT_BASE
) -> tuple[list[CheckResult], list[str]]:
    python = [name for name in paths if name.endswith(".py") and (ROOT / name).is_file()]
    checks = [CheckResult("baseline diff whitespace", ["git", "diff", "--check", base, "--"])]
    checks.append(CheckResult("staged whitespace", ["git", "diff", "--cached", "--check"]))
    if python:
        checks.extend(
            [
                CheckResult(
                    "changed Python lint", [sys.executable, "-m", "ruff", "check", *python]
                ),
                CheckResult(
                    "changed Python format",
                    [sys.executable, "-m", "ruff", "format", "--check", *python],
                ),
                CheckResult("changed Python types", [sys.executable, "-m", "mypy", *python]),
            ]
        )
    if any(known_h1(path) for path in paths):
        checks.append(
            CheckResult("trusted state/archive", [sys.executable, "-m", "scripts.current_state"])
        )
    if any(path.endswith(".md") for path in paths):
        checks.append(
            CheckResult("Markdown links/fences", [sys.executable, "-m", "scripts.check_docs"])
        )
    if any(path in H1_PYTHON | H1_TESTS or path.startswith("docs/harness/") for path in paths):
        checks.append(
            CheckResult(
                "H1 offline contracts",
                [sys.executable, "-m", "pytest", "-q", "-m", "offline", *sorted(H1_TESTS)],
            )
        )
    unmapped = [path for path in paths if not known_h1(path)]
    if mode == "impacted" and unmapped:
        checks.append(CheckResult("unmapped impacted tests", [], reason="Full required; not run"))
    return checks, unmapped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["fast", "impacted"])
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--timeout", type=int, choices=range(1, 601), default=120, metavar="1..600")
    args = parser.parse_args()
    started = time.monotonic()
    checks: list[CheckResult] = []
    report: dict[str, object] = {
        "schema_version": "harness-verify-v3.1",
        "mode": args.mode,
        "status": "FAILED",
        "base_sha": args.base,
        "full_gate": "NOT_RUN",
        "merge_eligible": False,
        "full_required": True,
        "usage_source": "UNKNOWN",
    }
    exit_code = 1
    previous_handlers = {
        sig: signal.signal(sig, interrupt) for sig in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        paths = changed_paths(args.base)
        report["head_sha"] = git("rev-parse", "HEAD")
        report["branch"] = git("branch", "--show-current")
        report["changed_paths"] = paths
        risk = "unknown"
        required_full = False
        if args.spec:
            spec = TaskSpec.model_validate_json(args.spec.read_text())
            if spec.base_sha != args.base or spec.owner.branch != report["branch"]:
                raise ValueError("spec base/branch mismatch")
            if Path(spec.owner.worktree).resolve() != ROOT:
                raise ValueError("spec owner worktree mismatch")
            if any(not spec.permits(path) for path in paths):
                raise ValueError("changed path outside approved scope")
            risk = spec.risk
            required_full = "full" in spec.required_checks
            report["spec_sha256"] = spec.spec_sha256
        reasons = full_reasons(paths, risk)
        if required_full:
            reasons.append("TaskSpec requires Full")
        report["full_required"] = bool(reasons)
        report["full_required_reasons"] = reasons
        errors = syntax_checks(paths)
        if errors:
            report["errors"] = errors
            raise ValueError("changed-path syntax/safety check failed")
        checks, unmapped = plan(args.mode, paths, args.base)
        report["unmapped_paths"] = unmapped
        for check in checks:
            if not check.command:
                continue
            run_check(check, args.timeout)
            if check.status != "PASSED":
                break
        if any(check.status in {"FAILED", "INTERRUPTED"} for check in checks):
            failed = next(check for check in checks if check.status in {"FAILED", "INTERRUPTED"})
            report["status"] = failed.status
            exit_code = failed.exit_code or 1
        elif any(check.status == "NOT_RUN" for check in checks):
            report["status"] = "NOT_RUN"
            exit_code = 3
        else:
            report["status"] = "LOCAL_PASS"
            exit_code = 0
    except Interrupted as error:
        report["status"] = "INTERRUPTED"
        exit_code = 128 + error.signum
    except (ValueError, OSError, subprocess.CalledProcessError):
        report["reason"] = "invalid input, contract, Git state, or changed-path syntax"
    finally:
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
        report["checks"] = [asdict(check) for check in checks]
        report["exit_code"] = exit_code
        report["wall_seconds"] = round(time.monotonic() - started, 6)
        print(json.dumps(report, sort_keys=True))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
