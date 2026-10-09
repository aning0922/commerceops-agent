import json
import threading
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from commerceops.adapters.feishu.contracts import (
    ContractCode,
    ProbeContractError,
    ProbePolicy,
)
from commerceops.adapters.feishu.repository import (
    ProbeDatabaseFailure,
    ProbeRepository,
)
from commerceops.infrastructure.repository import TaskScope
from lark_oapi.event.callback.model.p2_card_action_trigger import (  # type: ignore[import-untyped]
    P2CardActionTrigger,
)

from scripts.feishu_probe_harness.behavior_observer import ObservedGateway, SafeTrace
from scripts.feishu_probe_harness.card_behaviors import (
    WitnessReceiver,
    expected_M3_candidate,
    hold_own_card_lock,
)

from .support import MEMBERS, plan

pytestmark = pytest.mark.offline


class Store:
    def __init__(self: Any) -> None:
        self.plan = replace(plan(), message_id="om_synthetic_sent")
        self.scope = TaskScope(uuid4(), uuid4())
        self.ids = {a: uuid4() for a in "ABC"}
        self.policy = ProbePolicy(
            "cli_synthetic",
            "tenant_synthetic",
            "ou_synthetic_bot",
            frozenset(MEMBERS.values()),
            frozenset({self.plan.chat_id}),
        )
        self.identity = dict(
            members=[dict(alias=a, principal_id=str(self.ids[a]), auth_version=1) for a in "ABC"]
        )
        p = self.plan
        self.card = dict(
            id=UUID(p.probe_id),
            organization_id=self.scope.organization_id,
            shop_id=self.scope.shop_id,
            binding={
                k: v
                for k, v in p.__dict__.items()
                if k not in {"nonce", "expires_at", "chat_id", "message_id"}
            },
            nonce_sha256=p.binding().nonce_sha256,
            expires_at=p.expires_at,
            chat_id=p.chat_id,
            message_id=p.message_id,
            send_status="sent",
            decision=None,
            decided_by=None,
            decided_value_sha256=None,
            decided_at=None,
        )
        self.card["binding"]["required_assumption_keys"] = list(p.required_assumption_keys)
        self.queries: list[Any] = []
        self.receipts: dict[Any, Any] = {}
        self.keys: dict[Any, Any] = {}
        self.connections: list[Any] = []
        self.roles: list[Any] = []
        self.enabled = True
        self.fail_witness = False
        self.fail_card_lock = False

    def connection(self: Any) -> Any:
        c = Connection(self)
        self.connections.append(c)
        return c

    def payload(
        self: Any, alias: Any = "C", action: Any = "approve_with_assumptions", event_id: Any = None
    ) -> Any:
        return dict(
            schema="2.0",
            header=dict(
                app_id=self.policy.app_id,
                tenant_key=self.policy.tenant_key,
                event_id=event_id or str(uuid4()),
                event_type="card.action.trigger",
            ),
            event=dict(
                operator=dict(tenant_key=self.policy.tenant_key, open_id=MEMBERS[alias]),
                context=dict(open_chat_id=self.plan.chat_id, open_message_id=self.plan.message_id),
                action=dict(tag="button", value=self.plan.callback_value(action)),
            ),
        )


