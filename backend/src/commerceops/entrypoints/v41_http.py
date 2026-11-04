"""Opt-in strict V41 boundary. No database access or service startup during registration."""

import json
import re
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
from commerceops.application.v4_demo.contracts import Contract
from commerceops.application.v41 import contracts as dto
from commerceops.entrypoints.replenishment_http import unique_object
from commerceops.infrastructure.v4_demo_sessions import COOKIE, DemoConfig
from commerceops.infrastructure.v41_parse import ParseUnavailable
from commerceops.infrastructure.v41_store import BusinessStore, ReadKind

HEADERS = {"Cache-Control": "no-store", "Vary": "Cookie, Origin"}
NAMESPACES = frozenset({"dashboard", "products", "orders", "read-context", "imports", "actions"})
STATUS = {
    "SESSION_INVALID": 401,
    "ORIGIN_DENIED": 403,
    "CSRF_INVALID": 403,
    "ACCESS_DENIED": 403,
    "RESOURCE_NOT_FOUND": 404,
    "EPOCH_CHANGED": 409,
    "GENERATION_CHANGED": 409,
    "INVALID_REQUEST": 422,
    "IDEMPOTENCY_CONFLICT": 409,
    "VERSION_CONFLICT": 409,
    "STATE_CONFLICT": 409,
    "PAYMENT_STATE_UNKNOWN": 409,
    "SNAPSHOT_CHANGED": 409,
    "IMPORT_INVALID": 422,
    "IMPORT_EXPIRED": 409,
    "LIMIT_EXCEEDED": 429,
    "RATE_LIMITED": 429,
    "SERVICE_UNAVAILABLE": 503,
}


def business_path(path: str) -> bool:
    parts = path.split("/")
    return len(parts) >= 4 and parts[:3] == ["", "api", "v4"] and parts[3] in NAMESPACES


def failure(code: str, status: int | None = None, *, unknown: bool = False) -> JSONResponse:
    if code not in STATUS:
        code, unknown = "SERVICE_UNAVAILABLE", True
    wire = dto.FailureEnvelope.model_validate_json(
        json.dumps(
            dict(
                server_time=None,
                trace_id=str(uuid4()),
                status="UNKNOWN" if unknown else "REJECTED",
                error=dict(
                    code=code,
                    safe_message="请求未能完成，请核对当前会话及原请求回执。",
                    retryable=False,
                    request_key=None,
                ),
            )
        )
    )
    headers = HEADERS | ({"Retry-After": "30"} if STATUS[code] == 429 else {})
    return JSONResponse(
        wire.model_dump(mode="json"), status_code=status or STATUS[code], headers=headers
    )


class BusinessRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def guarded(request: Request) -> Response:
            try:
                return await original(request)
            except (RequestValidationError, ValidationError):
                return failure("INVALID_REQUEST")
            except WebFailure as error:
                return failure(error.code, unknown=error.code == "SERVICE_UNAVAILABLE")
            except ParseUnavailable as error:
                code = str(error)
                return failure(
                    code if code in STATUS else "SERVICE_UNAVAILABLE", unknown=code not in STATUS
                )
            except psycopg.Error as error:
                code = error.diag.message_primary or "SERVICE_UNAVAILABLE"
                return failure(
                    code if code in STATUS else "SERVICE_UNAVAILABLE",
                    unknown=code not in STATUS or code == "SERVICE_UNAVAILABLE",
                )
            except (OSError, ValueError, RecursionError) as error:
                code = str(error) if isinstance(error, ValueError) else "SERVICE_UNAVAILABLE"
                return failure(
                    code if code in STATUS else "SERVICE_UNAVAILABLE",
                    unknown=code not in STATUS or code == "SERVICE_UNAVAILABLE",
                )

        return guarded


