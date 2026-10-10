"""固定 DeepSeek Chat Completions，离线 transport 与真实发送证据严格分开。"""

import asyncio
import hashlib
import json
import re
from dataclasses import replace
from decimal import Decimal
from time import monotonic
from typing import cast
from uuid import uuid4

import httpx
from pydantic import SecretStr

from commerceops.application.model_explanation.contracts import (
    MAX_INPUT,
    MAX_OUTPUT,
    MODEL,
    PROMPT_VERSION,
    Admission,
    BudgetRequest,
    ErrorCode,
    Message,
    ModelReply,
    Pricing,
    Reservation,
    TokenCounter,
    Usage,
)
from commerceops.application.model_explanation.service import strict_json

BASE_URL = "https://api.deepseek.com"
DEADLINE_SECONDS = 20.0
MAX_RESPONSE_BYTES = 65_536


class SafeFailure(Exception):
    def __init__(self, code: ErrorCode) -> None:
        self.code = code
        super().__init__(code)


def remaining(deadline: float) -> float:
    """同步工作也消耗入口截止预算；不能仅依赖async timeout在yield时取消。"""
    seconds = deadline - monotonic()
    if seconds <= 0:
        raise TimeoutError
    return seconds


def safe_label(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:/-]{1,100}", value) is not None


def valid_pricing(pricing: Pricing | None) -> bool:
    return (
        pricing is not None
        and safe_label(pricing.version)
        and all(
            isinstance(rate, Decimal) and rate.is_finite() and rate > 0
            for rate in (pricing.input_per_million, pricing.output_per_million)
        )
    )


def usage_from(value: object) -> Usage | None:
    if not isinstance(value, dict):
        return None
    counts = [value.get(key) for key in ("prompt_tokens", "completion_tokens", "total_tokens")]
    if any(type(count) is not int or count < 0 for count in counts):
        return None
    prompt, completion, total = (cast(int, count) for count in counts)
    if prompt + completion != total or prompt == 0:
        return None
    return Usage(prompt, completion, total)


def parse_response(body: bytes, reply: ModelReply, pricing: Pricing | None) -> ModelReply:
    try:
        value = strict_json(body.decode("utf-8"))
    except (ValueError, UnicodeError, RecursionError):
        return replace(reply, error_code="INVALID_JSON", stop_required=True)
    if not isinstance(value, dict):
        return replace(reply, error_code="INVALID_SCHEMA", stop_required=True)
    # 未识别的模型字符串可能包含秘密：仅输出固定已知alias，不回显任意provider文本。
    returned_model = value.get("model")
    usage = usage_from(value.get("usage"))
    cost = pricing.cost(usage.input_tokens, usage.output_tokens) if pricing and usage else None
    reply = replace(reply, usage=usage, cost_estimate=cost)
    if returned_model != MODEL:
        return replace(reply, error_code="MODEL_MISMATCH", stop_required=True)
    reply = replace(reply, returned_model=MODEL)
    if usage is None:
        return replace(reply, error_code="UNKNOWN_USAGE", stop_required=True)
    if usage.input_tokens > MAX_INPUT:
        return replace(reply, error_code="INPUT_BUDGET", stop_required=True)
    if usage.output_tokens > MAX_OUTPUT:
        return replace(reply, error_code="OUTPUT_BUDGET", stop_required=True)
    if cost is None:
        return replace(reply, error_code="UNKNOWN_COST", stop_required=True)
    choices = value.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        return replace(reply, error_code="INVALID_SCHEMA")
    choice = choices[0]
    if choice.get("finish_reason") == "length":
        return replace(reply, error_code="TRUNCATED")
    if choice.get("finish_reason") != "stop":
        return replace(reply, error_code="INVALID_SCHEMA")
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        return replace(reply, error_code="INVALID_SCHEMA")
    # 明确拒绝工具与非空reasoning，不执行也不回显。
    if (
        message.get("tool_calls")
        or message.get("function_call")
        or message.get("reasoning_content")
    ):
        return replace(reply, error_code="UNSAFE_EXPLANATION")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        return replace(reply, error_code="INVALID_SCHEMA")
    return replace(reply, content=content)


