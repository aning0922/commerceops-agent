"""固定取回合同与原始 API wire 校验；无身份、SDK 或数据库访问。"""

import copy
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from commerceops.application.feishu_business.history import (
    ORIGINAL_START,
    HistoryPage,
    HistoryRecoveryRequest,
    verify_pages,
)

pytestmark = pytest.mark.offline

NEXT_PAGE = "owned-next"
WRONG_PAGE = "wrong"


def request() -> HistoryRecoveryRequest:
    task, report = uuid4(), uuid4()
    start = datetime.now(UTC) - timedelta(seconds=1)
    return HistoryRecoveryRequest.model_validate_json(
        json.dumps(
            {
                "schema_version": "p4-original-query-history-v1",
                "recovery_id": str(uuid4()),
                "organization_id": str(uuid4()),
                "shop_id": str(uuid4()),
                "principal_id": str(uuid4()),
                "identity_id": str(uuid4()),
                "auth_version": 3,
                "app_id": "owned-app",
                "tenant_key": "owned-tenant",
                "open_id": "owned-A",
                "chat_id": "owned-p2p",
                "expected_texts": [f"查询任务{task}进度", f"解释任务{task}的报告{report}"],
                "not_before": start.isoformat(),
                "expires_at": (start + timedelta(seconds=120)).isoformat(),
                "enabled": True,
            }
        )
    )


def row(r: HistoryRecoveryRequest, index: int = 0) -> dict[str, Any]:
    timestamp = str(int((ORIGINAL_START + timedelta(seconds=10 + index)).timestamp()) * 1000)
    return {
        "message_id": f"owned-original-{index}",
        "chat_id": r.chat_id,
        "msg_type": "text",
        "create_time": timestamp,
        "update_time": timestamp,
        "deleted": False,
        "updated": False,
        "sender": {
            "id": r.open_id,
            "id_type": "open_id",
            "sender_type": "user",
            "tenant_key": r.tenant_key,
        },
        "body": {"content": json.dumps({"text": r.expected_texts[index]})},
    }


def page(
    r: HistoryRecoveryRequest,
    rows: list[dict[str, Any]],
    *,
    more: bool = False,
    token: str | None = None,
) -> HistoryPage:
    data = {"items": rows, "has_more": more}
    if more:
        data["page_token"] = NEXT_PAGE
    return HistoryPage(
        json.dumps({"code": 0, "data": data}).encode(), 200, datetime.now(UTC), token
    )


def test_complete_two_pages_with_unrelated_rows_keeps_only_original_two() -> None:
    r = request()
    unrelated = copy.deepcopy(row(r))
    unrelated["message_id"] = "unrelated"
    unrelated["body"]["content"] = json.dumps({"text": "其它消息"})
    p1 = page(r, [unrelated, row(r)], more=True)
    p2 = page(r, [row(r, 1)], token=NEXT_PAGE)
    found = verify_pages(r, [p1, p2])
    assert [x.message_id for x in found] == ["owned-original-0", "owned-original-1"]
    assert [x.text for x in found] == list(r.expected_texts)
    assert HistoryPage.from_record(p1.record()) == p1


@pytest.mark.parametrize("partial", [False, True])
def test_forensic_page_evidence_never_serializes_original_wire_or_tokens(partial: bool) -> None:
    from scripts.p4_acceptance import history_page_evidence

    r = request()
    first = row(r)
    private_marker = "owned-extra-wire-sensitive"
    first["extra"] = {"token": private_marker}
    p1 = page(r, [first], more=True)
    records = [p1.record()]
    if not partial:
        records.append(page(r, [row(r, 1)], token=NEXT_PAGE).record())
    result = history_page_evidence(r, records)
    assert result["complete_unique_pair"] is not partial
    assert result["pages"][0]["raw_sha256"] == p1.record()["raw_sha256"]
    assert result["pages"][0]["exact_text_counts"] == [1, 0]
    assert all(v["request_token_matches_previous"] for v in result["pages"])
    if not partial:
        assert (
            result["pages"][0]["response_token_sha256"]
            == result["pages"][1]["request_token_sha256"]
        )
    encoded = json.dumps(result)
    assert NEXT_PAGE not in encoded and private_marker not in encoded
    assert "raw_body_b64" not in encoded and "wire_row" not in encoded


