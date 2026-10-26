"""离线安全反例与合成DTO单位测试；不作为真实Woo或本批平台Gate。"""

import json
import ssl
from pathlib import Path
from typing import Any

import certifi
import httpx
import pytest
from commerceops.adapters.commerce.woocommerce import WooCommerce
from commerceops.adapters.commerce.woocommerce_config import WooReadOnlyConfig, read_credential
from commerceops.application.commerce.contracts import CommerceFailure, ErrorCode, Quality, Window
from pytest import MonkeyPatch as Patch

from scripts.woo_readonly_probe import compare_groups, expected_input, project, write_output

pytestmark = pytest.mark.offline


@pytest.fixture
def config(tmp_path: Path) -> WooReadOnlyConfig:
    tmp_path.chmod(0o700)
    for name, prefix in (("key", "ck"), ("secret", "cs")):
        p = tmp_path / name
        p.write_text(prefix + "_" + "1" * 40)
        p.chmod(0o600)
    ca = tmp_path / "ca.crt"
    bundle = Path(certifi.where()).read_text()
    first = bundle.index("-----BEGIN CERTIFICATE-----")
    last = bundle.index("-----END CERTIFICATE-----", first) + len("-----END CERTIFICATE-----")
    ca.write_text(bundle[first:last] + "\n")
    ca.chmod(0o600)
    return WooReadOnlyConfig(
        base_url="https://127.0.0.1:18443",
        consumer_key_file=str(tmp_path / "key"),
        consumer_secret_file=str(tmp_path / "secret"),
        ca_file=str(ca),
        shop_id="woo-local",
        timezone="Asia/Shanghai",
        currency="CNY",
        window=Window.model_validate(
            {"start": "2026-10-18T16:00:00Z", "end": "2026-10-25T16:00:00Z"}
        ),
        per_page=1,
    )


def response(
    rows: Any,
    *,
    total: int | str | None = None,
    pages: int | str | None = None,
    extra: dict[str, str] | None = None,
) -> httpx.Response:
    count = len(rows) if isinstance(rows, list) else 1
    headers = {
        "X-WP-Total": str(total if total is not None else count),
        "X-WP-TotalPages": str(pages if pages is not None else count),
        **(extra or {}),
    }
    return httpx.Response(200, headers=headers, stream=httpx.ByteStream(json.dumps(rows).encode()))


def product(identity: int = 1, **updates: Any) -> dict[str, Any]:
    return {
        "id": identity,
        "type": "simple",
        "status": "publish",
        "name": "Synthetic product",
        "sku": "",
        "manage_stock": True,
        "stock_quantity": 5,
        "stock_status": "instock",
        "backorders": "no",
        "date_modified_gmt": "2026-10-26T00:00:00",
        **updates,
    }


def adapter_with(config: WooReadOnlyConfig, callback: Any) -> WooCommerce:
    return WooCommerce(config, transport=httpx.MockTransport(callback))


@pytest.mark.parametrize(
    "status,code",
    [
        (401, ErrorCode.AUTH_FAILED),
        (403, ErrorCode.PERMISSION_DENIED),
        (404, ErrorCode.RESOURCE_NOT_FOUND),
        (400, ErrorCode.INVALID_DATA),
        (429, ErrorCode.RATE_LIMITED),
        (500, ErrorCode.PROVIDER_UNAVAILABLE),
        (503, ErrorCode.PROVIDER_UNAVAILABLE),
        (302, ErrorCode.REDIRECT_REJECTED),
    ],
)
def test_http_failure_never_empty_complete_or_credential_leak(
    config: WooReadOnlyConfig, status: int, code: ErrorCode
) -> None:
    requests = []

    def fail(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            status,
            headers={"Location": "https://example.invalid/steal"},
            text=Path(config.consumer_secret_file).read_text(),
        )

    adapter = adapter_with(config, fail)
    try:
        page = adapter.list_products()
        assert not page.complete and page.error is not None and page.error.code == code
        assert page.items == () and len(requests) == 1
        dumped = page.model_dump_json()
        assert Path(config.consumer_secret_file).read_text() not in dumped
        assert requests[0].method == "GET" and requests[0].url.host == "127.0.0.1"
        assert "consumer_key" not in requests[0].url.query.decode()
        assert "consumer_secret" not in requests[0].url.query.decode()
    finally:
        adapter.close()


