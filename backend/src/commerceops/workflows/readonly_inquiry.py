"""Single-worker analyze runner; completed result replay never calls the choice port."""

import json
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from commerceops.application.commerce.readonly_inquiry_contracts import (
    ChoicePort,
    Context,
    IdentityPort,
    ReadPort,
    Window,
)
from commerceops.application.commerce.readonly_inquiry_executor import NAMES, Tool, execute
from commerceops.application.commerce.readonly_inquiry_service_contracts import (
    WORKFLOW,
    ResultPayload,
)
from commerceops.application.commerce.readonly_inquiry_service_demo import DemoChoice
from commerceops.application.replenishment.contracts import WebFailure
from commerceops.application.runner import RunRequest, RunResult
from commerceops.infrastructure.readonly_inquiry_runtime import (
    InquiryAuthority,
    ServiceReadPort,
    db_call,
)
from commerceops.infrastructure.readonly_inquiry_store import InquiryStore
from commerceops.infrastructure.worker_lock import WorkerSession


class RunnerStore(Protocol):
    def load(self, run: RunRequest) -> tuple[dict[str, Any], ResultPayload | None]: ...
    def mark(self, run: RunRequest) -> None: ...
    def finish(self, run: RunRequest, result: ResultPayload) -> None: ...
    def fail_safe(self, run: RunRequest, known: ResultPayload | None = None) -> None: ...


class RuntimeCheck(Protocol):
    async def check(self) -> None: ...


Runtime = tuple[Context, ChoicePort, IdentityPort, ReadPort]
RuntimeFactory = Callable[[RunRequest, dict[str, Any]], Awaitable[Runtime]]


def runtime_factory(store: InquiryStore, session: WorkerSession) -> RuntimeFactory:
    async def factory(run: RunRequest, row: dict[str, Any]) -> Runtime:
        fixture = store.inquiry.fixture()
        domain = Window.model_validate_json(json.dumps(row["source_domain"]))
        context = Context(
            request_id=str(run.task_id),
            principal_id=str(row["principal_id"]),
            organization_id=str(run.organization_id),
            shop_id=fixture.source.shop_id,
            identity_id=str(row["identity_id"]),
            auth_version=row["auth_version"],
            source_binding=row["source_binding"],
            question=row["request"]["question"],
        )
        report_id = str(row["context_report_id"]) if row["context_report_id"] else None
        return (
            context,
            DemoChoice(domain, report_id),
            InquiryAuthority(store, session, run),
            ServiceReadPort(store, run, domain),
        )

    return factory


class ReadonlyInquiryRunner:
    workflow_versions = frozenset({WORKFLOW})

    def __init__(self, store: RunnerStore, session: RuntimeCheck, factory: RuntimeFactory):
        self.store, self.session, self.factory = store, session, factory
        self.active = False

    async def run(self, run: RunRequest) -> RunResult:
        if self.active or run.workflow_version != WORKFLOW or run.kind != "analyze":
            raise ValueError("INQUIRY_RUN_BINDING")
        self.active = True
        payload: ResultPayload | None = None
        try:
            await self.session.check()
            row, previous = await db_call(self.store.load, run)
            if previous is not None:
                return RunResult()
            await db_call(self.store.mark, run)
            context, chooser, identity, reader = await self.factory(run, row)
            result = await execute(
                context, chooser, identity, {name: Tool("read", reader) for name in NAMES}
            )
            payload = ResultPayload.from_outcome(result)
            await self.session.check()
            await db_call(self.store.finish, run, payload)
            return RunResult()
        except (WebFailure, OSError):
            await self.session.check()
            await db_call(self.store.fail_safe, run, payload)
            return RunResult()
        finally:
            self.active = False
