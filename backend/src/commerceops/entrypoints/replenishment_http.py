"""P3 Cookie会话入口；先身份/CSRF/对象能力，再解析严格JSON。"""

import asyncio
import json
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware

from commerceops.application.replenishment.contracts import (
    CreateInput,
    DecisionInput,
    LoginInput,
    LogoutInput,
    ResolveInput,
    WebActor,
    WebFailure,
)
from commerceops.domain.commerce_values import utc_time
from commerceops.infrastructure.approval_decisions import DecisionStore
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.replenishment_items import ItemStore
from commerceops.infrastructure.replenishment_read import ReplenishmentReadStore
from commerceops.infrastructure.replenishment_repository import ReplenishmentStore
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.web_sessions import SessionStore, now

COOKIE = "commerceops_session"


def error_response(code: str, status: int, server_time: Any = None) -> JSONResponse:
    messages = {
        "SESSION_INVALID": "会话无效，请重新登录",
        "LOGIN_FAILED": "登录失败",
        "ACCESS_DENIED": "当前身份无此操作权限",
        "RESOURCE_NOT_FOUND": "无法访问该资源",
        "SERVICE_UNAVAILABLE": "服务暂不可用，请核实原请求",
        "NOT_READY": "结果尚未就绪",
        "RATE_LIMITED": "请求过于频繁，请稍后再试",
        "PLAN_CHANGED": "版本已变化，请重新读取",
        "IDEMPOTENCY_CONFLICT": "原请求键与本次内容冲突",
        "INVALID_CURSOR": "分页已失效，请刷新",
        "ORIGIN_DENIED": "请求来源不允许",
        "CSRF_INVALID": "请求校验失败，请刷新",
    }
    headers = {"Cache-Control": "no-store", "Vary": "Cookie, Origin"}
    if status == 429:
        headers["Retry-After"] = "300"
    return JSONResponse(
        status_code=status,
        headers=headers,
        content={
            "schema_version": "p3-web-v1",
            "server_time": server_time,
            "trace_id": str(uuid4()),
            "error": {
                "code": code,
                "safe_message": messages.get(code, "请求无效，请核对后重试"),
                "retryable": False,
                "receipt": None,
            },
        },
    )


def parsed_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise WebFailure("RESOURCE_NOT_FOUND", 404) from None


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


