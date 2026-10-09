"""Issue23 opt-in 诊断：仅安全阶段/PID/barrier，不改变业务或恢复结果。"""

import json
import os
import time
from typing import Any

import pytest


def emit(event: str, **fields: Any) -> None:
    print(
        "PG_DIAG "
        + json.dumps({"event": event, "pid": os.getpid(), "monotonic": time.monotonic(), **fields}),
        flush=True,
    )


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


def pytest_configure(config: Any) -> None:
    if os.environ.get("P123_DIAG") != "1":
        raise ValueError("explicit diagnostic mode required")
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
