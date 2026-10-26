"""部署启动层；本任务仅提供显式技术 test runner，正式图由 P1-04 注入。"""

import argparse
import asyncio
import os
import signal
from pathlib import Path
from uuid import UUID

from commerceops.adapters.feishu.contracts import ProbePolicy
from commerceops.application.commerce.analysis_task import InventoryTaskRequest
from commerceops.application.commerce.collection import InventoryCollector
from commerceops.application.commerce.source_binding import SourceBindingError
from commerceops.application.feishu_business.clarification import ClarificationSender
from commerceops.application.feishu_business.contracts import BaseProjectionAdapter
from commerceops.application.feishu_business.delivery import DeliveryGate
from commerceops.application.feishu_business.im_delivery import BusinessMessageSender
from commerceops.application.runner import RunnerPort, RunRequest, RunResult
from commerceops.infrastructure.database import DatabaseSettings
from commerceops.infrastructure.explanation_repository import ExplanationStore
from commerceops.infrastructure.feishu_base_delivery import BaseDeliveryStore
from commerceops.infrastructure.feishu_clarification import ClarificationDeliveryStore
from commerceops.infrastructure.feishu_im_delivery import IMDeliveryStore
from commerceops.infrastructure.intent_repository import IntentStore
from commerceops.infrastructure.inventory_repository import InventoryStore
from commerceops.infrastructure.replenishment_repository import ApprovalStore
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.woo_collection import BoundWooCollectorFactory
from commerceops.infrastructure.worker import UnsafeShutdown, Worker
from commerceops.infrastructure.worker_lock import WorkerSession, confirm_termination
from commerceops.workflows.inventory_analysis import InventoryRunner, MockCollectorFactory
from commerceops.workflows.inventory_routing import IntentRunner
from commerceops.workflows.replenishment import ApprovalRunner
from commerceops.workflows.report_explanation import (
    ExplanationRunner,
    InventoryCompositeRunner,
    ProviderFactory,
)


class TechnicalRunner:
    workflow_versions = frozenset({"p103-technical-v1"})

    async def run(self, request: RunRequest) -> RunResult:
        # 无库存/模型/审批/checkpoint，只证明串行调度；不写业务 completed。
        return RunResult()


def unavailable_mock(request: InventoryTaskRequest) -> InventoryCollector:
    raise SourceBindingError()


