"""PG服务端会话、持久登录限流和当前角色scope；不使用内存身份选择器。"""

import hmac
import re
import secrets
import threading
from datetime import datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg

from commerceops.application.replenishment.contracts import WebActor, WebFailure
from commerceops.application.replenishment.security import (
    csrf_token,
    digest,
    password_hash,
    verify_password,
)
from commerceops.domain.commerce_values import canonical, utc_time
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.web_config import WebConfig

DB = psycopg.Connection[dict[str, Any]]


def now(db: DB) -> datetime:
    row = db.execute("SELECT clock_timestamp() AS time").fetchone()
    if row is None:
        raise WebFailure("SERVICE_UNAVAILABLE", 503)
    return utc_time(row["time"])


def json_native(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: json_native(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_native(item) for item in value]
    return canonical(value)


def envelope(db: DB, **fields: Any) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json_native(
            {
                "schema_version": "p3-web-v1",
                "identity_mode": "session",
                "server_time": now(db),
                "trace_id": uuid4(),
                **fields,
            }
        ),
    )


def actor_guard(db: DB, actor: WebActor) -> dict[str, Any]:
    principal = db.execute(
        """SELECT * FROM business.principals WHERE id=%s AND organization_id=%s FOR SHARE""",
        (actor.principal_id, actor.organization_id),
    ).fetchone()
    session = db.execute(
        """SELECT * FROM business.web_sessions WHERE id=%s AND kind='session' FOR SHARE""",
        (actor.session_id,),
    ).fetchone()
    timestamp = now(db)
    if (
        principal is None
        or not principal["enabled"]
        or principal["auth_version"] != actor.auth_version
        or session is None
        or session["revoked_at"] is not None
        or session["absolute_expires_at"] <= timestamp
        or session["idle_expires_at"] <= timestamp
        or (
            session["principal_id"],
            session["organization_id"],
            session["identity_id"],
            session["auth_version"],
        )
        != (actor.principal_id, actor.organization_id, actor.identity_id, actor.auth_version)
    ):
        raise WebFailure("SESSION_INVALID", 401)
    return principal


def role_scope(db: DB, actor: WebActor, shop: UUID, role: str) -> bool:
    actor_guard(db, actor)
    row = db.execute(
        "SELECT business.lock_p3_permission(%s,%s,%s,%s,%s,%s) AS allowed",
        (
            actor.principal_id,
            actor.organization_id,
            shop,
            actor.identity_id,
            actor.auth_version,
            role,
        ),
    ).fetchone()
    return bool(row and row["allowed"])


def deployment(config: WebConfig, timezone: str | None = None) -> dict[str, Any]:
    return {
        "config_version": config.config_version,
        "shop_timezone": timezone,
        "approval_ttl_seconds": config.approval_ttl_seconds,
        "revalidation_max_age_seconds": config.revalidation_max_age_seconds,
        "max_plan_items": config.max_plan_items,
        "recovery_scan_seconds": config.recovery_scan_seconds,
        "session_absolute_seconds": config.session_absolute_seconds,
        "session_idle_seconds": config.session_idle_seconds,
        "transport_mode": config.transport_mode,
        "source_mode": "mock",
        "model_requests_enabled": False,
        "external_sender_enabled": False,
    }


