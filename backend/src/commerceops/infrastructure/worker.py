"""一个调度循环、一个 runner 槽；心跳仅维护连接和当前 job，不执行图。"""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress

from commerceops.application.replenishment.contracts import WORKFLOW_VERSION as P3_VERSION
from commerceops.application.runner import RunnerPort, RunRequest, RunResult
from commerceops.infrastructure.queue import JobQueue
from commerceops.infrastructure.worker_lock import WorkerSession, mark_attention, open_async


class UnsafeShutdown(Exception):
    """调用未在取消预算内停止；进程入口必须硬退出，保留未确认启动回执。"""


class Worker:
    def __init__(
        self,
        session: WorkerSession,
        runner: RunnerPort,
        *,
        heartbeat_seconds: float = 15,
        poll_seconds: float = 1,
        cancel_seconds: float = 5,
        max_attempts: int = 3,
        reconcile: Callable[[], Awaitable[None]] | None = None,
        recovery_scan_seconds: int = 30,
    ):
        if (
            min(heartbeat_seconds, poll_seconds, cancel_seconds) <= 0
            or max_attempts < 1
            or not 1 <= recovery_scan_seconds <= 30
        ):
            raise ValueError("invalid worker timing or attempt limit")
        self.session = session
        self.runner = runner
        self.queue = JobQueue(session)
        self.heartbeat_seconds = heartbeat_seconds
        self.poll_seconds = poll_seconds
        self.cancel_seconds = cancel_seconds
        self.max_attempts = max_attempts
        self.reconcile = reconcile
        self.recovery_scan_seconds = recovery_scan_seconds
        self.current: RunRequest | None = None
        self._job_lock = asyncio.Lock()

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_seconds)
            await self.session.check()
            async with self._job_lock:
                if self.current is not None:
                    await self.queue.renew(self.current)

    async def _cancel(self, task: asyncio.Task[object]) -> None:
        task.cancel()
        done, _ = await asyncio.wait([task], timeout=self.cancel_seconds)
        if not done:
            raise UnsafeShutdown("runner cancellation unconfirmed")
        # 获取异常，取消/调用失败均不误报成功；保留 running 供已确认停止后重排。
        with suppress(asyncio.CancelledError, Exception):
            task.result()

    async def run(self, stop: asyncio.Event) -> None:
        """session 必须先 start；正常返回时所有 runner 调用已结束。"""
        clean = False
        heartbeat = asyncio.create_task(self._heartbeat())
        stopping = asyncio.create_task(stop.wait())
        call: asyncio.Task[object] | None = None
        try:
            await self.queue.recover_confirmed()
            next_scan = 0.0
            while not stop.is_set():
                if heartbeat.done():
                    heartbeat.result()
                if self.reconcile is not None and asyncio.get_running_loop().time() >= next_scan:
                    # 只在同Worker无在途Graph时做P3匹配读取/ready；不是独立调度进程。
                    await self.reconcile()
                    next_scan = asyncio.get_running_loop().time() + self.recovery_scan_seconds
                if stop.is_set():
                    break
                job = await self.queue.claim()
                if job is None:
                    await asyncio.wait(
                        [heartbeat, stopping],
                        timeout=self.poll_seconds,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    continue
                self.current = job
                if job.kind not in ("analyze", "resume", "recover") or (
                    job.workflow_version not in self.runner.workflow_versions
                ):
                    async with self._job_lock:
                        await self.queue.dead(
                            job,
                            "JOB_KIND_UNSUPPORTED"
                            if job.kind not in ("analyze", "resume", "recover")
                            else "WORKFLOW_VERSION_UNSUPPORTED",
                        )
                        self.current = None
                    continue
                call = asyncio.create_task(self.runner.run(job))
                await asyncio.wait([call, heartbeat, stopping], return_when=asyncio.FIRST_COMPLETED)
                if heartbeat.done():
                    await self._cancel(call)
                    call = None
                    heartbeat.result()
                    raise RuntimeError("heartbeat unexpectedly stopped")
                if stop.is_set():
                    await self._cancel(call)
                    call = None
                    self.current = None
                    break
                async with self._job_lock:
                    try:
                        result = call.result()
                    except Exception:
                        if job.attempt >= self.max_attempts:
                            await self.queue.dead(job)
                        else:
                            await self.queue.defer(job, min(60, 2**job.attempt), failed=True)
                    else:
                        # call 的真实结果为 RunResult；object 标注允许统一取消任务。
                        if not isinstance(result, RunResult):
                            await self.queue.dead(job, "RUNNER_RESULT_INVALID")
                        elif result.status == "retry":
                            if job.attempt >= self.max_attempts:
                                await self.queue.dead(job)
                            else:
                                await self.queue.defer(job, result.delay_seconds)
                        elif result.status in ("waiting_checkpoint", "pending_execution"):
                            allowed = job.workflow_version == P3_VERSION and (
                                (result.status == "waiting_checkpoint" and job.kind == "resume")
                                or (result.status == "pending_execution" and job.kind == "recover")
                            )
                            if not allowed:
                                await self.queue.dead(job, "RUNNER_RESULT_INVALID")
                            else:
                                # 注册的持久依赖等待不按三次执行故障杀死，不重发决定/START。
                                await self.queue.defer(job, result.delay_seconds)
                        elif result.status in ("done", "interrupted"):
                            await self.queue.done(job)
                        else:
                            await self.queue.dead(job)
                    call = None
                    self.current = None
            clean = True
        finally:
            heartbeat.cancel()
            stopping.cancel()
            await asyncio.gather(heartbeat, stopping, return_exceptions=True)
            try:
                if call is not None:
                    await self._cancel(call)
                if not clean:
                    # 锁连接失效仍尝试独立业务连接留 needs_attention；DB 故障时
                    # 持久 started 回执在 DB 恢复后阻止任何自动启动。
                    with suppress(Exception):
                        async with await open_async(self.session.settings) as db:
                            await mark_attention(db, self.session.owner)
            finally:
                await self.session.close(clean=clean)
