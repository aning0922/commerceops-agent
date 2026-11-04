"""Owner-activated V41 key policy. Runtime configuration never activates itself.

Initialization: migrate, initialize the unchanged fixture, activate this policy in an owner
transaction, then grant the reviewed runtime functions and start the API with that exact config.
Rotation: stop old API ingress, activate a fresh version atomically, commit, then start the new API.
Tenant/session locks precede policy locks; old private demo bindings are permanently revoked.
Existing M3/non-demo sessions are excluded. Tenant GC must never delete the singleton.
"""

import hashlib
import hmac
import re
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from commerceops.application.replenishment.contracts import WebFailure
from commerceops.application.replenishment.security import csrf_token
from commerceops.domain.commerce_values import facts_hash
from commerceops.infrastructure.v4_demo_sessions import DemoConfig, bounded
from commerceops.infrastructure.web_sessions import DB


def config_fingerprint(config: DemoConfig) -> str:
    if not config.enabled or re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", config.web.key_version) is None:
        raise ValueError("V41_POLICY_CONFIGURATION")
    return facts_hash(
        dict(
            domain="v41-active-config-1",
            active_version=config.web.key_version,
            csrf_digest=hashlib.sha256(config.web.csrf_secret).hexdigest(),
            nonce_digest=hashlib.sha256(config.web.nonce_secret).hexdigest(),
            origins=sorted(config.web.origins),
            api_origin=config.api_origin,
            transport=config.web.transport_mode,
            allow_non_browser_get=config.allow_non_browser_get,
        )
    )


def policy_matches(row: Mapping[str, Any] | None, config: DemoConfig) -> bool:
    if row is None or row.get("active_version") != config.web.key_version:
        return False
    digest = row.get("config_digest")
    return (
        isinstance(digest, str)
        and re.fullmatch(r"[a-f0-9]{64}", digest) is not None
        and hmac.compare_digest(digest, config_fingerprint(config))
    )


def binding_proof(config: DemoConfig, bound_session_id: UUID) -> str:
    """Private server-derived bound-session MAC, never accepted from or returned to the browser."""
    config_fingerprint(config)
    return csrf_token(config.web.csrf_secret, bound_session_id)


def assert_policy(db: DB, config: DemoConfig) -> None:
    """Call inside the tenant-locked V41 guard; SQL actor locks the authoritative row too."""
    row = db.execute(
        "SELECT active_version,config_digest FROM business.v41_security_policy WHERE singleton"
    ).fetchone()
    if not policy_matches(row, config):
        raise WebFailure("SERVICE_UNAVAILABLE", 503)


def _owner(db: DB) -> None:
    revision = db.execute("SELECT version_num FROM business.alembic_version").fetchone()
    if revision != {"version_num": "0025_v41_catalog_operations"}:
        raise ValueError("V41_SCHEMA_REVISION")
    environment = db.execute("""SELECT current_database() AS name,
     current_setting('server_version') AS version,
     (SELECT extversion FROM pg_extension WHERE extname='vector') AS vector""").fetchone()
    if (
        not environment
        or re.fullmatch(r"v4_demo_[a-z0-9_]{1,48}", environment["name"]) is None
        or not environment["version"].startswith("17.11")
        or environment["vector"] != "0.8.7"
    ):
        raise ValueError("V41_OWNED_DATABASE")
    for table in ("v41_security_policy", "v4_demo_tenants", "v4_demo_sessions", "web_sessions"):
        owner = db.execute(
            "SELECT current_user=pg_get_userbyid(relowner) AS allowed FROM pg_class "
            "WHERE oid=to_regclass(%s)",
            ("business." + table,),
        ).fetchone()
        if owner is None or not owner["allowed"]:
            raise ValueError("V41_OWNER_REQUIRED")


def activate_policy(db: DB, config: DemoConfig) -> dict[str, Any]:
    """Caller owns transaction: tenant/session locks, then policy switch and old demo revocation."""
    fingerprint = config_fingerprint(config)
    _owner(db)
    bounded(db)
    db.execute("SELECT pg_advisory_xact_lock(1446261845,2)")
    # Serialize the owned transition with the existing V40 create/provision capacity transaction.
    db.execute("SELECT pg_advisory_xact_lock(1446261840,1)")
    tenants = db.execute("""SELECT t.id,o.name FROM business.v4_demo_tenants t
     JOIN business.organizations o ON o.id=t.organization_id
     ORDER BY t.id FOR UPDATE OF t""").fetchall()
    if any(row["name"] != "V4 synthetic demo " + str(row["id"]) for row in tenants):
        raise ValueError("V41_OWNED_BINDING")
    db.execute(
        "SELECT s.id FROM business.v4_demo_sessions s ORDER BY s.tenant_id,s.id FOR UPDATE"
    ).fetchall()
    current = db.execute(
        "SELECT * FROM business.v41_security_policy WHERE singleton FOR UPDATE"
    ).fetchone()
    version = config.web.key_version
    if current is None:
        db.execute(
            "INSERT INTO business.v41_security_policy(singleton,active_version,config_digest,"
            "generation) VALUES(true,%s,%s,1)",
            (version, fingerprint),
        )
    elif version == current["active_version"]:
        if not hmac.compare_digest(current["config_digest"], fingerprint):
            raise ValueError("V41_POLICY_VERSION_REUSE")
    else:
        if version in current["retired_versions"] or len(current["retired_versions"]) >= 64:
            raise ValueError("V41_POLICY_VERSION_REUSE")
        db.execute(
            """UPDATE business.v41_security_policy SET active_version=%s,config_digest=%s,
         generation=generation+1,activated_at=clock_timestamp(),
         retired_versions=array_append(retired_versions,active_version) WHERE singleton""",
            (version, fingerprint),
        )
    # Match private demo binding IDs only; never revoke M3/non-demo sessions by organization.
    stopped = db.execute(
        """UPDATE business.web_sessions w SET revoked_at=clock_timestamp()
     FROM business.v4_demo_sessions s JOIN business.v4_demo_tenants t ON t.id=s.tenant_id
     WHERE w.id=s.bound_web_session_id AND w.organization_id=t.organization_id
     AND w.principal_id=s.principal_id AND w.identity_id=s.identity_id
     AND s.key_version<>%s AND w.revoked_at IS NULL RETURNING w.id""",
        (version,),
    ).fetchall()
    result = db.execute(
        "SELECT active_version,generation FROM business.v41_security_policy WHERE singleton"
    ).fetchone()
    if result is None:
        raise ValueError("V41_POLICY_NOT_ACTIVATED")
    return dict(
        active_version=result["active_version"],
        generation=result["generation"],
        revoked_demo_bindings=len(stopped),
    )