@pytest.mark.parametrize(
    "kind,code",
    [
        ("timeout", ErrorCode.TIMEOUT),
        ("connect", ErrorCode.CONNECTION_FAILED),
        ("tls", ErrorCode.TLS_FAILURE),
    ],
)
def test_transport_classification(config: WooReadOnlyConfig, kind: str, code: ErrorCode) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        if kind == "timeout":
            raise httpx.ReadTimeout("private exception", request=request)
        if kind == "tls":
            try:
                raise ssl.SSLCertVerificationError("private TLS detail")
            except ssl.SSLCertVerificationError as cause:
                raise httpx.ConnectError("private TLS detail", request=request) from cause
        raise httpx.ConnectError("private DNS detail", request=request)

    adapter = adapter_with(config, fail)
    try:
        page = adapter.list_products()
        assert page.error is not None and page.error.code == code and not page.complete
        assert "private" not in page.model_dump_json()
    finally:
        adapter.close()


@pytest.mark.parametrize(
    "damage,quality",
    [
        ("missing", Quality.MISSING_PAGE),
        ("duplicate", Quality.DUPLICATE_ID),
        ("changed_total", Quality.SOURCE_CHANGED),
        ("changed_body", Quality.SOURCE_CHANGED),
        ("unordered", Quality.MISSING_PAGE),
        ("invalid_header", Quality.PARTIAL_FAILURE),
        ("capacity", Quality.CAPACITY_LIMIT),
    ],
)
def test_incomplete_or_mutating_pagination_rejected(
    config: WooReadOnlyConfig, damage: str, quality: Quality
) -> None:
    calls = 0

    def serve(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        page = int(request.url.params["page"])
        total: int | str = 2
        pages: int | str = 2
        row = product(page)
        if damage == "missing" and page == 2:
            return response([], total=2, pages=2)
        if damage == "duplicate" and page == 2:
            row = product(1)
        if damage == "unordered":
            row = product(3 if page == 1 else 2)
        if damage == "changed_total" and page == 2:
            total, pages = 3, 3
        if damage == "changed_body" and calls > 2:
            row = product(page, name="Mutated")
        if damage == "invalid_header":
            total = "02"
        if damage == "capacity":
            total, pages = 201, 201
        return response([row], total=total, pages=pages)

    adapter = adapter_with(config, serve)
    try:
        page = adapter.list_products()
        assert not page.complete and page.error is not None
        assert quality in page.warnings
    finally:
        adapter.close()


@pytest.mark.parametrize(
    "link",
    [
        '<https://example.invalid/products?page=2>; rel="next"',
        '<https://u:p@127.0.0.1:18443/wp-json/wc/v3/products?page=2>; rel="next"',
        '<https://127.0.0.1:18443/wp-json/wc/v3/products?consumer_key=bad>; rel="next"',
    ],
)
def test_cross_origin_or_credential_link_fails_without_following(
    config: WooReadOnlyConfig, link: str
) -> None:
    calls = []

    def serve(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return response([product()], extra={"Link": link})

    adapter = adapter_with(config, serve)
    try:
        page = adapter.list_products()
        assert page.error is not None and page.error.code == ErrorCode.REDIRECT_REJECTED
        assert len(calls) == 1 and calls[0].url.host == "127.0.0.1"
    finally:
        adapter.close()


@pytest.mark.parametrize(
    "damage",
    ["json", "duplicate_key", "nan", "oversize", "encoded", "fractional_stock", "bool_stock"],
)
def test_invalid_payload_rejected(config: WooReadOnlyConfig, damage: str) -> None:
    def serve(_: httpx.Request) -> httpx.Response:
        if damage == "oversize":
            return httpx.Response(200, stream=httpx.ByteStream(b"x" * 512))
        if damage == "encoded":
            return response([product()], extra={"Content-Encoding": "gzip"})
        raw = {
            "json": b"no-json",
            "duplicate_key": b'[{"id":1,"id":1}]',
            "nan": b'[{"id":NaN}]',
        }.get(damage)
        if raw is not None:
            return httpx.Response(
                200,
                headers={"X-WP-Total": "1", "X-WP-TotalPages": "1"},
                stream=httpx.ByteStream(raw),
            )
        return response([product(stock_quantity=True if damage == "bool_stock" else 1.5)])

    if damage == "oversize":
        config = config.model_copy(update={"max_response_bytes": 128})
    adapter = adapter_with(config, serve)
    try:
        page = adapter.list_products()
        if damage in {"fractional_stock", "bool_stock"}:
            assert page.error is None
            result = adapter.get_inventory(page.items[0].sku_key)
            assert result.error is not None and not result.complete
        else:
            assert page.error is not None and not page.complete
    finally:
        adapter.close()


def test_cursor_cannot_cross_adapter_query_or_scope(config: WooReadOnlyConfig) -> None:
    def serve(request: httpx.Request) -> httpx.Response:
        return response([product(int(request.url.params["page"]))], total=2, pages=2)

    a, b = adapter_with(config, serve), adapter_with(config, serve)
    try:
        page = a.list_products()
        assert page.next_cursor is not None
        with pytest.raises(CommerceFailure, match="INVALID_CURSOR"):
            b.list_products(cursor=page.next_cursor)
        with pytest.raises(CommerceFailure, match="INVALID_CURSOR"):
            a.list_order_lines(config.window, cursor=page.next_cursor)
        assert a.list_products().next_cursor == page.next_cursor
    finally:
        a.close()
        b.close()


def test_request_and_elapsed_limits(config: WooReadOnlyConfig) -> None:
    a = adapter_with(config.model_copy(update={"max_requests": 1}), lambda _: response([product()]))
    try:
        page = a.list_products()
        assert page.error is not None and Quality.CAPACITY_LIMIT in page.warnings
        assert sum(a.http.counts.values()) == 1
        a.http.started -= 1000
        result = a.get_inventory("sku/woo-local/1/p")
        assert result.error is not None and result.error.code == ErrorCode.TIMEOUT
    finally:
        a.close()


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:18443",
        "https://example.com:443",
        "https://u:p@localhost:18443",
        "https://localhost:18443?consumer_key=x",
        "https://localhost:18443/path",
        "https://localhost:18443#frag",
    ],
)
def test_only_explicit_local_https_origin(config: WooReadOnlyConfig, url: str) -> None:
    with pytest.raises(ValueError):
        WooReadOnlyConfig.model_validate({**config.model_dump(), "base_url": url})


