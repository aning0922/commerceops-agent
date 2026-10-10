"""只用于受控自有测试的T1提交/ACK屏障；无平台事件/生产身份后门。"""

import json
import os
import sys
from pathlib import Path
from uuid import UUID

from commerceops.application.intake import TestInbound, TrustedTestContext
from commerceops.application.replenishment.contracts import CreateInput, WebActor
from commerceops.infrastructure.intake import PgTestIntakeStore
from commerceops.infrastructure.replenishment_repository import ReplenishmentStore
from commerceops.infrastructure.web_config import WebConfig
from pydantic import TypeAdapter

from tests.inventory_support import DIRECTORY


def emit(event: str) -> None:
    print(json.dumps({"event": event, "pid": os.getpid()}), flush=True)


def main() -> None:
    value = json.loads(Path(sys.argv[1]).read_text())
    config = WebConfig.from_file(Path(value["configuration"]))

    def hook(point: str) -> None:
        emit(point)
        if point == value["barrier"] and sys.stdin.readline().strip() != "release":
            raise ValueError("controlled P3 release required")

    if value["action"] == "create":
        a = value["actor"]
        actor = WebActor(
            UUID(a["session_id"]),
            UUID(a["principal_id"]),
            UUID(a["identity_id"]),
            UUID(a["organization_id"]),
            a["auth_version"],
        )
        request: CreateInput = TypeAdapter(CreateInput).validate_json(json.dumps(value["payload"]))
        ReplenishmentStore(config, DIRECTORY).create(actor, request, hook)
    else:
        data = value["legacy"]
        context = TrustedTestContext(
            UUID(data["organization"]),
            UUID(data["shop"]),
            UUID(data["principal"]),
            UUID(data["conversation"]),
            "test",
        )
        event = TestInbound(
            app_id=data["app"],
            tenant_key=data["tenant"],
            event_id=value["payload"]["event_id"],
            message_id=value["payload"]["message_id"],
            workflow_version="p103-technical-v1",
            normalized_request={"schema_version": 1},
        )
        PgTestIntakeStore(config.database).accept(context, event, hook)
    emit("ack")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"event": "failed", "category": type(error).__name__}), flush=True)
        raise SystemExit(2) from None
