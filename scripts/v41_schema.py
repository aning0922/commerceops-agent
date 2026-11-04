"""Export strict V41 DTO schemas and route references; never register runtime routes."""

import argparse
import json
from pathlib import Path
from typing import Any

from commerceops.application.v41 import contracts as dto
from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "docs/v4/v4-1/API_CONTRACT.json"


def contract() -> dict[str, Any]:
    routes: list[tuple[str, str, type[BaseModel], type[BaseModel]]] = [
        ("GET", "/api/v4/dashboard", dto.PeriodQuery, dto.BusinessEnvelope[dto.DashboardData]),
        (
            "GET",
            "/api/v4/dashboard/drilldown",
            dto.DrilldownQuery,
            dto.BusinessEnvelope[dto.Page[dto.Order | dto.Product | dto.RefundEvent]],
        ),
        ("GET", "/api/v4/products", dto.ProductQuery, dto.BusinessEnvelope[dto.Page[dto.Product]]),
        (
            "GET",
            "/api/v4/products/export",
            dto.ProductQuery,
            dto.BusinessEnvelope[dto.ExportData],
        ),
        (
            "GET",
            "/api/v4/products/{product_id}",
            dto.Query,
            dto.BusinessEnvelope[dto.ProductDetail],
        ),
        (
            "POST",
            "/api/v4/products/{product_id}/tags",
            dto.SetProductTags,
            dto.BusinessEnvelope[dto.ActionResult],
        ),
        ("GET", "/api/v4/orders", dto.OrderQuery, dto.BusinessEnvelope[dto.Page[dto.Order]]),
        ("GET", "/api/v4/orders/export", dto.OrderQuery, dto.BusinessEnvelope[dto.ExportData]),
        ("GET", "/api/v4/orders/{order_id}", dto.Query, dto.BusinessEnvelope[dto.OrderDetail]),
        (
            "POST",
            "/api/v4/orders/{order_id}/fulfillment",
            dto.FulfillDemoOrder,
            dto.BusinessEnvelope[dto.ActionResult],
        ),
        (
            "GET",
            "/api/v4/read-context",
            dto.ReadContextQuery,
            dto.BusinessEnvelope[dto.ReadContextData],
        ),
        (
            "POST",
            "/api/v4/imports/previews",
            dto.ImportPreviewInput,
            dto.BusinessEnvelope[dto.ImportPreviewData],
        ),
        (
            "GET",
            "/api/v4/imports/preview-requests/{request_key}",
            dto.Query,
            dto.BusinessEnvelope[dto.PreviewLookup],
        ),
        (
            "GET",
            "/api/v4/imports/{import_job_id}",
            dto.Query,
            dto.BusinessEnvelope[dto.ImportPreviewData],
        ),
        (
            "POST",
            "/api/v4/imports/{import_job_id}/confirm",
            dto.ConfirmImport,
            dto.BusinessEnvelope[dto.ActionResult],
        ),
        (
            "GET",
            "/api/v4/actions/{operation}/{request_key}",
            dto.Query,
            dto.BusinessEnvelope[dto.ActionLookup],
        ),
    ]
    models = {model for _, _, request, response in routes for model in (request, response)}
    models.add(dto.FailureEnvelope)
    references, schema = models_json_schema(
        [(model, "validation") for model in sorted(models, key=lambda model: model.__name__)],
        title="V41 strict business DTOs",
    )
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    entries = []
    for method, path, request, response in routes:
        entry: dict[str, Any] = dict(
            method=method,
            path=path,
            request=references[(request, "validation")],
            response=references[(response, "validation")],
            failure=references[(dto.FailureEnvelope, "validation")],
            cookie="commerceops_v4_demo",
            current_identity_required=True,
            origin_required=method == "POST",
            csrf_required=method == "POST",
            context_headers=method == "GET",
        )
        if path.endswith("/export"):
            entry["transport"] = "application/json; context checked before CSV Blob download"
        entries.append(entry)
    return dict(
        schema_version="v41-api-contract-1",
        status="PURE_DTOS_NOT_RUNTIME_ROUTES",
        json_schema=schema,
        routes=entries,
    )


def encoded() -> str:
    return json.dumps(contract(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = encoded()
    if args.check:
        if not DESTINATION.exists() or DESTINATION.read_text() != output:
            raise SystemExit("V41_SCHEMA_DRIFT")
        print("V41 schema: exact generated DTO contract")
    else:
        DESTINATION.write_text(output)
        print("V41 schema: exported DTO contract")


if __name__ == "__main__":
    main()
