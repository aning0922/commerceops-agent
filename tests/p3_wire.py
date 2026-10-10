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
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.explanation_repository import create_explanation_task
from commerceops.infrastructure.web_sessions import SessionStore
from fastapi.testclient import TestClient

from tests.p3_support import ORIGIN, P3Process
from tests.test_p3_approval_pg import payload as decision_payload
from tests.test_p3_approval_pg import wait_state
from tests.test_p3_pg import fixture
from tests.test_p204_pg import done


def main() -> None:
    from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

    spec = json.loads((Path(__file__).parent.parent / "docs/contracts/p3-openapi.json").read_text())
    checks = 0
    covered: set[str] = set()
    expected = {op["operationId"] for ops in spec["paths"].values() for op in ops.values()}

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
        covered.add(operation["operationId"])
        print(operation["operationId"], response.status_code)

    with TemporaryDirectory(prefix="p3-wire-") as directory:
        lifecycle = cast(Any, fixture).__wrapped__(Path(directory))
        f = next(lifecycle)
        worker = None
        try:
            validate(f.client.get("/api/v1/auth/session"), "/api/v1/auth/session")
            validate(f.client.get("/api/v1/auth/csrf"), "/api/v1/auth/csrf")
            csrf = f.client.get("/api/v1/auth/csrf").json()["csrf_token"]
            validate(
                f.client.post(
                    "/api/v1/auth/login",
                    json={
                        "schema_version": "p3-web-v1",
                        "login": f.login,
                        "password": f.password.get_secret_value(),
                    },
                    headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
                ),
                "/api/v1/auth/login",
                "post",
            )
            f.actor = SessionStore(f.config).authenticate(
                f.client.cookies.get("commerceops_session")
            )
            with TestClient(
                create_app(web_config=f.config, replenishment_store=f.store), base_url=ORIGIN
            ) as anonymous:
                validate(anonymous.get("/api/v1/auth/csrf"), "/api/v1/auth/csrf")
                validate(anonymous.get("/api/v1/auth/session"), "/api/v1/auth/session")
            payload = f.new_cycle("unknown_inbound")
            created = f.client.post("/api/v1/tasks", json=payload, headers=f.headers())
            validate(created, "/api/v1/tasks", "post")
            task = UUID(created.json()["task_id"])
            worker = P3Process(
                f,
                "worker",
                {
                    "task_id": str(task),
                    "controlled": "long_sku",
                    "offline_explanation": True,
                },
                "never",
            )
            worker.until("after_ready")
            cache_task = UUID(f.create(f.new_cycle())["task_id"])
            worker.until("after_ready")
            with connect(f.config.database) as db:
                source = db.execute(
                    "SELECT * FROM business.p3_task_sources WHERE task_id=%s", (cache_task,)
                ).fetchone()
            assert source
            _, job = create_explanation_task(
                f.config.database, f.inventory.identity, source["source_task_id"], "offline_stub"
            )
            asyncio.run(done(f.inventory, job))
            with connect(f.config.database) as db:
                calls_before = db.execute(
                    "SELECT count(*) AS n FROM business.model_calls"
                ).fetchone()
                actual = db.execute(
                    "SELECT count(*) AS n FROM business.model_calls "
                    "WHERE evidence_mode='actual_provider'"
                ).fetchone()
            assert calls_before == {"n": 1} and actual == {"n": 0}
            for _ in range(2):
                cached = f.client.get(
                    f"/api/v1/tasks/{cache_task}/explanation?report_id={source['source_report_id']}"
                )
                assert cached.status_code == 200
                validate(cached, "/api/v1/tasks/{task_id}/explanation")
            with connect(f.config.database) as db:
                assert (
                    db.execute("SELECT count(*) AS n FROM business.model_calls").fetchone()
                    == calls_before
                )
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
            joint = decision_payload(f, task, "approve_with_assumptions")
            assert (
                len(joint["acknowledged_assumption_keys"][0]) == len("inbound_unknown_zero:") + 256
            )
            decided = f.client.post(
                f"/api/v1/approvals/{approval_id}/decision", json=joint, headers=f.headers()
            )
            validate(decided, "/api/v1/approvals/{approval_id}/decision", "post")
            repeated = f.client.post(
                f"/api/v1/approvals/{approval_id}/decision", json=joint, headers=f.headers()
            )
            validate(repeated, "/api/v1/approvals/{approval_id}/decision", "post")
            validate(
                f.client.get(f"/api/v1/requests/{joint['request_key']}?operation=decision"),
                "/api/v1/requests/{request_key}",
            )
            validate(
                f.client.get(f"/api/v1/approvals/{approval_id}"), "/api/v1/approvals/{approval_id}"
            )
            wait_state(f, task, "completed")
            execution = f.client.get(f"/api/v1/tasks/{task}/execution")
            assert execution.status_code == 200
            validate(execution, "/api/v1/tasks/{task_id}/execution")
            item = execution.json()["item_ids"][0]
            validate(f.client.get("/api/v1/replenishment-items"), "/api/v1/replenishment-items")
            validate(
                f.client.get(f"/api/v1/replenishment-items/{item}"),
                "/api/v1/replenishment-items/{item_id}",
            )
            resolve = {
                "schema_version": "p3-web-v1",
                "request_key": str(uuid4()),
                "action": "complete",
                "reason": "实际wire验证完成",
                "expected_version": 1,
            }
            for _ in range(2):
                result = f.client.post(
                    f"/api/v1/replenishment-items/{item}/resolve", json=resolve, headers=f.headers()
                )
                assert result.status_code == 200
                validate(result, "/api/v1/replenishment-items/{item_id}/resolve", "post")
            validate(
                f.client.get(f"/api/v1/requests/{resolve['request_key']}?operation=resolve"),
                "/api/v1/requests/{request_key}",
            )
            validate(f.client.get("/api/v1/admin/operations"), "/api/v1/admin/operations")
            with connect(f.inventory.owner) as db:
                db.execute(
                    "UPDATE business.principals SET roles=ARRAY['operator','approver','admin'],"
                    "auth_version=auth_version+1 WHERE id=%s",
                    (f.actor.principal_id,),
                )
                db.execute(
                    "INSERT INTO business.principal_role_shop_grants VALUES(%s,%s,%s,'admin',true)",
                    (f.actor.organization_id, f.inventory.data.shop, f.actor.principal_id),
                )
            f.relogin()
            operations = f.client.get("/api/v1/admin/operations")
            assert operations.status_code == 200
            validate(operations, "/api/v1/admin/operations")
            validate(
                f.client.post(
                    "/api/v1/auth/logout", json={"schema_version": "p3-web-v1"}, headers=f.headers()
                ),
                "/api/v1/auth/logout",
                "post",
            )
            assert covered == expected and len(covered) == 22
            print(
                "P3 actual wire checks",
                checks,
                "unique operations",
                len(covered),
                "actual provider",
                0,
            )
        finally:
            if worker and worker.process.poll() is None:
                worker.stop_clean()
            lifecycle.close()


if __name__ == "__main__":
    main()
