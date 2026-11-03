"""Offline fixed-source and report guards; never launch Node/browser or services."""

import copy
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from . import browser_lifecycle as browser
from .preflight import ROOT

pytestmark = pytest.mark.offline


def good_report() -> dict[str, Any]:
    return {
        "stats": {"expected": 1, "unexpected": 0, "flaky": 0, "skipped": 0},
        "errors": [],
        "suites": [
            {
                "specs": [
                    {
                        "title": browser.TITLE,
                        "ok": True,
                        "tests": [
                            {
                                "expectedStatus": "passed",
                                "results": [{"status": "passed", "retry": 0}],
                            }
                        ],
                    }
                ]
            }
        ],
    }


def test_only_one_real_unretried_result_passes_guard() -> None:
    browser.validate_report(good_report())


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected", 0),
        ("expected", 2),
        ("expected", True),
        ("skipped", 1),
        ("unexpected", 1),
        ("flaky", 1),
    ],
)
def test_empty_multitest_skip_failure_or_flaky_never_signs_browser(
    field: str, value: object
) -> None:
    report = good_report()
    report["stats"][field] = value
    with pytest.raises(AssertionError):
        browser.validate_report(report)


def test_wrong_title_or_retried_result_rejected() -> None:
    report = good_report()
    report["suites"][0]["specs"][0]["title"] = "some other unit test"
    with pytest.raises(AssertionError):
        browser.validate_report(report)
    report = good_report()
    report["suites"][0]["specs"][0]["tests"][0]["results"][0]["retry"] = 1
    with pytest.raises(AssertionError):
        browser.validate_report(report)


def test_duplicate_test_or_failed_result_rejected() -> None:
    report = good_report()
    tests = report["suites"][0]["specs"][0]["tests"]
    tests.append(copy.deepcopy(tests[0]))
    with pytest.raises(AssertionError):
        browser.validate_report(report)
    report = good_report()
    report["suites"][0]["specs"][0]["tests"][0]["results"][0]["status"] = "skipped"
    with pytest.raises(AssertionError):
        browser.validate_report(report)


def test_command_fixed_to_handed_off_file_and_exact_title() -> None:
    command = browser.command()
    assert "v4-tests/lifecycle.live.spec.ts" in command
    assert command[command.index("--grep") + 1] == "(?:^| )" + re.escape(browser.TITLE) + "$"
    assert command[command.index("--workers") + 1] == "1"
    assert command[command.index("--retries") + 1] == "0"
    # Pinned Playwright matches a full project/file/title string, not title alone.
    assert re.search(
        command[command.index("--grep") + 1], "chromium lifecycle.live.spec.ts " + browser.TITLE
    )


def test_missing_or_mutated_source_rejected_before_browser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(browser, "ROOT", tmp_path)
    with pytest.raises(ValueError):
        browser.verify_source()
    monkeypatch.setattr(browser, "WEB_HANDOFF_READY", True)  # Pure file guard test only.
    for name, blob in browser.PINS.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        # Read only the handed-off Git object, never WEB author WIP.
        path.write_bytes(subprocess.check_output(["git", "cat-file", "blob", blob], cwd=ROOT))
    monkeypatch.setattr(browser, "git", lambda *args: browser.PINS[args[1][len("HEAD:") :]])
    browser.verify_source()
    first = tmp_path / next(iter(browser.PINS))
    first.write_bytes(first.read_bytes() + b"\n// altered\n")
    with pytest.raises(ValueError):
        browser.verify_source()


def test_superseded_web_candidate_cannot_be_admitted_by_file_presence() -> None:
    assert browser.WEB_HANDOFF_READY is False
    with pytest.raises(ValueError, match="handoff pending"):
        browser.verify_source()
