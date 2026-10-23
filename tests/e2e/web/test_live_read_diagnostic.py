"""固定read7安全失败诊断的纯回归；不启动PG/API/browser或读取私有业务输入。"""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.web.run_live_batches import (
    LIVE_SOURCE_FILES,
    READ_REPORTER,
    READ_TITLES,
    ReadReporterRejected,
    read_failure_diagnostic,
    read_reporter,
)

pytestmark = pytest.mark.offline


def report(statuses: list[str]) -> dict[str, Any]:
    return {
        "status": "failed",
        "duration_ms": 10.5,
        "trace": "off",
        "video": "off",
        "automatic_screenshot": "off",
        "source_mode": "live-api",
        "commerce_source_mode": "mock-fixture",
        "identity_mode": "session",
        "tests": [
            {
                "test": title,
                "status": status,
                "duration_ms": 10,
                "location": "e2e/web/live/read.spec.ts:1",
            }
            for title, status in zip(READ_TITLES, statuses, strict=False)
        ],
    }


def write_report(directory: Path, value: dict[str, Any]) -> Path:
    path = directory / READ_REPORTER
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    return path


def window() -> dict[str, object]:
    # Low-entropy source metadata placeholders, not credentials or real evidence.
    return {
        "source_commit": "c" * 40,
        "source_files_sha256": {p: "d" * 64 for p in LIVE_SOURCE_FILES},
        "stop_at_utc": "2026-10-11T04:23:00Z",
        "stopped_at_utc": "2026-10-11T04:22:00+00:00",
        "pg_running": False,
        "pg_pid": 0,
        "owned_listeners_remaining": False,
        "private_directory": "private-placeholder-not-for-output",
        "api_origin": "https://private-placeholder.invalid",
    }


def test_titles_are_exact_existing_read_seven() -> None:
    source = Path(__file__).with_name("live").joinpath("read.spec.ts").read_text()
    assert tuple(re.findall(r'^test\("([^"]+)"', source, re.MULTILINE)) == READ_TITLES
    assert len(READ_TITLES) == 7


def test_partial_result_counts_closed_rows_and_source_stop(tmp_path: Path) -> None:
    write_report(tmp_path, report(["passed", "failed", "skipped"]))
    result = read_failure_diagnostic(tmp_path, window(), reporter_current=True)
    assert result["expected_count"] == 7
    assert result["counts"] == {"actual": 3, "passed": 1, "failed": 1, "skipped": 1, "not_run": 4}
    assert result["failure_category"] == "read_test_failed"
    assert result["reporter_valid"] is True
    assert result["resources_stopped"] is True
    assert result["source_commit"] == "c" * 40
    assert set(result) == {
        "schema_version",
        "failure_category",
        "reporter_valid",
        "reporter_status",
        "expected_count",
        "counts",
        "tests",
        "source_commit",
        "source_files_sha256",
        "stop_at_utc",
        "stopped_at_utc",
        "resources_stopped",
    }
    encoded = json.dumps(result)
    for forbidden in (
        "duration_ms",
        "location",
        "api_origin",
        "private_directory",
        "private-placeholder",
    ):
        assert forbidden not in encoded


@pytest.mark.parametrize(
    "status,category",
    [
        ("failed", "read_test_failed"),
        ("timedOut", "read_test_timed_out"),
        ("interrupted", "read_test_interrupted"),
        ("skipped", "read_tests_incomplete"),
        ("passed", "unknown"),
    ],
)
def test_only_result_category_not_inferred_assertion_cause(
    tmp_path: Path, status: str, category: str
) -> None:
    write_report(tmp_path, report([status] + ["passed"] * 6))
    result = read_failure_diagnostic(tmp_path, window(), reporter_current=True)
    assert result["failure_category"] == category


@pytest.mark.parametrize(
    "field,value",
    [
        ("raw_stdout", "private-placeholder"),
        ("trace", "on"),
        ("identity_mode", "mock"),
        ("status", "assertion-private-placeholder"),
        ("duration_ms", True),
        ("duration_ms", -1),
        ("duration_ms", float("inf")),
        ("duration_ms", 10**1000),
        ("tests", {}),
    ],
)
def test_outer_closed_schema_rejects(tmp_path: Path, field: str, value: object) -> None:
    candidate = report(["failed"])
    candidate[field] = value
    write_report(tmp_path, candidate)
    with pytest.raises(ReadReporterRejected, match="invalid read reporter"):
        read_reporter(tmp_path)
    result = read_failure_diagnostic(tmp_path, window(), reporter_current=True)
    assert result["counts"] is None and result["failure_category"] == "unknown"
    assert "private-placeholder" not in json.dumps(result)


