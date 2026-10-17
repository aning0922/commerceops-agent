"""从PG原carrier派生disabled输入→原parent/child/Factory；只Fake外HTTP。"""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.application.feishu_business.gateway_window import GatewayWindow
from commerceops.application.feishu_business.read_reply import (
    READ_REPLY_CAPS,
    ReadReplyPayload,
)
from commerceops.domain.commerce_values import facts_hash
from commerceops.entrypoints.feishu_gateway_child import BoundedReceiver
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.feishu_business import FeishuBusinessStore
from commerceops.infrastructure.feishu_gateway_window import guard_gateway
from commerceops.infrastructure.web_sessions import json_native

from scripts.p4_acceptance import AcceptanceFailure, read_reply_window_from_native, write_private
from tests.p3_support import P3Fixture, P3Process, initialize_p3
from tests.p4_parent_support import ParentInputs, native_gateway, prepare_parent
from tests.test_p4_acceptance_pg import database as database
from tests.test_p4_acceptance_pg import initialize_schema
from tests.test_p4_gateway_pg import message, service
from tests.test_p4_read_reply_pg import prepared
from tests.test_p4_template_results_pg import counts

pytestmark = pytest.mark.integration


def receive_and_select(
    f: P3Fixture, previous: dict[str, Any], *, behavior: str = "normal", ambiguous: bool = False
) -> tuple[dict[str, Any] | None, ParentInputs]:
    """新入站→持久回执→只读唯一selection→disabled模板；不复用旧pending。"""
    inputs = prepare_parent(f, None, mode="read_reply", behavior=behavior)
    settings = BusinessSettings.model_validate_json(inputs.business.read_bytes())
    original = service(f)
    gateway = GatewayWindow(
        schema_version="p4-gateway-v1",
        window_id=uuid4(),
        organization_id=settings.organization_id,
        shop_id=settings.shop_id,
        expires_at=datetime.now(UTC) + timedelta(seconds=120),
        enabled=True,
        parameters=original.parameters,
        max_workflows=0,
        max_callbacks=2,
    )
    payload = ReadReplyPayload.model_validate_json(json.dumps(previous["payload"]))
    report = (
        payload.source.report_id if payload.source and payload.kind == "explain_report" else None
    )
    text = (
        f"查询任务{payload.task_id}进度"
        if payload.kind == "task_status"
        else f"解释任务{payload.task_id}的报告{report}"
    )
    incoming = replace(message(f), text=text)
    predicate: dict[str, Any] = dict(
        task_id=payload.task_id,
        kind=payload.kind,
        identity_id=previous["identity_id"],
        chat_id=previous["chat_id"],
        text_sha256=facts_hash(incoming.text),
        report_id=report,
        expires_at=gateway.expires_at,
    )
    receiver = BoundedReceiver(
        FeishuBusinessStore(
            original.store,
            original.shop,
            original.parameters,
            gateway_guard=lambda db, create: guard_gateway(db, gateway, create),
        ),
        gateway,
    )

    def select(**changes: Any) -> Any:
        with connect(f.config.database) as db:
            db.execute("SET TRANSACTION READ ONLY")
            return read_reply_window_from_native(db, settings, gateway, **{**predicate, **changes})

    row = None
    with native_gateway(f, inputs, gateway.model_dump(mode="json")):
        # 相同任务/文本已有pending也不能冒充本次新Gateway收到的carrier。
        with pytest.raises(AcceptanceFailure, match="P4A_READ_SELECTION_UNIQUE"):
            select()
        receipt = receiver.message(incoming)
        if ambiguous:
            receiver.message(replace(incoming, event_id=uuid4().hex, message_id=uuid4().hex))
            with pytest.raises(AcceptanceFailure, match="P4A_READ_SELECTION_UNIQUE"):
                select()
        else:
            negative_selections: list[dict[str, Any]] = [
                {"text_sha256": "0" * 64},
                {"identity_id": uuid4()},
                {"chat_id": "different-owned-chat"},
            ]
            for changed in negative_selections:
                with pytest.raises(AcceptanceFailure):
                    select(**changed)
            template = select()
            assert not template.enabled and str(template.reply_id) == receipt["reply_id"]
            assert template.reply_id != previous["id"] and template.task_id == previous["task_id"]
            assert select() == template
            inputs.bind_window(template.model_dump(mode="json"))
            with connect(f.config.database) as db:
                row = db.execute(
                    "SELECT * FROM business.p4_read_replies WHERE id=%s", (template.reply_id,)
                ).fetchone()
            assert row and row["payload"]["as_of"] == receipt["as_of"]
        write_private(
            inputs.directory / "reception-and-selection.private.json",
            {
                "Gateway": gateway.model_dump(mode="json"),
                "receipt": receipt,
                "normalized_text_hash": predicate["text_sha256"],
                "kind": payload.kind,
                "old_pending_not_selected": True,
                "ambiguous_rejected": ambiguous,
                "selection_SQL_read_only": True,
                "mode": "simulated_feishu/native_Gateway_no_WS",
                "actual_WS_received": "not_run",
                "source_task": str(payload.task_id),
            },
        )
    assert json.loads((inputs.directory / "gateway.exit.safe.json").read_bytes())[
        "termination_confirmed"
    ]
    return row, inputs


