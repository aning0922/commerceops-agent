"""纯入站字段校验；调用方仍须完成 SDK 鉴权、PG 身份查询与提交后响应。"""

import hashlib
import hmac
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

MAX_PAYLOAD_BYTES = 32_768
MAX_TEXT_LENGTH = 4_000
VALUE_FIELDS = frozenset(
    {
        "probe_id",
        "task_id",
        "approval_id",
        "plan_id",
        "plan_version",
        "plan_hash",
        "action",
        "acknowledged_assumption_keys",
        "nonce",
    }
)


class ContractCode(StrEnum):
    INVALID_PAYLOAD = "INVALID_PAYLOAD"
    APP_DENIED = "APP_DENIED"
    TENANT_DENIED = "TENANT_DENIED"
    IDENTITY_DENIED = "IDENTITY_DENIED"
    CHAT_DENIED = "CHAT_DENIED"
    IGNORED_BOT = "IGNORED_BOT"
    IGNORED_MESSAGE = "IGNORED_MESSAGE"
    IGNORED_NO_MENTION = "IGNORED_NO_MENTION"
    PLAN_MISMATCH = "PLAN_MISMATCH"
    ASSUMPTION_ACK_REQUIRED = "ASSUMPTION_ACK_REQUIRED"
    NONCE_MISMATCH = "NONCE_MISMATCH"
    EXPIRED = "EXPIRED"


class ProbeContractError(ValueError):
    """异常只携带固定分类，不能携带平台 body、token、nonce 或用户文本。"""

    def __init__(self, code: ContractCode):
        self.code = code
        super().__init__(code.value)


def _invalid() -> ProbeContractError:
    return ProbeContractError(ContractCode.INVALID_PAYLOAD)


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or any(type(key) is not str for key in value):
        raise _invalid()
    return value


def _string(value: object, limit: int = 256) -> str:
    if type(value) is not str or not value or len(value) > limit or value.strip() != value:
        raise _invalid()
    return value


def _uuid(value: object) -> str:
    text = _string(value)
    try:
        parsed = UUID(text)
    except ValueError:
        raise _invalid() from None
    if str(parsed) != text:
        raise _invalid()
    return text


def _keys(value: object) -> tuple[str, ...]:
    if type(value) is not list or len(value) > 20:
        raise _invalid()
    keys = tuple(_string(key, 160) for key in value)
    if len(set(keys)) != len(keys) or any(
        re.fullmatch(r"inbound_unknown_zero:[A-Za-z0-9_-]{1,100}", key) is None for key in keys
    ):
        raise _invalid()
    return tuple(sorted(keys))


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _invalid()
        result[key] = value
    return result


def decode_payload(payload: bytes) -> dict[str, Any]:
    """限定 JSON 字节数，拒绝重复键和非标准常量；不会回显解析输入。"""
    if type(payload) is not bytes or not payload or len(payload) > MAX_PAYLOAD_BYTES:
        raise _invalid()

    def reject_constant(value: str) -> None:
        raise _invalid()

    try:
        return _object(
            json.loads(payload, object_pairs_hook=_unique_object, parse_constant=reject_constant)
        )
    except (ValueError, UnicodeError, RecursionError):
        raise _invalid() from None


@dataclass(frozen=True)
class ProbePolicy:
    """受信配置；仅应用/租户/测试身份范围，不替代 PG principal.enabled/roles。"""

    app_id: str
    tenant_key: str
    bot_open_id: str
    allowed_open_ids: frozenset[str]
    allowed_group_chat_ids: frozenset[str]

    def __post_init__(self) -> None:
        for value in (self.app_id, self.tenant_key, self.bot_open_id):
            _string(value)
        if type(self.allowed_open_ids) is not frozenset or not self.allowed_open_ids:
            raise _invalid()
        if type(self.allowed_group_chat_ids) is not frozenset:
            raise _invalid()
        for value in self.allowed_open_ids | self.allowed_group_chat_ids:
            _string(value)
        if self.bot_open_id in self.allowed_open_ids:
            raise _invalid()


@dataclass(frozen=True)
class PlatformIdentity:
    app_id: str
    tenant_key: str
    open_id: str


def _envelope(payload: object, policy: ProbePolicy, event_type: str) -> tuple[str, dict[str, Any]]:
    root = _object(payload)
    if root.get("schema") != "2.0":
        raise _invalid()
    header = _object(root.get("header"))
    if header.get("event_type") != event_type:
        raise _invalid()
    if _string(header.get("app_id")) != policy.app_id:
        raise ProbeContractError(ContractCode.APP_DENIED)
    if _string(header.get("tenant_key")) != policy.tenant_key:
        raise ProbeContractError(ContractCode.TENANT_DENIED)
    return _string(header.get("event_id")), _object(root.get("event"))


