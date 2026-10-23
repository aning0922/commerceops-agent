"""P1原受控scope贯穿真实PG队列/维护/Graph；窗口外canonical rows不变。"""

import asyncio
import json
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from commerceops.application.feishu_business.worker_window import (
    GROUP20_CAPS,
    ControlledWorkerWindow,
)
from commerceops.entrypoints.feishu_business import confirm_worker_child
from commerceops.entrypoints.feishu_worker_child import controlled_task_ids, trusted_scope
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_gateway_window import claim_gateway, guard_gateway
from commerceops.infrastructure.inventory_repository import InventoryStore
from commerceops.infrastructure.replenishment_repository import ApprovalStore
from commerceops.infrastructure.worker import Worker
from commerceops.infrastructure.worker_lock import WorkerSession
from commerceops.workflows.inventory_analysis import InventoryRunner
from commerceops.workflows.replenishment import ApprovalRunner
from psycopg import sql

from tests.p3_support import P3Fixture, P3Process
from tests.p4_demo_factory import M1DemoFactory
from tests.p4_recovery_support import gateway, settings
from tests.test_p3_pg import fixture as fixture
from tests.test_p4_gateway_pg import message, service

pytestmark = pytest.mark.integration


def waiting(f: P3Fixture, ttl: int) -> tuple[UUID, UUID]:
    configuration = json.loads(f.config_file.read_text())
    configuration["approval_ttl_seconds"] = ttl
    f.config_file.write_text(json.dumps(configuration))
    f.config_file.chmod(0o600)
    task = UUID(f.create(f.new_cycle())["task_id"])
    child = P3Process(f, "worker", {"task_id": str(task)}, "never")
    try:
        owner = UUID(child.until("started")["owner"])
        child.until("after_ready")
    finally:
        if child.process.poll() is None:
            child.stop_clean()
    asyncio.run(confirm_worker_child(f.config, f.actor.organization_id, child.process.pid))
    return task, owner


def seed_outside_jobs(f: P3Fixture, owner: UUID, conversation: UUID) -> list[UUID]:
    with connect(f.inventory.owner) as db:
        other_shop = uuid4()
        db.execute(
            """INSERT INTO business.shops(id,organization_id,adapter_kind,
        external_shop_key,timezone,currency,config_ref,environment)
        VALUES(%s,%s,'mock','scope-other','Asia/Shanghai','CNY','synthetic-scope','test')""",
            (other_shop, f.actor.organization_id),
        )
        tasks = []
        for shop, status in (
            (f.inventory.data.shop, "ready"),
            (f.inventory.data.shop, "retry_wait"),
            (f.inventory.data.shop, "running"),
            (other_shop, "ready"),
            (other_shop, "retry_wait"),
            (other_shop, "running"),
        ):
            task, job = uuid4(), uuid4()
            tasks.append(task)
            db.execute(
                """INSERT INTO business.business_tasks(id,organization_id,shop_id,
            conversation_id,requester_id,kind,normalized_request,workflow_version,thread_id)
            VALUES(%s,%s,%s,%s,%s,'technical_test','{"schema_version":"synthetic"}',
            'synthetic-scope-v1',%s)""",
                (
                    task,
                    f.actor.organization_id,
                    shop,
                    conversation,
                    f.actor.principal_id,
                    str(task),
                ),
            )
            db.execute(
                """INSERT INTO business.jobs(id,organization_id,shop_id,task_id,kind,
            dedupe_key,payload_ref,status,attempts,available_at,lease_owner,lease_until)
            VALUES(%s,%s,%s,%s,'analyze',%s,%s,%s,7,clock_timestamp()-interval '1 hour',%s,%s)""",
                (
                    job,
                    f.actor.organization_id,
                    shop,
                    task,
                    "outside:" + str(job),
                    "task:" + str(task),
                    status,
                    str(owner) if status == "running" else None,
                    datetime.now(UTC) if status == "running" else None,
                ),
            )
    return tasks


def outside_bytes(f: P3Fixture, tasks: list[UUID]) -> dict[str, Any]:
    with connect(f.config.database) as db:
        result = {}
        for table, column in (
            ("business_tasks", "id"),
            ("jobs", "task_id"),
            ("replenishment_plans", "task_id"),
            ("approvals", "task_id"),
            ("outbox", "task_id"),
        ):
            result[table] = db.execute(
                sql.SQL(
                    "SELECT row_to_json(t)::text AS canonical FROM "
                    "business.{} t WHERE {}=ANY(%s) ORDER BY id"
                ).format(sql.Identifier(table), sql.Identifier(column)),
                (tasks,),
            ).fetchall()
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            result[table] = db.execute(
                sql.SQL(
                    "SELECT row_to_json(t)::text AS canonical FROM "
                    "checkpoints.{} t WHERE thread_id=ANY(%s) ORDER BY row_to_json(t)::text"
                ).format(sql.Identifier(table)),
                ([str(t) for t in tasks],),
            ).fetchall()
        result["checkpoint_migrations"] = db.execute(
            "SELECT row_to_json(t)::text AS canonical FROM checkpoints.checkpoint_migrations t "
            "ORDER BY row_to_json(t)::text"
        ).fetchall()
        return result


