"""Fixed two-spec host browser path, durable subject import and scoped residual checks."""

import hashlib
import json
import math
import os
import re
import signal
import stat
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from commerceops.application.v41.contracts import Snapshot

from tests.e2e.v4.supervisor import Budget

from .owner_setup import decode, private_bytes
from .request_witness import server_request, validate_request
from .runner import persist
from .subjects import private_subject_bytes, registry

if TYPE_CHECKING:
    from .owned_driver import Case

ROOT = Path(__file__).resolve().parents[3]
TITLES = {
    "shell.live.spec.ts": "LIVE V41: shell identity navigation and responsive boundaries",
    "business.live.spec.ts": "LIVE V41: business reads writes and import roundtrip",
}
NATIVE_MODULE_SHA256 = "295bf2c61e7cd30e7a47d7368d93fbadb40764fb41072a9119b5d78ed925689e"
NATIVE_STATUS = "NATIVE_ZOOM_CAPTURED_PENDING_VISUAL_REVIEW"
SOURCE_PATHS = (
    "tests/e2e/v41/native_zoom.cjs",
    "frontend/v41-e2e/native-capture.ts",
    "frontend/v41-e2e/owned-cdp.fixture.ts",
    "frontend/v41-e2e/owned-cdp.argv.json",
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
        if (
            name == "tests/e2e/v41/native_zoom.cjs"
            and hashlib.sha256(committed).hexdigest() != NATIVE_MODULE_SHA256
        ):
            raise ValueError("REVIEWED_NATIVE_MODULE_REQUIRED")


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
    pins = {
        "executable",
        "sha256",
        "framework",
        "framework_sha256",
        "node_sha256",
        "playwright_version",
    }
    if set(record) != set(expected) | pins or any(record[k] != v for k, v in expected.items()):
        raise ValueError("ROOT_EXACT_BROWSER_RUNTIME_REQUIRED")
    runtime_tools(record)
    return dict(record)


def runtime_tools(record: dict[str, Any]) -> dict[str, str]:
    if record.get("playwright_version") != "1.64.0":
        raise ValueError("ROOT_FIXED_PLAYWRIGHT_VERSION_REQUIRED")
    tools = {}
    for name, digest, executable in (
        (record["executable"], record["sha256"], True),
        (record["framework"], record["framework_sha256"], False),
        (str((ROOT / ".tools/node/bin/node").resolve()), record["node_sha256"], True),
    ):
        path = Path(name)
        if (
            not path.is_absolute()
            or path.resolve() != path
            or not path.is_file()
            or executable
            and not os.access(path, os.X_OK)
            or not isinstance(digest, str)
            or not re.fullmatch(r"[a-f0-9]{64}", digest)
            or hashlib.sha256(path.read_bytes()).hexdigest() != digest
        ):
            raise ValueError("ROOT_BROWSER_BINARY_HASH_MISMATCH")
        tools[str(path)] = digest
    package = (ROOT / "frontend/node_modules/playwright/package.json").resolve(strict=True)
    if json.loads(package.read_bytes()).get("version") != record["playwright_version"]:
        raise ValueError("ROOT_FIXED_PLAYWRIGHT_VERSION_REQUIRED")
    tools[str(package)] = hashlib.sha256(package.read_bytes()).hexdigest()
    return tools


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


def validate_receipts(case: "Case", binding: dict[str, Any]) -> dict[str, Any]:
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
                **({"native200": "NOT_RUN_IN_THIS_SPEC"} if label == "business" else {}),
            }.items()
        ):
            raise ValueError("BROWSER_RECEIPT_SOURCE_OR_SCOPE_MISMATCH")
        if label == "shell":
            receipts["shell_cdp"] = validate_shell_cdp(case)
            validate_native_receipt(case, binding, value.get("native200"))
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
        if label == "business":
            receipts["business_mobile"] = validate_business_mobile(case, value)
        receipts[label] = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    return receipts


