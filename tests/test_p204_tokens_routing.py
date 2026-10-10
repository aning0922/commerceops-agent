"""官方固定token资产、GIL释放的有界计数及受控模型路由；actual未跑。"""

import asyncio
from uuid import uuid4

import pytest
from commerceops.application.commerce.inventory_routing import (
    GuardedRouter,
    ModelRoute,
    ParameterCandidate,
    RoutingInput,
)
from commerceops.application.model_explanation.contracts import MODEL, Message
from commerceops.infrastructure.p204_token_counter import (
    API_MARGIN,
    ASSISTANT,
    BOS,
    END_THINK,
    SYSTEM_MARKER,
    USER_MARKER,
    VerifiedTextCounter,
)
from pytest import MonkeyPatch as Patcher

pytestmark = pytest.mark.offline


@pytest.fixture(scope="module")
def counter() -> VerifiedTextCounter:
    return VerifiedTextCounter()


@pytest.mark.parametrize("text", ["Hello", "中文", "🙂漢字", "a\\b\n{}", "123456789", "\r\n" * 100])
def test_official_two_message_chat_profile(counter: VerifiedTextCounter, text: str) -> None:
    messages = (Message("system", "Return JSON."), Message("user", text))
    expected = BOS + SYSTEM_MARKER + "Return JSON." + USER_MARKER + text + ASSISTANT + END_THINK
    assert counter.render(messages) == expected
    result = counter.count(messages, model=MODEL)
    assert result.input_tokens == len(expected.encode()) + API_MARGIN <= 5120
    assert result.evidence == "verified_tokenizer" and "margin1024" in result.tokenizer_version


@pytest.mark.parametrize(
    "text", ["<think>", "</think>", "<｜User｜>", "｜DSML｜", "<｜deepseek_image｜>", "x" * 5000]
)
def test_literal_and_size_fail_closed(counter: VerifiedTextCounter, text: str) -> None:
    with pytest.raises(ValueError):
        counter.count((Message("system", "s"), Message("user", text)), model=MODEL)


class ScriptedModel:
    def __init__(self, proposal: ModelRoute):
        self.proposal = proposal

    async def route(self, text: str) -> ModelRoute:
        return self.proposal


@pytest.mark.parametrize(
    "intent", ["inventory_replenishment", "task_status", "explain_report", "clarify", "unsupported"]
)
def test_five_model_routes_typed_mock(intent: str) -> None:
    proposed = ModelRoute.model_validate({"intent": intent, "evidence_mode": "offline_stub"})
    decision = asyncio.run(
        GuardedRouter(ScriptedModel(proposed)).route(
            RoutingInput(text="受控数据文本", context_task_id=uuid4())
        )
    )
    assert decision.intent == intent and decision.evidence_mode == "offline_stub"
    assert not decision.execution_available


@pytest.mark.parametrize(
    "variant", ["bool", "fabricated", "duplicate", "out_of_route", "authority"]
)
def test_parameters_ambiguity_and_injection(variant: str) -> None:
    candidate = ParameterCandidate(name="L", value=4, start=2, end=3, source="explicit_text")
    proposal = ModelRoute(
        intent="inventory_replenishment", candidates=(candidate,), evidence_mode="offline_stub"
    )
    if variant == "bool":
        proposal = proposal.model_copy(
            update={"candidates": (candidate.model_copy(update={"value": True}),)}
        )
    elif variant == "fabricated":
        proposal = proposal.model_copy(
            update={"candidates": (candidate.model_copy(update={"value": 5}),)}
        )
    elif variant == "duplicate":
        proposal = proposal.model_copy(update={"candidates": (candidate, candidate)})
    elif variant == "out_of_route":
        proposal = proposal.model_copy(update={"intent": "explain_report"})
    else:
        proposal = proposal.model_copy(update={"tenant": "other", "approved": True})
    decision = asyncio.run(GuardedRouter(ScriptedModel(proposal)).route(RoutingInput(text="L=4")))
    assert decision.intent == "clarify" and decision.parameters["L"] == 3


def test_explicit_candidate_and_actual_route_not_enabled() -> None:
    candidate = ParameterCandidate(name="L", value=4, start=2, end=3, source="explicit_text")
    proposal = ModelRoute(
        intent="inventory_replenishment", candidates=(candidate,), evidence_mode="offline_stub"
    )
    decision = asyncio.run(GuardedRouter(ScriptedModel(proposal)).route(RoutingInput(text="L=4")))
    assert decision.parameters["L"] == 4 and decision.parameter_sources["L"] == "explicit_text"
    actual = proposal.model_copy(update={"evidence_mode": "actual_provider"})
    assert (
        asyncio.run(GuardedRouter(ScriptedModel(actual)).route(RoutingInput(text="L=4"))).intent
        == "clarify"
    )


