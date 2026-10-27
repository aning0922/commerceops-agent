"""Woo 专用有界 GET；不跟随链接/重定向，不记录响应或认证信息。"""

import base64
import hashlib
import json
import math
import re
import ssl
import time
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit

import httpx

from commerceops.adapters.commerce.woocommerce_config import (
    WooFilePins,
    WooReadOnlyConfig,
    credential_value,
    read_credential,
    read_private_file,
)
from commerceops.adapters.commerce.woocommerce_deadline import WooDeadlineTransport
from commerceops.application.commerce.contracts import ErrorCode, Quality
from commerceops.domain.commerce_values import canonical_bytes


class WooReadFailure(ValueError):
    def __init__(self, code: ErrorCode, quality: Quality = Quality.PARTIAL_FAILURE):
        self.code, self.quality = code, quality
        super().__init__(code.value)


def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for key, value in pairs:
        if key in row:
            raise ValueError("DUPLICATE_JSON_KEY")
        row[key] = value
    return row


def invalid_constant(_: str) -> None:
    raise ValueError("INVALID_JSON_CONSTANT")


def platform_id(value: object, *, zero: bool = False) -> str:
    if type(value) is not int or value < (0 if zero else 1):
        raise ValueError("INVALID_PLATFORM_ID")
    return str(value)


