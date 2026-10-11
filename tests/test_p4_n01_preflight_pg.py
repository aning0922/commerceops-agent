"""实际 PG/会话/HTTP 的 N01 业务零写入和原显式新周期合同，SDK/provider0。"""

import hashlib
import json
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from commerceops.application.replenishment.contracts import WebFailure
from commerceops.application.replenishment.nl_preflight import PreflightInput, PreflightResult
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.web_preflight import WebPreflightStore
from fastapi.testclient import TestClient
from psycopg import sql

from tests.p3_support import ORIGIN, P3Fixture
from tests.test_p3_pg import fixture as fixture

pytestmark = pytest.mark.integration
PATH = "/api/v1/tasks/preflight"


@pytest.fixture(autouse=True)
def actual_import_receipt() -> None:
    """实际 ASGI 同进程的四 N01 模块；不是 Worker/SDK child 回执。"""
    from commerceops.application.replenishment.nl_preflight import parse_preflight
    from commerceops.entrypoints.replenishment_http import install_web
    from commerceops.entrypoints.web_openapi import export_web

    root = Path(__file__).resolve().parents[1] / "backend/src/commerceops"
    names: dict[Any, str] = {
        parse_preflight: "application/replenishment/nl_preflight.py",
        WebPreflightStore: "infrastructure/web_preflight.py",
        install_web: "entrypoints/replenishment_http.py",
        export_web: "entrypoints/web_openapi.py",
    }
    hashes = {}
    for value, relative in names.items():
        filename = sys.modules[value.__module__].__file__
        assert filename is not None
        actual = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
        assert actual == hashlib.sha256((root / relative).read_bytes()).hexdigest()
        hashes[value.__name__] = actual
    evidence = Path("/run/owned")
    if evidence.is_dir():
        output = evidence / "imports-n01-asgi.safe.json"
        output.write_text(
            json.dumps(
                {
                    "four_imports_match": True,
                    "kind": "actual_N01_ASGI_same_process",
                    "hashes": hashes,
                }
            )
        )
        output.chmod(0o600)


def request(f: P3Fixture, text: str = "分析库存 L=3 R=7 S=2", **changes: Any) -> dict[str, Any]:
    return {
        "schema_version": "p3-web-v1",
        "shop_id": str(f.inventory.data.shop),
        "fixture_case": "baseline",
        "text": text,
        **changes,
    }


def business_bytes(f: P3Fixture) -> dict[str, Any]:
    """只读新自有库；不读取凭据/会话材料，不让失败输出包含密码 hash/token。"""
    with connect(f.inventory.owner) as db:
        rows = db.execute(
            "SELECT schemaname,tablename FROM pg_tables "
            "WHERE schemaname IN ('business','checkpoints') ORDER BY schemaname,tablename"
        ).fetchall()
        result = {}
        for row in rows:
            if row["tablename"] in ("web_credentials", "web_sessions", "web_login_attempts"):
                continue
            result[row["schemaname"] + "." + row["tablename"]] = db.execute(
                sql.SQL(
                    "SELECT row_to_json(t)::text AS canonical FROM {}.{} t "
                    "ORDER BY row_to_json(t)::text"
                ).format(sql.Identifier(row["schemaname"]), sql.Identifier(row["tablename"]))
            ).fetchall()
        return result


@pytest.mark.parametrize(
    "text,status",
    [
        ("请分析库存 全店 最近七个完整自然日 L=3天 R=7天 S=2天。", "ready"),
        ("分析最近七天的商品销量和库存情况，找出可能缺货的商品，生成补货建议。", "clarify"),
        ("分析最近七天的销量和库存，找出缺货风险并生成补货建议", "clarify"),
        ("分析库存 L=4", "clarify"),
        ("分析库存 L=3/4 R=7 S=2", "clarify"),
        ("分析库存 L=3 R=7 S=2 再采购", "clarify"),
        ("分析库存 SKU-A L=3 R=7 S=2", "unsupported"),
        ("分析库存 最近三天 L=3 R=7 S=2", "unsupported"),
    ],
)
def test_authenticated_preflight_has_closed_truthful_draft_and_all_business_cp_rows_unchanged(
    fixture: P3Fixture,
    text: str,
    status: str,
) -> None:
    f = fixture
    before = business_bytes(f)
    result = f.client.post(PATH, json=request(f, text), headers=f.headers())
    assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
    assert result.json()["identity_mode"] == "session"
    value = PreflightResult.model_validate_json(json.dumps(result.json()["preflight"]))
    assert value.status == status and value.source.evidence_mode == "not_used"
    assert value.source.fixture_case == "baseline" and value.scope.shop_id == f.inventory.data.shop
    assert (value.draft is not None) == (status == "ready")
    assert text not in json.dumps(result.json(), ensure_ascii=False)
    assert business_bytes(f) == before


