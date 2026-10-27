"""正式F02发送的原入站/候选/参数来源核验；无SDK、Task写入或新调度。"""

import json
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid5

from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.application.feishu_business.clarification import F02Candidate, F02Message
from commerceops.application.feishu_business.f02_window import F02Window, F02WorkerWindow
from commerceops.application.feishu_business.gateway_window import GatewayWindow
from commerceops.application.replenishment.contracts import WooCreateParameters
from commerceops.application.replenishment.nl_preflight import WooSource
from commerceops.infrastructure.commerce_sources import (
    CommerceSourceFiles,
    resolve_woo_source_async,
)
from commerceops.infrastructure.feishu_gateway_window import claimed_state


async def trusted_f02_gateway(
    db: Any,
    window: F02WorkerWindow,
    app_id: str,
    tenant_key: str,
    *,
    commerce_sources: CommerceSourceFiles | None = None,
) -> dict[str, Any]:
    cursor = await db.execute(
        """SELECT a.after_state,a.occurred_at FROM business.audit_events a
        JOIN business.organizations o ON o.id=a.organization_id
        JOIN business.shops s ON s.organization_id=o.id AND s.id=%s
        WHERE a.id=%s AND a.organization_id=%s AND a.source='feishu_gateway'
        AND a.action='gateway_start_claimed' AND a.entity_type='gateway_window'
        AND o.feishu_app_id=%s AND o.feishu_tenant_key=%s
        AND ((s.adapter_kind='mock' AND s.environment IN ('test','mock')
         AND a.after_state#>>'{parameters,source_mode}'='mock') OR
         (s.adapter_kind='woocommerce_test' AND s.environment='test'
         AND a.after_state#>>'{parameters,source_mode}'='woocommerce_test'))
        AND NOT EXISTS(SELECT 1 FROM business.audit_events e
        WHERE e.organization_id=a.organization_id AND e.source='feishu_gateway'
        AND e.action='termination_confirmed' AND e.entity_type='gateway_runtime'
        AND e.entity_id=a.entity_id)""",
        (
            window.shop_id,
            window.gateway_window_id,
            window.organization_id,
            app_id,
            tenant_key,
        ),
    )
    claim = await cursor.fetchone()
    if not claim:
        raise PermissionError("F02_GATEWAY_SCOPE_REQUIRED")
    gateway = GatewayWindow.model_validate_json(
        json.dumps({k: claim["after_state"].get(k) for k in GatewayWindow.model_fields})
    )
    if (
        claim["after_state"] != claimed_state(gateway)
        or not gateway.active()
        or (gateway.window_id, gateway.organization_id, gateway.shop_id)
        != (window.gateway_window_id, window.organization_id, window.shop_id)
        or window.expires_at > gateway.expires_at
    ):
        raise PermissionError("F02_GATEWAY_SCOPE_REQUIRED")
    if isinstance(gateway.parameters, WooCreateParameters):
        await resolve_woo_source_async(
            db,
            commerce_sources,
            window.organization_id,
            window.shop_id,
            expected_version=gateway.parameters.source_config_version,
        )
    return cast(dict[str, Any], claim)


async def selected_f02_reply(
    db: Any,
    settings: BusinessSettings,
    window: F02WorkerWindow,
    *,
    commerce_sources: CommerceSourceFiles | None = None,
) -> F02Window | None:
    """只读当前Gateway明确选择的首个request及其新回复；不是org pending扫描。"""
    window.window(settings)
    claim = await trusted_f02_gateway(
        db,
        window,
        settings.app_id,
        settings.tenant_key,
        commerce_sources=commerce_sources,
    )
    cursor = await db.execute(
        """SELECT after_state FROM business.audit_events
        WHERE organization_id=%s AND source='feishu_clarification'
        AND action='reply_selected' AND entity_type='f02_gateway_reply' AND entity_id=%s
        AND occurred_at>=%s ORDER BY occurred_at,id LIMIT 1""",
        (window.organization_id, str(window.gateway_window_id), claim["occurred_at"]),
    )
    first = await cursor.fetchone()
    if first is None:
        return None

    def selection(value: dict[str, Any]) -> F02Window:
        if set(value) != {
            "gateway_window_id",
            "organization_id",
            "shop_id",
            "request_id",
            "reply_id",
            "inbox_id",
            "round",
            "payload_hash",
        } or any(
            value[k] != str(getattr(window, k))
            for k in ("gateway_window_id", "organization_id", "shop_id")
        ):
            raise PermissionError("F02_SELECTION_SCOPE_REQUIRED")
        return F02Window.model_validate_json(
            json.dumps(
                {**window.model_dump(mode="json"), **value, "schema_version": "p4-f02-window-v1"}
            )
        )

    original = selection(first["after_state"])
    cursor = await db.execute(
        """SELECT a.after_state FROM business.audit_events a
        JOIN business.p4_clarification_replies r ON r.id::text=a.after_state->>'reply_id'
        AND r.organization_id=a.organization_id AND r.request_id=%s
        WHERE a.organization_id=%s AND a.source='feishu_clarification'
        AND a.action='reply_selected' AND a.entity_type='f02_gateway_reply' AND a.entity_id=%s
        AND a.occurred_at>=%s AND r.status IN ('pending','sending')
        ORDER BY a.occurred_at,a.id LIMIT 1""",
        (
            original.request_id,
            window.organization_id,
            str(window.gateway_window_id),
            claim["occurred_at"],
        ),
    )
    selected = await cursor.fetchone()
    if selected is None:
        return None
    result = selection(selected["after_state"])
    if result.request_id != original.request_id:
        raise PermissionError("F02_SELECTION_SCOPE_REQUIRED")
    return result


