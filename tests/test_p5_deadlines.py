"""P5截止P2反例：可取消DB等待与native FIFO；不启动PG/SDK/HTTP。"""

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from commerceops.adapters.commerce.woocommerce_config import WooReadOnlyConfig
from commerceops.application.replenishment.contracts import WooCreateParameters
from commerceops.infrastructure.database import DatabaseSettings
from commerceops.infrastructure.woo_collection import BoundWooCollectorFactory

from tests.test_p5_sources import bound
from tests.test_woocommerce_readonly import config as config

pytestmark = pytest.mark.offline


@pytest.mark.parametrize("phase", ["connect", "execute", "fetch"])
@pytest.mark.parametrize("external_cancel", [False, True])
def test_async_source_db_deadline_closes_before_cancel_and_reaps_every_task(
    config: WooReadOnlyConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    external_cancel: bool,
) -> None:
    files, registered, _ = bound(config, tmp_path)
    request = WooCreateParameters(
        source_mode="woocommerce_test",
        source_config_version=registered.source_config_version,
        L=3,
        R=7,
        S=2,
    ).bind(registered)
    settings = DatabaseSettings(
        host="127.0.0.1",
        name="offline",
        user="offline",
        password_file=Path(config.consumer_secret_file),
    )
    events: list[str] = []
    entered = asyncio.Event()

    async def stalled() -> None:
        entered.set()
        try:
            await asyncio.sleep(1)
            events.append("unbounded_wait_completed")
        except asyncio.CancelledError:
            if phase != "connect":
                assert "closed" in events
            events.append("cancelled")
            raise

    class Cursor:
        async def fetchone(self) -> Any:
            assert phase == "fetch"
            await stalled()
            return None

    class Connection:
        async def execute(self, query: str, params: Any) -> Cursor:
            assert query.startswith(("SELECT b.id", "SELECT set_config"))
            if phase == "execute":
                await stalled()
            return Cursor()

        async def close(self) -> None:
            events.append("closed")

    async def connect(**kwargs: Any) -> Connection:
        assert kwargs["autocommit"] is True
        if phase == "connect":
            try:
                await stalled()
            finally:
                events.append("connect_reaped")
        return Connection()

    monkeypatch.setattr(
        "commerceops.infrastructure.woo_collection.AsyncConnection.connect", connect
    )
    monkeypatch.setattr(
        "commerceops.infrastructure.woo_collection.WooCommerce",
        lambda *a, **k: pytest.fail("no HTTP factory after DB deadline"),
    )

    async def run() -> None:
        original = asyncio.all_tasks()
        factory = BoundWooCollectorFactory(settings, files)
        started = time.monotonic()
        operation = asyncio.create_task(
            factory(request, absolute_deadline=started + (1 if external_cancel else 0.025))
        )
        if external_cancel:
            await entered.wait()
            operation.cancel()
            with pytest.raises(asyncio.CancelledError):
                await operation
        else:
            with pytest.raises(TimeoutError, match="COMMERCE_SOURCE_DEADLINE"):
                await operation
        assert time.monotonic() - started < 0.25
        assert (
            events[-1] == "connect_reaped"
            if phase == "connect"
            else events == ["closed", "cancelled"]
        )
        assert "unbounded_wait_completed" not in events
        assert asyncio.all_tasks() == original

    asyncio.run(run())


def test_native_fifo_is_rejected_without_blocking_open_or_leaking_fd(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    fifo = tmp_path / "owned-fifo"
    os.mkfifo(fifo, 0o600)
    code = """import json,os,sys,time
from commerceops.adapters.commerce.woocommerce_config import read_private_file
directory="/proc/self/fd" if os.path.isdir("/proc/self/fd") else "/dev/fd"
original=len(os.listdir(directory))
start=time.monotonic()
try:
    read_private_file(sys.argv[1], 4096)
except ValueError as error:
    assert str(error)=="CREDENTIAL_FILE_UNSAFE"
    assert len(os.listdir(directory))==original
    print(json.dumps({"rejected":True,"elapsed":time.monotonic()-start}))
else:
    raise AssertionError("FIFO accepted")
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(fifo)], capture_output=True, text=True, timeout=2
    )
    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout)
    assert evidence["rejected"] and evidence["elapsed"] < 0.25
    # Repeat the same nonblocking rejection in the parent process.
    from commerceops.adapters.commerce.woocommerce_config import read_private_file

    with pytest.raises(ValueError, match="CREDENTIAL_FILE_UNSAFE"):
        read_private_file(str(fifo), 4096)


def test_native_async_pg_handshake_stall_closes_socket_at_client_deadline(
    config: WooReadOnlyConfig,
    tmp_path: Path,
) -> None:
    """本机假PG握手端不回应认证；实际psycopg客户端与socket关闭。"""
    files, registered, _ = bound(config, tmp_path)
    request = WooCreateParameters(
        source_mode="woocommerce_test",
        source_config_version=registered.source_config_version,
        L=3,
        R=7,
        S=2,
    ).bind(registered)

    async def run() -> None:
        before = asyncio.all_tasks()
        connected = asyncio.Event()
        ended = asyncio.Event()

        async def stall(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            try:
                await reader.readexactly(8)
                connected.set()
                await reader.read()
            finally:
                writer.close()
                await writer.wait_closed()
                ended.set()

        server = await asyncio.start_server(stall, "127.0.0.1", 0)
        try:
            port = server.sockets[0].getsockname()[1]
            settings = DatabaseSettings(
                host="127.0.0.1",
                port=port,
                name="offline",
                user="offline",
                password_file=Path(config.consumer_secret_file),
            )
            start = time.monotonic()
            with pytest.raises(TimeoutError, match="COMMERCE_SOURCE_DEADLINE"):
                await BoundWooCollectorFactory(settings, files)(
                    request, absolute_deadline=start + 0.05
                )
            assert connected.is_set()
            await asyncio.wait_for(ended.wait(), 0.25)
            assert time.monotonic() - start < 0.35
        finally:
            server.close()
            await server.wait_closed()
        await asyncio.sleep(0)
        assert asyncio.all_tasks() == before

    asyncio.run(run())
