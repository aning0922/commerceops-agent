"""一次固定 p2p 原查询取回；API 来源与实时事件来源分别建模。"""

import base64
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.application.feishu_business.contracts import Contract
from commerceops.application.feishu_business.read_intents import parse_read_intent
from commerceops.application.feishu_business.sdk_calls import SDKMethod
from commerceops.application.feishu_business.sdk_window import SDKWindow
from commerceops.domain.commerce_values import facts_hash

ORIGINAL_START = datetime(2026, 10, 17, 13, 1, 45, tzinfo=UTC)
ORIGINAL_END = datetime(2026, 10, 17, 13, 5, 45, tzinfo=UTC)
HISTORY_CAPS: Mapping[SDKMethod, int] = MappingProxyType(
    {"auth.v3.tenant_access_token.internal": 1, "bot.v3.info": 1, "im.v1.message.list": 2}
)


class HistoryRecoveryRequest(Contract):
    schema_version: Literal["p4-original-query-history-v1"]
    recovery_id: UUID
    organization_id: UUID
    shop_id: UUID
    principal_id: UUID
    identity_id: UUID
    auth_version: int = Field(ge=1)
    app_id: str = Field(min_length=1, max_length=128)
    tenant_key: str = Field(min_length=1, max_length=128)
    open_id: str = Field(min_length=1, max_length=128)
    chat_id: str = Field(min_length=1, max_length=128)
    expected_texts: tuple[str, str]
    not_before: datetime
    expires_at: datetime
    enabled: bool = False

    @model_validator(mode="after")
    def fixed_intents_and_window(self) -> Self:
        intents = tuple(parse_read_intent(text) for text in self.expected_texts)
        if (
            any(x is None for x in intents)
            or tuple(x.kind for x in intents if x) != ("task_status", "explain_report")
            or self.not_before.utcoffset() != timedelta(0)
            or self.expires_at.utcoffset() != timedelta(0)
            or not 0 < (self.expires_at - self.not_before).total_seconds() <= 120
        ):
            raise ValueError("HISTORY_FIXED_CONTRACT_INVALID")
        return self

    def window(self, settings: BusinessSettings) -> SDKWindow:
        if (
            not self.enabled
            or not self.not_before <= datetime.now(UTC) < self.expires_at
            or (self.organization_id, self.shop_id, self.app_id, self.tenant_key)
            != (settings.organization_id, settings.shop_id, settings.app_id, settings.tenant_key)
            or self.open_id not in settings.allowed_open_ids
        ):
            raise PermissionError("HISTORY_WINDOW_CLOSED")
        return SDKWindow(
            self.recovery_id,
            self.organization_id,
            self.shop_id,
            self.expires_at,
            HISTORY_CAPS,
            enabled=True,
            verification_mode="controlled_sdk",
        )


