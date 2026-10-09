import json
import threading
from types import SimpleNamespace
from typing import Any

import pytest
from commerceops.adapters.feishu.contracts import (
    ContractCode,
    ProbeContractError,
    ProbePolicy,
)
from commerceops.adapters.feishu.repository import (
    ProbeConflict,
    ProbeDatabaseFailure,
    ProbeReceipt,
    ProbeRepository,
)
from commerceops.adapters.feishu.sdk import ProbeGateway
from commerceops.infrastructure.repository import TaskScope

from scripts.feishu_probe_harness import behavior_observer as observer

from .support import CANARY, FAKE_UUID, MEMBERS, Delegate, dto

pytestmark = pytest.mark.offline


@pytest.mark.parametrize(
    "kind,error",
    [(k, e) for k in ("message", "card") for e in (None, "contract", "conflict", "database")],
)
def test_original_public_handler_and_receiver_each_exactly_once_objects_and_ack_semantics(
    monkeypatch: Any, kind: Any, error: Any
) -> None:
    original_error = {
        "contract": ProbeContractError(ContractCode.IDENTITY_DENIED),
        "conflict": ProbeConflict(),
        "database": ProbeDatabaseFailure(),
    }.get(error)
    result = ProbeReceipt(
        FAKE_UUID,
        "probe_recorded:approve_with_assumptions" if kind == "card" else "message_received",
    )
    delegate = Delegate(result, original_error)
    trace = observer.SafeTrace(clock=iter([100, 200]).__next__)
    gateway = observer.ObservedGateway(delegate, trace, MEMBERS)
    function = getattr(ProbeGateway, "on_" + kind)
    called: list[Any] = []
    returned: list[Any] = []

    def spy(self: Any, data: Any) -> Any:
        called.append(data)
        response = function(self, data)
        returned.append(response)
        return response

    monkeypatch.setattr(ProbeGateway, "on_" + kind, spy)
    data = dto(kind)
    if error == "database":
        with pytest.raises(ProbeDatabaseFailure) as caught:
            getattr(gateway, "on_" + kind)(data)
        assert caught.value is original_error
    else:
        response = getattr(gateway, "on_" + kind)(data)
        assert response is returned[0]
        if kind == "card":
            assert response.toast.type == ("error" if error else "success")
        else:
            assert response is None
    assert called == [data] and len(delegate.calls) == 1
    record = trace.buffer.get_nowait()
    observer.validate_record(record)
    assert record["receiver_calls"] == 1 and record["handler_to_ready_ns"] == 100
    assert record["handler_returned"] is (error != "database")
    assert record["commit_return_observed"] is (error is None)
    assert record["result"] == {
        "contract": "IDENTITY_DENIED",
        "conflict": "EVENT_CONFLICT",
        "database": "DB_FAILURE",
    }.get(error, result.result)
    assert record["wire_observed"] is False and record["client_toast_observed"] is False
    assert record["C_evidence_inconclusive"] is True
    text = json.dumps(record)
    assert CANARY not in text and "ou_synthetic" not in text and (str(FAKE_UUID) not in text)


@pytest.mark.parametrize(
    "kind,error",
    [(k, e) for k in ("message", "card") for e in (None, "contract", "conflict", "database")],
)
def test_receiver_preserves_exact_original_result_and_exception(kind: Any, error: Any) -> None:
    original = {
        "contract": ProbeContractError(ContractCode.PLAN_MISMATCH),
        "conflict": ProbeConflict(),
        "database": ProbeDatabaseFailure(),
    }.get(error)
    delegate = Delegate(error=original)
    trace = observer.SafeTrace()
    wrapper = observer.ReceiverObserver(delegate, trace)
    payload = {"nonce": CANARY}
    if original:
        with pytest.raises(type(original)) as caught:
            getattr(wrapper, "receive_" + kind)(payload)
        assert caught.value is original
    else:
        assert getattr(wrapper, "receive_" + kind)(payload) is delegate.result
    assert delegate.calls == [payload]


@pytest.mark.parametrize(
    "failure", ["full", "sink_exception", "clock_exception", "bad_dto_diagnostic"]
)
def test_observer_failures_cannot_replace_success_or_retry_original_delegate(
    monkeypatch: Any, failure: Any
) -> None:
    trace = observer.SafeTrace(capacity=1)
    delegate = Delegate()
    gateway = observer.ObservedGateway(delegate, trace, MEMBERS)
    if failure == "full":
        gateway.on_message(dto())
    elif failure == "sink_exception":

        def fail(*a: Any) -> Any:
            raise ValueError(CANARY)

        monkeypatch.setattr(trace, "offer", fail)
    elif failure == "clock_exception":
        trace.clock = lambda: (_ for _ in ()).throw(ValueError(CANARY))
    else:
        monkeypatch.setattr(
            ProbeGateway, "on_message", lambda self, data: self.receiver.receive_message({})
        )
    previous = len(delegate.calls)
    response = gateway.on_message(SimpleNamespace() if failure == "bad_dto_diagnostic" else dto())
    assert response is (delegate.result if failure == "bad_dto_diagnostic" else None)
    assert len(delegate.calls) == previous + 1 and trace.incomplete