class DeepSeekAdapter:
    def __init__(
        self,
        *,
        api_key: SecretStr,
        token_counter: TokenCounter | None = None,
        admission: Admission | None = None,
        pricing: Pricing | None = None,
        offline_transport: httpx.MockTransport | None = None,
        base_url: str = BASE_URL,
        model: str = MODEL,
    ) -> None:
        if base_url != BASE_URL or model != MODEL:
            raise ValueError("UNSAFE_PROVIDER_CONFIG")
        if offline_transport is not None and type(offline_transport) is not httpx.MockTransport:
            raise ValueError("UNSAFE_TRANSPORT")
        if not isinstance(api_key, SecretStr) or not api_key.get_secret_value():
            raise ValueError("INVALID_PROVIDER_CONFIG")
        self._credential = api_key
        self._counter = token_counter
        self._admission = admission
        self._pricing = pricing if valid_pricing(pricing) else None
        self._offline = offline_transport

    async def complete(self, messages: tuple[Message, ...], *, facts_hash: str) -> ModelReply:
        start = monotonic()
        deadline = start + DEADLINE_SECONDS
        reply = ModelReply(
            provider="deepseek",
            requested_model=MODEL,
            pricing_version=self._pricing.version if self._pricing else None,
        )
        if self._admission is None:
            return replace(reply, error_code="ADMISSION_REQUIRED")
        if self._counter is None:
            return replace(reply, error_code="TOKEN_COUNT_UNVERIFIED")
        try:
            # 仅纯计数在线程池运行，不传credential/admission/transport；取消后结果丢弃。
            # asyncio取消等待不会终止线程；调用方counter必须无副作用且有界。
            async with asyncio.timeout(remaining(deadline)):
                count = await asyncio.to_thread(self._counter.count, messages, model=MODEL)
            remaining(deadline)
            if (
                count.model != MODEL
                or not safe_label(count.tokenizer_version)
                or count.evidence not in {"verified_tokenizer", "offline_stub"}
                or (self._offline is None and count.evidence != "verified_tokenizer")
            ):
                return replace(reply, error_code="TOKEN_COUNT_UNVERIFIED")
            if type(count.input_tokens) is not int or not 1 <= count.input_tokens <= MAX_INPUT:
                return replace(reply, error_code="INPUT_BUDGET")
        except TimeoutError:
            return replace(
                reply,
                error_code="TIMEOUT",
                stop_required=True,
                latency_ms=max(0, int((monotonic() - start) * 1000)),
            )
        except Exception:
            return replace(reply, error_code="TOKEN_COUNT_UNVERIFIED")
        if self._offline is None and self._pricing is None:
            return replace(reply, error_code="UNKNOWN_COST", stop_required=True)
        body = json.dumps(
            {
                "model": MODEL,
                "messages": [{"role": item.role, "content": item.content} for item in messages],
                "thinking": {"type": "disabled"},
                "stream": False,
                "response_format": {"type": "json_object"},
                "max_tokens": MAX_OUTPUT,
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        request_id = str(uuid4())
        request_hash = hashlib.sha256(body).hexdigest()
        request = BudgetRequest(
            request_id,
            request_hash,
            facts_hash,
            "deepseek",
            MODEL,
            PROMPT_VERSION,
            count.input_tokens,
            MAX_OUTPUT,
            count.tokenizer_version,
            self._pricing.version if self._pricing else None,
            self._pricing.cost(count.input_tokens, MAX_OUTPUT) if self._pricing else None,
            "offline_stub" if self._offline is not None else "actual_provider",
        )
        reply = replace(reply, request_id=request_id)
        sent = False
        try:
            # 计数/请求构造已消耗同一入口deadline；admission与HTTP只用剩余时间。
            async with asyncio.timeout(remaining(deadline)):
                try:
                    reserved = await self._admission.reserve(request)
                except Exception:
                    raise SafeFailure("ADMISSION_FAILED") from None
                if reserved is None:
                    raise SafeFailure("BUDGET_DENIED")
                if not isinstance(reserved, Reservation) or (
                    reserved.request_id != request_id or reserved.request_hash != request_hash
                ):
                    raise SafeFailure("ADMISSION_FAILED")
                remaining(deadline)
                transport = self._offline or httpx.AsyncHTTPTransport(retries=0)
                async with httpx.AsyncClient(
                    transport=transport,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=httpx.Timeout(remaining(deadline)),
                ) as client:
                    remaining(deadline)
                    sent = True  # 保守：从进入send起即认为可能到达provider。
                    reply = replace(reply, evidence_mode=request.evidence_mode)
                    async with client.stream(
                        "POST",
                        BASE_URL + "/chat/completions",
                        content=body,
                        headers={
                            "Authorization": "Bearer " + self._credential.get_secret_value(),
                            "Content-Type": "application/json",
                            "Accept-Encoding": "identity",
                        },
                    ) as response:
                        if response.status_code != 200:
                            code: ErrorCode = {
                                401: "AUTH_FAILED",
                                402: "BALANCE_EXHAUSTED",
                                429: "RATE_LIMIT",
                            }.get(response.status_code, "HTTP_ERROR")  # type: ignore[assignment]
                            if 500 <= response.status_code <= 599:
                                code = "PROVIDER_UNAVAILABLE"
                            raise SafeFailure(code)
                        if response.headers.get("content-encoding", "identity") != "identity":
                            raise SafeFailure("INVALID_SCHEMA")
                        collected = bytearray()
                        async for chunk in response.aiter_bytes():
                            remaining(deadline)
                            if len(collected) + len(chunk) > MAX_RESPONSE_BYTES:
                                raise SafeFailure("RESPONSE_TOO_LARGE")
                            collected.extend(chunk)
                        remaining(deadline)
                        reply = parse_response(bytes(collected), reply, self._pricing)
                        remaining(deadline)
                        if reply.usage and reply.usage.input_tokens > count.input_tokens:
                            # 计数不再可信：调用方必须停止，保留实际usage/cost，不自动重试。
                            reply = replace(
                                reply, content=None, error_code="INPUT_BUDGET", stop_required=True
                            )
        except (TimeoutError, httpx.TimeoutException):
            reply = replace(reply, error_code="TIMEOUT", stop_required=True)
        except SafeFailure as exc:
            reply = replace(
                reply, error_code=exc.code, stop_required=sent or exc.code == "ADMISSION_FAILED"
            )
        except Exception:
            reply = replace(reply, error_code="TRANSPORT_ERROR", stop_required=sent)
        # CancelledError保持取消语义；A的预留须在取消/崩溃下仍占用，不能假称零费用。
        return replace(reply, latency_ms=max(0, int((monotonic() - start) * 1000)))