@pytest.mark.parametrize(
    "intent", ["inventory_replenishment", "task_status", "explain_report", "clarify", "unsupported"]
)
def test_real_routing_adapter_offline_http_contract(
    counter: VerifiedTextCounter, intent: str
) -> None:
    import hashlib
    import json

    import httpx
    from commerceops.adapters.commerce.deepseek_routing import DeepSeekRoutingPort
    from commerceops.adapters.model_explanation.deepseek import DeepSeekAdapter
    from commerceops.application.commerce.intent_task import ROUTE_SYSTEM, routing_body_hash
    from commerceops.application.model_explanation.contracts import BudgetRequest, Reservation
    from commerceops.infrastructure.model_budget_repository import PRICING
    from pydantic import SecretStr

    captured = []

    class Admission:
        async def reserve(self, r: BudgetRequest) -> Reservation:
            assert r.request_hash == routing_body_hash("查询这份库存")
            captured.append(r)
            return Reservation(r.request_id, r.request_hash)

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "deepseek-flash" and body["thinking"] == {"type": "disabled"}
        assert body["max_tokens"] == 800 and body["stream"] is False and "tools" not in body
        assert body["messages"][0]["content"] == ROUTE_SYSTEM
        assert json.loads(body["messages"][1]["content"]) == {"text": "查询这份库存"}
        assert hashlib.sha256(request.content).hexdigest() == routing_body_hash("查询这份库存")
        return httpx.Response(
            200,
            json={
                "model": "deepseek-flash",
                "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps({"intent": intent, "candidates": []}),
                        },
                    }
                ],
            },
        )

    port = DeepSeekRoutingPort(
        DeepSeekAdapter(
            api_key=SecretStr("offline-only"),
            token_counter=counter,
            admission=Admission(),
            pricing=PRICING,
            offline_transport=httpx.MockTransport(respond),
            prompt_version="inventory-routing-v1",
        ),
        "a" * 64,
    )
    proposal = asyncio.run(port.route("查询这份库存"))
    assert proposal.intent == intent and proposal.evidence_mode == "offline_stub"
    assert len(captured) == 1 and port.reply.content is None
    assert captured[0].prompt_version == port.reply.prompt_version == "inventory-routing-v1"


@pytest.mark.parametrize(
    "raw",
    [
        {"intent": "unsupported", "candidates": [], "approved": True},
        {
            "intent": "inventory_replenishment",
            "candidates": [
                {"name": "L", "value": True, "start": 2, "end": 3, "source": "explicit_text"}
            ],
        },
        {"intent": "refund", "candidates": []},
        {"intent": "clarify", "candidates": [], "tenant": "other"},
    ],
)
def test_routing_adapter_rejects_authority_schema(raw: dict[str, object]) -> None:
    import json

    from commerceops.adapters.commerce.deepseek_routing import DeepSeekRoutingPort
    from commerceops.application.model_explanation.contracts import Message, ModelReply

    class Reply:
        async def complete(self, messages: tuple[Message, ...], *, facts_hash: str) -> ModelReply:
            return ModelReply(content=json.dumps(raw), evidence_mode="offline_stub")

    port = DeepSeekRoutingPort(Reply(), "a" * 64)
    assert asyncio.run(port.route("L=4")).intent == "clarify"
    assert port.reply.content is None and port.reply.error_code == "UNSAFE_EXPLANATION"


def test_ambiguity_missing_candidates_and_port_failure() -> None:
    candidate = ParameterCandidate(name="L", value=4, start=2, end=3, source="explicit_text")
    proposal = ModelRoute(
        intent="inventory_replenishment", candidates=(candidate,), evidence_mode="offline_stub"
    )
    assert (
        asyncio.run(
            GuardedRouter(ScriptedModel(proposal)).route(RoutingInput(text="L=4 L=5"))
        ).intent
        == "clarify"
    )
    empty = proposal.model_copy(update={"candidates": ()})
    assert (
        asyncio.run(GuardedRouter(ScriptedModel(empty)).route(RoutingInput(text="L=4"))).intent
        == "clarify"
    )

    class Broken:
        async def route(self, text: str) -> ModelRoute:
            raise RuntimeError("untrusted provider failure")

    assert asyncio.run(GuardedRouter(Broken()).route(RoutingInput(text="库存"))).intent == "clarify"


def test_key_verify_only_stat_and_guarded_mock_key(tmp_path: object) -> None:
    from pathlib import Path

    from commerceops.infrastructure.model_probe_config import read_probe_key, verify_config

    path = Path(str(tmp_path)) / "offline_only"
    path.write_text("controlled-local-fake-value")
    path.chmod(0o600)
    result = verify_config(path)
    assert result["actual_provider_requests"] == 0 and result["key_read"] is False
    assert read_probe_key(path).get_secret_value() == "controlled-local-fake-value"
    link = path.with_name("symlink")
    link.symlink_to(path)
    with pytest.raises(ValueError):
        verify_config(link)
    path.chmod(0o644)
    with pytest.raises(ValueError):
        read_probe_key(path)


