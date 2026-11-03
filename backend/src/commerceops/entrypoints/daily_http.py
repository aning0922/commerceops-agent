"""日报独立GET与OpenAPI；沿用现有P3 session边界，不改变旧操作合同。"""

import copy
import json
from importlib.resources import files
from typing import Any, cast

from fastapi import FastAPI, Request

from commerceops.application.daily.read_models import DailyRead
from commerceops.application.replenishment.contracts import WebActor
from commerceops.entrypoints.replenishment_http import parsed_uuid
from commerceops.infrastructure.daily_read import DailyReadStore

PATH = "/api/v1/daily-reports/{task_id}"


def install_daily(app: FastAPI, store: DailyReadStore) -> None:
    @app.get(PATH, response_model=DailyRead)
    def daily_report(request: Request, task_id: str) -> Any:
        return store.read(cast(WebActor, request.state.web_actor), parsed_uuid(task_id))


def daily_openapi() -> dict[str, Any]:
    body = DailyRead.model_json_schema(
        mode="serialization", ref_template="#/components/schemas/{model}"
    )
    models = body.pop("$defs")
    models["DailyRead"] = body
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
    responses = {
        "200": {
            "description": "授权owner的日报详情",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/DailyRead"}}},
        }
    }
    errors = legacy["paths"]["/api/v1/tasks/{task_id}"]["get"]["responses"]
    responses.update({code: copy.deepcopy(errors[code]) for code in ("401", "403", "404", "503")})
    return {
        "openapi": "3.1.0",
        "info": {"title": "CommerceOps Daily Read", "version": "p6-m3-web-v1"},
        "paths": {
            PATH: {
                "get": {
                    "operationId": "read_daily_report",
                    "parameters": [
                        {
                            "name": "task_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        }
                    ],
                    "responses": responses,
                    "security": [{"SessionCookie": []}],
                }
            }
        },
        "components": {
            "schemas": models,
            "securitySchemes": legacy["components"]["securitySchemes"],
        },
    }


def separate_legacy(schema: dict[str, Any]) -> dict[str, Any]:
    """P3/P4/P5原完整schema不偷偷增加日报操作或models；新合同在独立asset。"""
    schema["paths"].pop(PATH, None)
    new_names = set(DailyRead.model_json_schema()["$defs"]) | {"DailyRead"}
    for name in new_names:
        schema.get("components", {}).get("schemas", {}).pop(name, None)
    return schema
