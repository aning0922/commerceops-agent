"""新owned PG/三Gateway真实生命周期；SDK Fake，原库/Secret/平台请求0。"""

import asyncio
import json
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from commerceops.adapters.feishu.business_base import BusinessBaseAdapter
from commerceops.application.feishu_business.delivery import DeliveryGate
from commerceops.application.feishu_business.sdk_window import SDKScope
from commerceops.application.feishu_business.worker_window import (
    READONLY_RECOVERY_CAPS,
    ControlledWorkerWindow,
)
from commerceops.domain.commerce_values import facts_hash
from commerceops.entrypoints.feishu_business import confirm_worker_child
from commerceops.entrypoints.feishu_worker_child import trusted_scope
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_base_delivery import BaseDeliveryStore
from commerceops.infrastructure.feishu_outbox_recovery import receipt_hash, sdk_window_hash
from commerceops.infrastructure.feishu_sdk_ledger import PersistentSDKLedger
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.worker_lock import WorkerSession

from tests.p3_support import P3Fixture
from tests.p4_recovery_support import (
    RecordedRecords,
    gateway,
    settings,
    start_gateway,
    stop_gateway,
    write_private,
)
from tests.test_p3_pg import fixture as fixture
from tests.test_p4_a08_recovery_pg import preserved
from tests.test_p4_delivery_pg import due
from tests.test_p4_first_create_pg import AckDropRecords, original_c0

pytestmark = pytest.mark.integration


async def sender_child(config_file: Path, window_file: Path, output: Path) -> None:
    config = WebConfig.from_file(config_file)
    window = ControlledWorkerWindow.model_validate_json(window_file.read_text())
    # 与正式路径相同顺序：真实Worker started -> trusted scope claim -> SDK ledger。
    session = WorkerSession(config.database, window.organization_id)
    await session.start()
    try:
        from commerceops.adapters.feishu.business_config import BusinessSettings

        business = BusinessSettings.model_validate_json(
            (window_file.parent / "sender-business.json").read_text()
        )
        await trusted_scope(config, business, window)
        ledger = PersistentSDKLedger(session, window.window(business))
        from types import SimpleNamespace

        async def authentication() -> Any:
            return SimpleNamespace(raw=SimpleNamespace(status_code=200), code=0)

        with ledger.scope(SDKScope(window.window_id, None, "preflight")):
            await ledger.invoke("auth.v3.tenant_access_token.internal", authentication)
        fake = AckDropRecords(ledger)
        store = BaseDeliveryStore(
            session,
            BusinessBaseAdapter(fake, {"test": ("fake", "fake")}),
            DeliveryGate(
                window.organization_id,
                window.shop_id,
                window.task_ids,
                "test",
                window.expires_at,
                enabled=True,
                verification_mode="controlled_sdk",
                first_create=window.first_create,
                first_create_window_id=window.window_id,
            ),
            ledger,
        )
        with connect(config.database) as db:
            db.execute("UPDATE business.p4_base_deliveries SET next_attempt_at=clock_timestamp()")
        assert await store.dispatch_one() == "unknown"
        assert [c[0] for c in fake.calls] == ["query", "create"]
        write_private(output, {"rows": fake.rows, "owner": session.owner})
    finally:
        await session.close(clean=True)


