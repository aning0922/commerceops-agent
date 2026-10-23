"""新owned原queued流水线与已核v1；只Fake外HTTP及明确合成审批人。"""

import asyncio
import time
from typing import Any
from uuid import uuid4

from commerceops.adapters.feishu.business_gateway import BusinessCard
from commerceops.application.replenishment.contracts import DecisionInput
from commerceops.infrastructure.approval_decisions import nonce_for
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_gateway_window import guard_gateway
from commerceops.infrastructure.feishu_queued_start import claim_queued_attempt

from tests.p4_acceptance_support import AcceptanceFixture, worker_request
from tests.p4_queued_support import prepare, start_ready, stop_ready
from tests.test_p4_gateway_pg import message, service


def verified_queued_origin(a: AcceptanceFixture) -> dict[str, Any]:
    f = a.fixture
    business, gateway, window = prepare(f)
    a.business = business.model_copy(
        update={
            "app_secret_file": a.business.app_secret_file,
            "base_app_token_file": a.business.base_app_token_file,
        }
    )
    asyncio.run(claim_queued_attempt(f.config, a.business, window, gateway))
    child, _ = start_ready(f, a.business, gateway)
    worker = None
    a.external_behavior("normal")
    try:
        worker = a.start(worker_request(f.config, a.business, window, f.private, a.external))
        r = window.queued_start
        assert r is not None
        end = time.monotonic() + min(80, a.deadline.remaining())
        while True:
            with connect(f.config.database) as db:
                approval = db.execute(
                    "SELECT * FROM business.approvals WHERE task_id=%s", (r.task_id,)
                ).fetchone()
                binding = (
                    None
                    if not approval
                    else db.execute(
                        "SELECT message_id,chat_id FROM business.p4_card_bindings "
                        "WHERE approval_id=%s",
                        (approval["id"],),
                    ).fetchone()
                )
                plan = (
                    None
                    if not approval
                    else db.execute(
                        "SELECT content FROM business.replenishment_plans WHERE id=%s",
                        (approval["plan_id"],),
                    ).fetchone()
                )
            if approval and approval["ready_at"] and binding and plan:
                break
            assert worker.process.poll() is None and time.monotonic() < end
            time.sleep(0.05)
        intake = service(
            f,
            "known_inbound",
            allow_live_bindings=True,
            gateway_guard=lambda db, create: guard_gateway(db, gateway, create),
        )
        decision = DecisionInput.model_validate(
            dict(
                schema_version="p3-web-v1",
                request_key=uuid4(),
                approval_id=approval["id"],
                plan_id=approval["plan_id"],
                plan_version=approval["plan_version"],
                plan_hash=approval["plan_hash"],
                nonce=nonce_for(f.config, approval),
                action="approve_with_assumptions"
                if plan["content"]["required_assumptions"]
                else "approve",
                acknowledged_assumption_keys=tuple(
                    x["key"] for x in plan["content"]["required_assumptions"]
                ),
            )
        )
        intake.card(
            BusinessCard(
                "synthetic-" + uuid4().hex,
                message(f).identity,
                binding["chat_id"],
                binding["message_id"],
                decision,
            )
        )
        while True:
            with connect(f.config.database) as db:
                deliveries = db.execute(
                    "SELECT d.*,o.request_hash FROM business.p4_base_deliveries d "
                    "JOIN business.outbox o ON o.id=d.outbox_id WHERE d.task_id=%s",
                    (r.task_id,),
                ).fetchall()
            if len(deliveries) == 1 and deliveries[0]["status"] == "verified":
                break
            assert worker.process.poll() is None and time.monotonic() < end
            time.sleep(0.05)
        worker.process.terminate()
        result = worker.wait(timeout=min(30, a.deadline.remaining()))
        a.confirm_worker(worker, result)
        assert result["exit_code"] == 0
        assert deliveries[0]["attempts"] == 1
        return dict(
            window=window,
            gateway=gateway,
            delivery=deliveries[0],
            owner=result["pg_proof"]["worker_owner"],
        )
    finally:
        if worker is not None and worker.process.poll() is None:
            worker.terminate()
        stop_ready(f, gateway, child)
