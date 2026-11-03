"""V4-only bearer resolution with the complete legacy credential/bound-session closure."""

import hmac
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

import psycopg
from pydantic import BaseModel, ConfigDict

from commerceops.application.replenishment.contracts import WebActor, WebFailure
from commerceops.application.replenishment.security import capability, csrf_token, digest
from commerceops.application.v4_demo import contracts as dto
from commerceops.application.v4_demo.contracts import Context
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.web_config import WebConfig, private_bytes
from commerceops.infrastructure.web_sessions import actor_guard, json_native, now, role_scope


class DemoLimit(WebFailure):
    def __init__(self, code: str, retry_after: int):
        super().__init__(code, 429)
        self.retry_after = max(1, retry_after)


DB = psycopg.Connection[dict[str, Any]]
COOKIE = "commerceops_v4_demo"


@dataclass(frozen=True)
class DemoConfig:
    web: WebConfig
    api_origin: str
    enabled: bool = False
    allow_non_browser_get: bool = False

    def __post_init__(self) -> None:
        origin = urlsplit(self.api_origin)
        _ = origin.port
        if (
            re.fullmatch(r"v4_demo_[a-z0-9_]{1,48}", self.web.database.name) is None
            or type(self.enabled) is not bool
            or type(self.allow_non_browser_get) is not bool
            or origin.path
            or origin.query
            or origin.fragment
            or origin.username
            or origin.password
            or not origin.hostname
            or self.api_origin != f"{origin.scheme}://{origin.netloc}"
            or self.web.transport_mode == "https"
            and origin.scheme != "https"
            or self.web.transport_mode == "local_http"
            and (
                origin.scheme != "http" or origin.hostname not in ("localhost", "127.0.0.1", "::1")
            )
            or self.allow_non_browser_get
            and self.web.transport_mode != "local_http"
        ):
            raise ValueError("INVALID_DEMO_CONFIGURATION")

    @classmethod
    def load(cls, path: Path) -> "DemoConfig":
        class File(BaseModel):
            model_config = ConfigDict(strict=True, extra="forbid")
            schema_version: Literal["v4-demo-deployment-v1"]
            web_config_file: str
            api_origin: str
            enabled: bool = False
            allow_non_browser_get: bool = False

        value = File.model_validate_json(private_bytes(path))
        return cls(
            WebConfig.from_file(Path(value.web_config_file)),
            value.api_origin,
            value.enabled,
            value.allow_non_browser_get,
        )


@dataclass(frozen=True)
class DemoIdentity:
    tenant: dict[str, Any]
    session: dict[str, Any]
    actor: WebActor

    def context(self, timestamp: datetime, shop_id: UUID | None = None) -> dict[str, Any]:
        value = Context(
            tenant_id=self.tenant["id"],
            organization_id=self.tenant["organization_id"],
            principal_id=self.actor.principal_id,
            shop_id=shop_id,
            reset_epoch=self.session["reset_epoch"],
            auth_generation=self.session["auth_generation"],
            authorized_at=timestamp,
        )
        return value.model_dump(mode="json")


def bounded(db: DB) -> None:
    db.execute("SET LOCAL statement_timeout='5000ms'")
    db.execute("SET LOCAL lock_timeout='1000ms'")


def token_hash(token: str | None, prefix: Literal["v4b_", "v4d_"]) -> str:
    if token is None or re.fullmatch(re.escape(prefix) + r"[A-Za-z0-9_-]{43}", token) is None:
        raise WebFailure("SESSION_INVALID", 401)
    return digest(token)


def demo_csrf(config: DemoConfig, sid: UUID, nonce: UUID, epoch: int, generation: int) -> str:
    return capability(
        config.web.csrf_secret,
        "v4-demo-csrf-v1",
        {
            "session_id": str(sid),
            "nonce": str(nonce),
            "epoch": epoch,
            "generation": generation,
        },
    )


