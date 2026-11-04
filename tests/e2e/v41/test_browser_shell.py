"""Browser report, journal and process identity components; no browser or services."""

import copy
import hashlib
import json
import os
import signal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from pytest import MonkeyPatch

from . import browser_shell as browser
from .final_facts import decode_subjects
from .owned_driver import Case
from .request_witness import canonical, match_original_request, server_request
from .subjects import frozen_subjects

pytestmark = pytest.mark.offline


def report() -> dict[str, Any]:
    return {
        "errors": [],
        "stats": {"expected": 2, "unexpected": 0, "flaky": 0, "skipped": 0},
        "suites": [
            {
                "specs": [
                    {
                        "title": title,
                        "file": name,
                        "ok": True,
                        "tests": [
                            {
                                "expectedStatus": "passed",
                                "results": [{"status": "passed", "retry": 0}],
                            }
                        ],
                    }
                    for name, title in browser.TITLES.items()
                ]
            }
        ],
    }


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "single",
        "extra",
        "title",
        "file",
        "retry",
        "skip",
        "boolean",
        "two_results",
        "runner_error",
    ],
)
def test_browser_report_requires_exact_two_fixed_tests_without_retry_or_skip(
    fault: str | None,
) -> None:
    value = report()
    specs = value["suites"][0]["specs"]
    if fault == "single":
        specs.pop()
    elif fault == "extra":
        specs.append(copy.deepcopy(specs[0]))
    elif fault == "title":
        specs[0]["title"] = "some other passing test"
    elif fault == "file":
        specs[0]["file"] = "elsewhere.spec.ts"
    elif fault == "retry":
        specs[0]["tests"][0]["results"][0]["retry"] = 1
    elif fault == "skip":
        value["stats"]["skipped"] = 1
    elif fault == "boolean":
        value["stats"]["flaky"] = False
    elif fault == "two_results":
        specs[0]["tests"][0]["results"].append({"status": "passed", "retry": 0})
    elif fault == "runner_error":
        value["errors"] = [{"message": "public component failure"}]
    if fault is None:
        browser.validate_report(value)
    else:
        with pytest.raises(ValueError):
            browser.validate_report(value)


def case(directory: Path) -> Case:
    return cast(
        Case, SimpleNamespace(directory=str(directory), source_sha="a" * 40, source_tree="b" * 40)
    )


def events(c: Case) -> tuple[dict[str, Any], dict[str, Any]]:
    context: dict[str, Any] = {
        n: str(uuid4()) for n in ("tenant_id", "organization_id", "principal_id")
    }
    context.update(reset_epoch=0, auth_generation=1)
    shop, key, target = str(uuid4()), str(uuid4()), str(uuid4())
    scope = {
        "schema": "v41-browser-subject-event-1",
        "source_sha": c.source_sha,
        "source_tree": c.source_tree,
        "context": context,
        "shop_id": shop,
        "operation": None,
        "request_key": None,
        "state": "ATTEMPT_STARTED",
        "request": None,
    }
    body = {
        "shop_id": shop,
        "request_key": key,
        "expected_epoch": 0,
        "expected_generation": 1,
        "expected_data_revision": "c" * 64,
        "expected_version": 0,
        "tags": ["QA"],
    }
    request = {
        "method": "POST",
        "path": f"/api/v4/products/{target}/tags",
        "body": body,
        "request_body_sha256": hashlib.sha256(canonical(body).encode()).hexdigest(),
    }
    return scope, {**scope, "operation": "product_tags", "request_key": key, "request": request}


def journal(directory: Path, label: str, values: list[dict[str, Any]], tail: bytes = b"") -> None:
    path = directory / f"browser-{label}.subjects.private.jsonl"
    path.write_bytes(b"".join(json.dumps(v).encode() + b"\n" for v in values) + tail)
    path.chmod(0o600)


