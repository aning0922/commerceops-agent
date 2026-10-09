"""脱敏合成样例；纯字段合同，不是 SDK、PG、真机卡片或正式 T3 证据。"""

import copy
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from commerceops.adapters.feishu.cards import build_probe_card
from commerceops.adapters.feishu.contracts import (
    MAX_PAYLOAD_BYTES,
    ContractCode,
    ProbeContractError,
    ProbePlan,
    ProbePolicy,
    decode_payload,
    parse_card,
    parse_message,
)

pytestmark = pytest.mark.offline
FIXTURES = Path(__file__).parent / "fixtures/feishu"
NOW = datetime(2026, 10, 8, 12, tzinfo=UTC)
POLICY = ProbePolicy(
    "probe-app",
    "probe-tenant",
    "probe-bot",
    frozenset({"probe-user-a", "probe-user-b"}),
    frozenset({"probe-group"}),
)


def fixture(name: str) -> dict[str, Any]:
    return decode_payload((FIXTURES / f"{name}.json").read_bytes())


def plan() -> ProbePlan:
    value = fixture("card_callback")["event"]["action"]["value"]
    return ProbePlan(
        probe_id=value["probe_id"],
        task_id=value["task_id"],
        approval_id=value["approval_id"],
        plan_id=value["plan_id"],
        plan_version=value["plan_version"],
        plan_hash=value["plan_hash"],
        required_assumption_keys=tuple(value["acknowledged_assumption_keys"]),
        nonce=value["nonce"],
        expires_at=NOW + timedelta(minutes=5),
        chat_id="probe-group",
        message_id="probe-card-message",
    )


def set_path(payload: dict[str, Any], path: str, value: object) -> None:
    target = payload
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"[]",
        b"null",
        b'{"header":1,"header":2}',
        b'{"value":NaN}',
        b'{"value":Infinity}',
        b"\xff",
        b" " * (MAX_PAYLOAD_BYTES + 1),
    ],
)
def test_wire_rejects_ambiguous_or_invalid_json_without_echo(payload: bytes) -> None:
    with pytest.raises(ProbeContractError, match="^INVALID_PAYLOAD$"):
        decode_payload(payload)


def test_message_filters_group_and_accepts_p2p_and_preserves_other_mentions() -> None:
    payload = fixture("message_group")
    payload["event"]["message"]["content"] = json.dumps(
        {"text": "@_user_1 技术探针 @_user_12 @_user_2"}
    )
    parsed = parse_message(payload, POLICY)
    assert parsed.text == "技术探针 @_user_12 @_user_2"
    assert parsed.identity.open_id == "probe-user-a"
    assert "text" not in parsed.sanitized_payload()
    assert parsed.text not in repr(parsed)
    message = payload["event"]["message"]
    message["chat_type"] = "p2p"
    message["chat_id"] = "probe-private-chat"
    message.pop("mentions")
    assert parse_message(payload, POLICY).chat_type == "p2p"


@pytest.mark.parametrize(
    "path,value,code",
    [
        ("schema", "1.0", ContractCode.INVALID_PAYLOAD),
        ("header.app_id", "other-app", ContractCode.APP_DENIED),
        ("header.tenant_key", "other-tenant", ContractCode.TENANT_DENIED),
        ("header.event_id", 1, ContractCode.INVALID_PAYLOAD),
        ("event.sender.sender_type", "bot", ContractCode.IGNORED_BOT),
        ("event.sender.sender_type", "unknown", ContractCode.INVALID_PAYLOAD),
        ("event.sender.tenant_key", "other-tenant", ContractCode.TENANT_DENIED),
        ("event.sender.sender_id.open_id", "outsider", ContractCode.IDENTITY_DENIED),
        ("event.message.chat_id", "other-group", ContractCode.CHAT_DENIED),
        ("event.message.message_type", "image", ContractCode.IGNORED_MESSAGE),
        ("event.message.mentions", [], ContractCode.IGNORED_NO_MENTION),
        ("event.message.message_id", None, ContractCode.INVALID_PAYLOAD),
        ("event.message.content", "broken-json", ContractCode.INVALID_PAYLOAD),
    ],
)
def test_message_adversarial_fields(path: str, value: object, code: ContractCode) -> None:
    payload = fixture("message_group")
    set_path(payload, path, value)
    with pytest.raises(ProbeContractError) as caught:
        parse_message(payload, POLICY)
    assert caught.value.code == code
    assert str(caught.value) == code.value