@contextmanager
def prepared_sender(f: P3Fixture) -> Any:
    with original_c0(f) as sender:
        cfg, win, output = (
            f.config_file,
            f.private / "sender-window.json",
            f.private / "sender-rows.json",
        )
        write_private(win, sender.model_dump(mode="json"))
        write_private(f.private / "sender-business.json", settings(f).model_dump(mode="json"))
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import asyncio,sys;from pathlib import Path;"
                "from tests.test_p4_sender_recovery_pg import sender_child;"
                "asyncio.run(sender_child(*(Path(p) for p in sys.argv[1:])))",
                str(cfg),
                str(win),
                str(output),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            _, errors = child.communicate(timeout=20)
            if child.returncode:
                diagnostic = f.private / "sender-failure.private.txt"
                diagnostic.write_bytes(errors)
                diagnostic.chmod(0o600)
                raise AssertionError("sender child failed; protected stderr preserved")
            asyncio.run(confirm_worker_child(f.config, sender.organization_id, child.pid))
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
    new = gateway(f, max_workflows=0)
    replacement = start_gateway(f, new)
    try:
        assert sender.workflow_recovery and sender.first_create
        original = sender.workflow_recovery
        with connect(f.config.database) as db:
            approval = db.execute(
                "SELECT * FROM business.approvals WHERE id=%s", (original.approval_id,)
            ).fetchone()
            receipt = db.execute(
                "SELECT r.*,i.payload_hash FROM business.p4_inbox_receipts r "
                "JOIN business.inbox_events i ON i.id=r.inbox_id WHERE r.inbox_id=%s",
                (original.inbox_id,),
            ).fetchone()
            sdk = db.execute(
                "SELECT * FROM business.p4_sdk_windows WHERE id=%s", (sender.window_id,)
            ).fetchone()
            sender_claim = db.execute(
                "SELECT after_state FROM business.audit_events WHERE id=%s",
                (sender.gateway_window_id,),
            ).fetchone()
            sender_end = db.execute(
                "SELECT id FROM business.audit_events WHERE entity_id=%s "
                "AND source='feishu_gateway' AND action='termination_confirmed'",
                (str(sender.gateway_window_id),),
            ).fetchone()
            owner = json.loads(output.read_text())["owner"]
            worker_end = db.execute(
                "SELECT id FROM business.audit_events WHERE entity_id=%s "
                "AND source='worker' AND action='termination_confirmed'",
                (owner,),
            ).fetchone()
            assert approval and receipt and sdk and sender_claim and sender_end and worker_end
        value = sender.model_dump(mode="json")
        value.update(
            window_id=str(uuid4()),
            gateway_window_id=str(new.window_id),
            expires_at=new.expires_at.isoformat(),
            profile="approved_outbox",
            caps=dict(READONLY_RECOVERY_CAPS),
            workflow_recovery=None,
            first_create=None,
        )
        value["recovery"] = {
            "schema_version": "p4-approved-outbox-v1",
            "worker_window_id": value["window_id"],
            "gateway_window_id": value["gateway_window_id"],
            "expires_at": value["expires_at"],
            "original_gateway_id": str(original.original_gateway_id),
            "original_gateway_hash": original.original_gateway_hash,
            "gateway_termination_id": str(original.gateway_termination_id),
            "worker_owner": owner,
            "worker_termination_id": str(worker_end["id"]),
            "original_sdk_window_id": str(sender.window_id),
            "original_sdk_window_hash": sdk_window_hash(sdk),
            "task_id": str(original.task_id),
            "task_version": original.task_version,
            "inbox_id": str(original.inbox_id),
            "receipt_hash": receipt_hash(receipt),
            "plan_id": str(approval["plan_id"]),
            "plan_version": approval["plan_version"],
            "plan_hash": approval["plan_hash"],
            "approval_id": str(approval["id"]),
            "decision_id": str(approval["decision_id"]),
            "execution_id": str(original.execution_id),
            "operator_auth_version": original.operator_auth_version,
            "approver_auth_version": approval["decided_auth_version"],
            "target_key": "test",
            "projections": [sender.first_create.model_dump(mode="json")],
            "sender_gateway": {
                "gateway_id": str(sender.gateway_window_id),
                "gateway_hash": facts_hash(sender_claim["after_state"]),
                "termination_id": str(sender_end["id"]),
            },
        }
        yield ControlledWorkerWindow.model_validate_json(json.dumps(value)), new, output
    finally:
        stop_gateway(f, new, replacement)


def test_origin_sender_reconcile_lineage_single_RO_anchor_no_duplicate_execution(
    fixture: P3Fixture,
) -> None:
    f = fixture
    with prepared_sender(f) as (window, _, output):
        before = preserved(f)
        with connect(f.config.database) as db:
            cp = db.execute(
                "SELECT row_to_json(t) AS body FROM checkpoints.checkpoints t"
            ).fetchall()
        asyncio.run(trusted_scope(f.config, settings(f), window))
        due(f)

        async def run() -> None:
            session = WorkerSession(f.config.database, window.organization_id)
            await session.start()
            try:
                ledger = PersistentSDKLedger(session, window.window(settings(f)))
                fake = RecordedRecords(ledger, rows=json.loads(output.read_text())["rows"])
                assert window.recovery
                gate = DeliveryGate(
                    window.organization_id,
                    window.shop_id,
                    window.task_ids,
                    "test",
                    window.expires_at,
                    enabled=True,
                    verification_mode="controlled_sdk",
                    outbox_ids=frozenset(p.outbox_id for p in window.recovery.projections),
                )
                store = BaseDeliveryStore(
                    session, BusinessBaseAdapter(fake, {"test": ("fake", "fake")}), gate, ledger
                )
                assert await store.dispatch_one() == "verified"
                assert await store.dispatch_one() == "idle"
                assert [call[0] for call in fake.calls] == ["query"]
            finally:
                await session.close(clean=True)

        asyncio.run(run())
        assert preserved(f) == before
        with connect(f.config.database) as db:
            assert (
                db.execute(
                    "SELECT row_to_json(t) AS body FROM checkpoints.checkpoints t"
                ).fetchall()
                == cp
            )
            assert db.execute(
                "SELECT status,attempts FROM business.p4_base_deliveries"
            ).fetchall() == [{"status": "verified", "attempts": 3}]
            assert db.execute("SELECT count(*) AS n FROM business.p4_base_links").fetchone() == {
                "n": 1
            }
            assert db.execute(
                "SELECT method,count(*) AS n FROM business.p4_sdk_calls "
                "WHERE window_id=%s GROUP BY method",
                (window.window_id,),
            ).fetchall() == [{"method": "bitable.v1.app_table_record.list", "n": 1}]