class Connection:
    def __init__(self: Any, store: Any) -> None:
        self.store = store
        self.locked = False
        self.rolled_back = False
        self.committed = False

    def __enter__(self: Any) -> Any:
        return self

    def __exit__(self: Any, kind: Any, *args: Any) -> Any:
        self.rolled_back = kind is not None
        self.committed = kind is None
        self.locked = False

    def execute(self: Any, query: Any, params: Any = None) -> Any:
        s = self.store
        q = str(query)
        s.queries.append((self, q, params))
        row = None
        if q.startswith("SAVEPOINT") or q.startswith("RELEASE"):
            pass
        elif q.startswith("ROLLBACK TO"):
            self.locked = False
        elif "SELECT p.id,p.enabled" in q:
            if s.fail_witness:
                raise ValueError("SYNTHETIC_CANARY")
            self.locked = True
            row = dict(
                id=s.ids["C"],
                enabled=s.enabled,
                roles=s.roles,
                auth_version=1,
                external_subject=MEMBERS["C"],
                app_id=s.policy.app_id,
                tenant_key=s.policy.tenant_key,
            )
        elif "SELECT p.id FROM" in q:
            alias = next(a for a in "ABC" if MEMBERS[a] == params[4])
            if alias == "C":
                row = None
            else:
                row = dict(id=s.ids[alias])
        elif "FROM feishu_probe.cards" in q:
            if s.fail_card_lock and "FOR UPDATE" in q:
                raise ValueError("SYNTHETIC_DB_LOCK_TIMEOUT")
            row = s.card
        elif "clock_timestamp() AS checked_at" in q:
            row = dict(checked_at=datetime.now(UTC))
        elif "pg_advisory_xact_lock" in q:
            pass
        elif "SELECT r.*" in q:
            rid = s.keys.get(params[2])
            row = s.receipts.get(rid)
        elif "UPDATE feishu_probe.cards SET decision" in q:
            decision, actor, digest, _ = params
            s.card.update(
                decision=decision,
                decided_by=actor,
                decided_value_sha256=digest,
                decided_at=datetime.now(UTC),
            )
        elif "INSERT INTO feishu_probe.receipts" in q:
            keys = (
                "id",
                "organization_id",
                "shop_id",
                "app_id",
                "tenant_key",
                "kind",
                "message_id",
                "context_message_id",
                "probe_id",
                "actor_id",
                "payload_sha256",
                "sanitized_payload",
                "result",
            )
            row = dict(zip(keys, params, strict=True))
            row["sanitized_payload"] = row["sanitized_payload"].obj
            s.receipts[row["id"]] = row
            row = None
        elif "INSERT INTO feishu_probe.event_keys" in q:
            s.keys[params[2]] = params[3]
        else:
            raise AssertionError("UNEXPECTED_SQL")
        return SimpleNamespace(fetchone=lambda: row)


def witness(store: Any, sink: Any) -> Any:
    trace = SafeTrace()
    receiver = WitnessReceiver(
        store.connection,
        store.scope,
        store.policy,
        trace,
        MEMBERS,
        store.identity,
        UUID(store.plan.probe_id),
        sink,
    )
    return (receiver, trace)


def test_C_same_callback_same_original_transaction_valid_binding_roleless_identity_denied() -> None:
    s = Store()
    evidence: list[Any] = []
    receiver, trace = witness(s, evidence.append)
    gateway = ObservedGateway(receiver, trace, MEMBERS)
    response = gateway.on_card(P2CardActionTrigger(s.payload()))
    assert response.toast.type == "error"
    assert len(evidence) == 1 and evidence[0]["qualified"] is True
    assert len(s.connections) == 1 and s.connections[0].rolled_back
    assert evidence[0]["pure_full_binding_value_context_valid"] is True
    assert evidence[0]["original_DAL_identity_denied"] is True
    row = trace.buffer.get_nowait()
    assert row["seq"] == evidence[0]["callback_seq"] and row["result"] == "IDENTITY_DENIED"
    assert row["receiver_calls"] == 1 and row["commit_return_observed"] is False
    assert s.receipts == {} and s.keys == {} and (s.card["decision"] is None)
    assert all((c is s.connections[0] for c, _, _ in s.queries))
    assert not any((q.lstrip().startswith(("INSERT", "UPDATE", "DELETE")) for _, q, _ in s.queries))
    text = json.dumps(evidence)
    assert all(v not in text for v in (MEMBERS["C"], s.plan.nonce, s.plan.probe_id))


@pytest.mark.parametrize(
    "changed",
    [
        "roles",
        "disabled",
        "context",
        "nonce",
        "ack",
        "expiry",
        "witness_sql_failure",
        "not_own_card",
        "trace_absent",
    ],
)
def test_C_bad_pure_or_identity_witness_never_qualified_or_committed(changed: Any) -> None:
    s = Store()
    payload = s.payload()
    if changed == "roles":
        s.roles = ["approver"]
    elif changed == "disabled":
        s.enabled = False
    elif changed == "context":
        payload["event"]["context"]["open_message_id"] = "wrong"
    elif changed == "nonce":
        payload["event"]["action"]["value"]["nonce"] = "wrong" * 8
    elif changed == "ack":
        payload["event"]["action"]["value"]["acknowledged_assumption_keys"] = []
    elif changed == "expiry":
        s.card["expires_at"] = datetime.now(UTC) - timedelta(seconds=1)
    elif changed == "witness_sql_failure":
        s.fail_witness = True
    elif changed == "not_own_card":
        payload["event"]["action"]["value"]["probe_id"] = str(uuid4())
    evidence: list[Any] = []
    receiver, trace = witness(s, evidence.append)
    if changed == "trace_absent":
        with pytest.raises(ProbeContractError):
            receiver.receive_card(payload)
    else:
        response = ObservedGateway(receiver, trace, MEMBERS).on_card(P2CardActionTrigger(payload))
        assert response.toast.type == "error"
    assert evidence[0]["qualified"] is False and s.receipts == {} and (s.keys == {})


