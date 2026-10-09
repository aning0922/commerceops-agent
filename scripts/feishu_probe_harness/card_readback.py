"""从冻结runtime提取的受限技术核心；实际平台证据不覆盖公开适配版本。"""

from dataclasses import replace
from datetime import datetime
from typing import Any
from uuid import UUID

from commerceops.adapters.feishu.contracts import ProbePolicy, parse_card
from commerceops.adapters.feishu.repository import semantic_hash


def validate_rows(
    alias: Any, plan: Any, card: Any, receipts: Any, key_map: Any, identity: Any, bot_open_id: Any
) -> Any:
    members = {m["alias"]: m for m in identity["members"]}
    org, shop = (identity["organization"], identity["shop"])
    policy = ProbePolicy(
        org["feishu_app_id"],
        org["feishu_tenant_key"],
        bot_open_id,
        frozenset(members[a]["open_id"] for a in "ABC"),
        frozenset({plan.chat_id}),
    )
    expected_binding = {
        k: getattr(plan, k)
        for k in ("probe_id", "task_id", "approval_id", "plan_id", "plan_version", "plan_hash")
    }
    expected_binding["required_assumption_keys"] = list(plan.required_assumption_keys)
    if (
        card["id"] != UUID(plan.probe_id)
        or card["organization_id"] != UUID(org["id"])
        or card["shop_id"] != UUID(shop["id"])
        or (card["binding"] != expected_binding)
        or (card["nonce_sha256"] != plan.binding().nonce_sha256)
        or (card["expires_at"] != plan.expires_at)
        or (card["chat_id"] != plan.chat_id)
        or (card["send_status"] != "sent")
        or (not isinstance(card["send_uuid"], UUID))
        or (card["send_uuid"].int == 0)
        or (type(card["message_id"]) is not str)
        or (not card["message_id"])
        or (card["message_id"] == plan.message_id)
    ):
        raise ValueError()
    expected = replace(plan, message_id=card["message_id"])
    if alias == "c1":
        if (
            receipts
            or card["decision"] is not None
            or card["decided_by"] is not None
            or (card["decided_value_sha256"] is not None)
            or (card["decided_at"] is not None)
        ):
            raise ValueError()
        return dict(
            alias=alias,
            receipt_count=0,
            event_key_count=0,
            decision="none",
            full_card_binding_verified=True,
            C_zero_receipts_is_not_role_witness=True,
        )
    actor_alias, decision = (
        ("A", "approve_with_assumptions")
        if alias == "m3"
        else ("B", "approve_with_assumptions" if alias == "M1" else "reject_assumptions")
    )
    if (
        card["decided_by"] != UUID(members[actor_alias]["principal_id"])
        or card["decision"] != decision
        or (not isinstance(card["decided_at"], datetime))
        or (not card["decided_at"] < plan.expires_at)
        or (not 1 <= len(receipts) <= 64)
    ):
        raise ValueError()
    diagnostics = []
    first = 0
    ids = set()
    event_ids = set()
    for row in receipts:
        payload = row["sanitized_payload"]
        who = next((a for a in "AB" if members[a]["open_id"] == payload["operator_open_id"]), None)
        if (
            who is None
            or row["id"] in ids
            or row["organization_id"] != UUID(org["id"])
            or (row["shop_id"] != UUID(shop["id"]))
            or (row["app_id"] != policy.app_id)
            or (row["tenant_key"] != policy.tenant_key)
            or (row["probe_id"] != UUID(plan.probe_id))
            or (row["actor_id"] != UUID(members[who]["principal_id"]))
            or (row["kind"] != "card")
            or (row["message_id"] is not None)
            or (row["context_message_id"] != card["message_id"])
        ):
            raise ValueError()
        action = payload["action"]
        parsed = parse_card(
            dict(
                schema="2.0",
                header=dict(
                    app_id=policy.app_id,
                    tenant_key=policy.tenant_key,
                    event_id=payload["event_id"],
                    event_type="card.action.trigger",
                ),
                event=dict(
                    operator=dict(open_id=members[who]["open_id"], tenant_key=policy.tenant_key),
                    context=dict(
                        open_chat_id=expected.chat_id, open_message_id=expected.message_id
                    ),
                    action=dict(tag="button", value=expected.callback_value(action)),
                ),
            ),
            policy,
            expected,
            row["created_at"],
        )
        if parsed.sanitized_payload() != payload or semantic_hash(payload) != row["payload_sha256"]:
            raise ValueError()
        same = (
            who == actor_alias
            and action == decision
            and (parsed.value_sha256 == card["decided_value_sha256"])
        )
        result = row["result"]
        if result == "probe_recorded:" + decision:
            first += 1
            if not same:
                raise ValueError()
        elif result == "duplicate_decision:" + decision:
            if not same:
                raise ValueError()
        elif result == "decision_conflict":
            if same:
                raise ValueError()
        else:
            raise ValueError()
        keys = key_map[row["id"]]
        if (
            keys
            != [
                dict(
                    app_id=policy.app_id,
                    tenant_key=policy.tenant_key,
                    event_id=payload["event_id"],
                    receipt_id=row["id"],
                )
            ]
            or payload["event_id"] in event_ids
        ):
            raise ValueError()
        ids.add(row["id"])
        event_ids.add(payload["event_id"])
        diagnostics.append(
            dict(
                actor=who,
                action=action,
                result=result,
                full_value_semantic_hash_original_event_key_verified=True,
            )
        )
    if first != 1:
        raise ValueError()
    if alias == "m3" and (
        not (
            any(
                r["actor"] == "A" and r["result"] == "duplicate_decision:approve_with_assumptions"
                for r in diagnostics
            )
            and any(
                r["actor"] == "B"
                and r["action"] == "reject_assumptions"
                and (r["result"] == "decision_conflict")
                for r in diagnostics
            )
        )
    ):
        raise ValueError()
    return dict(
        alias=alias,
        receipt_count=len(receipts),
        event_key_count=len(receipts),
        decision=decision,
        full_card_binding_verified=True,
        diagnostics=diagnostics,
    )
