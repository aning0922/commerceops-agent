"""Registry/export and independent digest boundaries only; no PG facts are fabricated."""

import copy
import json
from pathlib import Path
from uuid import uuid4

import pytest

from .final_facts import decode_subjects, effect_digest, preview_state
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


@pytest.mark.parametrize("rows", [[], [{"published": False}]])
@pytest.mark.parametrize("commitment", ["ACK_COMMITTED", "COMMITTED_READBACK"])
def test_committed_preview_readback_cannot_disappear_into_unknown(
    rows: list[dict[str, bool]],
    commitment: str,
) -> None:
    attempt = {"observations": ["ATTEMPT_STARTED", commitment]}
    original = copy.deepcopy(attempt)
    with pytest.raises(ValueError, match="FINAL_PUBLISHED_PREVIEW_READBACK_MISSING"):
        preview_state(attempt, rows)
    assert attempt == original


def test_unconfirmed_preview_unknown_and_actual_published_stay_distinct() -> None:
    attempt = {"observations": ["ATTEMPT_STARTED", "ACK_UNKNOWN", "UNKNOWN_READBACK"]}
    assert preview_state({"observations": ["ATTEMPT_STARTED", "ACK_OK"]}, []) == "UNKNOWN"
    assert preview_state(attempt, []) == "UNKNOWN"
    assert preview_state(attempt, [{"published": False}]) == "UNKNOWN"
    assert (
        preview_state({"observations": ["COMMITTED_READBACK"]}, [{"published": True}])
        == "PUBLISHED"
    )