def test_credentials_permissions_symlink_and_redaction(
    config: WooReadOnlyConfig, tmp_path: Path
) -> None:
    key = Path(config.consumer_key_file)
    key.chmod(0o644)
    with pytest.raises(ValueError, match="UNSAFE"):
        read_credential(str(key), "ck")
    key.chmod(0o600)
    alias = tmp_path / "alias"
    alias.symlink_to(key)
    with pytest.raises(OSError):
        read_credential(str(alias), "ck")
    adapter = adapter_with(config, lambda _: response([]))
    try:
        assert Path(config.consumer_secret_file).read_text() not in adapter.http.redact(
            Path(config.consumer_secret_file).read_text()
        )
    finally:
        adapter.close()


def test_normalization_unknown_shared_pool_and_decimal_are_dto_facts(
    config: WooReadOnlyConfig, monkeypatch: Patch
) -> None:
    """直接合成DTO输入，不模拟一次实际Woo成功；实际Gate另读B的真实API。"""
    adapter = adapter_with(config, lambda _: pytest.fail("No network in normalization unit"))
    parent = product(2, type="variable", variations=[3, 4], stock_quantity=8)
    independent = product(3, manage_stock=True, stock_quantity=0)
    shared = product(4, manage_stock="parent", stock_quantity=None)

    def scan(path: str, _: Any) -> tuple[dict[str, Any], ...]:
        return (
            (product(1, manage_stock=False, stock_quantity=None), parent)
            if path == "products"
            else (independent, shared)
        )

    monkeypatch.setattr(adapter.http, "scan", scan)
    try:
        page = adapter.list_products()
        assert page.error is None and len(adapter._catalog) == 3
        unknown = adapter.get_inventory("sku/woo-local/1/p")
        assert unknown.item is not None and unknown.item.available_stock is None
        assert unknown.item.inbound_units is None and unknown.item.inbound_quality == "unknown"
        stock = adapter.get_inventory("sku/woo-local/2/v/4")
        assert stock.item is not None and stock.item.stock_pool_key == "pool/woo-local/2"
        assert stock.item.available_stock == 8 and stock.item.pool_allocation == "unresolved"
        assert not stock.complete and Quality.SHARED_POOL_UNRESOLVED in stock.warnings
        own = adapter.get_inventory("sku/woo-local/2/v/3")
        assert own.item is not None and own.item.stock_pool_key == "pool/woo-local/3"
        assert own.item.available_stock == 0
    finally:
        adapter.close()