def _identity(actor: dict[str, Any], open_id: object, policy: ProbePolicy) -> PlatformIdentity:
    if _string(actor.get("tenant_key")) != policy.tenant_key:
        raise ProbeContractError(ContractCode.TENANT_DENIED)
    subject = _string(open_id)
    if subject not in policy.allowed_open_ids:
        raise ProbeContractError(ContractCode.IDENTITY_DENIED)
    return PlatformIdentity(policy.app_id, policy.tenant_key, subject)


@dataclass(frozen=True)
class MessageProbe:
    event_id: str
    message_id: str
    chat_id: str
    chat_type: str
    identity: PlatformIdentity
    text: str = field(repr=False)

    def sanitized_payload(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "source_mode": "feishu_technical_probe",
            "model_mode": "not_used",
            "approval_mode": "not_applicable",
            "event_type": "im.message.receive_v1",
            "event_id": self.event_id,
            "message_id": self.message_id,
            "chat_id": self.chat_id,
            "chat_type": self.chat_type,
            "operator_open_id": self.identity.open_id,
            "text_sha256": hashlib.sha256(self.text.encode()).hexdigest(),
        }


def parse_message(payload: object, policy: ProbePolicy) -> MessageProbe:
    event_id, event = _envelope(payload, policy, "im.message.receive_v1")
    sender = _object(event.get("sender"))
    if sender.get("sender_type") == "bot":
        raise ProbeContractError(ContractCode.IGNORED_BOT)
    if sender.get("sender_type") != "user":
        raise _invalid()
    identity = _identity(sender, _object(sender.get("sender_id")).get("open_id"), policy)
    message = _object(event.get("message"))
    if message.get("message_type") != "text":
        raise ProbeContractError(ContractCode.IGNORED_MESSAGE)
    chat_id = _string(message.get("chat_id"))
    chat_type = _string(message.get("chat_type"))
    content = message.get("content")
    if type(content) is not str or len(content) > MAX_PAYLOAD_BYTES:
        raise _invalid()
    raw_text = decode_payload(content.encode()).get("text")
    if type(raw_text) is not str or len(raw_text) > MAX_TEXT_LENGTH:
        raise _invalid()
    text = raw_text.strip()
    if not text:
        raise ProbeContractError(ContractCode.IGNORED_MESSAGE)
    if chat_type == "group":
        if chat_id not in policy.allowed_group_chat_ids:
            raise ProbeContractError(ContractCode.CHAT_DENIED)
        mentions = message.get("mentions", [])
        if type(mentions) is not list or len(mentions) > 100:
            raise _invalid()
        matched_keys = []
        for raw_mention in mentions:
            mention = _object(raw_mention)
            if (
                mention.get("mentioned_type") == "bot"
                and _object(mention.get("id")).get("open_id") == policy.bot_open_id
                and mention.get("tenant_key") == policy.tenant_key
            ):
                key = _string(mention.get("key"))
                if re.fullmatch(r"@_user_[0-9]+", key) is None:
                    raise _invalid()
                matched_keys.append(key)
        if not matched_keys:
            raise ProbeContractError(ContractCode.IGNORED_NO_MENTION)
        # 只移除完整的本机器人 mention 标记，保留其他人的 @ 和文本中的相似前缀。
        for key in matched_keys:
            text = re.sub(re.escape(key) + r"(?![0-9])", "", text)
        text = text.strip()
        if not text:
            raise ProbeContractError(ContractCode.IGNORED_MESSAGE)
    elif chat_type != "p2p":
        raise _invalid()
    return MessageProbe(
        event_id, _string(message.get("message_id")), chat_id, chat_type, identity, text
    )


