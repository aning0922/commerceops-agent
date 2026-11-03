"""Eight opt-in V4 demo routes with an independent boundary and public contract."""

import json
from collections.abc import Callable, Coroutine
from typing import Any, cast
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

from commerceops.application.replenishment.contracts import WebFailure
from commerceops.application.v4_demo import contracts as dto
from commerceops.entrypoints.replenishment_http import body
from commerceops.infrastructure.v4_demo_sessions import COOKIE, DemoConfig, DemoLimit
from commerceops.infrastructure.v4_demo_store import DemoStore

PREFIX = "/api/v4/demo"
HEADERS = {"Cache-Control": "no-store", "Vary": "Cookie, Origin"}


def failure(
    code: str, status: int, *, unknown: bool = False, retry_after: int | None = None
) -> JSONResponse:
    try:
        payload = dto.FailureEnvelope.model_validate(
            dict(
                schema_version="v4-demo-v1",
                server_time=None,
                trace_id=uuid4(),
                status="UNKNOWN" if unknown else "REJECTED",
                error=dict(
                    code=code,
                    safe_message="无法处理此演示请求，请核对当前会话或原请求回执。",
                    retryable=False,
                    request_key=None,
                ),
            )
        )
    except ValidationError:
        return failure("SERVICE_UNAVAILABLE", 503, unknown=True)
    headers = dict(HEADERS)
    if status == 429:
        headers["Retry-After"] = str(retry_after or (300 if code == "RATE_LIMITED" else 30))
    return JSONResponse(payload.model_dump(mode="json"), status_code=status, headers=headers)


class DemoRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def guarded(request: Request) -> Response:
            try:
                if request.method == "POST":
                    await body(
                        request
                    )  # bounded, duplicate-key-safe JSON, not permissive JSON loads.
                return await original(request)
            except WebFailure as error:
                if error.code in ("INVALID_JSON", "UNSUPPORTED_MEDIA_TYPE"):
                    return failure("INVALID_REQUEST", 422)
                unknown = error.code == "RESOURCE_NOT_FOUND" and "/operations/" in request.url.path
                return failure(
                    error.code,
                    error.status,
                    unknown=unknown,
                    retry_after=error.retry_after if isinstance(error, DemoLimit) else None,
                )
            except (ValidationError, RequestValidationError):
                return failure("INVALID_REQUEST", 422)
            except (psycopg.Error, OSError, ValueError):
                return failure("SERVICE_UNAVAILABLE", 503, unknown=True)

        return guarded


def reply(
    model: type[dto.Contract], data: dict[str, Any], *, committed: bool = False, status: int = 200
) -> JSONResponse:
    wire = dict(
        schema_version="v4-demo-v1",
        trace_id=str(uuid4()),
        status="COMMITTED" if committed else "OK",
        **data,
    )
    value = model.model_validate_json(json.dumps(wire))
    return JSONResponse(value.model_dump(mode="json"), status_code=status, headers=HEADERS)


def _router(store: DemoStore, config: DemoConfig) -> APIRouter:
    router = APIRouter(prefix=PREFIX, route_class=DemoRoute)

    def cookie(response: JSONResponse, token: str, age: int) -> JSONResponse:
        response.set_cookie(
            COOKIE,
            token,
            max_age=age,
            path="/api/v4",
            httponly=True,
            secure=config.web.transport_mode == "https",
            samesite="lax",
        )
        return response

    @router.get("/bootstrap", response_model=dto.BootstrapEnvelope)
    async def bootstrap(request: Request) -> JSONResponse:
        peer = request.client.host if request.client else "unknown"
        data, issued = await run_in_threadpool(store.bootstrap, request.cookies.get(COOKIE), peer)
        response = reply(dto.BootstrapEnvelope, data)
        return cookie(response, issued, 300) if issued else response

    @router.post("/sessions", response_model=dto.CreateEnvelope, status_code=201)
    async def create(request: Request, command: dto.CreateSessionInput) -> JSONResponse:
        peer = request.client.host if request.client else "unknown"
        data, issued = await run_in_threadpool(
            store.create,
            request.cookies.get(COOKIE),
            request.headers.get("x-csrf-token"),
            command,
            peer,
        )
        return cookie(reply(dto.CreateEnvelope, data, committed=True, status=201), issued, 1800)

    @router.get("/session", response_model=dto.SessionEnvelope)
    async def current(request: Request) -> JSONResponse:
        data = await run_in_threadpool(store.sessions.current, request.cookies.get(COOKIE))
        return reply(dto.SessionEnvelope, data)

    @router.get("/seed-summary", response_model=dto.SeedSummaryEnvelope)
    async def summary(request: Request, shop_id: UUID) -> JSONResponse:
        epoch, generation = (
            request.headers.get("x-demo-epoch", ""),
            request.headers.get("x-demo-generation", ""),
        )
        if (
            not epoch.isascii()
            or not generation.isascii()
            or not epoch.isdecimal()
            or not generation.isdecimal()
        ):
            raise WebFailure("INVALID_REQUEST", 422)
        data = await run_in_threadpool(
            store.summary, request.cookies.get(COOKIE), shop_id, int(epoch), int(generation)
        )
        return reply(dto.SeedSummaryEnvelope, data)

    @router.post("/persona", response_model=dto.ControlEnvelope)
    async def persona(request: Request, command: dto.PersonaInput) -> JSONResponse:
        data = await run_in_threadpool(
            store.control,
            request.cookies.get(COOKIE),
            request.headers.get("x-csrf-token"),
            "persona",
            command,
        )
        return reply(dto.ControlEnvelope, data, committed=True)

    @router.post("/reset", response_model=dto.ControlEnvelope)
    async def reset(request: Request, command: dto.ResetInput) -> JSONResponse:
        data = await run_in_threadpool(
            store.control,
            request.cookies.get(COOKIE),
            request.headers.get("x-csrf-token"),
            "reset",
            command,
        )
        return reply(dto.ControlEnvelope, data, committed=True)

    @router.post("/logout", response_model=dto.ControlEnvelope)
    async def logout(request: Request, command: dto.LogoutInput) -> JSONResponse:
        data = await run_in_threadpool(
            store.control,
            request.cookies.get(COOKIE),
            request.headers.get("x-csrf-token"),
            "logout",
            command,
        )
        response = reply(dto.ControlEnvelope, data, committed=True)
        response.delete_cookie(
            COOKIE,
            path="/api/v4",
            httponly=True,
            secure=config.web.transport_mode == "https",
            samesite="lax",
        )
        return response

    @router.get("/operations/{operation}/{request_key}", response_model=dto.OperationEnvelope)
    async def operation(
        request: Request, operation: dto.Operation, request_key: UUID
    ) -> JSONResponse:
        data = await run_in_threadpool(
            store.operation, request.cookies.get(COOKIE), operation, request_key
        )
        return reply(dto.OperationEnvelope, data)

    return router