def order(
    oid: int = 101, *, created: str = "2026-10-18T16:00:00", **line_updates: Any
) -> dict[str, Any]:
    return {
        "id": oid,
        "date_created_gmt": created,
        "date_paid_gmt": "2026-10-18T16:00:01",
        "date_completed_gmt": None,
        "currency": "CNY",
        "status": "processing",
        "refunds": [{"id": 301}],
        "line_items": [
            {
                "id": 11,
                "product_id": 1,
                "variation_id": 0,
                "quantity": 3,
                "total": "10.50",
                "total_tax": "0.50",
                **line_updates,
            }
        ],
    }


def test_order_boundaries_and_refund_original_line_cohort(
    config: WooReadOnlyConfig, monkeypatch: Patch
) -> None:
    adapter = adapter_with(config, lambda _: pytest.fail("DTO unit must not use HTTP"))
    calls = []

    def scan(path: str, query: Any) -> tuple[dict[str, Any], ...]:
        calls.append((path, query))
        if path == "products":
            return (product(),)
        if path == "orders":
            return (
                {**order(), "refunds": [{"id": 301}, {"id": 302}]},
                order(102, created="2026-10-18T15:59:59"),
                order(103, created="2026-10-25T16:00:00"),
            )
        return (
            {
                "id": 301,
                "amount": "3.50",
                "date_created_gmt": "2026-10-26T01:00:00",
                "line_items": [],
            },
            {
                "id": 302,
                "amount": "-1.25",
                "date_created_gmt": "2026-10-26T02:00:00",
                "restocked": True,
                "line_items": [
                    {
                        "id": 999,
                        "quantity": -1,
                        "meta_data": [{"key": "_refunded_item_id", "value": "11"}],
                    }
                ],
            },
        )

    monkeypatch.setattr(adapter.http, "scan", scan)
    try:
        lines = adapter.list_order_lines(config.window)
        assert lines.error is None and len(lines.items) == 1
        assert str(lines.items[0].net_amount) == "10.50"
        assert lines.items[0].order_id == "101" and lines.items[0].quantity == 3
        query = next(q for path, q in calls if path == "orders")
        assert query["dates_are_gmt"] == "true"
        assert query["after"].startswith("2026-10-18T15:59:59")
        refunds = adapter.list_refunds(("101",))
        assert refunds.error is None and refunds.next_cursor is not None
        amount_only = refunds.items[0]
        assert amount_only.lines == () and amount_only.quantity_reason == "AMOUNT_ONLY_REFUND"
        partial = adapter.list_refunds(("101",), cursor=refunds.next_cursor).items[0]
        assert partial.lines[0].line_id == "11" and partial.lines[0].refunded_quantity == 1
        assert str(partial.refund_amount) == "1.25" and partial.restocked is None
        assert partial.created_at > config.window.end  # refund cohort is not refund-time window
    finally:
        adapter.close()