def reply(model: type[Contract], data: dict[str, Any], *, committed: bool = False) -> JSONResponse:
    # Strict JSON validation preserves native UUID/time types while rejecting unexpected fields.
    wire = dict(
        schema_version="v4-business-v1",
        trace_id=str(uuid4()),
        status="COMMITTED" if committed else "OK",
        **data,
    )
    raw = json.dumps(
        wire,
        default=lambda value: (
            value.model_dump(mode="json") if isinstance(value, Contract) else str(value)
        ),
    )
    try:
        result = model.model_validate_json(raw)
    except ValidationError:
        raise WebFailure("SERVICE_UNAVAILABLE", 503) from None
    return JSONResponse(result.model_dump(mode="json"), headers=HEADERS)


def expected(request: Request) -> tuple[int, int]:
    values = []
    for name in ("x-demo-epoch", "x-demo-generation"):
        raw = request.headers.getlist(name)
        if len(raw) != 1 or re.fullmatch(r"0|[1-9][0-9]{0,8}", raw[0]) is None:
            raise WebFailure("INVALID_REQUEST", 422)
        values.append(int(raw[0]))
    return values[0], values[1]


def query_model[T: Contract](request: Request, model: type[T]) -> T:
    value: dict[str, Any] = {}
    for name, raw in request.query_params.multi_items():
        if name in value:
            raise WebFailure("INVALID_REQUEST", 422)
        if name in ("days", "limit"):
            if re.fullmatch(r"0|[1-9][0-9]{0,8}", raw) is None:
                raise WebFailure("INVALID_REQUEST", 422)
            value[name] = int(raw)
        else:
            value[name] = raw
    return model.model_validate_json(json.dumps(value))


