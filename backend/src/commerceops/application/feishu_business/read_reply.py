"""两种显式读取的冻结回复；不是通用 IM 或业务任务 DTO。"""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.application.commerce.explanation_read import ExplanationRead
from commerceops.application.feishu_business.contracts import Contract
from commerceops.application.feishu_business.im_delivery import BusinessMessage
from commerceops.application.feishu_business.sdk_calls import SDKMethod
from commerceops.application.feishu_business.sdk_window import SDKWindow
from commerceops.application.replenishment.template_result import P3TemplateRead, SourceKind

READ_REPLY_CAPS: Mapping[SDKMethod, int] = MappingProxyType(
    {
        "auth.v3.tenant_access_token.internal": 1,
        "bot.v3.info": 1,
        "im.v1.message.create": 1,
    }
)


class ReadSource(Contract):
    source_kind: SourceKind
    source_task_id: UUID
    observation_id: UUID | None
    report_id: UUID
    snapshot_id: UUID
    facts_hash: str = Field(pattern="^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def observation_binding(self) -> Self:
        if (
            (self.source_kind == "p3_observation") != (self.observation_id is not None)
            or self.observation_id is not None
            and self.snapshot_id != self.observation_id
        ):
            raise ValueError("INVALID_READ_REPLY_SOURCE")
        return self


class ReadReplyPayload(Contract):
    schema_version: Literal["p4-read-reply-v1"] = "p4-read-reply-v1"
    kind: Literal["task_status", "explain_report"]
    task_id: UUID
    task_version: int = Field(ge=1)
    task_state: Literal[
        "queued",
        "analyzing",
        "awaiting_approval",
        "executing",
        "completed",
        "rejected",
        "expired",
        "needs_reapproval",
        "failed",
        "needs_attention",
    ]
    as_of: datetime
    read_code: Literal["OK", "NOT_READY"] = "OK"
    source: ReadSource | None
    explanation: P3TemplateRead | ExplanationRead | None

    @model_validator(mode="after")
    def exact_kind_and_refs(self) -> Self:
        if (
            self.as_of.utcoffset() != timedelta(0)
            or self.kind == "task_status"
            and (self.explanation is not None or self.read_code != "OK")
            or self.kind == "explain_report"
            and self.source is None
            or self.kind == "explain_report"
            and ((self.read_code == "OK") != (self.explanation is not None))
        ):
            raise ValueError("INVALID_READ_REPLY_KIND")
        if self.explanation is not None:
            if self.source is None:
                raise ValueError("INVALID_READ_REPLY_SOURCE")
            result = self.explanation.result
            if (
                result.reference_ids.report_id != str(self.source.report_id)
                or result.reference_ids.snapshot_id != str(self.source.snapshot_id)
                or result.facts_hash != self.source.facts_hash
            ):
                raise ValueError("INVALID_READ_REPLY_FACTS")
            if isinstance(self.explanation, P3TemplateRead):
                if (
                    self.explanation.task_id != str(self.task_id)
                    or self.explanation.source_task_id != str(self.source.source_task_id)
                    or self.explanation.source_kind != self.source.source_kind
                    or self.explanation.observation_id
                    != (str(self.source.observation_id) if self.source.observation_id else None)
                ):
                    raise ValueError("INVALID_READ_REPLY_TASK")
            elif self.explanation.task_id != str(self.source.source_task_id):
                raise ValueError("INVALID_READ_REPLY_TASK")
        return self

    def message(self, identifier: UUID, provider_uuid: UUID, chat: str) -> BusinessMessage:
        # 逐行原模板完整卡片，不通过截断适配 text 的 3000 字符上限。
        lines = [
            f"任务：{self.task_id}；版本：{self.task_version}；状态：{self.task_state}。",
            f"读取时间：{self.as_of.isoformat()}。",
        ]
        if self.source is not None:
            lines.append(
                f"报告：{self.source.report_id}；快照：{self.source.snapshot_id}；"
                f"事实 hash：{self.source.facts_hash}。"
            )
        if self.read_code == "NOT_READY":
            lines.append("这份报告的解释尚未就绪，请稍后再次查询。")
        if self.explanation is not None:
            lines.extend(
                [
                    self.explanation.result.summary,
                    *(f"SKU {line.sku_key}：{line.text}" for line in self.explanation.result.lines),
                ]
            )
        card = {
            "schema": "2.0",
            "body": {"elements": [{"tag": "markdown", "content": text} for text in lines]},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "内部演示 · 任务进度"
                    if self.kind == "task_status"
                    else "内部演示 · 报告解释",
                }
            },
        }
        return BusinessMessage(
            outbox_id=identifier,
            provider_uuid=provider_uuid,
            chat_id=chat,
            kind="interactive",
            card=card,
        )


class ReadReplyWindow(Contract):
    schema_version: Literal["p4-read-reply-window-v1"]
    window_id: UUID
    organization_id: UUID
    shop_id: UUID
    reply_id: UUID
    task_id: UUID
    expires_at: datetime
    enabled: bool = False
    method_caps: dict[str, int]

    def window(self, settings: BusinessSettings) -> SDKWindow:
        caps = READ_REPLY_CAPS
        if (
            (self.organization_id, self.shop_id) != (settings.organization_id, settings.shop_id)
            or self.method_caps != caps
            or any(type(n) is not int for n in self.method_caps.values())
            or self.expires_at.utcoffset() != timedelta(0)
            or not self.enabled
            or not datetime.now(UTC) < self.expires_at <= datetime.now(UTC) + timedelta(minutes=30)
        ):
            raise PermissionError("READ_REPLY_WINDOW_CLOSED")
        return SDKWindow(
            self.window_id,
            self.organization_id,
            self.shop_id,
            self.expires_at,
            caps,
            enabled=True,
            verification_mode="controlled_sdk",
        )
