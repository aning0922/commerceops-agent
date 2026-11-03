"""Pure contract/fixture checks; no database, runtime session or external acceptance."""

import ast
import copy
import hashlib
import json
import random
import re
from datetime import UTC, datetime
from decimal import localcontext
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from commerceops.application.v4_demo import contracts as dto
from commerceops.application.v4_demo import seed_contract as seed
from commerceops.domain.commerce_values import canonical_bytes, currency
from pydantic import ValidationError

pytestmark = pytest.mark.offline
GOLDEN_CONTENT_DIGEST = "59eaeab0006af3421fb3432d2c1c199d3064eb823dc0b5a4a8b18354822211e8"


@pytest.fixture(scope="module")
def bundle() -> seed.SeedBundle:
    return seed.generate_seed()


@pytest.fixture
def content(bundle: seed.SeedBundle) -> dict[str, Any]:
    return bundle.content.model_dump(mode="json")


def replace(data: dict[str, Any], path: tuple[str | int, ...], value: Any) -> None:
    current: Any = data
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = value


def test_golden_canonical_content_and_repeated_generation(bundle: seed.SeedBundle) -> None:
    original = bundle.canonical_content()
    assert len(original) == 60412
    assert hashlib.sha256(original).hexdigest() == GOLDEN_CONTENT_DIGEST
    assert bundle.manifest.content_digest == GOLDEN_CONTENT_DIGEST
    assert seed.generate_seed().canonical_content() == original
    assert seed.SeedBundle.model_validate_json(bundle.model_dump_json()) == bundle
    parsed = json.loads(original)
    assert canonical_bytes(dict(reversed(list(parsed.items())))) == original
    assert parsed["snapshot_at"] == "2026-11-02T00:00:00Z"


def test_generator_does_not_depend_on_global_prng_or_decimal_context(
    bundle: seed.SeedBundle,
) -> None:
    previous = random.getstate()
    try:
        random.seed(7)
        before = random.getstate()
        with localcontext() as ctx:
            ctx.prec = 2
            generated = seed.generate_seed()
        assert generated == bundle
        assert random.getstate() == before
    finally:
        random.setstate(previous)


def test_counts_and_cross_currency_summary_are_separate(bundle: seed.SeedBundle) -> None:
    assert [(shop.shop_key, shop.timezone, shop.currency) for shop in bundle.content.shops] == [
        ("v4-shop-a", "Asia/Taipei", "TWD"),
        ("v4-shop-b", "Asia/Shanghai", "CNY"),
    ]
    for shop in bundle.content.shops:
        assert shop.summary_counts().model_dump() == dict(
            products=8, skus=10, orders=12, order_lines=18
        )
        assert shop.counts().model_dump() == dict(
            products=8,
            skus=10,
            orders=12,
            order_lines=18,
            inventory=10,
            refunds=2,
            customers=6,
            suppliers=2,
            supplier_quotes=3,
            knowledge_refs=2,
            purchase_fixture_refs=1,
            support_fixture_refs=1,
            campaign_fixture_refs=1,
        )
        assert len(shop.entities()) == 76
    # New demo support must not silently extend the original M3 currency contract.
    with pytest.raises(ValueError, match="UNSUPPORTED_CURRENCY"):
        currency("TWD")


def test_matching_sku_labels_do_not_share_source_identity(bundle: seed.SeedBundle) -> None:
    a, b = bundle.content.shops
    assert a.skus[0].label == b.skus[0].label
    assert a.skus[0].ref.id != b.skus[0].ref.id
    assert a.skus[0].stock_pool_ref != b.skus[0].stock_pool_ref
    assert a.skus[0].ref == seed.template_ref("v4-shop-a", "sku", 0)
    assert a.skus[0].product_ref == a.skus[1].product_ref
    assert a.skus[0].variant_ref != a.skus[1].variant_ref
    assert {item.ref.id for item in a.entities()}.isdisjoint(item.ref.id for item in b.entities())


