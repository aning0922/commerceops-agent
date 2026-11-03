"""Fixed WEB-owned browser test; no arbitrary command/spec or mock route."""

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from .preflight import ROOT, git

TITLE = "LIVE: isolated demo lifecycle and browser layout"
# Root handed off f18; Astra aa91caf accepted its prepared native-zoom delta.
# Presence, raw Git blobs and current HEAD must all agree before any resource launch.
WEB_HANDOFF_READY = True
WEB_SOURCE = "f18ba5bf5c9de88d113eb5a5bff244cd66416c2b"
PINS = {
    "frontend/playwright.v4-live.config.ts": "ca9bb704f27220de9930f7e03e56492c79b0faa4",
    "frontend/v4-tests/lifecycle.live.ts": "d590a90c1507b8a2a9550840d09bee9cfbf7a3dc",
    "frontend/v4-tests/lifecycle.waiter.mjs": "ec74f8c560ad293821dcd4545c275395c243d3d0",
    "frontend/v4-tests/lifecycle.profile.mjs": "343757319e0c3ed6d50f6777a3d7aadbc2a9d4ed",
    "frontend/lib/v4-schema.json": "e625120e42a28b8f777d7e2e02b0da0aa9d2b5be",
}


def verify_source() -> None:
    if not WEB_HANDOFF_READY:
        raise ValueError("new reviewed WEB SHA/path/blob handoff pending")
    for name, blob in PINS.items():
        path = ROOT / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(ROOT):
            raise ValueError("fixed WEB source missing or symlinked")
        raw = path.read_bytes()
        actual = hashlib.sha1(
            b"blob " + str(len(raw)).encode() + b"\0" + raw, usedforsecurity=False
        ).hexdigest()
        if actual != blob or git("rev-parse", "HEAD:" + name) != blob:
            raise ValueError("fixed WEB source changed; Root exact handoff required")


def command() -> tuple[str, ...]:
    return (
        str(ROOT / ".tools/node/bin/node"),
        str(ROOT / "frontend/node_modules/@playwright/test/cli.js"),
        "test",
        "--config",
        str(ROOT / "frontend/playwright.v4-live.config.ts"),
        "v4-tests/lifecycle.live.ts",
        "--grep",
        "(?:^| )" + re.escape(TITLE) + "$",
        "--workers",
        "1",
        "--retries",
        "0",
        "--forbid-only",
        "--reporter",
        "json",
    )


def validate_report(report: dict[str, Any]) -> None:
    stats = report["stats"]
    if report.get("errors") or any(
        type(stats.get(key)) is not int or stats[key] != wanted
        for key, wanted in {"expected": 1, "unexpected": 0, "flaky": 0, "skipped": 0}.items()
    ):
        raise AssertionError("exactly one unskipped/unflaky passing browser test required")
    specs: list[dict[str, Any]] = []

    def visit(suite: dict[str, Any]) -> None:
        specs.extend(suite.get("specs", []))
        for child in suite.get("suites", []):
            visit(child)

    for suite in report["suites"]:
        visit(suite)
    if len(specs) != 1 or specs[0]["title"] != TITLE or specs[0]["ok"] is not True:
        raise AssertionError("fixed lifecycle title not uniquely passed")
    tests = specs[0]["tests"]
    if len(tests) != 1 or tests[0]["expectedStatus"] != "passed":
        raise AssertionError("one real successful test required")
    results = tests[0]["results"]
    if len(results) != 1 or results[0]["status"] != "passed" or results[0].get("retry", 0) != 0:
        raise AssertionError("retry/skip/failure is not browser acceptance")


def main() -> None:
    from .owned_driver import Case

    if len(sys.argv) != 3 or sys.argv[1] != "--case":
        raise SystemExit(1)
    case = Case(**json.loads(Path(sys.argv[2]).read_text()))
    case.validate()
    if case.scenario != "browser_lifecycle":
        raise SystemExit(1)
    verify_source()
    os.umask(0o077)
    evidence = Path(case.directory) / "browser"
    evidence.mkdir(mode=0o700, exist_ok=False)
    argv = command()
    env = {
        "PATH": str(ROOT / ".tools/node/bin") + ":/usr/bin:/bin",
        "HOME": str(Path.home()),
        "V4_WEB_ORIGIN": case.web,
        "V4_API_ORIGIN": case.api,
        "V4_EVIDENCE_DIR": str(evidence),
        "NEXT_TELEMETRY_DISABLED": "1",
    }
    os.execve(argv[0], argv, env)  # noqa: S606 -- fixed local Node/CLI, no caller argv or shell.


if __name__ == "__main__":
    main()