async def body(request: Request) -> bytes:
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise WebFailure("UNSUPPORTED_MEDIA_TYPE", 415)
    value = await request.body()
    if len(value) > 65536:
        raise WebFailure("INVALID_REQUEST", 422)
    try:
        json.loads(
            value,
            object_pairs_hook=unique_object,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except (ValueError, UnicodeError, RecursionError):
        raise WebFailure("INVALID_JSON", 400) from None
    return value


def install_web(app: FastAPI, config: WebConfig, store: ReplenishmentStore) -> None:
    sessions = SessionStore(config)
    reads = ReplenishmentReadStore(store)
    decisions = DecisionStore(config)
    items = ItemStore(store)
    router = APIRouter(prefix="/api/v1")

    def failure_response_for(code: str, status: int) -> JSONResponse:
        try:
            with connect(store.settings) as db:
                timestamp = utc_time(now(db)).isoformat().replace("+00:00", "Z")
        except (psycopg.Error, OSError, ValueError):
            timestamp = None
        return error_response(code, status, timestamp)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )

    @app.middleware("http")
    async def web_boundary(request: Request, call_next: Any) -> Any:
        if not request.url.path.startswith("/api/v1/"):
            return await call_next(request)
        try:
            origin = request.headers.get("origin")
            if origin is not None and origin not in config.origins:
                raise WebFailure("ORIGIN_DENIED", 403)
            if config.transport_mode == "https" and request.url.scheme != "https":
                raise WebFailure("ORIGIN_DENIED", 403)
            if request.method == "OPTIONS":
                # 外层CORS处理preflight；不创建会话或业务。
                return await call_next(request)
            token = request.cookies.get(COOKIE)
            public = request.url.path in ("/api/v1/auth/csrf", "/api/v1/auth/login")
            if not public:
                request.state.web_actor = await run_in_threadpool(sessions.authenticate, token)
                path = request.url.path
                if not path.startswith("/api/v1/auth/"):
                    from commerceops.infrastructure.replenishment_repository import has_capability

                    def permitted_path() -> None:
                        with connect(store.settings) as db:
                            subject = cast(WebActor, request.state.web_actor)
                            roles = (
                                ("admin",)
                                if path.startswith("/api/v1/admin/")
                                else ("operator", "approver")
                            )
                            if not any(has_capability(db, subject, role) for role in roles):
                                raise WebFailure("ACCESS_DENIED", 403)

                    await run_in_threadpool(permitted_path)
            if request.method == "POST":
                if origin not in config.origins:
                    raise WebFailure("ORIGIN_DENIED", 403)
                await run_in_threadpool(
                    sessions.check_csrf, token, request.headers.get("x-csrf-token")
                )
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            response.headers["Vary"] = "Cookie, Origin"
            return response
        except WebFailure as failure:
            failure_response = await run_in_threadpool(
                failure_response_for, failure.code, failure.status
            )
            if request.headers.get("origin") in config.origins:
                failure_response.headers["Access-Control-Allow-Origin"] = request.headers["origin"]
                failure_response.headers["Access-Control-Allow-Credentials"] = "true"
            return failure_response
        except (psycopg.Error, OSError, ValueError):
            failure_response = error_response("SERVICE_UNAVAILABLE", 503)
            if request.headers.get("origin") in config.origins:
                failure_response.headers["Access-Control-Allow-Origin"] = request.headers["origin"]
                failure_response.headers["Access-Control-Allow-Credentials"] = "true"
            return failure_response

    @app.exception_handler(WebFailure)
    async def invalid_web(request: Request, failure: WebFailure) -> JSONResponse:
        return await run_in_threadpool(failure_response_for, failure.code, failure.status)

    @app.exception_handler(HTTPException)
    async def http_failure(request: Request, failure: HTTPException) -> Any:
        if request.url.path.startswith("/api/v1/"):
            code = "RESOURCE_NOT_FOUND" if failure.status_code == 404 else "INVALID_REQUEST"
            return await run_in_threadpool(failure_response_for, code, failure.status_code)
        return await http_exception_handler(request, failure)

    @app.exception_handler(ValidationError)
    async def invalid_shape(request: Request, failure: ValidationError) -> JSONResponse:
        if request.url.path.startswith("/api/v1/"):
            return await run_in_threadpool(failure_response_for, "INVALID_REQUEST", 422)
        return error_response("INVALID_REQUEST", 400)

    def actor(request: Request) -> WebActor:
        return cast(WebActor, request.state.web_actor)

    def response(
        data: dict[str, Any], status: int = 200, issued: str | None = None
    ) -> JSONResponse:
        result = JSONResponse(content=data, status_code=status)
        if issued:
            result.set_cookie(
                COOKIE,
                issued,
                httponly=True,
                secure=config.transport_mode == "https",
                samesite="lax",
                path="/",
                max_age=config.session_absolute_seconds,
            )
        return result

    @router.get("/auth/csrf")
    def csrf(request: Request) -> JSONResponse:
        issued, data = sessions.bootstrap(request.cookies.get(COOKIE))
        result = response(data, issued=issued)
        if issued and data["identity_mode"] == "anonymous_bootstrap":
            result.set_cookie(
                COOKIE,
                issued,
                httponly=True,
                secure=config.transport_mode == "https",
                samesite="lax",
                path="/",
                max_age=300,
            )
        return result

    @router.post("/auth/login")
    async def login(request: Request) -> JSONResponse:
        payload = LoginInput.model_validate_json(await body(request))
        peer = request.client.host if request.client else "unknown"
        issued, data = await run_in_threadpool(
            sessions.login, request.cookies.get(COOKIE) or "", payload.login, payload.password, peer
        )
        return response(data, issued=issued)

    @router.get("/auth/session")
    def session(request: Request) -> JSONResponse:
        return response(sessions.read(request.cookies.get(COOKIE)))

    @router.post("/auth/logout")
    async def logout(request: Request) -> JSONResponse:
        LogoutInput.model_validate_json(await body(request))
        result = response(await run_in_threadpool(sessions.logout, request.cookies.get(COOKIE)))
        result.delete_cookie(
            COOKIE, path="/", httponly=True, secure=config.transport_mode == "https", samesite="lax"
        )
        return result

    @router.post("/tasks")
    async def create(request: Request) -> JSONResponse:
        # 创建能力先于typed body校验；admin-only不能探测绑定错误。
        from commerceops.infrastructure.database import connect
        from commerceops.infrastructure.replenishment_repository import has_capability

        def permitted() -> None:
            with connect(store.settings) as db:
                if not has_capability(db, actor(request), "operator"):
                    raise WebFailure("ACCESS_DENIED", 403)

        await run_in_threadpool(permitted)
        payload: CreateInput = TypeAdapter(CreateInput).validate_json(await body(request))
        return response(await run_in_threadpool(store.create, actor(request), payload), 202)

    @router.get("/tasks")
    def tasks(request: Request) -> JSONResponse:
        try:
            limit = int(request.query_params.get("limit", "20"))
        except ValueError:
            raise WebFailure("INVALID_REQUEST", 422) from None
        return response(
            reads.tasks(
                actor(request),
                limit,
                request.query_params.get("state"),
                request.query_params.get("kind"),
                request.query_params.get("cursor"),
            )
        )

    @router.get("/tasks/{task_id}")
    def task(request: Request, task_id: str) -> JSONResponse:
        return response(reads.read_task(actor(request), parsed_uuid(task_id)))

    @router.get("/tasks/{task_id}/report")
    def report(request: Request, task_id: str) -> JSONResponse:
        report_id = request.query_params.get("report_id")
        return response(
            reads.report(
                actor(request), parsed_uuid(task_id), parsed_uuid(report_id) if report_id else None
            )
        )

    @router.get("/tasks/{task_id}/plans/{plan_version}")
    def plan(request: Request, task_id: str, plan_version: str) -> JSONResponse:
        try:
            version = int(plan_version)
        except ValueError:
            raise WebFailure("RESOURCE_NOT_FOUND", 404) from None
        return response(reads.plan(actor(request), parsed_uuid(task_id), version))

    @router.get("/approvals/{approval_id}")
    def approval(request: Request, approval_id: str) -> JSONResponse:
        return response(reads.approval(actor(request), parsed_uuid(approval_id)))

    @router.post("/approvals/{approval_id}/decision")
    async def decide(request: Request, approval_id: str) -> JSONResponse:
        identifier = parsed_uuid(approval_id)
        # 当前查看/操作能力先于body字段；原actor有当前查看权可重投原决定。
        await run_in_threadpool(decisions.authorize, actor(request), identifier)
        payload = DecisionInput.model_validate_json(await body(request))
        return response(
            await run_in_threadpool(decisions.decide, actor(request), identifier, payload)
        )

    @router.get("/requests/{request_key}")
    def receipt(request: Request, request_key: str) -> JSONResponse:
        operation = request.query_params.get("operation")
        if operation not in ("create_task", "decision", "resolve"):
            raise WebFailure("INVALID_REQUEST", 422)
        return response(reads.request(actor(request), parsed_uuid(request_key), operation))

    def limit_of(request: Request) -> int:
        try:
            return int(request.query_params.get("limit", "20"))
        except ValueError:
            raise WebFailure("INVALID_REQUEST", 422) from None

    @router.get("/replenishment-items")
    def item_list(request: Request) -> JSONResponse:
        return response(
            items.list(
                actor(request),
                state=request.query_params.get("state"),
                limit=limit_of(request),
                cursor=request.query_params.get("cursor"),
            )
        )

    @router.get("/tasks/{task_id}/execution")
    def execution_read(request: Request, task_id: str) -> JSONResponse:
        return response(reads.execution(actor(request), parsed_uuid(task_id)))

    @router.get("/replenishment-items/{item_id}")
    def item_read(request: Request, item_id: str) -> JSONResponse:
        return response(items.read(actor(request), parsed_uuid(item_id)))

    @router.post("/replenishment-items/{item_id}/resolve")
    async def item_resolve(request: Request, item_id: str) -> JSONResponse:
        identifier = parsed_uuid(item_id)
        await run_in_threadpool(items.authorize, actor(request), identifier)
        payload = ResolveInput.model_validate_json(await body(request))
        return response(await run_in_threadpool(items.resolve, actor(request), identifier, payload))

    @router.get("/config")
    def configuration(request: Request) -> JSONResponse:
        shop = request.query_params.get("shop_id")
        if not shop:
            raise WebFailure("INVALID_REQUEST", 422)
        return response(reads.config_read(actor(request), parsed_uuid(shop)))

    @router.get("/admin/operations")
    def operations(request: Request) -> JSONResponse:
        return response(reads.operations(actor(request)))

    @router.get("/tasks/{task_id}/plans")
    def versions(request: Request, task_id: str) -> JSONResponse:
        return response(
            reads.plans(
                actor(request),
                parsed_uuid(task_id),
                limit_of(request),
                request.query_params.get("cursor"),
            )
        )

    @router.get("/tasks/{task_id}/events")
    def events(request: Request, task_id: str) -> JSONResponse:
        return response(
            reads.events(
                actor(request),
                parsed_uuid(task_id),
                limit_of(request),
                request.query_params.get("cursor"),
            )
        )

    @router.get("/approvals")
    def approvals(request: Request) -> JSONResponse:
        return response(
            reads.approvals(
                actor(request),
                limit_of(request),
                request.query_params.get("state"),
                request.query_params.get("view", "visible"),
                request.query_params.get("cursor"),
            )
        )

    @router.get("/tasks/{task_id}/explanation")
    async def explanation(request: Request, task_id: str) -> JSONResponse:
        report_id = request.query_params.get("report_id")
        if not report_id:
            raise WebFailure("INVALID_REQUEST", 422)
        return response(
            await run_in_threadpool(
                lambda: asyncio.run(
                    reads.explanation(actor(request), parsed_uuid(task_id), parsed_uuid(report_id))
                )
            )
        )

    app.include_router(router)
