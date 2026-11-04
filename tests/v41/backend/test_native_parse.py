"""Actual local pure child processes; no API/database/service startup or mocked reaping."""

import base64
import os
import subprocess
import sys
import time
from uuid import uuid4

import pytest
from commerceops.application.v41.contracts import ColumnMapping
from commerceops.application.v41.parse_protocol import ParseInput
from commerceops.infrastructure.v41_parse import ParseUnavailable, run_parser

pytestmark = pytest.mark.offline


def command(data: bytes = b"sku,title,price,currency\nNEW-1,Example,0.1,TWD\n") -> ParseInput:
    return ParseInput(
        format="csv",
        file_base64=base64.b64encode(data).decode(),
        mapping=ColumnMapping(sku="sku", title="title", price="price", currency="currency"),
        currency="TWD",
        existing_skus=(),
    )


def test_native_result_exit_reaped_and_no_raw_file() -> None:
    events = []
    ref = uuid4()
    result = run_parser(command(), ref, lambda pid: events.append(pid), events.append)
    assert result.result.state == "READY" and result.result.products[0].price == "0.1"
    assert events[0] == result.proof["pid"] and events[1] == result.proof
    assert result.proof["native_exit"] == 0 and result.proof["reaped"] is True
    with pytest.raises(ProcessLookupError):
        os.kill(result.proof["pid"], 0)
    assert "file_base64" not in result.result.model_dump()


def test_binding_failure_kills_and_actually_reaps_before_stop() -> None:
    events = []

    def bind(pid: int) -> None:
        events.append(pid)
        raise OSError("simulated persistence loss")

    with pytest.raises(ParseUnavailable, match="PARSE_FAILED"):
        run_parser(command(), uuid4(), bind, events.append)
    proof = events[1]
    assert proof["native_exit"] != 0 and proof["reaped"] is True
    with pytest.raises(ProcessLookupError):
        os.kill(proof["pid"], 0)


def test_stop_persistence_failure_is_not_substituted_or_retried() -> None:
    events = []

    def stop(proof: dict) -> None:
        events.append(proof)
        raise OSError("simulated persistence loss")

    with pytest.raises(OSError):
        run_parser(command(), uuid4(), lambda _: None, stop)
    assert len(events) == 1 and events[0]["reaped"] is True


def test_invalid_actual_file_returns_no_partial_result_and_safe_native_failure() -> None:
    proofs = []
    with pytest.raises(ParseUnavailable, match="IMPORT_INVALID"):
        run_parser(command(b"not-a-valid-csv\x00"), uuid4(), lambda _: None, proofs.append)
    assert proofs[0]["native_exit"] == 1 and proofs[0]["reaped"] is True


def test_child_kernel_deadline_independent_of_parent_communicate() -> None:
    start = time.monotonic()
    child = subprocess.Popen(  # noqa: S603 - fixed interpreter/module and server UUID
        [
            sys.executable,
            "-I",
            "-m",
            "commerceops.entrypoints.v41_parse_child",
            "--process-ref",
            str(uuid4()),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env={"PATH": os.defpath},
    )
    try:
        # Keep stdin open and provide no input; no communicate(timeout) kills this child.
        native_exit = child.wait(timeout=4)
        assert native_exit != 0 and 1.5 <= time.monotonic() - start < 4
        with pytest.raises(ProcessLookupError):
            os.kill(child.pid, 0)
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate()
        child.wait()