@pytest.mark.parametrize("fault", [None, "truncated", "hash", "source", "ack_without_intent"])
def test_import_preserves_original_intent_and_valid_prefix_even_after_failure(
    tmp_path: Path, fault: str | None
) -> None:
    tmp_path.chmod(0o700)
    c = case(tmp_path)
    scope, intent = events(c)
    journal(tmp_path, "shell", [scope])
    ack = {**intent, "request": None, "state": "ACK_UNKNOWN"}
    values, tail = [intent, ack], b""
    if fault == "truncated":
        tail = b'{"unfinished":'
    elif fault == "hash":
        values[1] = {**ack, "state": "ATTEMPT_STARTED", "request": copy.deepcopy(intent["request"])}
        values[1]["request"]["request_body_sha256"] = "0" * 64
    elif fault == "source":
        values[1] = {**ack, "source_sha": "c" * 40}
    elif fault == "ack_without_intent":
        values = [ack]
    journal(tmp_path, "business", values, tail)
    result = browser.import_journals(c)
    assert bool(result["errors"]) == (fault is not None)
    subjects = decode_subjects(frozen_subjects(tmp_path))
    operations = next(iter(subjects["scopes"].values()))["operations"]
    if fault == "ack_without_intent":
        assert operations == {}
        return
    attempt = next(iter(operations.values()))
    assert attempt["requests"] == [intent["request"]]
    expected = server_request(intent["request"], "product_tags")
    match_original_request(attempt, canonical(expected))
    expected["body"]["tags"] = ["different"]
    with pytest.raises(ValueError, match="FINAL_BROWSER_ORIGINAL_REQUEST"):
        match_original_request(attempt, canonical(expected))


def test_preview_witness_uses_real_dto_defaults_and_file_digest() -> None:
    body = {
        "shop_id": str(uuid4()),
        "request_key": str(uuid4()),
        "expected_epoch": 0,
        "expected_generation": 0,
        "expected_data_revision": "a" * 64,
        "format": "csv",
        "filename": "tiny.csv",
        "file_base64": "YQ==",
    }
    request = {"method": "POST", "path": "/api/v4/imports/previews", "body": body}
    normalized = server_request(request, "preview")
    assert "file_base64" not in normalized["command"]
    assert normalized["file_digest"] == hashlib.sha256(b"a").hexdigest()
    assert normalized["command"]["mapping_version"] == 1
    assert normalized["command"]["parent_job_id"] is None


