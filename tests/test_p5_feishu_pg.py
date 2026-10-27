"""新owned PG/Fake入站与传输；不使用旧资产、平台秘密或真实SDK。"""

import asyncio
import json
import traceback
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from commerceops.adapters.commerce.woocommerce_config import WooReadOnlyConfig
from commerceops.application.commerce.source_binding import SourceBindingError
from commerceops.application.feishu_business.clarification import F02Candidate
from commerceops.application.feishu_business.gateway_window import GatewayWindow
from commerceops.application.feishu_business.worker_window import (
    KNOWN70_CAPS,
    ControlledWorkerWindow,
)
from commerceops.application.replenishment.contracts import WebFailure, WooCreateParameters
from commerceops.entrypoints.feishu_gateway_child import BoundedReceiver
from commerceops.entrypoints.feishu_worker_child import trusted_scope
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_business import FeishuBusinessStore
from commerceops.infrastructure.feishu_gateway_window import claim_gateway, guard_gateway

from tests.p3_support import P3Fixture
from tests.p4_recovery_support import settings
from tests.test_p3_pg import fixture as fixture
from tests.test_p4_clarification_pg import business_counts
from tests.test_p4_f02_pg import incoming, request_row, turn
from tests.test_p4_gateway_pg import message, service
from tests.test_p5_sources_pg import (
    _actual_pg_woo_factory_two_graphs_t4_and_original_key_replay,
    configure,
)
from tests.test_woocommerce_readonly import config as config

pytestmark = pytest.mark.integration


def safe_failure_frames(function: Callable[..., None]) -> Callable[..., None]:
    @wraps(function)
    def run(*args: Any, **kwargs: Any) -> None:
        try:
            function(*args, **kwargs)
        except BaseException as error:
            print(
                "P5_FEISHU_TEST_FAILURE",
                type(error).__name__,
                [
                    (Path(frame.filename).name, frame.name, frame.lineno)
                    for frame in traceback.extract_tb(error.__traceback__)
                ],
                flush=True,
            )
            raise

    return run


def woo_service(f: P3Fixture, **kwargs: Any) -> FeishuBusinessStore:
    original = service(f)  # only a new synthetic Feishu identity in this fixture DB
    return FeishuBusinessStore(
        original.store,
        original.shop,
        WooCreateParameters(
            source_mode="woocommerce_test", source_config_version="owned-p5-v1", L=3, R=7, S=2
        ),
        **kwargs,
    )


def window_for(f: P3Fixture) -> GatewayWindow:
    return GatewayWindow(
        schema_version="p4-gateway-v1",
        window_id=uuid4(),
        organization_id=f.actor.organization_id,
        shop_id=f.inventory.data.shop,
        expires_at=datetime.now(UTC) + timedelta(seconds=180),
        enabled=True,
        parameters=WooCreateParameters(
            source_mode="woocommerce_test", source_config_version="owned-p5-v1", L=3, R=7, S=2
        ),
    )


