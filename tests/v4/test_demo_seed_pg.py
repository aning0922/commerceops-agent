"""Native V4 SQL counterexamples; collected offline, run only in a Root-owned PG window."""

import secrets
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from commerceops.application.replenishment.security import digest, password_hash
from commerceops.domain.commerce_values import canonical_bytes
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.v4_demo_seed import grant_v4_runtime, initialize_fixture
from psycopg.types.json import Jsonb

from tests.test_p4_acceptance_pg import database as database
from tests.test_p4_acceptance_pg import initialize_schema

pytestmark = pytest.mark.integration
DB = psycopg.Connection[dict[str, Any]]


@dataclass(frozen=True)
class Fact:
    tenant: UUID
    session: UUID
    creation_key: UUID


@pytest.fixture(scope="module")
def credential() -> str:
    return password_hash(secrets.token_urlsafe(32))


@pytest.fixture
def sql_demo(
    database: tuple[DatabaseSettings, DatabaseSettings],
) -> tuple[DatabaseSettings, DatabaseSettings]:
    owner, app = database
    initialize_schema(owner, "head")
    with connect(owner) as db:
        initialize_fixture(db)
        grant_v4_runtime(db)
    return owner, app


def create(app: DatabaseSettings, credential: str) -> Fact:
    bid, sid, wid, key = uuid4(), uuid4(), uuid4(), uuid4()
    text = canonical_bytes(
        dict(
            method="POST",
            path="/api/v4/demo/sessions",
            body=dict(request_key=str(key), fixture_version="v4-demo-seed-1"),
        )
    ).decode()
    with connect(app) as db:
        db.execute(
            """INSERT INTO business.v4_demo_bootstraps
        (id,token_hash,csrf_digest,key_version,created_at,expires_at,create_request_key)
        SELECT %s,%s,%s,'p3-key-v1',stamp,stamp+interval '300 seconds',%s
        FROM (SELECT clock_timestamp() AS stamp) times""",
            (bid, digest(secrets.token_urlsafe(32)), digest(secrets.token_urlsafe(32)), key),
        )
        # Same timestamp must satisfy the exact lifetime CHECK.
        db.execute(
            "SELECT business.v4_demo_provision(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                bid,
                key,
                text,
                digest(text),
                digest(secrets.token_urlsafe(32)),
                sid,
                wid,
                digest(secrets.token_urlsafe(32)),
                uuid4(),
                digest(secrets.token_urlsafe(32)),
                digest(secrets.token_urlsafe(32)),
                "p3-key-v1",
                credential,
            ),
        )
        row = db.execute(
            "SELECT tenant_id FROM business.v4_demo_sessions WHERE id=%s", (sid,)
        ).fetchone()
        assert row is not None
        return Fact(row["tenant_id"], sid, key)


def receipt(
    db: DB,
    fact: Fact,
    *,
    operation: str = "reset",
    rid: UUID | None = None,
    before: tuple[int, int] = (0, 0),
    after: tuple[int, int] = (1, 1),
    payload: dict[str, Any] | None = None,
) -> UUID:
    key, identifier = uuid4(), rid or uuid4()
    request = payload or dict(
        method="POST",
        path="/api/v4/demo/" + operation,
        body=dict(
            request_key=str(key),
            fixture_version="v4-demo-seed-1",
            expected_epoch=before[0],
            expected_generation=before[1],
        ),
    )
    if payload is None and operation == "persona":
        request["body"].pop("fixture_version")
        request["body"]["persona_id"] = "operator"
    if payload is not None:
        key = UUID(request["body"]["request_key"])
    text = canonical_bytes(request).decode()
    db.execute(
        """INSERT INTO business.v4_demo_receipts
    (id,owner_session_id,tenant_id,operation,request_key,canonical_request,payload_digest,
    epoch_before,generation_before,reset_epoch,auth_generation,retain_until)
    SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,retain_until
    FROM business.v4_demo_tenants WHERE id=%s""",
        (
            identifier,
            fact.session,
            fact.tenant,
            operation,
            key,
            text,
            digest(text),
            *before,
            *after,
            fact.tenant,
        ),
    )
    return identifier


