"""human协调的认证/原key读取边界；HTTP模拟仅属offline，非真实PG验收。"""

import json
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest

from scripts.p4_acceptance import AcceptanceFailure, _human_auth_get, digest, write_private

pytestmark = pytest.mark.offline


@pytest.mark.parametrize("fault", [None, "login", "session", "original_get", "dto"])
def test_current_identity_auth_then_original_GET_never_business_POST_or_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str | None
) -> None:
    tmp_path.chmod(0o700)
    credentials = tmp_path / "credentials.json"
    write_private(credentials, {"login": "synthetic-operator", "password": "dummy"})
    schema = tmp_path / "schema.json"
    write_private(schema, {})
    context = dict(
        principal_id=str(uuid4()),
        organization_id=str(uuid4()),
        identity_id=str(uuid4()),
        auth_version=4,
        item_id=str(uuid4()),
    )
    key = str(uuid4())
    calls = []

    def transport(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        assert request.url.host == "127.0.0.1"
        if request.url.path.endswith("/csrf"):
            return httpx.Response(
                200,
                json={"csrf_token": "synthetic-csrf"},
                headers={
                    "Set-Cookie": (
                        "commerceops_session=synthetic-session; Path=/; HttpOnly; SameSite=Lax"
                    )
                },
            )
        if request.url.path.endswith("/login"):
            assert request.headers["X-CSRF-Token"] == "synthetic-csrf"
            assert json.loads(request.content) == {
                "schema_version": "p3-web-v1",
                "login": "synthetic-operator",
                "password": "dummy",
            }
            return httpx.Response(401 if fault == "login" else 200, json={"csrf_token": "c" * 43})
        if request.url.path.endswith("/session"):
            if fault == "session":
                return httpx.Response(401, json={})
            return httpx.Response(
                200,
                json={
                    "csrf_token": "c" * 43,
                    "principal": {
                        "principal_id": context["principal_id"],
                        "organization_id": context["organization_id"],
                        "auth_version": 4,
                        "linked_channels": ["web"],
                    },
                },
            )
        if "/replenishment-items/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "item": {
                        "item_id": context["item_id"],
                        "state": "closed",
                        "version": 2,
                        "sync": {"state": "pending"},
                    }
                },
            )
        if "/requests/" in request.url.path:
            assert request.method == "GET" and dict(request.url.params) == {"operation": "resolve"}
            return httpx.Response(
                404 if fault == "original_get" else 200, json={"request_key": key}
            )
        assert request.url.path.endswith("/logout")
        assert request.headers["X-CSRF-Token"] == "c" * 43
        return httpx.Response(200, json={})

    original = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(transport), **kwargs),
    )
    # C的strict schema另有独立用例；本单测只隔离本批认证/GET调用顺序与失败终止。
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 1 if fault == "dto" else 0),
    )
    root = Path(__file__).resolve().parents[1]
    node = Path(sys.executable).resolve()
    handoff = {
        "private_refs": {
            "web_credentials": {
                "path": str(credentials),
                "sha256": digest(credentials.read_bytes()),
            }
        },
        "web": {"api_origin": "http://127.0.0.1:18180", "web_origin": "http://127.0.0.1:18181"},
        "resource": {
            "runtime": {
                "deadline_utc": (datetime.now(UTC) + timedelta(seconds=600)).isoformat(),
                "monotonic_end": time.monotonic() + 600,
                "cleanup_reserve_seconds": 180,
            }
        },
        "candidate": {
            "toolchain": {
                "node_executable": str(node),
                "node_sha256": digest(node.read_bytes()),
                "read_schema_path": str(schema),
                "read_schema_sha256": digest(schema.read_bytes()),
                "frontend_node_modules": "/synthetic/node_modules",
                "ui_helper_sha256": digest(
                    (root / "tests/e2e/web/m1_acceptance_ui.cjs").read_bytes()
                ),
            }
        },
    }
    if fault:
        with pytest.raises(AcceptanceFailure):
            _human_auth_get(handoff, key, context)
    else:
        result = _human_auth_get(handoff, key, context)
        assert result["auth"] == {
            "bootstrap_GET": 1,
            "login_POST": 1,
            "session_GET": 1,
            "item_GET": 1,
            "original_key_GET": 1,
            "logout_POST": 1,
            "business_POST": 0,
        }
        assert result["value"]["status"] == 200
    assert calls.count(("POST", "/api/v1/auth/login")) == 1
    assert not any(
        method == "POST" and not path.startswith("/api/v1/auth/") for method, path in calls
    )
    if fault in ("session", "dto", "original_get"):
        assert calls[-1] == ("POST", "/api/v1/auth/logout")
    if fault in ("login", "session", "dto"):
        assert not any("/requests/" in path for _, path in calls)