def test_unknowns_are_preserved_and_not_defaulted_to_zero(bundle: seed.SeedBundle) -> None:
    for shop in bundle.content.shops:
        assert all(item.cost_amount is None for item in shop.skus)
        assert all(item.inbound_units is None for item in shop.inventory)
        assert all(item.inbound_reason == "UNKNOWN_INBOUND" for item in shop.inventory)
        assert all(item.quantity is None and item.restocked is None for item in shop.refunds)
        assert shop.orders[-1].paid_at is None
        assert shop.orders[-1].status_hint == "payment_timestamp_unknown"
    stock = bundle.content.shops[0].inventory[1].model_dump(mode="json")
    stock.update(available_units=None, stock_reason="UNKNOWN_STOCK")
    result = seed.Inventory.model_validate_json(json.dumps(stock))
    assert result.available_units is None
    assert json.loads(result.model_dump_json())["available_units"] is None


def test_six_refs_are_real_relationships_but_no_business_workflows(
    bundle: seed.SeedBundle,
) -> None:
    assert [item.scenario_id for item in bundle.content.scenarios] == [
        "stockout",
        "high_refund",
        "slow_moving",
        "purchase_pending",
        "support_escalation",
        "marketing_draft",
    ]
    assert all(
        item.status == "fixture_links_only_not_functional_flows"
        for item in bundle.content.scenarios
    )
    a, b = bundle.content.shops
    assert a.inventory[0].available_units == 0
    assert a.inventory[9].available_units == 80
    assert not any(line.sku_ref == a.skus[9].ref for line in a.order_lines)
    assert a.refunds[0].order_ref == a.orders[3].ref
    assert a.refunds[0].occurred_at.date() != a.orders[3].paid_at.date()  # type: ignore[union-attr]
    assert b.purchase_fixture_refs[0].quote_ref == b.supplier_quotes[0].ref
    assert b.support_fixture_refs[0].customer_ref == b.orders[6].customer_ref
    assert a.campaign_fixture_refs[0].sku_ref == a.skus[9].ref
    for shop in (a, b):
        assert "status" not in shop.purchase_fixture_refs[0].model_dump()
        assert "approved" not in shop.campaign_fixture_refs[0].model_dump()
        assert "sent" not in shop.support_fixture_refs[0].model_dump()


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("shops", 0, "currency"), "CNY"),
        (("shops", 0, "timezone"), "UTC"),
        (("shops", 0, "skus", 0, "currency"), "CNY"),
        (("shops", 0, "order_lines", 0, "currency"), "CNY"),
        (("shops", 0, "suppliers", 0, "currency"), "CNY"),
        (("shops", 0, "supplier_quotes", 0, "currency"), "CNY"),
        (("shops", 0, "skus", 0, "cost_amount"), "0"),
        (("shops", 0, "inventory", 0, "inbound_units"), 0),
        (("shops", 0, "inventory", 0, "available_units"), True),
        (("shops", 0, "inventory", 0, "available_units"), 1.5),
        (("shops", 0, "inventory", 0, "available_units"), -1),
        (("shops", 0, "inventory", 0, "stock_reason"), "UNKNOWN_STOCK"),
        (("shops", 0, "refunds", 0, "restocked"), False),
        (("shops", 0, "refunds", 0, "quantity"), 1),
        (("shops", 0, "order_lines", 0, "quantity"), True),
        (("shops", 0, "order_lines", 0, "quantity"), "1"),
        (("shops", 0, "order_lines", 0, "quantity"), 0),
        (("shops", 0, "order_lines", 0, "net_amount"), "101"),
        (("shops", 0, "orders", 0, "net_amount"), "1"),
        (("shops", 0, "orders", 0, "created_at"), "2026-10-01T00:00:00Z"),
        (("shops", 0, "orders", 0, "created_at"), "2026-10-21T10:00:00"),
        (("shops", 0, "orders", 0, "paid_at"), None),
        (("shops", 0, "refunds", 0, "amount"), "999999"),
        (("shops", 0, "refunds", 0, "amount"), "1"),
        (("shops", 0, "refunds", 0, "occurred_at"), "2026-10-01T00:00:00Z"),
        (("shops", 0, "supplier_quotes", 0, "valid_until"), "2026-10-01T00:00:00Z"),
        (("shops", 0, "supplier_quotes", 0, "moq"), 0),
        (("shops", 0, "inventory", 0, "available_units"), 1),
        (("shops", 0, "inventory", 9, "available_units"), 79),
        (("shops", 0, "customers", 0, "display_name"), "person@example.invalid"),
        (("shops", 0, "customers", 0, "phone"), "synthetic-only"),
        (("shops", 0, "knowledge_refs", 0, "body"), "外部未授权资料"),
        (("shops", 0, "knowledge_refs", 0, "content_hash"), "0" * 64),
        (("shops", 0, "skus", 0, "ref", "id"), str(UUID(int=0))),
        (("shops", 0, "skus", 0, "ref", "version"), True),
        (("random_seed",), 4000001.0),
        (("anchor_day",), "2026-11-02"),
        (("earliest_business_day",), "2026-10-18"),
        (("snapshot_at",), "2026-11-03T00:00:00Z"),
        (("modes", "data_mode"), "actual_authorized"),
        (("modes", "delivery_mode"), "authorized_platform"),
        (("scenarios", 0, "status"), "completed"),
        (("scenarios", 0, "refs"), []),
    ],
)
def test_rejects_semantic_and_untrusted_mutations(
    content: dict[str, Any],
    path: tuple[str | int, ...],
    value: Any,
) -> None:
    replace(content, path, value)
    with pytest.raises(ValidationError):
        seed.FixtureContent.model_validate_json(json.dumps(content))


