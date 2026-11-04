"""One owned native child per already-committed durable lease. No retries or expiry release."""

import hashlib
import os
import signal
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from commerceops.application.v41.parse_protocol import ParseInput, ParseResult
from commerceops.domain.commerce_values import canonical_bytes


class ParseUnavailable(ValueError):
    """The original durable lease/result must be reconciled, never replayed automatically."""


@dataclass(frozen=True)
class NativeParse:
    result: ParseResult
    proof: dict[str, Any]


def run_parser(
    command: ParseInput,
    process_ref: UUID,
    bind: Callable[[int], None],
    stop: Callable[[dict[str, Any]], None],
) -> NativeParse:
    """Caller committed reserve first. Bind commits PID; stop commits only after actual reap.

    If spawn raises without a process handle, or persistence fails, the reservation remains
    occupied. Parent death cannot erase it; the child additionally has its own kernel alarm.
    Neither a Python timeout nor an expired database row is evidence that the child stopped.
    """
    raw = canonical_bytes(command.model_dump(mode="json"))
    if len(raw) > 3 * 1024 * 1024:
        raise ParseUnavailable("LIMIT_EXCEEDED")
    process = subprocess.Popen(  # noqa: S603 - fixed interpreter/module; UUID-only server nonce
        [
            sys.executable,
            "-I",
            "-m",
            "commerceops.entrypoints.v41_parse_child",
            "--process-ref",
            str(process_ref),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
        env={"PATH": os.defpath, "PYTHONIOENCODING": "utf-8"},
    )
    timed_out = False
    output = b""
    caught: BaseException | None = None
    try:
        bind(process.pid)
        output, _ = process.communicate(raw, timeout=2.0)
    except BaseException as error:
        caught = error
        timed_out = isinstance(error, subprocess.TimeoutExpired)
    finally:
        if process.poll() is None:
            # This process group was created by this exact Popen handle, never a database PID.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        tail, _ = process.communicate()
        if not output:
            output = tail
        native_exit = process.wait()
        proof = dict(
            process_ref=str(process_ref),
            pid=process.pid,
            native_exit=native_exit,
            timed_out=timed_out,
            reaped=True,
            output_digest=hashlib.sha256(output.removesuffix(b"\n")).hexdigest(),
        )
        stop(proof)  # A failed write leaves the durable slot occupied; never substitute success.
    if caught is not None:
        if isinstance(caught, (KeyboardInterrupt, SystemExit)):
            raise caught
        raise ParseUnavailable("PARSE_FAILED") from None
    if native_exit != 0 or timed_out or not output.endswith(b"\n") or len(output) > 2097153:
        raise ParseUnavailable("IMPORT_INVALID")
    try:
        result = ParseResult.model_validate_json(output)
        if canonical_bytes(result.model_dump(mode="json")) + b"\n" != output:
            raise ValueError("PARSER_RESULT_INVALID")
    except ValueError:
        raise ParseUnavailable("IMPORT_INVALID") from None
    return NativeParse(result, proof)
