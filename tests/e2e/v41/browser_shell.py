"""Fixed two-spec host browser path, durable subject import and scoped residual checks."""

import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from tests.e2e.v4.supervisor import Budget

from .owner_setup import decode, private_bytes
from .runner import persist
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


def process_rows(output: str) -> list[dict[str, Any]]:
    rows = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split(None, 9)
        if len(parts) != 10:
            raise ValueError("BROWSER_PROCESS_INVENTORY_UNKNOWN")
        pid, ppid, uid, pgid = map(int, parts[:4])
        rows.append(
            {
                "pid": pid,
                "ppid": ppid,
                "uid": uid,
                "pgid": pgid,
                "birth": " ".join(parts[4:9]),
                "argv": parts[9],
            }
        )
    if len({r["pid"] for r in rows}) != len(rows):
        raise ValueError("BROWSER_PROCESS_IDENTITY_AMBIGUOUS")
    return rows


def inventory(budget: Budget, *, cleanup: bool = False) -> list[dict[str, Any]]:
    result = subprocess.run(
        ["/bin/ps", "-axo", "pid=,ppid=,uid=,pgid=,lstart=,command="],
        capture_output=True,
        text=True,
        env={"LC_ALL": "C"},
        timeout=budget.timeout(2, cleanup=cleanup),
        check=False,
    )
    if result.returncode or result.stderr:
        raise ValueError("BROWSER_PROCESS_INVENTORY_UNKNOWN")
    return process_rows(result.stdout)


def profile_pattern(directory: Path) -> re.Pattern[str]:
    return re.compile(
        r"(?:^| )--user-data-dir=("
        + re.escape(str(directory / "browser-tmp"))
        + r"/playwright_chromiumdev_profile-[^ /]+)(?: |$)"
    )


def observe_groups(
    rows: list[dict[str, Any]], directory: Path, executable: str, node: int, birth: str
) -> list[dict[str, Any]]:
    """Capture live detached browser groups only through the actual owned Node ancestry."""
    by_pid = {r["pid"]: r for r in rows}
    if node not in by_pid or by_pid[node]["birth"] != birth or by_pid[node]["uid"] != os.getuid():
        raise ValueError("OWNED_BROWSER_NODE_IDENTITY_UNKNOWN")
    groups = []
    for leader in rows:
        match = profile_pattern(directory).search(leader["argv"])
        if match is None or leader["pid"] != leader["pgid"]:
            continue
        if leader["uid"] != os.getuid() or not leader["argv"].startswith(executable + " "):
            raise ValueError("BROWSER_GROUP_LEADER_IDENTITY_UNKNOWN")
        ancestor, seen = leader["ppid"], set()
        while ancestor != node:
            if ancestor in seen or ancestor not in by_pid or by_pid[ancestor]["uid"] != os.getuid():
                raise ValueError("BROWSER_GROUP_ANCESTRY_UNKNOWN")
            seen.add(ancestor)
            ancestor = by_pid[ancestor]["ppid"]
        members = [
            {k: r[k] for k in ("pid", "uid", "birth")} for r in rows if r["pgid"] == leader["pgid"]
        ]
        if len(members) > 128 or any(m["uid"] != os.getuid() for m in members):
            raise ValueError("BROWSER_GROUP_MEMBERS_UNKNOWN")
        groups.append(
            {
                "kind": "GROUP",
                "pid": leader["pid"],
                "pgid": leader["pgid"],
                "birth": leader["birth"],
                "profile": match[1],
                "members": members,
            }
        )
    return groups


