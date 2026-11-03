"""日报来源的离线独立金标/transport反例；无HTTP服务、PG或外部凭据。"""

import copy
import hashlib
import inspect
import json
import time
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import httpx
import pytest
from commerceops.adapters.commerce.daily import collect, normalize
from commerceops.adapters.commerce.woocommerce_config import WooFilePins, WooReadOnlyConfig
from commerceops.application.daily.aggregation import aggregate_daily
from commerceops.application.daily.contracts import DailyRuleConfig
from commerceops.application.daily.source import (
    DailyManifest,
    DailyTaskRequest,
    MockMetadata,
    WooMetadata,
)
from commerceops.infrastructure.daily_sources import (
    ActiveBinding,
    DailyDeployment,
    fixture_rows,
    manifest_for,
)
from pydantic import ValidationError

from tests.test_daily_report import DAY, END, START
from tests.test_woocommerce_readonly import config as transport_config

pytestmark = pytest.mark.offline


def source_data() -> tuple[tuple[dict[str, Any], ...], dict[str, tuple[dict[str, Any], ...]]]:
    def row(identity: int, **updates: Any) -> dict[str, Any]:
        return {
            "id": identity,
            "currency": "CNY",
            "status": "processing",
            "date_created_gmt": START.isoformat(),
            "date_paid_gmt": START.isoformat(),
            "shipping_total": "0",
            "shipping_tax": "0",
            "fee_lines": [],
            "line_items": [],
            "total": "0",
            "refunds": [],
            **updates,
        }

    first = row(
        1,
        date_created_gmt=(START - timedelta(days=10)).isoformat(),
        shipping_total="5",
        shipping_tax="0.5",
        total="106.7",
        fee_lines=[{"id": 21, "total": "2", "total_tax": "0.2"}],
        line_items=[
            {"id": 11, "quantity": 3, "total": "60", "total_tax": "6"},
            {"id": 12, "quantity": 1, "total": "30", "total_tax": "3"},
        ],
    )
    zero_line = row(2, shipping_total="3", total="3")
    old = row(
        3,
        date_created_gmt=(START - timedelta(days=40)).isoformat(),
        date_paid_gmt=(START - timedelta(days=39)).isoformat(),
        total="50",
        status="refunded",
        line_items=[{"id": 31, "quantity": 1, "total": "50", "total_tax": "0"}],
        refunds=[{"id": 101}],
    )
    return (first, zero_line, old), {
        "1": (),
        "2": (),
        "3": (
            {"id": 101, "amount": "7.5", "date_created_gmt": START.isoformat(), "line_items": []},
        ),
    }


def metadata(tmp_path: Path) -> MockMetadata:
    return MockMetadata.model_validate(
        {
            "schema_version": "p6-daily-binding-v1",
            "organization_id": UUID(int=1),
            "shop_id": UUID(int=2),
            "config_ref": "daily-only-v1",
            "source_config_version": "source-1",
            "external_shop_key": "daily",
            "timezone": "Asia/Taipei",
            "currency": "CNY",
            "earliest_business_day": DAY,
            "manifest_ref": str(tmp_path / "manifest.json"),
            "manifest_digest": "a" * 64,
            "metric_version": "daily-metrics-v1",
            "status_mapping_version": "daily-status-v1",
            "source_kind": "mock",
            "environment": "test",
            "coverage_profile": "complete_fixture_v1",
            "fixture_ref": str(tmp_path / "fixture.json"),
            "fixture_digest": "b" * 64,
            "fixture_version": "daily-gold-1",
            "limits": {
                "per_page": 1,
                "max_pages": 32,
                "max_requests": 256,
                "timeout_seconds": 10,
                "max_elapsed_seconds": 18,
                "max_response_bytes": 2097152,
                "max_orders": 1000,
                "max_lines": 10000,
                "max_refunds": 10000,
                "max_snapshot_bytes": 8388608,
                "max_retries": 0,
            },
        }
    )


