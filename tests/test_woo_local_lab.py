"""Local lab guards: no external resources, secrets, or Docker creation in these tests."""

import ipaddress
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pytest import MonkeyPatch as MP

from scripts.woo_lab import lab

pytestmark = pytest.mark.offline


def test_mac_abbreviated_vpn_route_is_not_missed(monkeypatch: MP) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    raw = (
        b"Destination Gateway Flags Netif\ndefault 192.168.1.1 UGSc en0\n"
        b"8/5 198.18.0.1 UGSc utun4\n192.168.1/24 link U en0\n"
    )
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: raw)
    networks = lab.host_networks()
    assert ipaddress.IPv4Network("8.0.0.0/5") in networks
    assert ipaddress.IPv4Network("192.168.1.0/24") in networks
    monkeypatch.setattr(lab, "occupied_networks", lambda: networks)
    chosen = [ipaddress.IPv4Network(v) for v in lab.available_subnets()]
    assert len(chosen) == 2 and chosen[0] != chosen[1]
    assert all(not n.overlaps(old) for n in chosen for old in networks)


def private_config(tmp_path: Path, monkeypatch: MP) -> Path:
    monkeypatch.setattr(lab, "ROOT", tmp_path)
    directory = tmp_path / "runtime" / "woolab-123456789abc"
    directory.mkdir(parents=True, mode=0o700)
    config = {
        "project": directory.name,
        "checkout": str(tmp_path),
        "port": 18443,
        "url": "https://localhost:18443",
    }
    lab.write_private(directory / "lab.json", config)
    return directory


def test_private_files_and_origin_fail_closed(tmp_path: Path, monkeypatch: MP) -> None:
    directory = private_config(tmp_path, monkeypatch)
    assert lab.load(directory)["port"] == 18443
    file = directory / "lab.json"
    file.chmod(0o644)
    with pytest.raises(lab.LabFailure, match="FILE_MODE"):
        lab.load(directory)
    file.chmod(0o600)
    data = json.loads(file.read_text())
    data["url"] = "https://outside.example:18443"
    lab.write_private(file, data)
    with pytest.raises(lab.LabFailure, match="ORIGIN_BINDING"):
        lab.load(directory)


def test_symlink_secrets_are_never_consumed(tmp_path: Path, monkeypatch: MP) -> None:
    directory = private_config(tmp_path, monkeypatch)
    (directory / "consumer_key").symlink_to(tmp_path / "other-project-key")
    with pytest.raises(lab.LabFailure, match="FILE_MODE"):
        lab.load(directory)


def test_preexisting_project_is_not_stopped(tmp_path: Path, monkeypatch: MP) -> None:
    directory = private_config(tmp_path, monkeypatch)
    monkeypatch.setattr(lab, "owned_inventory", lambda *a: [{"owned_existing": True}])
    called = []
    monkeypatch.setattr(lab, "stop", lambda *a: called.append("stop"))
    with pytest.raises(lab.LabFailure, match="RESOURCES_ALREADY_EXIST"):
        lab.run(lab.load(directory), directory, 600, False)
    assert called == []


def test_cleanup_runs_even_when_failure_log_collection_fails(
    tmp_path: Path, monkeypatch: MP
) -> None:
    directory = private_config(tmp_path, monkeypatch)
    monkeypatch.setattr(lab, "owned_inventory", lambda *a: [])
    monkeypatch.setattr(lab, "check_network_allocation", lambda *a: None)
    called = []

    def fail(*a: object, **k: object) -> bytes:
        raise lab.LabFailure("SIMULATED_COMMAND_FAILURE")

    monkeypatch.setattr(lab, "compose", fail)
    monkeypatch.setattr(lab, "stop", lambda *a: called.append("stop"))
    with pytest.raises(lab.LabFailure):
        lab.run(lab.load(directory), directory, 600, False)
    assert called == ["stop"]


@pytest.mark.parametrize("status", [200, 401, 302])
def test_http_response_and_redirect_preserve_single_origin(monkeypatch: MP, status: int) -> None:
    import time

    import httpx

    seen = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            status,
            stream=httpx.ByteStream(b"[]"),
            headers={"Location": "https://outside.example"},
        )

    monkeypatch.setattr(lab, "WooDeadlineTransport", lambda *args: httpx.MockTransport(handle))
    client = deadline_client(time.monotonic() + 1)
    code, body, _ = client.request("/wp-json/wc/v3/products")
    assert code == status and body == [] and len(seen) == 1
    assert seen[0].url.host == "localhost"
    assert seen[0].headers["Authorization"] == client.authorization
    client.read_response("/wp-login.php")
    assert len(seen) == 2 and "Authorization" not in seen[1].headers


