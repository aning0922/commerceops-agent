"""原页仅内存诊断，结构/格式相似永不替代原严格verified准入。"""

import copy
import json
from typing import Any

import pytest

from scripts.p4_acceptance import history_page_evidence
from tests.test_p4_history import page, request, row

pytestmark = pytest.mark.offline


@pytest.mark.parametrize(
    "content,structure",
    [
        (None, "CONTENT_NOT_STRING"),
        ({"text": "private-marker"}, "CONTENT_NOT_STRING"),
        ('{"text":', "JSON_INVALID"),
        ('{"text":"a","text":"b"}', "JSON_INVALID"),
        ('{"text":NaN}', "JSON_INVALID"),
        ('["private-marker"]', "JSON_NOT_OBJECT"),
        ('{"unrecognized":"private-marker"}', "JSON_NO_TEXT"),
        ('{"text":null}', "JSON_TEXT_NOT_STRING"),
        ('{"text":{}}', "JSON_TEXT_NOT_STRING"),
    ],
)
def test_structure_failures_have_fixed_categories_without_raw_content(
    content: Any, structure: str
) -> None:
    r = request()
    second = row(r, 1)
    second["body"]["content"] = content
    result = history_page_evidence(r, [page(r, [row(r), second]).record()])
    evidence = result["pages"][0]["item_evidence"][1]
    assert evidence["text_structure"] == structure
    assert evidence["expected_comparisons"][1] == dict(exact=None, difference="UNKNOWN")
    assert not result["complete_unique_pair"]
    assert "private-marker" not in json.dumps(result)


@pytest.mark.parametrize(
    "variant,difference",
    [
        ("exact", "EXACT"),
        ("edge", "EDGE_WHITESPACE_ONLY"),
        ("inner", "WHITESPACE_ONLY"),
        ("compatibility", "UNICODE_COMPATIBILITY_ONLY"),
        ("different", "CONTENT_DIFFERENT"),
    ],
)
def test_format_comparisons_never_relax_strict_pair_verification(
    variant: str, difference: str
) -> None:
    r = request()
    second = row(r, 1)
    text = r.expected_texts[1]
    if variant == "edge":
        text = "\t" + text + "\u3000"
    elif variant == "inner":
        text = text[:2] + "\u00a0\n" + text[2:]
    elif variant == "compatibility":
        text = "".join(chr(ord(c) + 0xFEE0) if "a" <= c <= "f" else c for c in text)
        # UUIDs may contain no a-f; a fullwidth digit always yields a compatibility-only change.
        text = "".join(chr(ord(c) + 0xFEE0) if c.isascii() and c.isdigit() else c for c in text)
    elif variant == "different":
        text += "private-difference-marker"
    second["body"]["content"] = json.dumps({"text": text})
    result = history_page_evidence(r, [page(r, [row(r), second]).record()])
    evidence = result["pages"][0]["item_evidence"][1]
    assert evidence["expected_comparisons"][1] == dict(
        exact=variant == "exact", difference=difference
    )
    assert evidence["text"]["characters"] == len(text)
    assert evidence["text"]["utf8_bytes"] == len(text.encode())
    assert result["complete_unique_pair"] is (variant == "exact")
    encoded = json.dumps(result)
    assert text not in encoded and "private-difference-marker" not in encoded


@pytest.mark.parametrize(
    "msg_type,kind",
    [("post", "RICH_TEXT"), ("image", "NON_TEXT"), ({"private": "marker"}, "UNKNOWN")],
)
def test_message_type_is_closed_and_does_not_expose_arbitrary_values(
    msg_type: Any, kind: str
) -> None:
    r = request()
    second = row(r, 1)
    second["msg_type"] = msg_type
    result = history_page_evidence(r, [page(r, [row(r), second]).record()])
    assert result["pages"][0]["item_evidence"][1]["message_kind"] == kind
    assert not result["complete_unique_pair"]


def test_wire_types_and_identity_time_conditions_are_safe_independent_observations() -> None:
    r = request()
    second = row(r, 1)
    second.update(
        chat_id="private-wrong-chat",
        create_time=True,
        update_time=42,
        deleted=True,
        updated=True,
        message_id="private-message-identifier",
    )
    second["sender"].update(
        id="private-subject", id_type="user_id", sender_type="app", tenant_key="private-tenant"
    )
    second["unknown"] = {"URL": "https://private.invalid/a", "token": "private-token"}
    result = history_page_evidence(r, [page(r, [row(r), second]).record()])
    evidence = result["pages"][0]["item_evidence"][1]
    assert evidence["wire_types"]["create_time"] == "BOOL"
    assert not evidence["create_time_format_valid"] and evidence["time_in_original_window"] is None
    assert evidence["chat_matches"] is False
    assert not any(evidence["sender_matches"].values())
    assert evidence["deleted"] is True and evidence["updated"] is True
    assert not result["complete_unique_pair"]
    serialized = json.dumps(result)
    for marker in [
        "private-wrong-chat",
        "private-message-identifier",
        "private-subject",
        "private-tenant",
        "https://private.invalid/a",
        "private-token",
    ]:
        assert marker not in serialized


@pytest.mark.parametrize("variant", ["nonobject", "missing-body", "bad-body", "surrogate"])
def test_unexpected_shapes_and_invalid_utf8_remain_safe_unknown(variant: str) -> None:
    r = request()
    second: Any = copy.deepcopy(row(r, 1))
    if variant == "nonobject":
        second = ["private-marker"]
    elif variant == "missing-body":
        second.pop("body")
    elif variant == "bad-body":
        second["body"] = ["private-marker"]
    else:
        second["body"]["content"] = json.dumps({"text": "\ud800"})
    result = history_page_evidence(r, [page(r, [row(r), second]).record()])
    evidence = result["pages"][0]["item_evidence"][1]
    assert evidence["diagnostic_only"]
    if variant == "surrogate":
        assert evidence["text"]["utf8_valid"] is False
        assert evidence["text"]["sha256"] is None
    assert not result["complete_unique_pair"]
    assert "private-marker" not in json.dumps(result)
