"""W1 公开 handler/Receiver 观察；不改变 DAL、返回对象、异常或 ACK 语义。"""

import queue
import threading
import time
from typing import Any

from commerceops.adapters.feishu.contracts import ContractCode, ProbeContractError
from commerceops.adapters.feishu.repository import ProbeConflict, ProbeDatabaseFailure, ProbeReceipt
from commerceops.adapters.feishu.sdk import ProbeGateway

RESULTS = {"message_received", "decision_conflict"} | {
    prefix + action
    for prefix in ("probe_recorded:", "duplicate_decision:")
    for action in ("approve_with_assumptions", "reject_assumptions")
}
RESULTS |= {"duplicate:" + value for value in tuple(RESULTS)}
RESULTS |= {code.value for code in ContractCode} | {
    "EVENT_CONFLICT",
    "DB_FAILURE",
    "UNOBSERVED",
    "UNKNOWN_RECEIVER_RESULT",
    "UNKNOWN_RECEIVER_EXCEPTION",
}
FIELDS = {
    "seq",
    "kind",
    "actor",
    "chat_kind",
    "receiver_calls",
    "result",
    "commit_return_observed",
    "handler_returned",
    "toast_type",
    "entry_ns",
    "response_object_ready_ns",
    "handler_to_ready_ns",
    "observer_evidence_incomplete",
    "wire_observed",
    "client_toast_observed",
    "C_evidence_inconclusive",
}


class SafeTrace:
    def __init__(self: Any, capacity: Any = 64, *, clock: Any = time.monotonic_ns) -> None:
        if type(capacity) is not int or not 1 <= capacity <= 64:
            raise ValueError()
        self.buffer: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=capacity)
        self.clock = clock
        self.context = threading.local()
        self._state_lock = threading.Lock()
        self._incomplete = False
        self._next_seq = 0
        self._reserved: set[int] = set()
        self._emitted: set[int] = set()

    @property
    def incomplete(self: Any) -> Any:
        with self._state_lock:
            return self._incomplete

    @incomplete.setter
    def incomplete(self: Any, value: Any) -> Any:
        with self._state_lock:
            self._incomplete = self._incomplete or value is True

    @property
    def next_seq(self: Any) -> Any:
        with self._state_lock:
            return self._next_seq

    @property
    def offered(self: Any) -> Any:
        with self._state_lock:
            return len(self._reserved)

    def reserve(self: Any) -> Any:
        with self._state_lock:
            self._next_seq += 1
            if len(self._reserved) >= 64:
                self._incomplete = True
                return None
            seq = self._next_seq
            self._reserved.add(seq)
            return seq

    def now(self: Any) -> Any:
        try:
            value = self.clock()
            if type(value) is not int or value < 0:
                raise ValueError()
            return value
        except Exception:
            self.incomplete = True
            return 0

    def offer(self: Any, record: Any) -> Any:
        try:
            validate_record(record)
            with self._state_lock:
                if record["seq"] not in self._reserved or record["seq"] in self._emitted:
                    self._incomplete = True
                    return
                self._emitted.add(record["seq"])
            self.buffer.put_nowait(dict(record))
        except Exception:
            self.incomplete = True


def validate_record(record: Any) -> Any:
    if type(record) is not dict or set(record) != FIELDS:
        raise ValueError()
    if record["kind"] not in ("message", "card") or record["actor"] not in (*"ABC", "BOT", "OTHER"):
        raise ValueError()
    if record["chat_kind"] not in ("p2p", "group", "other") or record["result"] not in RESULTS:
        raise ValueError()
    if record["toast_type"] not in ("none", "success", "info", "warning", "error", "unobserved"):
        raise ValueError()
    for key in (
        "seq",
        "receiver_calls",
        "entry_ns",
        "response_object_ready_ns",
        "handler_to_ready_ns",
    ):
        if type(record[key]) is not int or record[key] < 0:
            raise ValueError()
    for key in FIELDS - {
        "seq",
        "receiver_calls",
        "entry_ns",
        "response_object_ready_ns",
        "handler_to_ready_ns",
        "kind",
        "actor",
        "chat_kind",
        "result",
        "toast_type",
    }:
        if type(record[key]) is not bool:
            raise ValueError()
    if (
        record["wire_observed"]
        or record["client_toast_observed"]
        or (not record["C_evidence_inconclusive"])
    ):
        raise ValueError()
    if record["receiver_calls"] not in (0, 1) or not 1 <= record["seq"] <= 64:
        raise ValueError()
    if (
        record["response_object_ready_ns"] < record["entry_ns"]
        or record["handler_to_ready_ns"] != record["response_object_ready_ns"] - record["entry_ns"]
    ):
        raise ValueError()