def test_expected_oracle_keeps_shared_pool_unknowns_and_refund_line_identity() -> None:
    from scripts.woo_lab.expectations import expected_document

    spec = json.loads(lab.FIXTURE.read_text())
    mapping: dict[str, Any] = {
        "products": {row["key"]: i + 1 for i, row in enumerate(spec["products"])},
        "orders": {
            row["key"]: {"id": 101 + i, "lines": [{"id": 201 + i}]}
            for i, row in enumerate(spec["orders"])
        },
        "refunds": {row["key"]: 301 + i for i, row in enumerate(spec["refunds"])},
    }
    groups = expected_document(spec, mapping)["expected"]
    assert {key: len(rows) for key, rows in groups.items()} == {
        "products": 9,
        "order_lines": 8,
        "refunds": 3,
        "inventories": 9,
    }
    shared = [r for r in groups["inventories"] if r["pool_allocation"] == "unresolved"]
    assert len(shared) == 2 and shared[0]["stock_pool_key"] == shared[1]["stock_pool_key"]
    assert all(
        row["inbound_units"] is None and row["inbound_quality"] == "unknown"
        for row in groups["inventories"]
    )
    assert all(row["restocked"] is None for row in groups["refunds"])
    partial = groups["refunds"][0]
    assert partial["lines"][0]["line_id"] == str(
        mapping["orders"]["partial_refund"]["lines"][0]["id"]
    )
    assert partial["lines"][0]["line_id"] != partial["refund_id"]
    money_only = groups["refunds"][2]
    assert money_only["lines"] == [] and money_only["quantity_reason"] == "AMOUNT_ONLY_REFUND"
    assert not {str(mapping["orders"][k]["id"]) for k in ("before_start", "at_end")} & {
        r["order_id"] for r in groups["order_lines"]
    }


def test_broad_capture_exception_never_ignores_private_or_direct_network() -> None:
    group = ("198.18.0.1", "utun4")
    assert (
        lab.classify_route(ipaddress.IPv4Network("8.0.0.0/5"), *group, "UGSc", group)
        == "broad_capture_overlap"
    )
    assert (
        lab.classify_route(ipaddress.IPv4Network("10.0.0.0/8"), *group, "UGSc", group)
        == "hard_exclusion"
    )
    assert (
        lab.classify_route(ipaddress.IPv4Network("10.247.0.0/24"), *group, "UGSc", group)
        == "hard_exclusion"
    )
    assert (
        lab.classify_route(ipaddress.IPv4Network("8.0.0.0/5"), *group, "USc", group)
        == "hard_exclusion"
    )
    assert (
        lab.classify_route(ipaddress.IPv4Network("8.0.0.0/5"), *group, "UGSc", None)
        == "hard_exclusion"
    )
    assert (
        lab.classify_route(ipaddress.IPv4Network("8.0.0.0/5"), "198.18.0.2", "utun4", "UGSc", group)
        == "hard_exclusion"
    )


def test_sensitive_seed_command_never_logs_credential_payload(
    tmp_path: Path, monkeypatch: MP
) -> None:
    payload = b"synthetic-sensitive-payload-marker"
    fake = subprocess.CompletedProcess(["fake"], 0, payload, b"LAB_TEST_DIAGNOSTIC")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake)
    assert lab.command(["fake"], tmp_path, "seed", 1, sensitive_output=True) == payload
    logs = list(tmp_path.glob("*.log"))
    assert len(logs) == 1 and payload not in logs[0].read_bytes()
    assert b"LAB_SENSITIVE_COMMAND_OUTPUT_SUPPRESSED" in logs[0].read_bytes()
    assert (logs[0].stat().st_mode & 0o777) == 0o600


@pytest.mark.parametrize("outcome", ["failure", "timeout"])
def test_sensitive_failure_does_not_log_or_chain_payload(
    tmp_path: Path, monkeypatch: MP, outcome: str
) -> None:
    import traceback

    payload = b"private-failure-output-marker"

    def failed(*args: Any, **kwargs: Any) -> Any:
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(["fake"], 1, output=payload, stderr=payload)
        return subprocess.CompletedProcess(["fake"], 1, payload, payload)

    monkeypatch.setattr(subprocess, "run", failed)
    with pytest.raises(lab.LabFailure) as caught:
        lab.command(["fake"], tmp_path, "seed", 1, sensitive_output=True)
    assert payload.decode() not in "".join(traceback.format_exception(caught.value))
    assert all(payload not in f.read_bytes() for f in tmp_path.iterdir())
    record = json.loads(next(tmp_path.glob("*.safe.json")).read_text())
    assert record["stdout_bytes"] == len(payload)
    assert record["stderr_bytes"] == len(payload)


def deadline_client(deadline: float) -> lab.Client:
    import ssl

    client = lab.Client.__new__(lab.Client)
    client.url = "https://localhost:18443"
    client.deadline = deadline
    client.requests = 0
    client.context = ssl.create_default_context()
    client.authorization = "Basic synthetic-test-only"
    return client


