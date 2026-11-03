"""Run only the explicitly reviewed Node contracts; exact collected/executed sets and zero skips."""

import json
import os
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FILES = frozenset(
    {
        "daily-read.spec.ts",
        "daily-s3-read.spec.ts",
        "daily-write.spec.ts",
        "live-network-guard.spec.ts",
        "p6-inquiry.spec.ts",
        "copy.spec.ts",
        "bounded-network.spec.ts",
        "owned-shop-scopes.spec.ts",
        "owned-copy-preview.spec.ts",
    }
)


def contract_cases(report: dict[str, Any], *, executed: bool) -> dict[str, tuple[str, str]]:
    cases: dict[str, tuple[str, str]] = {}
    files: set[str] = set()
    if report.get("errors"):
        raise ValueError("M3 contract reporter errors")

    def visit(suite: dict[str, Any]) -> None:
        for spec in suite.get("specs", []):
            # Playwright JSON file paths are relative to testDir, never arbitrary source suffixes.
            file = spec["file"]
            if file not in FILES:
                raise ValueError("M3 unexpected contract file")
            tests = spec["tests"]
            if len(tests) != 1 or tests[0].get("expectedStatus") != "passed":
                raise ValueError("M3 contracts require one non-skipped project")
            test = tests[0]
            if test.get("annotations") != [] or test.get("projectName") != "":
                raise ValueError("M3 annotated or alternate project refused")
            if executed and (
                test.get("status") != "expected"
                or len(test["results"]) != 1
                or test["results"][0].get("status") != "passed"
                or type(test["results"][0].get("retry")) is not int
                or test["results"][0]["retry"] != 0
            ):
                raise ValueError("M3 failed skipped or retried contract")
            key = spec["id"]
            if not isinstance(key, str) or key in cases:
                raise ValueError("M3 duplicate contract identity")
            files.add(file)
            cases[key] = (file, spec["title"])
        for child in suite.get("suites", []):
            visit(child)

    for suite in report["suites"]:
        visit(suite)
    if files != FILES or not cases:
        raise ValueError("M3 incomplete contract file coverage")
    if executed:
        stats = report["stats"]
        if (
            any(
                type(stats.get(key)) is not int
                for key in ("expected", "unexpected", "flaky", "skipped")
            )
            or stats.get("expected") != len(cases)
            or any(stats.get(key) != 0 for key in ("unexpected", "flaky", "skipped"))
        ):
            raise ValueError("M3 incomplete contract execution")
    return cases


def validate_reports(listed: dict[str, Any], executed: dict[str, Any]) -> int:
    planned = contract_cases(listed, executed=False)
    actual = contract_cases(executed, executed=True)
    if planned != actual:
        raise ValueError("M3 executed contracts differ from full collection")
    return len(actual)


def main() -> None:
    environment = os.environ.copy()
    for name in (
        "COMMERCEOPS_M3_UI_FIXTURE_URL",
        "COMMERCEOPS_M3_LIVE_WEB_URL",
        "COMMERCEOPS_M3_PRIVATE_DIR",
    ):
        environment.pop(name, None)
    command = [
        str(ROOT / ".tools/node/bin/node"),
        str(ROOT / "frontend/node_modules/@playwright/test/cli.js"),
        "test",
        "--config",
        "playwright.m3.noserver.config.ts",
        "--reporter=json",
    ]
    reports = []
    for flags in (["--list"], []):
        result = subprocess.run(
            [*command, *flags],
            cwd=ROOT / "frontend",
            env=environment,
            capture_output=True,
            text=True,
            timeout=75,
            check=False,
        )
        if result.returncode:
            raise ValueError("M3 contract command failed (raw output withheld)")
        report = json.loads(result.stdout)
        if flags:
            contract_cases(report, executed=False)  # Fail before execution on skipped/partial plan.
        reports.append(report)
    count = validate_reports(*reports)
    print(
        f"M3 no-server contracts: files={len(FILES)}, collected=executed={count}, "
        "skipped=0, retries=0"
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        raise SystemExit("M3 no-server contract gate failed (raw output withheld)") from None
