"""已注册P3运行端点的显式合同导出；手工鉴权后解析的schema不依赖FastAPI猜测。"""

import copy
import json
from importlib.resources import files
from typing import Any


def export_web(schema: dict[str, Any]) -> dict[str, Any]:
    contract = json.loads(
        files("commerceops.assets").joinpath("p3-web-v1.openapi.json").read_text()
    )
    n01 = json.loads(files("commerceops.assets").joinpath("p4-n01-web-v1.openapi.json").read_text())
    contract["paths"].update(n01["paths"])
    contract["components"]["schemas"].update(n01["components"]["schemas"])
    for path, operations in schema["paths"].items():
        if not path.startswith("/api/v1/"):
            continue
        declared = contract["paths"].get(path)
        if not declared:
            raise ValueError("P3 registered path has no approved contract")
        for method in operations:
            if method not in declared:
                raise ValueError("P3 registered operation has no approved contract")
            operations[method] = copy.deepcopy(declared[method])
            operations[method]["x-implementation-status"] = "implemented"
    components = schema.setdefault("components", {})
    for field in ("schemas", "securitySchemes"):
        components.setdefault(field, {}).update(copy.deepcopy(contract["components"][field]))
    return schema