@pytest.mark.parametrize(
    ("target", "source"),
    [
        (("shops", 0, "skus", 0, "product_ref"), ("shops", 1, "products", 0, "ref")),
        (("shops", 0, "order_lines", 0, "order_ref"), ("shops", 1, "orders", 0, "ref")),
        (("shops", 0, "inventory", 9, "sku_ref"), ("shops", 0, "skus", 8, "ref")),
        (("shops", 0, "order_lines", 0, "sku_ref"), ("shops", 0, "products", 0, "ref")),
        (
            ("shops", 0, "support_fixture_refs", 0, "customer_ref"),
            ("shops", 0, "customers", 1, "ref"),
        ),
        (
            ("shops", 0, "campaign_fixture_refs", 0, "knowledge_ref"),
            ("shops", 1, "knowledge_refs", 1, "ref"),
        ),
        (("shops", 0, "products", 1, "ref"), ("shops", 0, "products", 0, "ref")),
    ],
)
def test_cross_shop_wrong_kind_duplicate_and_missing_links_rejected(
    content: dict[str, Any],
    target: tuple[str | int, ...],
    source: tuple[str | int, ...],
) -> None:
    value: Any = content
    for key in source:
        value = value[key]
    replace(content, target, copy.deepcopy(value))
    with pytest.raises(ValidationError):
        seed.FixtureContent.model_validate_json(json.dumps(content))


@pytest.mark.parametrize("field", ["price", "cost_amount"])
@pytest.mark.parametrize("bad", [0.1, "-0", "01", "1.0", "1e2", "NaN", "Infinity", "1.0000001"])
def test_money_is_canonical_text_without_floating_point(
    bundle: seed.SeedBundle,
    field: str,
    bad: Any,
) -> None:
    wire = bundle.content.shops[0].skus[0].model_dump(mode="json")
    wire[field] = bad
    with pytest.raises(ValidationError):
        seed.SKU.model_validate_json(json.dumps(wire))


def test_hash_manifest_and_constructed_objects_are_revalidated(bundle: seed.SeedBundle) -> None:
    data = bundle.model_dump(mode="json")
    data["manifest"]["content_digest"] = "0" * 64
    with pytest.raises(ValidationError, match="SEED_MANIFEST_MISMATCH"):
        seed.SeedBundle.model_validate_json(json.dumps(data))
    data = bundle.model_dump(mode="json")
    data["manifest"]["shops"][0]["counts"]["products"] = 9
    with pytest.raises(ValidationError, match="SEED_MANIFEST_MISMATCH"):
        seed.SeedBundle.model_validate_json(json.dumps(data))
    data = bundle.model_dump(mode="json")
    data["manifest"]["shops"][0]["entities"][0]["content_hash"] = "0" * 64
    with pytest.raises(ValidationError, match="SEED_MANIFEST_MISMATCH"):
        seed.SeedBundle.model_validate_json(json.dumps(data))
    sku = bundle.content.shops[0].skus[0].model_copy(update={"cost_amount": "0"})
    shop = bundle.content.shops[0].model_copy(
        update={"skus": (sku, *bundle.content.shops[0].skus[1:])}
    )
    forged = bundle.content.model_copy(update={"shops": (shop, bundle.content.shops[1])})
    with pytest.raises(ValidationError):
        seed.FixtureContent.model_validate(forged)
    with pytest.raises(ValidationError):
        bundle.content.shops[0].skus[0].price = "0"  # type: ignore[misc]  # Frozen rejection.