@pytest.mark.parametrize(
    "revision,kind,outcome",
    [
        ("0015", "task_status", "sent"),
        ("0016", "task_status", "sent"),
        ("0015", "explain_report", "sent"),
        ("0016", "explain_report", "sent"),
        ("0016", "not_ready", "sent"),
        ("0016", "explain_report", "unknown"),
        ("0016", "explain_report", "revoked"),
        ("0016", "explain_report", "wrong_task"),
    ],
)
def test_generated_selected_read_parent_native_SQL_once_cold_replay_and_cleanup(
    database: tuple[DatabaseSettings, DatabaseSettings],
    tmp_path: Path,
    revision: str,
    kind: str,
    outcome: str,
) -> None:
    owner, app = database
    initialize_schema(owner, revision)
    f = initialize_p3(owner, app, tmp_path)
    try:
        if kind == "not_ready":
            # 新owned历史切片：原Graph真实落unavailable，独立旧进程必须退出。
            s = service(f)
            incoming = message(f)
            task = UUID(s.message(incoming)["task_id"])
            history = P3Process(
                f, "worker", {"task_id": str(task), "p4_template_unavailable": True}, "never"
            )
            try:
                history.until("after_ready")
                history.stop_clean()
            finally:
                if history.process.poll() is None:
                    history.kill_reap()
            with connect(app) as db:
                source = db.execute(
                    "SELECT source_report_id FROM business.p3_task_sources WHERE task_id=%s",
                    (task,),
                ).fetchone()
            assert source
            receipt = s.message(
                replace(
                    incoming,
                    event_id=uuid4().hex,
                    message_id=uuid4().hex,
                    text=f"解释任务{task}的报告{source['source_report_id']}",
                )
            )
            assert receipt["facts"]["error"]["code"] == "NOT_READY"
            with connect(app) as db:
                row = db.execute(
                    "SELECT * FROM business.p4_read_replies WHERE id=%s",
                    (UUID(receipt["reply_id"]),),
                ).fetchone()
            assert row and row["payload"]["explanation"] is None
        else:
            row = prepared(f, kind)
        old_pending = row
        row, inputs = receive_and_select(
            f, old_pending, behavior="im_timeout" if outcome == "unknown" else "normal"
        )
        assert row
        before = counts(f)
        # 只按本次明确原carrier取完整metadata，不扫描组织pending。
        with connect(app) as db:
            db.execute("SET TRANSACTION READ ONLY")
            selected = db.execute(
                "SELECT * FROM business.p4_read_replies WHERE id=%s AND task_id=%s",
                (row["id"], row["task_id"]),
            ).fetchone()
            low = db.execute(
                "SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user"
            ).fetchone()
        assert selected == row and low == {
            "rolsuper": False,
            "rolcreatedb": False,
            "rolcreaterole": False,
        }
        template = json.loads(inputs.disabled_window.read_bytes())
        write_private(
            inputs.directory / "selected-carrier.private.json",
            {
                "reply_id": str(row["id"]),
                "task_id": str(row["task_id"]),
                "as_of": row["payload"]["as_of"],
                "payload_hash": row["payload_hash"],
                "source": row["payload"]["source"],
                "revision": revision,
            },
        )
        assert inputs.run("disabled", disabled=True)[0] == 1
        if outcome == "revoked":
            with connect(owner) as db:
                db.execute(
                    "UPDATE business.principal_role_shop_grants SET enabled=false "
                    "WHERE principal_id=%s",
                    (row["principal_id"],),
                )
        elif outcome == "wrong_task":
            changed = json.loads(inputs.active_window.read_bytes())
            changed["task_id"] = str(uuid4())
            write_private(
                inputs.directory / "wrong-task.input-mapping.safe.json",
                {
                    "changed_field": "task_id",
                    "intentionally_invalid": True,
                },
            )
            write_private(inputs.active_window, changed)
        code, result = inputs.run("first")
        expected = outcome == "sent"
        assert code == (0 if expected else 1) and result["child_reaped"]
        assert result["lifecycle_termination_confirmed"] is True
        assert result["result"] == ("window_stopped" if expected else "failed")
        with connect(app) as db:
            saved = db.execute(
                "SELECT * FROM business.p4_read_replies WHERE id=%s", (row["id"],)
            ).fetchone()
            calls = db.execute(
                "SELECT * FROM business.p4_sdk_calls ORDER BY started_at,id"
            ).fetchall()
        assert saved and saved["payload"] == row["payload"] and saved["as_of"] == row["as_of"]
        assert saved["provider_uuid"] == row["provider_uuid"]
        assert saved["status"] == (
            "sent" if expected else "unknown" if outcome == "unknown" else "pending"
        )
        assert saved["attempts"] == (1 if outcome in ("sent", "unknown") else 0)
        assert len(calls) == (3 if outcome in ("sent", "unknown") else 0)
        if calls:
            assert {c["method"] for c in calls} == set(READ_REPLY_CAPS)
            assert all(str(c["window_id"]) == template["window_id"] for c in calls)
        messages = list(inputs.directory.glob("im-*.private.json"))
        assert len(messages) == (1 if outcome in ("sent", "unknown") else 0)
        if messages:
            body = json.loads(messages[0].read_bytes())
            payload = ReadReplyPayload.model_validate_json(json.dumps(row["payload"]))
            expected_message = payload.message(row["id"], row["provider_uuid"], row["chat_id"])
            assert json.loads(body["content"]) == expected_message.card
            assert (
                body["uuid"] == str(row["provider_uuid"]) and body["receive_id"] == row["chat_id"]
            )
        cold_code, cold = inputs.run("cold")
        assert cold_code == 1 and cold["child_reaped"] and cold["lifecycle_termination_confirmed"]
        with connect(app) as db:
            db.execute("SET TRANSACTION READ ONLY")
            assert (
                db.execute("SELECT * FROM business.p4_sdk_calls ORDER BY started_at,id").fetchall()
                == calls
            )
            assert (
                db.execute(
                    "SELECT * FROM business.p4_read_replies WHERE id=%s", (row["id"],)
                ).fetchone()
                == saved
            )
            assert (
                db.execute(
                    "SELECT * FROM business.p4_read_replies WHERE id=%s", (old_pending["id"],)
                ).fetchone()
                == old_pending
            )
            facts = {
                "database_UTC": db.execute("SELECT clock_timestamp() AS at").fetchone(),
                "carrier": saved,
                "old_pending": old_pending,
                "sdk_calls": calls,
                "sdk_windows": db.execute(
                    "SELECT * FROM business.p4_sdk_windows ORDER BY id"
                ).fetchall(),
                "lifecycle": db.execute(
                    "SELECT * FROM business.audit_events WHERE source IN "
                    "('worker','feishu_gateway') ORDER BY occurred_at,id"
                ).fetchall(),
            }
        write_private(inputs.directory / "final-PG-facts.private.json", json_native(facts))
        assert counts(f) == before
        write_private(
            inputs.directory / "verification.safe.json",
            {
                "revision": revision,
                "kind": kind,
                "outcome": outcome,
                "SDK_calls": len(calls),
                "cold_SDK_delta": 0,
                "business_counts_unchanged": True,
                "payload_asof_source_immutable": True,
                "real_termination_confirmed": True,
                "cached_ready": kind != "not_ready",
                "provider_calls": 0,
            },
        )
    finally:
        f.client.close()


def test_new_gateway_ambiguous_read_carriers_reject_without_window_or_SDK(
    database: tuple[DatabaseSettings, DatabaseSettings], tmp_path: Path
) -> None:
    owner, app = database
    initialize_schema(owner, "0016")
    f = initialize_p3(owner, app, tmp_path)
    try:
        previous = prepared(f, "task_status")
        before = counts(f)
        row, inputs = receive_and_select(f, previous, ambiguous=True)
        assert (
            row is None
            and not inputs.disabled_window.exists()
            and not inputs.active_window.exists()
        )
        with connect(app) as db:
            assert db.execute("SELECT count(*) AS n FROM business.p4_sdk_calls").fetchone() == {
                "n": 0
            }
            assert db.execute(
                "SELECT count(*) AS n FROM business.p4_read_replies WHERE status='pending'"
            ).fetchone() == {"n": 3}
        assert counts(f) == before
        write_private(
            inputs.directory / "verification.safe.json",
            {
                "ambiguous_selection_rejected": True,
                "SDK_calls": 0,
                "business_counts_unchanged": True,
                "disabled_and_active_window_not_created": True,
                "old_pending_not_selected": True,
            },
        )
    finally:
        f.client.close()