def test_csrf_origin_identity_and_nonoperator_precede_payload_without_business_writes(
    fixture: P3Fixture,
) -> None:
    f = fixture
    headers = f.headers()
    before = business_bytes(f)
    for supplied in (
        {"Origin": ORIGIN},
        {**headers, "X-CSRF-Token": "bad"},
        {"X-CSRF-Token": headers["X-CSRF-Token"]},
        {**headers, "Origin": "https://other.test"},
    ):
        result = f.client.post(PATH, json=request(f), headers=supplied)
        assert result.status_code == 403 and business_bytes(f) == before
    with TestClient(f.client.app, base_url=ORIGIN) as anonymous:
        result = anonymous.post(PATH, content="broken", headers={"Origin": ORIGIN})
        assert result.status_code == 401 and business_bytes(f) == before
    with connect(f.inventory.owner) as db:
        db.execute(
            "UPDATE business.principals SET roles=ARRAY['approver'],auth_version=auth_version+1 "
            "WHERE id=%s",
            (f.actor.principal_id,),
        )
    f.relogin()
    before = business_bytes(f)
    result = f.client.post(PATH, content="broken", headers=f.headers())
    assert result.status_code == 403 and result.json()["error"]["code"] == "ACCESS_DENIED"
    assert business_bytes(f) == before


def test_unknown_or_cross_shop_and_source_are_safe_denials_with_zero_business(
    fixture: P3Fixture,
) -> None:
    f = fixture
    other = uuid4()
    with connect(f.inventory.owner) as db:
        db.execute(
            "INSERT INTO business.shops(id,organization_id,adapter_kind,external_shop_key,"
            "timezone,currency,config_ref,environment) "
            "VALUES(%s,%s,'mock','other-demo','Asia/Shanghai','CNY','synthetic','test')",
            (other, f.actor.organization_id),
        )
    before = business_bytes(f)
    errors = []
    for shop in (other, uuid4()):
        result = f.client.post(PATH, json=request(f, shop_id=str(shop)), headers=f.headers())
        assert result.status_code == 404
        errors.append(result.json()["error"])
        assert str(shop) not in json.dumps(result.json()) and business_bytes(f) == before
    assert errors[0] == errors[1]
    result = f.client.post(PATH, json=request(f, fixture_case="dst"), headers=f.headers())
    assert result.status_code == 404 and business_bytes(f) == before


def test_strict_input_fixture_path_limit_json_and_content_type_zero_business(
    fixture: P3Fixture,
) -> None:
    f = fixture
    before = business_bytes(f)
    headers = f.headers()
    for changes in (
        {"text": True},
        {"text": "x" * 2001},
        {"actor": str(uuid4())},
        {"fixture_case": "../elsewhere"},
        {"fixture_case": "unknown_case"},
    ):
        result = f.client.post(PATH, json=request(f, **changes), headers=headers)
        assert result.status_code == 422 and business_bytes(f) == before
    for raw in ('{"text":"first","text":"second"}', "{broken", '{"number":NaN}'):
        result = f.client.post(
            PATH, content=raw, headers={**headers, "Content-Type": "application/json"}
        )
        assert result.status_code == 400 and business_bytes(f) == before
    result = f.client.post(PATH, content="text", headers=headers)
    assert result.status_code == 415 and business_bytes(f) == before


def test_ready_then_current_role_revocation_rejects_preflight_and_fresh_submit_zero_business(
    fixture: P3Fixture,
) -> None:
    f = fixture
    headers = f.headers()
    before = business_bytes(f)
    parsed = f.client.post(PATH, json=request(f), headers=headers)
    assert parsed.status_code == 200 and parsed.json()["preflight"]["status"] == "ready"
    with connect(f.inventory.owner) as db:
        db.execute(
            "UPDATE business.principal_role_shop_grants SET enabled=false "
            "WHERE principal_id=%s AND role='operator'",
            (f.actor.principal_id,),
        )
    before = business_bytes(f)
    create = f.new_cycle()
    create["parameters"] = parsed.json()["preflight"]["draft"]
    for path, payload in ((PATH, request(f)), ("/api/v1/tasks", create)):
        result = f.client.post(path, json=payload, headers=headers)
        assert result.status_code == 401 and business_bytes(f) == before
    with pytest.raises(WebFailure, match="SESSION_INVALID"):
        WebPreflightStore(f.store).parse(
            f.actor, PreflightInput.model_validate_json(json.dumps(request(f)))
        )
    assert business_bytes(f) == before


def test_only_explicit_original_create_new_cycle_generates_one_pair_original_key_receipt(
    fixture: P3Fixture,
) -> None:
    f = fixture
    before = business_bytes(f)
    headers = f.headers()
    parsed = f.client.post(PATH, json=request(f), headers=headers)
    assert parsed.status_code == 200 and business_bytes(f) == before
    payload = f.new_cycle()
    payload["parameters"] = parsed.json()["preflight"]["draft"]
    first = f.client.post("/api/v1/tasks", json=payload, headers=headers)
    assert first.status_code == 202
    after = business_bytes(f)
    for _ in range(9):
        repeated = f.client.post("/api/v1/tasks", json=payload, headers=headers)
        assert repeated.status_code == 202 and repeated.json()["task_id"] == first.json()["task_id"]
        assert repeated.json()["source_task_id"] == first.json()["source_task_id"]
        assert business_bytes(f) == after
    checked = f.client.get(
        "/api/v1/requests/" + payload["request_key"], params={"operation": "create_task"}
    )
    assert checked.status_code == 200 and business_bytes(f) == after
    with connect(f.config.database) as db:
        for table, n in (
            ("business_tasks", 2),
            ("jobs", 2),
            ("web_requests", 1),
            ("approvals", 0),
            ("executions", 0),
            ("outbox", 0),
            ("p4_sdk_calls", 0),
            ("model_calls", 0),
        ):
            assert db.execute(
                sql.SQL("SELECT count(*) AS n FROM business.{}").format(sql.Identifier(table))
            ).fetchone() == {"n": n + len(before["business." + table])}
