"""Offline negative_child through real HTTP routes and DecisionStore, synthetic SQL only."""

import json
import secrets
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import httpx
import pytest
from commerceops.application.replenishment.contracts import WebActor, WebFailure
from commerceops.application.replenishment.security import digest
from commerceops.entrypoints import replenishment_http as routes
from commerceops.entrypoints.api import create_app
from commerceops.infrastructure import approval_decisions as decisions
from commerceops.infrastructure.database import DatabaseSettings
from commerceops.infrastructure.replenishment_repository import ReplenishmentStore
from commerceops.infrastructure.web_config import WebConfig
from fastapi.testclient import TestClient

from scripts import m2_owned as target
from scripts.m2_backup import BackupFailure
from scripts.m2_state import save
from tests.test_m2_owned import fixture_request

pytestmark = pytest.mark.offline


@pytest.mark.parametrize("phase", ["revoked", "expired"])
@pytest.mark.parametrize(
    "mode",
    [
        "native",
        "wrong_code",
        "non_json",
        "timeout",
        "wrong_auth",
        "csrf",
        "bad_envelope",
        "unknown_code",
        "side_effect",
        "wrong_clock",
        "wrong_request",
        "invalid_json",
    ],
)
def test_real_negative_child_and_native_routes_fail_closed(
    tmp_path: Path, monkeypatch: Any, phase: str, mode: str
) -> None:
    directory, request = fixture_request(tmp_path)
    now = datetime.now(UTC)
    delta = 300 if phase == "revoked" else -1
    expiry = now + timedelta(seconds=(-delta if mode == "wrong_clock" else delta))
    task, plan, approval, organization, shop, principal = [uuid4() for _ in range(6)]
    actor = WebActor(uuid4(), principal, uuid4(), organization, 1)
    nonce = "N" * 43
    token = "C" * 43
    canonical = dict(
        task_id=str(task),
        plan_id=str(plan),
        approval_id=str(approval),
        organization_id=str(organization),
        shop_id=str(shop),
        plan_version=1,
        plan_hash="a" * 64,
        expires_at=expiry.isoformat(),
        required_assumption_keys=["inbound_unknown_zero:test"],
    )
    body = dict(
        schema_version="p3-web-v1",
        request_key=str(uuid4()),
        approval_id=str(approval),
        plan_id=str(plan),
        plan_version=1,
        plan_hash="a" * 64,
        action="approve_with_assumptions",
        acknowledged_assumption_keys=["inbound_unknown_zero:test"],
        nonce=nonce,
    )
    raw = json.dumps(body).encode()
    save(directory / "canonical/m2-facts.private.json", dict(canonical_source=canonical))
    save(
        directory / "seed.private.json",
        dict(
            accounts=dict(
                approver=dict(
                    expected_principal_id=str(principal),
                    login="owned-offline",
                    password=secrets.token_urlsafe(32),
                )
            )
        ),
    )
    save(directory / "restored/restored-decision-request.private.json", raw)
    save(
        directory / "restored/restored-observed.private.json",
        dict(decision_request_key=str(uuid4()) if mode == "wrong_request" else body["request_key"]),
    )
    approval_row = dict(
        id=approval,
        task_id=task,
        plan_id=plan,
        plan_version=1,
        plan_hash="a" * 64,
        status="pending",
        expires_at=expiry,
        nonce_hash=digest(nonce),
        now=now,
        decision_id=None,
        eligible_principal_ids=[principal],
    )
    sql_queries: list[str] = []

    class DB:
        def execute(self, query: Any, params: Any = ()) -> Any:
            text = query if isinstance(query, str) else query.as_string()
            sql_queries.append(text)
            assert text.startswith("SELECT "), "negative contract must have zero SQL writes"
            if "count(*)" in text:
                answer = {"n": int(mode == "side_effect" and "executions" in text)}
            elif "FROM business.business_tasks" in text:
                answer = dict(id=task, shop_id=shop)
            elif "FROM business.replenishment_plans" in text:
                answer = dict(id=plan)
            elif "FROM business.web_requests" in text:
                answer = None
            elif "FROM business.approvals" in text:
                answer = approval_row
            else:
                answer = None
            return SimpleNamespace(fetchone=lambda: answer, fetchall=lambda: [answer])

    @contextmanager
    def connect(*args: Any, **kwargs: Any) -> Any:
        yield DB()

    config = WebConfig(
        database=DatabaseSettings(
            host="127.0.0.1", name="offline", user="offline", password_file=tmp_path / "unused"
        ),
        csrf_secret=b"c" * 32,
        nonce_secret=b"n" * 32,
        origins=(request["web_origin"],),
        transport_mode="local_http",
    )
    monkeypatch.setattr(target, "database", lambda *a, **kw: config.database)
    monkeypatch.setattr("commerceops.infrastructure.database.connect", connect)
    monkeypatch.setattr(decisions, "connect", connect)
    monkeypatch.setattr(routes, "connect", connect)
    monkeypatch.setattr(routes, "now", lambda _: now)
    monkeypatch.setattr(decisions, "now", lambda _: now)
    monkeypatch.setattr(decisions, "actor_guard", lambda *a: {})
    monkeypatch.setattr(decisions, "visible_task", lambda *a: dict(id=task, shop_id=shop))
    monkeypatch.setattr(decisions, "role_scope", lambda *a: phase == "expired")
    monkeypatch.setattr(decisions, "nonce_for", lambda *a: nonce)
    monkeypatch.setattr(
        "commerceops.infrastructure.replenishment_repository.has_capability", lambda *a: True
    )

    def identity() -> dict[str, Any]:
        return dict(
            schema_version="p3-web-v1",
            identity_mode="session",
            csrf_token=token,
            principal=dict(
                principal_id=str(uuid4() if mode == "wrong_auth" else principal),
                organization_id=str(organization),
            ),
        )

    class Sessions:
        def __init__(self, *args: Any) -> None:
            pass

        def bootstrap(self, supplied: Any) -> Any:
            return "synthetic-cookie", dict(
                schema_version="p3-web-v1", identity_mode="anonymous_bootstrap", csrf_token=token
            )

        def login(self, *args: Any) -> Any:
            return "synthetic-cookie", identity()

        def read(self, *args: Any) -> Any:
            return identity()

        def authenticate(self, *args: Any) -> Any:
            return actor

        def check_csrf(self, cookie: Any, supplied: str) -> None:
            if supplied != token:
                raise WebFailure("CSRF_INVALID", 403)

    monkeypatch.setattr(routes, "SessionStore", Sessions)
    store = ReplenishmentStore(config, target.ROOT / "tests/fixtures/commerce/inventory-v1")
    client_class = httpx.Client
    sent: list[str] = []
    with TestClient(
        create_app(web_config=config, replenishment_store=store), base_url=request["api_origin"]
    ) as web:

        def transport(req: httpx.Request) -> httpx.Response:
            path = req.url.path
            sent.append(path)
            headers = dict(req.headers)
            if path.endswith("/decision"):
                assert req.content == raw and headers["origin"] == request["web_origin"]
                if mode == "timeout":
                    raise httpx.ReadTimeout("private-exception-must-not-escape", request=req)
                if mode == "invalid_json":
                    return httpx.Response(
                        403, content=b"{", headers={"Content-Type": "application/json"}
                    )
                if mode == "non_json":
                    return httpx.Response(403, text="private-body-must-not-escape")
                if mode in ("wrong_code", "unknown_code", "bad_envelope"):
                    code = (
                        "CSRF_INVALID"
                        if mode == "wrong_code"
                        else "private-code-must-not-escape"
                        if mode == "unknown_code"
                        else "ACCESS_DENIED"
                    )
                    response = routes.error_response(code, 403)
                    value = json.loads(response.body)
                    if mode == "bad_envelope":
                        value["error"]["extra"] = "private-extra-must-not-escape"
                    return httpx.Response(403, json=value)
                if mode == "csrf":
                    headers["x-csrf-token"] = "wrong"
            response = web.request(req.method, path, content=req.content, headers=headers)
            return httpx.Response(
                response.status_code, content=response.content, headers=response.headers
            )

        monkeypatch.setattr(
            httpx,
            "Client",
            lambda **kwargs: client_class(**kwargs, transport=httpx.MockTransport(transport)),
        )
        if mode == "native":
            target.negative_child(directory, request, phase + "-decision")
            target.negative_child(directory, request, phase + "-collect")
            result = json.loads((directory / (phase + "-collect.safe.json")).read_text())
            assert result["http_status"] == (403 if phase == "revoked" else 410)
            assert result["error_code"] == (
                "ACCESS_DENIED" if phase == "revoked" else "APPROVAL_EXPIRED"
            )
            assert (
                result["execution_count"]
                == result["item_count"]
                == result["decision_receipt_count"]
                == 0
            )
            assert result["original_expiry_preserved"] and result["original_nonce_preserved"]
        else:
            with pytest.raises(BackupFailure):
                target.negative_child(directory, request, phase + "-decision")
            assert not (directory / (phase + "-decision.safe.json")).exists()
    assert len([p for p in sent if p.endswith("/decision")]) == (
        0 if mode in ("wrong_auth", "wrong_clock", "wrong_request") else 1
    )
    evidence = list(directory.glob(phase + "-http-*.safe.json"))
    assert len(evidence) == (
        1 if mode in ("wrong_clock", "wrong_request") else 3 if mode == "wrong_auth" else 5
    )
    for path in evidence:
        raw_safe = path.read_text()
        for private in (
            str(task),
            str(approval),
            str(principal),
            nonce,
            token,
            "private-",
            "synthetic-cookie",
        ):
            assert private not in raw_safe
        row = json.loads(raw_safe)
        assert row["success_asserted"] is False and "stopped_collection" in row["not_run_steps"]
    if mode == "timeout":
        assert (
            json.loads((directory / (phase + "-http-decision.safe.json")).read_text())["transport"]
            == "timeout"
        )
    assert any("FROM business.approvals" in sql for sql in sql_queries)