def test_C_sink_failure_preserves_original_error_and_marks_observer_incomplete() -> None:
    s = Store()

    def sink(*a: Any) -> Any:
        raise ValueError("SYNTHETIC_CANARY")

    receiver, trace = witness(s, sink)
    with pytest.raises(ProbeContractError) as captured:
        receiver.receive_card(s.payload())
    assert captured.value.code == ContractCode.IDENTITY_DENIED and trace.incomplete


def test_M3_original_three_actions_committed_exact_toasts_and_same_card_decision() -> None:
    s = Store()
    normal = ProbeRepository(s.connection, s.scope, s.policy)
    trace = SafeTrace()
    gateway = ObservedGateway(normal, trace, MEMBERS)
    toasts: list[Any] = []
    for alias, action in [
        ("A", "approve_with_assumptions"),
        ("A", "approve_with_assumptions"),
        ("B", "reject_assumptions"),
    ]:
        toasts.append(gateway.on_card(P2CardActionTrigger(s.payload(alias, action))).toast.type)
    records = [trace.buffer.get_nowait() for _ in range(3)]
    assert toasts == ["success", "info", "warning"]
    assert expected_M3_candidate(records) is True
    assert len(s.receipts) == 3 and len(s.keys) == 3
    assert s.card["decision"] == "approve_with_assumptions" and s.card["decided_by"] == s.ids["A"]
    assert all(c.committed for c in s.connections)


def test_callback_expiry_original_parser_denies_no_receipt() -> None:
    s = Store()
    s.card["expires_at"] = datetime.now(UTC) - timedelta(seconds=1)
    trace = SafeTrace()
    gateway = ObservedGateway(ProbeRepository(s.connection, s.scope, s.policy), trace, MEMBERS)
    assert gateway.on_card(P2CardActionTrigger(s.payload("A"))).toast.type == "error"
    assert trace.buffer.get_nowait()["result"] == "EXPIRED" and s.receipts == {} and (s.keys == {})


def test_own_card_lock_timeout_original_database_failure_not_success_ACK() -> None:

    s = Store()
    s.fail_card_lock = True
    trace = SafeTrace()
    gateway = ObservedGateway(ProbeRepository(s.connection, s.scope, s.policy), trace, MEMBERS)
    with pytest.raises(ProbeDatabaseFailure):
        gateway.on_card(P2CardActionTrigger(s.payload("A")))
    row = trace.buffer.get_nowait()
    assert row["result"] == "DB_FAILURE" and row["handler_returned"] is False
    assert row["commit_return_observed"] is False and s.receipts == {} and (s.keys == {})


def test_lock_holder_own_scope_bounded_no_content_or_roles_mutation() -> None:
    s = Store()
    ready = threading.Event()

    class Stop:
        def wait(self: Any, seconds: Any) -> Any:
            assert seconds == 60 and ready.is_set()

    hold_own_card_lock(s.connection, s.scope, UUID(s.plan.probe_id), Stop(), ready)
    assert ready.is_set() is False and len(s.queries) == 1
    assert s.queries[0][2] == (UUID(s.plan.probe_id), s.scope.organization_id, s.scope.shop_id)
    assert "FOR UPDATE" in s.queries[0][1] and s.connections[0].committed
    with pytest.raises(ValueError):
        hold_own_card_lock(s.connection, s.scope, UUID(s.plan.probe_id), Stop(), ready, 61)


def test_baseline_no_witness_wrapper_normal_delegate_once_and_malformed_original_error() -> None:
    s = Store()
    evidence: list[Any] = []
    receiver, trace = witness(s, evidence.append)
    result = receiver.receive_card(s.payload("A"))
    assert result.result == "probe_recorded:approve_with_assumptions" and len(s.connections) == 1
    assert evidence == []
    with pytest.raises(ProbeContractError):
        receiver.receive_card(dict(event=None))
