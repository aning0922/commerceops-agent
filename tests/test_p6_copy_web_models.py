"""DTO/asset truth and structural cases for an independent JSON Schema engine."""

import copy
import json
from importlib.resources import files
from typing import Any
from uuid import UUID

import pytest
from commerceops.application.knowledge_copy.http_models import (
    COPY_ERROR_CODES,
    CandidateResponse,
    CopyError,
    DecisionResponse,
    UnknownCandidateResponse,
    UnknownDecisionResponse,
)
from commerceops.entrypoints.knowledge_copy_http import copy_error_response
from commerceops.entrypoints.knowledge_copy_openapi import (
    COPY_PATHS,
    copy_openapi,
    separate_copy_legacy,
)
from commerceops.entrypoints.web_openapi import export_web
from pydantic import TypeAdapter

from scripts.export_copy_schema import ROOT, TARGET, encoded, schema_bytes
from tests.test_p6_copy_drafts import review_command, sample_copy

pytestmark = pytest.mark.offline
RESPONSE: TypeAdapter[Any] = TypeAdapter(
    CandidateResponse
    | UnknownCandidateResponse
    | DecisionResponse
    | UnknownDecisionResponse
    | CopyError
)


def wire_cases() -> list[tuple[str, dict[str, Any], bool, bool]]:
    """name, wire body, Pydantic expectation, JSON-Schema structural expectation."""
    pending: dict[str, Any] = dict(
        schema_version="p6-copy-web-v1",
        data=dict(
            candidate=sample_copy().model_dump(mode="json"),
            state="awaiting_review",
            source_current=True,
            draft_id=None,
            publication_allowed=False,
        ),
    )
    cases: list[tuple[str, dict[str, Any], bool, bool]] = [("pending", pending, True, True)]
    for state, current, draft in (
        ("source_unavailable", False, None),
        ("saved", True, str(UUID(int=12))),
        ("saved", False, str(UUID(int=12))),
        ("rejected", True, None),
        ("rejected", False, None),
    ):
        value = copy.deepcopy(pending)
        value["data"].update(state=state, source_current=current, draft_id=draft)
        cases.append((state + str(current), value, True, True))
    command = review_command()
    unknown = dict(
        schema_version="p6-copy-web-v1",
        data=dict(state="UNKNOWN", request_key=str(command.request_key), publication_allowed=False),
    )
    cases.append(("unknown_create", unknown, True, True))
    for state in ("saved", "rejected", "UNKNOWN"):
        receipt = dict(
            schema_version="p6-copy-receipt-v1",
            state=state,
            request_key=str(command.request_key),
            candidate_id=str(sample_copy().candidate_id),
            candidate_hash=command.candidate_hash,
            decision_id=str(UUID(int=11)) if state != "UNKNOWN" else None,
            draft_id=str(UUID(int=12)) if state == "saved" else None,
            publication_allowed=False,
        )
        cases.append(
            ("decision_" + state, dict(schema_version="p6-copy-web-v1", data=receipt), True, True)
        )
    error = json.loads(bytes(copy_error_response("COPY_VERSION_CHANGED", 409).body))
    cases.append(("error", error, True, True))
    for name, field, item in (
        ("missing_draft", "draft_id", "REMOVE"),
        ("unknown_state", "state", "published"),
        ("pending_draft", "draft_id", str(UUID(int=12))),
        ("wrong_current", "source_current", False),
        ("boolean_number", "publication_allowed", 0),
        ("extra_approved", "approved", True),
    ):
        value = copy.deepcopy(pending)
        if item == "REMOVE":
            value["data"].pop(field)
        else:
            value["data"][field] = item
        cases.append((name, value, False, False))
    shape_changes: tuple[tuple[int, str, Any], ...] = (
        (6, "draft_id", str(UUID(int=12))),
        (7, "draft_id", None),
        (9, "decision_id", str(UUID(int=11))),
        (0, "publication_allowed", True),
    )
    for index, field, replacement in shape_changes:
        value = copy.deepcopy(cases[index][1])
        value["data"][field] = replacement
        cases.append((f"invalid_shape_{index}_{field}", value, False, False))
    value = copy.deepcopy(pending)
    value["data"]["candidate"]["text"] = "unverified replacement"
    cases.append(("hash_formula_requires_DTO", value, False, True))
    value = copy.deepcopy(pending)
    value["data"]["candidate"]["publication_allowed"] = 0
    cases.append(("nested_boolean_number", value, False, False))
    value = copy.deepcopy(error)
    value["error"]["code"] = "COPY_UNDECLARED"
    cases.append(("unknown_error_enum", value, False, False))
    return cases