@pytest.mark.parametrize(
    "field,value",
    [
        ("test", "dynamic-private-placeholder"),
        ("test", [READ_TITLES[0]]),
        ("status", "private-placeholder"),
        ("duration_ms", True),
        ("location", "https://private-placeholder.invalid"),
        ("error", {"message": "private-placeholder"}),
    ],
)
def test_illegal_title_status_location_extra_body_rejected(
    tmp_path: Path, field: str, value: object
) -> None:
    candidate = report(["failed"])
    candidate["tests"][0][field] = value
    write_report(tmp_path, candidate)
    with pytest.raises(ReadReporterRejected, match="invalid read reporter"):
        read_reporter(tmp_path)
    result = read_failure_diagnostic(tmp_path, window(), reporter_current=True)
    assert result["tests"] is None and result["failure_category"] == "unknown"
    assert "private-placeholder" not in json.dumps(result)


def test_missing_reporter_rejected_and_counts_not_fabricated(tmp_path: Path) -> None:
    with pytest.raises(ReadReporterRejected, match="missing read reporter"):
        read_reporter(tmp_path)
    result = read_failure_diagnostic(tmp_path, window(), reporter_current=True)
    assert result["reporter_valid"] is False
    assert result["counts"] is None and result["tests"] is None
    assert result["failure_category"] == "unknown"


def test_duplicate_title_missing_fields_and_excess_rows_rejected(tmp_path: Path) -> None:
    duplicate = report(["passed"])
    duplicate["tests"] *= 2
    missing = report(["failed"])
    del missing["tests"][0]["status"]
    missing_outer = report(["failed"])
    del missing_outer["status"]
    excess = report(["passed"] * 7)
    excess["tests"].append(excess["tests"][0])
    for candidate in (duplicate, missing, missing_outer, excess):
        write_report(tmp_path, candidate)
        with pytest.raises(ReadReporterRejected, match="invalid read reporter"):
            read_reporter(tmp_path)


def test_duplicate_json_fields_bad_permission_symlink_and_size_rejected(tmp_path: Path) -> None:
    path = write_report(tmp_path, report(["failed"]))
    path.write_text(path.read_text().replace('{"status":', '{"status":"passed","status":', 1))
    with pytest.raises(ReadReporterRejected):
        read_reporter(tmp_path)
    write_report(tmp_path, report(["failed"])).chmod(0o644)
    with pytest.raises(ReadReporterRejected):
        read_reporter(tmp_path)
    target = tmp_path / "fixture-only.json"
    path.rename(target)
    path.symlink_to(target)
    with pytest.raises(ReadReporterRejected):
        read_reporter(tmp_path)
    path.unlink()
    path = write_report(tmp_path, report(["failed"]))
    path.write_text(" " * 65537)
    with pytest.raises(ReadReporterRejected):
        read_reporter(tmp_path)


def test_stale_reporter_not_consumed_without_current_launch(tmp_path: Path) -> None:
    write_report(tmp_path, report(["failed"] * 7))
    result = read_failure_diagnostic(tmp_path, window(), reporter_current=False)
    assert result["counts"] is None and result["failure_category"] == "unknown"


def test_invalid_json_parser_limits_also_fail_closed(tmp_path: Path) -> None:
    path = write_report(tmp_path, report(["failed"]))
    for content in ('{"duration_ms":' + "1" * 5000 + "}", "[" * 2000 + "]" * 2000):
        path.write_text(content)
        with pytest.raises(ReadReporterRejected, match="invalid read reporter"):
            read_reporter(tmp_path)
        result = read_failure_diagnostic(tmp_path, window(), reporter_current=True)
        assert result["counts"] is None and result["failure_category"] == "unknown"


def test_bad_source_context_cannot_echo_private_values(tmp_path: Path) -> None:
    write_report(tmp_path, report(["failed"]))
    ledger = window()
    ledger.update(
        source_commit="private-placeholder",
        source_files_sha256={"private-placeholder": "raw"},
        stop_at_utc="private-placeholder",
        stopped_at_utc="private-placeholder",
        pg_pid=True,
    )
    result = read_failure_diagnostic(tmp_path, ledger, reporter_current=True)
    assert result["source_commit"] is result["source_files_sha256"] is None
    assert result["stop_at_utc"] is result["stopped_at_utc"] is None
    assert result["resources_stopped"] is False
    assert "private-placeholder" not in json.dumps(result)
