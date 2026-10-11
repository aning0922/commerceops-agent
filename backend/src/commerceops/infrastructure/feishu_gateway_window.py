"""复用原不可变audit+PG session锁，启动一次，不与Worker共享连接。"""

from typing import Any

from psycopg.types.json import Jsonb

from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.application.feishu_business.gateway_window import GatewayWindow
from commerceops.application.replenishment.contracts import WebFailure
from commerceops.infrastructure.web_sessions import DB


def claim_gateway(db: DB, settings: BusinessSettings, window: GatewayWindow) -> None:
    if not window.active() or (window.organization_id, window.shop_id) != (
        settings.organization_id,
        settings.shop_id,
    ):
        raise PermissionError("P4_GATEWAY_WINDOW_CLOSED")
    # 单部署同PG单App唯一consumer；不是第二Worker/Graph锁，不跨process传PG对象。
    row = db.execute(
        "SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS held",
        ("p4-gateway:" + settings.app_id,),
    ).fetchone()
    if not row or not row["held"]:
        raise PermissionError("P4_GATEWAY_ALREADY_RUNNING")
    org = db.execute(
        """SELECT 1 FROM business.organizations o JOIN business.shops s
        ON s.organization_id=o.id WHERE o.id=%s AND s.id=%s
        AND o.feishu_app_id=%s AND o.feishu_tenant_key=%s
        AND s.adapter_kind='mock' AND s.environment IN ('mock','test')""",
        (settings.organization_id, settings.shop_id, settings.app_id, settings.tenant_key),
    ).fetchone()
    if not org:
        raise PermissionError("P4_GATEWAY_TRUSTED_SCOPE_MISMATCH")
    # audit.id固定window原UUID，一次claim后同ID不能再次启动/重开预算；row不可变。
    db.execute(
        """INSERT INTO business.audit_events(id,organization_id,shop_id,source,
        action,entity_type,entity_id,after_state,trace_id)
        VALUES(%s,%s,%s,'feishu_gateway','gateway_start_claimed','gateway_window',%s,%s,%s)""",
        (
            window.window_id,
            settings.organization_id,
            settings.shop_id,
            str(window.window_id),
            Jsonb(
                {
                    "expires_at": window.expires_at.isoformat(),
                    "max_workflows": window.max_workflows,
                    "max_callbacks": window.max_callbacks,
                    "verification_mode": "controlled_sdk",
                    "ws_endpoint_discovery": "not_verified",
                    "ws_handshake": "not_verified",
                }
            ),
            window.window_id,
        ),
    )
    db.commit()


def guard_gateway(db: DB, window: GatewayWindow, create_workflow: bool) -> None:
    row = db.execute(
        """SELECT * FROM business.audit_events WHERE id=%s
        AND organization_id=%s AND shop_id=%s AND source='feishu_gateway'
        AND action='gateway_start_claimed' AND entity_type='gateway_window'
        AND clock_timestamp() < %s""",
        (window.window_id, window.organization_id, window.shop_id, window.expires_at),
    ).fetchone()
    if not row or row["after_state"] != {
        "expires_at": window.expires_at.isoformat(),
        "max_workflows": window.max_workflows,
        "max_callbacks": window.max_callbacks,
        "verification_mode": "controlled_sdk",
        "ws_endpoint_discovery": "not_verified",
        "ws_handshake": "not_verified",
    }:
        raise WebFailure("GATEWAY_WINDOW_CLOSED", 503)
    if create_workflow:
        # 单SDK callback loop+唯一App lease，原T1 transaction内才查/生成；重放不占新task。
        count: dict[str, Any] | None = db.execute(
            """SELECT count(DISTINCT e.task_id) AS n
            FROM business.inbox_events e JOIN business.p4_inbox_receipts r ON r.inbox_id=e.id
            WHERE e.organization_id=%s AND e.shop_id=%s AND e.source='feishu_business'
            AND e.task_id IS NOT NULL AND r.created_at>=%s""",
            (window.organization_id, window.shop_id, row["occurred_at"]),
        ).fetchone()
        if not count or count["n"] >= window.max_workflows:
            raise WebFailure("GATEWAY_WORKFLOW_CAP_EXHAUSTED", 503)
