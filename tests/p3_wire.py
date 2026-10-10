"""实际PG/HTTP响应与冻结合同比对；临时jsonschema工具不改生产依赖。

使用自有PG显式数据库配置运行：
uv run --frozen --with jsonschema==4.26.0 python -m tests.p3_wire
不记录响应正文/Cookie/CSRF；只输出operation/status/检查数量。
"""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast
from uuid import UUID, uuid4

from commerceops.entrypoints.api import create_app
from fastapi.testclient import TestClient

from tests.p3_support import ORIGIN, run_graphs
from tests.test_p3_pg import fixture


def main() -> None:
    from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

    spec = json.loads((Path(__file__).parent.parent / "docs/contracts/p3-openapi.json").read_text())
    checks = 0

    def validate(response: Any, path: str, method: str = "get") -> None:
        nonlocal checks
        operation = spec["paths"][path][method]
        schema = operation["responses"][str(response.status_code)]["content"]["application/json"][
            "schema"
        ]
        validator = Draft202012Validator(
            {**schema, "components": spec["components"]}, format_checker=FormatChecker()
        )
        errors = list(validator.iter_errors(response.json()))
        if errors:
            # 错误仅含字段路径/约束名，避免schema错误内容暴露会话值。
            raise RuntimeError(
                operation["operationId"]
                + ": "
                + repr([(list(error.absolute_path), error.validator) for error in errors])
            )
        checks += 1
        print(operation["operationId"], response.status_code)

    with TemporaryDirectory(prefix="p3-wire-") as directory:
        lifecycle = cast(Any, fixture).__wrapped__(Path(directory))
        f = next(lifecycle)
        try:
            validate(f.client.get("/api/v1/auth/session"), "/api/v1/auth/session")
            validate(f.client.get("/api/v1/auth/csrf"), "/api/v1/auth/csrf")
            with TestClient(
                create_app(web_config=f.config, replenishment_store=f.store), base_url=ORIGIN
            ) as anonymous:
                validate(anonymous.get("/api/v1/auth/csrf"), "/api/v1/auth/csrf")
                validate(anonymous.get("/api/v1/auth/session"), "/api/v1/auth/session")
            payload = f.new_cycle("unknown_inbound")
            created = f.client.post("/api/v1/tasks", json=payload, headers=f.headers())
            validate(created, "/api/v1/tasks", "post")
            task = UUID(created.json()["task_id"])
            asyncio.run(run_graphs(f, task))
            detail = f.client.get(f"/api/v1/tasks/{task}")
            validate(detail, "/api/v1/tasks/{task_id}")
            approval_id = detail.json()["approval_id"]
            paths = {
                "/api/v1/tasks": "/api/v1/tasks",
                f"/api/v1/tasks/{task}/report": "/api/v1/tasks/{task_id}/report",
                f"/api/v1/tasks/{task}/plans": "/api/v1/tasks/{task_id}/plans",
                f"/api/v1/tasks/{task}/plans/1": "/api/v1/tasks/{task_id}/plans/{plan_version}",
                f"/api/v1/tasks/{task}/events": "/api/v1/tasks/{task_id}/events",
                "/api/v1/approvals": "/api/v1/approvals",
                f"/api/v1/approvals/{approval_id}": "/api/v1/approvals/{approval_id}",
                f"/api/v1/config?shop_id={f.inventory.data.shop}": "/api/v1/config",
                f"/api/v1/requests/{payload['request_key']}?operation=create_task": (
                    "/api/v1/requests/{request_key}"
                ),
                f"/api/v1/tasks/{uuid4()}": "/api/v1/tasks/{task_id}",
            }
            for url, path in paths.items():
                validate(f.client.get(url), path)
            validate(
                f.client.post(
                    "/api/v1/auth/logout", json={"schema_version": "p3-web-v1"}, headers=f.headers()
                ),
                "/api/v1/auth/logout",
                "post",
            )
            print("P3 actual wire checks", checks)
        finally:
            lifecycle.close()


if __name__ == "__main__":
    main()
