"""P5 来源冻结与私有 pin 反例；全离线，不证明实际店铺或PG权限。"""

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from commerceops.adapters.commerce.woocommerce import WooCommerce
from commerceops.adapters.commerce.woocommerce_config import WooReadOnlyConfig
from commerceops.application.commerce.source_binding import (
    CommerceSourceCapability,
    RegisteredWooSource,
    SourceBindingError,
    WooSourceMetadata,
)
from commerceops.infrastructure.commerce_sources import CommerceSourceFiles

from tests.test_woocommerce_readonly import config as config

pytestmark = pytest.mark.offline


def bound(
    config: WooReadOnlyConfig, directory: Path
) -> tuple[CommerceSourceFiles, RegisteredWooSource, WooSourceMetadata]:
    value = WooSourceMetadata(
        organization_id=uuid4(),
        shop_id=uuid4(),
        config_ref="owned-woo",
        source_config_version="owned-v1",
        origin=config.base_url,
        external_shop_key=config.shop_id,
        currency=config.currency,
        timezone=config.timezone,
        profile="positive-v1",
        anchor_day=date(2026, 10, 1),
        consumer_key_file=config.consumer_key_file,
        consumer_secret_file=config.consumer_secret_file,
        ca_file=config.ca_file,
        private_pin_ref="owned-pins-v1",
    )
    registered = RegisteredWooSource(
        binding_id=uuid4(),
        organization_id=value.organization_id,
        shop_id=value.shop_id,
        config_ref=value.config_ref,
        source_config_version=value.source_config_version,
        config_digest=value.config_digest,
    )
    encoded = json.dumps(
        {
            "schema_version": "p5-private-pins-v1",
            "binding_id": str(registered.binding_id),
            "config_digest": registered.config_digest,
            **{
                key: hashlib.sha256(Path(filename).read_bytes()).hexdigest()
                for key, filename in (
                    ("key", config.consumer_key_file),
                    ("secret", config.consumer_secret_file),
                    ("ca", config.ca_file),
                )
            },
        }
    ).encode()
    for path, body in (
        (directory / f"{registered.binding_id}.json", value.model_dump_json().encode()),
        (directory / "owned-pins-v1.pins.json", encoded),
    ):
        path.write_bytes(body)
        path.chmod(0o600)
    files = CommerceSourceFiles(
        directory,
        {(value.organization_id, value.shop_id): registered.binding_id},
        {"owned-pins-v1": hashlib.sha256(encoded).hexdigest()},
    )
    return files, registered, value


def test_nonsecret_resolution_never_opens_credential_or_pin_files(
    config: WooReadOnlyConfig, tmp_path: Path
) -> None:
    files, registered, value = bound(config, tmp_path)
    for filename in (
        config.consumer_key_file,
        config.consumer_secret_file,
        config.ca_file,
        str(tmp_path / "owned-pins-v1.pins.json"),
    ):
        Path(filename).unlink()
    assert files.metadata(registered) == value
    with pytest.raises(SourceBindingError):
        files.credential_pins(registered, value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("origin", "https://localhost:19443"),
        ("external_shop_key", "another-shop"),
        ("anchor_day", "2026-09-30"),
        ("max_requests", 255),
        ("currency", "USD"),
        ("timezone", "UTC"),
        ("organization_id", "00000000-0000-4000-8000-000000000001"),
        ("shop_id", "00000000-0000-4000-8000-000000000002"),
        ("private_pin_ref", "replacement-pin"),
    ],
)
def test_same_version_changed_configuration_is_not_self_registered(
    config: WooReadOnlyConfig, tmp_path: Path, field: str, value: Any
) -> None:
    files, registered, original = bound(config, tmp_path)
    body = original.model_dump(mode="json")
    body[field] = value
    (tmp_path / f"{registered.binding_id}.json").write_text(json.dumps(body))
    with pytest.raises(SourceBindingError, match="COMMERCE_SOURCE_UNAVAILABLE"):
        files.metadata(registered)
    assert registered.config_digest == original.config_digest


@pytest.mark.parametrize(
    "field",
    [
        "consumer_key_file",  # explicit nonsecret file reference
        "consumer_secret_file",  # explicit nonsecret file reference
        "ca_file",
    ],
)
def test_same_file_reference_changed_bytes_fails_before_any_http(
    config: WooReadOnlyConfig, tmp_path: Path, field: str
) -> None:
    files, registered, actual = bound(config, tmp_path)
    pins = files.credential_pins(registered, actual)
    target = Path(getattr(config, field))
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="PRIVATE_CREDENTIAL_PIN_MISMATCH"):
        WooCommerce(
            config,
            pins=pins,
            transport=httpx.MockTransport(lambda _: pytest.fail("no HTTP after pin mismatch")),
        )
    assert "sha256" not in repr(pins)


def test_private_pin_replacement_and_scope_rebinding_fail_closed(
    config: WooReadOnlyConfig, tmp_path: Path
) -> None:
    files, registered, actual = bound(config, tmp_path)
    target = tmp_path / "owned-pins-v1.pins.json"
    target.write_text(target.read_text() + " ")
    with pytest.raises(SourceBindingError):
        files.credential_pins(registered, actual)
    foreign = registered.model_copy(update={"organization_id": uuid4()})
    with pytest.raises(SourceBindingError):
        files.metadata(foreign)
    with pytest.raises(TypeError):
        files.private_pin_digests["owned-pins-v1"] = "0" * 64  # type: ignore[index]


