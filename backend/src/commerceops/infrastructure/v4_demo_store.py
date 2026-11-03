"""Finite synchronous V4 demo controls; no jobs, Graph, external source or blind retries."""

import hashlib
import hmac
import math
import secrets
import threading
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from commerceops.application.replenishment.contracts import WebFailure
from commerceops.application.replenishment.security import csrf_token, digest, password_hash
from commerceops.application.v4_demo import contracts as dto
from commerceops.application.v4_demo.seed_contract import FixtureContent
from commerceops.domain.commerce_values import canonical_bytes
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.v4_demo_sessions import (
    DB,
    DemoConfig,
    DemoIdentity,
    DemoLimit,
    DemoSessions,
    bounded,
    demo_csrf,
)
from commerceops.infrastructure.web_sessions import json_native, now, role_scope

_HASH_SLOT = threading.Semaphore(1)


def _canonical(operation: dto.Operation, command: dto.Contract) -> str:
    suffix = "sessions" if operation == "session_create" else operation
    return canonical_bytes(
        dict(method="POST", path="/api/v4/demo/" + suffix, body=command.model_dump(mode="json"))
    ).decode()


def receipt_wire(row: dict[str, Any]) -> dict[str, Any]:
    return {
        name: json_native(row[name])
        for name in (
            "receipt_id",
            "operation",
            "request_key",
            "payload_digest",
            "committed_at",
            "reset_epoch",
            "auth_generation",
        )
    } | {"status": "COMMITTED"}


def _receipt_row(db: DB, owner: UUID, operation: str, key: UUID) -> dict[str, Any] | None:
    return db.execute(
        """SELECT *,id AS receipt_id FROM business.v4_demo_receipts
    WHERE owner_session_id=%s AND operation=%s AND request_key=%s""",
        (owner, operation, key),
    ).fetchone()


