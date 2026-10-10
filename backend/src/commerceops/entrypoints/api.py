"""P1-01 本机 liveness 入口，不代表数据库或业务 readiness。"""

import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from commerceops.entrypoints.explanation_http import ExplanationEndpoints, explanation_router
from commerceops.entrypoints.inventory_http import IdentityResolver, inventory_router
from commerceops.infrastructure.config import Settings
from commerceops.infrastructure.inventory_repository import InventoryReadStore
from commerceops.infrastructure.replenishment_repository import ReplenishmentStore
from commerceops.infrastructure.web_config import WebConfig


class Liveness(BaseModel):
    status: str = "ok"
    service: str = "commerceops-api"


def create_app(
    *,
    inventory_store: InventoryReadStore | None = None,
    identity_resolver: IdentityResolver | None = None,
    explanation_service: ExplanationEndpoints | None = None,
    web_config: WebConfig | None = None,
    replenishment_store: ReplenishmentStore | None = None,
) -> FastAPI:
    app = FastAPI(title="CommerceOps Agent", docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        if request.url.path.startswith("/api/v1/"):
            from commerceops.entrypoints.replenishment_http import error_response

            return error_response("INVALID_REQUEST", 422)
        return JSONResponse(
            status_code=400,
            content={
                "schema_version": "p204-read-v1"
                if request.url.path.startswith("/test/route")
                or request.url.path.endswith("/explanation")
                else "p203-read-v1",
                "analysis_only": True,
                "execution_available": False,
                "error": {"code": "INVALID_REQUEST", "safe_message": "INVALID_REQUEST"},
            },
        )

    @app.get("/health/live", response_model=Liveness)
    def liveness() -> Liveness:
        return Liveness()

    app.include_router(inventory_router(inventory_store, identity_resolver))
    app.include_router(explanation_router(explanation_service, identity_resolver))
    if web_config is not None and replenishment_store is not None:
        from commerceops.entrypoints.replenishment_http import install_web

        install_web(app, web_config, replenishment_store)
    # 所有请求校验错误均由固定400处理，移除FastAPI默认422文档。
    schema = app.openapi()
    for path, operations in schema["paths"].items():
        if path.startswith("/tasks/"):
            operations["get"]["responses"].pop("422", None)
    schema["paths"]["/test/route"]["post"]["responses"].pop("422", None)
    schema["paths"]["/test/routes/{task_id}"]["get"]["responses"].pop("422", None)
    if web_config is not None and replenishment_store is not None:
        from commerceops.entrypoints.web_openapi import export_web

        schema = export_web(schema)
    app.openapi_schema = schema
    return app


def main() -> None:
    try:
        settings = Settings()
    except ValidationError:
        # ValidationError 的原始输入可能包含秘密；入口只输出固定提示。
        raise SystemExit("启动配置无效，请检查 COMMERCEOPS_HOST/PORT/LOG_LEVEL") from None
    config_path = os.environ.get("COMMERCEOPS_P3_CONFIG_FILE")
    app = create_app()
    if config_path:
        try:
            config = WebConfig.from_file(Path(config_path))
            store = ReplenishmentStore(config, Path("tests/fixtures/commerce/inventory-v1"))
            app = create_app(web_config=config, replenishment_store=store)
        except (ValueError, OSError):
            raise SystemExit("P3配置无效，请核对本阶段私有配置") from None
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