def strict_json(body: bytes | str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("HISTORY_DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    try:
        return json.loads(
            body,
            object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except (ValueError, UnicodeError):
        raise ValueError("HISTORY_WIRE_JSON_INVALID") from None


@dataclass(frozen=True)
class HistoryPage:
    body: bytes
    http_status: int
    observed_at: datetime
    request_token: str | None

    def record(self) -> dict[str, Any]:
        return {
            "raw_body_b64": base64.b64encode(self.body).decode("ascii"),
            "raw_sha256": hashlib.sha256(self.body).hexdigest(),
            "http_status": self.http_status,
            "observed_at": self.observed_at.isoformat(),
            "request_token": self.request_token,
        }

    @classmethod
    def from_record(cls, value: dict[str, Any]) -> "HistoryPage":
        try:
            body = base64.b64decode(value["raw_body_b64"], validate=True)
            if hashlib.sha256(body).hexdigest() != value["raw_sha256"]:
                raise ValueError
            return cls(
                body,
                value["http_status"],
                datetime.fromisoformat(value["observed_at"]),
                value["request_token"],
            )
        except (ValueError, KeyError, TypeError):
            raise ValueError("HISTORY_PAGE_PROOF_INVALID") from None


@dataclass(frozen=True)
class VerifiedHistoryMessage:
    message_id: str
    text: str
    sent_at: datetime
    observed_at: datetime
    wire_row: dict[str, Any]
    page_sha256: str


def page_data(request: HistoryRecoveryRequest, page: HistoryPage) -> dict[str, Any]:
    if (
        type(page.http_status) is not int
        or not 200 <= page.http_status < 300
        or type(page.body) is not bytes
        or len(page.body) > 1024 * 1024
        or page.observed_at.utcoffset() != timedelta(0)
        or not request.not_before <= page.observed_at < request.expires_at
    ):
        raise ValueError("HISTORY_PAGE_RESPONSE_INVALID")
    body = strict_json(page.body)
    data = body.get("data") if type(body) is dict else None
    if (
        type(body) is not dict
        or type(body.get("code")) is not int
        or body["code"] != 0
        or type(data) is not dict
        or type(data.get("items")) is not list
        or len(data["items"]) > 50
        or type(data.get("has_more")) is not bool
        or data["has_more"]
        and (type(data.get("page_token")) is not str or not 1 <= len(data["page_token"]) <= 4096)
        or not data["has_more"]
        and data.get("page_token") not in (None, "")
    ):
        raise ValueError("HISTORY_PAGE_RESPONSE_INVALID")
    return data


def verify_pages(
    request: HistoryRecoveryRequest, pages: list[HistoryPage]
) -> tuple[VerifiedHistoryMessage, VerifiedHistoryMessage]:
    """完整分页后才选择两条；不要求列表总共只有两行。"""
    if not 1 <= len(pages) <= 2:
        raise ValueError("HISTORY_PAGE_LIMIT")
    token = None
    seen_tokens: set[str] = set()
    seen_messages: set[str] = set()
    matched: dict[str, list[VerifiedHistoryMessage]] = {text: [] for text in request.expected_texts}
    previous_time = ORIGINAL_START
    for index, page in enumerate(pages):
        if page.request_token != token:
            raise ValueError("HISTORY_PAGE_TOKEN_MISMATCH")
        data = page_data(request, page)
        if data["has_more"] != (index < len(pages) - 1):
            raise ValueError("HISTORY_PAGES_INCOMPLETE")
        token = data.get("page_token")
        if token:
            if token in seen_tokens:
                raise ValueError("HISTORY_PAGE_TOKEN_LOOP")
            seen_tokens.add(token)
        for row in data["items"]:
            if (
                type(row) is not dict
                or type(row.get("message_id")) is not str
                or not 1 <= len(row["message_id"]) <= 256
                or row["message_id"] in seen_messages
                or row.get("chat_id") != request.chat_id
                or type(row.get("create_time")) is not str
                or re.fullmatch(r"[1-9][0-9]{12}", row["create_time"]) is None
                or type(row.get("deleted")) is not bool
                or type(row.get("updated")) is not bool
            ):
                raise ValueError("HISTORY_MESSAGE_WIRE_INVALID")
            seen_messages.add(row["message_id"])
            sent = datetime.fromtimestamp(int(row["create_time"]) / 1000, UTC)
            if not previous_time <= sent <= ORIGINAL_END:
                raise ValueError("HISTORY_MESSAGE_TIME_INVALID")
            previous_time = sent
            sender = row.get("sender")
            if type(sender) is not dict:
                raise ValueError("HISTORY_SENDER_WIRE_INVALID")
            if row.get("msg_type") != "text" or row["deleted"]:
                continue
            content = row.get("body", {}).get("content") if type(row.get("body")) is dict else None
            if type(content) is not str:
                raise ValueError("HISTORY_TEXT_WIRE_INVALID")
            decoded = strict_json(content)
            if type(decoded) is not dict or type(decoded.get("text")) is not str:
                raise ValueError("HISTORY_TEXT_WIRE_INVALID")
            text = decoded["text"]
            if text not in matched:
                continue
            if (
                sender.get("id") != request.open_id
                or sender.get("id_type") != "open_id"
                or sender.get("sender_type") != "user"
                or sender.get("tenant_key") != request.tenant_key
                or row["updated"]
                or row.get("update_time") != row["create_time"]
            ):
                raise ValueError("HISTORY_ORIGINAL_SOURCE_MISMATCH")
            matched[text].append(
                VerifiedHistoryMessage(
                    row["message_id"],
                    text,
                    sent,
                    page.observed_at,
                    row,
                    hashlib.sha256(page.body).hexdigest(),
                )
            )
    if any(len(rows) != 1 for rows in matched.values()):
        raise ValueError("HISTORY_ORIGINAL_NOT_UNIQUE")
    return matched[request.expected_texts[0]][0], matched[request.expected_texts[1]][0]


def message_semantic(request: HistoryRecoveryRequest, text: str) -> str:
    return facts_hash({"open_id": request.open_id, "chat": request.chat_id, "text": text})
