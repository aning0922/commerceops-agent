"""生成 JSON2.0 技术卡片；没有 SDK 客户端、发送、审批提交或任务执行。"""

from typing import Any

from commerceops.adapters.feishu.contracts import ProbePlan


def build_probe_card(plan: ProbePlan) -> dict[str, Any]:
    keys = "\n".join(f"- `{key}`" for key in sorted(plan.required_assumption_keys))
    return {
        "schema": "2.0",
        "config": {"update_multi": True},
        "header": {
            "title": {"tag": "plain_text", "content": "CommerceOps 技术探针 · 模拟审批"},
            "template": "orange",
        },
        "body": {
            "elements": [
                {
                    "tag": "markdown",
                    "content": (
                        "**仅验证消息与回调合同，不创建补货项、不修改库存。**\n"
                        f"探针：{plan.probe_id}\n计划：{plan.plan_id}\n"
                        f"版本：{plan.plan_version}\nHash：{plan.plan_hash}\n"
                        f"有效期：{plan.expires_at.isoformat()}\n"
                        "技术样例假设：在途未知按 0 估算，可能造成重复补货。\n"
                        "确认动作必须覆盖下列全部确认键：\n" + keys
                    ),
                },
                {
                    "tag": "button",
                    "type": "primary",
                    "text": {
                        "tag": "plain_text",
                        "content": "模拟确认在途未知按 0 估算并批准本版本",
                    },
                    "behaviors": [
                        {
                            "type": "callback",
                            "value": plan.callback_value("approve_with_assumptions"),
                        }
                    ],
                },
                {
                    "tag": "button",
                    "type": "danger",
                    "text": {"tag": "plain_text", "content": "模拟拒绝此假设并拒绝计划"},
                    "behaviors": [
                        {"type": "callback", "value": plan.callback_value("reject_assumptions")}
                    ],
                },
            ]
        },
    }
