"""同active Gateway内P4原T1/完整group20/真实kill+单Graph恢复，SDK/真人0。"""

import asyncio
import json
from uuid import UUID, uuid4

import pytest
from commerceops.adapters.feishu.business_gateway import BusinessCard
from commerceops.application.feishu_business.worker_window import (
    GROUP20_CAPS,
    ControlledWorkerWindow,
)
from commerceops.application.replenishment.contracts import DecisionInput, WebFailure
from commerceops.infrastructure.approval_decisions import nonce_for
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_gateway_window import guard_gateway
from commerceops.infrastructure.worker_lock import confirm_termination

from tests.p3_support import P3Fixture, P3Process
from tests.p4_recovery_support import gateway, settings, start_gateway, stop_gateway
from tests.test_p3_approval_pg import checkpoint_state, wait_ready, wait_state
from tests.test_p3_execution_recovery_pg import wait_jobs
from tests.test_p3_pg import fixture as fixture
from tests.test_p4_gateway_pg import message, service

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "barrier",
    ["before_t2_commit", "after_t2_commit", "after_ready", "before_t4_commit", "after_t4_commit"],
)
def test_same_active_gateway_original_plan_ttl_and_scoped_graph_kill_restore(
    fixture: P3Fixture,
    barrier: str,
) -> None:
    f = fixture
    original = gateway(f, case="baseline", seconds=240, max_workflows=2)
    gateway_child = start_gateway(f, original)
    child = restored = None
    try:
        store = service(
            f,
            allow_live_bindings=True,
            gateway_guard=lambda db, create: guard_gateway(db, original, create),
        )
        incoming = message(f, kind="group")
        task = UUID(store.message(incoming)["task_id"])
        window = ControlledWorkerWindow.model_validate_json(
            json.dumps(
                {
                    "schema_version": "p4-worker-v1",
                    "window_id": str(uuid4()),
                    "gateway_window_id": str(original.window_id),
                    "organization_id": str(f.actor.organization_id),
                    "shop_id": str(f.inventory.data.shop),
                    "task_ids": [str(task)],
                    "expires_at": original.expires_at.isoformat(),
                    "enabled": True,
                    "profile": "group20",
                    "caps": dict(GROUP20_CAPS),
                }
            )
        )
        scoped = {
            "task_id": str(task),
            "p4_demo": True,
            "p4_scope": {
                "window": window.model_dump(mode="json"),
                "settings": settings(f).model_dump(mode="json"),
            },
        }
        child = P3Process(f, "worker", scoped, barrier)
        owner = child.until("started")["owner"]
        before = None
        if barrier in ("before_t4_commit", "after_t4_commit"):
            child.until("after_ready")
            card, before = ready_card(f, task, incoming)
            assert store.card(card)["decision_source"] == "feishu"
        child.until(barrier)
        if barrier == "after_t2_commit":
            card, before = ready_card(f, task, incoming)
            with pytest.raises(WebFailure, match="CARD_CONTEXT_MISMATCH"):
                store.card(card)
            with connect(f.config.database) as db:
                assert db.execute(
                    "SELECT count(*) AS n FROM business.approval_resumes WHERE task_id=%s", (task,)
                ).fetchone() == {"n": 0}
        elif barrier == "after_ready":
            _, before = ready_card(f, task, incoming)
        child.kill_reap()
        blocked = P3Process(f, "worker", scoped, "never")
        assert blocked.until("blocked")["category"] == "TerminationRequired"
        blocked.close_exited(2)
        asyncio.run(
            confirm_termination(
                f.config.database, owner, "A08 original owned Worker SIGKILL/wait=-9"
            )
        )
        with connect(f.config.database) as db:
            committed = barrier == "after_t4_commit"
            assert db.execute(
                "SELECT count(*) AS n FROM business.executions WHERE task_id=%s", (task,)
            ).fetchone() == {"n": int(committed)}
            assert db.execute(
                "SELECT count(*) AS n FROM business.replenishment_items WHERE task_id=%s", (task,)
            ).fetchone() == {"n": 20 * int(committed)}
        restored = P3Process(f, "worker", scoped, "never")
        restored.until("started")
        if barrier not in ("before_t4_commit", "after_t4_commit"):
            wait_ready(f, task)  # 原waiting CP重入可直接返回interrupted，无新after_ready hook。
            card, current = ready_card(f, task, incoming)
            if before:
                assert current == before  # 原plan/approval/hash/nonce/expiry，无TTL更新。
            assert store.card(card)["decision_source"] == "feishu"
        wait_state(f, task, "completed", restoring=True)
        wait_jobs(f, task)
        snapshot = asyncio.run(checkpoint_state(f, task))
        assert snapshot.next == () and not snapshot.interrupts
        with connect(f.config.database) as db:
            assert db.execute(
                "SELECT count(*) AS n FROM business.replenishment_plans WHERE task_id=%s", (task,)
            ).fetchone() == {"n": 1}
            assert db.execute(
                "SELECT count(*) AS n FROM business.executions WHERE task_id=%s", (task,)
            ).fetchone() == {"n": 1}
            items = db.execute(
                "SELECT id,quantity FROM business.replenishment_items WHERE task_id=%s", (task,)
            ).fetchall()
            assert len(items) == 20 and all(int(i["quantity"]) == 100 for i in items)
            assert db.execute(
                "SELECT count(*) AS n FROM business.outbox WHERE task_id=%s "
                "AND operation='item_projection'",
                (task,),
            ).fetchone() == {"n": 20}
            assert db.execute("SELECT count(*) AS n FROM business.p4_sdk_calls").fetchone() == {
                "n": 0
            }
    finally:
        if child and child.process.poll() is None:
            child.kill_reap()
        if restored and restored.process.poll() is None:
            restored.stop_clean()
        stop_gateway(f, original, gateway_child)


