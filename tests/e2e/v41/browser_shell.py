"""Fixed two-spec host browser path, durable subject import and scoped residual checks."""

import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from tests.e2e.v4.supervisor import Budget

from .owner_setup import decode, private_bytes
from .subjects import private_subject_bytes, registry

if TYPE_CHECKING:
    from .owned_driver import Case

ROOT = Path(__file__).resolve().parents[3]
TITLES = {
    "shell.live.spec.ts": "LIVE V41: shell identity navigation and responsive boundaries",
    "business.live.spec.ts": "LIVE V41: business reads writes and import roundtrip",
}
SOURCE_PATHS = (
    "frontend/v41-e2e/playwright.config.ts",
    "frontend/v41-e2e/shell.live.spec.ts",
    "frontend/v41-e2e/business.live.spec.ts",
    "frontend/v41-e2e/browser-subjects.ts",
    "frontend/lib/v4-schema.json",
    "frontend/lib/v41-schema.json",
    "frontend/lib/v41-routes.json",
    "frontend/package-lock.json",
)


def verify_source(root: Path) -> None:
    for name in SOURCE_PATHS:
        path = root / name
        if path.resolve() != path or not path.is_file():
            raise ValueError("FIXED_REVIEWED_BROWSER_SOURCE_REQUIRED")
        committed = subprocess.check_output(["git", "show", "HEAD:" + name], cwd=root)
        if path.read_bytes() != committed:
            raise ValueError("FIXED_BROWSER_SOURCE_DIFFERS_FROM_HEAD")


def runtime(case: "Case", authorization_id: str) -> dict[str, Any]:
    record = json.loads(private_bytes(Path(case.directory) / "browser-runtime.safe.json", 32768))
    expected = {
        "schema_version": "v41-browser-runtime-v1",
        "source_sha": case.source_sha,
        "source_tree": case.source_tree,
        "authorization_id": authorization_id,
        "directory": case.directory,
        "uid": case.uid,
        "project": case.project,
        "test_image": case.test_image,
    }
    if set(record) != set(expected) | {"executable", "sha256"} or any(
        record[k] != v for k, v in expected.items()
    ):
        raise ValueError("ROOT_EXACT_BROWSER_RUNTIME_REQUIRED")
    path = Path(record["executable"])
    if (
        not path.is_absolute()
        or path.resolve() != path
        or not path.is_file()
        or not os.access(path, os.X_OK)
        or not re.fullmatch(r"[a-f0-9]{64}", record["sha256"])
        or hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]
    ):
        raise ValueError("ROOT_BROWSER_BINARY_HASH_MISMATCH")
    return dict(record)


def command(case: "Case") -> tuple[str, ...]:
    return (
        str(ROOT / ".tools/node/bin/node"),
        str(ROOT / "frontend/node_modules/@playwright/test/cli.js"),
        "test",
        "--config",
        str(ROOT / "frontend/v41-e2e/playwright.config.ts"),
        "--grep",
        "(?:^| )(?:" + "|".join(re.escape(t) for t in TITLES.values()) + ")$",
        "--workers",
        "1",
        "--retries",
        "0",
        "--forbid-only",
        "--reporter",
        "json",
        "--output",
        str(Path(case.directory) / "browser-artifacts"),
    )


def validate_report(report: dict[str, Any]) -> None:
    wanted = {"expected": 2, "unexpected": 0, "flaky": 0, "skipped": 0}
    stats = report.get("stats", {})
    if report.get("errors") or any(
        type(stats.get(k)) is not int or stats[k] != n for k, n in wanted.items()
    ):
        raise ValueError("EXACT_TWO_BROWSER_PASSES_REQUIRED")
    specs: list[dict[str, Any]] = []

    def visit(suite: dict[str, Any]) -> None:
        specs.extend(suite.get("specs", []))
        for child in suite.get("suites", []):
            visit(child)

    for suite in report.get("suites", []):
        visit(suite)
    if len(specs) != 2 or {s["title"] for s in specs} != set(TITLES.values()):
        raise ValueError("EXACT_BROWSER_TITLE_SET_REQUIRED")
    for spec in specs:
        filename = Path(spec["file"]).name
        if TITLES.get(filename) != spec["title"] or spec.get("ok") is not True:
            raise ValueError("EXACT_BROWSER_TITLE_FILE_REQUIRED")
        tests = spec.get("tests", [])
        if len(tests) != 1 or tests[0].get("expectedStatus") != "passed":
            raise ValueError("ONE_REAL_RESULT_PER_BROWSER_TITLE_REQUIRED")
        results = tests[0].get("results", [])
        if (
            len(results) != 1
            or results[0].get("status") != "passed"
            or type(results[0].get("retry")) is not int
            or results[0]["retry"] != 0
        ):
            raise ValueError("BROWSER_RETRY_SKIP_OR_FAILURE_REFUSED")