@pytest.mark.parametrize("name,body,expected,_", wire_cases())
def test_response_wire_states_and_invalid_shapes(
    name: str, body: dict[str, Any], expected: bool, _: bool
) -> None:
    if expected:
        parsed = RESPONSE.validate_json(json.dumps(body))
        assert parsed.model_dump(mode="json") == body, name
    else:
        with pytest.raises(ValueError):
            RESPONSE.validate_json(json.dumps(body))


def test_assets_regenerate_exactly_and_error_codes_match_original_frozen_contract() -> None:
    assert TARGET.read_bytes() == schema_bytes()
    raw = encoded(copy_openapi())
    assert (ROOT / "docs/contracts/p6-copy-web-v1.openapi.json").read_bytes() == raw
    assert files("commerceops.assets").joinpath("p6-copy-web-v1.openapi.json").read_bytes() == raw
    old = json.loads(files("commerceops.assets").joinpath("p3-web-v1.openapi.json").read_text())
    assert COPY_ERROR_CODES == set(
        old["components"]["schemas"]["ErrorDetail"]["properties"]["code"]["enum"]
    )
    assert copy_openapi()["components"]["schemas"]["Error"] == old["components"]["schemas"]["Error"]


def test_copy_contract_is_closed_and_legacy_separation_keeps_unknown_paths_rejected() -> None:
    schema = copy_openapi()
    assert set(schema["paths"]) == COPY_PATHS
    separated = separate_copy_legacy(schema)
    assert not separated["paths"] and set(schema["paths"]) == COPY_PATHS
    export_web(separated)
    schema["paths"]["/api/v1/copy/unapproved"] = {"get": {"responses": {}}}
    with pytest.raises(ValueError, match="no approved contract"):
        export_web(separate_copy_legacy(schema))

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if "$ref" in value:
                ref = value["$ref"]
                assert ref.startswith("#/components/schemas/")
                assert ref.rsplit("/", 1)[1] in schema["components"]["schemas"]
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(schema)


@pytest.mark.parametrize(
    "internal,status,public",
    [
        ("COPY_VERSION_CHANGED", 409, "PLAN_CHANGED"),
        ("COPY_ALREADY_REVIEWED", 409, "DECISION_CONFLICT"),
        ("COPY_SOURCE_EXPIRED_OR_REVOKED", 409, "NOT_READY"),
        ("COPY_RECEIPT_UNAVAILABLE", 503, "SERVICE_UNAVAILABLE"),
        ("KNOWLEDGE_NOT_AVAILABLE", 403, "ACCESS_DENIED"),
        ("IDEMPOTENCY_CONFLICT", 409, "IDEMPOTENCY_CONFLICT"),
        ("UNKNOWN_INTERNAL_EXCEPTION_TEXT", 503, "SERVICE_UNAVAILABLE"),
    ],
)
def test_error_aliases_stay_in_frozen_enum(internal: str, status: int, public: str) -> None:
    result = copy_error_response(internal, status)
    parsed = CopyError.model_validate_json(bytes(result.body))
    assert result.status_code == status and parsed.error.code == public
    assert parsed.error.receipt is None and not parsed.error.retryable
