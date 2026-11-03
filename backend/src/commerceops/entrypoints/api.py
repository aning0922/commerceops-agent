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
from commerceops.infrastructure.daily_sources import DailyDeployment
from commerceops.infrastructure.inventory_repository import InventoryReadStore
from commerceops.infrastructure.knowledge_copy_config import CopyDeployment, load_copy_deployment
from commerceops.infrastructure.knowledge_copy_draft_store import CopyStore
from commerceops.infrastructure.readonly_inquiry_config import InquiryDeployment
from commerceops.infrastructure.readonly_inquiry_store import InquiryConfig, InquiryStore
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
    daily_enabled: bool = False,
    daily_files: DailyDeployment | None = None,
    inquiry_config: InquiryConfig | None = None,
    copy_deployment: CopyDeployment | None = None,
) -> FastAPI:
    if inquiry_config is not None and (web_config is None or replenishment_store is None):
        raise ValueError("inquiry requires explicit Web session configuration")
    if (
        copy_deployment is not None
        and copy_deployment.enabled
        and (web_config is None or replenishment_store is None)
    ):
        raise ValueError("copy requires explicit Web session configuration")
    app = FastAPI(title="CommerceOps Agent", docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        if request.url.path.startswith("/api/v1/"):
            if hasattr(app.state, "inquiry_openapi") and (
                request.url.path == "/api/v1/readonly-inquiries"
                or request.url.path.startswith("/api/v1/readonly-inquiries/")
            ):
                from commerceops.entrypoints.inquiry_http import failure

                return failure("INVALID_REQUEST", 422)
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
        if daily_enabled:
            from commerceops.entrypoints.daily_http import daily_openapi, install_daily
            from commerceops.infrastructure.daily_operations import DailyOperations
            from commerceops.infrastructure.daily_read import DailyReadStore

            install_daily(
                app,
                DailyReadStore(
                    replenishment_store.settings,
                    operations_enabled=daily_files is not None,
                    schedules_enabled=daily_files.schedules_enabled if daily_files else False,
                ),
                DailyOperations(replenishment_store.settings, daily_files, web_config.csrf_secret)
                if daily_files
                else None,
            )
            app.state.daily_openapi = daily_openapi()
    if inquiry_config is not None and web_config is not None:
        from commerceops.entrypoints.inquiry_http import inquiry_openapi, inquiry_router
        from commerceops.infrastructure.web_sessions import SessionStore

        app.include_router(
            inquiry_router(
                InquiryStore(web_config, inquiry_config), SessionStore(web_config), web_config
            )
        )
        app.state.inquiry_openapi = inquiry_openapi()
    if copy_deployment is not None and copy_deployment.enabled and web_config is not None:
        from commerceops.entrypoints.knowledge_copy_http import knowledge_copy_router
        from commerceops.entrypoints.knowledge_copy_openapi import copy_openapi

        app.include_router(
            knowledge_copy_router(
                web_config, CopyStore(web_config.database, copy_deployment.queries())
            )
        )
        app.state.copy_openapi = copy_openapi()
    # 所有请求校验错误均由固定400处理，移除FastAPI默认422文档。
    schema = app.openapi()
    if daily_enabled:
        from commerceops.entrypoints.daily_http import separate_legacy

        schema = separate_legacy(schema)
    if hasattr(app.state, "copy_openapi"):
        from commerceops.entrypoints.knowledge_copy_openapi import separate_copy_legacy

        schema = separate_copy_legacy(schema)
    if hasattr(app.state, "inquiry_openapi"):
        for path in app.state.inquiry_openapi["paths"]:
            schema["paths"].pop(path, None)
    for path, operations in schema["paths"].items():
        if path.startswith("/tasks/"):
            operations["get"]["responses"].pop("422", None)
    schema["paths"]["/test/route"]["post"]["responses"].pop("422", None)
    schema["paths"]["/test/routes/{task_id}"]["get"]["responses"].pop("422", None)
    if web_config is not None and replenishment_store is not None:
        from commerceops.entrypoints.web_openapi import export_web

        schema = export_web(schema)
    # Dedicated inquiry contract is exported separately; original contracts remain exact.
    app.openapi_schema = schema
    return app


def main() -> None:
    try:
        settings = Settings()
    except ValidationError:
        # ValidationError 的原始输入可能包含秘密；入口只输出固定提示。
        raise SystemExit("启动配置无效，请检查 COMMERCEOPS_HOST/PORT/LOG_LEVEL") from None
    config_path = os.environ.get("COMMERCEOPS_P3_CONFIG_FILE")
    if os.environ.get("COMMERCEOPS_M3_INQUIRY_CONFIG_FILE") and not config_path:
        raise SystemExit("inquiry requires explicit Web session configuration")
    copy_enabled = os.environ.get("COMMERCEOPS_M3_COPY_ENABLED", "false")
    if copy_enabled not in ("true", "false") or (copy_enabled == "true" and not config_path):
        raise SystemExit("copy requires explicit enabled and Web configuration")
    app = create_app()
    if config_path:
        try:
            config = WebConfig.from_file(Path(config_path))
            store = ReplenishmentStore(config, Path("tests/fixtures/commerce/inventory-v1"))
            app = create_app(
                web_config=config,
                replenishment_store=store,
                daily_enabled=os.environ.get("COMMERCEOPS_M3_DAILY_CONFIG_FILE") is not None,
                daily_files=DailyDeployment.load(
                    Path(os.environ["COMMERCEOPS_M3_DAILY_CONFIG_FILE"])
                )
                if os.environ.get("COMMERCEOPS_M3_DAILY_CONFIG_FILE")
                else None,
                inquiry_config=InquiryDeployment.load(
                    Path(os.environ["COMMERCEOPS_M3_INQUIRY_CONFIG_FILE"])
                ).runtime()
                if os.environ.get("COMMERCEOPS_M3_INQUIRY_CONFIG_FILE")
                else None,
                copy_deployment=load_copy_deployment(
                    Path(os.environ["COMMERCEOPS_M3_COPY_CONFIG_FILE"])
                    if os.environ.get("COMMERCEOPS_M3_COPY_CONFIG_FILE")
                    else None,
                    enabled=copy_enabled == "true",
                    expected_sha256=os.environ.get("COMMERCEOPS_M3_COPY_CONFIG_SHA256"),
                ),
            )
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
