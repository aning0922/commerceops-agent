"""锁定HTTPX/httpcore的Woo专用总截止传输；每次阻塞I/O重新夹取剩余时间。"""

import ssl
from collections.abc import Callable, Iterable
from typing import Any

import httpcore
import httpx


class WooDeadlineStream(httpcore.NetworkStream):
    def __init__(self, stream: httpcore.NetworkStream, remaining: Callable[[], float]):
        self._stream = stream
        self._remaining = remaining

    def _timeout(self, timeout: float | None) -> float:
        remaining = self._remaining()
        return remaining if timeout is None else min(timeout, remaining)

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        # SyncStream.read把此值绑定到本次socket.recv/SSL read，而不是整个响应复用旧值。
        data = self._stream.read(max_bytes, timeout=self._timeout(timeout))
        self._remaining()
        return data

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self._stream.write(buffer, timeout=self._timeout(timeout))
        self._remaining()

    def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.NetworkStream:
        stream = self._stream.start_tls(
            ssl_context, server_hostname=server_hostname, timeout=self._timeout(timeout)
        )
        try:
            self._remaining()
        except BaseException:
            stream.close()
            raise
        return WooDeadlineStream(stream, self._remaining)

    def get_extra_info(self, info: str) -> Any:
        return self._stream.get_extra_info(info)

    def close(self) -> None:
        self._stream.close()


class WooDeadlineBackend(httpcore.SyncBackend):
    def __init__(self, remaining: Callable[[], float]):
        self._remaining = remaining

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.NetworkStream:
        remaining = self._remaining()
        # 首批配置仅允许这三个loopback origin；localhost固定走IPv4 loopback，避免DNS等待。
        if host not in {"localhost", "127.0.0.1", "::1"}:
            raise httpcore.ConnectError("NONLOCAL_WOO_ORIGIN")
        stream = super().connect_tcp(
            "127.0.0.1" if host == "localhost" else host,
            port,
            timeout=remaining if timeout is None else min(timeout, remaining),
            local_address=local_address,
            socket_options=socket_options,
        )
        try:
            self._remaining()
        except BaseException:
            stream.close()
            raise
        return WooDeadlineStream(stream, self._remaining)


class WooDeadlineTransport(httpx.HTTPTransport):
    def __init__(self, context: ssl.SSLContext, remaining: Callable[[], float]):
        # HTTPX 0.28.1没有公开network_backend参数。沿其原异常映射/ResponseStream，
        # 仅替换尚未使用的pool为已锁httpcore的deadline backend；不新增线程/后台请求。
        super().__init__(verify=context, trust_env=False, retries=0)
        self._pool.close()
        self._pool = httpcore.ConnectionPool(
            ssl_context=context,
            max_connections=1,
            max_keepalive_connections=1,
            http2=False,
            retries=0,
            network_backend=WooDeadlineBackend(remaining),
        )
