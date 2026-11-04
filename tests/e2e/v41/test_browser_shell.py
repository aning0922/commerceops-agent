"""Browser report, journal and process identity components; no browser or services."""

import copy
import hashlib
import json
import os
import signal
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from commerceops.application.v41.contracts import Snapshot
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
    monkeypatch.setattr(browser, "validate_shell_cdp", lambda _case: {})
    monkeypatch.setattr(browser, "validate_business_mobile", lambda _case, _value: {})
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
    assert set(browser.validate_receipts(c, {})) == {
        "shell",
        "business",
        "shell_cdp",
        "business_mobile",
    }
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


def test_shell_cdp_endpoint_rejects_noncanonical_or_symlink(tmp_path: Path) -> None:
    p = tmp_path / "DevToolsActivePort"
    for raw in (
        b"0\n/devtools/browser/x",
        b"052345\n/devtools/browser/x",
        b"52345\nhttps://other",
        b"52345\n/devtools/browser/x\nextra",
    ):
        p.write_bytes(raw)
        p.chmod(0o600)
        with pytest.raises(ValueError):
            browser.shell_cdp_endpoint(tmp_path, os.getuid())
    p.write_bytes(b"52345\n/devtools/browser/owned-one")
    assert browser.shell_cdp_endpoint(tmp_path, os.getuid())[:2] == (
        52345,
        "/devtools/browser/owned-one",
    )
    p.rename(tmp_path / "target")
    p.symlink_to(tmp_path / "target")
    with pytest.raises(ValueError):
        browser.shell_cdp_endpoint(tmp_path, os.getuid())


