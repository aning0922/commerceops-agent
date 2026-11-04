"""Registry/export and independent digest boundaries only; no PG facts are fabricated."""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from .final_facts import decode_subjects, effect_digest
from .subjects import frozen_subjects, registry

pytestmark = pytest.mark.offline


def test_final_export_preserves_original_key_history_and_rejects_drift(tmp_path: Path) -> None:
    context = {
        "tenant_id": str(uuid4()),
        "organization_id": str(uuid4()),
        "principal_id": str(uuid4()),
        "reset_epoch": 0,
        "auth_generation": 0,
    }
    shop, key = str(uuid4()), str(uuid4())
    registry(tmp_path, context, shop, operation="product_tags", key=key)
    registry(tmp_path, context, shop, operation="product_tags", key=key, state="ACK_UNKNOWN")
    value = decode_subjects(frozen_subjects(tmp_path))
    entry = next(iter(value["scopes"].values()))
    assert entry["operations"]["product_tags:" + key]["observations"] == [
        "ATTEMPT_STARTED",
        "ACK_UNKNOWN",
    ]
    entry["scope"]["reset_epoch"] = 1
    with pytest.raises(ValueError, match="IDENTITY_MISMATCH"):
        decode_subjects(json.dumps(value).encode())


def test_effect_summary_is_order_stable_and_binds_object_payload_and_operation() -> None:
    rows = [
        {"product_id": str(uuid4()), "payload_digest": "a" * 64},
        {"product_id": str(uuid4()), "payload_digest": "b" * 64},
    ]
    expected = effect_digest(rows, "import_confirm", "product_id")
    assert effect_digest(list(reversed(rows)), "import_confirm", "product_id") == expected
    assert effect_digest(rows, "product_tags", "product_id") != expected
    assert (
        effect_digest(
            [{**rows[0], "payload_digest": "c" * 64}, rows[1]], "import_confirm", "product_id"
        )
        != expected
    )
