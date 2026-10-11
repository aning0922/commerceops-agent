"""显式受控测试的正式SDK装配；只复用原单Worker/Graph与持久delivery。"""

import argparse
import asyncio
import json
import os
import signal
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from commerceops.adapters.feishu.business_base import BusinessBaseAdapter, BusinessRecordSDK
from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.adapters.feishu.business_factory import BusinessSDKFactory, private_value
from commerceops.adapters.feishu.business_im import BusinessIMSDK
from commerceops.adapters.feishu.business_preflight import verified_target
from commerceops.adapters.feishu.sdk import restrict_sdk_logs
from commerceops.application.feishu_business.delivery import DeliveryGate
from commerceops.application.feishu_business.gateway_window import GatewayWindow
from commerceops.application.feishu_business.worker_window import ControlledWorkerWindow
from commerceops.infrastructure.explanation_repository import ExplanationStore
from commerceops.infrastructure.feishu_base_delivery import BaseDeliveryStore
from commerceops.infrastructure.feishu_gateway_window import claimed_state
from commerceops.infrastructure.feishu_im_delivery import IMDeliveryStore
from commerceops.infrastructure.feishu_sdk_ledger import PersistentSDKLedger
from commerceops.infrastructure.intent_repository import IntentStore
from commerceops.infrastructure.inventory_repository import InventoryStore
from commerceops.infrastructure.replenishment_repository import ApprovalStore
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.worker import UnsafeShutdown, Worker
from commerceops.infrastructure.worker_lock import WorkerSession, open_async
from commerceops.workflows.inventory_analysis import CollectorFactory, InventoryRunner
from commerceops.workflows.inventory_routing import IntentRunner
from commerceops.workflows.replenishment import ApprovalRunner
from commerceops.workflows.report_explanation import (
    ExplanationRunner,
    InventoryCompositeRunner,
    ProviderFactory,
)


async def trusted_scope(
    config: WebConfig, settings: BusinessSettings, window: ControlledWorkerWindow
) -> None:
    async with await open_async(config.database) as db:
        cursor = await db.execute(
            """SELECT g.after_state,g.occurred_at FROM business.audit_events g
            JOIN business.organizations o ON o.id=g.organization_id
            JOIN business.shops s ON s.organization_id=o.id AND s.id=%s
            WHERE g.id=%s AND g.organization_id=%s AND g.source='feishu_gateway'
            AND g.action='gateway_start_claimed' AND g.entity_type='gateway_window'
            AND o.feishu_app_id=%s AND o.feishu_tenant_key=%s
            AND s.adapter_kind='mock' AND s.environment IN ('mock','test')""",
            (
                settings.shop_id,
                window.gateway_window_id,
                settings.organization_id,
                settings.app_id,
                settings.tenant_key,
            ),
        )
        row = await cursor.fetchone()
        if not row:
            raise PermissionError("P4_CONTROLLED_GATEWAY_SCOPE_REQUIRED")
        state = row["after_state"]
        gateway = GatewayWindow.model_validate_json(
            json.dumps({key: state.get(key) for key in GatewayWindow.model_fields})
        )
        if (
            state != claimed_state(gateway)
            or not gateway.active()
            or (gateway.organization_id, gateway.shop_id)
            != (window.organization_id, window.shop_id)
            or window.expires_at > gateway.expires_at
        ):
            raise PermissionError("P4_CONTROLLED_GATEWAY_SCOPE_REQUIRED")
        cursor = await db.execute(
            """SELECT DISTINCT t.id,s.parameters FROM business.business_tasks t
            JOIN business.p3_task_sources s ON s.task_id=t.id
            AND s.organization_id=t.organization_id AND s.shop_id=t.shop_id
            JOIN business.conversations c ON c.id=t.conversation_id AND c.channel='feishu'
            JOIN business.inbox_events i ON i.task_id=t.id AND i.source='feishu_business'
            JOIN business.p4_inbox_receipts r ON r.inbox_id=i.id
            WHERE t.organization_id=%s AND t.shop_id=%s AND t.id=ANY(%s)
            AND t.kind='inventory_replenishment'
            AND t.workflow_version='p3-inventory-replenishment-v1'
            AND i.sanitized_payload->>'event_type'='im.message.receive_v1'
            AND r.created_at>=%s""",
            (window.organization_id, window.shop_id, list(window.task_ids), row["occurred_at"]),
        )
        tasks = await cursor.fetchall()
        if frozenset(task["id"] for task in tasks) != window.task_ids or any(
            task["parameters"] != gateway.parameters.model_dump(mode="json") for task in tasks
        ):
            raise PermissionError("P4_CONTROLLED_TASK_SCOPE_REQUIRED")
        cursor = await db.execute(
            """SELECT 1 FROM business.p4_base_deliveries WHERE task_id=ANY(%s)
            AND verification_mode<>'controlled_sdk'
            UNION ALL SELECT 1 FROM business.p4_im_deliveries WHERE task_id=ANY(%s)
            AND verification_mode<>'controlled_sdk' LIMIT 1""",
            (list(window.task_ids), list(window.task_ids)),
        )
        if await cursor.fetchone():
            raise PermissionError("P4_CONTROLLED_FAKE_HISTORY_DENIED")


