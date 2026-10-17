"""正式JSON2.0全计划披露，回调只含P3版本绑定输入；不发卡或改业务。"""

import re
from typing import Any

from commerceops.domain.commerce_values import facts_hash


def _literal(value: object) -> str:
    return re.sub(r"([\\`*_{}\[\]<>()#])", r"\\\1", str(value)).replace("\n", " ")


def build_business_card(
    content: dict[str, Any], approval: dict[str, Any], nonce: str
) -> dict[str, Any]:
    items = content.get("items", [])
    if (
        not content.get("disclosure_complete")
        or content.get("hard_blocks")
        or not 1 <= len(items) <= 20
        or content.get("item_count") != len(items)
        or content.get("plan_id") != str(approval["plan_id"])
        or content.get("plan_version") != approval["plan_version"]
        or facts_hash(content) != approval["plan_hash"]
    ):
        raise ValueError("CARD_DISCLOSURE_OR_BINDING_INVALID")
    if re.fullmatch(r"[A-Za-z0-9_-]{43}", nonce) is None:
        raise ValueError("CARD_NONCE_INVALID")
    keys = sorted(a["key"] for a in content["required_assumptions"])
    if len(keys) != len(set(keys)):
        raise ValueError("CARD_ASSUMPTIONS_INVALID")
    window, params, source = content["window"], content["parameters"], content["source"]
    lines = [
        "**仅创建内部补货工作项；不采购、不改真实库存。数据来源：Mock演示。**",
        f"任务：{content['task_id']} · 计划v{approval['plan_version']}",
        f"窗口：{window['start']} → {window['end']}",
        f"库存观测/采集：{source['collected_at']}",
        f"演示规则L/R/S：{params['L']}/{params['R']}/{params['S']} · {content['rule_version']}",
        f"期限：{content['expires_at']} · Hash：{approval['plan_hash']}",
        f"完整批准范围：{len(items)}项，{content['total_units']}单位",
    ]
    for number, item in enumerate(items, 1):
        inbound = (
            "未知，按0估算" if item["raw_inbound_units"] is None else str(item["raw_inbound_units"])
        )
        lines.append(
            f"{number}. {_literal(item['sku_label'])} · {_literal(item['sku_key'])}\n"
            f"建议{item['quantity']} · 风险{_literal(item['fact']['risk'])} · 在途{inbound}"
        )
    if keys:
        lines.append("**在途未知按0估算可能重复补货，必须联合确认本版本全部假设：**")
        lines.extend(_literal(key) for key in keys)

    def button(action: str, label: str, style: str) -> dict[str, Any]:
        return {
            "tag": "button",
            "type": style,
            "text": {"tag": "plain_text", "content": label},
            "behaviors": [
                {
                    "type": "callback",
                    "value": {
                        "approval_id": str(approval["id"]),
                        "plan_id": str(approval["plan_id"]),
                        "plan_version": approval["plan_version"],
                        "plan_hash": approval["plan_hash"],
                        "action": action,
                        "acknowledged_assumption_keys": keys
                        if action == "approve_with_assumptions"
                        else [],
                        "nonce": nonce,
                    },
                }
            ],
        }

    return {
        "schema": "2.0",
        "config": {"update_multi": True},
        "header": {
            "title": {"tag": "plain_text", "content": "内部补货审批 · Mock演示"},
            "template": "orange",
        },
        "body": {
            "elements": [
                {"tag": "markdown", "content": "\n".join(lines)},
                button(
                    "approve_with_assumptions" if keys else "approve",
                    "确认在途未知按0估算并批准本版本" if keys else "批准创建内部补货工作项",
                    "primary",
                ),
                button(
                    "reject_assumptions" if keys else "reject",
                    "拒绝此假设并拒绝计划" if keys else "拒绝计划",
                    "danger",
                ),
            ]
        },
    }
