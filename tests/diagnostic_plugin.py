"""Issue23 opt-in 诊断：仅安全阶段/PID/barrier，不改变业务或恢复结果。"""

import json
import os
import re
import stat
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest


def emit(event: str, **fields: Any) -> None:
    print(
        "PG_DIAG "
        + json.dumps({"event": event, "pid": os.getpid(), "monotonic": time.monotonic(), **fields}),
        flush=True,
    )


# A diagnostic observation, never the command/authorization deadline. CPython 3.12's
# C watchdog can crash while traversing concurrently retiring thread states. A Python
# callback holds the GIL; a GIL-stuck process still relies on the external supervisor.
STACK_DUMP_SECONDS = 45.0


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item: Any) -> Any:
    import faulthandler

    output = sys.__stderr__ if sys.__stderr__ is not None else sys.stderr
    descriptor = os.dup(output.fileno())
    errors: list[str] = []

    def dump() -> None:
        try:
            emit("stack_dump", nodeid=item.nodeid, mechanism="python_timer")
            faulthandler.dump_traceback(file=descriptor, all_threads=True)
        except Exception as error:
            errors.append(type(error).__name__)

    timer = threading.Timer(STACK_DUMP_SECONDS, dump)
    timer.daemon = True
    timer.start()
    try:
        result = yield
    finally:
        timer.cancel()
        timer.join(timeout=5)
        if timer.is_alive():
            # Keep this FD owned until process exit: a late writer must not hit a
            # recycled descriptor. An incomplete diagnostic cannot silently pass.
            raise RuntimeError("diagnostic stack timer did not stop")
        os.close(descriptor)
    if errors:
        raise RuntimeError("diagnostic stack dump failed: " + errors[0])
    return result


def pytest_collection_finish(session: Any) -> None:
    emit("collection", count=len(session.items), nodes=[item.nodeid for item in session.items])


def pytest_runtest_logstart(nodeid: str, location: Any) -> None:
    emit("node_start", nodeid=nodeid)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item: Any) -> Any:
    emit("phase_start", nodeid=item.nodeid, phase="setup")
    return (yield)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: Any) -> Any:
    emit("phase_start", nodeid=item.nodeid, phase="call")
    return (yield)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item: Any) -> Any:
    emit("phase_start", nodeid=item.nodeid, phase="teardown")
    return (yield)


def pytest_runtest_logreport(report: Any) -> None:
    emit(
        "phase_end",
        nodeid=report.nodeid,
        phase=report.when,
        outcome=report.outcome,
        duration=report.duration,
    )


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: Any, call: Any) -> Any:
    report = yield
    if (
        item.nodeid.split("::", 1)[0]
        not in {
            "tests/test_p5_sources_pg.py",
            "tests/test_p5_feishu_pg.py",
            "tests/test_p5_m2_pending_pg.py",
            "tests/test_p5_m2_backup_pg.py",
            "tests/test_p5_m2_mixed_pg.py",
        }
        and item.nodeid
        != (
            "tests/test_p4_history_pg.py::"
            "test_0016_upgrade_preserves_original_rows_payload_and_unknown_attempt"
        )
    ) or call.excinfo is None:
        return report
    # Only structural failure facts; never stringify exceptions, locals or SQL.
    error = call.excinfo.value
    kind = type(error).__name__
    if kind not in {
        "ValueError",
        "KeyError",
        "TypeError",
        "AttributeError",
        "AssertionError",
        "TimeoutError",
        "RuntimeError",
        "PermissionError",
        "OperationalError",
        "QueryCanceled",
        "InsufficientPrivilege",
        "CheckViolation",
        "SourceBindingError",
    }:
        kind = "BaseException"
    import psycopg

    try:
        state = error.sqlstate if isinstance(error, psycopg.Error) else None
    except Exception:
        state = None
    if not isinstance(state, str) or re.fullmatch(r"[0-9A-Z]{5}", state) is None:
        state = None
    frames: list[dict[str, str | int]] = []
    schema_delta = None
    trace = error.__traceback__
    while trace is not None:
        code = trace.tb_frame.f_code
        name = Path(code.co_filename).name
        if name in {
            "test_p5_sources_pg.py",
            "test_p5_feishu_pg.py",
            "woo_collection.py",
            "commerce_sources.py",
            "database.py",
            "web_config.py",
            "m2_state.py",
            "m2_backup.py",
            "test_p5_m2_pending_pg.py",
            "test_p5_m2_backup_pg.py",
            "test_p5_m2_mixed_pg.py",
            "test_p4_history_pg.py",
        }:
            frames.append({"file": name, "line": trace.tb_lineno})
        if (
            name == "test_p4_history_pg.py"
            and code.co_name
            == "test_0016_upgrade_preserves_original_rows_payload_and_unknown_attempt"
        ):
            before = trace.tb_frame.f_locals.get("before")
            after = trace.tb_frame.f_locals.get("after")
            if isinstance(before, dict) and isinstance(after, dict):
                known = {
                    "business.p4_history_recoveries",
                    "business.p4_history_messages",
                    "business.p4_read_message_sources",
                    "business.p5_commerce_source_bindings",
                }
                added = set(after) - set(before)
                schema_delta = dict(
                    known_added=sorted(added & known),
                    added_count=len(added),
                    removed_count=len(set(before) - set(after)),
                    original_rows_equal=all(after.get(k) == v for k, v in before.items()),
                )
        trace = trace.tb_next
    metadata = None
    fixture = item.funcargs.get("fixture")
    if fixture is not None:
        try:
            info = fixture.config.database.password_file.lstat()
            metadata = {
                "process_uid": os.geteuid(),
                "file_uid": info.st_uid,
                "mode": stat.S_IMODE(info.st_mode),
                "regular": stat.S_ISREG(info.st_mode),
            }
        except (AttributeError, OSError):
            pass
    emit(
        "p5_failure",
        nodeid=item.nodeid,
        phase=call.when,
        exception_class=kind,
        sqlstate=state,
        frames=frames[-16:],
        database_file_metadata=metadata,
        schema_delta=schema_delta,
    )
    return report


def pytest_configure(config: Any) -> None:
    if os.environ.get("P123_DIAG") != "1":
        raise ValueError("explicit diagnostic mode required")
    if float(config.getini("faulthandler_timeout")) != 0:
        raise ValueError("PG diagnostic requires its GIL-held timer, not the C watchdog")
    if os.environ.get("P123_TRACE_CHILD", "1") == "0":
        return
    # 同一测试进程内复用原事件 Queue；只在已批准的测试 harness 加观察点。
    from tests.checkpoint_support import Process as GraphProcess
    from tests.test_worker_pg import Process as WorkerProcess

    def read(process: Any) -> None:
        assert process.process.stdout is not None
        for line in process.process.stdout:
            event = json.loads(line)
            process.events.put(event)
            allowed = {
                k: v
                for k, v in event.items()
                if k
                in {
                    "event",
                    "point",
                    "task",
                    "job",
                    "thread",
                    "active",
                    "maximum",
                    "attempt",
                    "owner",
                    "kind",
                    "code",
                    "pid",
                    "lock_pid",
                }
            }
            emit("child_event", child_pid=process.process.pid, data=allowed)

    patch = pytest.MonkeyPatch()
    patch.setattr(GraphProcess, "_read", read)
    patch.setattr(WorkerProcess, "_read", read)
    config.add_cleanup(patch.undo)
