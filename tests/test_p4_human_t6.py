"""human协调的认证/原key读取边界；HTTP模拟仅属offline，非真实PG验收。"""

import json
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
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
