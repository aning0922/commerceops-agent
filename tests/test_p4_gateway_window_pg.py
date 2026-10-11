"""新A06必要PG gate，须Root新owned scope：Fake入站/no SDK、原business quota。"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.application.feishu_business.gateway_window import GatewayWindow
from commerceops.application.replenishment.contracts import WebFailure
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_gateway_window import claim_gateway, guard_gateway
from psycopg.errors import UniqueViolation

from tests.p3_support import P3Fixture
from tests.test_p3_pg import fixture as fixture
from tests.test_p4_gateway_pg import counts, message, service

pytestmark = pytest.mark.integration


def test_once_app_lease_original_replay_quota_and_expiry_have_no_duplicate_business(
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
                "expires_at": (datetime.now(UTC) + timedelta(minutes=2)).isoformat(),
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
    guarded = service(f, gateway_guard=lambda db, create: guard_gateway(db, window, create))
    with connect(f.config.database) as lease:
        claim_gateway(lease, settings, window)
        before = counts(f)
        wrong_shop = window.model_copy(update={"shop_id": uuid4()})
        assert wrong_shop.organization_id == window.organization_id
        changed_payloads = (
            wrong_shop,
            window.model_copy(update={"parameters": window.parameters.model_copy(update={"L": 4})}),
            window.model_copy(update={"max_workflows": 2}),
            window.model_copy(update={"max_callbacks": 99}),
            window.model_copy(update={"enabled": False}),
        )
        for denied in changed_payloads:
            rejecting = service(
                f, gateway_guard=lambda db, create, denied=denied: guard_gateway(db, denied, create)
            )
            with pytest.raises(WebFailure, match="GATEWAY_WINDOW_CLOSED"):
                rejecting.message(message(f))
            assert counts(f) == before
        with (
            connect(f.config.database) as rival,
            pytest.raises(PermissionError, match="P4_GATEWAY_ALREADY_RUNNING"),
        ):
            claim_gateway(rival, settings, window.model_copy(update={"window_id": uuid4()}))
        incoming = message(f)
        first = guarded.message(incoming)
        after = counts(f)
        assert guarded.message(incoming)["task_id"] == first["task_id"] and counts(f) == after
        with pytest.raises(WebFailure, match="GATEWAY_WORKFLOW_CAP_EXHAUSTED"):
            guarded.message(message(f))
        assert counts(f) == after
        expired = window.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
        with (
            connect(f.config.database) as db,
            pytest.raises(WebFailure, match="GATEWAY_WINDOW_CLOSED"),
        ):
            guard_gateway(db, expired, False)
        assert counts(f) == after
    with connect(f.config.database) as next_instance, pytest.raises(UniqueViolation):
        claim_gateway(next_instance, settings, window)
    assert counts(f) == after