def load_groups(case: "Case", binding: dict[str, Any], probe_pid: int) -> dict[int, dict[str, Any]]:
    raw = private_subject_bytes(Path(case.directory) / "browser-groups.private.jsonl")
    lines = raw.splitlines(keepends=True)
    if not 2 <= len(lines) <= 130 or any(not line.endswith(b"\n") for line in lines):
        raise ValueError("BROWSER_GROUP_JOURNAL_INCOMPLETE")
    records = [decode(line) for line in lines]
    header = {
        "kind": "START",
        "source_sha": case.source_sha,
        "source_tree": case.source_tree,
        "directory": case.directory,
        "wrapper_pid": probe_pid,
        "uid": os.getuid(),
        "binary_sha256": binding["sha256"],
    }
    if records[0] != header:
        raise ValueError("BROWSER_GROUP_JOURNAL_BINDING_MISMATCH")
    groups: dict[int, dict[str, Any]] = {}
    for record in records[1:]:
        if (
            set(record) != {"kind", "pid", "pgid", "birth", "profile", "members"}
            or record["kind"] != "GROUP"
        ):
            raise ValueError("BROWSER_GROUP_RECORD_REQUIRED")
        pid = record["pid"]
        if (
            type(pid) is not int
            or pid <= 0
            or type(record["pgid"]) is not int
            or record["pgid"] != pid
            or not isinstance(record["birth"], str)
            or not 10 < len(record["birth"]) < 40
            or profile_pattern(Path(case.directory)).fullmatch(
                "--user-data-dir=" + record["profile"]
            )
            is None
        ):
            raise ValueError("BROWSER_GROUP_ORIGINAL_IDENTITY_REQUIRED")
        members = record["members"]
        if not isinstance(members, list) or not 1 <= len(members) <= 128:
            raise ValueError("BROWSER_GROUP_ORIGINAL_MEMBERS_REQUIRED")
        group = groups.setdefault(pid, {**record, "members": {}})
        if (group["birth"], group["profile"]) != (record["birth"], record["profile"]):
            raise ValueError("BROWSER_GROUP_ID_REUSED")
        for member in members:
            if (
                set(member) != {"pid", "uid", "birth"}
                or type(member["pid"]) is not int
                or member["pid"] <= 0
                or member["uid"] != os.getuid()
                or not isinstance(member["birth"], str)
                or not 10 < len(member["birth"]) < 40
            ):
                raise ValueError("BROWSER_GROUP_MEMBER_IDENTITY_REQUIRED")
            previous = group["members"].setdefault(member["pid"], member)
            if previous != member:
                raise ValueError("BROWSER_GROUP_MEMBER_ID_REUSED")
        if group["members"].get(pid, {}).get("birth") != record["birth"]:
            raise ValueError("BROWSER_GROUP_LIVE_LEADER_PROOF_REQUIRED")
    if not groups:
        raise ValueError("BROWSER_GROUP_OWNERSHIP_NOT_CAPTURED")
    return groups


def group_members(
    rows: list[dict[str, Any]], groups: dict[int, dict[str, Any]], directory: Path
) -> list[dict[str, Any]]:
    for row in rows:
        if profile_pattern(directory).search(row["argv"]) and row["pgid"] not in groups:
            raise ValueError("BROWSER_UNREGISTERED_PROFILE_GROUP")
    members = []
    for pgid, group in groups.items():
        current = [r for r in rows if r["pgid"] == pgid]
        if current and not any(
            group["members"].get(r["pid"], {}).get("birth") == r["birth"] for r in current
        ):
            raise ValueError("BROWSER_GROUP_CONTINUITY_UNKNOWN")
        for row in current:
            previous = group["members"].get(row["pid"])
            if (
                row["uid"] != os.getuid()
                or previous is not None
                and row["birth"] != previous["birth"]
            ):
                raise ValueError("BROWSER_GROUP_MEMBER_IDENTITY_CHANGED")
            members.append({k: row[k] for k in ("pid", "uid", "pgid", "birth")})
    return members


