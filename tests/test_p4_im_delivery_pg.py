"""A04待独审后自有PG：单Worker正式Card/result伴随意图，SDK/Fake平台0。"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from commerceops.adapters.feishu.business_gateway import BusinessCard
from commerceops.application.feishu_business.clarification import NoticeResult
from commerceops.application.feishu_business.delivery import DeliveryGate
from commerceops.application.feishu_business.im_delivery import BusinessMessage
from commerceops.application.replenishment.contracts import DecisionInput
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_im_delivery import IMDeliveryStore
from commerceops.infrastructure.inventory_repository import InventoryStore
from commerceops.infrastructure.replenishment_repository import ApprovalStore
from commerceops.infrastructure.worker import Worker
from commerceops.infrastructure.worker_lock import WorkerSession
from commerceops.workflows.inventory_analysis import InventoryRunner, MockCollectorFactory
from commerceops.workflows.replenishment import ApprovalRunner

from tests.inventory_support import DIRECTORY
from tests.p3_support import P3Fixture
from tests.test_p3_approval_pg import payload
from tests.test_p3_pg import fixture as fixture
from tests.test_p4_clarification_pg import policy
from tests.test_p4_gateway_pg import message, service

pytestmark = pytest.mark.integration


class Sender:
    def __init__(self, *, unknown: bool = False):
        self.unknown = unknown
        self.calls: list[BusinessMessage] = []

    async def send_message(self, request: BusinessMessage) -> NoticeResult:
        self.calls.append(request)
        return (
            NoticeResult(outcome="unknown", code="ACK_UNPROVEN")
            if self.unknown
            else NoticeResult(
                outcome="sent", code="FAKE_ACK", message_id="synthetic-" + request.outbox_id.hex
            )
        )


@pytest.mark.parametrize("unknown", [False, True])
def test_existing_single_worker_card_binding_and_fixed_result_or_unknown_hold(
    fixture: P3Fixture, unknown: bool
) -> None:
    f = fixture
    gateway = service(f)
    incoming = message(f)
    task = UUID(gateway.message(incoming)["task_id"])
    sender = Sender(unknown=unknown)

    async def run() -> None:
        session = WorkerSession(f.config.database, f.actor.organization_id)
        await session.start()
        analysis = InventoryRunner(
            InventoryStore(f.config.database, session), MockCollectorFactory(DIRECTORY)
        )
        approval = ApprovalRunner(
            ApprovalStore(f.config, session), collector_factory=MockCollectorFactory(DIRECTORY)
        )
        im = IMDeliveryStore(
            session,
            f.config,
            policy(f),
            sender,
            DeliveryGate(
                f.actor.organization_id,
                f.inventory.data.shop,
                frozenset({task}),
                "synthetic",
                datetime.now(UTC) + timedelta(minutes=3),
                enabled=True,
            ),
        )

        class Router:
            workflow_versions = analysis.workflow_versions | approval.workflow_versions

            async def run(self, request: Any) -> Any:
                return await (
                    approval if request.workflow_version in approval.workflow_versions else analysis
                ).run(request)

        stop = asyncio.Event()
        worker = asyncio.create_task(
            Worker(
                session,
                Router(),
                reconcile=im.reconcile,
                heartbeat_seconds=0.1,
                poll_seconds=0.02,
                recovery_scan_seconds=1,
            ).run(stop)
        )
        try:
            for _ in range(600):
                if sender.calls:
                    break
                if worker.done():
                    worker.result()
                    raise AssertionError("owned worker stopped before card")
                await asyncio.sleep(0.02)
            assert len(sender.calls) == 1 and sender.calls[0].kind == "interactive"
            if unknown:
                for _ in range(10):
                    await im.reconcile()
                assert len(sender.calls) == 1
                with connect(f.config.database) as db:
                    assert db.execute(
                        "SELECT count(*) AS n FROM business.p4_card_bindings"
                    ).fetchone() == {"n": 0}
                    assert db.execute(
                        "SELECT count(*) AS n FROM business.executions"
                    ).fetchone() == {"n": 0}
                return
            request = DecisionInput.model_validate_json(json.dumps(payload(f, task)))
            gateway.card(
                BusinessCard(
                    "synthetic-event-card",
                    incoming.identity,
                    incoming.chat_id,
                    "synthetic-" + sender.calls[0].outbox_id.hex,
                    request,
                )
            )
            for _ in range(600):
                if len(sender.calls) == 2:
                    break
                if worker.done():
                    worker.result()
                    raise AssertionError("owned worker stopped before result")
                await asyncio.sleep(0.02)
            assert len(sender.calls) == 2 and sender.calls[1].kind == "text"
            assert "completed" in (sender.calls[1].text or "") and str(task) in (
                sender.calls[1].text or ""
            )
            with connect(f.config.database) as db:
                assert db.execute("SELECT count(*) AS n FROM business.executions").fetchone() == {
                    "n": 1
                }
                assert db.execute(
                    "SELECT count(*) AS n FROM business.p4_im_deliveries WHERE status='sent'"
                ).fetchone() == {"n": 2}
                assert db.execute(
                    "SELECT count(*) AS n FROM business.p4_card_bindings"
                ).fetchone() == {"n": 1}
        finally:
            stop.set()
            await worker

    asyncio.run(run())