def demo_openapi() -> dict[str, Any]:
    app = FastAPI(title="CommerceOps V4 local demo", version="v4-demo-v1")
    app.include_router(_router(cast(DemoStore, None), cast(DemoConfig, None)))
    schema = app.openapi()
    components = schema["components"]
    error = dto.FailureEnvelope.model_json_schema(ref_template="#/components/schemas/{model}")
    components["schemas"].update(error.pop("$defs", {}))
    components["schemas"]["FailureEnvelope"] = error
    components["securitySchemes"] = {
        "demoCookie": {"type": "apiKey", "in": "cookie", "name": COOKIE}
    }
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            operation["security"] = [] if path.endswith("/bootstrap") else [{"demoCookie": []}]
            operation["x-implementation-status"] = "LOCAL_CODE_PG_NOT_VERIFIED"
            operation["x-origin-policy"] = (
                "trusted Origin; same-origin GET exception only; POST Origin+CSRF"
            )
            for code in (401, 403, 404, 409, 415, 422, 429, 503):
                operation["responses"][str(code)] = dict(
                    description="Safe demo error; UNKNOWN never authorizes retry",
                    content={
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/FailureEnvelope"}
                        }
                    },
                )
            if method == "post":
                operation.setdefault("parameters", []).extend(
                    [
                        dict(
                            name="Origin",
                            **{"in": "header"},
                            required=True,
                            schema=dict(type="string"),
                        ),
                        dict(
                            name="X-CSRF-Token",
                            **{"in": "header"},
                            required=True,
                            schema=dict(type="string"),
                        ),
                    ]
                )
            if path.endswith("/seed-summary"):
                for name in ("X-Demo-Epoch", "X-Demo-Generation"):
                    operation.setdefault("parameters", []).append(
                        dict(
                            name=name,
                            **{"in": "header"},
                            required=True,
                            schema=dict(type="integer", minimum=0),
                        )
                    )
    return schema


def install_demo(app: FastAPI, config: DemoConfig, store: DemoStore | None = None) -> None:
    if not config.enabled:
        return
    target = store or DemoStore(config)
    app.include_router(_router(target, config))
    app.state.v4_demo_openapi = demo_openapi()

    @app.middleware("http")
    async def boundary(request: Request, call_next: Any) -> Any:
        if not request.url.path.startswith(PREFIX + "/"):
            return await call_next(request)
        origin = request.headers.get("origin")
        trusted = origin in config.web.origins
        same_origin = (
            request.headers.get("host") == urlsplit(config.api_origin).netloc
            and request.url.scheme == urlsplit(config.api_origin).scheme
        )
        get_exception = same_origin and (
            request.headers.get("sec-fetch-site") == "same-origin"
            or config.allow_non_browser_get
            and "sec-fetch-site" not in request.headers
        )
        if (
            config.web.transport_mode == "https"
            and request.url.scheme != "https"
            or origin is not None
            and not trusted
            or request.method == "POST"
            and not trusted
            or request.method == "GET"
            and origin is None
            and not get_exception
        ):
            return failure("ORIGIN_DENIED", 403)
        if request.method == "OPTIONS":
            if not trusted:
                return failure("ORIGIN_DENIED", 403)
            response = JSONResponse(None, status_code=204, headers=HEADERS)
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = (
                "Content-Type, X-CSRF-Token, X-Demo-Epoch, X-Demo-Generation"
            )
        else:
            response = await call_next(request)
        if trusted and origin is not None:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers.update(HEADERS)
        return response
