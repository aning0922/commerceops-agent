"""Native V4 SQL counterexamples; collected offline, run only in a Root-owned PG window."""

import secrets
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from commerceops.application.replenishment.contracts import WebFailure
from commerceops.application.replenishment.security import digest, password_hash
from commerceops.application.v4_demo import contracts as dto
from commerceops.domain.commerce_values import canonical_bytes
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.v4_demo_seed import grant_v4_runtime, initialize_fixture
from psycopg import sql
from psycopg.types.json import Jsonb

from tests.test_p4_acceptance_pg import database as database
from tests.test_p4_acceptance_pg import initialize_schema
from tests.v4.test_demo_sessions_pg import DemoPG
from tests.v4.test_demo_sessions_pg import demo as demo

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


_MATERIALIZED = (
    "organizations",
    "shops",
    "principals",
    "identities",
    "principal_shop_scopes",
    "principal_role_shop_grants",
    "web_credentials",
    "web_sessions",
    "v4_demo_tenants",
    "v4_demo_shops",
    "v4_demo_personas",
    "v4_demo_sessions",
    "v4_demo_receipts",
    "v4_demo_events",
    "v4_demo_overlays",
)


def materialized_counts(owner: DatabaseSettings) -> dict[str, int]:
    with connect(owner) as db:
        result: dict[str, int] = {}
        for table in _MATERIALIZED:
            row = db.execute(
                sql.SQL("SELECT count(*) AS n FROM {}").format(sql.Identifier("business", table))
            ).fetchone()
            assert row is not None
            result[table] = row["n"]
        return result


def test_seed_native_mid_persona_failure_rolls_back_but_preserves_reserved_key(
    demo: DemoPG,
) -> None:
    before = materialized_counts(demo.owner)
    bootstrap, token = demo.store.bootstrap(None, "seed-fault-author")
    assert token is not None
    key = uuid4()
    command = dto.CreateSessionInput(request_key=key, fixture_version="v4-demo-seed-1")
    with connect(demo.owner) as db:
        db.execute("""CREATE FUNCTION business.v4_author_persona_fault() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,business AS $$
        BEGIN
          IF NEW.persona_id='approver' THEN
            IF (SELECT count(*) FROM business.v4_demo_shops WHERE tenant_id=NEW.tenant_id)<>2
              OR NOT EXISTS(SELECT 1 FROM business.v4_demo_personas
                WHERE tenant_id=NEW.tenant_id AND persona_id='operator')
              OR (SELECT count(*) FROM business.principals
                WHERE organization_id=NEW.organization_id)<>2 THEN
              RAISE EXCEPTION 'V4_AUTHOR_FAULT_WRONG_STAGE' USING ERRCODE='P0001';
            END IF;
            RAISE EXCEPTION 'V4_AUTHOR_PERSONA_FAULT_AFTER_OPERATOR' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$""")
        db.execute(
            "REVOKE ALL ON FUNCTION business.v4_author_persona_fault() FROM PUBLIC,commerceops_app"
        )
        db.execute("""CREATE TRIGGER v4_author_persona_fault BEFORE INSERT
        ON business.v4_demo_personas FOR EACH ROW
        EXECUTE FUNCTION business.v4_author_persona_fault()""")
    try:
        with pytest.raises(psycopg.errors.CheckViolation) as captured:
            demo.store.create(token, bootstrap["data"]["csrf_token"], command, "seed-fault-author")
        assert captured.value.sqlstate == "23514"
        assert captured.value.diag.message_primary == "V4_AUTHOR_PERSONA_FAULT_AFTER_OPERATOR"
        assert materialized_counts(demo.owner) == before
        with connect(demo.app) as db:
            reservation = demo.store.sessions.bootstrap_locked(db, token)
            assert reservation["create_request_key"] == key and reservation["consumed_at"] is None
            assert reservation["expires_at"] > reservation["created_at"]
        recovered = demo.store.operation(token, "session_create", key)
        assert recovered["data"] == dict(
            operation="session_create",
            request_key=str(key),
            status="UNKNOWN",
            recovery="WAIT_READ_ONLY",
        )
    finally:
        with connect(demo.owner) as db:
            db.execute("DROP TRIGGER v4_author_persona_fault ON business.v4_demo_personas")
            db.execute("DROP FUNCTION business.v4_author_persona_fault()")
    # Removing the fixture fault grants no automatic POST/replacement-key authority.
    assert demo.store.operation(token, "session_create", key)["data"]["status"] == "UNKNOWN"
    with pytest.raises(WebFailure, match="RESOURCE_NOT_FOUND"):
        demo.store.create(
            token,
            bootstrap["data"]["csrf_token"],
            dto.CreateSessionInput(request_key=uuid4(), fixture_version="v4-demo-seed-1"),
            "seed-fault-author",
        )
    assert materialized_counts(demo.owner) == before


