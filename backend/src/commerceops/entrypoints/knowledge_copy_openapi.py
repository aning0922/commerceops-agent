"""Independent K3 contract derived from real Web DTOs. No app/config/DB construction."""

import copy
import json
from importlib.resources import files
from typing import Any

from pydantic import BaseModel

from commerceops.application.knowledge_copy.commands import CreateCopy, ReviewCopy
from commerceops.application.knowledge_copy.http_models import (
    CandidateResponse,
    DecisionResponse,
    UnknownCandidateResponse,
    UnknownDecisionResponse,
)

BASE = "/api/v1/copy"
COPY_PATHS = frozenset(
    {
        BASE + "/candidates",
        BASE + "/candidates/{identifier}",
        BASE + "/candidates/{identifier}/review",
        BASE + "/candidates/{identifier}/review-receipts/{key}",
        BASE + "/candidate-requests/{key}",
    }
)


def _refs(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        ref = value.get("$ref", "")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            found.add(ref.rsplit("/", 1)[1])
        for item in value.values():
            found.update(_refs(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_refs(item))
    return found


def copy_openapi() -> dict[str, Any]:
    models: dict[str, Any] = {}
    for model in (
        CreateCopy,
        ReviewCopy,
        CandidateResponse,
        UnknownCandidateResponse,
        DecisionResponse,
        UnknownDecisionResponse,
    ):
        definition = model.model_json_schema(
            mode="validation" if model in (CreateCopy, ReviewCopy) else "serialization",
            ref_template="#/components/schemas/{model}",
        )
        for name, body in definition.pop("$defs", {}).items():
            if name in models and models[name] != body:
                raise ValueError("COPY_SCHEMA_NAME_CONFLICT")
            models[name] = body
        models[model.__name__] = definition
    legacy = json.loads(files("commerceops.assets").joinpath("p3-web-v1.openapi.json").read_text())
    pending = ["Error"]
    while pending:
        name = pending.pop()
        if name in models:
            continue
        models[name] = copy.deepcopy(legacy["components"]["schemas"][name])
        pending.extend(sorted(_refs(models[name]) - models.keys()))

    def response(name: str, description: str) -> dict[str, Any]:
        return {
            "description": description,
            "headers": {"Cache-Control": {"schema": {"type": "string", "const": "no-store"}}},
            "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{name}"}}},
        }

    def operation(
        operation_id: str,
        responses: dict[str, Any],
        *,
        request: type[BaseModel] | None = None,
        identifiers: tuple[str, ...] = (),
        receipt_hash: bool = False,
    ) -> dict[str, Any]:
        errors = {
            str(code): response("Error", "Fixed P3 error; no copy write retry or new key implied.")
            for code in (400, 401, 403, 404, 409, 415, 422, 429, 503)
        }
        parameters: list[dict[str, Any]] = [
            {
                "name": name,
                "in": "path",
                "required": True,
                "schema": {"type": "string", "format": "uuid"},
            }
            for name in identifiers
        ]
        if receipt_hash:
            parameters.append(
                {
                    "name": "candidate_hash",
                    "in": "query",
                    "required": True,
                    "schema": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                }
            )
        result: dict[str, Any] = {
            "operationId": operation_id,
            "security": [{"SessionCookie": []}],
            "parameters": parameters,
            "responses": errors | responses,
            "x-implementation-status": "isolated-router; main integration pending",
        }
        if request is not None:
            parameters.extend(
                [
                    {
                        "name": "Origin",
                        "in": "header",
                        "required": True,
                        "schema": {"type": "string"},
                    },
                    {
                        "name": "X-CSRF-Token",
                        "in": "header",
                        "required": True,
                        "schema": {"type": "string", "minLength": 1},
                    },
                ]
            )
            result["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{request.__name__}"}
                    }
                },
            }
        return result

    create = response("CandidateResponse", "Created candidate read after the create COMMIT.")
    create["content"]["application/json"]["schema"] = {
        "anyOf": [
            {"$ref": "#/components/schemas/CandidateResponse"},
            {"$ref": "#/components/schemas/UnknownCandidateResponse"},
        ]
    }
    reads = {
        "200": response(
            "CandidateResponse", "Current authorized candidate state; saved draft stays internal."
        ),
        "202": response(
            "UnknownCandidateResponse", "Original create key is UNKNOWN; GET only, never resend."
        ),
    }
    decisions = {
        "200": response(
            "DecisionResponse", "Confirmed original decision COMMIT (approve or reject)."
        ),
        "202": response(
            "UnknownDecisionResponse",
            "Original decision key is UNKNOWN; read receipt without POST.",
        ),
    }
    paths = {
        BASE + "/candidates": {
            "post": operation("p6CopyCreate", {"202": create}, request=CreateCopy)
        },
        BASE + "/candidates/{identifier}": {
            "get": operation("p6CopyRead", {"200": reads["200"]}, identifiers=("identifier",))
        },
        BASE + "/candidate-requests/{key}": {
            "get": operation("p6CopyCreateReceipt", reads, identifiers=("key",))
        },
        BASE + "/candidates/{identifier}/review": {
            "post": operation(
                "p6CopyReview", decisions, request=ReviewCopy, identifiers=("identifier",)
            )
        },
        BASE + "/candidates/{identifier}/review-receipts/{key}": {
            "get": operation(
                "p6CopyReviewReceipt",
                decisions,
                identifiers=("identifier", "key"),
                receipt_hash=True,
            )
        },
    }
    return {
        "openapi": "3.1.0",
        "info": {"title": "CommerceOps Internal Copy", "version": "p6-copy-web-v1"},
        "paths": paths,
        "components": {
            "schemas": models,
            "securitySchemes": copy.deepcopy(legacy["components"]["securitySchemes"]),
        },
    }


def separate_copy_legacy(schema: dict[str, Any]) -> dict[str, Any]:
    """Remove only the five declared copy operations; unknown paths still reach export_web."""
    result = copy.deepcopy(schema)
    for path in COPY_PATHS:
        result.get("paths", {}).pop(path, None)
    models = result.get("components", {}).get("schemas", {})
    required = _refs(result.get("paths", {}))
    pending = list(required)
    while pending:
        name = pending.pop()
        extra = _refs(models.get(name, {})) - required
        required.update(extra)
        pending.extend(extra)
    legacy_names: set[str] = set()
    # Keep legacy models even if no currently mounted operation uses them.
    for filename in (
        "p3-web-v1.openapi.json",
        "p4-n01-web-v1.openapi.json",
        "p5-m2-v1.openapi.json",
    ):
        legacy_names.update(
            json.loads(files("commerceops.assets").joinpath(filename).read_text())["components"][
                "schemas"
            ]
        )
    for name in set(copy_openapi()["components"]["schemas"]) - required - legacy_names:
        models.pop(name, None)
    return result
