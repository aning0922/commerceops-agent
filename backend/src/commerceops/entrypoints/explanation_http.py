"""P204仅受控test路由与只读说明cache，GET不能发模型/创建任务。"""

from typing import Any
from uuid import UUID

import psycopg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from commerceops.application.commerce.analysis_task import InventoryTaskRequest, TrustedReadIdentity
from commerceops.application.commerce.explanation_read import (
    ExplanationError,
    ExplanationRead,
    IntentQueuedRead,
    IntentRead,
    RoutingRead,
)
from commerceops.application.commerce.explanation_task import ExplanationTaskRequest, logical_key
from commerceops.application.commerce.inventory_routing import GuardedRouter, RoutingInput
from commerceops.entrypoints.inventory_http import IdentityResolver
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.explanation_repository import (
    ExplanationStore,
    create_explanation_task,
    payload,
    trusted_parent,
    validated_row,
)
from commerceops.infrastructure.intent_repository import create_intent_task, read_intent
from commerceops.infrastructure.inventory_repository import (
    AnalysisUnsafe,
    InventoryReadStore,
    ReadFailure,
    _authorize,
    _stored,
    create_analysis_task,
)


class ExplanationEndpoints:
    def __init__(self, settings: DatabaseSettings, router: GuardedRouter | None = None):
        self.settings, self.router = settings, router or GuardedRouter()

    async def cached(self, identity: TrustedReadIdentity, parent: UUID) -> dict[str, Any]:
        try:
            with connect(self.settings) as db:
                task, report = trusted_parent(db, identity, parent)
                row = db.execute(
                    """SELECT e.*,t.normalized_request FROM business.model_explanations e
                    JOIN business.explanation_links l ON l.child_task_id=e.child_task_id
                    JOIN business.business_tasks t ON t.id=e.child_task_id
                    JOIN business.explanation_task_results x
                    ON x.child_task_id=t.id AND x.result_id=e.id
                    WHERE e.organization_id=%s AND e.shop_id=%s AND e.parent_task_id=%s
                    AND l.requester_id=%s AND e.report_id=%s AND e.facts_hash=%s
                    ORDER BY e.created_at DESC,e.id DESC LIMIT 1""",
                    (
                        identity.organization_id,
                        identity.shop_id,
                        parent,
                        identity.principal_id,
                        report["id"],
                        report["facts_hash"],
                    ),
                ).fetchone()
                if row is None:
                    raise ReadFailure("EXPLANATION_NOT_READY", 409)
                import json

                req = ExplanationTaskRequest.model_validate_json(
                    json.dumps(row["normalized_request"])
                )
                if req.logical_key != logical_key(
                    identity.organization_id,
                    identity.shop_id,
                    identity.principal_id,
                    parent,
                    report["id"],
                    report["facts_hash"],
                    req.body_hash,
                    req.evidence_mode,
                ):
                    raise AnalysisUnsafe("EXPLANATION_BODY_INVALID")
                result = validated_row(row, req, identity.organization_id, identity.shop_id)
                await ExplanationStore.verify(
                    result, _stored(report, task["normalized_request"]).report, req
                )
                return {
                    "schema_version": "p204-read-v1",
                    "analysis_only": True,
                    "execution_available": False,
                    "identity_mode": "simulated",
                    "task_id": str(parent),
                    "explanation_id": str(row["id"]),
                    "child_task_id": str(row["child_task_id"]),
                    "result": payload(result),
                }
        except ReadFailure:
            raise
        except (psycopg.Error, AnalysisUnsafe, ValueError, TypeError, KeyError, OSError):
            raise ReadFailure("DATABASE_UNAVAILABLE", 503) from None

    async def route(self, identity: TrustedReadIdentity, request: RoutingInput) -> dict[str, Any]:
        try:
            with connect(self.settings) as db:
                _authorize(db, identity)
            if self.router.port is None:
                task, job = create_intent_task(self.settings, identity, request, "template")
                return {
                    "schema_version": "p204-route-queued-v1",
                    "analysis_only": True,
                    "execution_available": False,
                    "identity_mode": "simulated",
                    "task_id": str(task),
                    "job_id": str(job),
                    "state": "queued",
                }
            decision = await self.router.route(request)
            if decision.intent == "inventory_replenishment" and any(
                source != "explicit_text" for source in decision.parameter_sources.values()
            ):
                decision = decision.model_copy(
                    update={"intent": "clarify", "safe_reason": "PARAMETER_CONFIRMATION_REQUIRED"}
                )
            response: dict[str, Any] = {
                "decision": decision.model_dump(mode="json"),
                "identity_mode": "simulated",
                "created_task_id": None,
                "job_id": None,
            }
            if decision.intent == "inventory_replenishment":
                with connect(self.settings) as db:
                    _authorize(db, identity)
                    row = db.execute(
                        """SELECT id FROM business.conversations WHERE organization_id=%s
                        AND actor_id=%s ORDER BY id LIMIT 1""",
                        (identity.organization_id, identity.principal_id),
                    ).fetchone()
                    if row is None:
                        raise ReadFailure("CONVERSATION_NOT_READY", 409)
                task, job = create_analysis_task(
                    self.settings,
                    identity,
                    row["id"],
                    InventoryTaskRequest(
                        L=decision.parameters["L"],
                        R=decision.parameters["R"],
                        S=decision.parameters["S"],
                    ),
                )
                response.update(created_task_id=str(task), job_id=str(job))
            elif decision.intent in ("explain_report", "task_status"):
                if request.context_task_id is None:
                    raise ReadFailure("TASK_NOT_FOUND", 404)
                if decision.intent == "task_status":
                    response["task"] = InventoryReadStore(self.settings).read(
                        identity, request.context_task_id, "task"
                    )
                else:
                    task, job = create_explanation_task(
                        self.settings, identity, request.context_task_id, "template"
                    )
                    response.update(created_task_id=str(task), job_id=str(job))
            return response
        except ReadFailure:
            raise
        except (psycopg.Error, ValueError, OSError):
            raise ReadFailure("DATABASE_UNAVAILABLE", 503) from None