class SessionStore:
    def __init__(self, config: WebConfig):
        self.config = config
        self._hash_slot = threading.Semaphore(1)
        self._dummy = password_hash(secrets.token_urlsafe(32))

    def _csrf(self, row: dict[str, Any]) -> str:
        if row["key_version"] != self.config.key_version:
            raise WebFailure("SESSION_INVALID", 401)
        value = csrf_token(self.config.csrf_secret, row["id"])
        if not hmac.compare_digest(digest(value), row["csrf_digest"]):
            raise WebFailure("SESSION_INVALID", 401)
        return value

    def _session(self, db: DB, token: str | None, *, touch: bool = True) -> dict[str, Any]:
        if token is None or re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None:
            raise WebFailure("SESSION_INVALID", 401)
        row = db.execute(
            "SELECT * FROM business.web_sessions WHERE token_hash=%s", (digest(token),)
        ).fetchone()
        if row is None:
            raise WebFailure("SESSION_INVALID", 401)
        if row["kind"] == "session":
            # 每次请求都重新校验principal/identity映射和当前auth_version。
            principal = db.execute(
                """SELECT p.* FROM business.principals p
                JOIN business.identities i ON i.principal_id=p.id
                AND i.organization_id=p.organization_id
                JOIN business.web_credentials c ON c.identity_id=i.id AND c.principal_id=p.id
                AND c.organization_id=p.organization_id WHERE p.id=%s AND p.organization_id=%s
                AND i.id=%s AND i.provider='web' AND c.enabled FOR SHARE OF p""",
                (row["principal_id"], row["organization_id"], row["identity_id"]),
            ).fetchone()
            if (
                not principal
                or not principal["enabled"]
                or principal["auth_version"] != row["auth_version"]
            ):
                raise WebFailure("SESSION_INVALID", 401)
        locked = db.execute(
            "SELECT * FROM business.web_sessions WHERE id=%s FOR UPDATE", (row["id"],)
        ).fetchone()
        timestamp = now(db)
        if (
            not locked
            or locked["revoked_at"]
            or min(locked["absolute_expires_at"], locked["idle_expires_at"]) <= timestamp
        ):
            raise WebFailure("SESSION_INVALID", 401)
        self._csrf(locked)
        if touch:
            idle = min(
                locked["absolute_expires_at"],
                timestamp + timedelta(seconds=self.config.session_idle_seconds),
            )
            db.execute(
                "UPDATE business.web_sessions SET last_seen_at=%s,idle_expires_at=%s WHERE id=%s",
                (timestamp, idle, locked["id"]),
            )
            locked["idle_expires_at"] = idle
        return locked

    @staticmethod
    def _actor(row: dict[str, Any]) -> WebActor:
        if row["kind"] != "session":
            raise WebFailure("SESSION_INVALID", 401)
        return WebActor(
            row["id"],
            row["principal_id"],
            row["identity_id"],
            row["organization_id"],
            row["auth_version"],
        )

    def authenticate(self, token: str | None) -> WebActor:
        with connect(self.config.database) as db:
            return self._actor(self._session(db, token))

    def check_csrf(self, token: str | None, supplied: str | None) -> None:
        with connect(self.config.database) as db:
            row = self._session(db, token, touch=False)
            if supplied is None or not hmac.compare_digest(digest(supplied), row["csrf_digest"]):
                raise WebFailure("CSRF_INVALID", 403)

    def _create(self, db: DB, identity: dict[str, Any] | None) -> tuple[str, dict[str, Any]]:
        timestamp, session_id, token = now(db), uuid4(), secrets.token_urlsafe(32)
        authenticated = identity is not None
        absolute = timestamp + timedelta(
            seconds=self.config.session_absolute_seconds if authenticated else 300
        )
        idle = min(
            absolute,
            timestamp
            + timedelta(seconds=self.config.session_idle_seconds if authenticated else 300),
        )
        db.execute(
            """INSERT INTO business.web_sessions
            (id,token_hash,kind,organization_id,principal_id,identity_id,auth_version,
            csrf_digest,key_version,created_at,last_seen_at,absolute_expires_at,idle_expires_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                session_id,
                digest(token),
                "session" if authenticated else "anonymous_bootstrap",
                identity["organization_id"] if identity else None,
                identity["principal_id"] if identity else None,
                identity["identity_id"] if identity else None,
                identity["auth_version"] if identity else None,
                digest(csrf_token(self.config.csrf_secret, session_id)),
                self.config.key_version,
                timestamp,
                timestamp,
                absolute,
                idle,
            ),
        )
        row = db.execute(
            "SELECT * FROM business.web_sessions WHERE id=%s", (session_id,)
        ).fetchone()
        if row is None:
            raise WebFailure("SERVICE_UNAVAILABLE", 503)
        return token, row

    def bootstrap(self, token: str | None) -> tuple[str | None, dict[str, Any]]:
        with connect(self.config.database) as db:
            try:
                # savepoint恢复过期/被撤销会话；不能吞掉DB错误。
                with db.transaction():
                    row = self._session(db, token)
                issued = None
            except WebFailure:
                issued, row = self._create(db, None)
            return issued, envelope(
                db,
                identity_mode=row["kind"],
                csrf_token=self._csrf(row),
                bootstrap_expires_at=row["absolute_expires_at"]
                if row["kind"] == "anonymous_bootstrap"
                else None,
            )

    def _record_attempt(self, login: str, peer: str) -> dict[str, Any] | None:
        login_key, peer_key = digest(login), digest(peer)
        with connect(self.config.database) as db:
            # 两个滑窗串行化，统一排序锁避免并发跨键形成锁环。
            for key in sorted(("account:" + login_key, "peer:" + peer_key)):
                db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (key,))
            timestamp = now(db)
            row = db.execute(
                """SELECT count(*) FILTER(WHERE login_digest=%s) AS account,
                count(*) FILTER(WHERE peer_digest=%s) AS peer FROM business.web_login_attempts
                WHERE occurred_at>%s""",
                (
                    login_key,
                    peer_key,
                    timestamp - timedelta(seconds=self.config.login_window_seconds),
                ),
            ).fetchone()
            if row and (
                row["account"] >= self.config.login_account_limit
                or row["peer"] >= self.config.login_peer_limit
            ):
                raise WebFailure("RATE_LIMITED", 429)
            db.execute(
                "INSERT INTO business.web_login_attempts VALUES (%s,%s,%s,%s)",
                (uuid4(), login_key, peer_key, timestamp),
            )
            return db.execute(
                "SELECT * FROM business.web_credentials WHERE login=%s", (login,)
            ).fetchone()

    def login(self, token: str, login: str, password: str, peer: str) -> tuple[str, dict[str, Any]]:
        normalized = login.strip().lower()
        credentials = self._record_attempt(normalized, peer)
        # 固定少量预置用户；单API进程仅一份128MiB scrypt工作区，不扩成调度器。
        with self._hash_slot:
            valid = verify_password(
                password, credentials["password_hash"] if credentials else self._dummy
            )
        if not valid or not credentials or not credentials["enabled"]:
            raise WebFailure("LOGIN_FAILED", 401)
        with connect(self.config.database) as db:
            identity = db.execute(
                """SELECT c.*,p.auth_version FROM business.web_credentials c
                JOIN business.principals p ON p.id=c.principal_id
                AND p.organization_id=c.organization_id
                JOIN business.identities i ON i.id=c.identity_id AND i.principal_id=p.id
                AND i.organization_id=p.organization_id WHERE c.login=%s AND c.enabled
                AND p.enabled AND i.provider='web' FOR SHARE OF p""",
                (normalized,),
            ).fetchone()
            if not identity or not hmac.compare_digest(
                identity["password_hash"], credentials["password_hash"]
            ):
                raise WebFailure("LOGIN_FAILED", 401)
            previous = self._session(db, token, touch=False)
            issued, row = self._create(db, identity)
            db.execute(
                "UPDATE business.web_sessions SET revoked_at=clock_timestamp() WHERE id=%s",
                (previous["id"],),
            )
            return issued, self._read(db, row)

    def _read(self, db: DB, row: dict[str, Any]) -> dict[str, Any]:
        actor = self._actor(row)
        principal = actor_guard(db, actor)
        grants = db.execute(
            """SELECT g.role,g.shop_id FROM business.principal_role_shop_grants g
            JOIN business.principal_shop_scopes s ON s.organization_id=g.organization_id
            AND s.shop_id=g.shop_id AND s.principal_id=g.principal_id
            WHERE g.organization_id=%s AND g.principal_id=%s AND g.enabled AND s.enabled
            AND g.role=ANY(%s) ORDER BY g.role,g.shop_id""",
            (actor.organization_id, actor.principal_id, principal["roles"]),
        ).fetchall()
        roles = {g["role"] for g in grants}
        business = bool(roles.intersection({"operator", "approver"}))
        capabilities = {
            "can_create_task": "operator" in roles,
            "can_read_tasks": business,
            "can_read_approvals": business,
            "can_resolve_items": False,  # A03运行/回执Gate前不宣称resolve可用。
            "can_read_operations": "admin" in roles,
            "home_path": "/tasks"
            if business
            else "/admin/operations"
            if "admin" in roles
            else "/access",
        }
        return envelope(
            db,
            principal={
                "principal_id": actor.principal_id,
                "organization_id": actor.organization_id,
                "display_name": principal["display_name"],
                "auth_version": actor.auth_version,
                "role_shop_grants": grants,
                "capabilities": capabilities,
            },
            csrf_token=self._csrf(row),
            absolute_expires_at=row["absolute_expires_at"],
            idle_expires_at=row["idle_expires_at"],
            config=deployment(self.config),
        )

    def read(self, token: str | None) -> dict[str, Any]:
        with connect(self.config.database) as db:
            return self._read(db, self._session(db, token))

    def logout(self, token: str | None) -> dict[str, Any]:
        with connect(self.config.database) as db:
            row = self._session(db, token, touch=False)
            self._actor(row)
            db.execute(
                "UPDATE business.web_sessions SET revoked_at=clock_timestamp() WHERE id=%s",
                (row["id"],),
            )
            return envelope(db, logged_out=True)