def manifest(meta: MockMetadata | WooMetadata) -> DailyManifest:
    return DailyManifest.model_validate(
        {
            "schema_version": "p6-daily-manifest-v1",
            "organization_id": meta.organization_id,
            "shop_id": meta.shop_id,
            "source_config_version": meta.source_config_version,
            "dataset_version": "daily-gold-1",
            "earliest_business_day": DAY,
            "latest_business_day": DAY,
            "controlled_dataset": True,
            "no_external_writers": True,
            "orders": (
                {"order_id": "1", "line_ids": ("11", "12"), "refund_ids": ()},
                {"order_id": "2", "line_ids": (), "refund_ids": ()},
                {"order_id": "3", "line_ids": ("31",), "refund_ids": ("101",)},
            ),
        }
    )


def request(meta: MockMetadata | WooMetadata) -> DailyTaskRequest:
    return DailyTaskRequest(
        schema_version="p6-daily-task-v1",
        daily_source=meta.source(UUID(int=3)),
        business_day=DAY,
        snapshot_id=UUID(int=4),
        rules=DailyRuleConfig(currency="CNY"),
        request_key=UUID(int=5),
        request_hash="c" * 64,
        conversation_id=UUID(int=6),
        requester_auth_version=1,
    )


def test_mapper_independent_gold_and_cross_period_refunds(tmp_path: Path) -> None:
    meta = metadata(tmp_path)
    orders, refunds = source_data()
    snapshot = normalize(
        request(meta), meta, orders, refunds, manifest(meta), END, END + timedelta(minutes=1)
    )
    actual = aggregate_daily(snapshot)
    assert actual.complete and actual.metrics is not None
    assert actual.metrics.paid_order_count == 2 and actual.metrics.created_order_count == 1
    assert actual.metrics.paid_order_total == Decimal("109.7")
    assert actual.metrics.refund_amount == Decimal("7.5") and actual.metrics.refund_count == 1
    assert (
        snapshot.refunds[0].quantity_reason == "AMOUNT_ONLY"
        and snapshot.refunds[0].restocked is None
    )


@pytest.mark.parametrize("state", ["pending", "on-hold", "failed", "trash"])
def test_payment_status_conflict_blocks_complete_report(tmp_path: Path, state: str) -> None:
    meta = metadata(tmp_path)
    orders, refunds = source_data()
    orders = ({**orders[0], "status": state}, *orders[1:])
    report = aggregate_daily(
        normalize(
            request(meta), meta, orders, refunds, manifest(meta), END, END + timedelta(seconds=1)
        )
    )
    assert not report.complete and report.metrics is None
    assert "PAYMENT_STATUS_CONFLICT" in report.coverage.quality_flags


@pytest.mark.parametrize("state", ["cancelled", "refunded", "completed"])
def test_later_status_preserves_recorded_payment(tmp_path: Path, state: str) -> None:
    meta = metadata(tmp_path)
    orders, refunds = source_data()
    report = aggregate_daily(
        normalize(
            request(meta),
            meta,
            ({**orders[0], "status": state}, *orders[1:]),
            refunds,
            manifest(meta),
            END,
            END + timedelta(seconds=1),
        )
    )
    assert report.complete and report.metrics is not None and report.metrics.paid_order_count == 2


@pytest.mark.parametrize("kind", ["order", "line", "refund"])
def test_manifest_detects_missing_objects(tmp_path: Path, kind: str) -> None:
    meta = metadata(tmp_path)
    orders, refunds = source_data()
    orders = copy.deepcopy(orders)
    refunds = copy.deepcopy(refunds)
    if kind == "order":
        orders = orders[1:]
        del refunds["1"]
    elif kind == "line":
        orders[0]["line_items"] = orders[0]["line_items"][1:]
    else:
        refunds["3"] = ()
    result = aggregate_daily(
        normalize(
            request(meta), meta, orders, refunds, manifest(meta), END, END + timedelta(seconds=1)
        )
    )
    assert (
        not result.complete
        and result.metrics is None
        and "COVERAGE_UNPROVEN" in result.coverage.quality_flags
    )


