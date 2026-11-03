"""同Worker槽内的确定性日报；无新调度器、模型、发送或后台采集任务。"""

import time
from collections.abc import Awaitable, Callable

from commerceops.adapters.commerce.daily import collect
from commerceops.application.daily.source import WORKFLOW, DailyUnsafe, WooMetadata
from commerceops.application.runner import RunRequest, RunResult
from commerceops.infrastructure.daily_sources import fixture_rows, manifest_for
from commerceops.infrastructure.daily_store import DailyStore


async def no_hook(point: str) -> None:
    pass


class DailyRunner:
    workflow_versions = frozenset({WORKFLOW})

    def __init__(self, store: DailyStore, *, hook: Callable[[str], Awaitable[None]] = no_hook):
        self.store, self.hook = store, hook
        self.active = False

    async def run(self, run: RunRequest) -> RunResult:
        if self.active:
            raise DailyUnsafe()
        self.active = True
        try:
            if run.kind not in ("analyze", "recover") or run.workflow_version != WORKFLOW:
                raise DailyUnsafe()
            # 先持久回执，既不读当前秘密也不重采；report经store从原snapshot复算。
            if await self.store.existing(run) is not None:
                await self.hook("persistent_replay")
                return RunResult()
            tick = time.monotonic()
            active_binding = self.store.files.active(run.organization_id, run.shop_id)
            configured = self.store.files.metadata(active_binding)
            deadline = tick + configured.limits.max_elapsed_seconds
            request, metadata = await self.store.load(run, deadline)
            manifest = manifest_for(metadata)
            if isinstance(metadata, WooMetadata):
                active = self.store.files.active(run.organization_id, run.shop_id)
                pins = self.store.files.pins(active, metadata)
                fixture = None
            else:
                pins, fixture = None, fixture_rows(metadata)
            if time.monotonic() >= deadline:
                raise DailyUnsafe("DAILY_SOURCE_UNAVAILABLE")
            await self.hook("before_collection")
            snapshot, report, receipt = collect(
                request, metadata, manifest, absolute_deadline=deadline, pins=pins, fixture=fixture
            )
            await self.hook("collected")
            await self.store.save(run, snapshot, report, receipt)
            await self.hook("report_committed")
            return RunResult()
        except DailyUnsafe as error:
            await self.store.fail(run, error.code)
            return RunResult()
        except (OSError, ValueError):
            await self.store.fail(run, "DAILY_SOURCE_UNAVAILABLE")
            return RunResult()
        except Exception:
            # 提交后故障不重采；存储故障沿用原Worker有限重试。
            if await self.store.existing(run) is not None:
                return RunResult()
            if run.attempt >= 3:
                await self.store.fail(run, "DAILY_STORAGE_FAILURE")
                return RunResult()
            raise
        finally:
            self.active = False
