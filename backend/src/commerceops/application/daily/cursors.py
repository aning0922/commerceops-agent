"""有界证据页游标；签名绑定当前actor/auth/org/shop/report/hash及页种类。"""

import base64
import hashlib
import hmac
import json
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from commerceops.application.commerce.contracts import Digest
from commerceops.application.daily.contracts import DailyDTO
from commerceops.domain.commerce_values import canonical_bytes


class EvidenceContext(DailyDTO):
    actor_id: UUID
    auth_version: Annotated[int, Field(ge=1)]
    organization_id: UUID
    shop_id: UUID
    task_id: UUID
    report_id: UUID
    snapshot_id: UUID
    content_hash: Digest
    facts_hash: Digest
    question_id: UUID | None


class PageCursor(DailyDTO):
    schema_version: Literal["p6-daily-cursor-v1"]
    context: EvidenceContext
    offset: Annotated[int, Field(ge=1, le=30000)]


def encode_cursor(key: bytes, context: EvidenceContext, offset: int) -> str:
    if len(key) < 32:
        raise ValueError("DAILY_CURSOR_KEY_INVALID")
    cursor = PageCursor(schema_version="p6-daily-cursor-v1", context=context, offset=offset)
    raw = canonical_bytes(cursor.model_dump(mode="json"))
    signature = hmac.digest(key, b"p6-daily-evidence-v1\0" + raw, hashlib.sha256)
    return base64.urlsafe_b64encode(raw + signature).decode().rstrip("=")


def decode_cursor(key: bytes, context: EvidenceContext, value: str) -> int:
    try:
        if len(key) < 32 or len(value) > 4096:
            raise ValueError
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        body, signature = raw[:-32], raw[-32:]
        if not hmac.compare_digest(
            hmac.digest(key, b"p6-daily-evidence-v1\0" + body, hashlib.sha256), signature
        ):
            raise ValueError
        cursor = PageCursor.model_validate_json(body)
        if cursor.context != context or canonical_bytes(json.loads(body)) != body:
            raise ValueError
        return cursor.offset
    except (ValueError, TypeError):
        raise ValueError("DAILY_CURSOR_INVALID") from None