@pytest.mark.parametrize(
    "updates",
    [
        {"quantity": True},
        {"quantity": 1.2},
        {"quantity": -1},
        {"total": 1.2},
        {"total": "NaN"},
        {"variation_id": False},
        {"product_id": 0},
        {"id": 0},
    ],
)
def test_bad_order_values_cannot_be_coerced(
    config: WooReadOnlyConfig, monkeypatch: Patch, updates: dict[str, Any]
) -> None:
    adapter = adapter_with(config, lambda _: pytest.fail("No HTTP"))
    monkeypatch.setattr(
        adapter.http,
        "scan",
        lambda path, _query: (product(),) if path == "products" else (order(**updates),),
    )
    try:
        page = adapter.list_order_lines(config.window)
        assert page.error is not None and page.error.code == ErrorCode.INVALID_DATA
        assert not page.complete and not page.items
    finally:
        adapter.close()


@pytest.mark.parametrize(
    "damage",
    [
        "own_id",
        "foreign_id",
        "duplicate_link",
        "positive_quantity",
        "fractional_quantity",
        "unknown_cohort",
    ],
)
def test_refund_links_and_quantity_must_be_proven(
    config: WooReadOnlyConfig, monkeypatch: Patch, damage: str
) -> None:
    adapter = adapter_with(config, lambda _: pytest.fail("No HTTP"))
    line: dict[str, Any] = {
        "id": 999,
        "quantity": -1,
        "meta_data": [{"key": "_refunded_item_id", "value": "11"}],
    }
    if damage == "own_id":
        line["meta_data"] = []
    if damage == "foreign_id":
        line["meta_data"][0]["value"] = "12"
    if damage == "duplicate_link":
        line["meta_data"] *= 2
    if damage == "positive_quantity":
        line["quantity"] = 1
    if damage == "fractional_quantity":
        line["quantity"] = -1.2
    adapter._orders = {"101": order()}
    monkeypatch.setattr(
        adapter.http,
        "scan",
        lambda _path, _query: (
            {
                "id": 301,
                "amount": "1.50",
                "date_created_gmt": "2026-10-26T01:00:00",
                "line_items": [line],
            },
        ),
    )
    try:
        page = adapter.list_refunds(("102" if damage == "unknown_cohort" else "101",))
        assert page.error is not None and not page.complete
    finally:
        adapter.close()


def test_expected_projection_and_private_exclusive_output(
    config: WooReadOnlyConfig, tmp_path: Path
) -> None:
    expected: dict[str, Any] = {
        "schema_version": "woo-local-expectations-v1",
        "fixture_version": "local-v1",
        "business_now": "2026-10-26T00:00:00Z",
        "shop_id": config.shop_id,
        "timezone": config.timezone,
        "currency": config.currency,
        "window": config.window.model_dump(mode="json"),
        "expected": {"products": [], "order_lines": [], "refunds": [], "inventories": []},
    }
    expected_input(config, expected)
    assert all(compare_groups(expected["expected"], expected["expected"]).values())
    expected["expected"]["refunds"] = [
        {
            "refund_id": "301",
            "order_id": "101",
            "created_at": "2026-10-26T00:00:00Z",
            "refund_amount": "1.25",
            "currency": config.currency,
            "lines": [{"line_id": "11", "refunded_quantity": 1, "quantity_reason": None}],
            "restocked": None,
            "quantity_reason": None,
        }
    ]
    expected_input(config, expected)
    assert project(
        {
            "source": {"secret": "excluded"},
            "schema_version": "dynamic",
            "observed_at": "dynamic",
            "source_version": "dynamic",
            "quantity": 3,
        }
    ) == {"quantity": 3}
    output = tmp_path / "report.json"
    write_output(output, {"complete": False}, redact=lambda s: s)
    assert output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        write_output(output, {"complete": True}, redact=lambda s: s)
    assert json.loads(output.read_text())["complete"] is False


