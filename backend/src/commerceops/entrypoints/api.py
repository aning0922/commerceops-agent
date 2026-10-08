"""P1-01 本机 liveness 入口，不代表数据库或业务 readiness。"""

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, ValidationError

from commerceops.infrastructure.config import Settings


class Liveness(BaseModel):
    status: str = "ok"
    service: str = "commerceops-api"


def create_app() -> FastAPI:
    app = FastAPI(title="CommerceOps Agent", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health/live", response_model=Liveness)
    def liveness() -> Liveness:
        return Liveness()

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