def event(
    db: DB,
    fact: Fact,
    rid: UUID,
    kind: str,
    epoch: int,
    generation: int,
    *,
    owner: UUID | None = None,
    tenant: UUID | None = None,
) -> None:
    db.execute(
        """INSERT INTO business.v4_demo_events
    (id,tenant_id,owner_session_id,receipt_id,event_kind,reset_epoch,auth_generation)
    VALUES(%s,%s,%s,%s,%s,%s,%s)""",
        (uuid4(), tenant or fact.tenant, owner or fact.session, rid, kind, epoch, generation),
    )


def transition(db: DB, fact: Fact, *, wrong_before: bool = False) -> UUID:
    old = db.execute(
        "SELECT * FROM business.v4_demo_sessions WHERE id=%s", (fact.session,)
    ).fetchone()
    assert old is not None
    rid, wid = uuid4(), uuid4()
    db.execute(
        "UPDATE business.web_sessions SET revoked_at=clock_timestamp() WHERE id=%s",
        (old["bound_web_session_id"],),
    )
    db.execute(
        """INSERT INTO business.web_sessions
    (id,token_hash,kind,organization_id,principal_id,identity_id,auth_version,csrf_digest,
    key_version,created_at,last_seen_at,absolute_expires_at,idle_expires_at)
    SELECT %s,%s,kind,organization_id,principal_id,identity_id,auth_version,%s,key_version,
    clock_timestamp(),clock_timestamp(),absolute_expires_at,idle_expires_at
    FROM business.web_sessions WHERE id=%s""",
        (
            wid,
            digest(secrets.token_urlsafe(32)),
            digest(secrets.token_urlsafe(32)),
            old["bound_web_session_id"],
        ),
    )
    after = old["auth_generation"] + 1
    db.execute(
        """UPDATE business.v4_demo_sessions SET bound_web_session_id=%s,
    auth_generation=%s,csrf_nonce=%s,csrf_digest=%s,last_receipt_id=%s WHERE id=%s""",
        (wid, after, uuid4(), digest(secrets.token_urlsafe(32)), rid, fact.session),
    )
    receipt(
        db,
        fact,
        operation="persona",
        rid=rid,
        before=(old["reset_epoch"], old["auth_generation"] + (1 if wrong_before else 0)),
        after=(old["reset_epoch"], after),
    )
    event(db, fact, rid, "demo.persona_changed", old["reset_epoch"], after)
    return rid


def test_correct_creation_and_single_transition_are_linked(
    sql_demo: tuple[DatabaseSettings, DatabaseSettings], credential: str
) -> None:
    _, app = sql_demo
    fact = create(app, credential)
    with connect(app) as db:
        counts = db.execute(
            "SELECT count(*) AS n FROM business.v4_demo_events WHERE tenant_id=%s", (fact.tenant,)
        ).fetchone()
        assert counts == {"n": 2}
        rid = transition(db, fact)
        db.execute("SET CONSTRAINTS ALL IMMEDIATE")
    with connect(app) as db:
        row = db.execute(
            "SELECT last_receipt_id,auth_generation,reset_epoch "
            "FROM business.v4_demo_sessions WHERE id=%s",
            (fact.session,),
        ).fetchone()
        assert row == dict(last_receipt_id=rid, auth_generation=1, reset_epoch=0)


def test_receipt_without_effect_and_effect_without_receipt_are_rejected(
    sql_demo: tuple[DatabaseSettings, DatabaseSettings], credential: str
) -> None:
    _, app = sql_demo
    fact = create(app, credential)
    with connect(app) as db:
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            rid = receipt(db, fact)
            event(db, fact, rid, "demo.reset_committed", 1, 1)
            db.execute("SET CONSTRAINTS ALL IMMEDIATE")
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(
                "UPDATE business.v4_demo_tenants SET reset_epoch=1 WHERE id=%s", (fact.tenant,)
            )
            db.execute("SET CONSTRAINTS ALL IMMEDIATE")
        current = db.execute(
            "SELECT reset_epoch,auth_generation FROM business.v4_demo_sessions WHERE id=%s",
            (fact.session,),
        ).fetchone()
        assert current == dict(reset_epoch=0, auth_generation=0)