def test_runtime_acl_rejects_mapping_credentials_history_and_public_function_access(
    sql_demo: tuple[DatabaseSettings, DatabaseSettings],
) -> None:
    owner, app = sql_demo
    with connect(owner) as db:
        owner_role = db.execute("SELECT current_user AS name").fetchone()
        assert owner_role is not None and owner_role["name"] != "commerceops_app"
        owners = db.execute("""SELECT c.relname,pg_get_userbyid(c.relowner) AS owner
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='business' AND c.relkind='r' AND c.relname LIKE 'v4_demo_%'""").fetchall()
        assert len(owners) == 10
        assert {row["owner"] for row in owners} == {owner_role["name"]}
        public_execute = db.execute("""SELECT count(*) AS n FROM pg_proc p
        JOIN pg_namespace n ON n.oid=p.pronamespace
        CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
        WHERE n.nspname='business' AND p.proname IN
        ('v4_demo_request_valid','v4_demo_guard','v4_demo_commit_guard','v4_demo_provision')
        AND a.grantee=0 AND a.privilege_type='EXECUTE'""").fetchone()
        assert public_execute == {"n": 0}
    statements = (
        "INSERT INTO business.v4_demo_fixture_versions DEFAULT VALUES",
        "INSERT INTO business.v4_demo_tenants DEFAULT VALUES",
        "INSERT INTO business.v4_demo_shops DEFAULT VALUES",
        "INSERT INTO business.v4_demo_personas DEFAULT VALUES",
        "INSERT INTO business.v4_demo_sessions DEFAULT VALUES",
        "INSERT INTO business.web_credentials DEFAULT VALUES",
        "INSERT INTO business.principal_role_shop_grants DEFAULT VALUES",
        "UPDATE business.v4_demo_fixture_versions SET version=version WHERE false",
        "UPDATE business.v4_demo_shops SET template_key=template_key WHERE false",
        "UPDATE business.v4_demo_personas SET persona_id=persona_id WHERE false",
        "UPDATE business.v4_demo_bootstraps SET token_hash=token_hash WHERE false",
        "UPDATE business.v4_demo_sessions SET token_hash=token_hash WHERE false",
        "UPDATE business.v4_demo_sessions SET expires_at=expires_at WHERE false",
        "DELETE FROM business.v4_demo_receipts WHERE false",
        "DELETE FROM business.v4_demo_events WHERE false",
        "TRUNCATE business.v4_demo_overlays",
    )
    with connect(app) as db:
        role = db.execute("""SELECT current_user AS name,r.rolsuper,r.rolcreatedb,r.rolcreaterole,
        r.rolreplication,r.rolbypassrls FROM pg_roles r WHERE r.rolname=current_user""").fetchone()
        assert role == dict(
            name="commerceops_app",
            rolsuper=False,
            rolcreatedb=False,
            rolcreaterole=False,
            rolreplication=False,
            rolbypassrls=False,
        )
        for statement in statements:
            with pytest.raises(psycopg.errors.InsufficientPrivilege) as captured, db.transaction():
                db.execute(statement)
            assert captured.value.sqlstate == "42501"
