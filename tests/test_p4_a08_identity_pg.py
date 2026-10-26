"""共同T1当前平台身份准入的真实owned PG，preassembly FakeSession/SDK0。"""

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from commerceops.application.feishu_business.worker_window import (
    GROUP20_CAPS,
    KNOWN70_CAPS,
    ControlledWorkerWindow,
)
from commerceops.application.replenishment.contracts import Parameters
from commerceops.entrypoints import feishu_worker_child as entry
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_gateway_window import claim_gateway, guard_gateway
from commerceops.infrastructure.worker_lock import open_async
from psycopg import sql

from tests.p3_support import P3Fixture
from tests.p4_demo_factory import M1DemoFactory
from tests.p4_recovery_support import gateway, settings
from tests.test_p3_pg import fixture as fixture
from tests.test_p4_gateway_pg import message, service

pytestmark = pytest.mark.integration


def frozen(f: P3Fixture) -> dict[str, Any]:
    with connect(f.config.database) as db:
        result = {}
        for schema, tables in (
            (
                "business",
                (
                    "business_tasks",
                    "jobs",
                    "replenishment_plans",
                    "approvals",
                    "outbox",
                    "inbox_events",
                    "p4_inbox_receipts",
                    "analysis_reports",
                    "commerce_snapshots",
                    "p4_sdk_windows",
                    "p4_sdk_calls",
                    "p4_im_deliveries",
                    "p4_base_deliveries",
                ),
            ),
            (
                "checkpoints",
                ("checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations"),
            ),
        ):
            for table in tables:
                result[schema + "." + table] = db.execute(
                    sql.SQL(
                        "SELECT row_to_json(t)::text AS canonical FROM {}.{} t "
                        "ORDER BY row_to_json(t)::text"
                    ).format(sql.Identifier(schema), sql.Identifier(table))
                ).fetchall()
        return result


@pytest.mark.parametrize("kind", ["p2p", "group"])
@pytest.mark.parametrize("change", ["none", "app", "tenant", "allowlist", "remapped", "revoked"])
def test_current_platform_identity_denied_before_sdk_graph_queue_with_pg_and_cp_unchanged(
    fixture: P3Fixture,
    kind: str,
    change: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    f = fixture
    profile = "known70" if kind == "p2p" else "group20"
    original = gateway(f, case="known_inbound" if kind == "p2p" else "baseline", max_workflows=2)
    config = settings(f)
    assert isinstance(original.parameters, Parameters)
    with connect(f.config.database) as lease:
        claim_gateway(lease, config, original)
        store = service(
            f,
            original.parameters.fixture_case,
            gateway_guard=lambda db, create: guard_gateway(db, original, create),
        )
        task = UUID(store.message(message(f, kind=kind))["task_id"])
        window = ControlledWorkerWindow.model_validate_json(
            json.dumps(
                {
                    "schema_version": "p4-worker-v1",
                    "window_id": str(uuid4()),
                    "gateway_window_id": str(original.window_id),
                    "organization_id": str(config.organization_id),
                    "shop_id": str(config.shop_id),
                    "task_ids": [str(task)],
                    "expires_at": original.expires_at.isoformat(),
                    "caps": dict(KNOWN70_CAPS if profile == "known70" else GROUP20_CAPS),
                    "profile": profile,
                    "enabled": True,
                }
            )
        )
        with connect(f.config.database) as db:
            claimed = db.execute(
                "SELECT occurred_at FROM business.audit_events WHERE id=%s", (original.window_id,)
            ).fetchone()
            assert claimed
        if change in ("app", "tenant", "allowlist"):
            config = config.model_copy(
                update={
                    {"app": "app_id", "tenant": "tenant_key", "allowlist": "allowed_open_ids"}[
                        change
                    ]: frozenset({"not-allowed"}) if change == "allowlist" else "synthetic-mismatch"
                }
            )
        elif change == "remapped":
            # 只新owned测试数据的可变identity映射；原T1/receipt/requester不改。
            with connect(f.inventory.owner) as db:
                principal = uuid4()
                db.execute(
                    """INSERT INTO business.principals(id,organization_id,display_name,roles)
                VALUES(%s,%s,'synthetic remapped',ARRAY['operator'])""",
                    (principal, config.organization_id),
                )
                db.execute(
                    "UPDATE business.identities SET principal_id=%s WHERE provider='feishu'",
                    (principal,),
                )
        elif change == "revoked":
            with connect(f.inventory.owner) as db:
                db.execute(
                    "UPDATE business.principal_role_shop_grants SET enabled=false "
                    "WHERE role='operator'"
                )
        before = frozen(f)

        async def common() -> None:
            async with await open_async(f.config.database) as db:
                await entry.trusted_tasks(db, config, window, original, claimed["occurred_at"])

        if change == "none":
            asyncio.run(common())
            asyncio.run(entry.trusted_scope(f.config, config, window))
        else:
            # 共同selector直接验证wrong app/tenant（生产入口还会先拒绝Gateway scope）。
            with pytest.raises(PermissionError, match="P4_CONTROLLED_TASK_SCOPE_REQUIRED"):
                asyncio.run(common())
            with pytest.raises(PermissionError):
                asyncio.run(entry.trusted_scope(f.config, config, window))
            session = type("NoGraphSession", (), {"start": AsyncMock(), "close": AsyncMock()})()
            monkeypatch.setattr(entry, "WorkerSession", Mock(return_value=session))
            ledger, factory, graph, queue_scope = Mock(), Mock(), Mock(), AsyncMock()
            monkeypatch.setattr(entry, "PersistentSDKLedger", ledger)
            monkeypatch.setattr(entry, "BusinessSDKFactory", factory)
            monkeypatch.setattr(entry, "Worker", graph)
            monkeypatch.setattr(entry, "controlled_task_ids", queue_scope)
            result = asyncio.run(entry.controlled_work(config, window, f.config, M1DemoFactory()))
            assert result["result"] == "failed" and result["failure_category"] == "PermissionError"
            ledger.assert_not_called()
            factory.assert_not_called()
            graph.assert_not_called()
            queue_scope.assert_not_called()
            session.close.assert_awaited_once_with(clean=True)
        assert frozen(f) == before