@pytest.mark.parametrize("value", [True, 1.0, "1", -1, 100])
def test_template_index_strict(value: Any) -> None:
    with pytest.raises(ValueError, match="INVALID_TEMPLATE_INDEX"):
        seed.template_ref("v4-shop-a", "sku", value)


@pytest.mark.parametrize("extra", ["role", "tenant_id", "principal_id", "approved", "auth_version"])
def test_creation_dto_cannot_supply_authority(extra: str) -> None:
    wire = dict(request_key=str(uuid4()), fixture_version="v4-demo-seed-1")
    dto.CreateSessionInput.model_validate_json(json.dumps(wire))
    wire[extra] = "untrusted"
    with pytest.raises(ValidationError):
        dto.CreateSessionInput.model_validate_json(json.dumps(wire))


@pytest.mark.parametrize("bad", [True, 1.0, "1", -1])
def test_expected_epoch_generation_are_strict_cas_not_authority(bad: Any) -> None:
    wire = dict(
        request_key=str(uuid4()), persona_id="operator", expected_epoch=0, expected_generation=0
    )
    for field in ("expected_epoch", "expected_generation"):
        with pytest.raises(ValidationError):
            dto.PersonaInput.model_validate_json(json.dumps({**wire, field: bad}))


def test_bootstrap_minimal_recovery_cannot_leak_identity() -> None:
    key = uuid4()
    valid = dto.BootstrapOperation(
        operation="session_create",
        request_key=key,
        status="COMMITTED",
        recovery="OWNER_RECOVERY_REQUIRED",
    )
    assert set(valid.model_dump()) == {"operation", "request_key", "status", "recovery"}
    for field in ("tenant_id", "session_id", "csrf_token", "token", "shops", "principal_id"):
        wire = {**valid.model_dump(mode="json"), field: "not-authorized"}
        with pytest.raises(ValidationError):
            dto.BootstrapOperation.model_validate_json(json.dumps(wire))
    with pytest.raises(ValidationError, match="INVALID_RECOVERY_STATE"):
        dto.BootstrapOperation(
            operation="session_create",
            request_key=key,
            status="UNKNOWN",
            recovery="OWNER_RECOVERY_REQUIRED",
        )


def test_response_failure_unknown_and_context_are_explicit() -> None:
    wire: dict[str, Any] = dict(
        schema_version="v4-demo-v1",
        server_time=None,
        trace_id=str(uuid4()),
        status="UNKNOWN",
        error=dict(
            code="SERVICE_UNAVAILABLE",
            safe_message="服务暂不可用",
            retryable=False,
            request_key=None,
        ),
    )
    failure = dto.FailureEnvelope.model_validate_json(json.dumps(wire))
    assert failure.server_time is None
    assert "data" not in failure.model_dump()
    wire["error"]["retryable"] = 0
    with pytest.raises(ValidationError):
        dto.FailureEnvelope.model_validate_json(json.dumps(wire))
    context = dto.Context(
        tenant_id=uuid4(),
        organization_id=uuid4(),
        principal_id=uuid4(),
        shop_id=None,
        reset_epoch=0,
        auth_generation=0,
        authorized_at=datetime(2026, 11, 3, tzinfo=UTC),
    )
    data = context.model_dump(mode="json")
    data.pop("auth_generation")
    with pytest.raises(ValidationError):
        dto.Context.model_validate_json(json.dumps(data))