class ReceiverObserver:
    def __init__(self: Any, delegate: Any, trace: Any) -> None:
        self.delegate, self.trace = (delegate, trace)

    def _receive(self: Any, function: Any, payload: Any) -> Any:
        current = getattr(self.trace.context, "record", None)
        try:
            if current is not None:
                current["receiver_calls"] += 1
        except Exception:
            self.trace.incomplete = True
        try:
            result = function(payload)
        except BaseException as error:
            try:
                code = (
                    error.code.value
                    if isinstance(error, ProbeContractError)
                    else "EVENT_CONFLICT"
                    if isinstance(error, ProbeConflict)
                    else "DB_FAILURE"
                    if isinstance(error, ProbeDatabaseFailure)
                    else "UNKNOWN_RECEIVER_EXCEPTION"
                )
                if current is not None:
                    current["result"] = code
            except Exception:
                self.trace.incomplete = True
            raise
        try:
            if current is not None:
                current["result"] = (
                    result.result
                    if isinstance(result, ProbeReceipt) and result.result in RESULTS
                    else "UNKNOWN_RECEIVER_RESULT"
                )
                current["commit_return_observed"] = isinstance(result, ProbeReceipt)
        except Exception:
            self.trace.incomplete = True
        return result

    def receive_message(self: Any, payload: Any) -> Any:
        return self._receive(self.delegate.receive_message, payload)

    def receive_card(self: Any, payload: Any) -> Any:
        return self._receive(self.delegate.receive_card, payload)


class ObservedGateway(ProbeGateway):
    def __init__(self: Any, receiver: Any, trace: Any, members: Any) -> None:
        if set(members) != set("ABC") or len(set(members.values())) != 3:
            raise ValueError()
        self.trace, self.members = (trace, dict(members))
        super().__init__(ReceiverObserver(receiver, trace))

    def _observe(self: Any, kind: Any, data: Any, original: Any) -> Any:
        trace = self.trace
        seq = trace.reserve()
        if seq is None:
            previous = getattr(trace.context, "record", None)
            trace.context.record = None
            try:
                return original(data)
            finally:
                trace.context.record = previous
        start = trace.now()
        record = dict(
            seq=seq,
            kind=kind,
            actor="OTHER",
            chat_kind="other",
            receiver_calls=0,
            result="UNOBSERVED",
            commit_return_observed=False,
            handler_returned=False,
            toast_type="none" if kind == "message" else "unobserved",
            entry_ns=start,
            response_object_ready_ns=start,
            handler_to_ready_ns=0,
            observer_evidence_incomplete=False,
            wire_observed=False,
            client_toast_observed=False,
            C_evidence_inconclusive=True,
        )
        previous = getattr(trace.context, "record", None)
        trace.context.record = record
        try:
            try:
                event = data.event
                if kind == "message":
                    sender = event.sender
                    if sender.sender_type == "bot":
                        record["actor"] = "BOT"
                    subject = sender.sender_id.open_id
                    chat = event.message.chat_type
                    record["chat_kind"] = chat if chat in ("p2p", "group") else "other"
                else:
                    subject = event.operator.open_id
                    record["chat_kind"] = "group"
                if record["actor"] != "BOT":
                    record["actor"] = next(
                        (a for a, value in self.members.items() if value == subject), "OTHER"
                    )
            except Exception:
                trace.incomplete = True
            response = original(data)
            record["handler_returned"] = True
            if kind == "card":
                try:
                    toast = response.toast.type
                    record["toast_type"] = (
                        toast if toast in ("success", "info", "warning", "error") else "unobserved"
                    )
                except Exception:
                    trace.incomplete = True
            return response
        finally:
            end = trace.now()
            record["response_object_ready_ns"] = max(start, end)
            record["handler_to_ready_ns"] = max(0, end - start)
            record["observer_evidence_incomplete"] = (
                trace.incomplete or record["receiver_calls"] != 1
            )
            trace.context.record = previous
            try:
                trace.offer(record)
            except Exception:
                trace.incomplete = True

    def on_message(self: Any, data: Any) -> Any:
        return self._observe("message", data, super().on_message)

    def on_card(self: Any, data: Any) -> Any:
        return self._observe("card", data, super().on_card)
