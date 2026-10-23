"""受控正式装配的必要PG scope gate；合成入站，SDK/Secret/Graph均0。"""

import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.application.feishu_business.gateway_window import GatewayWindow
from commerceops.application.feishu_business.worker_window import ControlledWorkerWindow
from commerceops.entrypoints.feishu_business import confirm_worker_child
from commerceops.entrypoints.feishu_worker_child import trusted_scope
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_gateway_window import claim_gateway, guard_gateway
from psycopg import sql

from tests.p3_support import P3Fixture
from tests.test_p3_pg import fixture as fixture
from tests.test_p4_gateway_pg import counts, message, service

pytestmark = pytest.mark.integration


def test_real_original_gateway_task_parameters_scope_no_sdk_or_business_increment(
    fixture: P3Fixture,
) -> None:
    f = fixture
    settings = BusinessSettings(
        schema_version="p4-v1",
        organization_id=f.actor.organization_id,
        shop_id=f.inventory.data.shop,
        app_id=f.inventory.data.app,
        tenant_key=f.inventory.data.tenant,
        bot_open_id="synthetic-bot",
        allowed_open_ids=frozenset({"p4-synthetic-user"}),
        allowed_group_chat_ids=frozenset(),
        app_secret_file=Path("/never-read/app-secret"),
        web_config_file=Path("/never-read/web-config"),
        base_target_key="synthetic",
        base_app_token_file=Path("/never-read/base-reference"),
        base_table_name="synthetic",
    )
    gateway = GatewayWindow.model_validate_json(
        json.dumps(
            {
                "schema_version": "p4-gateway-v1",
                "window_id": str(uuid4()),
                "organization_id": str(settings.organization_id),
                "shop_id": str(settings.shop_id),
                "expires_at": (datetime.now(UTC) + timedelta(seconds=180)).isoformat(),
                "parameters": {
                    "source_mode": "mock",
                    "dataset_version": "inventory-v1",
                    "fixture_case": "baseline",
                    "L": 3,
                    "R": 7,
                    "S": 2,
                },
                "enabled": True,
                "max_workflows": 1,
            }
        )
    )
    guarded = service(f, gateway_guard=lambda db, create: guard_gateway(db, gateway, create))
    with connect(f.config.database) as lease:
        claim_gateway(lease, settings, gateway)
        task = UUID(guarded.message(message(f))["task_id"])
        window = ControlledWorkerWindow.model_validate_json(
            json.dumps(
                {
                    "schema_version": "p4-worker-v1",
                    "window_id": str(uuid4()),
                    "gateway_window_id": str(gateway.window_id),
                    "organization_id": str(settings.organization_id),
                    "shop_id": str(settings.shop_id),
                    "task_ids": [str(task)],
                    "expires_at": (gateway.expires_at - timedelta(seconds=5)).isoformat(),
                    "enabled": True,
                    "caps": {
                        "auth.v3.tenant_access_token.internal": 1,
                        "bot.v3.info": 1,
                        "bitable.v1.app_table.list": 2,
                        "bitable.v1.app_table_field.list": 2,
                        "im.v1.message.create": 2,
                        "bitable.v1.app_table_record.create": 1,
                        "bitable.v1.app_table_record.list": 4,
                    },
                }
            )
        )
        before = counts(f)
        asyncio.run(trusted_scope(f.config, settings, window))
        assert counts(f) == before
        for change in (
            {"gateway_window_id": uuid4()},
            {"task_ids": frozenset({uuid4()})},
            {"expires_at": gateway.expires_at + timedelta(seconds=1)},
            {"shop_id": uuid4()},
        ):
            with pytest.raises(PermissionError):
                asyncio.run(trusted_scope(f.config, settings, window.model_copy(update=change)))
            assert counts(f) == before
        with connect(f.config.database) as db:
            for table in (
                "p4_sdk_windows",
                "p4_sdk_calls",
                "p4_im_deliveries",
                "p4_base_deliveries",
            ):
                # 固定已知表名，只验证scope读取无SDK意图或外部delivery增量。
                assert db.execute(
                    sql.SQL("SELECT count(*) AS n FROM business.{}").format(sql.Identifier(table))
                ).fetchone() == {"n": 0}


def test_same_container_parent_reaps_actual_session_child_and_confirms_full_pg_receipt(
    fixture: P3Fixture,
) -> None:
    f = fixture
    code = """import asyncio,sys
from pathlib import Path
from uuid import UUID
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.worker_lock import WorkerSession
async def run():
    config=WebConfig.from_file(Path(sys.argv[1]))
    session=WorkerSession(config.database,UUID(sys.argv[2]))
    await session.start()
    await session.close(clean=True)
asyncio.run(run())
"""
    child = subprocess.Popen(
        [sys.executable, "-c", code, str(f.config_file), str(f.actor.organization_id)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert child.wait(timeout=15) == 0
        assert child.poll() == 0
        asyncio.run(confirm_worker_child(f.config, f.actor.organization_id, child.pid))
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
    with connect(f.config.database) as db:
        row = db.execute(
            """SELECT count(*) AS n FROM business.audit_events WHERE organization_id=%s
            AND source='worker' AND entity_type='worker_runtime'
            AND action='termination_confirmed'""",
            (f.actor.organization_id,),
        ).fetchone()
        assert row == {"n": 1}
        assert db.execute("SELECT count(*) AS n FROM business.jobs").fetchone() == {"n": 0}
        assert db.execute("SELECT count(*) AS n FROM business.p4_sdk_calls").fetchone() == {"n": 0}