def test_shell_cdp_listener_is_exact_port_and_refuses_unknown(monkeypatch: MonkeyPatch) -> None:
    budget = SimpleNamespace(timeout=lambda *_a, **_k: 1)
    seen = []

    def fake(argv: list[str], **kwargs: Any) -> Any:
        seen.append(argv)
        return SimpleNamespace(returncode=0, stdout="p123\ncChrome\nn127.0.0.1:52345\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake)
    assert browser.shell_cdp_listener(52345, cast(Any, budget)) == [
        {"pid": 123, "address": "127.0.0.1:52345"}
    ]
    assert seen[0] == ["/usr/sbin/lsof", "-nP", "-iTCP:52345", "-sTCP:LISTEN", "-Fpcn"]
    with pytest.raises(ValueError):
        browser.shell_cdp_listener(True, cast(Any, budget))


def test_shell_cdp_reused_port_never_signals(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    intent: dict[str, Any] = {k: "bound" for k in browser.SHELL_CDP_FIELDS}
    monkeypatch.setattr(browser, "shell_cdp_intent", lambda _case: intent)
    monkeypatch.setattr(
        browser,
        "private_bytes",
        lambda _path: json.dumps(
            {**intent, "schema": "v41-shell-cdp-ack-v1", "port": 52345}
        ).encode(),
    )
    monkeypatch.setattr(
        browser,
        "shell_cdp_listener",
        lambda *_a, **_k: [{"pid": 999, "address": "127.0.0.1:52345"}],
    )
    monkeypatch.setattr(os, "killpg", lambda *_args: pytest.fail("port-reused process signaled"))
    with pytest.raises(ValueError, match="PORT_LIVE_OR_REUSED"):
        browser.shell_cdp_ports_closed(
            cast(Any, SimpleNamespace(directory=str(tmp_path))), cast(Any, None)
        )


@pytest.mark.parametrize("drift", [None, "birth", "ancestry", "native_pid", "argv", "listener"])
def test_shell_cdp_parent_ack_requires_owned_chain_and_exact_endpoint(
    monkeypatch: MonkeyPatch, tmp_path: Path, drift: str | None
) -> None:
    c = cast(Any, SimpleNamespace(directory=str(tmp_path), uid=os.getuid()))
    directory = tmp_path / "browser-shell-cdp"
    directory.mkdir(mode=0o700)
    profile = tmp_path / "browser-tmp/playwright_chromiumdev_profile-shell-cdp-owned"
    profile.mkdir(parents=True, mode=0o700)
    (profile / "DevToolsActivePort").write_bytes(b"52345\n/devtools/browser/owned")
    (profile / "DevToolsActivePort").chmod(0o600)
    rows, binding = browser_process_fixture(tmp_path)
    rows[1]["argv"] = binding["executable"] + " --user-data-dir=" + str(profile)
    intent: dict[str, Any] = {k: "bound" for k in browser.SHELL_CDP_FIELDS}
    intent.update(
        worker_pid=778,
        worker_birth=rows[0]["birth"],
        profile=str(profile),
        executable=binding["executable"],
        argv=["--user-data-dir=" + str(profile)],
    )
    spawned: dict[str, Any] = {k: intent[k] for k in browser.SHELL_CDP_FIELDS}
    spawned.update(schema="v41-shell-cdp-spawn-v1", native_pid=12345)
    (directory / "spawn.private.json").write_text(json.dumps(spawned))
    (directory / "spawn.private.json").chmod(0o600)
    if drift == "birth":
        rows[0]["birth"] = "different birth"
    elif drift == "ancestry":
        rows[1]["ppid"] = 999
    elif drift == "native_pid":
        spawned["native_pid"] = 999
        (directory / "spawn.private.json").write_text(json.dumps(spawned))
    elif drift == "argv":
        rows[1]["argv"] += " --extra-variable"
    monkeypatch.setattr(browser, "shell_cdp_intent", lambda _case: intent)
    monkeypatch.setattr(browser, "inventory", lambda *_a, **_k: rows)
    monkeypatch.setattr(
        browser,
        "shell_cdp_listener",
        lambda *_a, **_k: [
            {"pid": 999 if drift == "listener" else 12345, "address": "127.0.0.1:52345"}
        ],
    )
    # The only source-file read here is the pinned literal argv list; no browser is started.
    fake_root = tmp_path / "source"
    (fake_root / "frontend/v41-e2e").mkdir(parents=True)
    (fake_root / "frontend/v41-e2e/owned-cdp.argv.json").write_text(json.dumps(intent["argv"]))
    monkeypatch.setattr(browser, "ROOT", fake_root)
    if drift is not None:
        with pytest.raises(ValueError):
            browser.register_shell_cdp(c, binding, cast(Any, None), 778, intent["worker_birth"])
        assert not (directory / "endpoint-ack.safe.json").exists()
    else:
        browser.register_shell_cdp(c, binding, cast(Any, None), 778, intent["worker_birth"])
        ack = json.loads((directory / "endpoint-ack.safe.json").read_bytes())
        assert ack["native_pid"] == 12345 and ack["port"] == 52345
        assert {m["pid"] for m in ack["members"]} == {12345, 12346}
        original = (directory / "endpoint-ack.safe.json").read_bytes()
        browser.register_shell_cdp(c, binding, cast(Any, None), 778, intent["worker_birth"])
        assert (directory / "endpoint-ack.safe.json").read_bytes() == original


def test_shell_cdp_intent_binds_case_bytes_source_and_profile(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    root.chmod(0o700)
    c = cast(
        Any,
        SimpleNamespace(
            directory=str(root), source_sha="a" * 40, source_tree="b" * 40, uid=os.getuid()
        ),
    )
    directory = root / "browser-shell-cdp"
    directory.mkdir(mode=0o700)
    nonce = str(uuid4())
    profile = root / "browser-tmp" / ("playwright_chromiumdev_profile-shell-cdp-" + nonce)
    profile.mkdir(parents=True, mode=0o700)
    for name, raw in [
        ("case.json", b'{"complete-case":"component"}'),
        ("browser-runtime.safe.json", b'{"runtime":"component"}'),
    ]:
        (root / name).write_bytes(raw)
        (root / name).chmod(0o600)
    intent = {
        "schema": "v41-shell-cdp-intent-v1",
        "source_sha": c.source_sha,
        "source_tree": c.source_tree,
        "directory": c.directory,
        "uid": c.uid,
        "case_sha256": hashlib.sha256((root / "case.json").read_bytes()).hexdigest(),
        "runtime_sha256": hashlib.sha256(
            (root / "browser-runtime.safe.json").read_bytes()
        ).hexdigest(),
        "title": browser.TITLES["shell.live.spec.ts"],
        "nonce": nonce,
        "profile": str(profile),
        "worker_pid": 123,
        "worker_birth": "Wed Nov 4 11:00:00 2026",
        "executable": "/component/chromium",
        "argv": [],
    }
    path = directory / "intent.private.json"
    path.write_text(json.dumps(intent))
    path.chmod(0o600)
    assert browser.shell_cdp_intent(c) == intent
    for key in ["case_sha256", "runtime_sha256", "source_sha", "source_tree", "profile"]:
        path.write_text(json.dumps({**intent, key: "drift"}))
        with pytest.raises(ValueError):
            browser.shell_cdp_intent(c)


def test_shell_cdp_closure_requires_native_exit_and_bound_page_proof(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    c = cast(Any, SimpleNamespace(directory=str(tmp_path)))
    identity: dict[str, Any] = {k: "bound" for k in browser.SHELL_CDP_FIELDS}
    directory = tmp_path / "browser-shell-cdp"
    directory.mkdir(mode=0o700)
    monkeypatch.setattr(browser, "shell_cdp_intent", lambda _case: identity)
    ack = {**identity, "schema": "v41-shell-cdp-ack-v1", "native_pid": 123, "host": "127.0.0.1"}

    def write(name: str, value: dict[str, Any]) -> str:
        p = directory / name
        p.write_text(json.dumps(value))
        p.chmod(0o600)
        return hashlib.sha256(p.read_bytes()).hexdigest()

    ack_hash = write("endpoint-ack.safe.json", ack)
    page = {
        **identity,
        "schema": "v41-shell-cdp-page-v1",
        "native_pid": 123,
        "ack_sha256": ack_hash,
        "target_id": "owned",
        "window_id": 1,
        "context_id_present": False,
        "context_id": None,
        "initial_url": "about:blank",
        "transport": "OWNED_DEFAULT_CONTEXT_CDP",
        "no_defaults": True,
        "context_count": 1,
        "page_count": 1,
    }
    page_hash = write("page-binding.safe.json", page)
    native = {
        **identity,
        "schema": "v41-shell-cdp-native-exit-v1",
        "native_pid": 123,
        "native_exit": 0,
        "signal": None,
    }
    write("native-exit.private.json", native)
    closeout = {
        **identity,
        "schema": "v41-shell-cdp-closeout-v1",
        "native_pid": 123,
        "ack_sha256": ack_hash,
        "page_binding_sha256": page_hash,
        "status": "NATIVE_CLOSED_PENDING_PARENT_CHECK",
        "close_ack": True,
        "native_exit": 0,
        "signal": None,
        "failures": [],
        "close_failure": None,
    }
    write("closeout.safe.json", closeout)
    assert browser.validate_shell_cdp(c)["path"] == str(directory / "closeout.safe.json")
    deltas: list[dict[str, Any]] = [
        {"native_exit": "UNKNOWN"},
        {"native_exit": True},
        {"close_ack": False},
        {"native_pid": 999},
        {"page_binding_sha256": "different"},
        {"failures": [{"stage": "setup"}]},
    ]
    for delta in deltas:
        write("closeout.safe.json", {**closeout, **delta})
        with pytest.raises(ValueError):
            browser.validate_shell_cdp(c)


def mobile_component_receipt(root: Path) -> tuple[Any, dict[str, Any]]:
    """Synthetic headers/DTOs for pure rejection checks, never real screenshots or API evidence."""
    from .request_witness import canonical

    root = root.resolve()
    root.chmod(0o700)
    c = SimpleNamespace(directory=str(root), source_sha="a" * 40, source_tree="b" * 40)
    context: dict[str, Any] = {
        "tenant_id": str(uuid4()),
        "organization_id": str(uuid4()),
        "principal_id": str(uuid4()),
        "reset_epoch": 0,
        "auth_generation": 1,
    }
    shop = str(uuid4())
    events: list[dict[str, Any]] = []

    def event(op: str | None, key: str | None, state: str, request: Any = None) -> None:
        events.append(
            {
                "schema": "v41-browser-subject-event-1",
                "source_sha": c.source_sha,
                "source_tree": c.source_tree,
                "context": context,
                "shop_id": shop,
                "operation": op,
                "request_key": key,
                "state": state,
                "request": request,
            }
        )

    event(None, None, "ATTEMPT_STARTED")
    ops: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []

    def source(revision: str, uploads: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        normalized = [
            {
                "data_mode": "demo_upload",
                "fixture_digest": "e" * 64,
                "baseline_snapshot_at": "2026-11-02T00:00:00Z",
                "import_row": 2,
                **row,
            }
            for row in uploads or []
        ]
        snapshot = Snapshot.model_validate_json(
            json.dumps(
                {
                    "data_revision": revision,
                    "snapshot_id": "a" * 64,
                    "read_at": "2026-11-04T08:00:00Z",
                    "source": {
                        "data_mode": "demo_mixed" if normalized else "demo_fixture",
                        "fixture_digest": "e" * 64,
                        "baseline_snapshot_at": "2026-11-02T00:00:00Z",
                        "uploads": normalized,
                    },
                }
            )
        ).model_dump(mode="json")
        return {
            "context": context,
            "shop_id": shop,
            "snapshot": snapshot,
            "job": None,
            "file_digest": None,
        }

    def add(
        kind: str,
        resource: str,
        before: str,
        after: str | None,
        version: int = 1,
        fmt: str | None = None,
        parent: str | None = None,
    ) -> dict[str, Any]:
        key = str(uuid4())
        body: dict[str, Any] = {
            "shop_id": shop,
            "request_key": key,
            "expected_epoch": 0,
            "expected_generation": 1,
            "expected_data_revision": before,
        }
        if kind == "preview":
            path = "/api/v4/imports/previews"
            body.update(
                format=fmt,
                filename="component." + str(fmt),
                file_base64="YQ==",
                mapping_version=1,
                parent_job_id=parent,
                mapping=None
                if parent is None
                else {
                    "sku": "sku",
                    "title": "title",
                    "price": "price",
                    "currency": "currency",
                    "tags": None,
                },
            )
        else:
            name = (
                "products"
                if kind == "product_tags"
                else "orders"
                if kind == "order_fulfillment"
                else "imports"
            )
            path = (
                f"/api/v4/{name}/{resource}/"
                + {
                    "product_tags": "tags",
                    "order_fulfillment": "fulfillment",
                    "import_confirm": "confirm",
                }[kind]
            )
            body["expected_job_version" if kind == "import_confirm" else "expected_version"] = (
                version if kind == "import_confirm" else version - 1
            )
            if kind == "product_tags":
                body["tags"] = ["same-label"]
            elif kind == "order_fulfillment":
                body["action"] = "mark_demo_fulfilled"
            else:
                body["expected_job_digest"] = "d" * 64
        witness = {
            "method": "POST",
            "path": path,
            "body": body,
            "request_body_sha256": hashlib.sha256(canonical(body).encode()).hexdigest(),
        }
        event(kind, key, "ATTEMPT_STARTED", witness)
        event(kind, key, "ACK_OK" if kind == "preview" else "ACK_COMMITTED")
        event(kind, state="COMMITTED_READBACK", key=key)
        read = {
            **source(after or before),
            "resource_id": resource,
            "version": version,
            "tags": ["same-label"] if kind == "product_tags" else None,
            "demo_fulfillment": "demo_fulfilled" if kind == "order_fulfillment" else None,
            "state": "COMMITTED",
            "row_count": 1,
        }
        if kind == "preview":
            read["snapshot"] = None
        if kind in {"preview", "import_confirm"}:
            read.update(
                job={
                    "import_job_id": resource,
                    "version": version,
                    "data_revision": before,
                    "job_digest": "d" * 64,
                },
                file_digest=hashlib.sha256(b"a").hexdigest(),
            )
            if kind == "import_confirm":
                read["dataset"] = source(
                    str(after),
                    [{"import_job_id": resource, "file_digest": hashlib.sha256(b"a").hexdigest()}],
                )
        operation = {
            "operation": kind,
            "key": key,
            "resource_id": resource,
            "version": version,
            "before_revision": before,
            "after_revision": after,
            "effect_count": None if kind == "preview" else 1,
            "context": context,
            "shop_id": shop,
            "width": 390,
            "post_ordinal": len(ops) + 1,
            "status": "OK" if kind == "preview" else "COMMITTED",
            "readback": read,
        }
        ops.append(operation)
        pending.append(
            {
                "key": key,
                "operation": "import_preview" if kind == "preview" else kind,
                "resource_id": None if kind == "preview" else resource,
                "shop_id": shop,
                "context": context,
                "version": version - 1 if kind != "import_confirm" else version,
                "revision": before,
            }
        )
        return operation

    first = add("product_tags", str(uuid4()), "0" * 64, "1" * 64)
    second = add("product_tags", str(uuid4()), "1" * 64, "2" * 64)
    fulfillment = add("order_fulfillment", str(uuid4()), "2" * 64, "3" * 64)
    pipelines = {}
    revision = "3" * 64
    for index, fmt in enumerate(("csv", "xlsx")):
        discovery = add("preview", str(uuid4()), revision, None, fmt=fmt)
        mapped = add(
            "preview",
            str(uuid4()),
            revision,
            None,
            version=2,
            fmt=fmt,
            parent=discovery["resource_id"],
        )
        committed = add(
            "import_confirm", mapped["resource_id"], revision, str(index + 4) * 64, version=2
        )
        revision = committed["after_revision"]
        pipelines[fmt] = (discovery, mapped, committed)
    journal(root, "business", events)
    directory = root / "browser-business"
    directory.mkdir(mode=0o700)
    screenshots = []
    required = {
        (state, width) for state in browser.MOBILE_STATES for width in (390, 1280, 1440)
    } | {(state, 390) for state in browser.MOBILE_EXTRAS}
    for state, width in sorted(required):
        src = source("0" * 64)
        if state in {"anonymous_empty", "second_visitor_empty"}:
            src = {
                "permission": "anonymous",
                "revocation_tested": False,
                "context": None,
                "shop_id": None,
            }
        elif state in {"csv_mapping", "xlsx_mapping"}:
            src = {
                name: pipelines[state.split("_")[0]][0]["readback"][name]
                for name in ("context", "shop_id", "snapshot", "job", "file_digest")
            }
        elif state in {"csv_readback", "xlsx_readback"}:
            src = pipelines[state.split("_")[0]][2]["readback"]["dataset"]
        route = "/v4/products"
        if state in {"product_detail", "tag_edit", "tag_readback"}:
            route += "/" + first["resource_id"]
        elif state in {"order_detail", "fulfillment_confirm", "fulfillment_readback"}:
            route = "/v4/orders/" + fulfillment["resource_id"]
        elif state == "order_list":
            route = "/v4/orders"
        elif state in {"csv_mapping", "xlsx_mapping"}:
            route = "/v4/products/import"
        if state == "tag_readback":
            src = source(first["after_revision"])
        elif state == "fulfillment_readback":
            src = source(fulfillment["after_revision"])
        elif state == "batch_readback":
            src = source(second["after_revision"])
        elif state in {"order_list", "order_detail", "fulfillment_confirm"}:
            src = source(fulfillment["before_revision"])
        png = (
            bytes((137, 80, 78, 71, 13, 10, 26, 10))
            + bytes((0, 0, 0, 13))
            + b"IHDR"
            + width.to_bytes(4)
            + (900).to_bytes(4)
        )
        p = directory / f"{state}-{width}.png"
        p.write_bytes(png)
        p.chmod(0o600)
        screenshots.append(
            {
                "state": state,
                "width": width,
                "path": str(p),
                "sha256": hashlib.sha256(png).hexdigest(),
                "pixel_width": width,
                "pixel_height": 900,
                "viewport": {"width": width, "height": 900, "dpr": 1},
                "route": route,
                "source": src,
            }
        )
    batch = {
        "selected_ids": [first["resource_id"], second["resource_id"]],
        "keys": [first["key"], second["key"]],
        "initial_revision": first["before_revision"],
        "current_page": {
            "items": [
                {"product_id": op["resource_id"], "version": op["version"] - 1}
                for op in (first, second)
            ],
            "query": "?shop_id=" + shop,
            "source": source(first["before_revision"]),
        },
        "serial_readback": True,
        "serial_evidence": [
            {
                "previous_key": first["key"],
                "next_key": second["key"],
                "read_start": 1000,
                "read_end_offset": 20,
                "next_post_start": 1021,
            }
        ],
        "progress": {"已核成功": 2, "明确拒绝": 0, "待核对": 0, "未发送": 0},
    }
    mobile = {
        "schema": "v41-business-mobile-v1",
        "screenshots": screenshots,
        "operations": ops,
        "pending_proofs": pending,
        "mobile_keys": [op["key"] for op in ops],
        "batch": batch,
        "permission_evidence": "ANONYMOUS_ONLY_NOT_403_REVOKED",
        "interactions": [
            {
                "state": state,
                "width": 390,
                "tab_inside": True,
                "escape": "NON_MODAL_NO_POST"
                if state.endswith("_mapping")
                else "RETURNED_LIST_NO_POST",
            }
            for state in (
                "product_detail",
                "fulfillment_confirm",
                "tag_edit",
                "csv_mapping",
                "xlsx_mapping",
            )
        ],
    }
    counts = {
        "tag_committed": sum(op["operation"] == "product_tags" for op in ops),
        "fulfillment_committed": sum(op["operation"] == "order_fulfillment" for op in ops),
        "preview_committed": sum(op["operation"] == "preview" for op in ops),
        "import_committed": sum(op["operation"] == "import_confirm" for op in ops),
        "downloads": 0,
    }
    return c, {"mobile_business": mobile, "counts": counts, "facts": {"downloads": []}}


def test_mobile_receipt_accepts_only_journal_bound_dynamic_facts(tmp_path: Path) -> None:
    c, value = mobile_component_receipt(tmp_path)
    result = browser.validate_business_mobile(c, value)
    assert len(result["confirmed_keys"]) == len(value["mobile_business"]["operations"])
    assert result["png_count"] == len(value["mobile_business"]["screenshots"])


@pytest.mark.parametrize(
    "drift",
    [
        "missing_png",
        "png_hash",
        "png_geometry",
        "png_path",
        "png_scope",
        "count",
        "key",
        "pending",
        "version",
        "mobile",
        "batch_scope",
        "batch_revision",
        "batch_member",
        "batch_time",
        "batch_progress",
        "format_source",
        "anonymous",
        "journal_unknown",
    ],
)
def test_mobile_receipt_rejects_missing_mismatched_or_ambiguous(tmp_path: Path, drift: str) -> None:
    c, value = mobile_component_receipt(tmp_path)
    mobile = value["mobile_business"]
    if drift == "missing_png":
        mobile["screenshots"].pop()
    elif drift == "png_hash":
        mobile["screenshots"][0]["sha256"] = "wrong"
    elif drift == "png_geometry":
        mobile["screenshots"][0]["pixel_width"] += 1
    elif drift == "png_path":
        mobile["screenshots"][0]["path"] = str(tmp_path.parent / "unowned.png")
    elif drift == "png_scope":
        mobile["screenshots"][1]["source"] = {
            "context": {**mobile["operations"][0]["context"], "reset_epoch": 999},
            "shop_id": mobile["operations"][0]["shop_id"],
            "snapshot": {},
        }
    elif drift == "count":
        value["counts"]["tag_committed"] += 1
    elif drift == "key":
        mobile["operations"][0]["key"] = mobile["operations"][1]["key"]
    elif drift == "pending":
        mobile["pending_proofs"][0]["key"] = str(uuid4())
    elif drift == "version":
        mobile["operations"][0]["version"] += 1
    elif drift == "mobile":
        mobile["mobile_keys"].pop()
    elif drift == "batch_scope":
        mobile["batch"]["current_page"]["query"] = "?shop_id=" + str(uuid4())
    elif drift == "batch_revision":
        mobile["batch"]["initial_revision"] = "9" * 64
    elif drift == "batch_member":
        mobile["batch"]["selected_ids"][0] = str(uuid4())
    elif drift == "batch_time":
        mobile["batch"]["serial_evidence"][0]["next_post_start"] = 1001
    elif drift == "batch_progress":
        mobile["batch"]["progress"]["待核对"] = 1
    elif drift == "format_source":
        for shot in mobile["screenshots"]:
            if shot["state"] == "xlsx_mapping":
                shot["source"] = next(
                    s["source"] for s in mobile["screenshots"] if s["state"] == "csv_mapping"
                )
    elif drift == "anonymous":
        mobile["screenshots"][0]["source"]["revocation_tested"] = True
    elif drift == "journal_unknown":
        path = tmp_path / "browser-business.subjects.private.jsonl"
        path.write_bytes(path.read_bytes().replace(b"ACK_COMMITTED", b"ACK_UNKNOWN", 1))
    with pytest.raises(ValueError):
        browser.validate_business_mobile(c, value)


@pytest.mark.parametrize("status", ["UNKNOWN", "COMMITTED", "REJECTED"])
def test_preview_status_must_match_original_ack(tmp_path: Path, status: str) -> None:
    c, value = mobile_component_receipt(tmp_path)
    next(op for op in value["mobile_business"]["operations"] if op["operation"] == "preview")[
        "status"
    ] = status
    with pytest.raises(ValueError, match="STATUS_ACK_MISMATCH"):
        browser.validate_business_mobile(c, value)


def test_preview_ack_cannot_be_relabelled_while_status_stays_ok(tmp_path: Path) -> None:
    c, value = mobile_component_receipt(tmp_path)
    path = tmp_path / "browser-business.subjects.private.jsonl"
    events = [json.loads(line) for line in path.read_bytes().splitlines()]
    next(
        event for event in events if event["operation"] == "preview" and event["state"] == "ACK_OK"
    )["state"] = "ACK_COMMITTED"
    journal(tmp_path, "business", events)
    with pytest.raises(ValueError, match="STATUS_ACK_MISMATCH"):
        browser.validate_business_mobile(c, value)


def test_action_committed_ack_cannot_claim_unknown_status(tmp_path: Path) -> None:
    c, value = mobile_component_receipt(tmp_path)
    value["mobile_business"]["operations"][0]["status"] = "UNKNOWN"
    with pytest.raises(ValueError, match="STATUS_ACK_MISMATCH"):
        browser.validate_business_mobile(c, value)


def test_all_reported_file_digests_cannot_override_original_bytes(tmp_path: Path) -> None:
    c, value = mobile_component_receipt(tmp_path)
    actual = hashlib.sha256(b"a").hexdigest()
    forged = json.loads(json.dumps(value).replace(actual, "9" * 64))
    # All job/upload/mapping/screenshot summaries agree with each other, but not raw POST bytes.
    with pytest.raises(ValueError, match="PREVIEW_ORIGINAL_BYTES_DIGEST"):
        browser.validate_business_mobile(c, forged)


def test_changed_original_base64_is_independently_rehashed(tmp_path: Path) -> None:
    c, value = mobile_component_receipt(tmp_path)
    path = tmp_path / "browser-business.subjects.private.jsonl"
    events = [json.loads(line) for line in path.read_bytes().splitlines()]
    event = next(
        e for e in events if e["operation"] == "preview" and e["state"] == "ATTEMPT_STARTED"
    )
    event["request"]["body"]["file_base64"] = "Yg=="
    event["request"]["request_body_sha256"] = hashlib.sha256(
        canonical(event["request"]["body"]).encode()
    ).hexdigest()
    journal(tmp_path, "business", events)
    with pytest.raises(ValueError, match="PREVIEW_ORIGINAL_BYTES_DIGEST"):
        browser.validate_business_mobile(c, value)


def test_mapping_cannot_borrow_another_legitimately_registered_scope(tmp_path: Path) -> None:
    c, value = mobile_component_receipt(tmp_path)
    path = tmp_path / "browser-business.subjects.private.jsonl"
    events = [json.loads(line) for line in path.read_bytes().splitlines()]
    registration = copy.deepcopy(events[0])
    registration["context"].update(
        tenant_id=str(uuid4()), organization_id=str(uuid4()), principal_id=str(uuid4())
    )
    registration["shop_id"] = str(uuid4())
    events.insert(0, registration)
    journal(tmp_path, "business", events)
    for shot in value["mobile_business"]["screenshots"]:
        if shot["state"] == "csv_mapping":
            shot["source"] = {
                **copy.deepcopy(shot["source"]),
                "context": registration["context"],
                "shop_id": registration["shop_id"],
            }
    # The second scope really is registered; membership alone must not confer job provenance.
    with pytest.raises(ValueError, match="SCREENSHOT_MAIN_SCOPE"):
        browser.validate_business_mobile(c, value)


@pytest.mark.parametrize("field", ["all", "snapshot_id", "read_at", "source", "extra", "evidence"])
def test_three_width_snapshot_uses_frozen_public_dto(tmp_path: Path, field: str) -> None:
    c, value = mobile_component_receipt(tmp_path)
    shot = next(
        s
        for s in value["mobile_business"]["screenshots"]
        if s["state"] == "product_list" and s["width"] == 1280
    )
    shot["source"] = copy.deepcopy(shot["source"])
    snapshot = shot["source"]["snapshot"]
    if field == "all":
        shot["source"]["snapshot"] = {}
    elif field == "extra":
        snapshot["not_a_public_field"] = True
    elif field == "evidence":
        snapshot["source"]["evidence_mode"] = "financial_authority"
    else:
        del snapshot[field]
    with pytest.raises(ValueError):
        browser.validate_business_mobile(c, value)


def test_valid_but_unrelated_fixture_snapshot_is_not_operation_source(tmp_path: Path) -> None:
    c, value = mobile_component_receipt(tmp_path)
    for shot in value["mobile_business"]["screenshots"]:
        if shot["state"] == "tag_edit":
            shot["source"] = copy.deepcopy(shot["source"])
            shot["source"]["snapshot"]["source"]["fixture_digest"] = "9" * 64
    with pytest.raises(ValueError, match="FIXTURE_SOURCE_CHAIN"):
        browser.validate_business_mobile(c, value)


def test_late_qa_readback_marker_is_not_a_global_network_order_gate(tmp_path: Path) -> None:
    c, value = mobile_component_receipt(tmp_path)
    path = tmp_path / "browser-business.subjects.private.jsonl"
    events = [json.loads(line) for line in path.read_bytes().splitlines()]
    first, second = value["mobile_business"]["batch"]["keys"]
    # The true fresh GET can finish before QA persists READBACK after Promise.all.
    mark = next(
        e for e in events if e["request_key"] == first and e["state"] == "COMMITTED_READBACK"
    )
    events.remove(mark)
    position = next(
        i
        for i, e in enumerate(events)
        if e["request_key"] == second and e["state"] == "ACK_COMMITTED"
    )
    events.insert(position + 1, mark)
    journal(tmp_path, "business", events)
    assert browser.validate_business_mobile(c, value)["confirmed_keys"]


@pytest.mark.parametrize("location", ["preview", "import_confirm", "mapping_screenshot"])
def test_one_job_projection_version_cannot_drift(tmp_path: Path, location: str) -> None:
    c, value = mobile_component_receipt(tmp_path)
    mobile = value["mobile_business"]
    if location == "mapping_screenshot":
        shot = next(
            s for s in mobile["screenshots"] if s["state"] == "csv_mapping" and s["width"] == 390
        )
        shot["source"] = copy.deepcopy(shot["source"])
        shot["source"]["job"]["version"] = 999
        reason = "THREE_WIDTH_SOURCE_MISMATCH"
    else:
        op = next(op for op in mobile["operations"] if op["operation"] == location)
        op["readback"]["job"] = {**op["readback"]["job"], "version": 999}
        reason = "JOB_PROJECTION_VERSION_BINDING"
    with pytest.raises(ValueError, match=reason):
        browser.validate_business_mobile(c, value)


def test_all_job_projections_cannot_agree_on_version_999(tmp_path: Path) -> None:
    c, value = mobile_component_receipt(tmp_path)
    mobile = value["mobile_business"]
    journal_path = tmp_path / "browser-business.subjects.private.jsonl"
    original_journal = journal_path.read_bytes()
    originals = [
        (op["key"], op["version"], op["readback"]["version"]) for op in mobile["operations"]
    ]
    pending_versions = [proof["version"] for proof in mobile["pending_proofs"]]
    for op in mobile["operations"]:
        if op["readback"].get("job") is not None:
            op["readback"]["job"]["version"] = 999
    for shot in mobile["screenshots"]:
        if shot["source"].get("job") is not None:
            shot["source"]["job"]["version"] = 999
    assert originals == [
        (op["key"], op["version"], op["readback"]["version"]) for op in mobile["operations"]
    ]
    assert pending_versions == [proof["version"] for proof in mobile["pending_proofs"]]
    assert journal_path.read_bytes() == original_journal
    with pytest.raises(ValueError, match="JOB_PROJECTION_VERSION_BINDING"):
        browser.validate_business_mobile(c, value)
