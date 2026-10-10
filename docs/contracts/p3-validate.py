"""首批离线OpenAPI/输入负例校验；不运行服务、PG或业务授权。

uv run --frozen --with openapi-spec-validator==0.7.2 python docs/contracts/p3-validate.py
临时工具环境不写项目锁；validator依赖版本在交付记录披露。
"""

import copy
import json
from pathlib import Path
from typing import Any

from commerceops.application.commerce.explanation_read import ExplanationRead
from commerceops.application.commerce.inventory_facts import InventoryReport
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate

ROOT = Path(__file__).resolve().parent
SPEC = json.loads((ROOT / "p3-openapi.json").read_text())
CHECKS = 0


def require(condition: bool, message: str) -> None:
    global CHECKS
    CHECKS += 1
    if not condition:
        raise ValueError(message)


def nodes(value: Any) -> Any:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


def check_input(name: str, payload: dict[str, Any], valid: bool) -> None:
    schema = {
        "$ref": f"#/components/schemas/{name}",
        "components": SPEC["components"],
    }
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload))
    require(bool(errors) != valid, f"input vector failed: {name}, expected valid={valid}")


def check_p2_export(model: Any, prefix: str) -> None:
    raw = model.model_json_schema()
    definitions = raw.pop("$defs", {})

    def convert(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: "#/components/schemas/" + prefix + item.split("/")[-1]
                if key == "$ref"
                else convert(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [convert(item) for item in value]
        return value

    schemas = SPEC["components"]["schemas"]
    for name, definition in {**definitions, model.__name__: raw}.items():
        require(schemas[prefix + name] == convert(definition), "P2 schema changed in wrapper")


def main() -> None:
    validate(SPEC)
    require(SPEC["openapi"] == "3.1.0", "OpenAPI version drift")
    for node in nodes(SPEC):
        if "$ref" in node:
            target: Any = SPEC
            require(node["$ref"].startswith("#/"), "unexpected external schema ref")
            for part in node["$ref"][2:].split("/"):
                target = target[part.replace("~1", "/").replace("~0", "~")]
    operations = []
    for path, methods in SPEC["paths"].items():
        require(path.startswith("/api/v1/"), "new API namespace drift")
        require(
            not any(x in path for x in ("/retry", "/recompute", "/send", "/resume")),
            "disabled operation exposed",
        )
        for method, endpoint in methods.items():
            operations.append(endpoint["operationId"])
            require(
                endpoint["x-implementation-status"] == "not_implemented", "candidate misreported"
            )
            if method == "post":
                headers = {
                    p["name"]
                    for p in endpoint["parameters"]
                    if p["in"] == "header" and p["required"]
                }
                require(headers == {"Origin", "X-CSRF-Token"}, "POST security header missing")
                require(endpoint["security"] == [{"SessionCookie": []}], "POST session missing")
            if path not in ("/api/v1/auth/csrf",):
                require(
                    endpoint["security"] == [{"SessionCookie": []}], "authenticated route drift"
                )
    require(len(operations) == len(set(operations)) == 22, "operation identity drift")
    schemas = SPEC["components"]["schemas"]
    check_p2_export(InventoryReport, "P2")
    check_p2_export(ExplanationRead, "P2Explanation")
    for name in (
        "DecisionInput",
        "ResolveInput",
        "CreateFromReport",
        "CreateNewCycle",
        "LoginInput",
    ):
        schema = schemas[name]
        require(schema["additionalProperties"] is False, "write input allows extras")
        require(
            not {
                "actor",
                "principal_id",
                "roles",
                "approved",
                "eligible",
                "organization_id",
            }.intersection(schema["properties"]),
            "trusted field in input",
        )
    require(
        schemas["P2InventoryReport"]["properties"]["analysis_only"]["const"] is True,
        "P2 facts mutated",
    )
    require(
        schemas["P2InventoryReport"]["properties"]["execution_available"]["const"] is False,
        "P2 execution enabled",
    )
    statuses = SPEC["paths"]["/api/v1/approvals/{approval_id}/decision"]["post"]["responses"]
    require(
        {"401", "403", "404", "409", "410", "422"}.issubset(statuses),
        "decision error contract incomplete",
    )
    require(
        SPEC["x-error-statuses"]["404"] == ["RESOURCE_NOT_FOUND"], "object leakage error branch"
    )
    require(SPEC["x-error-statuses"]["410"] == ["APPROVAL_EXPIRED"], "expiry status drift")
    error = {
        "schema_version": "p3-web-v1",
        "server_time": None,
        "trace_id": "00000000-0000-4000-8000-000000000001",
        "error": {
            "code": "RESOURCE_NOT_FOUND",
            "safe_message": "无法访问该资源",
            "retryable": False,
            "receipt": None,
        },
    }
    check_input("Error", error, True)
    check_input("Error", {**error, "task_id": error["trace_id"]}, False)
    check_input("Error", {**error, "schema_version": "p203-read-v1"}, False)
    uuid = "00000000-0000-4000-8000-000000000001"
    decision = {
        "schema_version": "p3-web-v1",
        "request_key": uuid,
        "approval_id": uuid,
        "plan_id": uuid,
        "plan_version": 1,
        "plan_hash": "0" * 64,
        "action": "approve",
        "acknowledged_assumption_keys": [],
        "nonce": "N" * 43,
    }
    check_input("DecisionInput", decision, True)
    for field in decision:
        broken = copy.deepcopy(decision)
        broken.pop(field)
        check_input("DecisionInput", broken, False)
    for field, value in (
        ("actor", uuid),
        ("approved", True),
        ("roles", ["approver"]),
        ("plan_version", True),
        ("plan_version", 0),
        ("plan_hash", "bad"),
        ("nonce", "bad"),
        ("action", "confirm"),
    ):
        check_input("DecisionInput", {**decision, field: value}, False)
    keys = ["inbound_unknown_zero:sku/A", "inbound_unknown_zero:sku/B"]
    joint = {**decision, "action": "approve_with_assumptions", "acknowledged_assumption_keys": keys}
    check_input("DecisionInput", joint, True)
    check_input("DecisionInput", {**joint, "acknowledged_assumption_keys": []}, False)
    check_input("DecisionInput", {**joint, "acknowledged_assumption_keys": keys + keys[:1]}, False)
    check_input("DecisionInput", {**decision, "acknowledged_assumption_keys": keys}, False)
    check_input("DecisionInput", {**decision, "action": "reject_assumptions"}, True)
    long_key = "inbound_unknown_zero:" + "x" * 256
    require(len(long_key) == 277, "full SKU assumption key length drift")
    check_input("DecisionInput", {**joint, "acknowledged_assumption_keys": [long_key]}, True)
    receipt = {
        "schema_version": "p3-web-v1",
        "identity_mode": "session",
        "server_time": "2026-10-10T00:00:00+00:00",
        "trace_id": uuid,
        "request_key": uuid,
        "decision_id": uuid,
        "task_id": uuid,
        "approval_id": uuid,
        "plan_id": uuid,
        "plan_version": 1,
        "plan_hash": "0" * 64,
        "decision_payload_hash": "0" * 64,
        "action": "approve_with_assumptions",
        "acknowledged_assumption_keys": [long_key],
        "approval_status": "approved",
        "decided_by": uuid,
        "decided_at": "2026-10-10T00:00:00+00:00",
        "decision_source": "web",
        "reason_code": None,
        "resume_state": "queued",
        "duplicate": False,
    }
    check_input("DecisionReceipt", receipt, True)
    check_input("DecisionReceipt", {**receipt, "acknowledged_assumption_keys": ["x" * 301]}, False)
    resolve = {
        "schema_version": "p3-web-v1",
        "request_key": uuid,
        "action": "complete",
        "reason": "内部跟进已完成",
        "expected_version": 1,
    }
    check_input("ResolveInput", resolve, True)
    for field, value in (
        ("reason", ""),
        ("reason", " \t\n"),
        ("reason", "中" * 1001),
        ("action", "reopen"),
        ("expected_version", False),
        ("expected_version", 0),
        ("actor", uuid),
    ):
        check_input("ResolveInput", {**resolve, field: value}, False)
    create = {
        "schema_version": "p3-web-v1",
        "mode": "from_report",
        "request_key": uuid,
        "source_task_id": uuid,
        "source_report_id": uuid,
        "snapshot_id": uuid,
        "facts_hash": "0" * 64,
    }
    check_input("CreateTaskInput", create, True)
    check_input("CreateTaskInput", {**create, "shop_id": uuid}, False)
    cycle = {
        "schema_version": "p3-web-v1",
        "mode": "new_cycle",
        "request_key": uuid,
        "shop_id": uuid,
        "parameters": {
            "source_mode": "mock",
            "dataset_version": "inventory-v1",
            "fixture_case": "baseline",
            "L": 3,
            "R": 7,
            "S": 2,
        },
    }
    check_input("CreateTaskInput", cycle, True)
    check_input("CreateTaskInput", {**cycle, "old_approval_id": uuid}, False)
    broken_cycle = copy.deepcopy(cycle)
    broken_cycle["parameters"]["source_mode"] = "production"
    check_input("CreateTaskInput", broken_cycle, False)
    print(
        f"OpenAPI valid: {len(SPEC['paths'])} paths / {len(operations)} operations / "
        f"{len(schemas)} schemas"
    )
    print(f"Contract checks passed: {CHECKS}; no service/PG/identity/decision execution")
    print(
        "JSON Schema integer permits integral float; runtime strict JSON integer "
        "is checked separately by runtime tests; this command supplies contract evidence only."
    )


if __name__ == "__main__":
    main()
