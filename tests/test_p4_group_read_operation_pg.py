"""显式600秒群读取：旧两条入站保留，新两条精确选择，四次callback后封闭。"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from commerceops.application.feishu_business.gateway_window import GatewayWindow
from commerceops.application.replenishment.contracts import WebFailure
from commerceops.domain.commerce_values import facts_hash
from commerceops.entrypoints.feishu_gateway_child import BoundedReceiver
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.feishu_business import FeishuBusinessStore
from commerceops.infrastructure.feishu_gateway_window import claim_gateway, guard_gateway

from scripts.p4_acceptance import (
    AcceptanceFailure,
    group_read_subject,
    read_reply_window_from_native,
    read_reply_window_from_saved_selection,
)
from tests.p3_support import initialize_p3
from tests.test_p4_acceptance_pg import database as database
from tests.test_p4_acceptance_pg import initialize_schema
from tests.test_p4_gateway_pg import message, service
from tests.test_p4_read_reply_parent_pg import completed_group_inputs

pytestmark = pytest.mark.integration


def test_group_operation_selects_only_new_hashes_and_rechecks_original_claim(
    database: tuple[DatabaseSettings, DatabaseSettings], tmp_path: Path
) -> None:
    owner, app = database
    initialize_schema(owner, "0017")
    f = initialize_p3(owner, app, tmp_path)
    try:
        task, identity, chat, inputs, settings = completed_group_inputs(f)
        original = service(f)
        gateway = GatewayWindow(
            schema_version="p4-gateway-v1",
            window_id=uuid4(),
            organization_id=settings.organization_id,
            shop_id=settings.shop_id,
            expires_at=datetime.now(UTC) + timedelta(seconds=540),
            enabled=True,
            parameters=original.parameters,
            max_workflows=0,
            max_callbacks=4,
            group_operation_chat_id=chat,
        )
        receiver = BoundedReceiver(
            FeishuBusinessStore(
                original.store,
                original.shop,
                original.parameters,
                gateway_guard=lambda db, create: guard_gateway(db, gateway, create),
            ),
            gateway,
            group_chat_ids=frozenset({chat}),
        )
        with connect(app) as lease:
            claim_gateway(lease, settings, gateway)
            with connect(app) as db:
                db.execute("SET TRANSACTION READ ONLY")
                subject = group_read_subject(
                    db, settings, task_id=task, identity_id=identity, chat_id=chat
                )
            texts = [q["text"] for q in subject["queries"]] + [
                f"查询任务 {task} 进度",
                f"解释任务 {task} 的报告 {subject['report_id']}",
            ]
            receipts = []
            for text in texts:
                receipts.append(
                    receiver.message(
                        replace(
                            message(f, kind="group"),
                            text=text,
                            event_id=str(uuid4()),
                            message_id=str(uuid4()),
                        )
                    )
                )
            assert receiver.admitted == 4
            with pytest.raises(WebFailure, match="GATEWAY_CALLBACK_CAP_EXHAUSTED"):
                receiver.message(replace(message(f, kind="group"), text=texts[2]))
            selected = []
            for query, text, receipt in zip(
                subject["queries"], texts[2:], receipts[2:], strict=True
            ):
                with connect(app) as db:
                    db.execute("SET TRANSACTION READ ONLY")
                    window = read_reply_window_from_native(
                        db,
                        settings,
                        gateway,
                        task_id=task,
                        kind=query["kind"],
                        identity_id=identity,
                        chat_id=chat,
                        text_sha256=facts_hash(text),
                        report_id=UUID(subject["report_id"])
                        if query["kind"] == "explain_report"
                        else None,
                        expires_at=datetime.now(UTC) + timedelta(seconds=120),
                    )
                    assert str(window.reply_id) == receipt["reply_id"]
                    # Even an otherwise valid opgroup cannot change its original expiry.
                    changed = gateway.model_copy(
                        update={"expires_at": gateway.expires_at + timedelta(seconds=1)}
                    )
                    with pytest.raises(AcceptanceFailure, match="P4A_READ_ARM_ORIGINAL_CLAIM"):
                        read_reply_window_from_saved_selection(
                            db,
                            settings,
                            changed,
                            window,
                            payload_hash=receipt["reply_payload_hash"],
                            text_sha256=facts_hash(text),
                            expires_at=datetime.now(UTC) + timedelta(seconds=120),
                        )
                selected.append((window, receipt, facts_hash(text)))
        for index, (window, receipt, text_hash) in enumerate(selected):
            with connect(app) as db:
                db.execute("SET TRANSACTION READ ONLY")
                armed = read_reply_window_from_saved_selection(
                    db,
                    settings,
                    gateway,
                    window,
                    payload_hash=receipt["reply_payload_hash"],
                    text_sha256=text_hash,
                    expires_at=datetime.now(UTC) + timedelta(seconds=120),
                )
            inputs.bind_window(armed.model_dump(mode="json"))
            assert inputs.run(f"new-{index}")[0] == 0
            assert inputs.run(f"new-{index}-cold")[0] == 1
        with connect(app) as db:
            rows = db.execute(
                "SELECT id,status,attempts FROM business.p4_read_replies WHERE task_id=%s",
                (task,),
            ).fetchall()
            old_ids = {r["reply_id"] for r in receipts[:2]}
            assert len(rows) == 4
            assert all(
                (r["status"], r["attempts"])
                == (("pending", 0) if str(r["id"]) in old_ids else ("sent", 1))
                for r in rows
            )
    finally:
        f.client.close()
