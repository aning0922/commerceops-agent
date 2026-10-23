"""窄回复/完整模板/严格有限窗口；pure，无 IO 或 SDK。"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from commerceops.application.feishu_business.read_reply import ReadReplyPayload, ReadReplyWindow
from commerceops.application.feishu_business.sdk_window import SDKScope
from commerceops.infrastructure import p3_template_results as templates
from pydantic import ValidationError

from tests.test_model_explanation import report
from tests.test_p4_controlled_worker import configured
from tests.test_p4_template_results import Memory, binding

pytestmark = pytest.mark.offline


def payload(kind: str = "explain_report") -> dict[str, Any]:
    db, refs = Memory(), binding()
    identifier = asyncio.run(templates.freeze(db, refs, report()))
    assert db.row
    explanation = {
        "task_id": str(refs.p3_task_id),
        "source_task_id": str(refs.source_task_id),
        "source_kind": refs.source_kind,
        "observation_id": None,
        "explanation_id": str(identifier),
        "report_id": str(refs.report_id),
        "snapshot_id": str(refs.snapshot_id),
        "facts_hash": refs.facts_hash,
        "template_version": "p3-report-template-v1",
        "created_at": db.row["created_at"].isoformat(),
        "result": db.row["result"],
    }
    source = {
        key: explanation[key]
        for key in (
            "source_kind",
            "source_task_id",
            "observation_id",
            "report_id",
            "snapshot_id",
            "facts_hash",
        )
    }
    return {
        "kind": kind,
        "task_id": str(refs.p3_task_id),
        "task_version": 1,
        "task_state": "awaiting_approval",
        "as_of": datetime.now(UTC).isoformat(),
        "source": source,
        "explanation": explanation if kind == "explain_report" else None,
    }


@pytest.mark.parametrize("kind", ["task_status", "explain_report"])
def test_two_kind_original_complete_card_and_uuid(kind: str) -> None:
    body = ReadReplyPayload.model_validate_json(json.dumps(payload(kind)))
    request = body.message(uuid4(), uuid4(), "synthetic-chat")
    assert request.kind == "interactive" and request.card
    text = "\n".join(row["content"] for row in request.card["body"]["elements"])
    assert str(body.task_id) in text and body.as_of.isoformat() in text
    if body.explanation:
        assert all(
            line.text in text and line.sku_key in text for line in body.explanation.result.lines
        )


@pytest.mark.parametrize(
    "change", ["report", "snapshot", "facts", "task", "extra", "kind", "timezone"]
)
def test_reply_payload_rejects_wrong_explicit_refs_and_extra_shape(change: str) -> None:
    value = payload()
    if change in ("report", "snapshot"):
        value["source"][change + "_id"] = str(uuid4())
    elif change == "facts":
        value["source"]["facts_hash"] = "0" * 64
    elif change == "task":
        value["task_id"] = str(uuid4())
    elif change == "extra":
        value["job_id"] = str(uuid4())
    elif change == "kind":
        value["kind"] = "clarification"
    else:
        value["as_of"] = datetime.now(UTC).astimezone().replace(tzinfo=None).isoformat()
    with pytest.raises(ValidationError):
        ReadReplyPayload.model_validate_json(json.dumps(value))


def window() -> tuple[Any, dict[str, Any]]:
    settings, _, _ = configured()
    return settings, {
        "schema_version": "p4-read-reply-window-v1",
        "window_id": str(uuid4()),
        "organization_id": str(settings.organization_id),
        "shop_id": str(settings.shop_id),
        "reply_id": str(uuid4()),
        "task_id": str(uuid4()),
        "enabled": True,
        "expires_at": (datetime.now(UTC) + timedelta(minutes=2)).isoformat(),
        "method_caps": {
            "auth.v3.tenant_access_token.internal": 1,
            "bot.v3.info": 1,
            "im.v1.message.create": 1,
        },
    }


@pytest.mark.parametrize("change", ["disabled", "cap", "extra_method", "expiry", "long", "shop"])
def test_read_reply_window_missing_metadata_cap_or_expiry_zero_admission(change: str) -> None:
    settings, value = window()
    if change == "disabled":
        value["enabled"] = False
    elif change == "cap":
        value["method_caps"]["im.v1.message.create"] = 2
    elif change == "extra_method":
        value["method_caps"]["bitable.v1.app_table_record.create"] = 1
    elif change == "shop":
        value["shop_id"] = str(uuid4())
    else:
        value["expires_at"] = (
            datetime.now(UTC) + timedelta(minutes=-1 if change == "expiry" else 31)
        ).isoformat()
    candidate = ReadReplyWindow.model_validate_json(json.dumps(value))
    with pytest.raises(PermissionError):
        candidate.window(settings)


def test_sdk_scope_read_reply_requires_actual_task_and_original_subject() -> None:
    with pytest.raises(ValueError):
        SDKScope(uuid4(), None, "read_reply")
    assert SDKScope(uuid4(), uuid4(), "read_reply").kind == "read_reply"
    settings, value = window()
    sdk = ReadReplyWindow.model_validate_json(json.dumps(value)).window(settings)
    assert sum(sdk.caps.values()) == 3 and sdk.allows("im.v1.message.create")
