"""Deterministic copy response JSON Schema and independent OpenAPI, from actual DTOs."""

import json
from pathlib import Path

from commerceops.application.knowledge_copy.http_models import (
    CandidateResponse,
    CopyError,
    DecisionResponse,
    UnknownCandidateResponse,
    UnknownDecisionResponse,
)
from commerceops.entrypoints.knowledge_copy_openapi import copy_openapi
from pydantic import TypeAdapter

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "docs/contracts/p6-copy-web-v1.schema.json"


def schema_bytes() -> bytes:
    schema = TypeAdapter(
        CandidateResponse
        | UnknownCandidateResponse
        | DecisionResponse
        | UnknownDecisionResponse
        | CopyError
    ).json_schema(mode="serialization")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "urn:commerceops:p6-copy-web-v1"
    schema["description"] = (
        "Generated Web response shapes; hashes, source replay and current authorization "
        "require the real DTO/store."
    )
    return encoded(schema)


def encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def main() -> None:
    TARGET.write_bytes(schema_bytes())
    raw = encoded(copy_openapi())
    (ROOT / "docs/contracts/p6-copy-web-v1.openapi.json").write_bytes(raw)
    (ROOT / "backend/src/commerceops/assets/p6-copy-web-v1.openapi.json").write_bytes(raw)


if __name__ == "__main__":
    main()