async def serve(
    settings: DatabaseSettings,
    organization: UUID,
    fixture: Path | None = None,
    *,
    allow_actual: bool = False,
    key_file: Path | None = None,
    web_config: WebConfig | None = None,
    clarification_sender: ClarificationSender | None = None,
    feishu_policy: ProbePolicy | None = None,
    base_adapter: BaseProjectionAdapter | None = None,
    delivery_gate: DeliveryGate | None = None,
    message_sender: BusinessMessageSender | None = None,
    message_gate: DeliveryGate | None = None,
) -> None:
    stop = asyncio.Event()
    if web_config is not None and (allow_actual or key_file is not None):
        raise ValueError("P3 model requests are disabled")
    if (clarification_sender is not None or message_sender is not None) != (
        feishu_policy is not None
    ):
        raise ValueError("explicit matching clarification transport/policy required")
    if (base_adapter is None) != (delivery_gate is None):
        raise ValueError("explicit matching Base adapter/delivery gate required")
    if (
        (message_sender is None) != (message_gate is None)
        or message_sender is not None
        and web_config is None
    ):
        raise ValueError("explicit matching IM sender/gate/business configuration required")
    if web_config is not None and any(
        getattr(settings, key) != getattr(web_config.database, key)
        for key in ("host", "port", "name", "user", "password_file")
    ):
        raise ValueError("P3 worker and owned database configuration differ")
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    session = WorkerSession(settings, organization)
    await session.start()
    print(f"technical test worker started: owner={session.owner}", flush=True)
    try:
        runner: RunnerPort
        sources = web_config.commerce_sources if web_config is not None else None
        woo_factory = BoundWooCollectorFactory(settings, sources) if sources is not None else None
        mock_factory = MockCollectorFactory(fixture) if fixture is not None else unavailable_mock
        approval = (
            ApprovalRunner(
                ApprovalStore(web_config, session),
                collector_factory=MockCollectorFactory(fixture) if fixture is not None else None,
                woo_collector_factory=woo_factory,
            )
            if web_config is not None
            else None
        )
        if fixture is not None or woo_factory is not None:
            factory = ProviderFactory(allow_actual=allow_actual, key_file=key_file)
            runner = InventoryCompositeRunner(
                InventoryRunner(
                    InventoryStore(settings, session, commerce_sources=sources),
                    mock_factory,
                    woo_collector_factory=woo_factory,
                ),
                ExplanationRunner(ExplanationStore(settings, session), factory),
                IntentRunner(IntentStore(settings, session), factory),
                approval,
            )
        else:
            runner = TechnicalRunner()
        clarification = (
            ClarificationDeliveryStore(
                session, feishu_policy, clarification_sender, controlled_sender=True
            )
            if feishu_policy is not None and clarification_sender is not None
            else None
        )
        base_delivery = (
            BaseDeliveryStore(session, base_adapter, delivery_gate)
            if base_adapter is not None and delivery_gate is not None
            else None
        )
        im_delivery = (
            IMDeliveryStore(session, web_config, feishu_policy, message_sender, message_gate)
            if web_config is not None
            and feishu_policy is not None
            and message_sender is not None
            and message_gate is not None
            else None
        )

        async def maintenance() -> None:
            if approval is not None:
                await approval.reconcile()
            if clarification is not None:
                await clarification.reconcile()
            if im_delivery is not None:
                await im_delivery.reconcile()
            if base_delivery is not None:
                await base_delivery.reconcile()

        await Worker(
            session,
            runner,
            reconcile=maintenance
            if approval or clarification or im_delivery or base_delivery
            else None,
            recovery_scan_seconds=web_config.recovery_scan_seconds if web_config else 30,
        ).run(stop)
    except UnsafeShutdown:
        # 在 asyncio.run 清理 pending tasks 之前退出；非合作调用不能拖住退出。
        print("worker cancellation unconfirmed; termination confirmation required", flush=True)
        os._exit(75)


def main() -> None:
    parser = argparse.ArgumentParser(description="Single Worker technical test / recovery")
    parser.add_argument("action", choices=["test-run", "inventory-test-run", "confirm-termination"])
    parser.add_argument("--organization", type=UUID)
    parser.add_argument("--fixture-directory", type=Path)
    parser.add_argument("--allow-actual-model-probe", action="store_true")
    parser.add_argument("--model-key-file", type=Path)
    parser.add_argument("--owner")
    parser.add_argument("--evidence-reference")
    parser.add_argument("--confirm-old-process-terminated", action="store_true")
    args = parser.parse_args()
    try:
        config_path = os.environ.get("COMMERCEOPS_P3_CONFIG_FILE")
        web_config = WebConfig.from_file(Path(config_path)) if config_path else None
        settings = web_config.database if web_config else DatabaseSettings()
        if args.action in ("test-run", "inventory-test-run"):
            if os.environ.get("COMMERCEOPS_MODE") != "test" or args.organization is None:
                raise ValueError("explicit test mode and organization required")
            if args.action == "inventory-test-run" and args.fixture_directory is None:
                raise ValueError("owned fixture directory required")
            if args.allow_actual_model_probe and (
                args.action != "inventory-test-run" or args.model_key_file is None
            ):
                raise ValueError("actual model probe requires explicit test fixture/key file")
            asyncio.run(
                serve(
                    settings,
                    args.organization,
                    args.fixture_directory if args.action == "inventory-test-run" else None,
                    allow_actual=args.allow_actual_model_probe,
                    key_file=args.model_key_file,
                    web_config=web_config,
                )
            )
        else:
            if (
                not args.confirm_old_process_terminated
                or not args.owner
                or not args.evidence_reference
            ):
                raise ValueError("operator termination confirmation required")
            asyncio.run(confirm_termination(settings, args.owner, args.evidence_reference))
    except UnsafeShutdown:
        print(
            "worker unsafe cancellation: process exiting; termination confirmation required",
            flush=True,
        )
        os._exit(75)
    except Exception as error:
        # 仅固定异常类别；不打印数据库/runner 原始错误、参数或 DSN。
        raise SystemExit(f"worker failed: {type(error).__name__}") from None


if __name__ == "__main__":
    main()
