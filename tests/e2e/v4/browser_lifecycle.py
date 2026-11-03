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
PINS = {
    "frontend/playwright.v4-live.config.ts": "45e1cca1f3de9aefdf42eac5403703ad91ddec57",
    "frontend/v4-tests/lifecycle.live.spec.ts": "0eafd5ccd665f6e90e41432a545cf07cd66d97d2",
}


def verify_source() -> None:
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
        "v4-tests/lifecycle.live.spec.ts",
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
