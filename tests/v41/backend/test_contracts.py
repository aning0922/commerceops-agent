"""Pure strict DTO boundaries; these checks do not claim runtime authorization."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from commerceops.application.v41 import contracts as dto
from pydantic import ValidationError

from scripts.v41_schema import DESTINATION, contract, encoded

pytestmark = pytest.mark.offline


def command() -> dict[str, object]:
    return dict(
        shop_id=str(uuid4()),
        request_key=str(uuid4()),
        expected_epoch=0,
        expected_generation=0,
        expected_data_revision="a" * 64,
        expected_version=0,
        tags=["演示"],
    )


@pytest.mark.parametrize("field", ["tenant_id", "principal_id", "roles", "approved", "server_time"])
def test_no_client_authority_fields(field: str) -> None:
    raw = command()
    raw[field] = "untrusted"
    with pytest.raises(ValidationError):
        dto.SetProductTags.model_validate_json(json.dumps(raw))


@pytest.mark.parametrize("value", [True, -1, 0.5, "0"])
def test_cas_is_strict_integer(value: object) -> None:
    raw = command()
    raw["expected_epoch"] = value
    with pytest.raises(ValidationError):
        dto.SetProductTags.model_validate_json(json.dumps(raw))


@pytest.mark.parametrize("tags", [["same", "same"], [" padded "], ["a"] * 9, ["x" * 25]])
def test_tags_not_silently_rewritten(tags: list[str]) -> None:
    raw = command()
    raw["tags"] = tags
    with pytest.raises(ValidationError):
        dto.SetProductTags.model_validate_json(json.dumps(raw))


def test_mapping_discovery_and_preview_recovery_are_operable() -> None:
    raw = command()
    del raw["expected_version"], raw["tags"]
    raw.update(format="csv", filename="products.csv", file_base64="c2t1Cg==")
    parsed = dto.ImportPreviewInput.model_validate_json(json.dumps(raw))
    assert parsed.mapping is None and parsed.parent_job_id is None
    raw["mapping"] = dict(sku="编码", title="名称", price="价格", currency="币种", tags=None)
    raw["parent_job_id"] = str(uuid4())
    assert dto.ImportPreviewInput.model_validate_json(json.dumps(raw)).parent_job_id is not None
    raw["mapping_version"] = True
    with pytest.raises(ValidationError):
        dto.ImportPreviewInput.model_validate_json(json.dumps(raw))
    key = uuid4()
    assert dto.PreviewLookup(request_key=key, status="UNKNOWN", job=None).job is None
    with pytest.raises(ValidationError):
        dto.PreviewLookup(request_key=key, status="COMMITTED", job=None)


def test_partial_metric_cannot_claim_numeric_value_or_zero_denominator() -> None:
    fields = dict(
        metric="paid_order_amount",
        value=None,
        known_value="12.5",
        unit="money",
        currency="TWD",
        completeness="PARTIAL",
        reason_codes=["UNKNOWN_PAYMENT_TIME"],
        included_count=1,
        excluded_count=1,
        settlement_status="UNKNOWN",
    )
    assert dto.Metric.model_validate_json(json.dumps(fields)).value is None
    fields["value"] = "12.5"
    with pytest.raises(ValidationError):
        dto.Metric.model_validate_json(json.dumps(fields))


def test_upload_source_cannot_impersonate_fixture() -> None:
    fields: dict[str, object] = dict(
        data_mode="demo_fixture",
        fixture_digest="a" * 64,
        baseline_snapshot_at=datetime.now(UTC).isoformat(),
        import_job_id=str(uuid4()),
    )
    with pytest.raises(ValidationError):
        dto.SourceRef.model_validate_json(json.dumps(fields))
    fields["data_mode"] = "demo_upload"
    fields["import_row"] = 2
    fields["file_digest"] = "b" * 64
    assert dto.SourceRef.model_validate_json(json.dumps(fields)).import_job_id is not None


def test_schema_is_generated_closed_and_has_preview_lookup() -> None:
    assert DESTINATION.read_text() == encoded()
    generated = contract()
    definitions = generated["json_schema"]["$defs"]
    for definition in definitions.values():
        if definition.get("type") == "object":
            assert definition["additionalProperties"] is False
    routes = {entry["path"]: entry for entry in generated["routes"]}
    lookup = routes["/api/v4/imports/preview-requests/{request_key}"]
    assert lookup["current_identity_required"] is True
    request_ref = routes["/api/v4/imports/previews"]["request"]["$ref"].split("/")[-1]
    preview = definitions[request_ref]
    assert "mapping" not in preview["required"]
    assert "parent_job_id" in preview["properties"]
    assert routes["/api/v4/products/{product_id}/tags"]["csrf_required"] is True
