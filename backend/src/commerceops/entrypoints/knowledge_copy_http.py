"""Explicitly mounted K3 router; no main API/Worker registration or provider construction."""

import json
from typing import Any, Protocol
from uuid import UUID

import psycopg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError
from starlette.concurrency import run_in_threadpool

from commerceops.application.commerce.contracts import Digest
from commerceops.application.knowledge_copy.commands import CopyReceipt, CreateCopy, ReviewCopy
from commerceops.application.knowledge_copy.contracts import Contract, checked
from commerceops.application.knowledge_copy.http_models import (
    COPY_ERROR_CODES,
    CandidateResponse,
    CopyError,
    DecisionResponse,
    UnknownCandidateResponse,
    UnknownDecisionResponse,
    strict_flags,
)
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


def copy_error_response(code: str, status: int) -> JSONResponse:
    aliases = {
        "KNOWLEDGE_NOT_AVAILABLE": "ACCESS_DENIED",
        "COPY_QUERY_UNAVAILABLE": "NOT_READY",
        "COPY_REVIEWER_UNAVAILABLE": "NOT_READY",
        "COPY_PRODUCT_UNAVAILABLE": "NOT_READY",
        "COPY_SOURCE_EXPIRED_OR_REVOKED": "NOT_READY",
        "COPY_VERSION_CHANGED": "PLAN_CHANGED",
        "COPY_ALREADY_REVIEWED": "DECISION_CONFLICT",
        "COPY_RECEIPT_UNAVAILABLE": "SERVICE_UNAVAILABLE",
    }
    code = aliases.get(code, code)
    if code not in COPY_ERROR_CODES or status not in (400, 401, 403, 404, 409, 415, 422, 429, 503):
        code, status = "SERVICE_UNAVAILABLE", 503
    result = error_response(code, status)
    CopyError.model_validate_json(bytes(result.body))
    return result


def _reply(value: Contract, status: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        headers={"Cache-Control": "no-store", "Vary": "Cookie, Origin"},
        content=checked(value).model_dump(mode="json"),
    )


def candidate_reply(
    data: dict[str, Any],
    *,
    status: int = 200,
    identifier: UUID | None = None,
    request_key: UUID | None = None,
) -> JSONResponse:
    try:
        wire = json.dumps({"schema_version": "p6-copy-web-v1", "data": data}, allow_nan=False)
        if data.get("state") == "UNKNOWN":
            unknown = UnknownCandidateResponse.model_validate_json(wire)
            if request_key is None or unknown.data.request_key != request_key:
                raise ValueError
            return _reply(unknown, 202)
        known = CandidateResponse.model_validate_json(wire)
        if identifier is not None and known.data.candidate.candidate_id != identifier:
            raise ValueError
        return _reply(known, status)
    except (ValueError, TypeError):
        raise WebFailure("SERVICE_UNAVAILABLE", 503) from None


def decision_reply(
    value: CopyReceipt, identifier: UUID, request_key: UUID, candidate_hash: str
) -> JSONResponse:
    try:
        strict_flags(value)
        value = checked(value)
        if (value.candidate_id, value.request_key, value.candidate_hash) != (
            identifier,
            request_key,
            candidate_hash,
        ):
            raise ValueError
        wire = json.dumps(
            {"schema_version": "p6-copy-web-v1", "data": value.model_dump(mode="json")}
        )
        if value.state == "UNKNOWN":
            return _reply(UnknownDecisionResponse.model_validate_json(wire), 202)
        return _reply(DecisionResponse.model_validate_json(wire))
    except (ValueError, TypeError):
        raise WebFailure("SERVICE_UNAVAILABLE", 503) from None


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
            return copy_error_response(error.code, error.status)
        if isinstance(error, (ValidationError, ValueError)):
            return copy_error_response("DATA_INCOMPLETE", 409)
        return copy_error_response("SERVICE_UNAVAILABLE", 503)

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
                return copy_error_response("INVALID_REQUEST", 422)
            value = await run_in_threadpool(store.create, actor, command)
            result = await run_in_threadpool(store.read, actor, value.candidate_id)
            return candidate_reply(result, status=202, identifier=value.candidate_id)
        except (psycopg.OperationalError, psycopg.InterfaceError):
            if command is not None:
                return candidate_reply(
                    dict(
                        state="UNKNOWN",
                        request_key=str(command.request_key),
                        publication_allowed=False,
                    ),
                    request_key=command.request_key,
                )
            return copy_error_response("SERVICE_UNAVAILABLE", 503)
        except (WebFailure, ValueError, psycopg.Error, OSError) as error:
            return failed(error)

    @router.get("/candidate-requests/{key}")
    async def candidate_request(key: str, request: Request) -> JSONResponse:
        try:
            actor = await protect(request)
            request_key = parsed_uuid(key)
            value = await run_in_threadpool(store.candidate_request, actor, request_key)
            return candidate_reply(value, request_key=request_key)
        except (WebFailure, ValueError, psycopg.Error, OSError) as error:
            return failed(error)

    @router.get("/candidates/{identifier}")
    async def read(identifier: str, request: Request) -> JSONResponse:
        try:
            actor = await protect(request)
            candidate_id = parsed_uuid(identifier)
            return candidate_reply(
                await run_in_threadpool(store.read, actor, candidate_id), identifier=candidate_id
            )
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
                return copy_error_response("INVALID_REQUEST", 422)
            receipt = await run_in_threadpool(store.review, actor, candidate_id, command)
            return decision_reply(
                receipt, candidate_id, command.request_key, command.candidate_hash
            )
        except (psycopg.OperationalError, psycopg.InterfaceError):
            if command is not None and candidate_id is not None:
                unknown = CopyReceipt(
                    request_key=command.request_key,
                    candidate_id=candidate_id,
                    candidate_hash=command.candidate_hash,
                    state="UNKNOWN",
                )
                return decision_reply(
                    unknown, candidate_id, command.request_key, command.candidate_hash
                )
            return copy_error_response("SERVICE_UNAVAILABLE", 503)
        except (WebFailure, ValueError, psycopg.Error, OSError) as error:
            return failed(error)

    @router.get("/candidates/{identifier}/review-receipts/{key}")
    async def receipt(
        identifier: str, key: str, request: Request, candidate_hash: str | None = None
    ) -> JSONResponse:
        try:
            actor = await protect(request)
            try:
                expected = TypeAdapter(Digest).validate_python(candidate_hash)
            except ValidationError:
                raise WebFailure("INVALID_REQUEST", 422) from None
            result = await run_in_threadpool(
                store.receipt, actor, parsed_uuid(identifier), parsed_uuid(key), expected
            )
            return decision_reply(result, parsed_uuid(identifier), parsed_uuid(key), expected)
        except (WebFailure, ValueError, psycopg.Error, OSError) as error:
            return failed(error)

    return router
