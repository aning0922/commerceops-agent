"""Contract-shaped pure invariants; no HTTP/PG results are fabricated or signed."""

from uuid import uuid4

import pytest
from commerceops.application.v41 import contracts as dto

from .http_recipes import assert_context, fulfillment_fields

pytestmark = pytest.mark.offline


@pytest.mark.parametrize(
    "field",
    ["tenant_id", "organization_id", "principal_id", "shop_id", "reset_epoch", "auth_generation"],
)
def test_schema_valid_but_wrong_scope_cannot_pass(field: str) -> None:
    current = {
        "tenant_id": str(uuid4()),
        "organization_id": str(uuid4()),
        "principal_id": str(uuid4()),
        "shop_id": None,
        "reset_epoch": 0,
        "auth_generation": 0,
        "authorized_at": "2026-11-04T00:00:00Z",
    }
    shop = str(uuid4())
    response = {**current, "shop_id": shop}
    response[field] = 1 if field in {"reset_epoch", "auth_generation"} else str(uuid4())
    with pytest.raises(AssertionError, match="CONTEXT_DRIFT"):
        assert_context(response, current, shop)


def test_shop_binding_is_request_target_not_null_session_shop() -> None:
    current = {
        "tenant_id": str(uuid4()),
        "organization_id": str(uuid4()),
        "principal_id": str(uuid4()),
        "shop_id": None,
        "reset_epoch": 0,
        "auth_generation": 0,
        "authorized_at": "2026-11-04T00:00:00Z",
    }
    shop = str(uuid4())
    assert_context(
        {**current, "shop_id": shop, "authorized_at": "2026-11-04T00:01:00Z"}, current, shop
    )
    with pytest.raises(AssertionError):
        assert_context({**current, "shop_id": None}, current, shop)


def test_fulfillment_uses_real_order_contract_field_not_product_version() -> None:
    assert "version" not in dto.Order.model_fields
    assert "fulfillment_version" in dto.Order.model_fields
    assert fulfillment_fields({"fulfillment_version": 3}) == {
        "expected_version": 3,
        "action": "mark_demo_fulfilled",
    }
