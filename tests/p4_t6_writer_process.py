"""明确合成真人的原生T6事务子进程；仅用于新owned PG的inflight边界。"""

import hashlib
import json
import os
import socket
import sys
import time
from pathlib import Path

from commerceops.application.replenishment.contracts import ResolveInput
from commerceops.infrastructure.replenishment_items import ItemStore
from commerceops.infrastructure.replenishment_repository import ReplenishmentStore
from commerceops.infrastructure.web_config import WebConfig, private_bytes
from commerceops.infrastructure.web_sessions import SessionStore
from commerceops.infrastructure.worker_lock import process_namespace

from scripts.p4_acceptance import write_private
from tests.inventory_support import DIRECTORY


def main() -> int:
    raw = private_bytes(Path(sys.argv[1]))
    if hashlib.sha256(raw).hexdigest() != sys.argv[2]:
        raise PermissionError("SYNTHETIC_T6_INPUT_HASH")
    value = json.loads(raw)
    config = WebConfig.from_file(Path(value["config"]))
    if not config.database.name.startswith("p4_acceptance_"):
        raise PermissionError("SYNTHETIC_T6_OWNED_ONLY")
    actor = SessionStore(config).authenticate(value["session"])
    request = ResolveInput.model_validate_json(json.dumps(value["request"]))
    from uuid import UUID

    def hook(stage: str) -> None:
        if stage != "before_t6_commit":
            return
        write_private(
            Path(value["ready"]),
            dict(
                pid=os.getpid(),
                host=socket.gethostname(),
                pid_namespace=process_namespace(),
            ),
        )
        end = time.monotonic() + 15
        while not Path(value["release"]).exists():
            if time.monotonic() >= end:
                raise TimeoutError("SYNTHETIC_T6_RELEASE_TIMEOUT")
            time.sleep(0.02)

    try:
        result = ItemStore(ReplenishmentStore(config, DIRECTORY)).resolve(
            actor,
            UUID(value["item_id"]),
            request,
            hook=hook if value["pause"] else None,
        )
        write_private(Path(value["result"]), dict(status="COMMITTED", receipt=result))
        return 0
    except Exception as error:
        write_private(
            Path(value["result"]),
            dict(status="REJECTED_OR_UNKNOWN", exception_type=type(error).__name__),
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
