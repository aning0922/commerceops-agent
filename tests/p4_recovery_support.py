"""A08新owned PG的真实进程/原SDK账本+Fake transport；平台调用与秘密读取0。"""

import asyncio
import json
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from commerceops.adapters.feishu.business_base import BusinessBaseAdapter
from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.adapters.feishu.projection_contract import ApiReply
from commerceops.application.feishu_business.delivery import DeliveryGate
from commerceops.application.feishu_business.gateway_window import GatewayWindow
from commerceops.application.feishu_business.sdk_calls import SDKMethod
from commerceops.application.feishu_business.sdk_window import SDKWindow
from commerceops.entrypoints.feishu_business import confirm_gateway_child, confirm_worker_child
from commerceops.infrastructure.feishu_base_delivery import BaseDeliveryStore
from commerceops.infrastructure.feishu_sdk_ledger import PersistentSDKLedger
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.worker_lock import WorkerSession

from tests.p3_support import P3Fixture
from tests.test_p4_base_adapter import MemoryRecords


def settings(f: P3Fixture) -> BusinessSettings:
    return BusinessSettings(
        schema_version="p4-v1",
        organization_id=f.actor.organization_id,
        shop_id=f.inventory.data.shop,
        app_id=f.inventory.data.app,
        tenant_key=f.inventory.data.tenant,
        bot_open_id="synthetic-bot",
        allowed_open_ids=frozenset({"p4-synthetic-user", "p4-synthetic-B"}),
        allowed_group_chat_ids=frozenset({"p4-synthetic-chat"}),
        app_secret_file=Path("/never-read/app-secret"),
        web_config_file=f.config_file,
        base_target_key="test",
        base_app_token_file=Path("/never-read/base-reference"),
        base_table_name="synthetic",
    )


def gateway(
    f: P3Fixture, *, case: str = "known_inbound", seconds: int = 180, max_workflows: int = 1
) -> GatewayWindow:
    return GatewayWindow.model_validate_json(
        json.dumps(
            {
                "schema_version": "p4-gateway-v1",
                "window_id": str(uuid4()),
                "organization_id": str(f.actor.organization_id),
                "shop_id": str(f.inventory.data.shop),
                "expires_at": (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat(),
                "enabled": True,
                "max_workflows": max_workflows,
                "parameters": {
                    "source_mode": "mock",
                    "dataset_version": "inventory-v1",
                    "fixture_case": case,
                    "L": 3,
                    "R": 7,
                    "S": 2,
                },
            }
        )
    )


def write_private(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, default=str))
    path.chmod(0o600)