def test_wrong_before_old_receipt_and_two_controls_in_one_transaction_are_rejected(
    sql_demo: tuple[DatabaseSettings, DatabaseSettings], credential: str
) -> None:
    _, app = sql_demo
    fact = create(app, credential)
    with connect(app) as db:
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            transition(db, fact, wrong_before=True)
            db.execute("SET CONSTRAINTS ALL IMMEDIATE")
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(
                "UPDATE business.v4_demo_sessions SET last_receipt_id=last_receipt_id WHERE id=%s",
                (fact.session,),
            )
            db.execute("SET CONSTRAINTS ALL IMMEDIATE")
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            transition(db, fact)
            transition(db, fact)
            db.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_event_cross_tenant_kind_and_generation_are_rejected(
    sql_demo: tuple[DatabaseSettings, DatabaseSettings], credential: str
) -> None:
    _, app = sql_demo
    a, b = create(app, credential), create(app, credential)
    with connect(app) as db:
        row = db.execute(
            "SELECT last_receipt_id FROM business.v4_demo_sessions WHERE id=%s", (a.session,)
        ).fetchone()
        assert row is not None
        rid = row["last_receipt_id"]
        transition(db, a)
        db.execute("SET CONSTRAINTS ALL IMMEDIATE")
    # The creation receipt is now historical, so an event-only append cannot rely on
    # re-running its INSERT guard. The event's own guards must reject it.
    with connect(app) as db:
        for owner, tenant, kind, epoch, generation in (
            (b.session, a.tenant, "demo.persona_changed", 0, 0),
            (a.session, b.tenant, "demo.persona_changed", 0, 0),
            (a.session, a.tenant, "demo.persona_changed", 0, 0),
            (a.session, a.tenant, "demo.reset_committed", 1, 1),
        ):
            with (
                pytest.raises((psycopg.errors.CheckViolation, psycopg.errors.ForeignKeyViolation)),
                db.transaction(),
            ):
                event(db, a, rid, kind, epoch, generation, owner=owner, tenant=tenant)
                db.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_sql_request_validator_rejects_missing_null_extra_wrong_types_and_cas(
    sql_demo: tuple[DatabaseSettings, DatabaseSettings],
) -> None:
    _, app = sql_demo
    key = uuid4()
    base: dict[str, Any] = dict(
        method="POST",
        path="/api/v4/demo/reset",
        body=dict(
            request_key=str(key),
            fixture_version="v4-demo-seed-1",
            expected_epoch=0,
            expected_generation=0,
        ),
    )
    cases: list[dict[str, Any]] = []
    value: Any
    for name in ("method", "path", "body"):
        for value in (None, [], 1, True):
            cases.append({**base, name: value})
        cases.append({k: v for k, v in base.items() if k != name})
    cases.append({**base, "extra": True})
    for name in base["body"]:
        cases.append({**base, "body": {k: v for k, v in base["body"].items() if k != name}})
        cases.append({**base, "body": {**base["body"], name: None}})
    for value in (True, "0", -1, 1, 0.1):
        cases.append({**base, "body": {**base["body"], "expected_epoch": value}})
    cases.append({**base, "body": {**base["body"], "role": "admin"}})
    with connect(app) as db:

        def valid(value: dict[str, Any]) -> bool:
            row = db.execute(
                "SELECT business.v4_demo_request_valid("
                "%s,'reset',%s,0,0,'v4-demo-seed-1','operator') AS valid",
                (Jsonb(value), key),
            ).fetchone()
            assert row is not None
            return bool(row["valid"])

        assert valid(base)
        assert all(not valid(value) for value in cases)