def explanation_router(
    service: ExplanationEndpoints | None, resolver: IdentityResolver | None
) -> APIRouter:
    router = APIRouter()

    def identity(request: Request) -> TrustedReadIdentity:
        selected = resolver(request) if resolver else None
        if selected is None:
            raise ReadFailure("IDENTITY_REQUIRED", 401)
        if not isinstance(selected, TrustedReadIdentity):
            raise ReadFailure("IDENTITY_SCOPE_DENIED", 403)
        return selected

    def error(failure: ReadFailure) -> JSONResponse:
        return JSONResponse(
            status_code=failure.status,
            content={
                "schema_version": "p204-read-v1",
                "analysis_only": True,
                "execution_available": False,
                "error": {"code": failure.code, "safe_message": failure.code},
            },
        )

    errors: dict[int | str, dict[str, Any]] = {
        code: {"model": ExplanationError} for code in (400, 401, 403, 404, 409, 503)
    }

    @router.get("/tasks/{task_id}/explanation", response_model=ExplanationRead, responses=errors)
    async def get(request: Request, task_id: str) -> Any:
        try:
            actor = identity(request)
            try:
                task = UUID(task_id)
            except ValueError:
                raise ReadFailure("TASK_NOT_FOUND", 404) from None
            if service is None:
                raise ReadFailure("DATABASE_UNAVAILABLE", 503)
            return await service.cached(actor, task)
        except ReadFailure as failure:
            return error(failure)

    @router.post(
        "/test/route",
        response_model=RoutingRead | IntentQueuedRead,
        responses=errors,
        response_model_exclude_none=True,
    )
    async def route(request: Request, body: RoutingInput) -> Any:
        try:
            actor = identity(request)
            if service is None:
                raise ReadFailure("DATABASE_UNAVAILABLE", 503)
            return await service.route(actor, body)
        except ReadFailure as failure:
            return error(failure)

    @router.get("/test/routes/{task_id}", response_model=IntentRead, responses=errors)
    async def route_result(request: Request, task_id: str) -> Any:
        try:
            actor = identity(request)
            try:
                task = UUID(task_id)
            except ValueError:
                raise ReadFailure("TASK_NOT_FOUND", 404) from None
            if service is None:
                raise ReadFailure("DATABASE_UNAVAILABLE", 503)
            return await read_intent(service.settings, actor, task)
        except ReadFailure as failure:
            return error(failure)

    return router