def test_sender_lineage_rejects_rebound_permission_and_unterminated_evidence(
    fixture: P3Fixture,
) -> None:
    f = fixture
    with prepared_sender(f) as (window, _, _):
        for change in (
            "sender_id",
            "sender_hash",
            "sender_end",
            "origin_hash",
            "worker_end",
            "sdk_hash",
            "sdk_span",
            "receipt",
            "token",
            "projection",
            "role",
            "expiry",
            "create_history",
        ):
            value = window.model_dump(mode="json")
            r = value["recovery"]
            if change.startswith("sender_"):
                key = {
                    "sender_id": "gateway_id",
                    "sender_hash": "gateway_hash",
                    "sender_end": "termination_id",
                }[change]
                r["sender_gateway"][key] = "c" * 64 if key.endswith("hash") else str(uuid4())
            elif change == "sdk_span":
                # 用确实存在、hash正确但属于原入站Gateway的旧SDK，必须在sender span拒绝。
                with connect(f.config.database) as db:
                    claim = db.execute(
                        "SELECT after_state FROM business.audit_events WHERE id=%s",
                        (UUID(r["original_sdk_window_id"]),),
                    ).fetchone()
                    assert claim
                    old_id = UUID(
                        claim["after_state"]["workflow_recovery"]["original_sdk_window_id"]
                    )
                    old_sdk = db.execute(
                        "SELECT * FROM business.p4_sdk_windows WHERE id=%s",
                        (old_id,),
                    ).fetchone()
                    assert old_sdk
                r["original_sdk_window_id"] = str(old_id)
                r["original_sdk_window_hash"] = sdk_window_hash(old_sdk)
            elif change in {"origin_hash", "worker_end", "sdk_hash", "receipt"}:
                key = {
                    "origin_hash": "original_gateway_hash",
                    "worker_end": "worker_termination_id",
                    "sdk_hash": "original_sdk_window_hash",
                    "receipt": "receipt_hash",
                }[change]
                r[key] = "c" * 64 if key.endswith("hash") else str(uuid4())
            elif change in {"token", "projection"}:
                key = "client_token" if change == "token" else "projection_hash"
                r["projections"][0][key] = str(uuid4()) if change == "token" else "c" * 64
            elif change == "expiry":
                from datetime import timedelta

                value["expires_at"] = (window.expires_at + timedelta(seconds=1)).isoformat()
                r["expires_at"] = value["expires_at"]
            elif change == "role":
                with connect(f.inventory.owner) as db:
                    db.execute(
                        "UPDATE business.principal_role_shop_grants SET enabled=false "
                        "WHERE role='approver'"
                    )
            else:
                # 独立Fake ledger预占第二次C；不违反既有attempt不可回退保护。
                async def extra_history() -> None:
                    from datetime import UTC, datetime, timedelta
                    from types import SimpleNamespace

                    from commerceops.application.feishu_business.sdk_window import SDKWindow

                    assert window.recovery
                    session = WorkerSession(f.config.database, window.organization_id)
                    await session.start()
                    try:
                        ledger = PersistentSDKLedger(
                            session,
                            SDKWindow(
                                uuid4(),
                                window.organization_id,
                                window.shop_id,
                                datetime.now(UTC) + timedelta(seconds=30),
                                {"bitable.v1.app_table_record.create": 1},
                                enabled=True,
                                verification_mode="controlled_sdk",
                            ),
                        )

                        async def fake_returned() -> Any:
                            return SimpleNamespace(raw=SimpleNamespace(status_code=200), code=0)

                        p = window.recovery.projections[0]
                        with ledger.scope(
                            SDKScope(p.outbox_id, window.recovery.task_id, "base_projection")
                        ):
                            await ledger.invoke("bitable.v1.app_table_record.create", fake_returned)
                    finally:
                        await session.close(clean=True)

                asyncio.run(extra_history())
            if change == "role":
                # 后续负例还核同原有效角色；不把一次撤销留给无关case。
                restore_role = True
            else:
                restore_role = False
            wrong = ControlledWorkerWindow.model_validate_json(json.dumps(value))
            before = preserved(f)
            with pytest.raises(PermissionError):
                asyncio.run(trusted_scope(f.config, settings(f), wrong))
            assert preserved(f) == before
            with connect(f.config.database) as db:
                assert db.execute(
                    "SELECT count(*) AS n FROM business.p4_sdk_calls WHERE window_id=%s",
                    (window.window_id,),
                ).fetchone() == {"n": 0}
            if restore_role:
                with connect(f.inventory.owner) as db:
                    db.execute(
                        "UPDATE business.principal_role_shop_grants SET enabled=true "
                        "WHERE role='approver'"
                    )
