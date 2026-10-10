"""P1-01 本机 liveness 入口，不代表数据库或业务 readiness。"""

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from commerceops.entrypoints.inventory_http import IdentityResolver, inventory_router
from commerceops.infrastructure.config import Settings
from commerceops.infrastructure.inventory_repository import InventoryReadStore


class Liveness(BaseModel):
    status: str = "ok"
    service: str = "commerceops-api"


def create_app(
    *,
    inventory_store: InventoryReadStore | None = None,
    identity_resolver: IdentityResolver | None = None,
) -> FastAPI:
    app = FastAPI(title="CommerceOps Agent", docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "schema_version": "p203-read-v1",
                "analysis_only": True,
                "execution_available": False,
                "error": {"code": "INVALID_REQUEST", "safe_message": "INVALID_REQUEST"},
            },
        )

    @app.get("/health/live", response_model=Liveness)
    def liveness() -> Liveness:
        return Liveness()

    app.include_router(inventory_router(inventory_store, identity_resolver))
    # 所有请求校验错误均由固定400处理，移除FastAPI默认422文档。
    schema = app.openapi()
    for path, operations in schema["paths"].items():
        if path.startswith("/tasks/"):
            operations["get"]["responses"].pop("422", None)
    app.openapi_schema = schema
    return app


def main() -> None:
    try:
        settings = Settings()
    except ValidationError:
        # ValidationError 的原始输入可能包含秘密；入口只输出固定提示。
        raise SystemExit("启动配置无效，请检查 COMMERCEOPS_HOST/PORT/LOG_LEVEL") from None
    uvicorn.run(create_app(), host=settings.host, port=settings.port, log_level=settings.log_level)


if __name__ == "__main__":
    main()