def validate_native_receipt(case: "Case", binding: dict[str, Any], summary: Any) -> None:
    directory = Path(case.directory) / "native-zoom"
    receipt_path = directory / "receipt.json"
    if (
        not isinstance(summary, dict)
        or set(summary)
        != {"status", "receiptPath", "nativeBrowserExit", "visualAcceptance", "receiptSha256"}
        or any(
            summary[k] != value
            for k, value in {
                "status": NATIVE_STATUS,
                "receiptPath": str(receipt_path),
                "nativeBrowserExit": "NOT_EXPOSED",
                "visualAcceptance": "PENDING_REVIEW",
            }.items()
        )
    ):
        raise ValueError("NATIVE_CAPTURE_PENDING_REVIEW_REQUIRED")
    raw = private_bytes(receipt_path, 2_000_000)
    receipt = decode(raw)
    expected_source = {
        "head": case.source_sha,
        "tree": case.source_tree,
        "moduleSha256": NATIVE_MODULE_SHA256,
        "inputs": case.inputs,
    }
    tools = runtime_tools(binding)
    if (
        hashlib.sha256(raw).hexdigest() != summary["receiptSha256"]
        or receipt.get("source") != expected_source
        or receipt.get("tools") != tools
        or receipt.get("status") != NATIVE_STATUS
        or receipt.get("scope") != "SAME_SHELL_VISITOR_READONLY_NATIVE_200"
        or receipt.get("nativeBrowserExit") != "NOT_EXPOSED"
        or receipt.get("humanVisualAcceptance") != "NOT_RUN"
        or receipt.get("failure")
    ):
        raise ValueError("NATIVE_RECEIPT_IDENTITY_OR_STATUS_MISMATCH")
    cleanup = receipt.get("cleanup", {})
    if (
        cleanup.get("confirmed") is not True
        or cleanup.get("forced", False) is not False
        or cleanup.get("emergencyEvents", []) != []
        or cleanup.get("profileProcesses") != []
        or cleanup.get("registeredAlive") != []
        or cleanup.get("sourceAfter") != expected_source
        or cleanup.get("toolsAfter") != tools
        or cleanup.get("failure")
        or cleanup.get("closeFailure")
    ):
        raise ValueError("NATIVE_CLEANUP_NOT_CONFIRMED")
    if receipt.get("profile") != {
        "path": str(
            Path(case.directory) / "browser-tmp" / "playwright_chromiumdev_profile-native200"
        ),
        "mode": 0o700,
        "uid": case.uid,
    }:
        raise ValueError("NATIVE_PROFILE_CAPTURE_SCOPE_MISMATCH")
    requests = receipt.get("requests", {})
    if (
        type(requests.get("allowedReads")) is not int
        or requests["allowedReads"] <= 0
        or requests.get("refused") != []
    ):
        raise ValueError("NATIVE_READONLY_CAPTURE_REQUIRED")
    pages = receipt.get("pages", [])
    if not isinstance(pages, list) or [p["label"] for p in pages] != ["dashboard", "products"]:
        raise ValueError("NATIVE_FIXED_PAGE_SET_REQUIRED")
    for page in pages:
        before, after = page["before"], page["after"]
        baseline, zoom = page["baseline"], page["zoom"]
        if (
            page["pathname"] != "/v4/" + page["label"]
            or type(page["rowCount"]) is not int
            or page["rowCount"] <= 0
            or baseline["actual"] != 1
            or zoom["actual"] != 2
            or type(zoom["tabId"]) is not int
            or baseline["tabId"] != zoom["tabId"]
            or not any(
                e.get("tabId") == zoom["tabId"]
                and e.get("oldZoomFactor") == 1
                and e.get("newZoomFactor") == 2
                for e in zoom["events"]
            )
        ):
            raise ValueError("NATIVE_FACTOR_EVENT_REQUIRED")
        for value in (baseline, zoom):
            if (
                value["settings"].get("mode") != "automatic"
                or value["settings"].get("scope") != "per-tab"
            ):
                raise ValueError("NATIVE_BROWSER_PER_TAB_REQUIRED")
        for geometry in (before, after):
            for key in ("innerWidth", "innerHeight", "devicePixelRatio"):
                if (
                    isinstance(geometry[key], bool)
                    or not isinstance(geometry[key], (int, float))
                    or not math.isfinite(geometry[key])
                    or geometry[key] <= 0
                ):
                    raise ValueError("NATIVE_FINITE_GEOMETRY_REQUIRED")
            if geometry["outerWidth"] != 1440 or geometry["outerHeight"] != 1000:
                raise ValueError("NATIVE_ACTUAL_WINDOW_GEOMETRY_REQUIRED")
            for css in (geometry["rootCss"], geometry["bodyCss"]):
                if css["zoom"] not in {"1", "normal"} or css["transform"] != "none":
                    raise ValueError("NATIVE_CSS_SIMULATION_REFUSED")
        if (
            abs(after["innerWidth"] * 2 - before["innerWidth"]) > 2
            or abs(after["innerHeight"] * 2 - before["innerHeight"]) > 2
            or abs(after["devicePixelRatio"] - before["devicePixelRatio"] * 2) > 0.000001
        ):
            raise ValueError("NATIVE_LAYOUT_SCALE_MISMATCH")
        names = [page["label"] + "-100.png", page["label"] + "-200.png"]
        if page["label"] == "products":
            names.append("products-200-bottom.png")
        if [shot["path"] for shot in page["screenshots"]] != ["screenshots/" + n for n in names]:
            raise ValueError("NATIVE_FIXED_PNG_SET_REQUIRED")
        for index, shot in enumerate(page["screenshots"]):
            image = private_bytes(directory / shot["path"], 8_000_000)
            width, height = int.from_bytes(image[16:20]), int.from_bytes(image[20:24])
            geometry = before if index == 0 else after
            if (
                len(image) < 24
                or image[:8] != bytes((137, 80, 78, 71, 13, 10, 26, 10))
                or hashlib.sha256(image).hexdigest() != shot["sha256"]
                or (width, height) != (shot["pixelWidth"], shot["pixelHeight"])
                or abs(width - geometry["innerWidth"] * geometry["devicePixelRatio"]) > 2
                or abs(height - geometry["innerHeight"] * geometry["devicePixelRatio"]) > 2
            ):
                raise ValueError("NATIVE_PNG_BYTES_OR_GEOMETRY_MISMATCH")


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
    shell_cdp_ports_closed(case, budget)
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
                register_shell_cdp(case, binding, budget, child.pid, node_birth)
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


SHELL_CDP_FIELDS = (
    "source_sha",
    "source_tree",
    "case_sha256",
    "runtime_sha256",
    "directory",
    "uid",
    "worker_pid",
    "worker_birth",
    "nonce",
    "profile",
)