def test_trace_failure_does_not_swallow_database_failure(monkeypatch: Any) -> None:
    trace = observer.SafeTrace()
    error = ProbeDatabaseFailure()
    delegate = Delegate(error=error)
    monkeypatch.setattr(trace, "offer", lambda *a: (_ for _ in ()).throw(ValueError(CANARY)))
    with pytest.raises(ProbeDatabaseFailure) as caught:
        observer.ObservedGateway(delegate, trace, MEMBERS).on_card(dto("card"))
    assert caught.value is error and len(delegate.calls) == 1 and trace.incomplete


def test_global_trace_cap_remains_bounded_even_when_writer_drains() -> None:
    trace = observer.SafeTrace()
    delegate = Delegate()
    gateway = observer.ObservedGateway(delegate, trace, MEMBERS)
    for _ in range(64):
        gateway.on_message(dto())
        trace.buffer.get_nowait()
    gateway.on_message(dto())
    assert (
        trace.buffer.empty()
        and trace.offered == 64
        and trace.incomplete
        and (len(delegate.calls) == 65)
    )


@pytest.mark.parametrize("iteration", range(10))
def test_two_callback_threads_atomically_reserve_only_one_64th_record(iteration: Any) -> None:
    trace = observer.SafeTrace()
    delegate = Delegate()
    gateway = observer.ObservedGateway(delegate, trace, MEMBERS)
    recorded: list[Any] = []
    for _ in range(63):
        gateway.on_message(dto())
        recorded.append(trace.buffer.get_nowait())
    before = len(delegate.calls)
    entering = threading.Barrier(3)
    in_delegate = threading.Barrier(2)
    original = delegate.receive_message

    def simultaneous(payload: Any) -> Any:
        in_delegate.wait(timeout=3)
        return original(payload)

    delegate.receive_message = simultaneous  # type: ignore[method-assign]  # Synthetic concurrency barrier.
    outcomes, errors = ([], [])

    def callback() -> Any:
        try:
            entering.wait(timeout=3)
            outcomes.append(gateway.on_message(dto()))
        except BaseException as error:
            errors.append(type(error).__name__)

    threads = [threading.Thread(target=callback) for _ in range(2)]
    for thread in threads:
        thread.start()
    entering.wait(timeout=3)
    for thread in threads:
        thread.join(timeout=5)
    assert not any(thread.is_alive() for thread in threads) and errors == []
    assert outcomes == [None, None] and len(delegate.calls) - before == 2
    assert trace.incomplete and trace.offered == 64 and (trace.next_seq == 65)
    last = trace.buffer.get_nowait()
    assert trace.buffer.empty() and last["seq"] == 64
    recorded.append(last)
    assert len(recorded) == len({record["seq"] for record in recorded}) == 64


def test_same_reserved_record_cannot_be_offered_twice_after_writer_drains() -> None:
    trace = observer.SafeTrace()
    observer.ObservedGateway(Delegate(), trace, MEMBERS).on_message(dto())
    record = trace.buffer.get_nowait()
    trace.offer(record)
    assert trace.buffer.empty() and trace.incomplete


def test_actual_repository_commit_before_observed_return_without_real_database(
    monkeypatch: Any,
) -> None:

    class Connection:
        committed = False

        def __enter__(self: Any) -> Any:
            return self

        def __exit__(self: Any, *a: Any) -> Any:
            self.committed = True

        def execute(self: Any, statement: Any, parameters: Any = None) -> Any:
            return SimpleNamespace(
                fetchone=lambda: {"id": str(FAKE_UUID)} if "SELECT p.id" in statement else None
            )

    connection = Connection()
    policy = ProbePolicy(
        "cli_synthetic",
        "tenant_synthetic",
        "ou_bot",
        frozenset(MEMBERS[a] for a in "AB"),
        frozenset({"oc_synthetic"}),
    )
    repository = ProbeRepository(lambda: connection, TaskScope(FAKE_UUID, FAKE_UUID), policy)
    original = ProbeRepository.receive_message
    calls: list[Any] = []

    def spy(self: Any, payload: Any) -> Any:
        calls.append(payload)
        return original(self, payload)

    monkeypatch.setattr(ProbeRepository, "receive_message", spy)
    trace = observer.SafeTrace()
    gateway = observer.ObservedGateway(repository, trace, MEMBERS)
    assert gateway.on_message(dto()) is None
    assert len(calls) == 1 and connection.committed
    record = trace.buffer.get_nowait()
    assert record["result"] == "message_received" and record["commit_return_observed"]


def test_status_cannot_claim_C_role_qualification_even_after_identity_denied() -> None:
    trace = observer.SafeTrace()
    delegate = Delegate(error=ProbeContractError(ContractCode.IDENTITY_DENIED))
    observer.ObservedGateway(delegate, trace, MEMBERS).on_card(dto("card", "C"))
    record = trace.buffer.get_nowait()
    assert (
        record["actor"] == "C"
        and record["result"] == "IDENTITY_DENIED"
        and record["C_evidence_inconclusive"]
    )


def test_trace_validator_rejects_sensitive_extra_fields() -> None:
    trace = observer.SafeTrace()
    observer.ObservedGateway(Delegate(), trace, MEMBERS).on_message(dto())
    value = trace.buffer.get_nowait()
    value["nonce"] = CANARY
    with pytest.raises(ValueError):
        observer.validate_record(value)