async def command_model[T: Contract](request: Request, model: type[T]) -> T:
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise WebFailure("INVALID_REQUEST", 422)
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > 3 * 1024 * 1024:
            raise WebFailure("INVALID_REQUEST", 422)
        data.extend(chunk)
    try:
        json.loads(
            data,
            object_pairs_hook=unique_object,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except (ValueError, UnicodeError, RecursionError):
        raise WebFailure("INVALID_REQUEST", 422) from None
    return model.model_validate_json(bytes(data))


def query_parameters(model: type[Contract]) -> list[dict[str, Any]]:
    schema = model.model_json_schema()
    required = schema.get("required", [])
    return [
        dict(name=name, required=name in required, **{"in": "query"}, schema=field)
        for name, field in schema["properties"].items()
    ]


def _router(store: BusinessStore) -> APIRouter:
    router = APIRouter(prefix="/api/v4", route_class=BusinessRoute)

    def get_route(
        path: str,
        kind: ReadKind,
        query_type: type[dto.Query],
        response: type[Contract],
        *,
        detail: bool = False,
    ) -> None:
        if detail:

            async def get_detail(request: Request) -> JSONResponse:
                resource_id = UUID(next(iter(request.path_params.values())))
                query = query_model(request, query_type)
                epoch, generation = expected(request)
                data = await run_in_threadpool(
                    store.read,
                    request.cookies.get(COOKIE),
                    epoch,
                    generation,
                    query,
                    kind,
                    resource_id,
                )
                return reply(response, data)

            name = path.split("{")[1].split("}")[0]
            router.add_api_route(
                path,
                get_detail,
                methods=["GET"],
                response_model=response,
                openapi_extra={
                    "parameters": query_parameters(query_type)
                    + [
                        dict(
                            name=name,
                            required=True,
                            **{"in": "path"},
                            schema=dict(type="string", format="uuid"),
                        )
                    ]
                },
            )
        else:

            async def get(request: Request) -> JSONResponse:
                query = query_model(request, query_type)
                epoch, generation = expected(request)
                data = await run_in_threadpool(
                    store.read, request.cookies.get(COOKIE), epoch, generation, query, kind
                )
                return reply(response, data)

            router.add_api_route(
                path,
                get,
                methods=["GET"],
                response_model=response,
                openapi_extra={"parameters": query_parameters(query_type)},
            )

    # Fixed export paths must precede UUID detail routes.
    get_route("/dashboard", "dashboard", dto.PeriodQuery, dto.BusinessEnvelope[dto.DashboardData])
    get_route(
        "/dashboard/drilldown",
        "drilldown",
        dto.DrilldownQuery,
        dto.BusinessEnvelope[dto.Page[dto.Order | dto.Product | dto.RefundReference]],
    )
    get_route(
        "/products", "products", dto.ProductQuery, dto.BusinessEnvelope[dto.Page[dto.Product]]
    )
    get_route(
        "/products/export", "product_export", dto.ProductQuery, dto.BusinessEnvelope[dto.ExportData]
    )
    get_route(
        "/products/{product_id}",
        "product",
        dto.Query,
        dto.BusinessEnvelope[dto.ProductDetail],
        detail=True,
    )
    get_route("/orders", "orders", dto.OrderQuery, dto.BusinessEnvelope[dto.Page[dto.Order]])
    get_route(
        "/orders/export", "order_export", dto.OrderQuery, dto.BusinessEnvelope[dto.ExportData]
    )
    get_route(
        "/orders/{order_id}",
        "order",
        dto.Query,
        dto.BusinessEnvelope[dto.OrderDetail],
        detail=True,
    )
    get_route(
        "/read-context",
        "read_context",
        dto.ReadContextQuery,
        dto.BusinessEnvelope[dto.ReadContextData],
    )

    def post_route(path: str, operation: dto.Operation, model: type[dto.WriteContext]) -> None:
        async def post(request: Request) -> JSONResponse:
            resource_id = UUID(next(iter(request.path_params.values())))
            command = await command_model(request, model)
            data = await run_in_threadpool(
                store.action,
                request.cookies.get(COOKIE),
                request.headers.get("x-csrf-token"),
                command,
                operation,
                resource_id,
            )
            return reply(dto.BusinessEnvelope[dto.ActionResult], data, committed=True)

        router.add_api_route(
            path,
            post,
            methods=["POST"],
            response_model=dto.BusinessEnvelope[dto.ActionResult],
            openapi_extra={
                "parameters": [
                    dict(
                        name=path.split("{")[1].split("}")[0],
                        required=True,
                        **{"in": "path"},
                        schema=dict(type="string", format="uuid"),
                    )
                ],
                "x-v41-request-model": model.__name__,
            },
        )

    post_route("/products/{product_id}/tags", "product_tags", dto.SetProductTags)
    post_route("/orders/{order_id}/fulfillment", "order_fulfillment", dto.FulfillDemoOrder)
    post_route("/imports/{import_job_id}/confirm", "import_confirm", dto.ConfirmImport)

    @router.post(
        "/imports/previews",
        response_model=dto.BusinessEnvelope[dto.ImportPreviewData],
        openapi_extra={"x-v41-request-model": "ImportPreviewInput"},
    )
    async def preview(request: Request) -> JSONResponse:
        command = await command_model(request, dto.ImportPreviewInput)
        data = await run_in_threadpool(
            store.preview, request.cookies.get(COOKIE), request.headers.get("x-csrf-token"), command
        )
        return reply(dto.BusinessEnvelope[dto.ImportPreviewData], data, committed=True)

    @router.get(
        "/imports/preview-requests/{request_key}",
        response_model=dto.BusinessEnvelope[dto.PreviewLookup],
        openapi_extra={"parameters": query_parameters(dto.Query)},
    )
    async def preview_request(request: Request, request_key: UUID) -> JSONResponse:
        query = query_model(request, dto.Query)
        epoch, generation = expected(request)
        data = await run_in_threadpool(
            store.preview_lookup, request.cookies.get(COOKIE), epoch, generation, query, request_key
        )
        return reply(dto.BusinessEnvelope[dto.PreviewLookup], data)

    @router.get(
        "/imports/{import_job_id}",
        response_model=dto.BusinessEnvelope[dto.ImportPreviewData],
        openapi_extra={"parameters": query_parameters(dto.Query)},
    )
    async def import_job(request: Request, import_job_id: UUID) -> JSONResponse:
        query = query_model(request, dto.Query)
        epoch, generation = expected(request)
        data = await run_in_threadpool(
            store.preview_lookup,
            request.cookies.get(COOKIE),
            epoch,
            generation,
            query,
            import_job_id,
            by_id=True,
        )
        return reply(dto.BusinessEnvelope[dto.ImportPreviewData], data)

    @router.get(
        "/actions/{operation}/{request_key}", response_model=dto.BusinessEnvelope[dto.ActionLookup]
    )
    async def action(request: Request, operation: dto.Operation, request_key: UUID) -> JSONResponse:
        query = query_model(request, dto.Query)
        epoch, generation = expected(request)
        data = await run_in_threadpool(
            store.action_lookup,
            request.cookies.get(COOKIE),
            epoch,
            generation,
            query,
            operation,
            request_key,
        )
        return reply(dto.BusinessEnvelope[dto.ActionLookup], data)

    return router


def business_openapi() -> dict[str, Any]:
    app = FastAPI(title="CommerceOps V41 local business", version="v4-business-v1")
    app.include_router(_router(cast(BusinessStore, None)))
    schema = app.openapi()
    models = (dto.SetProductTags, dto.FulfillDemoOrder, dto.ConfirmImport, dto.ImportPreviewInput)
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    for model in models:
        definition = model.model_json_schema(ref_template="#/components/schemas/{model}")
        components.update(definition.pop("$defs", {}))
        components[model.__name__] = definition
    error = dto.FailureEnvelope.model_json_schema(ref_template="#/components/schemas/{model}")
    components.update(error.pop("$defs", {}))
    components["FailureEnvelope"] = error
    schema["components"]["securitySchemes"] = {
        "demoCookie": dict(type="apiKey", **{"in": "cookie"}, name=COOKIE)
    }
    for methods in schema["paths"].values():
        for method, operation in methods.items():
            operation["security"] = [{"demoCookie": []}]
            operation["x-implementation-status"] = "LOCAL_CODE_PG_NOT_VERIFIED"
            if method == "post":
                name = operation.pop("x-v41-request-model")
                operation["requestBody"] = dict(
                    required=True,
                    content={
                        "application/json": {"schema": {"$ref": "#/components/schemas/" + name}}
                    },
                )
                names = ("Origin", "X-CSRF-Token")
            else:
                names = ("X-Demo-Epoch", "X-Demo-Generation")
            operation.setdefault("parameters", []).extend(
                dict(name=name, required=True, **{"in": "header"}, schema=dict(type="string"))
                for name in names
            )
            for status in set(STATUS.values()):
                operation["responses"][str(status)] = dict(
                    description="Safe business failure",
                    content={
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/FailureEnvelope"}
                        }
                    },
                )
    return schema


def install_business(app: FastAPI, config: DemoConfig, store: BusinessStore | None = None) -> None:
    if not config.enabled:
        return
    app.include_router(_router(store or BusinessStore(config)))
    app.state.v41_business_openapi = business_openapi()

    @app.middleware("http")
    async def boundary(request: Request, call_next: Any) -> Any:
        if not business_path(request.url.path):
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
            return failure("ORIGIN_DENIED")
        if request.method == "OPTIONS":
            if not trusted:
                return failure("ORIGIN_DENIED")
            response = JSONResponse(None, status_code=204, headers=HEADERS)
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = (
                "Content-Type, X-CSRF-Token, X-Demo-Epoch, X-Demo-Generation"
            )
        else:
            response = await call_next(request)
            if response.status_code in (404, 405):
                response = failure("RESOURCE_NOT_FOUND")
        if trusted and origin is not None:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers.update(HEADERS)
        return response
