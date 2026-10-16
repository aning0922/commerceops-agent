"""queued恢复的最小运行回执；同原child，不另加observer或协议验收Gate。"""

import os
import socket
from typing import Any
from uuid import uuid5

from psycopg.types.json import Jsonb

from commerceops.adapters.feishu.queued_gateway_ready import SDK_WS_SHA256
from commerceops.application.feishu_business.gateway_window import GatewayWindow
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_outbox_recovery import full_process_receipt
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.worker_lock import process_namespace


def ready_state(process: dict[str, Any]) -> dict[str, Any]:
    return dict(
        process=process,
        sdk_ws_sha256=SDK_WS_SHA256,
        state="OPEN",
        handlers=["im.message.receive_v1", "card.action.trigger"],
        receive_task_scheduled=True,
        auto_reconnect=False,
    )


def gateway_transport_event(config: WebConfig, window: GatewayWindow, *, lost: bool) -> None:
    process = dict(pid=os.getpid(), host=socket.gethostname(), pid_namespace=process_namespace())
    if config.database.user != "commerceops_app" or not full_process_receipt(process):
        raise PermissionError("P4_QUEUED_GATEWAY_PROCESS_REQUIRED")
    with connect(config.database) as db:
        row = db.execute(
            """SELECT after_state FROM business.audit_events WHERE organization_id=%s
            AND source='feishu_gateway' AND action='started' AND entity_type='gateway_runtime'
            AND entity_id=%s""",
            (window.organization_id, str(window.window_id)),
        ).fetchall()
        if len(row) != 1 or row[0]["after_state"] != process or (not lost and not window.active()):
            raise PermissionError("P4_QUEUED_GATEWAY_PROCESS_REQUIRED")
        action = "transport_lost" if lost else "ready"
        db.execute(
            """INSERT INTO business.audit_events(id,organization_id,source,action,
            entity_type,entity_id,after_state,trace_id) VALUES(%s,%s,'feishu_gateway',%s,
            'gateway_runtime',%s,%s,%s)""",
            (
                uuid5(window.window_id, action),
                window.organization_id,
                action,
                str(window.window_id),
                Jsonb(ready_state(process)),
                window.window_id,
            ),
        )
