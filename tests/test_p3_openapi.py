"""完整22路由注册合同导出；不替代PG/会话或actual wire Gate。"""

import copy
import json
from importlib.resources import files
from pathlib import Path

import pytest
from commerceops.entrypoints.api import create_app
from commerceops.entrypoints.web_openapi import export_web
from commerceops.infrastructure.database import DatabaseSettings
from commerceops.infrastructure.replenishment_repository import ReplenishmentStore
from commerceops.infrastructure.web_config import WebConfig

pytestmark = pytest.mark.offline
ROOT = Path(__file__).resolve().parents[1]


def test_registered_runtime_openapi_matches_approved_subset_without_pending_routes() -> None:
    source = (ROOT / "docs/contracts/p3-openapi.json").read_bytes()
    assert files("commerceops.assets").joinpath("p3-web-v1.openapi.json").read_bytes() == source
    contract = json.loads(source)
    n01_source = (ROOT / "docs/contracts/p4-n01-openapi.json").read_bytes()
    assert (
        files("commerceops.assets").joinpath("p4-n01-web-v1.openapi.json").read_bytes()
        == n01_source
    )
    n01 = json.loads(n01_source)
    assert sum(len(operations) for operations in contract["paths"].values()) == 22
    assert set(n01["paths"]) == {"/api/v1/tasks/preflight"}
    assert set(n01["paths"]["/api/v1/tasks/preflight"]) == {"post"}
    contract["paths"].update(n01["paths"])
    contract["components"]["schemas"].update(n01["components"]["schemas"])
    m2_source = (ROOT / "docs/contracts/p5-m2-openapi.json").read_bytes()
    assert files("commerceops.assets").joinpath("p5-m2-v1.openapi.json").read_bytes() == m2_source
    m2 = json.loads(m2_source)
    contract["paths"].update(m2["paths"])
    contract["components"]["schemas"].update(m2["components"]["schemas"])
    config = WebConfig(
        database=DatabaseSettings(
            host="127.0.0.1", name="offline", user="offline", password_file=Path("unused-offline")
        ),
        csrf_secret=b"c" * 32,
        nonce_secret=b"n" * 32,
        origins=("https://example.test",),
    )
    store = ReplenishmentStore(config, ROOT / "tests/fixtures/commerce/inventory-v1")
    schema = create_app(web_config=config, replenishment_store=store).openapi()
    actual = {
        path: operations
        for path, operations in schema["paths"].items()
        if path.startswith("/api/v1/")
    }
    assert len(actual) == 22 and sum(len(operations) for operations in actual.values()) == 23
    assert sum(len(operations) for operations in contract["paths"].values()) == 23
    for path, operations in actual.items():
        for method, operation in operations.items():
            expected = copy.deepcopy(contract["paths"][path][method])
            expected["x-implementation-status"] = "implemented"
            assert operation == expected
    missing = {
        (path, method)
        for path, operations in contract["paths"].items()
        for method in operations
        if method not in actual.get(path, {})
    }
    assert missing == set()
    for field in ("schemas", "securitySchemes"):
        for name, value in contract["components"][field].items():
            assert schema["components"][field][name] == value


def test_unapproved_registered_operation_fails_export() -> None:
    for path, method in (("/api/v1/unapproved", "get"), ("/api/v1/tasks", "delete")):
        with pytest.raises(ValueError):
            export_web({"paths": {path: {method: {}}}})