def validate_receipts(case: "Case") -> dict[str, Any]:
    directory = Path(case.directory)
    receipts = {}
    for label in ("shell", "business"):
        path = directory / ("browser-" + label) / (label + ".safe.json")
        value = json.loads(private_bytes(path, 512000))
        if any(
            value.get(k) != expected
            for k, expected in {
                "source_sha": case.source_sha,
                "source_tree": case.source_tree,
                "scope": "LIVE_" + label.upper() + "_ONLY",
                "native200": "NOT_RUN_IN_THIS_SPEC",
            }.items()
        ):
            raise ValueError("BROWSER_RECEIPT_SOURCE_OR_SCOPE_MISMATCH")
        if label == "shell":
            screenshots = value.get("screenshots", [])
            expected_paths = [
                str(directory / "browser-shell" / f"shell-{n}.png") for n in (1440, 1280, 390)
            ]
            if [s["path"] for s in screenshots] != expected_paths or value.get(
                "actual_create_requests"
            ) != 1:
                raise ValueError("BROWSER_SHELL_SCREENSHOT_SET_MISMATCH")
            for shot in screenshots:
                if (
                    hashlib.sha256(private_bytes(Path(shot["path"]), 8_000_000)).hexdigest()
                    != shot["sha256"]
                ):
                    raise ValueError("BROWSER_SCREENSHOT_HASH_MISMATCH")
        receipts[label] = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    return receipts


def import_journals(case: "Case") -> dict[str, Any]:
    """Only after every browser writer stops; retain valid intents even after a later bad line."""
    directory = Path(case.directory)
    report: dict[str, Any] = {"journals": {}, "errors": []}
    for label in ("shell", "business"):
        path = directory / ("browser-" + label + ".subjects.private.jsonl")
        seen: set[tuple[str, str, str]] = set()
        imported = 0
        try:
            raw = private_subject_bytes(path)
            report["journals"][label] = {"sha256": hashlib.sha256(raw).hexdigest()}
            lines = raw.splitlines(keepends=True)
            if not 1 <= len(lines) <= 1000:
                raise ValueError("BOUNDED_NONEMPTY_BROWSER_JOURNAL_REQUIRED")
            for index, line in enumerate(lines):
                try:
                    if not line.endswith(b"\n"):
                        raise ValueError("INCOMPLETE_BROWSER_INTENT_LINE")
                    event = decode(line)
                    if set(event) != {
                        "schema",
                        "source_sha",
                        "source_tree",
                        "context",
                        "shop_id",
                        "operation",
                        "request_key",
                        "state",
                        "request",
                    } or any(
                        event[k] != expected
                        for k, expected in {
                            "schema": "v41-browser-subject-event-1",
                            "source_sha": case.source_sha,
                            "source_tree": case.source_tree,
                        }.items()
                    ):
                        raise ValueError("BROWSER_JOURNAL_SOURCE_OR_FIELDS_MISMATCH")
                    context = event["context"]
                    if set(context) != {
                        "tenant_id",
                        "organization_id",
                        "principal_id",
                        "reset_epoch",
                        "auth_generation",
                    } or any(
                        type(context[n]) is not int or context[n] < 0
                        for n in ("reset_epoch", "auth_generation")
                    ):
                        raise ValueError("BROWSER_JOURNAL_SCOPE_REQUIRED")
                    for n in ("tenant_id", "organization_id", "principal_id"):
                        if str(UUID(context[n])) != context[n]:
                            raise ValueError("BROWSER_CANONICAL_UUID_REQUIRED")
                    op, key, state = event["operation"], event["request_key"], event["state"]
                    identity = (json.dumps(context, sort_keys=True) + event["shop_id"], op, key)
                    if op is None:
                        if (
                            key is not None
                            or event["request"] is not None
                            or state != "ATTEMPT_STARTED"
                        ):
                            raise ValueError("BROWSER_SCOPE_EVENT_REQUIRED")
                    elif label == "shell":
                        raise ValueError("SHELL_MUST_NOT_WRITE_BUSINESS")
                    elif state == "ATTEMPT_STARTED":
                        if event["request"] is None:
                            raise ValueError("BROWSER_WRITE_AHEAD_REQUEST_REQUIRED")
                    elif identity not in seen or event["request"] is not None:
                        raise ValueError("BROWSER_ACK_WITHOUT_ORIGINAL_INTENT")
                    registry(
                        directory,
                        context,
                        event["shop_id"],
                        operation=op,
                        key=key,
                        state=state,
                        request=event["request"],
                    )
                    if op is not None:
                        seen.add(identity)
                    imported += 1
                except Exception as error:
                    report["errors"].append(
                        {"label": label, "line": index + 1, "type": type(error).__name__}
                    )
            report["journals"][label]["imported"] = imported
        except Exception as error:
            report["errors"].append({"label": label, "type": type(error).__name__})
    return report