def test_new_owned_files_are_pinned_and_version_bound(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    meta = metadata(tmp_path)
    gold = manifest(meta)
    orders, refunds = source_data()
    for filename, body in (
        (meta.manifest_ref, gold.model_dump(mode="json")),
        (meta.fixture_ref, {"orders": orders, "refunds": refunds}),
    ):
        path = Path(filename)
        path.write_text(json.dumps(body))
        path.chmod(0o600)
    meta = meta.model_copy(
        update={
            "manifest_digest": hashlib.sha256(Path(meta.manifest_ref).read_bytes()).hexdigest(),
            "fixture_digest": hashlib.sha256(Path(meta.fixture_ref).read_bytes()).hexdigest(),
        }
    )
    assert manifest_for(meta) == gold
    assert fixture_rows(meta)[0][0]["id"] == 1
    binding = ActiveBinding(
        organization_id=meta.organization_id,
        shop_id=meta.shop_id,
        binding_id=UUID(int=3),
        config_digest=meta.config_digest,
        private_pin_digest=None,
    )
    deployment = DailyDeployment(
        schema_version="p6-daily-deployment-v1",
        directory=tmp_path,
        bindings=(binding,),
        model_requests_enabled=False,
        external_sender_enabled=False,
    )
    file = tmp_path / f"{binding.binding_id}.json"
    file.write_text(meta.model_dump_json())
    file.chmod(0o600)
    assert deployment.metadata(binding) == meta
    file.write_text(meta.model_copy(update={"currency": "USD"}).model_dump_json())
    with pytest.raises(ValueError, match="DAILY_SOURCE_BINDING_CHANGED"):
        deployment.metadata(binding)
    Path(meta.fixture_ref).write_text("{}")
    with pytest.raises(ValueError, match="DAILY_SOURCE_BINDING_CHANGED"):
        fixture_rows(meta)


def woo_metadata(tmp_path: Path, config: WooReadOnlyConfig) -> WooMetadata:
    body = metadata(tmp_path).model_dump(mode="python")
    for key in ("fixture_ref", "fixture_digest", "fixture_version"):
        del body[key]
    body.update(
        source_kind="woocommerce_test",
        coverage_profile="closed_test_manifest_v1",
        origin=config.base_url,
        consumer_key_file=config.consumer_key_file,
        consumer_secret_file=config.consumer_secret_file,
        ca_file=config.ca_file,
        private_pin_ref="new-owned-pin",
    )
    return WooMetadata.model_validate(body)


def test_complete_mock_transport_uses_all_headers_and_old_order_refunds(tmp_path: Path) -> None:
    config: WooReadOnlyConfig = cast(
        Callable[[Path], WooReadOnlyConfig], inspect.unwrap(transport_config)
    )(tmp_path)
    meta = woo_metadata(tmp_path, config)
    orders, refunds = source_data()
    seen = []

    def respond(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.path.endswith("/orders"):
            rows = [] if req.url.params["status"] == "trash" else list(orders)
        else:
            rows = list(refunds[req.url.path.split("/")[-2]])
        page = int(req.url.params["page"])
        size = int(req.url.params["per_page"])
        return httpx.Response(
            200,
            headers={
                "X-WP-Total": str(len(rows)),
                "X-WP-TotalPages": str((len(rows) + size - 1) // size),
            },
            stream=httpx.ByteStream(json.dumps(rows[(page - 1) * size : page * size]).encode()),
        )

    pins = WooFilePins(
        *(
            hashlib.sha256(Path(path).read_bytes()).hexdigest()
            for path in (config.consumer_key_file, config.consumer_secret_file, config.ca_file)
        )
    )
    snapshot, result, receipt = collect(
        request(meta),
        meta,
        manifest(meta),
        absolute_deadline=time.monotonic() + 18,
        pins=pins,
        transport=httpx.MockTransport(respond),
        clock=lambda: END + timedelta(minutes=1),
    )
    assert (
        result.complete
        and result.metrics is not None
        and str(result.metrics.paid_order_total) == "109.700000"
    )
    assert receipt.expected_set_hash == receipt.observed_set_hash and receipt.request_count == 21
    assert all(
        req.method == "GET" and req.url.params["dp"] == "6" and "after" not in req.url.params
        for req in seen
    )
    assert (
        snapshot.source.source_kind == "woocommerce_test"
        and snapshot.source.fixture_version is None
    )


@pytest.mark.parametrize(
    "bad",
    [{"max_elapsed_seconds": 19}, {"max_requests": 257}, {"max_retries": 1}, {"per_page": True}],
)
def test_limits_cannot_relax_transport_contract(tmp_path: Path, bad: dict[str, Any]) -> None:
    body = metadata(tmp_path).model_dump(mode="python")
    body["limits"].update(bad)
    with pytest.raises(ValidationError):
        MockMetadata.model_validate(body)


@pytest.mark.parametrize(
    "fault",
    ["401", "403", "302", "429", "500", "bad_headers", "missing_page", "cross_origin", "expired"],
)
def test_daily_transport_failure_cannot_become_complete(tmp_path: Path, fault: str) -> None:
    config = cast(Callable[[Path], WooReadOnlyConfig], inspect.unwrap(transport_config))(tmp_path)
    meta = woo_metadata(tmp_path, config)
    pins = WooFilePins(
        *(
            hashlib.sha256(Path(path).read_bytes()).hexdigest()
            for path in (config.consumer_key_file, config.consumer_secret_file, config.ca_file)
        )
    )
    calls = []

    def response(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        if fault.isdecimal():
            return httpx.Response(int(fault), headers={"Location": "https://example.invalid"})
        headers = {"X-WP-Total": "0", "X-WP-TotalPages": "0"}
        if fault == "bad_headers":
            headers["X-WP-Total"] = "unknown"
        if fault == "missing_page":
            headers.update({"X-WP-Total": "2", "X-WP-TotalPages": "2"})
        if fault == "cross_origin":
            headers["Link"] = '<https://example.invalid/orders>; rel="next"'
        return httpx.Response(200, headers=headers, stream=httpx.ByteStream(b"[]"))

    with pytest.raises(ValueError, match="DAILY_SOURCE_UNAVAILABLE"):
        collect(
            request(meta),
            meta,
            manifest(meta),
            absolute_deadline=time.monotonic() + (-1 if fault == "expired" else 18),
            pins=pins,
            transport=httpx.MockTransport(response),
            clock=lambda: END + timedelta(minutes=1),
        )
    assert len(calls) == (0 if fault == "expired" else 1)


def test_manifest_flags_and_private_source_json_are_strict(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    meta = metadata(tmp_path)
    body = manifest(meta).model_dump(mode="python")
    body["no_external_writers"] = 1
    with pytest.raises(ValidationError, match="DAILY_BOOLEAN_INVALID"):
        DailyManifest.model_validate(body)
    binding = ActiveBinding(
        organization_id=meta.organization_id,
        shop_id=meta.shop_id,
        binding_id=UUID(int=3),
        config_digest=meta.config_digest,
        private_pin_digest=None,
    )
    files = DailyDeployment(
        schema_version="p6-daily-deployment-v1",
        directory=tmp_path,
        bindings=(binding,),
        model_requests_enabled=False,
        external_sender_enabled=False,
    )
    filename = tmp_path / f"{binding.binding_id}.json"
    filename.write_text('{"currency":"CNY",' + meta.model_dump_json()[1:])
    filename.chmod(0o600)
    with pytest.raises(ValueError, match="DAILY_SOURCE_BINDING_CHANGED"):
        files.metadata(binding)
    filename.write_text(meta.model_dump_json())
    tmp_path.chmod(0o755)
    with pytest.raises(ValueError, match="DAILY_SOURCE_BINDING_CHANGED"):
        files.metadata(binding)


@pytest.mark.parametrize("kind", ["unknown_mapping", "null_quantity", "known_quantity"])
def test_refund_quantity_evidence_never_guessed_from_amount(tmp_path: Path, kind: str) -> None:
    meta = metadata(tmp_path)
    orders, refunds = source_data()
    item = {
        "id": 1001,
        "quantity": None if kind == "null_quantity" else -1,
        "meta_data": []
        if kind == "unknown_mapping"
        else [{"key": "_refunded_item_id", "value": 31}],
    }
    refunds["3"] = ({**refunds["3"][0], "line_items": [item]},)
    snapshot = normalize(
        request(meta), meta, orders, refunds, manifest(meta), END, END + timedelta(seconds=1)
    )
    actual = aggregate_daily(snapshot)
    assert (
        actual.complete
        and actual.metrics is not None
        and actual.metrics.refund_amount == Decimal("7.5")
    )
    evidence = snapshot.refunds[0]
    if kind == "unknown_mapping":
        assert not evidence.lines and evidence.quantity_reason == "LINE_MAPPING_UNVERIFIED"
    elif kind == "null_quantity":
        assert (
            evidence.lines[0].quantity is None
            and evidence.lines[0].quantity_reason == "SOURCE_QUANTITY_UNAVAILABLE"
        )
    else:
        assert evidence.lines[0].quantity == 1 and evidence.lines[0].quantity_reason is None
