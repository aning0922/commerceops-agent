"""日报独立GET与OpenAPI；沿用现有P3 session边界，不改变旧操作合同。"""

import copy
import json
from importlib.resources import files
from typing import Any, cast

from fastapi import FastAPI, Request
from pydantic import BaseModel

from commerceops.application.daily.http_models import (
    AcceptanceRead,
    CapabilityRead,
    CreateDailyInput,
    EvidenceRead,
    QuestionRead,
)
from commerceops.application.daily.questions import QuestionInput
from commerceops.application.daily.read_models import DailyRead
from commerceops.application.replenishment.contracts import WebActor
from commerceops.entrypoints.replenishment_http import parsed_uuid
from commerceops.infrastructure.daily_operations import DailyOperations
from commerceops.infrastructure.daily_read import DailyReadStore
from commerceops.infrastructure.daily_sources import checked_json

PATH = "/api/v1/daily-reports/{task_id}"
DAILY_PATHS = {
    PATH,
    "/api/v1/daily-capabilities",
    "/api/v1/daily-reports",
    PATH + "/questions",
    PATH + "/questions/{question_id}",
    PATH + "/evidence",
}


def install_daily(
    app: FastAPI, store: DailyReadStore, operations: DailyOperations | None = None
) -> None:
    @app.get(PATH, response_model=DailyRead)
    def daily_report(request: Request, task_id: str) -> Any:
        payload = store.read(cast(WebActor, request.state.web_actor), parsed_uuid(task_id))
        # strict DTO的JSON形式包含UUID/时间字符串及数组；不能将wire dict按Python再次校验。
        return DailyRead.model_validate_json(json.dumps(payload))

    if operations is None:
        return

    def actor(request: Request) -> WebActor:
        return cast(WebActor, request.state.web_actor)

    async def input_body(request: Request, model: type[BaseModel]) -> Any:
        from commerceops.application.replenishment.contracts import WebFailure

        raw = await request.body()
        if len(raw) > 32768:
            raise WebFailure("INVALID_REQUEST", 422)
        try:
            checked_json(raw)
            return model.model_validate_json(raw)
        except ValueError:
            raise WebFailure("INVALID_REQUEST", 422) from None

    @app.get("/api/v1/daily-capabilities", response_model=CapabilityRead)
    def capabilities(request: Request, shop_id: str) -> Any:
        return operations.capabilities(actor(request), parsed_uuid(shop_id))

    @app.post("/api/v1/daily-reports", status_code=202, response_model=AcceptanceRead)
    async def create_report(request: Request) -> Any:
        from starlette.concurrency import run_in_threadpool

        body = await input_body(request, CreateDailyInput)
        return await run_in_threadpool(operations.create, actor(request), body)

    @app.post(PATH + "/questions", status_code=202, response_model=AcceptanceRead)
    async def create_question(request: Request, task_id: str) -> Any:
        from starlette.concurrency import run_in_threadpool

        body = await input_body(request, QuestionInput)
        return await run_in_threadpool(
            operations.create_question, actor(request), parsed_uuid(task_id), body
        )

    @app.get(PATH + "/questions/{question_id}", response_model=QuestionRead)
    def question(
        request: Request, task_id: str, question_id: str, cursor: str | None = None
    ) -> Any:
        return operations.question(
            actor(request), parsed_uuid(task_id), parsed_uuid(question_id), cursor
        )

    @app.get(PATH + "/evidence", response_model=EvidenceRead)
    def evidence(request: Request, task_id: str, report_id: str, cursor: str | None = None) -> Any:
        return operations.evidence(
            actor(request), parsed_uuid(task_id), parsed_uuid(report_id), cursor
        )


def daily_openapi() -> dict[str, Any]:
    app = FastAPI(title="CommerceOps Daily", version="p6-m3-web-v1")
    install_daily(app, cast(DailyReadStore, None), cast(DailyOperations, object()))
    schema = app.openapi()
    models = schema["components"]["schemas"]
    for model in (CreateDailyInput, QuestionInput):
        body = model.model_json_schema(
            mode="validation", ref_template="#/components/schemas/{model}"
        )
        models.update(body.pop("$defs", {}))
        models[model.__name__] = body
    legacy = json.loads(files("commerceops.assets").joinpath("p3-web-v1.openapi.json").read_text())
    # Only the existing fixed error DTO dependency closure, not any legacy operations.
    pending = ["Error"]
    while pending:
        name = pending.pop()
        if name in models:
            continue
        definition = legacy["components"]["schemas"][name]
        models[name] = copy.deepcopy(definition)

        def refs(value: Any) -> None:
            if isinstance(value, dict):
                if "$ref" in value:
                    pending.append(value["$ref"].rsplit("/", 1)[-1])
                for child in value.values():
                    refs(child)
            elif isinstance(value, list):
                for child in value:
                    refs(child)

        refs(definition)
    errors = legacy["paths"]["/api/v1/tasks/{task_id}"]["get"]["responses"]
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            operation["security"] = [{"SessionCookie": []}]
            for code in ("401", "403", "404", "503"):
                operation["responses"][code] = copy.deepcopy(errors[code])
            for code in ("409", "422"):
                operation["responses"][code] = {
                    "description": "固定安全错误",
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
                    },
                }
            if method == "post":
                model_name = (
                    "CreateDailyInput" if path == "/api/v1/daily-reports" else "QuestionInput"
                )
                operation["requestBody"] = {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/" + model_name}
                        }
                    },
                }
    models.pop("HTTPValidationError", None)
    models.pop("ValidationError", None)
    schema["components"]["securitySchemes"] = legacy["components"]["securitySchemes"]
    return schema


def separate_legacy(schema: dict[str, Any]) -> dict[str, Any]:
    """P3/P4/P5原完整schema不偷偷增加日报操作或models；新合同在独立asset。"""
    for path in list(schema["paths"]):
        if path.startswith(("/api/v1/daily-reports", "/api/v1/daily-capabilities")):
            schema["paths"].pop(path)
    legacy_names = set(
        json.loads(files("commerceops.assets").joinpath("p3-web-v1.openapi.json").read_text())[
            "components"
        ]["schemas"]
    )
    new_names = set(daily_openapi()["components"]["schemas"]) - legacy_names
    for name in new_names:
        schema.get("components", {}).get("schemas", {}).pop(name, None)
    return schema
