"""Real fixed V41 HTTP recipes; no mocked transport, write retry or guessed identity."""

import argparse
import base64
import io
import json
import subprocess
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from xml.sax.saxutils import escape

from tests.e2e.v4.http_probe import Visitor
from tests.e2e.v4.owned_adapter import OwnedAdapter, compose_environment, owner_run
from tests.e2e.v4.supervisor import Budget

from .kpi_reference import assert_metrics, reference
from .owned_driver import ROOT, Case, fixed_compose
from .runner import persist
from .subjects import registry

ROUTES = {
    "dashboard": ("GET", "/api/v4/dashboard"),
    "products": ("GET", "/api/v4/products"),
    "product": ("GET", "/api/v4/products/{product_id}"),
    "tags": ("POST", "/api/v4/products/{product_id}/tags"),
    "orders": ("GET", "/api/v4/orders"),
    "order": ("GET", "/api/v4/orders/{order_id}"),
    "fulfill": ("POST", "/api/v4/orders/{order_id}/fulfillment"),
    "preview": ("POST", "/api/v4/imports/previews"),
    "preview_lookup": ("GET", "/api/v4/imports/preview-requests/{request_key}"),
    "job": ("GET", "/api/v4/imports/{import_job_id}"),
    "confirm": ("POST", "/api/v4/imports/{import_job_id}/confirm"),
    "receipt": ("GET", "/api/v4/actions/{operation}/{request_key}"),
}


def import_bytes(kind: str, sku: str, currency: str) -> bytes:
    rows = [
        ["sku", "title", "price", "currency"],
        [sku, "QA synthetic product", "12.500000", currency],
    ]
    if kind == "csv":
        return ("\n".join(",".join(row) for row in rows) + "\n").encode()
    if kind != "xlsx":
        raise ValueError("fixed CSV/XLSX only")
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
    )
    for n, row in enumerate(rows, 1):
        sheet += (
            f'<row r="{n}">'
            + "".join(
                f'<c r="{chr(65 + i)}{n}" t="inlineStr"><is><t>{escape(v)}</t></is></c>'
                for i, v in enumerate(row)
            )
            + "</row>"
        )
    sheet += "</sheetData></worksheet>"
    parts = {
        "[Content_Types].xml": (
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content'
            '-types"><Default Extension="rels" ContentType="application/vnd.openx'
            'mlformats-package.relationships+xml"/><Default Extension="xml" Conte'
            'ntType="application/xml"/><Override PartName="/xl/workbook.xml" Cont'
            'entType="application/vnd.openxmlformats-officedocument.spreadsheetml'
            '.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" Con'
            'tentType="application/vnd.openxmlformats-officedocument.spreadsheetm'
            'l.worksheet+xml"/></Types>'
        ),
        "_rels/.rels": (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006'
            '/relationships"><Relationship Id="rId1" Type="http://schemas.openxml'
            'formats.org/officeDocument/2006/relationships/officeDocument" Target'
            '="xl/workbook.xml"/></Relationships>'
        ),
        "xl/workbook.xml": (
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/200'
            '6/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/20'
            '06/relationships"><sheets><sheet name="Products" sheetId="1" r:id="r'
            'Id1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006'
            '/relationships"><Relationship Id="rId1" Type="http://schemas.openxml'
            'formats.org/officeDocument/2006/relationships/worksheet" Target="wor'
            'ksheets/sheet1.xml"/></Relationships>'
        ),
        "xl/worksheets/sheet1.xml": sheet,
    }
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in parts.items():
            archive.writestr(name, text)
    return stream.getvalue()


def assert_context(actual: dict[str, Any], session: dict[str, Any], target_shop: str) -> None:
    for key in ("tenant_id", "organization_id", "principal_id", "reset_epoch", "auth_generation"):
        if actual.get(key) != session[key]:
            raise AssertionError("V41_CONTEXT_DRIFT")
    if actual.get("shop_id") != target_shop:
        raise AssertionError("V41_SHOP_CONTEXT_DRIFT")