def stop_residuals(
    case: "Case", binding: dict[str, Any], budget: Budget, probe_pid: int
) -> dict[str, Any]:
    """Full previously observed groups, including orphaned children without profile arguments."""
    groups = load_groups(case, binding, probe_pid)
    empty: set[int] = set()

    def current() -> list[dict[str, Any]]:
        rows = group_members(inventory(budget, cleanup=True), groups, Path(case.directory))
        if any(r["pgid"] in empty for r in rows):
            raise ValueError("BROWSER_EMPTIED_GROUP_REAPPEARED")
        empty.update(pgid for pgid in groups if not any(r["pgid"] == pgid for r in rows))
        return rows

    initial = current()
    for pgid in sorted({r["pgid"] for r in initial}):
        for sig in (signal.SIGTERM, signal.SIGKILL):
            if not any(r["pgid"] == pgid for r in current()):
                break
            # Unknown or reused identities raise before signaling the original continuous group.
            os.killpg(pgid, sig)
            until = time.monotonic() + budget.timeout(1, cleanup=True)
            while any(r["pgid"] == pgid for r in current()) and time.monotonic() < until:
                time.sleep(0.02)
    remaining = current()
    return {
        "forced": initial,
        "remaining": remaining,
        "clean_exit": not initial and not remaining,
        "registered_groups": sorted(groups),
    }


def run_browser(
    case: "Case", binding: dict[str, Any], argv: tuple[str, ...], env: dict[str, str]
) -> int:
    budget = Budget.bind(
        datetime.fromisoformat(case.starts_at), datetime.fromisoformat(case.deadline)
    )
    path = Path(case.directory) / "browser-groups.private.jsonl"
    with path.open("xb") as journal:
        path.chmod(0o600)
        count = 0

        def append(record: dict[str, Any]) -> None:
            nonlocal count
            raw = (json.dumps(record, sort_keys=True) + "\n").encode()
            if count >= 130 or journal.tell() + len(raw) > 512000:
                raise ValueError("BROWSER_GROUP_JOURNAL_BOUND")
            journal.write(raw)
            journal.flush()
            os.fsync(journal.fileno())
            count += 1

        append(
            {
                "kind": "START",
                "source_sha": case.source_sha,
                "source_tree": case.source_tree,
                "directory": case.directory,
                "wrapper_pid": os.getpid(),
                "uid": os.getuid(),
                "binary_sha256": binding["sha256"],
            }
        )
        # Node inherits the Supervisor wrapper group; capture detached Chromium groups below.
        child = subprocess.Popen(argv, cwd=ROOT, env=env, stdin=subprocess.DEVNULL)
        seen: dict[int, dict[str, Any]] = {}
        node_birth: str | None = None
        try:
            while child.poll() is None:
                rows = inventory(budget)
                if child.poll() is not None:
                    break
                node = next((r for r in rows if r["pid"] == child.pid), None)
                if node is None:
                    raise ValueError("OWNED_BROWSER_NODE_NOT_OBSERVED")
                if node_birth is None:
                    node_birth = node["birth"]
                for group in observe_groups(
                    rows, Path(case.directory), binding["executable"], child.pid, node_birth
                ):
                    old = seen.get(group["pgid"])
                    if old is not None and old["birth"] != group["birth"]:
                        raise ValueError("BROWSER_GROUP_ID_REUSED")
                    if old != group:
                        append(group)
                        seen[group["pgid"]] = group
                time.sleep(min(0.05, budget.timeout(0.05)))
            return child.wait(timeout=budget.timeout(2, cleanup=True))
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=budget.timeout(2, cleanup=True))
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=budget.timeout(2, cleanup=True))
            persist(
                Path(case.directory) / "browser-node.exit.private.json",
                {
                    "source_sha": case.source_sha,
                    "source_tree": case.source_tree,
                    "pid": child.pid,
                    "birth": node_birth,
                    "native_exit": child.returncode,
                    "scope": "OWNED_NODE_CLI_CHILD",
                },
            )


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
    raise SystemExit(run_browser(case, binding, argv, env))


if __name__ == "__main__":
    main()