@pytest.mark.parametrize(
    "damage", ["schema", "window", "currency", "groups", "float", "partial_row"]
)
def test_expected_invalid_never_passes_input(config: WooReadOnlyConfig, damage: str) -> None:
    expected: dict[str, Any] = {
        "schema_version": "woo-local-expectations-v1",
        "fixture_version": "local-v1",
        "business_now": "2026-10-26T00:00:00Z",
        "shop_id": config.shop_id,
        "timezone": config.timezone,
        "currency": config.currency,
        "window": config.window.model_dump(mode="json"),
        "expected": {"products": [], "order_lines": [], "refunds": [], "inventories": []},
    }
    if damage == "schema":
        expected["schema_version"] = "wrong"
    if damage == "currency":
        expected["currency"] = "USD"
    if damage == "window":
        expected["window"] = {"start": "2026-10-19T16:00:00Z", "end": "2026-10-25T16:00:00Z"}
    if damage == "groups":
        expected["expected"].pop("refunds")
    if damage in {"float", "partial_row"}:
        expected["expected"]["inventories"] = [{"available_stock": 1.2 if damage == "float" else 1}]
    with pytest.raises((ValueError, KeyError)):
        expected_input(config, expected)


@pytest.mark.parametrize("status,attempts", [(401, 1), (403, 1), (500, 2), (503, 2)])
def test_retry_bound_and_actual_http_status(
    config: WooReadOnlyConfig, status: int, attempts: int
) -> None:
    a = adapter_with(config.model_copy(update={"max_retries": 1}), lambda _: httpx.Response(status))
    try:
        page = a.list_products()
        assert page.error is not None and not page.complete
        assert sum(a.http.counts.values()) == attempts
        assert a.http.status_counts[status] == attempts
        assert page.error.provider_code is None  # actual HTTP status is recorded separately
    finally:
        a.close()


def test_long_retry_after_does_not_sleep_or_retry_early(config: WooReadOnlyConfig) -> None:
    a = adapter_with(
        config.model_copy(update={"max_retries": 1}),
        lambda _: httpx.Response(429, headers={"Retry-After": "3600"}),
    )
    try:
        first = a.list_products()
        second = a.list_products()
        assert first.error is not None and first.error.retry_after_seconds == 3600
        assert second.error is not None and second.error.code == ErrorCode.RATE_LIMITED
        assert sum(a.http.counts.values()) == 1
    finally:
        a.close()


def test_ca_must_be_private_plain_file(config: WooReadOnlyConfig, tmp_path: Path) -> None:
    ca = Path(config.ca_file)
    ca.chmod(0o644)
    with pytest.raises(ValueError, match="UNSAFE"):
        adapter_with(config, lambda _: pytest.fail("must fail before HTTP"))
    ca.chmod(0o600)
    alias = tmp_path / "ca-alias"
    alias.symlink_to(ca)
    with pytest.raises(OSError):
        adapter_with(
            config.model_copy(update={"ca_file": str(alias)}), lambda _: pytest.fail("No HTTP")
        )