def owned_browser_processes(output: str, directory: Path, executable: str) -> list[dict[str, int]]:
    """Fresh exclusive TMPDIR plus exact binary/current UID; never a system browser profile."""
    profile = re.compile(
        r"(?:^| )--user-data-dir="
        + re.escape(str(directory / "browser-tmp"))
        + r"/playwright_chromiumdev_profile-[^ /]+(?: |$)"
    )
    matching = []
    for line in output.splitlines():
        parts = line.strip().split(None, 3)
        if len(parts) == 4 and profile.search(parts[3]):
            matching.append((int(parts[0]), int(parts[1]), int(parts[2]), parts[3]))
    leaders = {
        pid
        for pid, uid, group, argv in matching
        if uid == os.getuid() and group == pid and argv.startswith(executable + " ")
    }
    if any(uid != os.getuid() or group not in leaders for _, uid, group, _ in matching):
        raise ValueError("BROWSER_RESIDUAL_IDENTITY_UNKNOWN")
    return [{"pid": pid, "pgid": pid} for pid in sorted(leaders)]


def stop_residuals(case: "Case", binding: dict[str, Any], budget: Budget) -> dict[str, Any]:
    """Independent after-writers inventory; any forced stop remains a failed run."""

    def inventory() -> list[dict[str, int]]:
        result = subprocess.run(
            ["/bin/ps", "-axo", "pid=,uid=,pgid=,command="],
            capture_output=True,
            text=True,
            env={},
            timeout=budget.timeout(2, cleanup=True),
            check=False,
        )
        if result.returncode or result.stderr:
            raise ValueError("BROWSER_PROCESS_INVENTORY_UNKNOWN")
        return owned_browser_processes(result.stdout, Path(case.directory), binding["executable"])

    initial = inventory()
    for row in initial:
        # Recheck exact fresh profile/binary/UID/group immediately before every signal.
        for sig in (signal.SIGTERM, signal.SIGKILL):
            if row not in inventory():
                break
            os.killpg(row["pgid"], sig)
            until = time.monotonic() + budget.timeout(1, cleanup=True)
            while row in inventory() and time.monotonic() < until:
                time.sleep(0.02)
    remaining = inventory()
    return {"forced": initial, "remaining": remaining, "clean_exit": not initial and not remaining}


def main() -> None:
    from .owned_driver import Case, runtime_handoff

    if len(sys.argv) != 3 or sys.argv[1] != "--case":
        raise SystemExit(1)
    path = Path(sys.argv[2])
    case = Case(**json.loads(private_bytes(path)))
    case.validate(prepared=True)
    if path != Path(case.directory) / "case.json" or case.scenario != "shell_navigation":
        raise ValueError("FIXED_BROWSER_CASE_REQUIRED")
    auth = runtime_handoff(case)
    verify_source(ROOT)
    binding = runtime(case, auth["authorization_id"])
    os.umask(0o077)
    directory = Path(case.directory)
    for name in ("browser-home", "browser-tmp"):
        (directory / name).mkdir(mode=0o700)
    argv = command(case)
    env = {
        "PATH": str(ROOT / ".tools/node/bin") + ":/usr/bin:/bin",
        "HOME": str(directory / "browser-home"),
        "TMPDIR": str(directory / "browser-tmp"),
        "V41_CASE_FILE": str(path),
        "V41_CHROMIUM_EXECUTABLE": binding["executable"],
        "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1",
        "PLAYWRIGHT_BROWSERS_PATH": "0",
        "NEXT_TELEMETRY_DISABLED": "1",
    }
    os.execve(argv[0], argv, env)  # noqa: S606 -- fixed reviewed executable/argv, no shell.


if __name__ == "__main__":
    main()