async def trusted_f02_source(
    db: Any,
    row: dict[str, Any],
    current: dict[str, Any],
    window: F02Window,
    *,
    commerce_sources: CommerceSourceFiles | None = None,
) -> bool:
    """与原轮次/权限核验一起在发送事务中调用，preflight也调用相同核验。"""
    claim = await trusted_f02_gateway(
        db,
        window,
        current["app_id"],
        current["tenant_key"],
        commerce_sources=commerce_sources,
    )
    payload = F02Candidate.model_validate_json(json.dumps(row["frozen_payload"]))
    F02Message(
        reply_id=row["id"],
        provider_uuid=row["provider_uuid"],
        chat_id=row["chat_id"],
        candidate=payload,
        payload_hash=row["frozen_payload_hash"],
    )
    candidate = F02Candidate.model_validate_json(json.dumps(current["candidate"]))
    parameters = claim["after_state"]["parameters"]
    if candidate.source.source_mode != parameters["source_mode"]:
        return False
    if isinstance(candidate.source, WooSource):
        if candidate.source.source_config_version != parameters["source_config_version"]:
            return False
        _, actual = await resolve_woo_source_async(
            db,
            commerce_sources,
            window.organization_id,
            window.shop_id,
            expected_version=candidate.source.source_config_version,
        )
        if (
            candidate.window.start,
            candidate.window.end,
            candidate.window.timezone,
            candidate.window.as_of,
        ) != (actual.window.start, actual.window.end, actual.timezone, actual.business_now):
            return False
    if (
        row["identity_provider"] != "feishu"
        or (row["organization_id"], row["shop_id"], row["request_id"], row["id"])
        != (window.organization_id, window.shop_id, window.request_id, window.reply_id)
        or row["round"] != window.round
        or row["inbox_id"] != window.inbox_id
        or row["frozen_payload_hash"] != window.payload_hash
        or candidate.request_id != window.request_id
        or candidate.round != window.round
        or candidate.scope.shop_id != window.shop_id
        or candidate.confirmation_hash() != current["candidate_hash"]
        or payload.confirmation_hash() != candidate.confirmation_hash()
        or current["request_key"] != uuid5(NAMESPACE_URL, f"p4-f02-t1:{window.request_id}")
        or current["context"]
        != {k: candidate.model_dump(mode="json")[k] for k in ("source", "window", "scope")}
    ):
        return False

    async def inbox(identifier: Any) -> dict[str, Any] | None:
        cursor = await db.execute(
            """SELECT i.payload_hash,i.sanitized_payload,i.task_id,r.identity_id,r.result
            FROM business.inbox_events i JOIN business.p4_inbox_receipts r ON r.inbox_id=i.id
            WHERE i.id=%s AND i.organization_id=%s AND i.shop_id=%s AND i.app_id=%s
            AND i.tenant_key=%s AND i.source='feishu_business'""",
            (
                identifier,
                current["organization_id"],
                current["shop_id"],
                current["app_id"],
                current["tenant_key"],
            ),
        )
        return cast(dict[str, Any] | None, await cursor.fetchone())

    def same_actor(receipt: dict[str, Any] | None) -> bool:
        return bool(
            receipt
            and receipt["identity_id"] == current["identity_id"]
            and receipt["sanitized_payload"].get("principal_id") == str(current["principal_id"])
            and receipt["sanitized_payload"].get("auth_version") == current["auth_version"]
            and receipt["sanitized_payload"].get("chat_id") == current["chat_id"]
            and receipt["sanitized_payload"].get("chat_type") == current["chat_type"]
            and receipt["result"].get("clarification_id") == str(current["id"])
        )

    origin = await inbox(current["origin_inbox_id"])
    reply = await inbox(row["inbox_id"])
    if (
        not same_actor(origin)
        or origin is None
        or origin["payload_hash"] != current["source_hash"]
        or origin["task_id"] is not None
        or origin["result"].get("round") != 1
        or not same_actor(reply)
        or reply is None
        or reply["result"].get("reply_id") != str(row["id"])
        or reply["result"].get("round") != window.round
        or reply["result"].get("candidate_hash") != candidate.confirmation_hash()
        or reply["task_id"] != (current["task_id"] if payload.kind == "created" else None)
    ):
        return False
    cursor = await db.execute(
        """SELECT after_state FROM business.audit_events
        WHERE organization_id=%s AND source='feishu_clarification' AND action='candidate_frozen'
        AND entity_id=%s AND after_state->>'candidate_hash'=%s""",
        (current["organization_id"], str(current["id"]), current["candidate_hash"]),
    )
    frozen = await cursor.fetchall()
    if len(frozen) != 1 or frozen[0]["after_state"].get("candidate") != candidate.model_dump(
        mode="json"
    ):
        return False
    for key, source in candidate.parameter_sources.items():
        receipt = await inbox(source.inbox_id)
        if (
            not same_actor(receipt)
            or receipt is None
            or receipt["sanitized_payload"].get("text_sha256") != source.text_hash
            or receipt["result"].get("clarification", {}).get("parameters", {}).get(key)
            != candidate.parameters[key]
            or receipt["result"].get("clarification", {}).get("parameter_sources", {}).get(key)
            != source.model_dump(mode="json")
        ):
            return False
    return True