def test_end_revalidation_detects_changes_between_resources(config: WooReadOnlyConfig) -> None:
    from commerceops.adapters.commerce.woocommerce_http import WooReadFailure

    calls = 0

    def serve(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response([product(name="Before" if calls <= 2 else "After")])

    adapter = adapter_with(config, serve)
    try:
        assert adapter.list_products().error is None
        with pytest.raises(WooReadFailure) as failure:
            adapter.http.revalidate()
        assert failure.value.quality == Quality.SOURCE_CHANGED and calls == 3
    finally:
        adapter.close()


@pytest.mark.parametrize("mode", ["dribble", "tail_block"])
def test_total_deadline_bounds_native_blocking_stream(
    config: WooReadOnlyConfig, monkeypatch: Patch, mode: str
) -> None:
    """仅故障注入：socketpair真实阻塞I/O；TLS握手Fake，不签真实Woo或TLS成功。"""
    import socket
    import threading
    import time

    import httpcore
    from commerceops.adapters.commerce.woocommerce_deadline import (
        WooDeadlineBackend,
        WooDeadlineStream,
        WooDeadlineTransport,
    )
    from httpcore._backends.sync import SyncStream

    reader, peer = socket.socketpair()
    stop = threading.Event()
    sent = []

    class NoHandshakeStream(SyncStream):
        def start_tls(
            self,
            ssl_context: ssl.SSLContext,
            server_hostname: str | None = None,
            timeout: float | None = None,
        ) -> httpcore.NetworkStream:
            return self

    def connect(
        backend: WooDeadlineBackend,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.NetworkStream:
        return WooDeadlineStream(NoHandshakeStream(reader), backend._remaining)

    monkeypatch.setattr(WooDeadlineBackend, "connect_tcp", connect)

    def server() -> None:
        try:
            peer.settimeout(2)
            request = b""
            while b"\r\n\r\n" not in request:
                part = peer.recv(4096)
                if not part:
                    return
                request += part
            length = 40 if mode == "dribble" else 3
            peer.sendall(
                (
                    "HTTP/1.1 200 OK\r\nContent-Length: "
                    + str(length)
                    + "\r\nX-WP-Total: 0\r\nX-WP-TotalPages: 0\r\n\r\n"
                ).encode()
            )
            if mode == "dribble":
                for value in b"[" + b" " * 38 + b"]":
                    if stop.wait(0.06):
                        return
                    peer.sendall(bytes([value]))
                    sent.append(value)
            else:
                peer.sendall(b"[")
                if stop.wait(0.7):
                    return
                peer.sendall(b" ")
                sent.append(1)
                if not stop.wait(3):
                    peer.sendall(b"]")
        except OSError:
            pass  # expected peer closure after the tested hard deadline
        finally:
            peer.close()

    worker = threading.Thread(target=server)
    worker.start()
    adapter = WooCommerce(config.model_copy(update={"max_elapsed_seconds": 1}))
    try:
        assert isinstance(adapter.http.client._transport, WooDeadlineTransport)
        started = time.monotonic()
        page = adapter.list_products()
        elapsed = time.monotonic() - started
        assert page.error is not None and page.error.code == ErrorCode.TIMEOUT
        assert not page.complete and page.items == ()
        assert 0.75 <= elapsed < 1.35
        assert len(sent) < 40 and (mode != "tail_block" or sent == [1])
        assert sum(adapter.http.counts.values()) == 1
    finally:
        adapter.close()
        stop.set()
        reader.close()
        worker.join(timeout=2)
        assert not worker.is_alive()


def test_total_deadline_checks_each_unaggregated_mock_chunk(config: WooReadOnlyConfig) -> None:
    """重现原40×60ms单字节反例，不将Fake读成功作为平台证据。"""
    import time
    from collections.abc import Iterator

    class SlowStream(httpx.SyncByteStream):
        def __init__(self) -> None:
            self.sent = 0
            self.closed = False

        def __iter__(self) -> Iterator[bytes]:
            for _ in range(40):
                time.sleep(0.06)
                self.sent += 1
                yield b" "

        def close(self) -> None:
            self.closed = True

    stream = SlowStream()
    adapter = adapter_with(
        config.model_copy(update={"max_elapsed_seconds": 1}),
        lambda _: httpx.Response(200, stream=stream),
    )
    try:
        started = time.monotonic()
        page = adapter.list_products()
        elapsed = time.monotonic() - started
        assert page.error is not None and page.error.code == ErrorCode.TIMEOUT
        assert not page.complete and elapsed < 1.35
        assert stream.sent < 40 and stream.closed
    finally:
        adapter.close()


@pytest.mark.parametrize("refund_failure", [False, True])
def test_empty_line_order_still_belongs_to_refund_cohort(
    config: WooReadOnlyConfig, monkeypatch: Patch, refund_failure: bool
) -> None:
    """完整窗口订单cohort不因没有商品行丢失；仅合成DTO反例，未访问Woo。"""
    from commerceops.adapters.commerce.woocommerce_http import WooReadFailure

    from scripts.woo_readonly_probe import collect

    adapter = adapter_with(config, lambda _: pytest.fail("No HTTP in semantic unit"))
    paths = []

    def scan(path: str, _: Any) -> tuple[dict[str, Any], ...]:
        paths.append(path)
        if path == "products":
            return ()
        if path == "orders":
            return ({**order(), "line_items": [], "refunds": [{"id": 301}]},)
        assert path == "orders/101/refunds"
        if refund_failure:
            raise WooReadFailure(ErrorCode.TIMEOUT)
        return (
            {
                "id": 301,
                "amount": "5.50",
                "date_created_gmt": "2026-10-26T01:00:00",
                "line_items": [],
            },
        )

    monkeypatch.setattr(adapter.http, "scan", scan)
    try:
        with pytest.raises(CommerceFailure):
            _ = adapter.observed_order_ids
        if refund_failure:
            with pytest.raises(CommerceFailure, match="TIMEOUT"):
                collect(adapter)
        else:
            actual, _ = collect(adapter)
            assert actual["order_lines"] == []
            assert len(actual["refunds"]) == 1
            assert actual["refunds"][0]["order_id"] == "101"
            assert actual["refunds"][0]["refund_amount"] == "5.5"
            assert actual["refunds"][0]["quantity_reason"] == "AMOUNT_ONLY_REFUND"
        assert adapter.observed_order_ids == ("101",)
        assert paths.count("orders/101/refunds") == 1
    finally:
        adapter.close()


def test_product_related_ids_only_may_change_between_reads(config: WooReadOnlyConfig) -> None:
    calls = 0

    def serve(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response([product(related_ids=[100 + calls])])

    adapter = adapter_with(config, serve)
    try:
        page = adapter.list_products()
        assert page.error is None and page.complete
        adapter.http.revalidate()
        assert calls == 3
        # The observed original resource remains intact; only its comparison digest projects.
        assert adapter._catalog["sku/woo-local/1/p"][1]["related_ids"] == [101]
    finally:
        adapter.close()


@pytest.mark.parametrize("stage", ["initial_pair", "final_revalidation"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("stock_quantity", 99),
        ("price", "11.25"),
        ("status", "draft"),
        ("id", 2),
        ("backorders", "yes"),
        ("name", "Changed consumed title"),
        ("meta_data", [{"id": 1, "key": "test", "value": "changed"}]),
    ],
)
def test_business_fields_still_change_observation(
    config: WooReadOnlyConfig, stage: str, field: str, value: Any
) -> None:
    from commerceops.adapters.commerce.woocommerce_http import WooReadFailure

    calls = 0

    def serve(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        row = product(price="10.50", meta_data=[], related_ids=[100 + calls])
        if calls >= (2 if stage == "initial_pair" else 3):
            row[field] = value
        return response([row])

    adapter = adapter_with(config, serve)
    try:
        page = adapter.list_products()
        if stage == "initial_pair":
            assert page.error is not None and Quality.SOURCE_CHANGED in page.warnings
            assert not page.complete
        else:
            assert page.error is None
            with pytest.raises(WooReadFailure) as failure:
                adapter.http.revalidate()
            assert failure.value.quality == Quality.SOURCE_CHANGED
    finally:
        adapter.close()


@pytest.mark.parametrize("path", ["orders", "products/1/variations", "orders/101/refunds"])
def test_related_ids_exception_is_not_applied_to_other_resources(
    config: WooReadOnlyConfig, path: str
) -> None:
    from commerceops.adapters.commerce.woocommerce_http import WooReadFailure

    calls = 0

    def serve(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response([product(related_ids=[calls])])

    adapter = adapter_with(config, serve)
    try:
        with pytest.raises(WooReadFailure) as failure:
            adapter.http.scan(path, {})
        assert failure.value.quality == Quality.SOURCE_CHANGED
    finally:
        adapter.close()