def phase_request(tmp_path: Path) -> tuple[dict[str, Any], Any]:
    from types import SimpleNamespace

    from commerceops.infrastructure.database import DatabaseSettings

    tmp_path.chmod(0o700)
    start = datetime.now(UTC) - timedelta(seconds=1)
    candidate = {"source_sha": "a" * 40, "tree": "b" * 40}
    owner_file = tmp_path / "owner.json"
    write_private(
        owner_file,
        DatabaseSettings(
            host="127.0.0.1",
            name="p4_ro_lab_synthetic",
            user="commerceops_owner",
            password_file=tmp_path / "dummy-material",
        ).model_dump(mode="json"),
    )
    phases = {}
    for i, name in enumerate(("human", "terminal")):
        end = start + timedelta(seconds=600 * (i + 1))
        phases[name] = dict(
            not_before_utc=(start + timedelta(seconds=600 * i)).isoformat(),
            runtime=dict(
                deadline_utc=end.isoformat(),
                monotonic_end=time.monotonic() + (end - datetime.now(UTC)).total_seconds(),
                cleanup_reserve_seconds=180,
            ),
            private_directory=str(tmp_path),
            pg_resource=dict(volume="p4terminal-shared", project="p4terminal-" + name),
            private_refs=dict(
                owner_database=dict(path=str(owner_file), sha256=digest(owner_file.read_bytes())),
                lab_http={},
            ),
        )
    end = start + timedelta(seconds=1200)
    return dict(
        transport="lab",
        phases=phases,
        runtime=dict(
            deadline_utc=end.isoformat(),
            monotonic_end=time.monotonic() + 1199,
            cleanup_reserve_seconds=180,
        ),
    ), SimpleNamespace(manifest=dict(candidate=candidate), check_loaded=lambda: None)


@pytest.mark.parametrize("fault", ["real_release", "overlap", "extended_total", "different_volume"])
def test_two_phase_plan_rejects_before_starting_any_resource(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    from scripts import p4_acceptance as acceptance

    request, binding = phase_request(tmp_path)
    if fault == "real_release":
        request.update(transport="real", root_real_release=True)
    elif fault == "overlap":
        request["phases"]["terminal"]["not_before_utc"] = (
            datetime.now(UTC) + timedelta(seconds=10)
        ).isoformat()
    elif fault == "extended_total":
        end = datetime.now(UTC) + timedelta(seconds=1201)
        request["phases"]["terminal"]["runtime"]["deadline_utc"] = request["runtime"][
            "deadline_utc"
        ] = end.isoformat()
    else:
        request["phases"]["terminal"]["pg_resource"]["volume"] = "another-volume"
    calls = []
    monkeypatch.setattr(acceptance, "_ro_resource", lambda *a, **kw: calls.append(a))
    with pytest.raises(AcceptanceFailure):
        acceptance.human_terminal_stage(request, binding)
    assert calls == []


def test_human_resource_failure_still_closes_web_and_original_pg(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import p4_acceptance as acceptance

    request, binding = phase_request(tmp_path)
    phase = request["phases"]["human"]
    phase.update(
        revision="0015",
        manifest_ref={},
        toolchain={},
        web=dict(api_origin="http://127.0.0.1:18180", web_origin="http://127.0.0.1:18181"),
        api_port=18180,
        web_resource=dict(port=18181),
        run_id=str(uuid4()),
        human_report_file=str(tmp_path / "human-report.json"),
        original_get_file=str(tmp_path / "get.json"),
        capture_context=dict(
            revision="0015_p4_read_replies",
            organization_id=str(uuid4()),
            shop_id=str(uuid4()),
            task_id=str(uuid4()),
            item_id=str(uuid4()),
            principal_id=str(uuid4()),
            identity_id=str(uuid4()),
            auth_version=1,
            checkpoint_threads=["synthetic"],
            sdk_subject_ids=[],
            sdk_window_id=None,
            request_key=None,
            case_kind="recover_single_item",
            expected_item_count=1,
            expected_quantity_total="70",
        ),
    )
    calls = []
    monkeypatch.setattr(acceptance, "_ro_context", lambda *a: None)

    def pg(*args: Any, start: bool) -> dict[str, bool]:
        calls.append("PG-up" if start else "PG-down")
        return dict(verified=True)

    def web(*args: Any, start: bool) -> dict[str, bool]:
        calls.append("Web-up" if start else "Web-down")
        if start:
            raise AcceptanceFailure("P4A_RESOURCE_ALLOWLIST")
        return dict(verified=True)

    monkeypatch.setattr(acceptance, "_ro_resource", pg)
    monkeypatch.setattr(acceptance, "human_web_resource", web)
    result = acceptance.human_t6_stage(phase, binding)
    assert result["exit_code"] == 1 and result["stages"]["RESOURCE"]["state"] == "FAILED"
    assert result["cleanup_verified"] is True and result["stages"]["T6"]["state"] == "NOT_RUN"
    assert calls == ["PG-up", "Web-up", "Web-down", "PG-down"]
