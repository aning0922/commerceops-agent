"""Explicitly mounted K3 router; no main API/Worker registration or provider construction."""

from typing import Any, Protocol
from uuid import UUID

import psycopg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError
from starlette.concurrency import run_in_threadpool

from commerceops.application.commerce.contracts import Digest
from commerceops.application.knowledge_copy.commands import CopyReceipt, CreateCopy, ReviewCopy
from commerceops.application.replenishment.contracts import WebActor, WebFailure
from commerceops.entrypoints.replenishment_http import COOKIE, body, error_response, parsed_uuid
from commerceops.infrastructure.knowledge_copy_drafts import CopyCandidate
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.web_sessions import SessionStore


class CopyEndpoints(Protocol):
    def create(self, actor: WebActor, request: CreateCopy) -> CopyCandidate: ...
    def read(self, actor: WebActor, identifier: UUID) -> dict[str, Any]: ...
    def candidate_request(self, actor: WebActor, request_key: UUID) -> dict[str, Any]: ...
    def review(self, actor: WebActor, identifier: UUID, request: ReviewCopy) -> CopyReceipt: ...
    def receipt(
        self, actor: WebActor, identifier: UUID, request_key: UUID, candidate_hash: str
    ) -> CopyReceipt: ...


def _reply(data: Any, status: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        headers={"Cache-Control": "no-store", "Vary": "Cookie, Origin"},
        content={"schema_version": "p6-copy-web-v1", "data": data},
    )


def knowledge_copy_router(config: WebConfig, store: CopyEndpoints) -> APIRouter:
    """Backend explicitly includes this router alongside its existing session routes/middleware."""
    sessions = SessionStore(config)
    router = APIRouter(prefix="/api/v1/copy")

    async def protect(request: Request, *, write: bool = False) -> WebActor:
        origin = request.headers.get("origin")
        if (
            origin is not None
            and origin not in config.origins
            or write
            and origin not in config.origins
            or config.transport_mode == "https"
            and request.url.scheme != "https"
        ):
            raise WebFailure("ORIGIN_DENIED", 403)
        token = request.cookies.get(COOKIE)
        actor = await run_in_threadpool(sessions.authenticate, token)
        if write:
            await run_in_threadpool(sessions.check_csrf, token, request.headers.get("x-csrf-token"))
        return actor

    def failed(error: Exception) -> JSONResponse:
        if isinstance(error, WebFailure):
            return error_response(error.code, error.status)
        if isinstance(error, (ValidationError, ValueError)):
            return error_response("COPY_EVIDENCE_OR_REQUEST_INVALID", 409)
        return error_response("SERVICE_UNAVAILABLE", 503)

    @router.post(
        "/candidates",
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": CreateCopy.model_json_schema()}},
            }
        },
    )
    async def create(request: Request) -> JSONResponse:
        command: CreateCopy | None = None
        try:
            actor = await protect(request, write=True)
            try:
                command = CreateCopy.model_validate_json(await body(request))
            except ValidationError:
                return error_response("INVALID_REQUEST", 422)
            value = await run_in_threadpool(store.create, actor, command)
            result = await run_in_threadpool(store.read, actor, value.candidate_id)
            return _reply(result, 202)
        except (psycopg.OperationalError, psycopg.InterfaceError):
            if command is not None:
                return _reply(
                    dict(
                        state="UNKNOWN",
                        request_key=str(command.request_key),
                        publication_allowed=False,
                    ),
                    202,
                )
            return error_response("SERVICE_UNAVAILABLE", 503)
        except (WebFailure, ValueError, psycopg.Error, OSError) as error:
            return failed(error)

    @router.get("/candidate-requests/{key}")
    async def candidate_request(key: str, request: Request) -> JSONResponse:
        try:
            actor = await protect(request)
            value = await run_in_threadpool(store.candidate_request, actor, parsed_uuid(key))
            return _reply(value, 202 if value.get("state") == "UNKNOWN" else 200)
        except (WebFailure, ValueError, psycopg.Error, OSError) as error:
            return failed(error)

    @router.get("/candidates/{identifier}")
    async def read(identifier: str, request: Request) -> JSONResponse:
        try:
            actor = await protect(request)
            return _reply(await run_in_threadpool(store.read, actor, parsed_uuid(identifier)))
        except (WebFailure, ValueError, psycopg.Error, OSError) as error:
            return failed(error)

    @router.post(
        "/candidates/{identifier}/review",
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": ReviewCopy.model_json_schema()}},
            }
        },
    )
    async def review(identifier: str, request: Request) -> JSONResponse:
        command: ReviewCopy | None = None
        candidate_id: UUID | None = None
        try:
            actor = await protect(request, write=True)
            candidate_id = parsed_uuid(identifier)
            try:
                command = ReviewCopy.model_validate_json(await body(request))
            except ValidationError:
                return error_response("INVALID_REQUEST", 422)
            receipt = await run_in_threadpool(store.review, actor, candidate_id, command)
            return _reply(receipt.model_dump(mode="json"))
        except (psycopg.OperationalError, psycopg.InterfaceError):
            if command is not None and candidate_id is not None:
                unknown = CopyReceipt(
                    request_key=command.request_key,
                    candidate_id=candidate_id,
                    candidate_hash=command.candidate_hash,
                    state="UNKNOWN",
                )
                return _reply(unknown.model_dump(mode="json"), 202)
            return error_response("SERVICE_UNAVAILABLE", 503)
        except (WebFailure, ValueError, psycopg.Error, OSError) as error:
            return failed(error)

    @router.get("/candidates/{identifier}/review-receipts/{key}")
    async def receipt(
        identifier: str, key: str, candidate_hash: str, request: Request
    ) -> JSONResponse:
        try:
            actor = await protect(request)
            expected = TypeAdapter(Digest).validate_python(candidate_hash)
            result = await run_in_threadpool(
                store.receipt, actor, parsed_uuid(identifier), parsed_uuid(key), expected
            )
            return _reply(result.model_dump(mode="json"), 202 if result.state == "UNKNOWN" else 200)
        except (WebFailure, ValueError, psycopg.Error, OSError) as error:
            return failed(error)

    return router
