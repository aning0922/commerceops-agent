"""浏览器安全投影/实际运行Gate；不暴露target/record/client token/PID/外部身份。"""

import re
from typing import Any
from uuid import UUID

from commerceops.infrastructure.web_sessions import DB, now
from commerceops.infrastructure.worker_lock import LOCK_KEY


def sender_gates(db: DB, organization: UUID, shops: list[UUID] | None) -> list[dict[str, Any]]:
    rows = db.execute(
        """SELECT s.destination_alias,s.configured_enabled,s.expires_at,s.verification_mode,
        s.checked_at,EXISTS(SELECT 1 FROM pg_locks l WHERE l.locktype='advisory'
        AND l.pid=s.worker_backend_pid AND l.classid=%s AND l.objid=%s AND l.granted)
        AND EXISTS(SELECT 1 FROM business.audit_events e WHERE e.source='worker'
        AND e.entity_type='worker_runtime' AND e.entity_id=s.worker_owner AND e.action='started')
        AND NOT EXISTS(SELECT 1 FROM business.audit_events e WHERE e.source='worker'
        AND e.entity_type='worker_runtime' AND e.entity_id=s.worker_owner
        AND e.action IN ('stopped','termination_confirmed')) AS worker_ready
        FROM business.p4_sender_state s WHERE s.organization_id=%s
        AND (%s::uuid[] IS NULL OR s.shop_id=ANY(%s)) ORDER BY s.destination_alias,s.shop_id""",
        (LOCK_KEY >> 32, LOCK_KEY & 0xFFFFFFFF, organization, shops, shops),
    ).fetchall()
    timestamp = now(db)
    result = []
    for row in rows:
        reason = (
            "DISABLED_BY_CONFIGURATION"
            if not row["configured_enabled"]
            else "WINDOW_EXPIRED"
            if row["expires_at"] <= timestamp
            else "WORKER_NOT_READY"
            if not row["worker_ready"]
            else "CONTROLLED_WINDOW_ACTIVE"
        )
        result.append(
            {
                "destination_alias": row["destination_alias"],
                "sender_enabled": reason == "CONTROLLED_WINDOW_ACTIVE",
                "reason_code": reason,
                "verification_mode": row["verification_mode"],
                "as_of": row["checked_at"],
                "worker_ready": row["worker_ready"],
            }
        )
    present = {r["destination_alias"] for r in result}
    return result + [
        {
            "destination_alias": alias,
            "sender_enabled": False,
            "reason_code": "NOT_CONFIGURED",
            "verification_mode": None,
            "as_of": timestamp,
            "worker_ready": None,
        }
        for alias in ("IM", "Base")
        if alias not in present
    ]


def external_enabled(gates: list[dict[str, Any]]) -> bool:
    return any(g["sender_enabled"] and g["verification_mode"] == "controlled_sdk" for g in gates)


def safe_code(value: object) -> str | None:
    if value is None:
        return None
    return (
        value
        if isinstance(value, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", value)
        else "PROJECTION_ERROR"
    )
