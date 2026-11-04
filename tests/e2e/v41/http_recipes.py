"""Real fixed V41 HTTP recipes; no mocked transport, write retry or guessed identity."""

import argparse
import base64
import io
import json
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from xml.sax.saxutils import escape

from tests.e2e.v4 import owned_driver as public
from tests.e2e.v4.http_probe import Visitor
from tests.e2e.v4.owned_adapter import OwnedAdapter, compose_environment, owner_run
from tests.e2e.v4.supervisor import Budget

from .owned_driver import ROOT, Case
from .runner import persist

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


class Business:
    def __init__(
        self, visitor: Visitor, case: Case, compose: tuple[str, ...], budget: Budget
    ) -> None:
        self.visitor, self.case, self.compose, self.budget = visitor, case, compose, budget
        self.pending: dict[str, Any] | None = None
        if visitor.current is None:
            raise ValueError("actual current demo identity required")
        self.shop = visitor.current["data"]["shops"][0]

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
        if method == "POST":
            headers["X-CSRF-Token"] = current["data"]["csrf_token"]
            self.pending = {
                "route": name,
                "ids": ids,
                "payload": payload,
                "state": "UNKNOWN_UNTIL_READBACK",
            }
            persist(Path(self.case.directory) / "pending.private.json", self.pending)
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
        if response.status_code < 400 and reply["context"] != context:
            # Context is server authority; never accept a cross tenant/shop/epoch response.
            for key in ("tenant_id", "principal_id", "reset_epoch", "auth_generation"):
                if reply["context"][key] != context[key]:
                    raise AssertionError("V41_CONTEXT_DRIFT")
        if method == "POST" and self.pending is not None:
            self.pending["state"] = "ACK_" + reply["status"]
            persist(Path(self.case.directory) / "pending.private.json", self.pending)
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
    confirm = business.write(
        before["snapshot"]["data_revision"],
        expected_job_version=job["version"],
        expected_job_digest=job["job_digest"],
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
    dashboard = business.call("dashboard")["data"]
    metric = next(m for m in dashboard["metrics"] if m["metric"] == "product_count")
    from decimal import Decimal

    if Decimal(metric["value"]) != before["total"] + 1:
        raise AssertionError("V41_KPI_IMPORT_COUNT_MISMATCH")
    if found["snapshot"]["data_revision"] != dashboard["snapshot"]["data_revision"]:
        raise AssertionError("V41_READS_MIXED_REVISION")
    business.pending = None


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
    orders = business.call("orders", query={"payment": "recorded"})["data"]
    order = next(o for o in orders["items"] if o["demo_fulfillment"] == "demo_unfulfilled")
    linked = business.call("order", ids={"order_id": order["order_id"]})["data"]["order"]
    for line in linked["lines"]:
        target = business.call("product", ids={"product_id": line["product_id"]})["data"]
        if target["product"]["product_id"] != line["product_id"]:
            raise AssertionError("V41_ORDER_PRODUCT_LINK_WRONG")
    effect = business.write(
        orders["snapshot"]["data_revision"],
        expected_version=order["version"],
        action="mark_demo_fulfilled",
    )
    committed = business.call("fulfill", ids={"order_id": order["order_id"]}, payload=effect)[
        "data"
    ]["receipt"]
    found = business.call(
        "receipt", ids={"operation": "order_fulfillment", "request_key": effect["request_key"]}
    )["data"]
    if found["status"] != "COMMITTED" or found["receipt"] != committed:
        raise AssertionError("V41_FULFILLMENT_ORIGINAL_KEY_UNVERIFIED")


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
    confirm = business.write(
        snapshot["data_revision"],
        expected_job_version=job["version"],
        expected_job_digest=job["job_digest"],
    )
    business.call(
        "confirm", ids={"import_job_id": job["import_job_id"]}, payload=confirm, expected=(409,)
    )
    after = business.facts()
    for table in ["v41_import_products", "v41_action_receipts", "v41_action_events"]:
        if after[table] != before[table]:
            raise AssertionError("V41_INVALID_IMPORT_PARTIALLY_COMMITTED")


def isolate_other_visitor(business: Business, budget: Budget) -> None:
    product = business.call("products")["data"]["items"][0]
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
        isolated.call("product", ids={"product_id": product["product_id"]}, expected=(404,))
    finally:
        other.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    args = parser.parse_args()
    case = Case(**json.loads(args.case.read_text()))
    case.validate(prepared=True)

    compose = public.compose(case)  # type: ignore[arg-type]
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
            if products["snapshot"]["data_revision"] != dashboard["snapshot"]["data_revision"]:
                raise AssertionError("V41_READS_MIXED_REVISION")
        elif case.scenario == "catalog_orders":
            catalog_flow(business)
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