def test_scoped_worker_preserves_outside_jobs_tasks_approvals_and_checkpoint_bytes(
    fixture: P3Fixture,
) -> None:
    f = fixture
    expired, _ = waiting(f, 60)
    pending, owner = waiting(f, 86400)
    with connect(f.config.database) as db:
        expiry = db.execute(
            "SELECT expires_at FROM business.approvals WHERE task_id=%s", (expired,)
        ).fetchone()
        conversation = db.execute(
            "SELECT conversation_id FROM business.business_tasks WHERE id=%s", (pending,)
        ).fetchone()
        assert expiry and conversation
        sources = [
            r["source_task_id"]
            for r in db.execute(
                "SELECT source_task_id FROM business.p3_task_sources WHERE task_id=ANY(%s)",
                ([expired, pending],),
            ).fetchall()
        ]
    outside = [
        expired,
        pending,
        *sources,
        *seed_outside_jobs(f, owner, conversation["conversation_id"]),
    ]
    # 原真实冻结approval TTL，等DB时钟越界；不UPDATE plan/nonce/expiry造过期。
    deadline = time.monotonic() + 65
    while datetime.now(UTC) < expiry["expires_at"]:
        assert time.monotonic() < deadline
        time.sleep(0.05)
    settings_value = settings(f)
    original = gateway(f, case="baseline", max_workflows=2)
    with connect(f.config.database) as lease:
        claim_gateway(lease, settings_value, original)
        service_value = service(
            f, gateway_guard=lambda db, create: guard_gateway(db, original, create)
        )
        task = UUID(service_value.message(message(f, kind="group"))["task_id"])
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
                    "caps": dict(GROUP20_CAPS),
                    "profile": "group20",
                }
            )
        )
        asyncio.run(trusted_scope(f.config, settings_value, window))
        authorized = asyncio.run(controlled_task_ids(f.config, window))
        assert len(authorized) == 2 and task in authorized and authorized.isdisjoint(outside)
        before = outside_bytes(f, outside)

        async def run() -> None:
            session = WorkerSession(f.config.database, f.actor.organization_id)
            await session.start()
            analysis = InventoryRunner(InventoryStore(f.config.database, session), M1DemoFactory())
            approval = ApprovalRunner(
                ApprovalStore(f.config, session), collector_factory=M1DemoFactory()
            )

            class Router:
                workflow_versions = analysis.workflow_versions | approval.workflow_versions

                async def run(self, request: Any) -> Any:
                    assert request.task_id in authorized
                    return await (
                        approval
                        if request.workflow_version in approval.workflow_versions
                        else analysis
                    ).run(request)

            stop = asyncio.Event()

            async def maintenance() -> None:
                await approval.reconcile(task_ids=window.task_ids)
                with connect(f.config.database) as db:
                    row = db.execute(
                        "SELECT state FROM business.business_tasks WHERE id=%s", (task,)
                    ).fetchone()
                    assert row
                    if row["state"] == "awaiting_approval":
                        stop.set()

            worker = asyncio.create_task(
                Worker(
                    session,
                    Router(),
                    task_ids=authorized,
                    reconcile=maintenance,
                    poll_seconds=0.02,
                    heartbeat_seconds=0.1,
                    recovery_scan_seconds=1,
                ).run(stop)
            )
            try:
                await asyncio.wait_for(asyncio.shield(worker), 20)
            finally:
                stop.set()
                await worker

        asyncio.run(run())
        assert outside_bytes(f, outside) == before
        with connect(f.config.database) as db:
            assert db.execute(
                "SELECT state FROM business.business_tasks WHERE id=%s", (task,)
            ).fetchone() == {"state": "awaiting_approval"}
            assert db.execute("SELECT count(*) AS n FROM business.p4_sdk_calls").fetchone() == {
                "n": 0
            }
            assert db.execute(
                "SELECT status FROM business.approvals WHERE task_id=%s", (expired,)
            ).fetchone() == {"status": "pending"}