def test_every_official_added_literal_fails_closed(counter: VerifiedTextCounter) -> None:
    for literal in counter._literals:
        with pytest.raises(ValueError):
            counter.count((Message("system", "s"), Message("user", literal)), model=MODEL)


@pytest.mark.parametrize(
    "scalar",
    [
        "4.5",
        "4/5",
        "4-5",
        "4~5",
        "4到5",
        "4 5",
        "4，5",
        "4５",
        "4天到5天",
        "4\u00a05",
        "4\u00a0到5",
        "4",
        "4天",
        "4，",
    ],
)
def test_complete_integer_scalar_not_truncated(scalar: str) -> None:
    text = f"L={scalar} R=7 S=2"
    candidates = tuple(
        ParameterCandidate.model_validate(
            {"name": n, "value": v, "start": i, "end": i + 1, "source": "explicit_text"}
        )
        for n, v, i in [("L", 4, 2), ("R", 7, text.index("R=") + 2), ("S", 2, text.index("S=") + 2)]
    )
    proposed = ModelRoute(
        intent="inventory_replenishment", candidates=candidates, evidence_mode="offline_stub"
    )
    decision = asyncio.run(GuardedRouter(ScriptedModel(proposed)).route(RoutingInput(text=text)))
    assert decision.intent == (
        "inventory_replenishment" if scalar in ("4", "4天", "4，") else "clarify"
    )


@pytest.mark.parametrize(
    "scalar",
    [
        "4 天到5天",
        "4\u00a0天到5天",
        "4 天 / 5 天",
        "4 ½",
        "4 天 ½",
        "4 ¼",
        "4 ⅓",
        "4天半",
        "4天 半",
        "4 天 半",
        "4 半天",
        "4\u00a0天\u00a0½",
        "4",
        "4天",
        "4 天",
        "4\u00a0天",
    ],
)
def test_unit_whitespace_keeps_spans_and_blocks_business_dispatch(
    scalar: str, monkeypatch: Patcher
) -> None:
    from pathlib import Path
    from uuid import uuid4

    from commerceops.application.commerce.analysis_task import TrustedReadIdentity
    from commerceops.entrypoints import explanation_http
    from commerceops.entrypoints.api import create_app
    from commerceops.entrypoints.explanation_http import ExplanationEndpoints
    from commerceops.infrastructure.database import DatabaseSettings
    from fastapi.testclient import TestClient

    text = f"L={scalar} R=7 S=2"
    candidates = tuple(
        ParameterCandidate.model_validate(
            {"name": n, "value": v, "start": i, "end": i + 1, "source": "explicit_text"}
        )
        for n, v, i in [("L", 4, 2), ("R", 7, text.index("R=") + 2), ("S", 2, text.index("S=") + 2)]
    )
    proposal = ModelRoute(
        intent="inventory_replenishment", candidates=candidates, evidence_mode="offline_stub"
    )
    valid = scalar in ("4", "4天", "4 天", "4\u00a0天")
    decision = asyncio.run(GuardedRouter(ScriptedModel(proposal)).route(RoutingInput(text=text)))
    assert decision.intent == ("inventory_replenishment" if valid else "clarify")
    assert [(c.start, c.end, text[c.start : c.end]) for c in candidates] == [
        (2, 3, "4"),
        (text.index("R=") + 2, text.index("R=") + 3, "7"),
        (text.index("S=") + 2, text.index("S=") + 3, "2"),
    ]
    created = []

    class Db:
        def __enter__(self) -> "Db":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def execute(self, *args: object) -> "Db":
            return self

        def fetchone(self) -> dict[str, object]:
            return {"id": uuid4()}

    def create(*args: object) -> tuple[object, object]:
        created.append(args)
        return uuid4(), uuid4()

    # 明确离线scope/数据库替身，只验证已守卫意图的应用分派，不冒充真实PG/认证。
    monkeypatch.setattr(explanation_http, "connect", lambda _: Db())
    monkeypatch.setattr(explanation_http, "_authorize", lambda *_: None)
    monkeypatch.setattr(explanation_http, "create_analysis_task", create)
    actor = TrustedReadIdentity(uuid4(), uuid4(), uuid4(), uuid4(), 1)
    client = TestClient(
        create_app(
            explanation_service=ExplanationEndpoints(
                DatabaseSettings(
                    host="offline",
                    name="offline",
                    user="offline",
                    password_file=Path("not_read_offline"),
                ),
                GuardedRouter(ScriptedModel(proposal)),
            ),
            identity_resolver=lambda _: actor,
        )
    )
    response = client.post("/test/route", json={"text": text})
    assert response.status_code == 200 and len(created) == int(valid)
    assert response.json()["decision"]["intent"] == (
        "inventory_replenishment" if valid else "clarify"
    )