def test_display_name_or_wrong_bot_identity_cannot_satisfy_mention() -> None:
    payload = fixture("message_group")
    mention = payload["event"]["message"]["mentions"][0]
    mention["id"]["open_id"] = "different-bot"
    mention["name"] = POLICY.bot_open_id
    with pytest.raises(ProbeContractError, match="IGNORED_NO_MENTION"):
        parse_message(payload, POLICY)


def test_card_roundtrip_complete_keys_and_reject_has_no_ack() -> None:
    expected = plan()
    card = build_probe_card(expected)
    assert card["schema"] == "2.0"
    assert card["config"]["update_multi"] is True
    assert "elements" not in card
    elements = card["body"]["elements"]
    assert "不创建补货项" in elements[0]["content"]
    payload = fixture("card_callback")
    for button in elements[1:]:
        payload["event"]["action"]["value"] = button["behaviors"][0]["value"]
        parsed = parse_card(payload, POLICY, expected, NOW)
        assert parsed.action == button["behaviors"][0]["value"]["action"]
        assert bool(parsed.acknowledged_assumption_keys) == (
            parsed.action == "approve_with_assumptions"
        )


@pytest.mark.parametrize(
    "path,value,code",
    [
        ("event.operator.open_id", "outsider", ContractCode.IDENTITY_DENIED),
        ("event.operator.tenant_key", "other-tenant", ContractCode.TENANT_DENIED),
        ("event.context.open_chat_id", "other-group", ContractCode.CHAT_DENIED),
        ("event.context.open_message_id", "other-card", ContractCode.PLAN_MISMATCH),
        ("event.action.tag", "input", ContractCode.INVALID_PAYLOAD),
        ("event.action.value", "not-an-object", ContractCode.INVALID_PAYLOAD),
        ("event.action.value.plan_version", True, ContractCode.INVALID_PAYLOAD),
        ("event.action.value.plan_version", "1", ContractCode.INVALID_PAYLOAD),
        ("event.action.value.plan_version", 2, ContractCode.PLAN_MISMATCH),
        ("event.action.value.plan_hash", "b" * 64, ContractCode.PLAN_MISMATCH),
        ("event.action.value.nonce", "x" * 32, ContractCode.NONCE_MISMATCH),
        ("event.action.value.nonce", "非ASCII" * 10, ContractCode.INVALID_PAYLOAD),
        ("event.action.value.action", "approve", ContractCode.ASSUMPTION_ACK_REQUIRED),
        (
            "event.action.value.acknowledged_assumption_keys",
            [],
            ContractCode.ASSUMPTION_ACK_REQUIRED,
        ),
        (
            "event.action.value.acknowledged_assumption_keys",
            ["inbound_unknown_zero:probe_sku_1"],
            ContractCode.ASSUMPTION_ACK_REQUIRED,
        ),
        (
            "event.action.value.acknowledged_assumption_keys",
            ["inbound_unknown_zero:probe_sku_1"] * 2,
            ContractCode.INVALID_PAYLOAD,
        ),
    ],
)
def test_card_adversarial_fields(path: str, value: object, code: ContractCode) -> None:
    payload = fixture("card_callback")
    set_path(payload, path, value)
    with pytest.raises(ProbeContractError) as caught:
        parse_card(payload, POLICY, plan(), NOW)
    assert caught.value.code == code


def test_card_value_cannot_supply_identity_or_role_and_auth_precedes_expiry() -> None:
    payload = fixture("card_callback")
    payload["event"]["action"]["value"]["open_id"] = "probe-user-a"
    with pytest.raises(ProbeContractError, match="INVALID_PAYLOAD"):
        parse_card(payload, POLICY, plan(), NOW)
    payload["event"]["operator"]["open_id"] = "outsider"
    with pytest.raises(ProbeContractError, match="IDENTITY_DENIED"):
        parse_card(payload, POLICY, plan(), NOW + timedelta(hours=1))