def test_public_dto_fields_match_frozen_openapi() -> None:
    document = json.loads(Path("docs/v4/baseline/v4-public-openapi.json").read_text())
    models = (
        dto.Context,
        dto.Shop,
        dto.Source,
        dto.Receipt,
        dto.BootstrapData,
        dto.SessionData,
        dto.CreateData,
        dto.SeedSummaryData,
        dto.ControlData,
        dto.Error,
        dto.FailureEnvelope,
        dto.BootstrapEnvelope,
        dto.SessionEnvelope,
        dto.CreateEnvelope,
        dto.SeedSummaryEnvelope,
        dto.ControlEnvelope,
        dto.OperationEnvelope,
    )
    for model in models:
        approved = document["components"]["schemas"][model.__name__]
        schema = model.model_json_schema()
        assert set(schema["properties"]) == set(approved["properties"]), model.__name__
        assert set(schema["required"]) == set(approved["required"]), model.__name__
        assert schema["additionalProperties"] is False
    requests: dict[str, type[dto.Contract]] = {
        "/api/v4/demo/sessions": dto.CreateSessionInput,
        "/api/v4/demo/persona": dto.PersonaInput,
        "/api/v4/demo/reset": dto.ResetInput,
        "/api/v4/demo/logout": dto.LogoutInput,
    }
    for path, request in requests.items():
        approved = document["paths"][path]["post"]["requestBody"]["content"]["application/json"][
            "schema"
        ]
        actual = request.model_json_schema()
        assert set(actual["properties"]) == set(approved["properties"])
        assert set(actual["required"]) == set(approved["required"])
        assert actual["additionalProperties"] is False


def test_seed_imports_have_no_runtime_or_io_dependencies() -> None:
    for module in (dto, seed):
        path = Path(module.__file__ or "")
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                name = node.module or ""
                assert not any(
                    part in name
                    for part in (
                        "infrastructure",
                        "entrypoints",
                        "adapters",
                        "psycopg",
                        "httpx",
                        "socket",
                    )
                )
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {
                    "now",
                    "today",
                    "connect",
                    "open",
                    "request",
                    "write_text",
                }


@pytest.mark.parametrize(
    "target,source",
    [
        (0, "other_shop"),
        (0, "other_product"),
        (0, "random"),
        (0, "null"),
        (4, "other_shop"),
        (4, "random"),
    ],
)
def test_variant_source_and_nullable_shape_are_exact(
    content: dict[str, Any],
    target: int,
    source: str,
) -> None:
    variants: dict[str, Any] = {
        "other_shop": content["shops"][1]["skus"][0]["variant_ref"],
        "other_product": content["shops"][0]["skus"][2]["variant_ref"],
        "random": str(UUID(int=99)),
        "null": None,
    }
    content["shops"][0]["skus"][target]["variant_ref"] = variants[source]
    with pytest.raises(ValidationError, match="INVALID_SKU_PRODUCT_VARIANT"):
        seed.FixtureContent.model_validate_json(json.dumps(content))


def test_sql_structure_has_deferred_bidirectional_binding_without_implicit_parameters() -> None:
    from sqlalchemy import text

    path = Path("backend/migrations/versions/0024_v4_demo_foundation.py")
    module = ast.parse(path.read_text())
    constants = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in module.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in ("DDL", "FUNCTIONS")
    }
    ddl, functions = constants["DDL"], constants["FUNCTIONS"]
    assert len(re.findall(r"CREATE TABLE business\.v4_demo_", ddl)) == 10
    assert "FOREIGN KEY(last_receipt_id,id,tenant_id,reset_epoch,auth_generation)" in ddl
    assert "FOREIGN KEY(receipt_id,owner_session_id,tenant_id,reset_epoch,auth_generation)" in ddl
    assert ddl.count("DEFERRABLE INITIALLY DEFERRED") == 2
    assert "to_jsonb(s) IS DISTINCT FROM to_jsonb(NEW)" in functions
    assert "NEW.id IS DISTINCT FROM s.last_receipt_id" in functions
    assert "r.epoch_before=OLD.reset_epoch" in functions
    assert "r.generation_before=OLD.auth_generation" in functions
    assert "TG_TABLE_NAME='v4_demo_events'" in functions
    assert functions.count("NOT coalesce(business.v4_demo_request_valid(") == 2
    assert "req->>'method' IS DISTINCT FROM 'POST'" in functions
    assert "req-ARRAY['method','path','body']" in functions
    assert not text(ddl).compile().params
    assert not text(functions).compile().params