@dataclass(frozen=True)
class ProbePlan:
    """受信技术样例合同；未来从 PG 读取，不得从 callback value 构造 expected。"""

    probe_id: str
    task_id: str
    approval_id: str
    plan_id: str
    plan_version: int
    plan_hash: str
    required_assumption_keys: tuple[str, ...]
    nonce: str = field(repr=False)
    expires_at: datetime
    chat_id: str
    message_id: str

    def __post_init__(self) -> None:
        for value in (self.probe_id, self.task_id, self.approval_id, self.plan_id):
            _uuid(value)
        if type(self.plan_version) is not int or self.plan_version <= 0:
            raise _invalid()
        if re.fullmatch(r"[a-f0-9]{64}", _string(self.plan_hash)) is None:
            raise _invalid()
        if type(self.required_assumption_keys) is not tuple or not self.required_assumption_keys:
            raise _invalid()
        _keys(list(self.required_assumption_keys))
        if re.fullmatch(r"[A-Za-z0-9_-]{32,128}", _string(self.nonce)) is None:
            raise _invalid()
        if not isinstance(self.expires_at, datetime) or self.expires_at.utcoffset() is None:
            raise _invalid()
        _string(self.chat_id)
        _string(self.message_id)

    def callback_value(self, action: str) -> dict[str, Any]:
        if action not in ("approve_with_assumptions", "reject_assumptions"):
            raise _invalid()
        return {
            "probe_id": self.probe_id,
            "task_id": self.task_id,
            "approval_id": self.approval_id,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "plan_hash": self.plan_hash,
            "action": action,
            "acknowledged_assumption_keys": (
                sorted(self.required_assumption_keys)
                if action == "approve_with_assumptions"
                else []
            ),
            "nonce": self.nonce,
        }


@dataclass(frozen=True)
class CardProbe:
    event_id: str
    context_message_id: str
    chat_id: str
    identity: PlatformIdentity
    probe_id: str
    action: str
    acknowledged_assumption_keys: tuple[str, ...]
    value_sha256: str

    def sanitized_payload(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "source_mode": "feishu_technical_probe",
            "model_mode": "not_used",
            "approval_mode": "simulated_probe",
            "event_type": "card.action.trigger",
            "event_id": self.event_id,
            "context_message_id": self.context_message_id,
            "chat_id": self.chat_id,
            "operator_open_id": self.identity.open_id,
            "probe_id": self.probe_id,
            "action": self.action,
            "acknowledged_assumption_keys": list(self.acknowledged_assumption_keys),
            "value_sha256": self.value_sha256,
        }


def parse_card(
    payload: object, policy: ProbePolicy, expected: ProbePlan, now: datetime
) -> CardProbe:
    event_id, event = _envelope(payload, policy, "card.action.trigger")
    operator = _object(event.get("operator"))
    identity = _identity(operator, operator.get("open_id"), policy)
    context = _object(event.get("context"))
    chat_id = _string(context.get("open_chat_id"))
    if chat_id != expected.chat_id:
        raise ProbeContractError(ContractCode.CHAT_DENIED)
    message_id = _string(context.get("open_message_id"))
    if message_id != expected.message_id:
        raise ProbeContractError(ContractCode.PLAN_MISMATCH)
    action = _object(event.get("action"))
    if action.get("tag") != "button":
        raise _invalid()
    value = _object(action.get("value"))
    if set(value) != VALUE_FIELDS:
        raise _invalid()
    for key in ("probe_id", "task_id", "approval_id", "plan_id"):
        if _uuid(value.get(key)) != getattr(expected, key):
            raise ProbeContractError(ContractCode.PLAN_MISMATCH)
    if type(value.get("plan_version")) is not int or value["plan_version"] <= 0:
        raise _invalid()
    if (
        value["plan_version"] != expected.plan_version
        or value.get("plan_hash") != expected.plan_hash
    ):
        raise ProbeContractError(ContractCode.PLAN_MISMATCH)
    nonce = _string(value.get("nonce"))
    if re.fullmatch(r"[A-Za-z0-9_-]{32,128}", nonce) is None:
        raise _invalid()
    if not hmac.compare_digest(nonce, expected.nonce):
        raise ProbeContractError(ContractCode.NONCE_MISMATCH)
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise _invalid()
    if now >= expected.expires_at:
        raise ProbeContractError(ContractCode.EXPIRED)
    decision = _string(value.get("action"))
    keys = _keys(value.get("acknowledged_assumption_keys"))
    if decision == "approve_with_assumptions":
        if keys != tuple(sorted(expected.required_assumption_keys)):
            raise ProbeContractError(ContractCode.ASSUMPTION_ACK_REQUIRED)
    elif decision == "reject_assumptions":
        if keys:
            raise ProbeContractError(ContractCode.ASSUMPTION_ACK_REQUIRED)
    else:
        raise ProbeContractError(ContractCode.ASSUMPTION_ACK_REQUIRED)
    canonical_value = {**value, "acknowledged_assumption_keys": list(keys)}
    value_hash = hashlib.sha256(
        json.dumps(
            canonical_value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()
    return CardProbe(
        event_id, message_id, chat_id, identity, expected.probe_id, decision, keys, value_hash
    )