@pytest.mark.parametrize("mode", ["dribble", "tail_block", "headers"])
@pytest.mark.parametrize("status", [200, 401])
def test_native_deadline_aborts_slow_http_and_enters_owner_cleanup(
    tmp_path: Path, monkeypatch: MP, mode: str, status: int
) -> None:
    """Real socket blocking, Fake TLS handshake; no real Woo/TLS acceptance claim."""
    import socket
    import ssl
    import threading
    import time

    import httpcore
    from commerceops.adapters.commerce.woocommerce_deadline import (
        WooDeadlineBackend,
        WooDeadlineStream,
    )
    from httpcore._backends.sync import SyncStream

    reader, peer = socket.socketpair()
    stop = threading.Event()

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
            peer.settimeout(1)
            request = b""
            while b"\r\n\r\n" not in request:
                part = peer.recv(4096)
                if not part:
                    return
                request += part
            headers = f"HTTP/1.1 {status} Test\r\nContent-Length: 12\r\n\r\n".encode()
            if mode == "headers":
                for value in headers:
                    if stop.wait(0.04):
                        return
                    peer.sendall(bytes([value]))
            else:
                peer.sendall(headers)
                if mode == "tail_block":
                    peer.sendall(b"[" + b" " * 10)
                    if not stop.wait(1):
                        peer.sendall(b"]")
                else:
                    for value in b"[" + b" " * 10 + b"]":
                        if stop.wait(0.04):
                            return
                        peer.sendall(bytes([value]))
        except OSError:
            pass
        finally:
            peer.close()

    directory = private_config(tmp_path, monkeypatch)
    monkeypatch.setattr(lab, "owned_inventory", lambda *a: [])
    monkeypatch.setattr(lab, "check_network_allocation", lambda *a: None)
    monkeypatch.setattr(lab, "compose", lambda *a, **k: b"")
    monkeypatch.setattr(lab, "runtime_boundary", lambda *a: None)
    monkeypatch.setattr(lab, "initialize", lambda *a: {})
    cleaned = []
    monkeypatch.setattr(lab, "stop", lambda *a: cleaned.append(lab.bounded_timeout(1000)))

    def verify(*args: Any) -> Any:
        client = deadline_client(time.monotonic() + 0.18)
        return client.request("/wp-json/wc/v3/products")

    monkeypatch.setattr(lab, "verify", verify)
    worker = threading.Thread(target=server)
    worker.start()
    started = time.monotonic()
    try:
        with pytest.raises(lab.LabFailure, match="LAB_DEADLINE"):
            lab.run(lab.load(directory), directory, 300, False)
        elapsed = time.monotonic() - started
        assert 0.12 <= elapsed < 0.45
        assert len(cleaned) == 1 and 299 < cleaned[0] <= 300
        assert not (directory / "verification.safe.json").exists()
        assert not (directory / "reseed.safe.json").exists()
        assert lab._operation_deadline.get() is None
    finally:
        stop.set()
        reader.close()
        worker.join(timeout=1)
        assert not worker.is_alive()


def test_late_complete_response_rejected_before_json_success(monkeypatch: MP) -> None:
    import time

    client = deadline_client(time.monotonic() + 1)

    def late(*args: Any, **kwargs: Any) -> Any:
        client.deadline = time.monotonic() - 1
        return 200, b"[]", {}

    monkeypatch.setattr(client, "read_response", late)
    with pytest.raises(lab.LabFailure, match="LAB_DEADLINE"):
        client.request("/wp-json/wc/v3/products")


def test_owner_rejects_late_verifier_pass_and_bounds_cleanup(
    tmp_path: Path, monkeypatch: MP
) -> None:
    import time

    directory = private_config(tmp_path, monkeypatch)
    now = [100.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    monkeypatch.setattr(lab, "owned_inventory", lambda *a: [])
    monkeypatch.setattr(lab, "check_network_allocation", lambda *a: None)
    monkeypatch.setattr(lab, "compose", lambda *a, **k: b"")
    monkeypatch.setattr(lab, "runtime_boundary", lambda *a: None)
    monkeypatch.setattr(lab, "initialize", lambda *a: {})

    def late(*args: Any) -> dict[str, str]:
        now[0] = 311.0  # Work stops at 310; cleanup still has 89 of the total 300 seconds.
        return {"status": "PASS"}

    monkeypatch.setattr(lab, "verify", late)
    cleanup_timeouts = []

    def clean(*args: Any) -> None:
        def native(*args: Any, **kwargs: Any) -> Any:
            cleanup_timeouts.append(kwargs["timeout"])
            now[0] = 401.0  # Native exit arrives after the original cleanup deadline.
            return subprocess.CompletedProcess(["fake"], 0, b"", b"")

        monkeypatch.setattr(subprocess, "run", native)
        lab.command(["fake"], directory, "cleanup-native", 120)

    monkeypatch.setattr(lab, "stop", clean)
    with pytest.raises(lab.LabFailure, match="LAB_DEADLINE"):
        lab.run(lab.load(directory), directory, 300, False)
    assert cleanup_timeouts == [89.0]
    assert not (directory / "verification.safe.json").exists()
    assert not (directory / "cleanup.safe.json").exists()
    assert list(directory.glob("cleanup-failure-*.safe.json"))
    assert lab._operation_deadline.get() is None
