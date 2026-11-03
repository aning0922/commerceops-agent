"""New-owned PG identity/control author cases. No implicit skip or service startup."""

import json
import secrets
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from commerceops.application.replenishment.contracts import WebFailure
from commerceops.application.v4_demo import contracts as dto
from commerceops.entrypoints.api import create_app
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.replenishment_repository import ReplenishmentStore
from commerceops.infrastructure.v4_demo_seed import grant_v4_runtime, initialize_fixture
from commerceops.infrastructure.v4_demo_sessions import DemoConfig
from commerceops.infrastructure.v4_demo_store import DemoStore
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.web_sessions import actor_guard
from fastapi.testclient import TestClient
from psycopg import sql

from tests.test_p4_acceptance_pg import initialize_schema

pytestmark = pytest.mark.integration
ORIGIN = "http://127.0.0.1:13440"
API = "http://127.0.0.1:18440"


@dataclass(frozen=True)
class DemoPG:
    owner: DatabaseSettings
    app: DatabaseSettings
    config: DemoConfig
    store: DemoStore


@pytest.fixture
def demo() -> Iterator[DemoPG]:
    base = DatabaseSettings()
    assert base.runtime_password_file is not None
    name = "v4_demo_" + uuid4().hex
    owner = base.model_copy(update={"name": name})
    app = owner.model_copy(
        update=dict(
            user="commerceops_app",
            password_file=base.runtime_password_file,
            runtime_password_file=None,
        )
    )
    with psycopg.connect(**base.kwargs(), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            initialize_schema(owner, "head")
            with connect(owner) as db:
                initialize_fixture(db)
                grant_v4_runtime(db)
            web = WebConfig(
                app,
                secrets.token_bytes(32),
                secrets.token_bytes(32),
                (ORIGIN,),
                transport_mode="local_http",
            )
            config = DemoConfig(web, API, enabled=True)
            yield DemoPG(owner, app, config, DemoStore(config))
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def enter(demo: DemoPG) -> tuple[dict[str, Any], str]:
    bootstrap, token = demo.store.bootstrap(None, "v4-author")
    assert token is not None
    response, active = demo.store.create(
        token,
        bootstrap["data"]["csrf_token"],
        dto.CreateSessionInput(request_key=uuid4(), fixture_version="v4-demo-seed-1"),
        "v4-author",
    )
    return response, active


def test_real_current_scope_summary_and_v1_renamed_cookie_refusal(demo: DemoPG) -> None:
    created, token = enter(demo)
    current = demo.store.sessions.current(token)
    value = dto.SessionData.model_validate_json(json.dumps(current["data"]))
    assert len(value.shops) == 2 and value.persona_id == "operator"
    for shop in value.shops:
        result = demo.store.summary(token, shop.shop_id, 0, 0)
        assert result["data"]["counts"] == dict(products=8, skus=10, orders=12, order_lines=18)
        assert result["context"]["shop_id"] == str(shop.shop_id)
    app = create_app(
        web_config=demo.config.web,
        replenishment_store=ReplenishmentStore(
            demo.config.web, Path("tests/fixtures/commerce/inventory-v1")
        ),
        v4_demo_config=demo.config,
    )
    with TestClient(app, base_url=API) as client:
        client.cookies.set("commerceops_session", token)
        response = client.get("/api/v1/auth/session", headers={"Origin": ORIGIN})
        assert response.status_code == 401
        client.cookies.set("commerceops_v4_demo", token)
        response = client.get("/api/v4/demo/session", headers={"Origin": ORIGIN})
        assert response.status_code == 200
        dto.SessionEnvelope.model_validate_json(response.content)
    with connect(demo.app) as db:
        assert db.execute("SELECT count(*) AS n FROM business.business_tasks").fetchone() == {
            "n": 0
        }
        assert db.execute("SELECT count(*) AS n FROM business.jobs").fetchone() == {"n": 0}
    assert created["data"]["receipt"]["operation"] == "session_create"


def test_persona_reset_revoke_old_actor_and_keep_current_persona_deadline(demo: DemoPG) -> None:
    _, token = enter(demo)
    before = demo.store.sessions.current(token)
    with connect(demo.app) as db:
        old = demo.store.sessions.resolve_locked(db, token).actor
    switch = dto.PersonaInput(
        request_key=uuid4(), expected_epoch=0, expected_generation=0, persona_id="restricted_admin"
    )
    demo.store.control(token, before["data"]["csrf_token"], "persona", switch)
    admin = demo.store.sessions.current(token)
    assert admin["data"]["persona_id"] == "restricted_admin" and admin["data"]["shops"] == []
    assert admin["data"]["expires_at"] == before["data"]["expires_at"]
    with connect(demo.app) as db, pytest.raises(WebFailure, match="SESSION_INVALID"):
        actor_guard(db, old)
    reset = dto.ResetInput(
        request_key=uuid4(),
        expected_epoch=0,
        expected_generation=1,
        fixture_version="v4-demo-seed-1",
    )
    demo.store.control(token, admin["data"]["csrf_token"], "reset", reset)
    after = demo.store.sessions.current(token)
    assert after["context"]["reset_epoch"] == 1 and after["context"]["auth_generation"] == 2
    assert after["data"]["persona_id"] == "restricted_admin" and after["data"]["shops"] == []
    assert after["data"]["expires_at"] == before["data"]["expires_at"]
    with pytest.raises(WebFailure, match="CSRF_INVALID"):
        demo.store.control(token, admin["data"]["csrf_token"], "reset", reset)
    duplicate = demo.store.control(token, after["data"]["csrf_token"], "reset", reset)
    assert duplicate["data"]["receipt"]["reset_epoch"] == 1
    assert demo.store.sessions.current(token)["context"]["reset_epoch"] == 1


def test_unbound_reuse_bound_429_restart_and_original_unknown_recovery(
    demo: DemoPG, monkeypatch: pytest.MonkeyPatch
) -> None:
    bootstrap, owner = demo.store.bootstrap(None, "v4-author")
    assert owner is not None
    reused, issued = demo.store.bootstrap(owner, "v4-author")
    assert issued is None and reused["data"] == bootstrap["data"]
    key = uuid4()
    original_rate = demo.store.rate

    def limited(peer: str, operation: str) -> None:
        if operation == "session_create":
            raise WebFailure("RATE_LIMITED", 429)
        original_rate(peer, operation)

    monkeypatch.setattr(demo.store, "rate", limited)
    with pytest.raises(WebFailure, match="RATE_LIMITED"):
        demo.store.create(
            owner,
            bootstrap["data"]["csrf_token"],
            dto.CreateSessionInput(request_key=key, fixture_version="v4-demo-seed-1"),
            "v4-author",
        )
    monkeypatch.setattr(demo.store, "rate", original_rate)
    fresh, new_owner = demo.store.bootstrap(owner, "v4-author")
    assert new_owner is not None
    recovered = demo.store.operation(owner, "session_create", key)
    assert recovered["data"]["status"] == "UNKNOWN"
    with pytest.raises(WebFailure, match="RESOURCE_NOT_FOUND"):
        demo.store.operation(owner, "session_create", uuid4())
    _, active = demo.store.create(
        new_owner,
        fresh["data"]["csrf_token"],
        dto.CreateSessionInput(request_key=uuid4(), fixture_version="v4-demo-seed-1"),
        "v4-author",
    )
    assert demo.store.sessions.current(active)["context"]["reset_epoch"] == 0
    with pytest.raises(WebFailure, match="GENERATION_CHANGED"):
        demo.store.bootstrap(active, "v4-author")


def test_lost_create_cookie_only_minimal_bootstrap_recovery_and_no_active_post(
    demo: DemoPG,
) -> None:
    bootstrap, owner = demo.store.bootstrap(None, "v4-author")
    assert owner is not None
    key = uuid4()
    command = dto.CreateSessionInput(request_key=key, fixture_version="v4-demo-seed-1")
    _, active = demo.store.create(owner, bootstrap["data"]["csrf_token"], command, "v4-author")
    minimal = demo.store.operation(owner, "session_create", key)["data"]
    assert set(minimal) == {"operation", "request_key", "status", "recovery"}
    assert minimal["status"] == "COMMITTED" and minimal["recovery"] == "OWNER_RECOVERY_REQUIRED"
    with pytest.raises(WebFailure, match="OWNER_RECOVERY_REQUIRED"):
        demo.store.create(owner, bootstrap["data"]["csrf_token"], command, "v4-author")
    with pytest.raises(WebFailure, match="SESSION_INVALID"):
        demo.store.create(active, bootstrap["data"]["csrf_token"], command, "v4-author")
    assert demo.store.sessions.current(active)["data"]["creation_request_key"] == str(key)


@pytest.mark.parametrize(
    "mutation",
    [
        "credential_disabled",
        "identity_provider",
        "principal_disabled",
        "bound_csrf",
        "bound_key",
        "bound_auth_version",
        "bound_tuple",
        "bound_revoked",
        "bound_expired",
    ],
)
def test_complete_credential_and_bound_checks(demo: DemoPG, mutation: str) -> None:
    _, token = enter(demo)
    with connect(demo.app) as db:
        subject = demo.store.sessions.resolve_locked(db, token)
    with connect(demo.owner) as db:
        if mutation == "credential_disabled":
            db.execute(
                "UPDATE business.web_credentials SET enabled=false WHERE identity_id=%s",
                (subject.actor.identity_id,),
            )
        elif mutation == "identity_provider":
            db.execute(
                "UPDATE business.identities SET provider='synthetic-invalid' WHERE id=%s",
                (subject.actor.identity_id,),
            )
        elif mutation == "principal_disabled":
            db.execute(
                "UPDATE business.principals SET enabled=false,auth_version=auth_version+1 "
                "WHERE id=%s",
                (subject.actor.principal_id,),
            )
        elif mutation == "bound_csrf":
            db.execute(
                "UPDATE business.web_sessions SET csrf_digest=repeat('0',64) WHERE id=%s",
                (subject.actor.session_id,),
            )
        elif mutation == "bound_key":
            db.execute(
                "UPDATE business.web_sessions SET key_version='wrong-key' WHERE id=%s",
                (subject.actor.session_id,),
            )
        elif mutation == "bound_auth_version":
            db.execute(
                "UPDATE business.web_sessions SET auth_version=auth_version+1 WHERE id=%s",
                (subject.actor.session_id,),
            )
        elif mutation == "bound_tuple":
            db.execute(
                """UPDATE business.web_sessions w SET principal_id=m.principal_id,
                identity_id=m.identity_id,auth_version=p.auth_version
                FROM business.v4_demo_personas m JOIN business.principals p ON p.id=m.principal_id
                WHERE m.tenant_id=%s AND m.persona_id='approver' AND w.id=%s""",
                (subject.tenant["id"], subject.actor.session_id),
            )
        elif mutation == "bound_revoked":
            db.execute(
                "UPDATE business.web_sessions SET revoked_at=clock_timestamp() WHERE id=%s",
                (subject.actor.session_id,),
            )
        else:
            db.execute(
                "UPDATE business.web_sessions SET "
                "idle_expires_at=created_at+interval '1 microsecond' "
                "WHERE id=%s",
                (subject.actor.session_id,),
            )
    with pytest.raises(WebFailure, match="SESSION_INVALID"):
        demo.store.sessions.current(token)


def test_cap_three_rejects_fourth_and_fifth_without_evicting_other_tenants(demo: DemoPG) -> None:
    visitors = [enter(demo) for _ in range(3)]
    for _ in range(2):  # Fourth and fifth visitors both leave the first three intact.
        bootstrap, owner = demo.store.bootstrap(None, "v4-author")
        assert owner is not None
        with pytest.raises(WebFailure, match="CAPACITY_LIMIT"):
            demo.store.create(
                owner,
                bootstrap["data"]["csrf_token"],
                dto.CreateSessionInput(request_key=uuid4(), fixture_version="v4-demo-seed-1"),
                "v4-author",
            )
    contexts = [demo.store.sessions.current(token)["context"] for _, token in visitors]
    assert len({context["tenant_id"] for context in contexts}) == 3
    first_data, first_token = visitors[0]
    other_shop = UUID(visitors[1][0]["data"]["session"]["shops"][0]["shop_id"])
    with pytest.raises(WebFailure, match="RESOURCE_NOT_FOUND"):
        demo.store.summary(first_token, other_shop, 0, 0)
    with pytest.raises(WebFailure, match="RESOURCE_NOT_FOUND"):
        demo.store.operation(
            first_token, "session_create", UUID(visitors[1][0]["data"]["receipt"]["request_key"])
        )
    assert first_data["context"]["tenant_id"] == contexts[0]["tenant_id"]


def test_logout_receipt_commits_and_then_has_no_recovery_privilege(demo: DemoPG) -> None:
    _, token = enter(demo)
    before = demo.store.sessions.current(token)
    command = dto.LogoutInput(request_key=uuid4(), expected_epoch=0, expected_generation=0)
    result = demo.store.control(token, before["data"]["csrf_token"], "logout", command)
    assert result["data"]["next_step"] == "LOGGED_OUT"
    with pytest.raises(WebFailure, match="SESSION_INVALID"):
        demo.store.sessions.current(token)
    with pytest.raises(WebFailure, match="SESSION_INVALID"):
        demo.store.operation(token, "logout", command.request_key)
    fresh, issued = demo.store.bootstrap(token, "v4-author")
    assert issued is not None and fresh["data"]["state"] == "anonymous_bootstrap"


def test_reset_clears_only_current_overlay_and_preserves_other_tenant(demo: DemoPG) -> None:
    first, first_token = enter(demo)
    second, second_token = enter(demo)
    for created in (first, second):
        with connect(demo.owner) as db:
            db.execute(
                """INSERT INTO business.v4_demo_overlays
            (tenant_id,shop_id,reset_epoch,object_kind,object_key,version,payload,
             canonical_payload,payload_digest)
            VALUES(%s,%s,0,'fixture_note','author-note',1,'{}'::jsonb,'{}',
              encode(sha256(convert_to('{}','UTF8')),'hex'))""",
                (
                    UUID(created["context"]["tenant_id"]),
                    UUID(created["data"]["session"]["shops"][0]["shop_id"]),
                ),
            )
    before_second = demo.store.sessions.current(second_token)
    current = demo.store.sessions.current(first_token)
    command = dto.ResetInput(
        request_key=uuid4(),
        expected_epoch=0,
        expected_generation=0,
        fixture_version="v4-demo-seed-1",
    )
    demo.store.control(first_token, current["data"]["csrf_token"], "reset", command)
    with connect(demo.app) as db:
        first_count = db.execute(
            "SELECT count(*) AS n FROM business.v4_demo_overlays WHERE tenant_id=%s",
            (UUID(first["context"]["tenant_id"]),),
        ).fetchone()
        second_count = db.execute(
            "SELECT count(*) AS n FROM business.v4_demo_overlays WHERE tenant_id=%s",
            (UUID(second["context"]["tenant_id"]),),
        ).fetchone()
        assert first_count == {"n": 0} and second_count == {"n": 1}
    after_second = demo.store.sessions.current(second_token)
    assert before_second["data"] == after_second["data"]
    assert before_second["context"]["reset_epoch"] == after_second["context"]["reset_epoch"] == 0
    assert (
        before_second["context"]["auth_generation"]
        == after_second["context"]["auth_generation"]
        == 0
    )


def test_reset_same_key_payload_once_changed_payload_conflicts_and_other_tenant_stays(
    demo: DemoPG,
) -> None:
    _, first_token = enter(demo)
    _, second_token = enter(demo)
    first = demo.store.sessions.current(first_token)
    second = demo.store.sessions.current(second_token)
    command = dto.ResetInput(
        request_key=uuid4(),
        expected_epoch=0,
        expected_generation=0,
        fixture_version="v4-demo-seed-1",
    )
    committed = demo.store.control(first_token, first["data"]["csrf_token"], "reset", command)
    current = demo.store.sessions.current(first_token)
    repeated = demo.store.control(first_token, current["data"]["csrf_token"], "reset", command)
    assert repeated["data"]["receipt"] == committed["data"]["receipt"]
    changed = dto.ResetInput(
        request_key=command.request_key,
        expected_epoch=1,
        expected_generation=1,
        fixture_version="v4-demo-seed-1",
    )
    with pytest.raises(WebFailure, match="IDEMPOTENCY_CONFLICT"):
        demo.store.control(first_token, current["data"]["csrf_token"], "reset", changed)
    after = demo.store.sessions.current(first_token)
    assert after["context"]["reset_epoch"] == 1 and after["context"]["auth_generation"] == 1
    other = demo.store.sessions.current(second_token)
    assert other["data"] == second["data"]
    for name in ("tenant_id", "organization_id", "principal_id", "reset_epoch", "auth_generation"):
        assert other["context"][name] == second["context"][name]
    with connect(demo.app) as db:
        receipts = db.execute(
            "SELECT count(*) AS n FROM business.v4_demo_receipts "
            "WHERE tenant_id=%s AND operation='reset'",
            (UUID(first["context"]["tenant_id"]),),
        ).fetchone()
        events = db.execute(
            "SELECT count(*) AS n FROM business.v4_demo_events "
            "WHERE tenant_id=%s AND event_kind='demo.reset_committed'",
            (UUID(first["context"]["tenant_id"]),),
        ).fetchone()
        assert receipts == {"n": 1} and events == {"n": 1}


def test_revoked_target_persona_is_denied_while_current_operator_remains_valid(
    demo: DemoPG,
) -> None:
    _, token = enter(demo)
    before = demo.store.sessions.current(token)
    tenant_id = UUID(before["context"]["tenant_id"])
    with connect(demo.owner) as db:
        changed = db.execute(
            """UPDATE business.web_credentials c SET enabled=false
            FROM business.v4_demo_personas m
            WHERE m.tenant_id=%s AND m.persona_id='approver' AND c.identity_id=m.identity_id
            RETURNING c.principal_id""",
            (tenant_id,),
        ).fetchall()
        assert len(changed) == 1
        assert changed[0]["principal_id"] != UUID(before["context"]["principal_id"])
    still_current = demo.store.sessions.current(token)
    assert still_current["data"] == before["data"]
    command = dto.PersonaInput(
        request_key=uuid4(), expected_epoch=0, expected_generation=0, persona_id="approver"
    )
    with pytest.raises(WebFailure, match="SESSION_INVALID"):
        demo.store.control(token, before["data"]["csrf_token"], "persona", command)
    after = demo.store.sessions.current(token)
    assert after["data"] == before["data"]
    assert after["context"]["auth_generation"] == 0
    assert after["context"]["reset_epoch"] == 0
    with connect(demo.app) as db:
        receipts = db.execute(
            "SELECT count(*) AS n FROM business.v4_demo_receipts "
            "WHERE tenant_id=%s AND operation='persona'",
            (tenant_id,),
        ).fetchone()
        assert receipts == {"n": 0}