def shell_cdp_intent(case: "Case") -> dict[str, Any] | None:
    directory = Path(case.directory) / "browser-shell-cdp"
    path = directory / "intent.private.json"
    if not path.exists():
        return None
    info = directory.lstat()
    if (
        directory.resolve() != directory
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != case.uid
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise ValueError("SHELL_CDP_PRIVATE_DIRECTORY_REQUIRED")
    value = decode(private_bytes(path))
    expected = {
        "schema": "v41-shell-cdp-intent-v1",
        "source_sha": case.source_sha,
        "source_tree": case.source_tree,
        "directory": case.directory,
        "uid": case.uid,
        "case_sha256": hashlib.sha256(
            private_bytes(Path(case.directory) / "case.json")
        ).hexdigest(),
        "runtime_sha256": hashlib.sha256(
            private_bytes(Path(case.directory) / "browser-runtime.safe.json")
        ).hexdigest(),
        "title": TITLES["shell.live.spec.ts"],
    }
    if set(value) != set(SHELL_CDP_FIELDS) | {"schema", "title", "executable", "argv"} or any(
        value.get(k) != v for k, v in expected.items()
    ):
        raise ValueError("SHELL_CDP_INTENT_BINDING_MISMATCH")
    nonce = value["nonce"]
    if not isinstance(nonce, str) or str(UUID(nonce)) != nonce:
        raise ValueError("SHELL_CDP_NONCE_REQUIRED")
    profile = (
        Path(case.directory) / "browser-tmp" / ("playwright_chromiumdev_profile-shell-cdp-" + nonce)
    )
    pi = profile.lstat()
    if (
        value["profile"] != str(profile)
        or profile.resolve() != profile
        or not stat.S_ISDIR(pi.st_mode)
        or pi.st_uid != case.uid
        or stat.S_IMODE(pi.st_mode) != 0o700
    ):
        raise ValueError("SHELL_CDP_PROFILE_IDENTITY_REQUIRED")
    if (
        type(value["worker_pid"]) is not int
        or value["worker_pid"] <= 0
        or not isinstance(value["worker_birth"], str)
    ):
        raise ValueError("SHELL_CDP_WORKER_IDENTITY_REQUIRED")
    return value


def shell_cdp_listener(port: int, budget: Budget, *, cleanup: bool = False) -> list[dict[str, Any]]:
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("SHELL_CDP_EXACT_PORT_REQUIRED")
    result = subprocess.run(
        ["/usr/sbin/lsof", "-nP", "-iTCP:" + str(port), "-sTCP:LISTEN", "-Fpcn"],
        capture_output=True,
        text=True,
        env={"LC_ALL": "C"},
        timeout=budget.timeout(2, cleanup=cleanup),
        check=False,
    )
    if result.returncode == 1 and not result.stdout.strip() and not result.stderr.strip():
        return []
    if result.returncode or result.stderr.strip():
        raise ValueError("SHELL_CDP_LISTENER_UNKNOWN")
    records = []
    pid = None
    for line in result.stdout.splitlines():
        if line.startswith("p"):
            if not line[1:].isdigit():
                raise ValueError("SHELL_CDP_LISTENER_PID_UNKNOWN")
            pid = int(line[1:])
        elif line.startswith("n"):
            if pid is None:
                raise ValueError("SHELL_CDP_LISTENER_PID_MISSING")
            records.append({"pid": pid, "address": line[1:]})
    if not records:
        raise ValueError("SHELL_CDP_LISTENER_RECORDS_UNKNOWN")
    return records


def shell_cdp_endpoint(profile: Path, uid: int) -> tuple[int, str, str]:
    path = profile / "DevToolsActivePort"
    if path.resolve() != path:
        raise ValueError("SHELL_CDP_ENDPOINT_SYMLINK_REFUSED")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != uid or info.st_mode & 0o022:
            raise ValueError("SHELL_CDP_ENDPOINT_OWNER_MODE_REQUIRED")
        raw = stream.read(1025)
    lines = raw.decode("ascii").splitlines()
    if (
        len(raw) > 1024
        or len(lines) != 2
        or re.fullmatch(r"[1-9][0-9]{0,4}", lines[0]) is None
        or not 1 <= int(lines[0]) <= 65535
        or re.fullmatch(r"/devtools/browser/[A-Za-z0-9-]+", lines[1]) is None
    ):
        raise ValueError("SHELL_CDP_ENDPOINT_NONCANONICAL")
    return int(lines[0]), lines[1], hashlib.sha256(raw).hexdigest()


def register_shell_cdp(
    case: "Case", binding: dict[str, Any], budget: Budget, node: int, birth: str
) -> None:
    intent = shell_cdp_intent(case)
    if intent is None:
        return
    directory = Path(case.directory) / "browser-shell-cdp"
    if (directory / "endpoint-ack.safe.json").exists():
        return  # Immutable original acknowledgement; never replace or extend.
    spawn_path = directory / "spawn.private.json"
    if not spawn_path.exists():
        return
    spawned = decode(private_bytes(spawn_path))
    expected = {k: intent[k] for k in SHELL_CDP_FIELDS}
    if (
        set(spawned) != set(expected) | {"schema", "native_pid"}
        or spawned.get("schema") != "v41-shell-cdp-spawn-v1"
        or any(spawned.get(k) != v for k, v in expected.items())
        or type(spawned["native_pid"]) is not int
    ):
        raise ValueError("SHELL_CDP_SPAWN_BINDING_MISMATCH")
    rows = inventory(budget)
    by_pid = {r["pid"]: r for r in rows}
    worker = by_pid.get(intent["worker_pid"])
    if worker is None or worker["birth"] != intent["worker_birth"] or worker["uid"] != case.uid:
        raise ValueError("SHELL_CDP_WORKER_BIRTH_UNKNOWN")
    cursor, visited = worker["pid"], set()
    while cursor != node:
        if cursor in visited or cursor not in by_pid or by_pid[cursor]["uid"] != case.uid:
            raise ValueError("SHELL_CDP_WORKER_ANCESTRY_UNKNOWN")
        visited.add(cursor)
        cursor = by_pid[cursor]["ppid"]
    groups = observe_groups(rows, Path(case.directory), binding["executable"], node, birth)
    groups = [g for g in groups if g["profile"] == intent["profile"]]
    if not groups:
        return
    if len(groups) != 1 or groups[0]["pid"] != spawned["native_pid"]:
        raise ValueError("SHELL_CDP_NATIVE_GROUP_MISMATCH")
    group = groups[0]
    leader = by_pid[group["pid"]]
    args = [
        arg.replace("<OWNED_SHELL_PROFILE>", intent["profile"])
        for arg in json.loads((ROOT / "frontend/v41-e2e/owned-cdp.argv.json").read_bytes())
    ]
    if (
        leader["ppid"] != worker["pid"]
        or intent["executable"] != binding["executable"]
        or intent["argv"] != args
        or leader["argv"] != binding["executable"] + " " + " ".join(args)
    ):
        raise ValueError("SHELL_CDP_FIXED_NATIVE_ARGV_REQUIRED")
    registration = {
        **expected,
        "native_pid": group["pid"],
        "native_birth": group["birth"],
        "pgid": group["pgid"],
        "members": group["members"],
        "actual_argv": leader["argv"],
    }
    registered_path = directory / "registered.private.json"
    if not registered_path.exists():
        persist(registered_path, {"schema": "v41-shell-cdp-registered-v1", **registration})
    active = Path(intent["profile"]) / "DevToolsActivePort"
    if not active.exists():
        return
    port, browser_path, file_sha = shell_cdp_endpoint(Path(intent["profile"]), case.uid)
    listeners = shell_cdp_listener(port, budget)
    if not listeners:
        return
    if any(r != {"pid": group["pid"], "address": "127.0.0.1:" + str(port)} for r in listeners):
        raise ValueError("SHELL_CDP_EXCLUSIVE_OWNED_LOOPBACK_REQUIRED")
    current = next((r for r in inventory(budget) if r["pid"] == leader["pid"]), None)
    if current != leader:
        raise ValueError("SHELL_CDP_NATIVE_IDENTITY_CHANGED")
    persist(
        directory / "endpoint-ack.safe.json",
        {
            "schema": "v41-shell-cdp-ack-v1",
            **registration,
            "host": "127.0.0.1",
            "port": port,
            "browser_path": browser_path,
            "devtools_file_sha256": file_sha,
            "listeners": listeners,
        },
    )


def validate_shell_cdp(case: "Case") -> dict[str, Any]:
    intent = shell_cdp_intent(case)
    if intent is None:
        raise ValueError("SHELL_CDP_INTENT_NOT_CAPTURED")
    directory = Path(case.directory) / "browser-shell-cdp"
    ack_raw = private_bytes(directory / "endpoint-ack.safe.json")
    ack = decode(ack_raw)
    closeout = decode(private_bytes(directory / "closeout.safe.json"))
    expected = {k: intent[k] for k in SHELL_CDP_FIELDS}
    if (
        any(ack.get(k) != v or closeout.get(k) != v for k, v in expected.items())
        or ack.get("schema") != "v41-shell-cdp-ack-v1"
        or ack.get("host") != "127.0.0.1"
        or closeout.get("schema") != "v41-shell-cdp-closeout-v1"
    ):
        raise ValueError("SHELL_CDP_RECEIPT_BINDING_MISMATCH")
    if (
        closeout.get("native_pid") != ack.get("native_pid")
        or closeout.get("ack_sha256") != hashlib.sha256(ack_raw).hexdigest()
        or closeout.get("status") != "NATIVE_CLOSED_PENDING_PARENT_CHECK"
        or closeout.get("close_ack") is not True
        or type(closeout.get("native_exit")) is not int
        or closeout["native_exit"] != 0
        or closeout.get("signal") is not None
        or closeout.get("failures") != []
        or closeout.get("close_failure") is not None
    ):
        raise ValueError("SHELL_CDP_NATIVE_CLOSURE_NOT_CONFIRMED")
    page_raw = private_bytes(directory / "page-binding.safe.json")
    page = decode(page_raw)
    if (
        any(page.get(k) != v for k, v in expected.items())
        or page.get("schema") != "v41-shell-cdp-page-v1"
        or page.get("native_pid") != ack.get("native_pid")
        or page.get("ack_sha256") != hashlib.sha256(ack_raw).hexdigest()
        or closeout.get("page_binding_sha256") != hashlib.sha256(page_raw).hexdigest()
        or not isinstance(page.get("target_id"), str)
        or not page["target_id"]
        or type(page.get("window_id")) is not int
        or page.get("transport") != "OWNED_DEFAULT_CONTEXT_CDP"
        or page.get("no_defaults") is not True
        or page.get("initial_url") != "about:blank"
        or page.get("context_count") != 1
        or page.get("page_count") != 1
        or type(page.get("context_id_present")) is not bool
        or (
            page["context_id_present"]
            and (not isinstance(page.get("context_id"), str) or not page["context_id"])
        )
        or (not page["context_id_present"] and page.get("context_id") is not None)
    ):
        raise ValueError("SHELL_CDP_PAGE_PROOF_REQUIRED")
    native = decode(private_bytes(directory / "native-exit.private.json"))
    if (
        native.get("schema") != "v41-shell-cdp-native-exit-v1"
        or any(native.get(k) != v for k, v in expected.items())
        or native.get("native_pid") != ack.get("native_pid")
        or type(native.get("native_exit")) is not int
        or native["native_exit"] != 0
        or native.get("signal") is not None
    ):
        raise ValueError("SHELL_CDP_NATIVE_EXIT_NOT_CAPTURED")
    return {
        "path": str(directory / "closeout.safe.json"),
        "sha256": hashlib.sha256(private_bytes(directory / "closeout.safe.json")).hexdigest(),
    }


def shell_cdp_ports_closed(case: "Case", budget: Budget) -> None:
    intent = shell_cdp_intent(case)
    if intent is None:
        return
    ack = decode(private_bytes(Path(case.directory) / "browser-shell-cdp/endpoint-ack.safe.json"))
    if (
        any(ack.get(k) != intent[k] for k in SHELL_CDP_FIELDS)
        or ack.get("schema") != "v41-shell-cdp-ack-v1"
    ):
        raise ValueError("SHELL_CDP_CLEANUP_ENDPOINT_UNKNOWN")
    if shell_cdp_listener(ack["port"], budget, cleanup=True):
        raise ValueError("SHELL_CDP_PORT_LIVE_OR_REUSED_NO_SIGNAL")


MOBILE_STATES = {
    "product_list",
    "product_detail",
    "tag_edit",
    "order_list",
    "order_detail",
    "fulfillment_confirm",
    "csv_mapping",
    "xlsx_mapping",
}
MOBILE_EXTRAS = {
    "anonymous_empty",
    "second_visitor_empty",
    "batch_confirm",
    "batch_readback",
    "tag_readback",
    "fulfillment_readback",
    "csv_readback",
    "xlsx_readback",
}
MOBILE_IDENTITY = ("tenant_id", "organization_id", "principal_id", "reset_epoch", "auth_generation")


def mobile_require(condition: Any, reason: str) -> None:
    if not condition:
        raise ValueError("BUSINESS_MOBILE_" + reason)


def mobile_scope(context: Any, shop: Any) -> tuple[Any, ...]:
    mobile_require(isinstance(context, dict) and set(context) == set(MOBILE_IDENTITY), "CONTEXT")
    for name in MOBILE_IDENTITY[:3]:
        mobile_require(
            isinstance(context[name], str) and str(UUID(context[name])) == context[name], "UUID"
        )
    for name in MOBILE_IDENTITY[3:]:
        mobile_require(type(context[name]) is int and context[name] >= 0, "IDENTITY_COUNTER")
    mobile_require(isinstance(shop, str) and str(UUID(shop)) == shop, "SHOP")
    return (*[context[name] for name in MOBILE_IDENTITY], shop)


def mobile_journal(case: "Case") -> tuple[set[tuple[Any, ...]], dict[str, dict[str, Any]]]:
    raw = private_subject_bytes(Path(case.directory) / "browser-business.subjects.private.jsonl")
    lines = raw.splitlines(keepends=True)
    mobile_require(
        lines and len(lines) <= 1000 and all(line.endswith(b"\n") for line in lines),
        "JOURNAL_BOUND",
    )
    scopes: set[tuple[Any, ...]] = set()
    entries: dict[str, dict[str, Any]] = {}
    for line in lines:
        event = decode(line)
        mobile_require(
            event.get("schema") == "v41-browser-subject-event-1"
            and event.get("source_sha") == case.source_sha
            and event.get("source_tree") == case.source_tree,
            "JOURNAL_SOURCE",
        )
        scope = mobile_scope(event["context"], event["shop_id"])
        if event["operation"] is None:
            mobile_require(
                event["request_key"] is None
                and event["state"] == "ATTEMPT_STARTED"
                and event["request"] is None,
                "JOURNAL_SCOPE_EVENT",
            )
            scopes.add(scope)
            continue
        mobile_require(scope in scopes, "UNREGISTERED_SCOPE")
        key, operation, state = event["request_key"], event["operation"], event["state"]
        mobile_require(isinstance(key, str) and str(UUID(key)) == key, "KEY")
        mobile_require(
            operation in {"product_tags", "order_fulfillment", "preview", "import_confirm"},
            "OPERATION",
        )
        entry = entries.setdefault(
            key, {"scope": scope, "operation": operation, "states": [], "request": None}
        )
        mobile_require(
            entry["scope"] == scope and entry["operation"] == operation, "KEY_SCOPE_ALIAS"
        )
        if state == "ATTEMPT_STARTED":
            mobile_require(not entry["states"], "DUPLICATE_DISPATCH")
            entry["request"] = validate_request(
                event["request"],
                operation,
                key,
                {**event["context"], "shop_id": event["shop_id"]},
            )
        else:
            mobile_require(
                entry["request"] is not None and event["request"] is None, "ACK_WITHOUT_INTENT"
            )
        entry["states"].append(state)
    for entry in entries.values():
        states = entry["states"]
        allowed = (
            {"ACK_OK", "ACK_COMMITTED"} if entry["operation"] == "preview" else {"ACK_COMMITTED"}
        )
        mobile_require(
            len(states) == 3
            and states[0] == "ATTEMPT_STARTED"
            and states[1] in allowed
            and states[2] == "COMMITTED_READBACK",
            "UNSETTLED_OR_AMBIGUOUS_JOURNAL",
        )
    for entry in entries.values():
        if entry["operation"] == "preview":
            entry["file_digest"] = server_request(entry["request"], "preview")["file_digest"]
    return scopes, entries


def mobile_snapshot(value: Any) -> None:
    # Validate the frozen public DTO directly; do not manufacture missing wire fields.
    Snapshot.model_validate_json(json.dumps(value, allow_nan=False))


def mobile_same_source(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    fields = ("context", "shop_id", "snapshot", "job", "file_digest")
    mobile_require(
        set(actual) == set(fields) and actual == {name: expected[name] for name in fields},
        "SCREENSHOT_OPERATION_SOURCE",
    )


def mobile_screenshots(
    case: "Case", records: Any, scopes: set[tuple[Any, ...]]
) -> dict[tuple[str, int], dict[str, Any]]:
    mobile_require(isinstance(records, list) and len(records) <= 64, "SCREENSHOT_LIST")
    shots: dict[tuple[str, int], dict[str, Any]] = {}
    for record in records:
        state, width = record["state"], record["width"]
        mobile_require(
            state in MOBILE_STATES | MOBILE_EXTRAS
            and type(width) is int
            and width in {390, 1280, 1440},
            "SCREENSHOT_STATE",
        )
        pair = (state, width)
        mobile_require(pair not in shots, "DUPLICATE_SCREENSHOT")
        path = Path(case.directory) / "browser-business" / f"{state}-{width}.png"
        mobile_require(record["path"] == str(path) and path.resolve() == path, "SCREENSHOT_PATH")
        image = private_bytes(path, 8_000_000)
        mobile_require(
            len(image) >= 24
            and image[:8] == bytes((137, 80, 78, 71, 13, 10, 26, 10))
            and image[12:16] == b"IHDR"
            and hashlib.sha256(image).hexdigest() == record["sha256"],
            "PNG_BYTES_HASH",
        )
        pixels = (int.from_bytes(image[16:20]), int.from_bytes(image[20:24]))
        viewport = record["viewport"]
        dpr = viewport["dpr"]
        mobile_require(
            viewport["width"] == width
            and type(viewport["height"]) is int
            and viewport["height"] > 0
            and type(dpr) in {int, float}
            and math.isfinite(dpr)
            and dpr > 0,
            "VIEWPORT",
        )
        mobile_require(
            pixels == (record["pixel_width"], record["pixel_height"])
            and abs(pixels[0] - width * dpr) <= 1
            and pixels[1] >= viewport["height"] * dpr - 1,
            "PNG_GEOMETRY",
        )
        mobile_require(
            isinstance(record["route"], str) and record["route"].startswith("/v4/"), "ROUTE"
        )
        route = record["route"]
        if state in {"product_detail", "tag_edit", "tag_readback"}:
            mobile_require(re.fullmatch(r"/v4/products/[a-f0-9-]{36}", route), "PRODUCT_ROUTE")
        elif state in {"order_detail", "fulfillment_confirm", "fulfillment_readback"}:
            mobile_require(re.fullmatch(r"/v4/orders/[a-f0-9-]{36}", route), "ORDER_ROUTE")
        elif state in {"csv_mapping", "xlsx_mapping"}:
            mobile_require(route == "/v4/products/import", "IMPORT_ROUTE")
        else:
            mobile_require(
                route == ("/v4/orders" if state == "order_list" else "/v4/products"), "LIST_ROUTE"
            )
        source = record["source"]
        if state in {"anonymous_empty", "second_visitor_empty"}:
            mobile_require(
                width == 390
                and source.get("permission") == "anonymous"
                and source.get("revocation_tested") is False
                and source.get("context") is None
                and source.get("shop_id") is None,
                "ANONYMOUS_NOT_REVOCATION",
            )
        else:
            mobile_require(
                mobile_scope(source["context"], source["shop_id"]) in scopes, "SCREENSHOT_SCOPE"
            )
            mobile_require(
                isinstance(source.get("snapshot"), dict) or isinstance(source.get("job"), dict),
                "SCREENSHOT_SOURCE",
            )
        if source.get("snapshot") is not None:
            mobile_snapshot(source["snapshot"])
        shots[pair] = record
    required = {(state, width) for state in MOBILE_STATES for width in (390, 1280, 1440)} | {
        (state, 390) for state in MOBILE_EXTRAS
    }
    mobile_require(set(shots) == required, "MISSING_SCREENSHOT_COVERAGE")
    return shots


def validate_business_mobile(case: "Case", value: dict[str, Any]) -> dict[str, Any]:
    mobile: Any = value.get("mobile_business")
    mobile_require(
        isinstance(mobile, dict)
        and mobile.get("schema") == "v41-business-mobile-v1"
        and mobile.get("permission_evidence") == "ANONYMOUS_ONLY_NOT_403_REVOKED",
        "SCHEMA",
    )
    scopes, journal = mobile_journal(case)
    shots = mobile_screenshots(case, mobile["screenshots"], scopes)
    operations = mobile["operations"]
    mobile_require(
        isinstance(operations, list) and len(operations) == len(journal), "OPERATION_COVERAGE"
    )
    by_key: dict[str, dict[str, Any]] = {}
    ordinals: set[int] = set()
    proofs: dict[str, dict[str, Any]] = {}
    for proof in mobile["pending_proofs"]:
        mobile_require(proof["key"] not in proofs, "DUPLICATE_PENDING")
        proofs[proof["key"]] = proof
    for operation in operations:
        key = operation["key"]
        mobile_require(key in journal and key not in by_key and key in proofs, "KEY_COVERAGE")
        entry, proof = journal[key], proofs[key]
        mobile_require(
            operation["status"] == ("OK" if entry["states"][1] == "ACK_OK" else "COMMITTED"),
            "STATUS_ACK_MISMATCH",
        )
        kind, request = entry["operation"], entry["request"]
        body = request["body"]
        mobile_require(
            operation["operation"] == kind
            and mobile_scope(operation["context"], operation["shop_id"]) == entry["scope"],
            "OPERATION_SCOPE",
        )
        mobile_require(
            mobile_scope(proof["context"], proof["shop_id"]) == entry["scope"]
            and proof["key"] == key
            and proof["operation"] == ("import_preview" if kind == "preview" else kind)
            and proof["revision"] == body["expected_data_revision"],
            "PENDING_BINDING",
        )
        mobile_require(
            type(operation["post_ordinal"]) is int
            and operation["post_ordinal"] > 0
            and operation["post_ordinal"] not in ordinals
            and operation["width"] in {390, 1280, 1440},
            "POST_OBSERVATION",
        )
        ordinals.add(operation["post_ordinal"])
        mobile_require(
            operation["before_revision"] == body["expected_data_revision"]
            and type(operation["version"]) is int
            and operation["version"] > 0,
            "CAS_BEFORE",
        )
        read = operation["readback"]
        mobile_require(
            mobile_scope(read["context"], read["shop_id"]) == entry["scope"]
            and read["resource_id"] == operation["resource_id"]
            and read["version"] == operation["version"],
            "FRESH_READBACK_IDENTITY",
        )
        if read.get("snapshot") is not None:
            mobile_snapshot(read["snapshot"])
        if kind in {"preview", "import_confirm"}:
            job = read.get("job")
            mobile_require(
                isinstance(job, dict)
                and type(job.get("version")) is int
                and job["version"] == operation["version"] == read["version"],
                "JOB_PROJECTION_VERSION_BINDING",
            )
        if kind == "preview":
            mobile_require(
                read["file_digest"] == entry["file_digest"], "PREVIEW_ORIGINAL_BYTES_DIGEST"
            )
            mobile_require(
                proof["resource_id"] is None
                and proof["version"] == operation["version"] - 1
                and operation["after_revision"] is None
                and operation["effect_count"] is None
                and read["job"]["import_job_id"] == operation["resource_id"]
                and read["job"]["data_revision"] == operation["before_revision"],
                "PREVIEW_BINDING",
            )
        else:
            version = (
                body["expected_job_version"]
                if kind == "import_confirm"
                else body["expected_version"]
            )
            mobile_require(
                proof["resource_id"] == operation["resource_id"]
                and proof["version"] == version
                and request["path"].split("/")[4] == operation["resource_id"]
                and operation["version"] == version + (0 if kind == "import_confirm" else 1),
                "RESOURCE_VERSION",
            )
            mobile_require(
                operation["status"] == "COMMITTED"
                and type(operation["effect_count"]) is int
                and operation["effect_count"] > 0
                and re.fullmatch(r"[a-f0-9]{64}", operation["after_revision"]) is not None
                and operation["after_revision"] != operation["before_revision"],
                "COMMITTED_EFFECT",
            )
            if kind == "import_confirm":
                dataset = read["dataset"]
                mobile_snapshot(dataset["snapshot"])
                mobile_require(
                    read["job"]["job_digest"] == body["expected_job_digest"],
                    "IMPORT_ORIGINAL_JOB_DIGEST",
                )
                mobile_require(
                    mobile_scope(dataset["context"], dataset["shop_id"]) == entry["scope"]
                    and dataset["snapshot"]["data_revision"] == operation["after_revision"]
                    and read["state"] == "COMMITTED"
                    and read["job"]["import_job_id"] == operation["resource_id"]
                    and read["row_count"] == operation["effect_count"],
                    "IMPORT_EFFECT_READBACK",
                )
                uploads = dataset["snapshot"]["source"]["uploads"]
                mobile_require(
                    len(
                        [
                            row
                            for row in uploads
                            if row["import_job_id"] == operation["resource_id"]
                            and row["file_digest"] == read["file_digest"]
                        ]
                    )
                    == operation["effect_count"],
                    "IMPORT_SOURCE_COUNT",
                )
            else:
                mobile_require(
                    operation["effect_count"] == 1
                    and read["snapshot"]["data_revision"] == operation["after_revision"],
                    "SINGLE_EFFECT",
                )
                mobile_require(
                    read["tags"] == body["tags"]
                    if kind == "product_tags"
                    else read["demo_fulfillment"] == "demo_fulfilled",
                    "RESOURCE_EFFECT_VALUE",
                )
        by_key[key] = operation
    mobile_require(set(by_key) == set(journal) == set(proofs), "UNOBSERVED_OPERATION_OR_PENDING")
    main_scopes = {mobile_scope(op["context"], op["shop_id"]) for op in operations}
    mobile_require(len(main_scopes) == 1, "BUSINESS_MAIN_SCOPE")
    main_scope = next(iter(main_scopes))
    for (state, _width), shot in shots.items():
        if state not in {"anonymous_empty", "second_visitor_empty"}:
            mobile_require(
                mobile_scope(shot["source"]["context"], shot["source"]["shop_id"]) == main_scope,
                "SCREENSHOT_MAIN_SCOPE",
            )
    expected_counts = {
        "tag_committed": sum(op["operation"] == "product_tags" for op in operations),
        "fulfillment_committed": sum(op["operation"] == "order_fulfillment" for op in operations),
        "preview_committed": sum(op["operation"] == "preview" for op in operations),
        "import_committed": sum(op["operation"] == "import_confirm" for op in operations),
        "downloads": len(value["facts"]["downloads"]),
    }
    mobile_require(
        value["counts"] == expected_counts
        and all(type(n) is int for n in value["counts"].values()),
        "COUNTS",
    )
    mobile_keys = mobile["mobile_keys"]
    mobile_require(
        isinstance(mobile_keys, list)
        and len(mobile_keys) == len(set(mobile_keys))
        and set(mobile_keys) == {key for key, op in by_key.items() if op["width"] == 390},
        "MOBILE_SUBSET",
    )
    mobile_require(
        {by_key[key]["operation"] for key in mobile_keys} >= {"product_tags", "order_fulfillment"},
        "MOBILE_TWO_OPERATIONS",
    )
    for state, kind in (
        ("tag_readback", "product_tags"),
        ("fulfillment_readback", "order_fulfillment"),
    ):
        shot = shots[(state, 390)]
        matches = [
            op
            for op in operations
            if op["operation"] == kind
            and op["width"] == 390
            and op["resource_id"] == shot["route"].split("/")[3]
            and op["after_revision"] == shot["source"]["snapshot"]["data_revision"]
            and mobile_scope(op["context"], op["shop_id"])
            == mobile_scope(shot["source"]["context"], shot["source"]["shop_id"])
        ]
        mobile_require(len(matches) == 1, "MOBILE_READBACK_SCREENSHOT")
        mobile_same_source(shot["source"], matches[0]["readback"])
    batch = mobile["batch"]
    selected, keys = batch["selected_ids"], batch["keys"]
    mobile_require(
        len(selected) == len(set(selected)) == len(keys) == len(set(keys)) == 2
        and set(keys) <= set(by_key),
        "BATCH_CARDINALITY",
    )
    page = batch["current_page"]
    source = page["source"]
    page_scope = mobile_scope(source["context"], source["shop_id"])
    mobile_require(
        page_scope in scopes and source["snapshot"]["data_revision"] == batch["initial_revision"],
        "BATCH_PAGE_SOURCE",
    )
    mobile_require(page_scope == main_scope, "BATCH_MAIN_SCOPE")
    mobile_snapshot(source["snapshot"])
    fixture_fields = ("fixture_digest", "baseline_snapshot_at", "fixture_version", "evidence_mode")
    fixture_anchor = tuple(source["snapshot"]["source"][name] for name in fixture_fields)
    snapshots = [
        shot["source"]["snapshot"]
        for shot in shots.values()
        if shot["source"].get("snapshot") is not None
    ]
    snapshots += [
        op["readback"]["snapshot"]
        for op in operations
        if op["readback"].get("snapshot") is not None
    ]
    snapshots += [
        op["readback"]["dataset"]["snapshot"] for op in operations if "dataset" in op["readback"]
    ]
    mobile_require(
        all(
            tuple(snapshot["source"][name] for name in fixture_fields) == fixture_anchor
            for snapshot in snapshots
        ),
        "FIXTURE_SOURCE_CHAIN",
    )
    for state in MOBILE_STATES:
        mobile_require(
            all(
                shots[(state, width)]["source"] == shots[(state, 390)]["source"]
                for width in (1280, 1440)
            ),
            "THREE_WIDTH_SOURCE_MISMATCH",
        )
    for state in ("product_list", "batch_confirm"):
        for (shot_state, _width), shot in shots.items():
            if state == shot_state:
                mobile_same_source(shot["source"], source)
    for state, kind in (
        ("product_detail", "product_tags"),
        ("tag_edit", "product_tags"),
        ("order_list", "order_fulfillment"),
        ("order_detail", "order_fulfillment"),
        ("fulfillment_confirm", "order_fulfillment"),
    ):
        for (shot_state, _width), shot in shots.items():
            if shot_state != state:
                continue
            revision = shot["source"]["snapshot"]["data_revision"]
            resource = shot["route"].split("/")[3] if state != "order_list" else None
            mobile_require(
                any(
                    op["operation"] == kind
                    and op["before_revision"] == revision
                    and (resource is None or op["resource_id"] == resource)
                    for op in operations
                ),
                "SCREENSHOT_BEFORE_OPERATION",
            )
    query = urllib.parse.parse_qs(page["query"].removeprefix("?"), keep_blank_values=True)
    mobile_require(query.get("shop_id") == [source["shop_id"]], "BATCH_PAGE_QUERY")
    items = {item["product_id"]: item["version"] for item in page["items"]}
    mobile_require(
        len(items) == len(page["items"]) and set(selected) <= set(items), "BATCH_PAGE_MEMBERSHIP"
    )
    mobile_require({by_key[key]["resource_id"] for key in keys} == set(selected), "BATCH_RESOURCES")
    revision = batch["initial_revision"]
    tags = None
    for index, key in enumerate(keys):
        op = by_key[key]
        mobile_require(
            op["operation"] == "product_tags"
            and mobile_scope(op["context"], op["shop_id"]) == page_scope
            and op["before_revision"] == revision
            and op["version"] == items[op["resource_id"]] + 1,
            "BATCH_CAS_CHAIN",
        )
        if index:
            mobile_require(
                op["post_ordinal"] > by_key[keys[index - 1]]["post_ordinal"], "BATCH_POST_ORDER"
            )
        if tags is None:
            tags = op["readback"]["tags"]
        mobile_require(op["readback"]["tags"] == tags, "BATCH_UNIFORM_TAGS")
        revision = op["after_revision"]
    mobile_require(
        shots[("batch_readback", 390)]["source"]["snapshot"]["data_revision"] == revision
        and mobile_scope(
            shots[("batch_readback", 390)]["source"]["context"],
            shots[("batch_readback", 390)]["source"]["shop_id"],
        )
        == page_scope,
        "BATCH_SCREENSHOT_READBACK",
    )
    evidence = batch["serial_evidence"]
    mobile_require(
        len(evidence) == len(keys) - 1 and batch["serial_readback"] is True, "BATCH_TIMING_COVERAGE"
    )
    for index, item in enumerate(evidence):
        mobile_require(
            item["previous_key"] == keys[index]
            and item["next_key"] == keys[index + 1]
            and all(
                type(item[n]) in {int, float} and math.isfinite(item[n])
                for n in ("read_start", "read_end_offset", "next_post_start")
            )
            and item["read_start"] > 0
            and item["read_end_offset"] >= 0
            and item["next_post_start"] >= item["read_start"] + item["read_end_offset"],
            "BATCH_READ_BEFORE_NEXT_POST",
        )
    mobile_require(
        batch["progress"] == {"已核成功": len(keys), "明确拒绝": 0, "待核对": 0, "未发送": 0},
        "BATCH_PROGRESS",
    )
    for fmt in ("csv", "xlsx"):
        candidates = [
            op
            for key, op in by_key.items()
            if op["operation"] == "preview" and journal[key]["request"]["body"]["format"] == fmt
        ]
        discovered = [
            op
            for op in candidates
            if journal[op["key"]]["request"]["body"].get("parent_job_id") is None
        ]
        mobile_require(len(discovered) == 1, "FORMAT_DISCOVERY")
        initial = discovered[0]
        mapped = [
            op
            for op in candidates
            if journal[op["key"]]["request"]["body"].get("parent_job_id") == initial["resource_id"]
        ]
        mobile_require(len(mapped) == 1, "FORMAT_MAPPING")
        digest = journal[initial["key"]]["file_digest"]
        mobile_require(
            journal[mapped[0]["key"]]["file_digest"] == digest
            and mapped[0]["readback"]["file_digest"] == digest,
            "MAPPED_ORIGINAL_BYTES_DIGEST",
        )
        imports = [
            op
            for op in operations
            if op["operation"] == "import_confirm" and op["resource_id"] == mapped[0]["resource_id"]
        ]
        mobile_require(len(imports) == 1 and imports[0]["width"] == 390, "MOBILE_FORMAT_IMPORT")
        imported = imports[0]
        mobile_require(
            imported["readback"]["file_digest"] == digest
            and imported["readback"]["job"] == mapped[0]["readback"]["job"]
            and journal[imported["key"]]["request"]["body"]["expected_job_digest"]
            == mapped[0]["readback"]["job"]["job_digest"],
            "IMPORT_JOB_BYTES_CHAIN",
        )
        for width in (390, 1280, 1440):
            mobile_same_source(shots[(fmt + "_mapping", width)]["source"], initial["readback"])
        read_shot = shots[(fmt + "_readback", 390)]["source"]
        mobile_require(
            read_shot["snapshot"]["data_revision"] == imported["after_revision"],
            "FORMAT_READBACK_REVISION",
        )
        for width in (390, 1280, 1440):
            mobile_require(
                shots[(fmt + "_mapping", width)]["source"]["job"]["import_job_id"]
                == initial["resource_id"]
                and shots[(fmt + "_mapping", width)]["source"]["file_digest"]
                == initial["readback"]["file_digest"],
                "MAPPING_SCREENSHOT_SOURCE",
            )
        uploaded = shots[(fmt + "_readback", 390)]["source"]["snapshot"]["source"]["uploads"]
        mobile_require(
            any(
                row["import_job_id"] == mapped[0]["resource_id"]
                and row["file_digest"] == mapped[0]["readback"]["file_digest"]
                for row in uploaded
            ),
            "FORMAT_SCREENSHOT_READBACK",
        )
    mobile_require(
        all(type(n) is int and n >= 0 for n in batch["progress"].values()), "BATCH_PROGRESS_TYPES"
    )
    interactions = mobile["interactions"]
    for state in (
        "product_detail",
        "fulfillment_confirm",
        "tag_edit",
        "csv_mapping",
        "xlsx_mapping",
    ):
        mobile_require(
            any(
                item["state"] == state
                and item["width"] == 390
                and (item.get("tab_inside") is True or item.get("tab_controls") is True)
                for item in interactions
            ),
            "FOCUS_EVIDENCE",
        )
    for state in ("product_detail", "fulfillment_confirm"):
        mobile_require(
            any(
                item["state"] == state and item.get("escape") == "RETURNED_LIST_NO_POST"
                for item in interactions
            ),
            "ESCAPE_EVIDENCE",
        )
    for state in ("csv_mapping", "xlsx_mapping"):
        mobile_require(
            any(
                item["state"] == state and item.get("escape") == "NON_MODAL_NO_POST"
                for item in interactions
            ),
            "MAPPING_ESCAPE_EVIDENCE",
        )
    return {
        "confirmed_keys": sorted(by_key),
        "mobile_keys": sorted(mobile_keys),
        "png_count": len(shots),
        "journal_sha256": hashlib.sha256(
            private_subject_bytes(Path(case.directory) / "browser-business.subjects.private.jsonl")
        ).hexdigest(),
    }


if __name__ == "__main__":
    main()