class WooHTTP:
    def __init__(
        self,
        config: WooReadOnlyConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        pins: WooFilePins | None = None,
        absolute_deadline: float | None = None,
    ):
        self.config = config
        self.started = time.monotonic()
        self.deadline = min(
            self.started + config.max_elapsed_seconds,
            absolute_deadline if absolute_deadline is not None else float("inf"),
        )
        self.counts: Counter[str] = Counter()
        self.response_bytes = 0
        self.status_counts: Counter[int] = Counter()
        self.retry_after_seconds: int | None = None
        self._not_before = 0.0
        self._observations: dict[str, tuple[str, dict[str, str | int], str]] = {}
        # Explicit CA is still required with injected Fake HTTP; injection is tests-only.
        if pins is None:
            ca = read_private_file(config.ca_file, 131072)
            key = read_credential(config.consumer_key_file, "ck")
            secret = read_credential(config.consumer_secret_file, "cs")
        else:
            ca = pins.read(config.ca_file, 131072, pins.ca)
            key = credential_value(
                pins.read(config.consumer_key_file, 128, pins.consumer_key),
                "ck",
            )
            secret = credential_value(
                pins.read(config.consumer_secret_file, 128, pins.consumer_secret),
                "cs",
            )
        context = ssl.create_default_context(cadata=ca.decode("ascii"))
        self._private_literals = (
            key,
            secret,
            base64.b64encode((key + ":" + secret).encode()).decode(),
        )
        self.client = httpx.Client(
            base_url=config.base_url.rstrip("/") + "/wp-json/wc/v3/",
            auth=httpx.BasicAuth(key, secret),
            headers={"Accept-Encoding": "identity"},
            verify=context,
            trust_env=False,
            follow_redirects=False,
            timeout=config.timeout_seconds,
            transport=transport
            if transport is not None
            else WooDeadlineTransport(context, self.remaining),
        )

    def redact(self, text: str) -> str:
        for value in self._private_literals:
            text = text.replace(value, "[REDACTED]")
        return text

    def close(self) -> None:
        self.client.close()

    def remaining(self) -> float:
        left = min(self.deadline, self.started + self.config.max_elapsed_seconds) - time.monotonic()
        if left <= 0:
            raise WooReadFailure(ErrorCode.TIMEOUT)
        return left

    def _request(self, path: str, params: dict[str, str | int]) -> tuple[bytes, httpx.Headers]:
        if (
            re.fullmatch(
                r"(?:products(?:/[1-9][0-9]*/variations)?|orders(?:/[1-9][0-9]*/refunds)?)", path
            )
            is None
        ):
            raise WooReadFailure(ErrorCode.INVALID_DATA)
        for attempt in range(self.config.max_retries + 1):
            self.remaining()
            if time.monotonic() < self._not_before:
                raise WooReadFailure(ErrorCode.RATE_LIMITED)
            if sum(self.counts.values()) >= self.config.max_requests:
                raise WooReadFailure(ErrorCode.INVALID_DATA, Quality.CAPACITY_LIMIT)
            self.counts[path] += 1
            try:
                with self.client.stream(
                    "GET",
                    path,
                    params=params,
                    timeout=min(self.config.timeout_seconds, self.remaining()),
                ) as response:
                    code = response.status_code
                    self.status_counts[code] += 1
                    if code == 200:
                        if (
                            response.headers.get("Content-Encoding", "identity").lower()
                            != "identity"
                        ):
                            raise WooReadFailure(ErrorCode.INVALID_DATA)
                        for link in response.links.values():
                            destination = urlsplit(urljoin(str(response.url), link.get("url", "")))
                            origin = urlsplit(self.config.base_url)
                            discovery = (
                                link.get("rel") == "https://api.w.org/"
                                and destination.path == "/wp-json/"
                                and not destination.query
                                and not destination.fragment
                            )
                            if (
                                (destination.scheme, destination.hostname, destination.port)
                                != (origin.scheme, origin.hostname, origin.port)
                                or destination.username is not None
                                or destination.password is not None
                                or (destination.path != "/wp-json/wc/v3/" + path and not discovery)
                                or {k.lower() for k in parse_qs(destination.query)}
                                & {"consumer_key", "consumer_secret", "authorization"}
                            ):
                                raise WooReadFailure(ErrorCode.REDIRECT_REJECTED)
                        data = bytearray()
                        for chunk in response.iter_raw():
                            self.response_bytes += len(chunk)
                            self.remaining()
                            if len(data) + len(chunk) > self.config.max_response_bytes:
                                raise WooReadFailure(ErrorCode.INVALID_DATA, Quality.CAPACITY_LIMIT)
                            data.extend(chunk)
                        self.remaining()
                        return bytes(data), response.headers
                    category = (
                        ErrorCode.AUTH_FAILED
                        if code == 401
                        else ErrorCode.PERMISSION_DENIED
                        if code == 403
                        else ErrorCode.REDIRECT_REJECTED
                        if 300 <= code < 400
                        else ErrorCode.RESOURCE_NOT_FOUND
                        if code == 404
                        else ErrorCode.RATE_LIMITED
                        if code == 429
                        else ErrorCode.PROVIDER_UNAVAILABLE
                        if 500 <= code < 600
                        else ErrorCode.INVALID_DATA
                    )
                    delay = 0
                    if category == ErrorCode.RATE_LIMITED:
                        header = response.headers.get("Retry-After")
                        try:
                            if header is None:
                                delay = 0
                            elif re.fullmatch(r"[0-9]{1,10}", header):
                                delay = int(header)
                            else:
                                instant = parsedate_to_datetime(header)
                                if instant.utcoffset() is None:
                                    raise ValueError("INVALID_RETRY_DATE")
                                delay = max(
                                    0, math.ceil((instant - datetime.now(UTC)).total_seconds())
                                )
                        except (ValueError, TypeError, OverflowError):
                            delay = self.config.max_elapsed_seconds + 1
                        self.retry_after_seconds = delay
                        self._not_before = time.monotonic() + delay
                        if delay > 2:
                            raise WooReadFailure(category)
                    if (
                        category in {ErrorCode.RATE_LIMITED, ErrorCode.PROVIDER_UNAVAILABLE}
                        and attempt < self.config.max_retries
                        and delay < self.remaining()
                    ):
                        if delay:
                            time.sleep(delay)
                        continue
                    raise WooReadFailure(category)
            except httpx.TimeoutException:
                if attempt < self.config.max_retries:
                    continue
                raise WooReadFailure(ErrorCode.TIMEOUT) from None
            except httpx.TransportError as exc:
                cause: BaseException | None = exc
                tls = False
                for _ in range(10):
                    if cause is None:
                        break
                    tls = tls or isinstance(cause, ssl.SSLError)
                    cause = cause.__cause__ or cause.__context__
                raise WooReadFailure(
                    ErrorCode.TLS_FAILURE if tls else ErrorCode.CONNECTION_FAILED
                ) from None
        raise WooReadFailure(ErrorCode.PROVIDER_UNAVAILABLE)

    @staticmethod
    def _observation_digest(path: str, rows: tuple[dict[str, Any], ...]) -> str:
        # Woo11.2.1的产品推荐列表会随机变化；它不参与任何commerce-v1字段。
        # 只排除products资源这一顶层字段，保留其他全部原始字段/metadata的变化检测。
        compared = (
            tuple(
                {key: value for key, value in row.items() if key != "related_ids"} for row in rows
            )
            if path == "products"
            else rows
        )
        return hashlib.sha256(canonical_bytes(compared)).hexdigest()

    def scan(self, path: str, query: dict[str, str | int]) -> tuple[dict[str, Any], ...]:
        """两次有界完整分页比较，检测可观察变化；并非平台原子快照。"""
        first = self._scan_once(path, query)
        second = self._scan_once(path, query)
        if self._observation_digest(path, first) != self._observation_digest(path, second):
            raise WooReadFailure(ErrorCode.INVALID_DATA, Quality.SOURCE_CHANGED)
        digest = self._observation_digest(path, first)
        self._observations[hashlib.sha256(canonical_bytes([path, query])).hexdigest()] = (
            path,
            dict(query),
            digest,
        )
        return first

    def revalidate(self) -> None:
        """结束前重读同一固定查询，检测跨端点读取期间的可观察变化。"""
        for path, query, digest in tuple(self._observations.values()):
            current = self._scan_once(path, query)
            if self._observation_digest(path, current) != digest:
                raise WooReadFailure(ErrorCode.INVALID_DATA, Quality.SOURCE_CHANGED)

    def _scan_once(self, path: str, query: dict[str, str | int]) -> tuple[dict[str, Any], ...]:
        rows: list[dict[str, Any]] = []
        expected: tuple[int, int] | None = None
        seen: set[str] = set()
        last_id = 0
        for page in range(1, self.config.max_pages + 1):
            data, headers = self._request(
                path,
                {
                    **query,
                    "page": page,
                    "per_page": self.config.per_page,
                    "order": "asc",
                    "orderby": "id",
                    "context": "view",
                },
            )
            try:
                totals = []
                for name in ("X-WP-Total", "X-WP-TotalPages"):
                    raw = headers[name]
                    if re.fullmatch(r"0|[1-9][0-9]{0,9}", raw) is None:
                        raise ValueError("INVALID_PAGINATION_HEADER")
                    totals.append(int(raw))
                total, pages = totals
                if pages != (total + self.config.per_page - 1) // self.config.per_page:
                    raise ValueError("PAGE_TOTAL_MISMATCH")
                if pages > self.config.max_pages:
                    raise WooReadFailure(ErrorCode.INVALID_DATA, Quality.CAPACITY_LIMIT)
                if expected is not None and expected != (total, pages):
                    raise WooReadFailure(ErrorCode.INVALID_DATA, Quality.SOURCE_CHANGED)
                expected = total, pages
                body = json.loads(
                    data,
                    parse_float=Decimal,
                    parse_constant=invalid_constant,
                    object_pairs_hook=object_pairs,
                )
                required = min(
                    self.config.per_page, max(total - (page - 1) * self.config.per_page, 0)
                )
                if type(body) is not list or len(body) != required:
                    raise WooReadFailure(ErrorCode.INVALID_DATA, Quality.MISSING_PAGE)
                for row in body:
                    if type(row) is not dict:
                        raise ValueError("INVALID_RESOURCE")
                    identity = platform_id(row["id"])
                    if identity in seen:
                        raise WooReadFailure(ErrorCode.INVALID_DATA, Quality.DUPLICATE_ID)
                    if int(identity) <= last_id:
                        raise WooReadFailure(ErrorCode.INVALID_DATA, Quality.MISSING_PAGE)
                    seen.add(identity)
                    last_id = int(identity)
                    rows.append(row)
                if page >= pages:
                    if len(rows) != total:
                        raise WooReadFailure(ErrorCode.INVALID_DATA, Quality.MISSING_PAGE)
                    return tuple(rows)
            except (ValueError, KeyError, TypeError, UnicodeError, RecursionError) as exc:
                if isinstance(exc, WooReadFailure):
                    raise
                raise WooReadFailure(ErrorCode.INVALID_DATA) from None
        raise WooReadFailure(ErrorCode.INVALID_DATA, Quality.CAPACITY_LIMIT)
