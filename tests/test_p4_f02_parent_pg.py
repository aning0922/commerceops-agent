"""真实生成disabled F02输入→同parent/child/低权Gateway与SQL；仅HTTP Fake。"""

import json
import os
import signal
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from commerceops.application.feishu_business.f02_window import F02WorkerWindow
from commerceops.application.feishu_business.gateway_window import GatewayWindow
from commerceops.entrypoints.feishu_gateway_child import BoundedReceiver
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.feishu_business import FeishuBusinessStore
from commerceops.infrastructure.feishu_gateway_window import guard_gateway
from commerceops.infrastructure.web_sessions import json_native

from scripts.p4_acceptance import write_private
from tests.p3_support import initialize_p3
from tests.p4_parent_support import native_gateway, prepare_parent
from tests.test_p4_acceptance_pg import database as database
from tests.test_p4_acceptance_pg import initialize_schema
from tests.test_p4_clarification_pg import business_counts
from tests.test_p4_f02_pg import checkpoints, incoming, request_row, turn
from tests.test_p4_gateway_pg import service

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("outcome", ["sent", "unknown"])
def test_disabled_F02_template_native_parent_rounds_confirm_cold_stop_and_no_graph(
    database: tuple[DatabaseSettings, DatabaseSettings], tmp_path: Path, outcome: str
) -> None:
    owner, app = database
    initialize_schema(owner, "0016")
    f = initialize_p3(owner, app, tmp_path)
    try:
        original = service(f)
        gateway = GatewayWindow(
            schema_version="p4-gateway-v1",
            window_id=uuid4(),
            organization_id=f.actor.organization_id,
            shop_id=f.inventory.data.shop,
            expires_at=datetime.now(UTC) + timedelta(seconds=120),
            enabled=True,
            parameters=original.parameters,
            max_workflows=1,
            max_callbacks=20,
        )
        disabled = F02WorkerWindow(
            schema_version="p4-f02-worker-window-v1",
            window_id=uuid4(),
            gateway_window_id=gateway.window_id,
            organization_id=gateway.organization_id,
            shop_id=gateway.shop_id,
            expires_at=gateway.expires_at,
            method_caps={
                "auth.v3.tenant_access_token.internal": 1,
                "bot.v3.info": 1,
                "im.v1.message.create": 3,
            },
        ).model_dump(mode="json")
        assert "request_id" not in disabled and "reply_id" not in disabled
        inputs = prepare_parent(
            f,
            disabled,
            mode="f02_clarification",
            behavior="im_timeout" if outcome == "unknown" else "normal",
        )
        assert inputs.run("disabled", disabled=True)[0] == 1
        s = FeishuBusinessStore(
            original.store,
            original.shop,
            original.parameters,
            f02_enabled=True,
            f02_gateway_window_id=gateway.window_id,
            gateway_guard=lambda db, create: guard_gateway(db, gateway, create),
        )
        receiver = BoundedReceiver(s, gateway)
        before, cp = business_counts(f), checkpoints(f)
        with native_gateway(f, inputs, gateway.model_dump(mode="json")):
            first_message = incoming(f, "分析库存 L=3")
            first = receiver.message(first_message)
            assert "task_id" not in first and "source_task_id" not in first
            assert business_counts(f) == before
            identifier = UUID(first["clarification_id"])

            def rows() -> list[dict[str, Any]]:
                with connect(app) as db:
                    return db.execute(
                        "SELECT * FROM business.p4_clarification_replies "
                        "WHERE request_id=%s ORDER BY created_at,id",
                        (identifier,),
                    ).fetchall()

            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(inputs.run, "first")

                def until(predicate: Any) -> None:
                    end = time.monotonic() + 25
                    while not predicate():
                        assert not future.done() and time.monotonic() < end
                        time.sleep(0.03)

                if outcome == "sent":
                    until(lambda: len([r for r in rows() if r["status"] == "sent"]) == 1)
                    ready = receiver.message(turn(f, first))
                    assert ready["clarification_state"] == "awaiting_confirmation"
                    assert business_counts(f) == before
                    until(lambda: len([r for r in rows() if r["status"] == "sent"]) == 2)
                    confirm_message = turn(f, ready, confirm=True)
                    confirmed = receiver.message(confirm_message)
                    assert confirmed["task_id"] and confirmed["source_task_id"]
                    for _ in range(10):
                        assert receiver.message(confirm_message) == {**confirmed, "duplicate": True}
                    code, result = future.result(timeout=30)
                    assert code == 0 and result["official_summary"]["sent"] == 3
                    assert request_row(f, str(identifier))["state"] == "consumed"
                    after = business_counts(f)
                    assert after["business_tasks"] - before["business_tasks"] == 2
                    assert after["jobs"] - before["jobs"] == 2
                    assert all(
                        after[k] == before[k] for k in before if k not in ("business_tasks", "jobs")
                    )
                else:
                    code, result = future.result(timeout=30)
                    assert code == 1 and result["official_summary"]["result"] == "delivery_stopped"
                    assert business_counts(f) == before
                assert result["child_reaped"] and result["lifecycle_termination_confirmed"]
                summary = result["official_summary"]
                assert (
                    summary["base_requests"]
                    == summary["business_graphs"]
                    == summary["model_requests"]
                    == 0
                )
                sent_rows = rows()
                assert len(sent_rows) == (3 if outcome == "sent" else 1)
                assert all(
                    r["status"] == ("sent" if outcome == "sent" else "unknown")
                    and r["attempts"] == 1
                    for r in sent_rows
                )
                bodies = [
                    json.loads(p.read_bytes()) for p in inputs.directory.glob("im-*.private.json")
                ]
                assert {b["uuid"] for b in bodies} == {str(r["provider_uuid"]) for r in sent_rows}
                with connect(app) as db:
                    calls = db.execute(
                        "SELECT * FROM business.p4_sdk_calls ORDER BY started_at,id"
                    ).fetchall()
                    started = db.execute(
                        "SELECT count(*) AS n FROM business.audit_events "
                        "WHERE source='worker' AND action='started'"
                    ).fetchone()
                assert len(calls) == (5 if outcome == "sent" else 3) and started
                # 同窗口/同request冷启动；由真实started回执后发送SIGTERM，验证原stop/reap链。
                future = pool.submit(inputs.run, "cold")

                def cold_started() -> bool:
                    with connect(app) as db:
                        current = db.execute(
                            "SELECT count(*) AS n FROM business.audit_events "
                            "WHERE source='worker' AND action='started'"
                        ).fetchone()
                    return bool(current and current["n"] == started["n"] + 1)

                until(cold_started)
                pid = json.loads((inputs.directory / "cold.spawn.safe.json").read_bytes())["PID"]
                os.kill(pid, signal.SIGTERM)
                cold_code, cold = future.result(timeout=15)
                assert cold_code == 0 and cold["forced_stop"] is True
                assert cold["child_reaped"] and cold["lifecycle_termination_confirmed"]
                with connect(app) as db:
                    assert (
                        db.execute(
                            "SELECT * FROM business.p4_sdk_calls ORDER BY started_at,id"
                        ).fetchall()
                        == calls
                    )
                assert rows() == sent_rows and checkpoints(f) == cp
                write_private(
                    inputs.directory / "verification.safe.json",
                    {
                        "outcome": outcome,
                        "SQL_real": True,
                        "SDK_Fake_HTTP_only": True,
                        "SDK_calls": len(calls),
                        "cold_SDK_delta": 0,
                        "business_graphs": 0,
                        "complete_confirmation_only_creates_original_T1_two_tasks_two_jobs": True,
                        "same_gateway_selected_request": True,
                        "native_reply_association": False,
                        "cold_real_SIGTERM_reap_termination_confirmed": True,
                    },
                )
        # 全部native writers（包括Gateway）退出后保存原生PG账本；不是另造observer。
        with connect(app) as db:
            db.execute("SET TRANSACTION READ ONLY")
            facts = {
                "database_UTC": db.execute("SELECT clock_timestamp() AS at").fetchone(),
                "request": db.execute(
                    "SELECT * FROM business.p4_clarification_requests WHERE id=%s", (identifier,)
                ).fetchone(),
                "replies": db.execute(
                    "SELECT * FROM business.p4_clarification_replies WHERE request_id=%s "
                    "ORDER BY created_at,id",
                    (identifier,),
                ).fetchall(),
                "sdk_calls": db.execute(
                    "SELECT * FROM business.p4_sdk_calls ORDER BY started_at,id"
                ).fetchall(),
                "sdk_windows": db.execute(
                    "SELECT * FROM business.p4_sdk_windows ORDER BY id"
                ).fetchall(),
                "audit": db.execute(
                    "SELECT * FROM business.audit_events WHERE source IN "
                    "('worker','feishu_gateway','feishu_clarification','feishu_recovery',"
                    "'feishu_delivery') ORDER BY occurred_at,id"
                ).fetchall(),
                "tasks": db.execute("SELECT * FROM business.business_tasks ORDER BY id").fetchall(),
                "jobs": db.execute("SELECT * FROM business.jobs ORDER BY id").fetchall(),
                "business_before": before,
                "business_after": business_counts(f),
            }
        write_private(inputs.directory / "final-PG-facts.private.json", json_native(facts))
    finally:
        f.client.close()
