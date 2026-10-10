"""固定prompt版本的实例元数据合同；仅MockTransport，不实现业务路由。"""

import asyncio
import json
import time
from typing import Any

import httpx
import pytest
from commerceops.adapters.model_explanation import DeepSeekAdapter, deepseek
from commerceops.application.model_explanation.contracts import (
    BudgetRequest,
    Message,
    ModelReply,
    Reservation,
    TokenCount,
)
from pydantic import SecretStr

from tests.test_model_explanation import Counter, LedgerStub, adapter, envelope

pytestmark = pytest.mark.offline
VERSIONS = ("inventory-explanation-v1", "inventory-routing-v1")
MESSAGES = (Message("system", "Return json only."), Message("user", "Synthetic offline input."))


def complete(provider: DeepSeekAdapter) -> ModelReply:
    return asyncio.run(provider.complete(MESSAGES, facts_hash="a" * 64))


@pytest.mark.parametrize("version", [None, *VERSIONS])
def test_prompt_version_binds_budget_reply_without_changing_wire(version: str | None) -> None:
    ledger = LedgerStub()
    bodies = []

    def handle(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=envelope('{"kind":"demo"}'))

    kwargs = {} if version is None else {"prompt_version": version}
    result = complete(adapter(handle, admission=ledger, **kwargs))
    expected = version or "inventory-explanation-v1"
    assert result.error_code is None and result.content == '{"kind":"demo"}'
    assert result.prompt_version == ledger.requests[0].prompt_version == expected
    assert result.request_id == ledger.requests[0].request_id
    assert result.evidence_mode == ledger.requests[0].evidence_mode == "offline_stub"
    assert bodies == [
        {
            "model": "deepseek-flash",
            "messages": [
                {"role": "system", "content": "Return json only."},
                {"role": "user", "content": "Synthetic offline input."},
            ],
            "thinking": {"type": "disabled"},
            "stream": False,
            "response_format": {"type": "json_object"},
            "max_tokens": 800,
        }
    ]
    assert ledger.requests[0].input_tokens == 1000 and ledger.requests[0].output_tokens == 800


@pytest.mark.parametrize(
    "version", ["", "arbitrary", "inventory-routing-v2", "inventory-routing-v1 ", None, True, []]
)
def test_unapproved_prompt_labels_fail_without_echo(version: Any) -> None:
    with pytest.raises(ValueError, match="^UNSUPPORTED_PROMPT_VERSION$"):
        DeepSeekAdapter(api_key=SecretStr("test"), prompt_version=version)


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize(
    "scenario,code,reserved",
    [
        ("no_admission", "ADMISSION_REQUIRED", False),
        ("no_counter", "TOKEN_COUNT_UNVERIFIED", False),
        ("counter_error", "TOKEN_COUNT_UNVERIFIED", False),
        ("counter_timeout", "TIMEOUT", False),
        ("input_budget", "INPUT_BUDGET", False),
        ("denied", "BUDGET_DENIED", True),
        ("admission_error", "ADMISSION_FAILED", True),
        ("admission_timeout", "TIMEOUT", True),
        ("rate_limit", "RATE_LIMIT", True),
        ("server_error", "PROVIDER_UNAVAILABLE", True),
        ("read_timeout", "TIMEOUT", True),
        ("invalid_json", "INVALID_JSON", True),
        ("unknown_usage", "UNKNOWN_USAGE", True),
        ("unknown_cost", "UNKNOWN_COST", True),
    ],
)
def test_prompt_version_survives_early_and_provider_errors(
    version: str,
    scenario: str,
    code: str,
    reserved: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FaultCounter(Counter):
        def count(self, messages: tuple[Message, ...], *, model: str) -> TokenCount:
            if scenario == "counter_timeout":
                time.sleep(0.06)
                return super().count(messages, model=model)
            raise ValueError("UNTRUSTED_DETAIL")

    class FaultAdmission(LedgerStub):
        async def reserve(self, request: BudgetRequest) -> Reservation | None:
            self.requests.append(request)
            if scenario == "admission_timeout":
                await asyncio.sleep(1)
            raise ValueError("UNTRUSTED_DETAIL")

    ledger = (
        FaultAdmission()
        if scenario.startswith("admission_")
        else LedgerStub(allow=scenario != "denied")
    )
    kwargs: dict[str, Any] = {"admission": ledger, "prompt_version": version}
    if scenario == "no_admission":
        kwargs["admission"] = None
    if scenario == "no_counter":
        kwargs["token_counter"] = None
    if scenario.startswith("counter_"):
        kwargs["token_counter"] = FaultCounter()
    if scenario == "input_budget":
        kwargs["token_counter"] = Counter(8001)
    if scenario == "unknown_cost":
        kwargs["pricing"] = None
    if scenario in {"counter_timeout", "admission_timeout"}:
        monkeypatch.setattr(deepseek, "DEADLINE_SECONDS", 0.02)

    def handle(request: httpx.Request) -> httpx.Response:
        if scenario == "rate_limit":
            return httpx.Response(429)
        if scenario == "server_error":
            return httpx.Response(500)
        if scenario == "read_timeout":
            raise httpx.ReadTimeout("UNTRUSTED_DETAIL", request=request)
        if scenario == "invalid_json":
            return httpx.Response(200, content=b"invalid")
        if scenario == "unknown_usage":
            return httpx.Response(200, json=envelope(usage=None))
        return httpx.Response(200, json=envelope())

    result = complete(adapter(handle, **kwargs))
    assert result.error_code == code and result.prompt_version == version
    assert bool(ledger.requests) == reserved
    assert all(request.prompt_version == version for request in ledger.requests)
    if not reserved:
        assert result.evidence_mode == "not_used"
    if scenario in {"counter_timeout", "admission_timeout", "unknown_usage", "unknown_cost"}:
        assert result.stop_required
    assert "UNTRUSTED_DETAIL" not in repr(result)


@pytest.mark.parametrize("version", VERSIONS)
def test_real_presend_unknown_cost_keeps_version_without_network(version: str) -> None:
    ledger = LedgerStub()
    result = complete(
        DeepSeekAdapter(
            api_key=SecretStr("test"),
            admission=ledger,
            token_counter=Counter(evidence="verified_tokenizer"),
            prompt_version=version,
        )
    )
    assert result.prompt_version == version and result.error_code == "UNKNOWN_COST"
    assert result.evidence_mode == "not_used" and result.stop_required
    assert not ledger.requests
