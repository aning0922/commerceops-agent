"""Unregistered inquiry router and Pydantic-derived OpenAPI. No server starts on import."""

import argparse
import json
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from pydantic.json_schema import models_json_schema

from commerceops.application.commerce.readonly_inquiry_service_contracts import (
    CreateInquiry,
    InquiryError,
    InquiryRead,
    InquiryReceipt,
)
from commerceops.application.replenishment.contracts import WebActor, WebFailure
from commerceops.entrypoints.replenishment_http import COOKIE, body
from commerceops.infrastructure.readonly_inquiry_runtime import db_call
from commerceops.infrastructure.web_config import WebConfig

PREFIX = "/api/v1/readonly-inquiries"


class SessionBoundary(Protocol):
    def authenticate(self, token: str | None) -> WebActor: ...
    def check_csrf(self, token: str | None, supplied: str | None) -> None: ...


class HttpStore(Protocol):
    def authorize_entry(self, actor: WebActor) -> None: ...
    def create(self, actor: WebActor, request: CreateInquiry) -> InquiryReceipt: ...
    def read(
        self, actor: WebActor, task_id: UUID | None = None, request_key: UUID | None = None
    ) -> InquiryRead: ...


def failure(code: str, status: int) -> JSONResponse:
    try:
        error = InquiryError.model_validate({"code": code, "trace_id": uuid4()})
    except ValidationError:
        error = InquiryError(code="SERVICE_UNAVAILABLE", trace_id=uuid4())
        status = 503
    return JSONResponse(
        error.model_dump(mode="json"),
        status_code=status,
        headers={"Cache-Control": "no-store", "Vary": "Cookie, Origin"},
    )


def identifier(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise WebFailure("RESOURCE_NOT_FOUND", 404) from None


def inquiry_router(store: HttpStore, sessions: SessionBoundary, config: WebConfig) -> APIRouter:
    router = APIRouter(prefix=PREFIX)

    async def actor(request: Request) -> WebActor:
        origin = request.headers.get("origin")
        if origin is not None and origin not in config.origins:
            raise WebFailure("ORIGIN_DENIED", 403)
        if config.transport_mode == "https" and request.url.scheme != "https":
            raise WebFailure("ORIGIN_DENIED", 403)
        token = request.cookies.get(COOKIE)
        subject = await db_call(sessions.authenticate, token)
        if request.method == "POST":
            if origin not in config.origins:
                raise WebFailure("ORIGIN_DENIED", 403)
            await db_call(sessions.check_csrf, token, request.headers.get("x-csrf-token"))
        await db_call(store.authorize_entry, subject)
        return subject

    @router.post("")
    async def create(request: Request) -> JSONResponse:
        try:
            subject = await actor(request)
            value = CreateInquiry.model_validate_json(await body(request))
            result = await db_call(store.create, subject, value)
            # Do not publish an unvalidated result from a store implementation.
            try:
                result = InquiryReceipt.model_validate_json(result.model_dump_json())
            except ValidationError:
                raise WebFailure("SERVICE_UNAVAILABLE", 503) from None
            return JSONResponse(
                result.model_dump(mode="json"),
                status_code=202,
                headers={"Cache-Control": "no-store", "Vary": "Cookie, Origin"},
            )
        except WebFailure as exc:
            return failure(exc.code, exc.status)
        except ValidationError:
            return failure("INVALID_REQUEST", 422)
        except (psycopg.Error, OSError, ValueError):
            return failure("SERVICE_UNAVAILABLE", 503)

    async def read(request: Request, value: str, by_key: bool) -> JSONResponse:
        try:
            subject = await actor(request)
            parsed = identifier(value)
            result = await db_call(
                store.read, subject, None if by_key else parsed, parsed if by_key else None
            )
            result = InquiryRead.model_validate_json(result.model_dump_json())
            return JSONResponse(
                result.model_dump(mode="json"),
                headers={"Cache-Control": "no-store", "Vary": "Cookie, Origin"},
            )
        except WebFailure as exc:
            return failure(exc.code, exc.status)
        except ValidationError:
            return failure("SERVICE_UNAVAILABLE", 503)
        except (psycopg.Error, OSError, ValueError):
            return failure("SERVICE_UNAVAILABLE", 503)

    @router.get("/requests/{request_key}")
    async def receipt(request: Request, request_key: str) -> JSONResponse:
        return await read(request, request_key, True)

    @router.get("/{task_id}")
    async def task(request: Request, task_id: str) -> JSONResponse:
        return await read(request, task_id, False)

    return router


def inquiry_openapi() -> dict[str, Any]:
    """Dedicated schema for Root's shared export merge; does not modify p3-web-v1."""
    _, document = models_json_schema(
        [
            (CreateInquiry, "validation"),
            (InquiryReceipt, "serialization"),
            (InquiryRead, "serialization"),
            (InquiryError, "serialization"),
        ],
        ref_template="#/components/schemas/{model}",
    )

    def response(model: str, description: str) -> dict[str, object]:
        return {
            "description": description,
            "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{model}"}}},
        }

    errors = {
        str(code): response("InquiryError", "Safe error")
        for code in (400, 401, 403, 404, 409, 415, 422, 503)
    }
    paths: dict[str, Any] = {
        PREFIX: {
            "post": {
                "operationId": "createReadonlyInquiry",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/CreateInquiry"}
                        }
                    },
                },
                "responses": {
                    "202": response("InquiryReceipt", "Persisted task receipt"),
                    **errors,
                },
            }
        }
    }
    for suffix, parameter, operation in (
        ("/{task_id}", "task_id", "readReadonlyInquiry"),
        ("/requests/{request_key}", "request_key", "readReadonlyInquiryReceipt"),
    ):
        paths[PREFIX + suffix] = {
            "get": {
                "operationId": operation,
                "parameters": [
                    {
                        "in": "path",
                        "name": parameter,
                        "required": True,
                        "schema": {"type": "string", "format": "uuid"},
                    }
                ],
                "responses": {
                    "200": response("InquiryRead", "Currently authorized persisted result"),
                    **errors,
                },
            }
        }
    return {
        "openapi": "3.1.0",
        "info": {"title": "P6 offline inquiry", "version": "p6-inquiry-web-v1"},
        "paths": paths,
        "components": {"schemas": document["$defs"]},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export inquiry schema; no API service")
    parser.add_argument("--export", type=Path, required=True)
    args = parser.parse_args()
    args.export.write_text(json.dumps(inquiry_openapi(), ensure_ascii=False, indent=2) + "\n")