def test_expiry_is_inclusive_and_naive_clock_rejected() -> None:
    expected = plan()
    payload = fixture("card_callback")
    with pytest.raises(ProbeContractError, match="EXPIRED"):
        parse_card(payload, POLICY, expected, expected.expires_at)
    with pytest.raises(ProbeContractError, match="INVALID_PAYLOAD"):
        parse_card(payload, POLICY, expected, NOW.replace(tzinfo=None))


def test_identity_is_from_operator_and_parsing_does_not_claim_idempotent_decision() -> None:
    payload = fixture("card_callback")
    original = copy.deepcopy(payload)
    first = parse_card(payload, POLICY, plan(), NOW)
    assert parse_card(payload, POLICY, plan(), NOW) == first
    assert payload == original
    payload["event"]["operator"]["open_id"] = "probe-user-b"
    second = parse_card(payload, POLICY, plan(), NOW)
    assert second.identity.open_id == "probe-user-b"
    # 两个允许用户均能通过字段校验；首次决定/冲突裁决是后续 PG 事务职责。
    assert first.identity != second.identity


def test_ack_order_is_semantic_set_but_reject_must_have_empty_keys() -> None:
    payload = fixture("card_callback")
    expected = plan()
    parsed = parse_card(payload, POLICY, expected, NOW)
    value = payload["event"]["action"]["value"]
    value["acknowledged_assumption_keys"].reverse()
    reordered = parse_card(payload, POLICY, expected, NOW)
    assert parsed.value_sha256 == reordered.value_sha256
    value["action"] = "reject_assumptions"
    with pytest.raises(ProbeContractError, match="ASSUMPTION_ACK_REQUIRED"):
        parse_card(payload, POLICY, expected, NOW)


@pytest.mark.parametrize("field", ["probe_id", "task_id", "approval_id", "plan_id"])
def test_every_plan_identity_is_bound_to_trusted_record(field: str) -> None:
    payload = fixture("card_callback")
    payload["event"]["action"]["value"][field] = "00000000-0000-4000-8000-000000000099"
    with pytest.raises(ProbeContractError, match="PLAN_MISMATCH"):
        parse_card(payload, POLICY, plan(), NOW)


def test_user_text_whitespace_is_normalized_and_mention_only_is_ignored() -> None:
    payload = fixture("message_group")
    payload["event"]["message"]["content"] = json.dumps({"text": "  @_user_1 技术探针  "})
    assert parse_message(payload, POLICY).text == "技术探针"
    payload["event"]["message"]["content"] = json.dumps({"text": "@_user_1"})
    with pytest.raises(ProbeContractError, match="IGNORED_MESSAGE"):
        parse_message(payload, POLICY)


def test_sanitized_payload_and_error_do_not_contain_platform_tokens_or_nonce() -> None:
    payload = fixture("card_callback")
    payload["header"]["token"] = "HEADER_CANARY_DO_NOT_OUTPUT"  # noqa: S105 - synthetic canary
    payload["event"]["token"] = "CALLBACK_CANARY_DO_NOT_OUTPUT"  # noqa: S105 - synthetic canary
    expected = plan()
    parsed = parse_card(payload, POLICY, expected, NOW)
    sanitized = json.dumps(parsed.sanitized_payload()) + repr(parsed) + repr(expected)
    assert "HEADER_CANARY" not in sanitized
    assert "CALLBACK_CANARY" not in sanitized
    assert expected.nonce not in sanitized
    assert "message_id" not in parsed.sanitized_payload()
    assert parsed.sanitized_payload()["context_message_id"] == "probe-card-message"
    payload["event"]["action"]["value"]["nonce"] = "DO_NOT_OUTPUT" * 3
    with pytest.raises(ProbeContractError) as caught:
        parse_card(payload, POLICY, expected, NOW)
    assert "DO_NOT_OUTPUT" not in str(caught.value)


@pytest.mark.parametrize(
    "changes", [{"plan_version": True}, {"expires_at": NOW.replace(tzinfo=None)}]
)
def test_trusted_plan_still_has_strict_configuration_validation(changes: dict[str, Any]) -> None:
    with pytest.raises(ProbeContractError, match="INVALID_PAYLOAD"):
        replace(plan(), **changes)