def assert_read_status(name: str, reply: dict[str, Any]) -> None:
    if name not in {"receipt", "preview_lookup"} and reply.get("status") != "OK":
        raise AssertionError("V41_ORDINARY_READ_REQUIRES_OK")


def fulfillment_fields(order: dict[str, Any]) -> dict[str, Any]:
    return {"expected_version": order["fulfillment_version"], "action": "mark_demo_fulfilled"}


class Business:
    def __init__(
        self, visitor: Visitor, case: Case, compose: tuple[str, ...], budget: Budget
    ) -> None:
        self.visitor, self.case, self.compose, self.budget = visitor, case, compose, budget
        self.unique_product_id: str | None = None
        if visitor.current is None:
            raise ValueError("actual current demo identity required")
        self.shop = visitor.current["data"]["shops"][0]
        registry(Path(case.directory), visitor.current["context"], self.shop["shop_id"])

    def call(
        self,
        name: str,
        *,
        ids: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        query: dict[str, str] | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> dict[str, Any]:
        method, template = ROUTES[name]
        current = self.visitor.current
        if current is None:
            raise ValueError("actual current identity missing")
        ids = dict(ids or {})
        for key, value in ids.items():
            if key == "operation":
                if value not in {"product_tags", "order_fulfillment", "import_confirm"}:
                    raise ValueError("fixed action only")
            else:
                UUID(value)
        path = template.format(**ids)
        context = current["context"]
        headers = {
            "Origin": self.visitor.origin,
            "X-Demo-Epoch": str(context["reset_epoch"]),
            "X-Demo-Generation": str(context["auth_generation"]),
        }
        params = {"shop_id": self.shop["shop_id"], **(query or {})}
        pending: dict[str, Any] | None = None
        pending_path = Path(self.case.directory) / ("request-" + uuid4().hex + ".private.json")
        if method == "POST":
            headers["X-CSRF-Token"] = current["data"]["csrf_token"]
            pending = {
                "route": name,
                "ids": ids,
                "payload": payload,
                "state": "UNKNOWN_UNTIL_READBACK",
            }
            persist(pending_path, pending)
        operation = {
            "preview": "preview",
            "confirm": "import_confirm",
            "tags": "product_tags",
            "fulfill": "order_fulfillment",
        }.get(name)
        if method == "POST" and operation is not None and payload is not None:
            registry(
                Path(self.case.directory),
                context,
                str(payload["shop_id"]),
                operation=operation,
                key=payload["request_key"],
            )
        response = self.visitor.client.request(
            method,
            path,
            json=payload if method == "POST" else None,
            params=params if method == "GET" else None,
            headers=headers,
            timeout=self.budget.timeout(10),
        )
        reply: dict[str, Any] = response.json()
        result = subprocess.run(
            [
                str(ROOT / ".tools/node/bin/node"),
                str(Path(__file__).with_name("validate_response.mjs")),
            ],
            input=json.dumps(
                {
                    "method": method,
                    "route": template,
                    "status": response.status_code,
                    "payload": reply,
                }
            ),
            capture_output=True,
            text=True,
            env={},
            timeout=self.budget.timeout(5),
            check=False,
        )
        if (
            result.returncode
            or json.loads(result.stdout) != {"valid": True}
            or response.status_code not in expected
        ):
            raise AssertionError("V41_STRICT_HTTP_RESPONSE_FAILED")
        if response.headers.get("cache-control") != "no-store":
            raise AssertionError("V41_NO_STORE_REQUIRED")
        if response.status_code < 400:
            if method == "GET":
                assert_read_status(name, reply)
            target_shop = (
                str(payload["shop_id"]) if method == "POST" and payload else params["shop_id"]
            )
            assert_context(reply["context"], context, target_shop)
        if method == "POST" and pending is not None:
            pending["state"] = "ACK_" + reply["status"]
            if operation is not None and payload is not None:
                registry(
                    Path(self.case.directory),
                    context,
                    str(payload["shop_id"]),
                    operation=operation,
                    key=payload["request_key"],
                    state=pending["state"],
                )
            persist(pending_path, pending)
        if name in {"preview_lookup", "receipt"}:
            if reply["data"].get("request_key") != ids["request_key"]:
                raise AssertionError("V41_READBACK_ORIGINAL_KEY_MISMATCH")
            if name == "receipt" and reply["data"].get("operation") != ids["operation"]:
                raise AssertionError("V41_READBACK_OPERATION_MISMATCH")
            lookup_operation = "preview" if name == "preview_lookup" else ids["operation"]
            state = (
                "COMMITTED_READBACK"
                if reply["data"]["status"] == "COMMITTED"
                else "UNKNOWN_READBACK"
            )
            registry(
                Path(self.case.directory),
                context,
                params["shop_id"],
                operation=lookup_operation,
                key=ids["request_key"],
                state=state,
            )
        return reply

    def write(self, revision: str, **extra: Any) -> dict[str, Any]:
        current = self.visitor.current
        if current is None:
            raise ValueError("identity required")
        return {
            "shop_id": self.shop["shop_id"],
            "request_key": str(uuid4()),
            "expected_epoch": current["context"]["reset_epoch"],
            "expected_generation": current["context"]["auth_generation"],
            "expected_data_revision": revision,
            **extra,
        }

    def facts(self) -> dict[str, Any]:
        current = self.visitor.current
        if current is None:
            raise ValueError("identity required")
        result = subprocess.run(
            [
                *owner_run(self.compose),
                "tests.e2e.v41.pg_observer",
                "tenant",
                "--tenant",
                current["context"]["tenant_id"],
                "--shop",
                self.shop["shop_id"],
                "--deadline",
                self.case.deadline,
            ],
            cwd=ROOT,
            env=compose_environment(),
            capture_output=True,
            text=True,
            timeout=self.budget.timeout(15),
            check=False,
        )
        if result.returncode:
            raise RuntimeError("V41_PG_OBSERVER_FAILED")
        value: dict[str, Any] = json.loads(result.stdout)
        persist(Path(self.case.directory) / ("facts-" + uuid4().hex + ".private.json"), value)
        counts = value.get("counts")
        if not isinstance(counts, dict) or any(
            type(n) is not int or n < 0 for n in counts.values()
        ):
            raise ValueError("V41_PG_COUNTS_INVALID")
        return counts


def seed_dashboard_golden(data: dict[str, Any], currency: str, imported: int = 0) -> None:
    from commerceops.application.v4_demo.seed_contract import generate_seed

    seed = generate_seed()
    period = data["period"]
    expected = reference(
        seed.content.model_dump(mode="json"),
        currency,
        date.fromisoformat(period["from_date"]),
        date.fromisoformat(period["to_date"]),
        imported=imported,
    )
    assert_metrics(data, expected)
    source = data["snapshot"]["source"]
    if source["fixture_digest"] != seed.manifest.content_digest:
        raise AssertionError("V41_KPI_WRONG_SEED_DIGEST")
    if source["data_mode"] != ("demo_mixed" if imported else "demo_fixture"):
        raise AssertionError("V41_KPI_WRONG_EFFECTIVE_SOURCE")


def confirmation_fields(
    job: dict[str, Any], preview_revision: str, current_revision: str
) -> dict[str, Any]:
    if job.get("data_revision") != preview_revision or current_revision != preview_revision:
        raise ValueError("V41_PREVIEW_REVISION_CHANGED_REPREVIEW_REQUIRED")
    if (
        job.get("parser_version") != "v41-parser-1"
        or job.get("import_schema_version") != "v41-import-1"
    ):
        raise ValueError("V41_PREVIEW_PARSER_SCHEMA_CHANGED")
    return {"expected_job_version": job["version"], "expected_job_digest": job["job_digest"]}


def assert_import_receipt(
    receipt: dict[str, Any], job: dict[str, Any], request_key: str, after_revision: str
) -> None:
    expected = {
        "operation": "import_confirm",
        "request_key": request_key,
        "resource_id": job["import_job_id"],
        "resource_version": job["version"],
        "before_revision": job["data_revision"],
        "after_revision": after_revision,
    }
    if (
        any(receipt.get(k) != v for k, v in expected.items())
        or after_revision == job["data_revision"]
    ):
        raise AssertionError("V41_IMPORT_RECEIPT_JOB_VERSION_REVISION_MISMATCH")


def import_flow(business: Business, kind: str) -> None:
    before = business.call("products")["data"]
    original_counts = business.facts()
    sku = "QA-" + uuid4().hex[:16]
    currency = business.shop["currency"]
    body = business.write(
        before["snapshot"]["data_revision"],
        format=kind,
        filename="products." + kind,
        file_base64=base64.b64encode(import_bytes(kind, sku, currency)).decode(),
        mapping={"sku": "sku", "title": "title", "price": "price", "currency": "currency"},
    )
    preview = business.call("preview", payload=body)["data"]
    if not preview["confirmable"] or preview["row_count"] != 1:
        raise AssertionError("V41_PREVIEW_NOT_READY")
    lookup = business.call("preview_lookup", ids={"request_key": body["request_key"]})["data"]
    if lookup["status"] != "COMMITTED" or lookup["job"] != preview["job"]:
        raise AssertionError("V41_PREVIEW_KEY_READBACK_MISMATCH")
    counts = business.facts()
    if counts["v41_import_products"] != original_counts["v41_import_products"]:
        raise AssertionError("V41_PREVIEW_WROTE_PRODUCT")
    job = preview["job"]
    current_revision = business.call("products")["data"]["snapshot"]["data_revision"]
    confirm = business.write(
        current_revision,
        **confirmation_fields(job, before["snapshot"]["data_revision"], current_revision),
    )
    committed = business.call(
        "confirm", ids={"import_job_id": job["import_job_id"]}, payload=confirm
    )["data"]["receipt"]
    original = business.call(
        "receipt", ids={"operation": "import_confirm", "request_key": confirm["request_key"]}
    )["data"]
    if original["status"] != "COMMITTED" or original["receipt"] != committed:
        raise AssertionError("V41_IMPORT_ORIGINAL_KEY_UNKNOWN_NO_REPOST")
    for _ in range(10):
        replay = business.call(
            "confirm", ids={"import_job_id": job["import_job_id"]}, payload=confirm
        )
        if replay["data"]["receipt"] != committed:
            raise AssertionError("V41_REPLAY_CHANGED_RECEIPT")
    actual = business.facts()
    for name in ["v41_import_products", "v41_action_receipts", "v41_action_events"]:
        if actual[name] != original_counts[name] + 1:
            raise AssertionError("V41_IMPORT_EFFECT_NOT_ONCE")
    found = business.call("products", query={"q": sku})["data"]
    if len(found["items"]) != 1 or found["items"][0]["skus"][0]["label"] != sku:
        raise AssertionError("V41_IMPORTED_SKU_NOT_QUERYABLE")
    assert_import_receipt(
        committed, job, confirm["request_key"], found["snapshot"]["data_revision"]
    )
    business.unique_product_id = found["items"][0]["product_id"]
    dashboard = business.call("dashboard")["data"]
    seed_dashboard_golden(dashboard, currency, imported=1)
    metric = next(m for m in dashboard["metrics"] if m["metric"] == "product_count")
    from decimal import Decimal

    if Decimal(metric["value"]) != before["total"] + 1:
        raise AssertionError("V41_KPI_IMPORT_COUNT_MISMATCH")
    if found["snapshot"]["data_revision"] != dashboard["snapshot"]["data_revision"]:
        raise AssertionError("V41_READS_MIXED_REVISION")


def catalog_flow(business: Business) -> None:
    page = business.call("products")["data"]
    product = page["items"][0]
    before = business.facts()
    bad = business.write(
        page["snapshot"]["data_revision"],
        expected_version=product["version"] + 99,
        tags=["QA reviewed"],
    )
    business.call("tags", ids={"product_id": product["product_id"]}, payload=bad, expected=(409,))
    if business.facts() != before:
        raise AssertionError("V41_STALE_VERSION_WROTE_EFFECT")
    body = business.write(
        page["snapshot"]["data_revision"], expected_version=product["version"], tags=["QA reviewed"]
    )
    receipt = business.call("tags", ids={"product_id": product["product_id"]}, payload=body)[
        "data"
    ]["receipt"]
    original = business.call(
        "receipt", ids={"operation": "product_tags", "request_key": body["request_key"]}
    )["data"]
    if original["status"] != "COMMITTED" or original["receipt"] != receipt:
        raise AssertionError("V41_TAG_ORIGINAL_KEY_UNKNOWN_NO_REPOST")
    for _ in range(10):
        if (
            business.call("tags", ids={"product_id": product["product_id"]}, payload=body)["data"][
                "receipt"
            ]
            != receipt
        ):
            raise AssertionError("V41_TAG_REPLAY_CHANGED_EFFECT")
    detail = business.call("product", ids={"product_id": product["product_id"]})["data"]
    current = next(
        p
        for p in business.call("products")["data"]["items"]
        if p["product_id"] == product["product_id"]
    )
    if (
        detail["product"] != current
        or current["version"] != product["version"] + 1
        or current["tags"] != ["QA reviewed"]
    ):
        raise AssertionError("V41_TAG_DETAIL_LIST_VERSION_MISMATCH")
    after_tags = business.facts()
    for table in ("v41_product_tags", "v41_action_receipts", "v41_action_events"):
        if after_tags[table] != before[table] + 1:
            raise AssertionError("V41_TAG_DB_EFFECT_NOT_ONCE")
    orders = business.call("orders", query={"payment": "recorded"})["data"]
    order = next(o for o in orders["items"] if o["demo_fulfillment"] == "demo_unfulfilled")
    linked = business.call("order", ids={"order_id": order["order_id"]})["data"]["order"]
    for line in linked["lines"]:
        target = business.call("product", ids={"product_id": line["product_id"]})["data"]
        if target["product"]["product_id"] != line["product_id"]:
            raise AssertionError("V41_ORDER_PRODUCT_LINK_WRONG")
    effect = business.write(
        orders["snapshot"]["data_revision"],
        **fulfillment_fields(order),
    )
    before_fulfill = business.facts()
    committed = business.call("fulfill", ids={"order_id": order["order_id"]}, payload=effect)[
        "data"
    ]["receipt"]
    found = business.call(
        "receipt", ids={"operation": "order_fulfillment", "request_key": effect["request_key"]}
    )["data"]
    if found["status"] != "COMMITTED" or found["receipt"] != committed:
        raise AssertionError("V41_FULFILLMENT_ORIGINAL_KEY_UNVERIFIED")

    for _ in range(10):
        if (
            business.call("fulfill", ids={"order_id": order["order_id"]}, payload=effect)["data"][
                "receipt"
            ]
            != committed
        ):
            raise AssertionError("V41_FULFILLMENT_REPLAY_CHANGED_RECEIPT")
    final = business.call("order", ids={"order_id": order["order_id"]})["data"]["order"]
    if (
        final["fulfillment_version"] != order["fulfillment_version"] + 1
        or final["demo_fulfillment"] != "demo_fulfilled"
    ):
        raise AssertionError("V41_FULFILLMENT_STATE_VERSION_MISMATCH")

    def immutable(row: dict[str, Any]) -> dict[str, Any]:
        return {
            k: v for k, v in row.items() if k not in {"fulfillment_version", "demo_fulfillment"}
        }

    if immutable(final) != immutable(linked):
        raise AssertionError("V41_FULFILLMENT_CHANGED_MONEY_OR_ORDER")
    after_fulfill = business.facts()
    for table in ("v41_order_fulfillments", "v41_action_receipts", "v41_action_events"):
        if after_fulfill[table] != before_fulfill[table] + 1:
            raise AssertionError("V41_FULFILLMENT_DB_EFFECT_NOT_ONCE")


def invalid_import_is_atomic(business: Business) -> None:
    snapshot = business.call("products")["data"]["snapshot"]
    before = business.facts()
    raw = (
        "sku,title,price,currency\nQA-"
        + uuid4().hex[:12]
        + ",Good,1,"
        + business.shop["currency"]
        + "\nQA-"
        + uuid4().hex[:12]
        + ",Bad,-1,"
        + business.shop["currency"]
        + "\n"
    ).encode()
    body = business.write(
        snapshot["data_revision"],
        format="csv",
        filename="invalid.csv",
        file_base64=base64.b64encode(raw).decode(),
        mapping={"sku": "sku", "title": "title", "price": "price", "currency": "currency"},
    )
    preview = business.call("preview", payload=body)["data"]
    if preview["confirmable"] or preview["state"] != "INVALID" or preview["issue_count"] < 1:
        raise AssertionError("V41_INVALID_ROW_ACCEPTED")
    job = preview["job"]
    current_revision = business.call("products")["data"]["snapshot"]["data_revision"]
    confirm = business.write(
        current_revision, **confirmation_fields(job, snapshot["data_revision"], current_revision)
    )
    business.call(
        "confirm", ids={"import_job_id": job["import_job_id"]}, payload=confirm, expected=(409,)
    )
    after = business.facts()
    for table in ["v41_import_products", "v41_action_receipts", "v41_action_events"]:
        if after[table] != before[table]:
            raise AssertionError("V41_INVALID_IMPORT_PARTIALLY_COMMITTED")


def isolate_other_visitor(business: Business, budget: Budget) -> None:
    observer = OwnedAdapter(
        business.compose,
        business.case.project,
        budget,
        evidence=Path(business.case.directory) / "observers",
    )
    other = Visitor(business.case.api, business.case.web, budget, observer)
    try:
        other.create()
        isolated = Business(other, business.case, business.compose, budget)
        # Shared fixture IDs are intentionally legal in each visitor's own authorized shop.
        own_product = isolated.call("products")["data"]["items"][0]
        isolated.call("product", ids={"product_id": own_product["product_id"]})
        isolated.call("products", query={"shop_id": business.shop["shop_id"]}, expected=(404,))
        if business.unique_product_id is not None:
            # Only an explicitly registered tenant-owned upload is a foreign-object negative.
            isolated.call(
                "product", ids={"product_id": business.unique_product_id}, expected=(404,)
            )
    finally:
        other.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    args = parser.parse_args()
    case = Case(**json.loads(args.case.read_text()))
    case.validate(prepared=True)

    compose = fixed_compose(case)
    budget = Budget.bind(
        datetime.fromisoformat(case.starts_at),
        datetime.fromisoformat(case.deadline),
    )
    visitor = Visitor(
        case.api,
        case.web,
        budget,
        OwnedAdapter(compose, case.project, budget, evidence=Path(case.directory) / "observers"),
    )
    try:
        visitor.create()
        business = Business(visitor, case, compose, budget)
        if case.scenario in {"import_csv", "import_xlsx"}:
            import_flow(business, case.scenario.removeprefix("import_"))
        elif case.scenario == "dashboard_same_source":
            products = business.call("products")["data"]
            dashboard = business.call("dashboard")["data"]
            seed_dashboard_golden(dashboard, business.shop["currency"])
            if products["snapshot"]["data_revision"] != dashboard["snapshot"]["data_revision"]:
                raise AssertionError("V41_READS_MIXED_REVISION")
        elif case.scenario == "catalog_orders":
            catalog_flow(business)
            from .concurrency_recipes import catalog_concurrency

            catalog_concurrency(business)
        else:
            raise ValueError("V41_BROWSER_RECIPE_ALIGNMENT_PENDING")
        if case.scenario in {"import_csv", "import_xlsx"}:
            invalid_import_is_atomic(business)
        isolate_other_visitor(business, budget)
        print(json.dumps({"status": "SCENARIO_COMPLETED_PENDING_REVIEW"}))
    finally:
        visitor.close()


if __name__ == "__main__":
    main()