async def controlled_work(
    settings: BusinessSettings,
    window: ControlledWorkerWindow,
    config: WebConfig,
    collector: CollectorFactory,
) -> dict[str, Any]:
    sdk_window = window.window(settings)
    if config.database.user != "commerceops_app":
        raise PermissionError("P4_CONTROLLED_RUNTIME_ROLE_REQUIRED")
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop.set)
    timer = loop.call_later(
        max(0, (window.expires_at - datetime.now(UTC)).total_seconds() - 15), stop.set
    )
    session = WorkerSession(config.database, settings.organization_id)
    running = False
    summary: dict[str, Any] = {"result": "failed", "method_counts": "not_verified"}
    try:
        await session.start()
        await trusted_scope(config, settings, window)
        ledger = PersistentSDKLedger(session, sdk_window)
        factory = BusinessSDKFactory(settings, ledger)
        app_token, table_id, field_count = await verified_target(factory)
        client = factory.business_client()
        gate = DeliveryGate(
            window.organization_id,
            window.shop_id,
            window.task_ids,
            settings.base_target_key,
            window.expires_at,
            enabled=True,
            verification_mode="controlled_sdk",
        )
        im = IMDeliveryStore(
            session,
            config,
            settings.policy(),
            BusinessIMSDK(client, option=factory.option),
            gate,
            ledger,
        )
        base = BaseDeliveryStore(
            session,
            BusinessBaseAdapter(
                BusinessRecordSDK(client, option=factory.option),
                {settings.base_target_key: (app_token, table_id)},
            ),
            gate,
            ledger,
        )
        approval = ApprovalRunner(ApprovalStore(config, session), collector_factory=collector)
        provider = ProviderFactory()
        runner = InventoryCompositeRunner(
            InventoryRunner(InventoryStore(config.database, session), collector),
            ExplanationRunner(ExplanationStore(config.database, session), provider),
            IntentRunner(IntentStore(config.database, session), provider),
            approval,
        )

        async def maintenance() -> None:
            await approval.reconcile()
            if stop.is_set() or not gate.active():
                stop.set()
                return
            for store, accepted in ((im, {"idle", "sent"}), (base, {"idle", "verified"})):
                outcome = await store.dispatch_one()
                if outcome not in accepted:
                    summary["delivery_stopped"] = True
                    stop.set()
                    return

        summary.update({"target_unique": True, "field_count": field_count})
        running = True
        await Worker(
            session,
            runner,
            reconcile=maintenance,
            recovery_scan_seconds=config.recovery_scan_seconds,
        ).run(stop)
        summary["result"] = (
            "delivery_stopped" if summary.get("delivery_stopped") else "window_stopped"
        )
    except UnsafeShutdown:
        os._exit(75)  # 原非合作Graph取消合同；不伪造clean stop。
    except Exception as error:
        summary["failure_category"] = type(error).__name__
    finally:
        timer.cancel()
        if not running:
            await session.close(clean=True)  # 装配失败尚未执行Graph/Worker。
        async with await open_async(config.database) as db:
            cursor = await db.execute(
                """SELECT method,status,http_status,provider_code,count(*) AS n
                FROM business.p4_sdk_calls WHERE window_id=%s
                GROUP BY method,status,http_status,provider_code ORDER BY method,status""",
                (window.window_id,),
            )
            summary["method_counts"] = await cursor.fetchall()
    summary["model_requests"] = 0
    summary["verification_mode"] = "controlled_sdk"
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Bounded controlled Feishu SDK Worker")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--window-file", required=True, type=Path)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    try:
        restrict_sdk_logs()
        if not args.live or os.environ.get("COMMERCEOPS_MODE") != "p4-controlled-test":
            raise PermissionError("P4_CONTROLLED_TEST_MODE_REQUIRED")
        settings = BusinessSettings.model_validate_json(private_value(args.config))
        window = ControlledWorkerWindow.model_validate_json(private_value(args.window_file))
        window.window(settings)
        config = WebConfig.from_file(settings.web_config_file)
        # 明确Mock/test部署才使用原已审20+known70测试fixture；不成为生产资料来源。
        from tests.p4_demo_factory import M1DemoFactory

        result = asyncio.run(controlled_work(settings, window, config, M1DemoFactory()))
        print(json.dumps(result, sort_keys=True))
        if result["result"] != "window_stopped":
            raise SystemExit(1)
    except Exception:
        raise SystemExit("P4_CONTROLLED_WORKER_FAILED") from None


if __name__ == "__main__":
    main()
