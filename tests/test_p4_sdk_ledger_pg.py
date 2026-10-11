"""新SDK账本真实PG原cap/原窗口不复位、未授权scope0调用；Fake SDK非wire。"""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from commerceops.application.feishu_business.sdk_window import SDKScope, SDKWindow
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_sdk_ledger import PersistentSDKLedger
from commerceops.infrastructure.worker_lock import WorkerSession
from psycopg.errors import CheckViolation

from tests.p3_support import P3Fixture
from tests.test_p3_pg import fixture as fixture

pytestmark = pytest.mark.integration


def test_original_window_cap_persistent_restart_scope_and_terminal_call_immutability(
    fixture: P3Fixture,
) -> None:
    f = fixture
    calls = []

    async def fake() -> SimpleNamespace:
        calls.append("SDK invoked")
        return SimpleNamespace(raw=SimpleNamespace(status_code=200), code=0)

    async def run() -> None:
        session = WorkerSession(f.config.database, f.actor.organization_id)
        await session.start()
        window = SDKWindow(
            uuid4(),
            f.actor.organization_id,
            f.inventory.data.shop,
            datetime.now(UTC) + timedelta(minutes=2),
            {"bitable.v1.app_table.list": 1},
            enabled=True,
        )
        ledger = PersistentSDKLedger(session, window)
        try:
            with pytest.raises(PermissionError, match="SDK_WINDOW_CLOSED"):
                await ledger.invoke("bitable.v1.app_table.list", fake)
            with ledger.scope(SDKScope(window.window_id, None, "preflight")):
                assert (await ledger.invoke("bitable.v1.app_table.list", fake)).code == 0
            replacement = PersistentSDKLedger(session, window)
            with replacement.scope(SDKScope(window.window_id, None, "preflight")):
                with pytest.raises(PermissionError, match="SDK_METHOD_CAP_EXHAUSTED"):
                    await replacement.invoke("bitable.v1.app_table.list", fake)
            assert len(calls) == 1
            with connect(f.config.database) as db:
                assert db.execute(
                    "SELECT status,http_status,provider_code FROM business.p4_sdk_calls"
                ).fetchone() == {"status": "returned", "http_status": 200, "provider_code": 0}
            with connect(f.config.database) as db, pytest.raises(CheckViolation):
                db.execute("DELETE FROM business.p4_sdk_calls")
        finally:
            await session.close(clean=True)

    asyncio.run(run())