def ready_card(
    f: P3Fixture, task: UUID, incoming: object
) -> tuple[BusinessCard, dict[str, object]]:
    from commerceops.adapters.feishu.contracts import MessageProbe

    assert isinstance(incoming, MessageProbe)
    with connect(f.config.database) as db:
        approval = db.execute(
            "SELECT * FROM business.approvals WHERE task_id=%s", (task,)
        ).fetchone()
        assert approval
        plan = db.execute(
            "SELECT content FROM business.replenishment_plans WHERE id=%s", (approval["plan_id"],)
        ).fetchone()
        outbox = db.execute(
            "SELECT id FROM business.outbox WHERE aggregate_id=%s", (approval["id"],)
        ).fetchone()
        assert plan and outbox
        db.execute(
            """INSERT INTO business.p4_card_bindings
        (approval_id,outbox_id,chat_id,message_id,source_mode)
        VALUES(%s,%s,%s,'synthetic-recovery-card','feishu') ON CONFLICT DO NOTHING""",
            (approval["id"], outbox["id"], incoming.chat_id),
        )
    request = DecisionInput.model_validate(
        dict(
            schema_version="p3-web-v1",
            request_key=uuid4(),
            approval_id=approval["id"],
            plan_id=approval["plan_id"],
            plan_version=approval["plan_version"],
            plan_hash=approval["plan_hash"],
            action="approve_with_assumptions",
            nonce=nonce_for(f.config, approval),
            acknowledged_assumption_keys=tuple(
                a["key"] for a in plan["content"]["required_assumptions"]
            ),
        )
    )
    frozen = {
        key: approval[key]
        for key in ("id", "plan_id", "plan_version", "plan_hash", "nonce_hash", "expires_at")
    }
    return BusinessCard(
        "event-" + uuid4().hex,
        incoming.identity,
        incoming.chat_id,
        "synthetic-recovery-card",
        request,
    ), frozen