@pytest.mark.parametrize("mode", ["t1", "f02"])
@safe_failure_frames
def test_formal_woo_inbound_source_graphs_and_frozen_queries(
    fixture: P3Fixture,
    config: WooReadOnlyConfig,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    f = fixture
    with ExitStack() as stack:
        selected: list[FeishuBusinessStore] = []

        def create(current: P3Fixture) -> UUID:
            gateway = window_for(current)
            sdk_settings = settings(current).model_copy(update={"f02_enabled": mode == "f02"})
            lease = stack.enter_context(connect(current.config.database))
            claim_gateway(
                lease, sdk_settings, gateway, commerce_sources=current.config.commerce_sources
            )
            store = woo_service(
                current,
                f02_enabled=mode == "f02",
                f02_gateway_window_id=gateway.window_id if mode == "f02" else None,
                gateway_guard=lambda db, create: guard_gateway(db, gateway, create),
            )
            selected.append(store)
            receiver = BoundedReceiver(store, gateway)
            before = business_counts(current)
            if mode == "t1":
                origin = message(current)
                receipt = receiver.message(origin)
            else:
                first = receiver.message(incoming(current, "分析库存 L=3"))
                assert business_counts(current) == before
                ready = receiver.message(turn(current, first))
                assert business_counts(current) == before
                candidate = F02Candidate.model_validate_json(
                    json.dumps(request_row(current, ready["clarification_id"])["candidate"])
                )
                assert candidate.source.source_mode == "woocommerce_test"
                assert "Woo测试店" in candidate.text() and "Mock" not in candidate.text()
                origin = turn(current, ready, confirm=True)
                receipt = receiver.message(origin)
            after = business_counts(current)
            for _ in range(10):
                assert receiver.message(origin)["task_id"] == receipt["task_id"]
            assert business_counts(current) == after
            assert after["business_tasks"] - before["business_tasks"] == 2
            task = UUID(receipt["task_id"])
            worker = ControlledWorkerWindow(
                schema_version="p4-worker-v1",
                window_id=uuid4(),
                gateway_window_id=gateway.window_id,
                organization_id=gateway.organization_id,
                shop_id=gateway.shop_id,
                task_ids=frozenset({task}),
                expires_at=gateway.expires_at,
                caps=dict(KNOWN70_CAPS),
                enabled=True,
            )
            worker.window(sdk_settings)
            asyncio.run(trusted_scope(current.config, sdk_settings, worker))
            return task

        task = _actual_pg_woo_factory_two_graphs_t4_and_original_key_replay(
            f,
            config,
            monkeypatch,
            create_task=create,
        )
        before = business_counts(f)
        report = f.client.get(f"/api/v1/tasks/{task}/report")
        assert report.status_code == 200
        with connect(f.config.database) as db:
            source = db.execute(
                "SELECT source_report_id FROM business.p3_task_sources WHERE task_id=%s", (task,)
            ).fetchone()
            assert source
        for text in (f"查询任务{task}进度", f"解释任务{task}的报告{source['source_report_id']}"):
            read = selected[0].message(replace(message(f), text=text))
            assert read["state"] == "read_completed"
            assert read["referenced_task_id"] == str(task)
            assert "error" not in read["facts"]
        assert business_counts(f) == before
        assert '"source_kind":"woocommerce_test"' in report.text.replace(" ", "")


@safe_failure_frames
def test_woo_gateway_and_f02_confirm_reject_same_version_drift_before_tasks(
    fixture: P3Fixture,
) -> None:
    f = fixture
    metadata, path = configure(f)
    store = woo_service(f, f02_enabled=True)
    first = store.message(incoming(f, "分析库存 L=3 R=7 S=2"))
    before = business_counts(f)
    changed = metadata.model_dump(mode="json")
    changed["origin"] = "https://127.0.0.1:29443"
    path.write_text(json.dumps(changed))
    with pytest.raises(WebFailure) as rejected:
        store.message(turn(f, first, confirm=True))
    assert rejected.value.code == "COMMERCE_SOURCE_UNAVAILABLE"
    assert business_counts(f) == before
    gateway = window_for(f)
    with pytest.raises(SourceBindingError), connect(f.config.database) as db:
        claim_gateway(db, settings(f), gateway, commerce_sources=f.config.commerce_sources)
    with connect(f.config.database) as db:
        assert db.execute(
            "SELECT count(*) AS n FROM business.audit_events WHERE id=%s", (gateway.window_id,)
        ).fetchone() == {"n": 0}


@pytest.mark.parametrize("outcome", ["sent", "unknown"])
@safe_failure_frames
def test_woo_f02_official_selection_worker_with_fake_sdk_keeps_once_and_no_base(
    fixture: P3Fixture,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    from tests import test_p4_f02_pg as original

    configure(fixture)
    monkeypatch.setattr(original, "service", woo_service)
    original.test_runtime_gateway_selected_chain_original_worker_ledger_and_no_Base(
        fixture,
        monkeypatch,
        outcome,
        window_seconds=40,
    )