def test_woo_unavailable_capability_cannot_implicitly_become_mock() -> None:
    capability = CommerceSourceCapability(
        source_kind="woocommerce_test", source_config_version=None, creation_enabled=False
    )
    assert capability.model_dump()["source_kind"] == "woocommerce_test"
    with pytest.raises(ValueError, match="COMMERCE_SOURCE_UNAVAILABLE"):
        CommerceSourceCapability(
            source_kind="woocommerce_test", source_config_version=None, creation_enabled=True
        )


@pytest.mark.parametrize(
    "extra",
    ["source_binding_id", "organization_id", "fixture_case", "dataset_version", "origin", "now"],
)
def test_public_woo_create_and_n01_reject_private_or_mock_fields(extra: str) -> None:
    from commerceops.application.replenishment.contracts import CreateInput
    from commerceops.application.replenishment.nl_preflight import PreflightRequest
    from pydantic import TypeAdapter

    parameters = {
        "source_mode": "woocommerce_test",
        "source_config_version": "owned-v1",
        "L": 3,
        "R": 7,
        "S": 2,
    }
    create = {
        "schema_version": "p3-web-v1",
        "mode": "new_cycle",
        "request_key": str(uuid4()),
        "shop_id": str(uuid4()),
        "parameters": {**parameters, extra: "forged"},
    }
    with pytest.raises(ValueError):
        TypeAdapter(CreateInput).validate_json(json.dumps(create))
    n01 = {
        "schema_version": "p3-web-v1",
        "source_mode": "woocommerce_test",
        "source_config_version": "owned-v1",
        "shop_id": str(uuid4()),
        "text": "分析库存 L=3 R=7 S=2",
        extra: "forged",
    }
    with pytest.raises(ValueError):
        TypeAdapter(PreflightRequest).validate_json(json.dumps(n01))


@pytest.mark.parametrize(
    "text,status",
    [
        ("分析库存 L=3 R=7 S=2", "ready"),
        ("分析库存", "clarify"),
        ("分析库存 L=3 R=7 S=2 再采购", "clarify"),
        ("退款 L=3 R=7 S=2", "unsupported"),
    ],
)
def test_woo_n01_uses_original_text_grammar_and_frozen_metadata(
    config: WooReadOnlyConfig,
    tmp_path: Path,
    text: str,
    status: str,
) -> None:
    from commerceops.application.replenishment.nl_preflight import (
        WooPreflightInput,
        WooWindow,
        parse_woo_preflight,
    )

    _, _, metadata = bound(config, tmp_path)
    result = parse_woo_preflight(
        WooPreflightInput(
            schema_version="p3-web-v1",
            source_mode="woocommerce_test",
            shop_id=metadata.shop_id,
            source_config_version=metadata.source_config_version,
            text=text,
        ),
        WooWindow(
            start=metadata.window.start,
            end=metadata.window.end,
            timezone=metadata.timezone,
            as_of=metadata.business_now,
        ),
    )
    assert result.status == status
    assert result.source.evidence_mode == "not_used" and not result.execution_available
    assert result.window.source == "commerce_configuration"
    assert result.scope.kind == "all_shop_products"
    if result.draft is not None:
        assert set(result.draft.model_dump()) == {
            "source_mode",
            "source_config_version",
            "L",
            "R",
            "S",
        }
    serialized = result.model_dump_json()
    assert config.base_url not in serialized and str(tmp_path) not in serialized


@pytest.mark.parametrize("refund_failure", [False, True])
def test_business_collector_covers_orders_without_lines_and_final_validation(
    config: WooReadOnlyConfig,
    monkeypatch: pytest.MonkeyPatch,
    refund_failure: bool,
) -> None:
    import asyncio

    from commerceops.adapters.commerce.woocommerce_http import WooReadFailure
    from commerceops.application.commerce.contracts import ErrorCode
    from commerceops.infrastructure.woo_collection import WooInventoryCollector

    from tests.test_woocommerce_readonly import order

    adapter = WooCommerce(config, transport=httpx.MockTransport(lambda _: pytest.fail("no HTTP")))
    paths: list[str] = []
    final: list[bool] = []

    def scan(path: str, query: Any) -> tuple[dict[str, Any], ...]:
        paths.append(path)
        if path == "products":
            return ()
        if path == "orders":
            return ({**order(), "line_items": [], "refunds": []},)
        assert path == "orders/101/refunds"
        if refund_failure:
            raise WooReadFailure(ErrorCode.TIMEOUT)
        return ()

    monkeypatch.setattr(adapter.http, "scan", scan)
    monkeypatch.setattr(adapter.http, "revalidate", lambda: final.append(True))
    result = asyncio.run(WooInventoryCollector(adapter, config.window.end).collect())
    assert paths == ["products", "orders", "orders/101/refunds"]
    assert result.data.complete is (not refund_failure)
    assert final == ([] if refund_failure else [True])
    assert adapter.http.client.is_closed


def test_factory_absolute_deadline_already_consumed_fails_before_http(
    config: WooReadOnlyConfig,
) -> None:
    import time

    from commerceops.application.commerce.contracts import ErrorCode

    adapter = WooCommerce(
        config,
        absolute_deadline=time.monotonic() - 1,
        transport=httpx.MockTransport(lambda _: pytest.fail("expired factory cannot send")),
    )
    try:
        page = adapter.list_products()
        assert page.error is not None and page.error.code == ErrorCode.TIMEOUT
        assert sum(adapter.http.counts.values()) == 0
    finally:
        adapter.close()
