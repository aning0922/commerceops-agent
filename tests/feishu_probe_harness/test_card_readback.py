from dataclasses import asdict, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from commerceops.adapters.feishu.contracts import (
    ProbePolicy,
    parse_card,
)
from commerceops.adapters.feishu.repository import (
    semantic_hash,
)

from scripts.feishu_probe_harness import card_readback as leaf

from .support import identity_body, plan

pytestmark = pytest.mark.offline


def fixture() -> Any:
    identity = identity_body()
    members = {m["alias"]: m for m in identity["members"]}
    org, shop = (identity["organization"], identity["shop"])
    plans = {a: plan() for a in ("M1", "M2", "m3", "c1")}
    body = dict(
        identity=identity,
        C_child_only_allowlist_armed=True,
        bot_open_id="ou_synthetic_bot",
        plans={},
        prior_plans={},
    )
    cards: dict[Any, Any] = {}
    receipts: dict[Any, Any] = {}
    keys: dict[Any, Any] = {}
    for alias, p in plans.items():
        raw = asdict(p)
        raw["expires_at"] = p.expires_at.isoformat()
        (body["plans"] if alias in ("m3", "c1") else body["prior_plans"])[alias] = raw
        expected = replace(p, message_id="om_synthetic_" + alias)
        who, action = (
            ("A", "approve_with_assumptions")
            if alias == "m3"
            else ("B", "reject_assumptions" if alias == "M2" else "approve_with_assumptions")
        )
        policy = ProbePolicy(
            org["feishu_app_id"],
            org["feishu_tenant_key"],
            body["bot_open_id"],
            frozenset(m["open_id"] for m in members.values()),
            frozenset({p.chat_id}),
        )
        states = [] if alias == "c1" else [(who, action, "probe_recorded:" + action)]
        if alias == "m3":
            states.extend(
                [
                    ("A", action, "duplicate_decision:" + action),
                    ("B", "reject_assumptions", "decision_conflict"),
                ]
            )
        found: list[Any] = []
        for actor, act, result in states:
            at = datetime.now(UTC)
            payload = dict(
                schema="2.0",
                header=dict(
                    app_id=policy.app_id,
                    tenant_key=policy.tenant_key,
                    event_id=str(uuid4()),
                    event_type="card.action.trigger",
                ),
                event=dict(
                    operator=dict(open_id=members[actor]["open_id"], tenant_key=policy.tenant_key),
                    context=dict(
                        open_chat_id=expected.chat_id, open_message_id=expected.message_id
                    ),
                    action=dict(tag="button", value=expected.callback_value(act)),
                ),
            )
            parsed = parse_card(payload, policy, expected, at)
            sanitized = parsed.sanitized_payload()
            rid = uuid4()
            found.append(
                dict(
                    id=rid,
                    organization_id=UUID(org["id"]),
                    shop_id=UUID(shop["id"]),
                    app_id=policy.app_id,
                    tenant_key=policy.tenant_key,
                    probe_id=UUID(p.probe_id),
                    actor_id=UUID(members[actor]["principal_id"]),
                    kind="card",
                    message_id=None,
                    context_message_id=expected.message_id,
                    sanitized_payload=sanitized,
                    payload_sha256=semantic_hash(sanitized),
                    result=result,
                    created_at=at,
                )
            )
            keys[rid] = [
                dict(
                    app_id=policy.app_id,
                    tenant_key=policy.tenant_key,
                    event_id=sanitized["event_id"],
                    receipt_id=rid,
                )
            ]
        receipts[UUID(p.probe_id)] = found
        binding = {
            k: getattr(p, k)
            for k in ("probe_id", "task_id", "approval_id", "plan_id", "plan_version", "plan_hash")
        }
        binding["required_assumption_keys"] = list(p.required_assumption_keys)
        cards[UUID(p.probe_id)] = dict(
            id=UUID(p.probe_id),
            organization_id=UUID(org["id"]),
            shop_id=UUID(shop["id"]),
            binding=binding,
            nonce_sha256=p.binding().nonce_sha256,
            expires_at=p.expires_at,
            chat_id=p.chat_id,
            message_id=expected.message_id,
            send_uuid=uuid4(),
            send_status="sent",
            decision=action if found else None,
            decided_by=UUID(members[who]["principal_id"]) if found else None,
            decided_value_sha256=found[0]["sanitized_payload"]["value_sha256"] if found else None,
            decided_at=found[0]["created_at"] if found else None,
        )
    return (body, plans, cards, receipts, keys)


@pytest.mark.parametrize(
    "change",
    [
        "binding",
        "nonce",
        "target",
        "decision",
        "actor",
        "value_hash",
        "semantic_hash",
        "key",
        "C_receipt",
        "missing_first",
        "same_conflict",
        "missing_duplicate",
        "foreign_context",
    ],
)
def test_invalid_full_association_or_C_side_effect_rejected(change: Any) -> None:
    body, plans, cards, receipts, keys = fixture()
    p = plans["m3"]
    card = cards[UUID(p.probe_id)]
    rows = receipts[UUID(p.probe_id)]
    if change == "binding":
        card["binding"]["plan_version"] = 99
    elif change == "nonce":
        card["nonce_sha256"] = "0" * 64
    elif change == "target":
        card["shop_id"] = uuid4()
    elif change == "decision":
        card["decision"] = "reject_assumptions"
    elif change == "actor":
        rows[0]["actor_id"] = uuid4()
    elif change == "value_hash":
        rows[0]["sanitized_payload"]["value_sha256"] = "0" * 64
    elif change == "semantic_hash":
        rows[0]["payload_sha256"] = "0" * 64
    elif change == "key":
        keys[rows[0]["id"]].append(dict(keys[rows[0]["id"]][0]))
    elif change == "missing_first":
        rows.pop(0)
    elif change == "same_conflict":
        rows[1]["result"] = "decision_conflict"
    elif change == "missing_duplicate":
        rows.pop(1)
    elif change == "foreign_context":
        rows[0]["context_message_id"] = "foreign_synthetic"
    else:
        p = plans["c1"]
        card = cards[UUID(p.probe_id)]
        rows = [rows[0]]
    with pytest.raises(ValueError):
        leaf.validate_rows(
            "c1" if change == "C_receipt" else "m3",
            p,
            card,
            rows,
            keys,
            body["identity"],
            body["bot_open_id"],
        )