def test_forensic_page_corruption_is_a_fixed_safe_failure() -> None:
    from scripts.p4_acceptance import history_page_evidence

    r = request()
    corrupted = page(r, [row(r), row(r, 1)]).record()
    corrupted["raw_sha256"] = "0" * 64
    result = history_page_evidence(r, [corrupted])
    assert result == {
        "complete_unique_pair": False,
        "pages": [],
        "originals": [],
        "failure": "P4A_HISTORY_PAGE_UNVERIFIED",
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("create_time", True),
        ("create_time", 1792242115000),
        ("create_time", "1792242115000.0"),
        ("updated", True),
        ("deleted", True),
        ("update_time", "0"),
        ("chat_id", "other-chat"),
        ("msg_type", "interactive"),
    ],
)
def test_malformed_or_changed_original_is_held(field: str, value: object) -> None:
    r = request()
    rows = [row(r), row(r, 1)]
    rows[0][field] = value
    with pytest.raises(ValueError):
        verify_pages(r, [page(r, rows)])


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "other-A"),
        ("id_type", "user_id"),
        ("sender_type", "app"),
        ("tenant_key", "other-tenant"),
    ],
)
def test_original_sender_requires_exact_current_contract(field: str, value: str) -> None:
    r = request()
    rows = [row(r), row(r, 1)]
    rows[0]["sender"][field] = value
    with pytest.raises(ValueError, match="SOURCE_MISMATCH"):
        verify_pages(r, [page(r, rows)])


def test_both_texts_not_enough_when_page_completeness_unknown() -> None:
    r = request()
    with pytest.raises(ValueError, match="INCOMPLETE"):
        verify_pages(r, [page(r, [row(r), row(r, 1)], more=True)])


@pytest.mark.parametrize(
    "variant",
    ["duplicate-id", "duplicate-text", "missing", "wrong-token", "third-page", "reversed"],
)
def test_ambiguity_or_incomplete_order_never_selects_latest(variant: str) -> None:
    r = request()
    a, b = row(r), row(r, 1)
    pages = [page(r, [a, b])]
    if variant == "duplicate-id":
        b["message_id"] = a["message_id"]
        pages = [page(r, [a, b])]
    if variant == "duplicate-text":
        c = copy.deepcopy(b)
        c["message_id"] = "third"
        c["body"]["content"] = a["body"]["content"]
        pages = [page(r, [a, b, c])]
    if variant == "missing":
        pages = [page(r, [a])]
    if variant == "wrong-token":
        pages = [page(r, [a], more=True), page(r, [b], token=WRONG_PAGE)]
    if variant == "third-page":
        pages = [
            page(r, [], more=True),
            page(r, [], more=True, token=NEXT_PAGE),
            page(r, [a, b], token=NEXT_PAGE),
        ]
    if variant == "reversed":
        pages = [page(r, [b, a])]
    with pytest.raises(ValueError):
        verify_pages(r, pages)


@pytest.mark.parametrize(
    "body",
    [
        b'{"code":0,"code":0,"data":{}}',
        b'{"code":false,"data":{}}',
        b'{"code":0,"data":{"items":[],"has_more":0}}',
        b"not json",
    ],
)
def test_raw_json_types_and_duplicate_keys_are_preserved(body: bytes) -> None:
    r = request()
    with pytest.raises(ValueError):
        verify_pages(r, [HistoryPage(body, 200, datetime.now(UTC), None)])


def test_observation_time_http_status_and_proof_hash_fail_closed() -> None:
    r = request()
    p = page(r, [row(r), row(r, 1)])
    for invalid in [
        replace(p, http_status=403),
        replace(p, http_status=True),
        replace(p, observed_at=r.expires_at),
        replace(p, observed_at=r.not_before - timedelta(seconds=1)),
    ]:
        with pytest.raises(ValueError):
            verify_pages(r, [invalid])
    stored = p.record()
    stored["raw_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        HistoryPage.from_record(stored)
