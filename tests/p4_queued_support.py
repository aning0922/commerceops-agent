"""New owned original T1 and native transport-ready Gateway; no business/permission mocks."""

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.application.feishu_business.worker_window import (
    KNOWN70_CAPS,
    ControlledWorkerWindow,
)
from commerceops.domain.commerce_values import facts_hash
from commerceops.entrypoints.feishu_business import confirm_gateway_child
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_gateway_window import guard_gateway
from commerceops.infrastructure.feishu_outbox_recovery import receipt_hash
from commerceops.infrastructure.feishu_queued_start import original_jobs_hash, original_task_hash
from commerceops.infrastructure.feishu_workflow_recovery import task_binding_hash

from tests.p3_support import P3Fixture
from tests.p4_recovery_support import gateway, settings, start_gateway, stop_gateway, write_private
from tests.test_p4_gateway_pg import message, service


def prepare(f: P3Fixture) -> tuple[BusinessSettings, Any, ControlledWorkerWindow]:
    business = settings(f).model_copy(
        update={
            "allowed_open_ids": frozenset({"p4-synthetic-user"}),
            "allowed_group_chat_ids": frozenset(),
        }
    )
    secret = f.private / "queued-dummy-material"
    secret.write_text("offline-material")
    secret.chmod(0o600)
    business = business.model_copy(update={"app_secret_file": secret})
    old = gateway(f, case="known_inbound", seconds=300, max_workflows=1)
    child = start_gateway(f, old)
    try:
        store = service(
            f,
            "known_inbound",
            allow_live_bindings=True,
            gateway_guard=lambda db, create: guard_gateway(db, old, create),
        )
        task = UUID(store.message(message(f))["task_id"])
    finally:
        stop_gateway(f, old, child)
    new = gateway(f, case="known_inbound", seconds=300, max_workflows=0)
    with connect(f.config.database) as db:
        task_row = db.execute(
            "SELECT t.*,s.source_task_id,s.parameters,s.config_version FROM "
            "business.business_tasks t JOIN business.p3_task_sources s ON "
            "s.task_id=t.id WHERE t.id=%s",
            (task,),
        ).fetchone()
        assert task_row
        source = db.execute(
            "SELECT * FROM business.business_tasks WHERE id=%s", (task_row["source_task_id"],)
        ).fetchone()
        jobs = db.execute(
            "SELECT * FROM business.jobs WHERE task_id=ANY(%s) ORDER BY id",
            ([task, task_row["source_task_id"]],),
        ).fetchall()
        receipt = db.execute(
            "SELECT r.*,i.payload_hash FROM business.p4_inbox_receipts r JOIN "
            "business.inbox_events i ON i.id=r.inbox_id WHERE i.task_id=%s",
            (task,),
        ).fetchone()
        claim = db.execute(
            "SELECT after_state FROM business.audit_events WHERE id=%s", (old.window_id,)
        ).fetchone()
        end = db.execute(
            "SELECT id FROM business.audit_events WHERE source='feishu_gateway' AND "
            "action='termination_confirmed' AND entity_id=%s",
            (str(old.window_id),),
        ).fetchone()
        principal = db.execute(
            "SELECT auth_version FROM business.principals WHERE id=%s", (f.actor.principal_id,)
        ).fetchone()
        assert source and receipt and claim and end and principal and len(jobs) == 2
    worker = uuid4()
    window = ControlledWorkerWindow.model_validate_json(
        json.dumps(
            dict(
                schema_version="p4-worker-v1",
                window_id=str(worker),
                gateway_window_id=str(new.window_id),
                organization_id=str(business.organization_id),
                shop_id=str(business.shop_id),
                task_ids=[str(task)],
                expires_at=new.expires_at.isoformat(),
                enabled=True,
                profile="approved_queued_start",
                caps=dict(KNOWN70_CAPS),
                queued_start=dict(
                    schema_version="p4-approved-queued-start-v1",
                    worker_window_id=str(worker),
                    gateway_window_id=str(new.window_id),
                    expires_at=new.expires_at.isoformat(),
                    original_gateway_id=str(old.window_id),
                    original_gateway_hash=facts_hash(claim["after_state"]),
                    gateway_termination_id=str(end["id"]),
                    task_id=str(task),
                    source_task_id=str(task_row["source_task_id"]),
                    task_version=1,
                    task_binding_hash=task_binding_hash(task_row),
                    source_binding_hash=original_task_hash(source),
                    job_ids=[str(j["id"]) for j in jobs],
                    jobs_binding_hash=original_jobs_hash(jobs),
                    inbox_id=str(receipt["inbox_id"]),
                    receipt_hash=receipt_hash(receipt),
                    operator_auth_version=principal["auth_version"],
                    target_key=business.base_target_key,
                ),
            )
        )
    )
    return business, new, window


def start_ready(
    f: P3Fixture, business: BusinessSettings, window: Any
) -> tuple[subprocess.Popen[bytes], Path]:
    d = f.private / ("queued-gateway-" + uuid4().hex)
    d.mkdir(mode=0o700)
    config = d / "business.json"
    scope = d / "window.json"
    write_private(config, business.model_dump(mode="json"))
    write_private(scope, window.model_dump(mode="json"))
    stream = (d / "private.log").open("wb")
    (d / "private.log").chmod(0o600)
    child = subprocess.Popen(
        [sys.executable, "-m", "tests.p4_queued_gateway_process", str(config), str(scope), str(d)],
        stdout=stream,
        stderr=subprocess.STDOUT,
    )
    stream.close()
    try:
        end = time.monotonic() + 15
        while True:
            with connect(f.config.database) as db:
                n = db.execute(
                    "SELECT count(*) AS n FROM business.audit_events WHERE "
                    "source='feishu_gateway' AND action='ready' AND entity_id=%s",
                    (str(window.window_id),),
                ).fetchone()
            if n and n["n"] == 1:
                return child, d
            assert child.poll() is None and time.monotonic() < end
            time.sleep(0.03)
    except BaseException:
        stop_ready(f, window, child)
        raise


def stop_ready(f: P3Fixture, window: Any, child: subprocess.Popen[bytes]) -> None:
    if child.poll() is None:
        child.terminate()
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=5)
    asyncio.run(
        confirm_gateway_child(
            f.config, f.actor.organization_id, window.window_id, child.pid, child.returncode
        )
    )