class DemoSessions:
    def __init__(self, config: DemoConfig):
        self.config = config

    def bootstrap_csrf(self, bid: UUID) -> str:
        return capability(self.config.web.csrf_secret, "v4-demo-bootstrap-v1", str(bid))

    def bootstrap_locked(self, db: DB, token: str | None) -> dict[str, Any]:
        value = token_hash(token, "v4b_")
        row = db.execute(
            "SELECT * FROM business.v4_demo_bootstraps WHERE token_hash=%s FOR UPDATE", (value,)
        ).fetchone()
        if (
            not row
            or row["expires_at"] <= now(db)
            or row["key_version"] != self.config.web.key_version
        ):
            raise WebFailure("SESSION_INVALID", 401)
        if not hmac.compare_digest(row["csrf_digest"], digest(self.bootstrap_csrf(row["id"]))):
            raise WebFailure("SESSION_INVALID", 401)
        return row

    @staticmethod
    def supplied_csrf(row: dict[str, Any], supplied: str | None) -> None:
        if supplied is None or not hmac.compare_digest(row["csrf_digest"], digest(supplied)):
            raise WebFailure("CSRF_INVALID", 403)

    @staticmethod
    def credential(db: DB, org: UUID, principal: UUID, identity: UUID) -> dict[str, Any]:
        row = db.execute(
            """SELECT p.* FROM business.principals p
        JOIN business.identities i ON i.principal_id=p.id AND i.organization_id=p.organization_id
        JOIN business.web_credentials c ON c.identity_id=i.id AND c.principal_id=p.id
        AND c.organization_id=p.organization_id WHERE p.id=%s AND p.organization_id=%s
        AND i.id=%s AND i.provider='web' AND c.enabled FOR SHARE OF p""",
            (principal, org, identity),
        ).fetchone()
        if row is None or not row["enabled"]:
            raise WebFailure("SESSION_INVALID", 401)
        return row

    def resolve_locked(
        self, db: DB, token: str | None, *, target_persona: dto.PersonaId | None = None
    ) -> DemoIdentity:
        value = token_hash(token, "v4d_")
        target = db.execute(
            "SELECT tenant_id FROM business.v4_demo_sessions WHERE token_hash=%s", (value,)
        ).fetchone()
        if target is None:
            raise WebFailure("SESSION_INVALID", 401)
        tenant = db.execute(
            "SELECT * FROM business.v4_demo_tenants WHERE id=%s FOR UPDATE", (target["tenant_id"],)
        ).fetchone()
        session = db.execute(
            "SELECT * FROM business.v4_demo_sessions WHERE token_hash=%s AND "
            "tenant_id=%s FOR UPDATE",
            (value, target["tenant_id"]),
        ).fetchone()
        stamp = now(db)
        if (
            not tenant
            or not session
            or tenant["revoked_at"]
            or session["revoked_at"]
            or tenant["expires_at"] <= stamp
            or session["expires_at"] != tenant["expires_at"]
            or session["reset_epoch"] != tenant["reset_epoch"]
            or session["key_version"] != self.config.web.key_version
        ):
            raise WebFailure("SESSION_INVALID", 401)
        persona = db.execute(
            """SELECT 1 FROM business.v4_demo_personas WHERE tenant_id=%s
        AND organization_id=%s AND persona_id=%s AND principal_id=%s AND identity_id=%s""",
            (
                tenant["id"],
                tenant["organization_id"],
                session["persona_id"],
                session["principal_id"],
                session["identity_id"],
            ),
        ).fetchone()
        if target_persona is not None:
            targets = db.execute(
                """SELECT * FROM business.v4_demo_personas
            WHERE tenant_id=%s AND persona_id=ANY(%s) ORDER BY principal_id""",
                (tenant["id"], [session["persona_id"], target_persona]),
            ).fetchall()
            if not any(row["persona_id"] == target_persona for row in targets):
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            for target in targets:
                self.credential(
                    db, tenant["organization_id"], target["principal_id"], target["identity_id"]
                )
        principal = self.credential(
            db, tenant["organization_id"], session["principal_id"], session["identity_id"]
        )
        if not persona or principal["auth_version"] != session["auth_version"]:
            raise WebFailure("SESSION_INVALID", 401)
        bound = db.execute(
            "SELECT * FROM business.web_sessions WHERE id=%s FOR UPDATE",
            (session["bound_web_session_id"],),
        ).fetchone()
        stamp = now(db)
        if (
            not bound
            or bound["kind"] != "session"
            or bound["revoked_at"]
            or (
                bound["organization_id"],
                bound["principal_id"],
                bound["identity_id"],
                bound["auth_version"],
            )
            != (
                tenant["organization_id"],
                session["principal_id"],
                session["identity_id"],
                session["auth_version"],
            )
            or min(bound["absolute_expires_at"], bound["idle_expires_at"]) <= stamp
            or max(bound["absolute_expires_at"], bound["idle_expires_at"]) > session["expires_at"]
            or bound["key_version"] != self.config.web.key_version
            or bound["token_hash"] == value
            or not hmac.compare_digest(
                bound["csrf_digest"], digest(csrf_token(self.config.web.csrf_secret, bound["id"]))
            )
        ):
            raise WebFailure("SESSION_INVALID", 401)
        expected_csrf = demo_csrf(
            self.config,
            session["id"],
            session["csrf_nonce"],
            session["reset_epoch"],
            session["auth_generation"],
        )
        if not hmac.compare_digest(session["csrf_digest"], digest(expected_csrf)):
            raise WebFailure("SESSION_INVALID", 401)
        actor = WebActor(
            bound["id"],
            session["principal_id"],
            session["identity_id"],
            tenant["organization_id"],
            session["auth_version"],
        )
        actor_guard(db, actor)
        return DemoIdentity(tenant, session, actor)

    def session_data(self, db: DB, subject: DemoIdentity) -> dict[str, Any]:
        s, t = subject.session, subject.tenant
        rows = db.execute(
            """SELECT sh.*,m.template_key FROM business.v4_demo_shops m
        JOIN business.shops sh ON sh.id=m.shop_id AND sh.organization_id=m.organization_id
        WHERE m.tenant_id=%s ORDER BY m.shop_id""",
            (t["id"],),
        ).fetchall()
        shops = []
        for row in rows:
            grants = [
                role
                for role in ("operator", "approver")
                if role_scope(db, subject.actor, row["id"], role)
            ]
            if grants:
                shops.append(
                    dict(
                        shop_id=row["id"],
                        display_name="台北合成演示店"
                        if row["template_key"] == "v4-shop-a"
                        else "上海合成演示店",
                        timezone=row["timezone"],
                        currency=row["currency"],
                        grants=grants,
                    )
                )
        return dict(
            creation_request_key=s["creation_request_key"],
            persona_id=s["persona_id"],
            expires_at=s["expires_at"],
            csrf_token=demo_csrf(
                self.config, s["id"], s["csrf_nonce"], s["reset_epoch"], s["auth_generation"]
            ),
            shops=shops,
            source=dict(
                data_mode="demo_fixture",
                evidence_mode="synthetic_demo",
                fixture_version=t["fixture_version"],
                fixture_digest=t["fixture_digest"],
            ),
        )

    def current(self, token: str | None) -> dict[str, Any]:
        with connect(self.config.web.database) as db:
            bounded(db)
            subject = self.resolve_locked(db, token)
            data = self.session_data(db, subject)
            self.resolve_locked(db, token)
            stamp = now(db)
            return dict(
                data=json_native(data),
                context=subject.context(stamp),
                server_time=json_native(stamp),
            )