def start_gateway(f: P3Fixture, window: GatewayWindow) -> subprocess.Popen[bytes]:
    # 固定plain child只执行原claim/process_started；不是官方WS/wire测试。
    cfg, win = (
        f.private / ("business-" + uuid4().hex + ".json"),
        f.private / ("gateway-" + uuid4().hex + ".json"),
    )
    write_private(cfg, settings(f).model_dump(mode="json"))
    write_private(win, window.model_dump(mode="json"))
    code = """import sys,time
from pathlib import Path
from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.application.feishu_business.gateway_window import GatewayWindow
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_gateway_window import claim_gateway,gateway_process_started
from commerceops.infrastructure.web_config import WebConfig
settings=BusinessSettings.model_validate_json(Path(sys.argv[1]).read_text())
window=GatewayWindow.model_validate_json(Path(sys.argv[2]).read_text())
web=WebConfig.from_file(settings.web_config_file)
with connect(web.database) as db:
    claim_gateway(db,settings,window)
    gateway_process_started(db,window)
    print('ready',flush=True)
    time.sleep(60)
"""
    child = subprocess.Popen(
        [sys.executable, "-c", code, str(cfg), str(win)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert child.stdout
        # 有界readiness，不能让stdout.readline绕截止。
        import select

        assert select.select([child.stdout], [], [], 10)[0]
        assert child.stdout.readline().strip() == b"ready"
        return child
    except BaseException:
        child.kill()
        child.wait(timeout=5)
        if child.stdout:
            child.stdout.close()
        raise


def stop_gateway(f: P3Fixture, window: GatewayWindow, child: subprocess.Popen[bytes]) -> None:
    if child.poll() is None:
        child.terminate()
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=5)
    if child.stdout:
        child.stdout.close()
    asyncio.run(
        confirm_gateway_child(
            f.config, f.actor.organization_id, window.window_id, child.pid, child.returncode
        )
    )


class RecordedRecords(MemoryRecords):
    """通过原Ledger记录每个Fake SDK method；不构造BusinessSDKFactory/Client。"""

    def __init__(self, ledger: PersistentSDKLedger, **kwargs: Any):
        super().__init__(**kwargs)
        self.ledger = ledger

    async def list(self, *args: Any, **kwargs: Any) -> ApiReply:
        async def call() -> ApiReply:
            return await super(RecordedRecords, self).list(*args, **kwargs)

        return cast(ApiReply, await self.ledger.invoke("bitable.v1.app_table_record.list", call))

    async def create(self, *args: Any, **kwargs: Any) -> ApiReply:
        async def call() -> ApiReply:
            return await super(RecordedRecords, self).create(*args, **kwargs)

        return cast(ApiReply, await self.ledger.invoke("bitable.v1.app_table_record.create", call))

    async def update(self, *args: Any, **kwargs: Any) -> ApiReply:
        async def call() -> ApiReply:
            return await super(RecordedRecords, self).update(*args, **kwargs)

        return cast(ApiReply, await self.ledger.invoke("bitable.v1.app_table_record.update", call))


async def unknown_child(config_file: Path, spec_file: Path, output: Path) -> None:
    config = WebConfig.from_file(config_file)
    spec = json.loads(spec_file.read_text())
    organization, shop, task = (UUID(spec[k]) for k in ("organization", "shop", "task"))
    expiry = datetime.fromisoformat(spec["expires_at"])
    session = WorkerSession(config.database, organization)
    await session.start()
    try:
        caps: dict[SDKMethod, int] = {
            "bitable.v1.app_table_record.list": 2,
            "bitable.v1.app_table_record.create": 1,
        }
        window = SDKWindow(
            UUID(spec["sdk_window"]),
            organization,
            shop,
            expiry,
            caps,
            enabled=True,
            verification_mode="controlled_sdk",
        )
        ledger = PersistentSDKLedger(session, window)
        fake = RecordedRecords(ledger, reply=ApiReply(None, None))
        store = BaseDeliveryStore(
            session,
            BusinessBaseAdapter(fake, {"test": ("fake", "fake")}),
            DeliveryGate(
                organization,
                shop,
                frozenset({task}),
                "test",
                expiry,
                enabled=True,
                verification_mode="controlled_sdk",
            ),
            ledger,
        )
        outcome = await store.dispatch_one()
        write_private(
            output,
            {
                "rows": fake.rows,
                "owner": session.owner,
                "outcome": outcome,
                "window_active": window.allows("bitable.v1.app_table_record.create"),
                "observed_at": datetime.now(UTC).isoformat(),
                "expires_at": expiry.isoformat(),
            },
        )
        assert outcome == "unknown"
    finally:
        await session.close(clean=True)


def original_unknown(f: P3Fixture, task: UUID, window: GatewayWindow) -> tuple[Path, UUID]:
    spec, output = f.private / "unknown-spec.private.json", f.private / "remote.private.json"
    original_sdk = uuid4()
    write_private(
        spec,
        {
            "organization": str(f.actor.organization_id),
            "shop": str(f.inventory.data.shop),
            "task": str(task),
            "expires_at": window.expires_at.isoformat(),
            "sdk_window": str(original_sdk),
        },
    )
    code = """import asyncio,json,sys,traceback
from pathlib import Path
from tests.p4_recovery_support import unknown_child
try:
    asyncio.run(unknown_child(*(Path(p) for p in sys.argv[1:])))
except Exception as error:
    print(json.dumps({'error_category':type(error).__name__,'trace':[
        {'file':Path(frame.filename).name,'function':frame.name,'line':frame.lineno}
        for frame in traceback.extract_tb(error.__traceback__)]}),file=sys.stderr)
    raise SystemExit(1) from None
"""
    child = subprocess.Popen(
        [sys.executable, "-c", code, str(f.config_file), str(spec), str(output)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        _, errors = child.communicate(timeout=15)
        if child.returncode:
            evidence = Path("/run/owned") if Path("/run/owned").is_dir() else f.private
            diagnostic = evidence / ("unknown-child-" + uuid4().hex + ".private.txt")
            diagnostic.write_bytes(errors)
            diagnostic.chmod(0o600)
            raise AssertionError("original unknown child failed; retained private stderr")
        asyncio.run(confirm_worker_child(f.config, f.actor.organization_id, child.pid))
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
    return output, original_sdk


def wait_expired(window: GatewayWindow) -> None:
    remaining = (window.expires_at - datetime.now(UTC)).total_seconds()
    assert remaining < 30
    if remaining > 0:
        time.sleep(remaining + 0.02)