class DemoStore:
    def __init__(self, config: DemoConfig):
        self.config = config
        self.sessions = DemoSessions(config)

    def rate(self, peer: str, operation: str) -> None:
        peer_hash = hashlib.sha256(
            hmac.digest(self.config.web.csrf_secret, peer.encode(), "sha256")
        ).hexdigest()
        with connect(self.config.web.database) as db:
            bounded(db)
            db.execute("SELECT pg_advisory_xact_lock(1446261841,hashtext(%s))", (peer_hash,))
            stamp = now(db)
            count = db.execute(
                """SELECT count(*) AS n FROM business.v4_demo_rate_attempts
            WHERE peer_digest=%s AND operation=%s AND occurred_at>%s""",
                (peer_hash, operation, stamp - timedelta(seconds=300)),
            ).fetchone()
            if count and count["n"] >= (20 if operation == "bootstrap" else 10):
                raise WebFailure("RATE_LIMITED", 429)
            db.execute(
                "INSERT INTO business.v4_demo_rate_attempts(id,peer_digest,operation) "
                "VALUES(%s,%s,%s)",
                (uuid4(), peer_hash, operation),
            )

    def bootstrap(self, token: str | None, peer: str) -> tuple[dict[str, Any], str | None]:
        with connect(self.config.web.database) as db:
            bounded(db)
            if token and token.startswith("v4d_"):
                try:
                    with db.transaction():
                        self.sessions.resolve_locked(db, token)
                except WebFailure as error:
                    if error.status != 401:
                        raise
                else:
                    raise WebFailure("GENERATION_CHANGED", 409)
            if token and token.startswith("v4b_"):
                try:
                    with db.transaction():
                        old = self.sessions.bootstrap_locked(db, token)
                        if old["create_request_key"] is None:
                            return self._bootstrap_response(db, old), None
                except WebFailure as error:
                    if error.status != 401:
                        raise
        self.rate(peer, "bootstrap")
        issued, bid = "v4b_" + secrets.token_urlsafe(32), uuid4()
        with connect(self.config.web.database) as db:
            bounded(db)
            db.execute("SELECT pg_advisory_xact_lock(1446261840,2)")
            stamp = now(db)
            count = db.execute(
                "SELECT count(*) AS n FROM business.v4_demo_bootstraps WHERE expires_at>%s",
                (stamp,),
            ).fetchone()
            if count and count["n"] >= 128:
                raise WebFailure("RATE_LIMITED", 429)
            row = db.execute(
                """INSERT INTO business.v4_demo_bootstraps
            (id,token_hash,csrf_digest,key_version,created_at,expires_at)
            VALUES(%s,%s,%s,%s,%s,%s) RETURNING *""",
                (
                    bid,
                    digest(issued),
                    digest(self.sessions.bootstrap_csrf(bid)),
                    self.config.web.key_version,
                    stamp,
                    stamp + timedelta(seconds=300),
                ),
            ).fetchone()
            if row is None:
                raise WebFailure("SERVICE_UNAVAILABLE", 503)
            return self._bootstrap_response(db, row), issued

    def _bootstrap_response(self, db: DB, row: dict[str, Any]) -> dict[str, Any]:
        return dict(
            server_time=json_native(now(db)),
            data=dict(
                csrf_token=self.sessions.bootstrap_csrf(row["id"]),
                expires_at=json_native(row["expires_at"]),
                state="anonymous_bootstrap",
            ),
        )

    def create(
        self,
        token: str | None,
        supplied_csrf: str | None,
        command: dto.CreateSessionInput,
        peer: str,
    ) -> tuple[dict[str, Any], str]:
        command = dto.CreateSessionInput.model_validate(command)
        # Owner/key reservation is intentionally separate from the business transaction.
        with connect(self.config.web.database) as db:
            bounded(db)
            b = self.sessions.bootstrap_locked(db, token)
            self.sessions.supplied_csrf(b, supplied_csrf)
            if b["create_request_key"] not in (None, command.request_key):
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            if b["consumed_at"] is not None:
                raise WebFailure("OWNER_RECOVERY_REQUIRED", 409)
            db.execute(
                "UPDATE business.v4_demo_bootstraps SET create_request_key=%s WHERE id=%s",
                (command.request_key, b["id"]),
            )
        self.rate(peer, "session_create")
        if not _HASH_SLOT.acquire(blocking=False):
            raise WebFailure("RATE_LIMITED", 429)
        try:
            credential = password_hash(secrets.token_urlsafe(32))
        finally:
            _HASH_SLOT.release()
        issued, sid, wid, nonce = "v4d_" + secrets.token_urlsafe(32), uuid4(), uuid4(), uuid4()
        text = _canonical("session_create", command)
        with connect(self.config.web.database) as db:
            bounded(db)
            db.execute("SELECT pg_advisory_xact_lock(1446261840,1)")
            b = self.sessions.bootstrap_locked(db, token)
            self.sessions.supplied_csrf(b, supplied_csrf)
            if b["create_request_key"] != command.request_key:
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            if b["consumed_at"] is not None:
                raise WebFailure("OWNER_RECOVERY_REQUIRED", 409)
            count = db.execute("""SELECT count(*) AS n,min(t.expires_at) AS next_expiry
            FROM business.v4_demo_tenants t
            JOIN business.v4_demo_sessions s ON s.tenant_id=t.id WHERE t.revoked_at IS NULL
            AND s.revoked_at IS NULL AND t.expires_at>clock_timestamp()""").fetchone()
            if count and count["n"] >= 3:
                raise DemoLimit(
                    "CAPACITY_LIMIT", math.ceil((count["next_expiry"] - now(db)).total_seconds())
                )
            db.execute(
                "SELECT business.v4_demo_provision(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    b["id"],
                    command.request_key,
                    text,
                    digest(text),
                    digest(issued),
                    sid,
                    wid,
                    digest(demo_csrf(self.config, sid, nonce, 0, 0)),
                    nonce,
                    digest(secrets.token_urlsafe(32)),
                    digest(csrf_token(self.config.web.csrf_secret, wid)),
                    self.config.web.key_version,
                    credential,
                ),
            )
            subject = self.sessions.resolve_locked(db, issued)
            receipt = _receipt_row(db, sid, "session_create", command.request_key)
            if receipt is None:
                raise WebFailure("SERVICE_UNAVAILABLE", 503)
            data = dict(
                session=self.sessions.session_data(db, subject), receipt=receipt_wire(receipt)
            )
            return self._result(db, subject, data), issued

    @staticmethod
    def _result(
        db: DB, subject: DemoIdentity, data: dict[str, Any], shop: UUID | None = None
    ) -> dict[str, Any]:
        stamp = now(db)
        return dict(
            server_time=json_native(stamp),
            context=subject.context(stamp, shop),
            data=json_native(data),
        )

    def summary(self, token: str | None, shop: UUID, epoch: int, generation: int) -> dict[str, Any]:
        with connect(self.config.web.database) as db:
            bounded(db)
            subject = self.sessions.resolve_locked(db, token)
            self._cas(subject, epoch, generation)
            row = db.execute(
                "SELECT template_key FROM business.v4_demo_shops WHERE tenant_id=%s AND shop_id=%s",
                (subject.tenant["id"], shop),
            ).fetchone()
            if row is None or not any(
                role_scope(db, subject.actor, shop, role) for role in ("operator", "approver")
            ):
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            fixture = db.execute(
                "SELECT canonical_content,content_hash FROM "
                "business.v4_demo_fixture_versions WHERE version=%s",
                (subject.tenant["fixture_version"],),
            ).fetchone()
            if (
                fixture is None
                or fixture["content_hash"] != subject.tenant["fixture_digest"]
                or digest(fixture["canonical_content"]) != fixture["content_hash"]
            ):
                raise WebFailure("SERVICE_UNAVAILABLE", 503)
            content = FixtureContent.model_validate_json(fixture["canonical_content"])
            template = next(s for s in content.shops if s.shop_key == row["template_key"])
            source = self.sessions.session_data(db, subject)["source"]
            self.sessions.resolve_locked(db, token)
            return self._result(
                db,
                subject,
                dict(
                    source=source,
                    counts=template.summary_counts().model_dump(),
                    snapshot_at=json_native(content.snapshot_at),
                ),
                shop,
            )

    @staticmethod
    def _cas(subject: DemoIdentity, epoch: int, generation: int) -> None:
        if type(epoch) is not int or type(generation) is not int or min(epoch, generation) < 0:
            raise WebFailure("INVALID_REQUEST", 422)
        if epoch != subject.session["reset_epoch"]:
            raise WebFailure("EPOCH_CHANGED", 409)
        if generation != subject.session["auth_generation"]:
            raise WebFailure("GENERATION_CHANGED", 409)

    def control(
        self,
        token: str | None,
        supplied_csrf: str | None,
        operation: dto.Operation,
        command: dto.PersonaInput | dto.ResetInput | dto.LogoutInput,
    ) -> dict[str, Any]:
        expected_types: dict[str, type[dto.ExpectedContext]] = {
            "persona": dto.PersonaInput,
            "reset": dto.ResetInput,
            "logout": dto.LogoutInput,
        }
        if operation not in expected_types:
            raise WebFailure("INVALID_REQUEST", 422)
        request = expected_types[operation].model_validate(command)
        text = _canonical(operation, request)
        with connect(self.config.web.database) as db:
            bounded(db)
            target_persona = request.persona_id if isinstance(request, dto.PersonaInput) else None
            subject = self.sessions.resolve_locked(db, token, target_persona=target_persona)
            s, t = subject.session, subject.tenant
            self.sessions.supplied_csrf(s, supplied_csrf)
            old = _receipt_row(db, s["id"], operation, request.request_key)
            if old is not None:
                if old["payload_digest"] != digest(text):
                    raise WebFailure("IDEMPOTENCY_CONFLICT", 409)
                return self._result(
                    db, subject, dict(receipt=receipt_wire(old), next_step="READ_CURRENT_SESSION")
                )
            self._cas(subject, request.expected_epoch, request.expected_generation)
            stamp = now(db)
            if (
                isinstance(request, dto.ResetInput)
                and request.fixture_version != t["fixture_version"]
            ):
                raise WebFailure("INVALID_REQUEST", 422)
            db.execute(
                "UPDATE business.web_sessions SET revoked_at=%s WHERE id=%s",
                (stamp, s["bound_web_session_id"]),
            )
            rid = uuid4()
            epoch, generation = s["reset_epoch"], s["auth_generation"]
            if operation == "logout":
                db.execute(
                    "UPDATE business.v4_demo_sessions SET revoked_at=%s,last_receipt_id=%s "
                    "WHERE id=%s",
                    (stamp, rid, s["id"]),
                )
                db.execute(
                    "UPDATE business.v4_demo_tenants SET revoked_at=%s WHERE id=%s",
                    (stamp, t["id"]),
                )
            else:
                persona = target_persona or s["persona_id"]
                target = db.execute(
                    "SELECT * FROM business.v4_demo_personas WHERE tenant_id=%s AND persona_id=%s",
                    (t["id"], persona),
                ).fetchone()
                if target is None:
                    raise WebFailure("RESOURCE_NOT_FOUND", 404)
                p = self.sessions.credential(
                    db, t["organization_id"], target["principal_id"], target["identity_id"]
                )
                generation += 1
                if operation == "reset":
                    epoch += 1
                    db.execute(
                        "DELETE FROM business.v4_demo_overlays WHERE tenant_id=%s", (t["id"],)
                    )
                    db.execute(
                        "UPDATE business.v4_demo_tenants SET reset_epoch=%s WHERE id=%s",
                        (epoch, t["id"]),
                    )
                wid, nonce = uuid4(), uuid4()
                db.execute(
                    """INSERT INTO business.web_sessions
                (id,token_hash,kind,organization_id,principal_id,identity_id,auth_version,
                csrf_digest,key_version,created_at,last_seen_at,absolute_expires_at,idle_expires_at)
                VALUES(%s,%s,'session',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        wid,
                        digest(secrets.token_urlsafe(32)),
                        t["organization_id"],
                        target["principal_id"],
                        target["identity_id"],
                        p["auth_version"],
                        digest(csrf_token(self.config.web.csrf_secret, wid)),
                        self.config.web.key_version,
                        stamp,
                        stamp,
                        s["expires_at"],
                        s["expires_at"],
                    ),
                )
                db.execute(
                    """UPDATE business.v4_demo_sessions SET persona_id=%s,principal_id=%s,
                identity_id=%s,bound_web_session_id=%s,auth_version=%s,auth_generation=%s,
                reset_epoch=%s,csrf_nonce=%s,csrf_digest=%s,last_receipt_id=%s WHERE id=%s""",
                    (
                        persona,
                        target["principal_id"],
                        target["identity_id"],
                        wid,
                        p["auth_version"],
                        generation,
                        epoch,
                        nonce,
                        digest(demo_csrf(self.config, s["id"], nonce, epoch, generation)),
                        rid,
                        s["id"],
                    ),
                )
            row = db.execute(
                """INSERT INTO business.v4_demo_receipts
            (id,owner_session_id,tenant_id,operation,request_key,canonical_request,payload_digest,
            epoch_before,generation_before,reset_epoch,auth_generation,retain_until)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *,id AS receipt_id""",
                (
                    rid,
                    s["id"],
                    t["id"],
                    operation,
                    request.request_key,
                    text,
                    digest(text),
                    s["reset_epoch"],
                    s["auth_generation"],
                    epoch,
                    generation,
                    t["retain_until"],
                ),
            ).fetchone()
            db.execute(
                """INSERT INTO business.v4_demo_events
            (id,tenant_id,owner_session_id,receipt_id,event_kind,reset_epoch,auth_generation)
            VALUES(%s,%s,%s,%s,%s,%s,%s)""",
                (
                    uuid4(),
                    t["id"],
                    s["id"],
                    rid,
                    {
                        "persona": "demo.persona_changed",
                        "reset": "demo.reset_committed",
                        "logout": "demo.session_revoked",
                    }[operation],
                    epoch,
                    generation,
                ),
            )
            if row is None:
                raise WebFailure("SERVICE_UNAVAILABLE", 503)
            if operation != "logout":
                subject = self.sessions.resolve_locked(db, token)
            return self._result(
                db,
                subject,
                dict(
                    receipt=receipt_wire(row),
                    next_step="LOGGED_OUT" if operation == "logout" else "READ_CURRENT_SESSION",
                ),
            )

    def operation(self, token: str | None, operation: dto.Operation, key: UUID) -> dict[str, Any]:
        data: dict[str, Any]
        with connect(self.config.web.database) as db:
            bounded(db)
            if token and token.startswith("v4b_"):
                b = self.sessions.bootstrap_locked(db, token)
                if operation != "session_create" or b["create_request_key"] != key:
                    raise WebFailure("RESOURCE_NOT_FOUND", 404)
                row = db.execute(
                    """SELECT r.id FROM business.v4_demo_sessions s
                JOIN business.v4_demo_receipts r ON r.owner_session_id=s.id
                WHERE s.bootstrap_id=%s AND r.operation='session_create' AND r.request_key=%s""",
                    (b["id"], key),
                ).fetchone()
                committed = row is not None
                data = dict(
                    operation="session_create",
                    request_key=str(key),
                    status="COMMITTED" if committed else "UNKNOWN",
                    recovery="OWNER_RECOVERY_REQUIRED" if committed else "WAIT_READ_ONLY",
                )
            else:
                subject = self.sessions.resolve_locked(db, token)
                row = _receipt_row(db, subject.session["id"], operation, key)
                if row is None:
                    raise WebFailure("RESOURCE_NOT_FOUND", 404)
                data = dict(receipt=receipt_wire(row))
            return dict(data=data, server_time=json_native(now(db)))
