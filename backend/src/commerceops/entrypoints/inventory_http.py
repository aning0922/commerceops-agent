"""P203只读路由；默认无可信resolver失败关闭，无正式session/登录。"""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from commerceops.application.commerce.analysis_task import TrustedReadIdentity
from commerceops.application.commerce.read_models import ErrorRead, EventsRead, ReportRead, TaskRead
from commerceops.infrastructure.inventory_repository import InventoryReadStore, ReadFailure

IdentityResolver = Callable[[Request], TrustedReadIdentity | None]


def inventory_router(
    store: InventoryReadStore | None, resolver: IdentityResolver | None
) -> APIRouter:
    router = APIRouter()
    errors: dict[int | str, dict[str, Any]] = {
        status: {"model": ErrorRead} for status in (400, 401, 403, 404, 409, 503)
    }

    def read(
        request: Request,
        task_id: str,
        resource: str,
        limit: int = 50,
        cursor: str | None = Query(None, max_length=2048),
    ) -> Any:
        try:
            identity = resolver(request) if resolver else None
            if identity is None:
                raise ReadFailure("IDENTITY_REQUIRED", 401)
            if not isinstance(identity, TrustedReadIdentity):
                raise ReadFailure("IDENTITY_SCOPE_DENIED", 403)
            try:
                parsed = UUID(task_id)
            except ValueError:
                raise ReadFailure("TASK_NOT_FOUND", 404) from None
            if store is None:
                raise ReadFailure("DATABASE_UNAVAILABLE", 503)
            return store.read(identity, parsed, resource, limit=limit, cursor=cursor)
        except ReadFailure as failure:
            return JSONResponse(
                status_code=failure.status,
                content={
                    "schema_version": "p203-read-v1",
                    "analysis_only": True,
                    "execution_available": False,
                    "error": {"code": failure.code, "safe_message": failure.code},
                },
            )

    @router.get("/tasks/{task_id}", response_model=TaskRead, responses=errors)
    def task(request: Request, task_id: str) -> Any:
        return read(request, task_id, "task")

    @router.get("/tasks/{task_id}/report", response_model=ReportRead, responses=errors)
    def report(request: Request, task_id: str) -> Any:
        return read(request, task_id, "report")

    @router.get(
        "/tasks/{task_id}/events",
        response_model=EventsRead,
        responses=errors,
    )
    def events(
        request: Request,
        task_id: str,
        limit: int = Query(50, ge=1, le=100),
        cursor: str | None = Query(None, max_length=2048),
    ) -> Any:
        return read(request, task_id, "events", limit, cursor)

    return router