def browser_process_fixture(directory: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    birth = "Wed Nov 4 11:00:00 2026"
    binary = "/new/approved/chromium"
    rows = [
        {
            "pid": 778,
            "ppid": 777,
            "uid": os.getuid(),
            "pgid": 777,
            "birth": birth,
            "argv": "/approved/node cli.js",
        },
        {
            "pid": 12345,
            "ppid": 778,
            "uid": os.getuid(),
            "pgid": 12345,
            "birth": birth,
            "argv": binary
            + " --user-data-dir="
            + str(directory / "browser-tmp/playwright_chromiumdev_profile-x"),
        },
        {
            "pid": 12346,
            "ppid": 12345,
            "uid": os.getuid(),
            "pgid": 12345,
            "birth": birth,
            "argv": "/approved/chromium-helper --type=renderer",
        },
    ]
    return rows, {"executable": binary, "sha256": "f" * 64}


def test_live_group_capture_requires_owned_node_ancestry_and_exact_profile_binary(
    tmp_path: Path,
) -> None:
    rows, binding = browser_process_fixture(tmp_path)
    row = rows[1]
    raw = f"{row['pid']} {row['ppid']} {row['uid']} {row['pgid']} {row['birth']} {row['argv']}\n"
    assert browser.process_rows(raw) == [row]
    groups = browser.observe_groups(rows, tmp_path, binding["executable"], 778, rows[0]["birth"])
    assert len(groups) == 1
    assert {r["pid"] for r in groups[0]["members"]} == {12345, 12346}
    for changes in (
        {"ppid": 1},
        {"argv": rows[1]["argv"].replace(binding["executable"], "/other/chromium")},
    ):
        bad = copy.deepcopy(rows)
        bad[1].update(changes)
        with pytest.raises(ValueError):
            browser.observe_groups(bad, tmp_path, binding["executable"], 778, rows[0]["birth"])


def group_journal(c: Case, rows: list[dict[str, Any]], binding: dict[str, Any]) -> None:
    header = {
        "kind": "START",
        "source_sha": c.source_sha,
        "source_tree": c.source_tree,
        "directory": c.directory,
        "wrapper_pid": 777,
        "uid": os.getuid(),
        "binary_sha256": binding["sha256"],
    }
    groups = browser.observe_groups(
        rows, Path(c.directory), binding["executable"], 778, rows[0]["birth"]
    )
    path = Path(c.directory) / "browser-groups.private.jsonl"
    path.write_bytes(b"".join(json.dumps(row).encode() + b"\n" for row in [header, *groups]))
    path.chmod(0o600)


@pytest.mark.parametrize("leader_at_first_check", [True, False])
def test_cleanup_checks_all_recorded_group_members_after_leader_exits(
    tmp_path: Path, monkeypatch: MonkeyPatch, leader_at_first_check: bool
) -> None:
    from tests.e2e.v4.supervisor import Budget

    tmp_path.chmod(0o700)
    c = case(tmp_path)
    rows, binding = browser_process_fixture(tmp_path)
    group_journal(c, rows, binding)
    current = rows[1:] if leader_at_first_check else [rows[2]]
    signals: list[tuple[int, int]] = []

    def signal_group(pgid: int, sig: int) -> None:
        nonlocal current
        signals.append((pgid, sig))
        # TERM removes only the leader. Renderer has no profile argument and remains in the group.
        current = [rows[2]] if sig == signal.SIGTERM else []

    monkeypatch.setattr(browser, "inventory", lambda *_args, **_kwargs: current)
    monkeypatch.setattr(os, "killpg", signal_group)
    budget = cast(Budget, SimpleNamespace(timeout=lambda *_args, **_kwargs: 0))
    result = browser.stop_residuals(c, binding, budget, 777)
    assert signals == [(12345, signal.SIGTERM), (12345, signal.SIGKILL)]
    assert result["remaining"] == [] and result["clean_exit"] is False
    assert result["forced"]


def test_missing_capture_and_reused_member_birth_never_allow_signal_or_clean(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    from tests.e2e.v4.supervisor import Budget

    tmp_path.chmod(0o700)
    c = case(tmp_path)
    rows, binding = browser_process_fixture(tmp_path)
    group_journal(c, rows, binding)
    current = [{**rows[2], "birth": "Wed Nov 4 11:01:00 2026"}]
    monkeypatch.setattr(browser, "inventory", lambda *_args, **_kwargs: current)
    monkeypatch.setattr(os, "killpg", lambda *_args: pytest.fail("unknown PID/group signaled"))
    budget = cast(Budget, SimpleNamespace(timeout=lambda *_args, **_kwargs: 0))
    with pytest.raises(ValueError, match="CONTINUITY_UNKNOWN"):
        browser.stop_residuals(c, binding, budget, 777)
    path = tmp_path / "browser-groups.private.jsonl"
    path.write_bytes(path.read_bytes().splitlines(keepends=True)[0])
    with pytest.raises(ValueError, match="JOURNAL_INCOMPLETE"):
        browser.stop_residuals(c, binding, budget, 777)


def test_browser_safe_receipts_bind_exact_sources_and_original_screenshot_bytes(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    tmp_path.chmod(0o700)
    c = cast(
        Case, SimpleNamespace(**vars(case(tmp_path)), inputs={"uv.lock": "a" * 64}, uid=os.getuid())
    )
    tools = {"/approved/component-browser": "a" * 64}
    monkeypatch.setattr(browser, "runtime_tools", lambda _binding: tools)
    source = {
        "head": c.source_sha,
        "tree": c.source_tree,
        "moduleSha256": browser.NATIVE_MODULE_SHA256,
        "inputs": c.inputs,
    }
    native_dir = tmp_path / "native-zoom"
    (native_dir / "screenshots").mkdir(parents=True)
    native_dir.chmod(0o700)
    pages = []
    for label in ("dashboard", "products"):
        css = {"zoom": "1", "transform": "none"}
        before = {
            "outerWidth": 1440,
            "outerHeight": 1000,
            "innerWidth": 1440,
            "innerHeight": 900,
            "devicePixelRatio": 1,
            "rootCss": css,
            "bodyCss": css,
        }
        after = {**before, "innerWidth": 720, "innerHeight": 450, "devicePixelRatio": 2}
        settings = {"mode": "automatic", "scope": "per-tab"}
        names = [label + "-100.png", label + "-200.png"]
        if label == "products":
            names.append("products-200-bottom.png")
        screenshots = []
        for name in names:
            # Header-only component bytes are not evidence of any real image or native browser.
            png = bytes((137, 80, 78, 71, 13, 10, 26, 10)) + bytes((0, 0, 0, 13)) + b"IHDR"
            png += (1440).to_bytes(4) + (900).to_bytes(4)
            path = native_dir / "screenshots" / name
            path.write_bytes(png)
            path.chmod(0o600)
            screenshots.append(
                {
                    "path": "screenshots/" + name,
                    "sha256": hashlib.sha256(png).hexdigest(),
                    "pixelWidth": 1440,
                    "pixelHeight": 900,
                }
            )
        pages.append(
            {
                "label": label,
                "pathname": "/v4/" + label,
                "rowCount": 1,
                "baseline": {"actual": 1, "tabId": 7, "settings": settings},
                "zoom": {
                    "actual": 2,
                    "tabId": 7,
                    "settings": settings,
                    "events": [{"tabId": 7, "oldZoomFactor": 1, "newZoomFactor": 2}],
                },
                "before": before,
                "after": after,
                "screenshots": screenshots,
            }
        )
    report: dict[str, Any] = {
        "source": source,
        "tools": tools,
        "status": browser.NATIVE_STATUS,
        "scope": "SAME_SHELL_VISITOR_READONLY_NATIVE_200",
        "nativeBrowserExit": "NOT_EXPOSED",
        "humanVisualAcceptance": "NOT_RUN",
        "cleanup": {
            "confirmed": True,
            "profileProcesses": [],
            "registeredAlive": [],
            "sourceAfter": source,
            "toolsAfter": tools,
        },
        "requests": {"allowedReads": 2, "refused": []},
        "pages": pages,
        "profile": {
            "path": str(tmp_path / "browser-tmp/playwright_chromiumdev_profile-native200"),
            "mode": 0o700,
            "uid": c.uid,
        },
    }
    native_file = native_dir / "receipt.json"
    native_file.write_text(json.dumps(report))
    native_file.chmod(0o600)
    native_summary = {
        "status": browser.NATIVE_STATUS,
        "receiptPath": str(native_file),
        "nativeBrowserExit": "NOT_EXPOSED",
        "visualAcceptance": "PENDING_REVIEW",
        "receiptSha256": hashlib.sha256(native_file.read_bytes()).hexdigest(),
    }
    for label in ("shell", "business"):
        folder = tmp_path / ("browser-" + label)
        folder.mkdir(mode=0o700)
        value: dict[str, Any] = {
            "source_sha": c.source_sha,
            "source_tree": c.source_tree,
            "scope": "LIVE_" + label.upper() + "_ONLY",
            "native200": native_summary if label == "shell" else "NOT_RUN_IN_THIS_SPEC",
        }
        if label == "shell":
            screenshots = []
            for width in (1440, 1280, 390):
                path = folder / f"shell-{width}.png"
                path.write_bytes(b"component public bytes, not an actual screenshot")
                path.chmod(0o600)
                screenshots.append(
                    {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                )
            value.update(screenshots=screenshots, actual_create_requests=1)
        path = folder / (label + ".safe.json")
        path.write_text(json.dumps(value))
        path.chmod(0o600)
    assert set(browser.validate_receipts(c, {})) == {"shell", "business"}
    bad = {**native_summary, "status": "PASS"}
    with pytest.raises(ValueError, match="PENDING_REVIEW_REQUIRED"):
        browser.validate_native_receipt(c, {}, bad)
    report["cleanup"]["forced"] = True
    native_file.write_text(json.dumps(report))
    forced = {
        **native_summary,
        "receiptSha256": hashlib.sha256(native_file.read_bytes()).hexdigest(),
    }
    with pytest.raises(ValueError, match="CLEANUP_NOT_CONFIRMED"):
        browser.validate_native_receipt(c, {}, forced)
    del report["cleanup"]["forced"]
    report["pages"][0]["zoom"]["actual"] = 1
    native_file.write_text(json.dumps(report))
    changed = {
        **native_summary,
        "receiptSha256": hashlib.sha256(native_file.read_bytes()).hexdigest(),
    }
    with pytest.raises(ValueError, match="FACTOR_EVENT"):
        browser.validate_native_receipt(c, {}, changed)
    report["pages"][0]["zoom"]["actual"] = 2
    native_file.write_text(json.dumps(report))
    (tmp_path / "browser-shell/shell-1440.png").write_bytes(b"changed")
    with pytest.raises(ValueError, match="SCREENSHOT_HASH"):
        browser.validate_receipts(c, {})


def test_browser_runtime_rejects_unbound_source_and_binary_drift_before_launch(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    tmp_path.chmod(0o700)
    c = cast(
        Case,
        SimpleNamespace(
            **vars(case(tmp_path)),
            uid=os.getuid(),
            project="v41qa_component_browser",
            test_image="sha256:" + "c" * 64,
        ),
    )
    executable = tmp_path / "public-binary-fixture"
    executable.write_text("public file fixture; never executed")
    executable.chmod(0o700)
    root = tmp_path / "public-source"
    node = root / ".tools/node/bin/node"
    node.parent.mkdir(parents=True)
    node.write_text("public node fixture; never executed")
    node.chmod(0o700)
    package = root / "frontend/node_modules/playwright/package.json"
    package.parent.mkdir(parents=True)
    package.write_text(json.dumps({"version": "1.64.0"}))
    framework = root / "public-framework"
    framework.write_text("public framework fixture; never loaded")
    monkeypatch.setattr(browser, "ROOT", root)
    auth = str(uuid4())
    value = {
        "schema_version": "v41-browser-runtime-v1",
        "source_sha": c.source_sha,
        "source_tree": c.source_tree,
        "directory": c.directory,
        "uid": c.uid,
        "authorization_id": auth,
        "project": c.project,
        "test_image": c.test_image,
        "executable": str(executable),
        "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "framework": str(framework),
        "framework_sha256": hashlib.sha256(framework.read_bytes()).hexdigest(),
        "node_sha256": hashlib.sha256(node.read_bytes()).hexdigest(),
        "playwright_version": "1.64.0",
    }
    path = tmp_path / "browser-runtime.safe.json"
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    assert browser.runtime(c, auth) == value
    with pytest.raises(ValueError, match="EXACT_BROWSER"):
        browser.runtime(c, str(uuid4()))
    framework.write_text("changed public framework")
    with pytest.raises(ValueError, match="BINARY_HASH"):
        browser.runtime(c, auth)
    framework.write_text("public framework fixture; never loaded")
    executable.write_text("changed public bytes")
    with pytest.raises(ValueError, match="BINARY_HASH"):
        browser.runtime(c, auth)
