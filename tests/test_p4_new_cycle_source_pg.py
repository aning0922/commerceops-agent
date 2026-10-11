"""原新Feishu T1/未完成P2源→单Worker→plan/card outbox；无SDK/真人。"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.application.feishu_business.gateway_window import GatewayWindow
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_gateway_window import claim_gateway
from commerceops.infrastructure.inventory_repository import AnalysisUnsafe, InventoryStore
from commerceops.workflows.inventory_analysis import MockCollectorFactory
from psycopg import sql

from tests.inventory_support import DIRECTORY
from tests.p3_support import P3Fixture, run_graphs
from tests.test_p3_pg import fixture as fixture
from tests.test_p4_gateway_pg import message, service

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "field,value",
    [("external_shop_key", "p4-ro-only"), ("currency", "USD"), ("timezone", "UTC")],
)
def test_wrong_fixture_metadata_rejected_before_gateway_claim_and_sdk(
    fixture: P3Fixture,
    field: str,
    value: str,
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
        web_config_file=Path("/never-read/config"),
        base_target_key="synthetic",
        base_app_token_file=Path("/never-read/base-token"),
        base_table_name="synthetic",
    )
    window = GatewayWindow.model_validate_json(
        json.dumps(
            {
                "schema_version": "p4-gateway-v1",
                "window_id": str(uuid4()),
                "organization_id": str(f.actor.organization_id),
                "shop_id": str(f.inventory.data.shop),
                "expires_at": (datetime.now(UTC) + timedelta(seconds=120)).isoformat(),
                "enabled": True,
                "parameters": {
                    "source_mode": "mock",
                    "dataset_version": "inventory-v1",
                    "fixture_case": "known_inbound",
                    "L": 3,
                    "R": 7,
                    "S": 2,
                },
            }
        )
    )
    with connect(f.inventory.owner) as db:
        db.execute(
            sql.SQL("UPDATE business.shops SET {}=%s WHERE id=%s").format(sql.Identifier(field)),
            (value, f.inventory.data.shop),
        )
    with connect(f.config.database) as lease:
        with (
            pytest.raises(PermissionError, match="^P4_CONTROLLED_FIXTURE_SCOPE_REQUIRED$"),
            lease.transaction(),
        ):
            claim_gateway(lease, settings, window)
    with connect(f.config.database) as db:
        assert db.execute(
            "SELECT count(*) AS n FROM business.audit_events WHERE id=%s",
            (window.window_id,),
        ).fetchone() == {"n": 0}
        for table in ("p4_sdk_windows", "p4_sdk_calls", "p4_im_deliveries", "p4_base_deliveries"):
            assert db.execute(
                sql.SQL("SELECT count(*) AS n FROM business.{}").format(sql.Identifier(table))
            ).fetchone() == {"n": 0}


def source_task(f: P3Fixture, task: UUID) -> UUID:
    with connect(f.config.database) as db:
        row = db.execute(
            "SELECT source_task_id FROM business.p3_task_sources WHERE task_id=%s", (task,)
        ).fetchone()
        assert row
        source = row["source_task_id"]
        assert isinstance(source, UUID)
        state = db.execute(
            "SELECT state FROM business.business_tasks WHERE id=%s", (source,)
        ).fetchone()
        assert state == {"state": "queued"}
        assert db.execute(
            "SELECT count(*) AS n FROM business.analysis_reports WHERE task_id=%s", (source,)
        ).fetchone() == {"n": 0}
        return source


def test_same_live_configuration_scope_error_is_not_mislabeled_checkpoint(
    fixture: P3Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    f = fixture
    with connect(f.inventory.owner) as db:
        db.execute(
            "UPDATE business.shops SET external_shop_key='p4-ro-only' WHERE id=%s",
            (f.inventory.data.shop,),
        )
    task = UUID(service(f, "known_inbound").message(message(f))["task_id"])
    source = source_task(f, task)
    with connect(f.inventory.owner) as db:
        db.execute(
            "UPDATE business.jobs SET available_at=clock_timestamp()-interval '1 second'"
            " WHERE task_id=%s",
            (source,),
        )
    errors: list[str] = []
    original = InventoryStore.save

    async def capture(self: InventoryStore, *args: Any, **kwargs: Any) -> Any:
        try:
            return await original(self, *args, **kwargs)
        except AnalysisUnsafe as error:
            # 仅已知源码固定码，拒绝回显任意exception文本。
            errors.append(
                "ANALYSIS_SOURCE_SCOPE_MISMATCH"
                if error.args == ("ANALYSIS_SOURCE_SCOPE_MISMATCH",)
                else "OTHER_UNSAFE"
            )
            raise

    monkeypatch.setattr(InventoryStore, "save", capture)
    asyncio.run(run_graphs(f, task, factory=MockCollectorFactory(DIRECTORY)))
    assert errors == ["ANALYSIS_SOURCE_SCOPE_MISMATCH"]
    with connect(f.config.database) as db:
        assert db.execute(
            "SELECT state,failure_code FROM business.business_tasks WHERE id=%s", (source,)
        ).fetchone() == {
            "state": "needs_attention",
            "failure_code": "ANALYSIS_SOURCE_SCOPE_MISMATCH",
        }
        assert db.execute(
            "SELECT state,failure_code FROM business.business_tasks WHERE id=%s", (task,)
        ).fetchone() == {"state": "failed", "failure_code": "DATA_INCOMPLETE"}
        for table in ("analysis_reports", "commerce_snapshots", "replenishment_plans", "outbox"):
            assert db.execute(
                sql.SQL("SELECT count(*) AS n FROM business.{}").format(sql.Identifier(table))
            ).fetchone() == {"n": 0}


def test_new_feishu_cycle_with_P3_available_first_waits_for_source_and_creates_card_outbox(
    fixture: P3Fixture,
) -> None:
    f = fixture
    task = UUID(service(f, "known_inbound").message(message(f))["task_id"])
    source = source_task(f, task)
    with connect(f.inventory.owner) as db:
        # 确定性P3更早eligible；不得依靠UUID随机先后或预完成from_report。
        db.execute(
            "UPDATE business.jobs SET available_at=clock_timestamp()-interval '2 seconds'"
            " WHERE task_id=%s",
            (task,),
        )
        db.execute(
            "UPDATE business.jobs SET available_at=clock_timestamp()-interval '1 second'"
            " WHERE task_id=%s",
            (source,),
        )
    asyncio.run(run_graphs(f, task, factory=MockCollectorFactory(DIRECTORY)))
    with connect(f.config.database) as db:
        assert db.execute(
            "SELECT state FROM business.business_tasks WHERE id=%s", (source,)
        ).fetchone() == {"state": "completed"}
        assert db.execute(
            "SELECT state FROM business.business_tasks WHERE id=%s", (task,)
        ).fetchone() == {"state": "awaiting_approval"}
        assert db.execute(
            "SELECT count(*) AS n FROM business.analysis_reports WHERE task_id=%s", (source,)
        ).fetchone() == {"n": 1}
        approval = db.execute(
            "SELECT id,ready_at FROM business.approvals WHERE task_id=%s", (task,)
        ).fetchone()
        assert approval and approval["ready_at"]
        assert db.execute(
            "SELECT count(*) AS n FROM business.outbox WHERE aggregate_id=%s AND status='pending'",
            (approval["id"],),
        ).fetchone() == {"n": 1}
        plan = db.execute(
            "SELECT content FROM business.replenishment_plans WHERE task_id=%s", (task,)
        ).fetchone()
        assert plan and len(plan["content"]["items"]) == 1
        assert plan["content"]["items"][0]["quantity"] == 70
        assert db.execute("SELECT count(*) AS n FROM business.p4_sdk_calls").fetchone() == {"n": 0}
