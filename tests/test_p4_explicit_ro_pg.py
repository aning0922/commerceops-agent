"""新owned PG+Fake：自动attempts3保持，单次人工RO独立消费；不读原库/Secret。"""

import asyncio
import json
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from commerceops.adapters.feishu.business_base import BusinessBaseAdapter
from commerceops.adapters.feishu.projection_contract import ApiReply
from commerceops.application.feishu_business.delivery import DeliveryGate
from commerceops.application.feishu_business.sdk_window import SDKScope
from commerceops.application.feishu_business.worker_window import ControlledWorkerWindow
from commerceops.domain.commerce_values import facts_hash
from commerceops.entrypoints.feishu_business import confirm_worker_child
from commerceops.entrypoints.feishu_worker_child import trusted_scope
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_base_delivery import BaseDeliveryStore
from commerceops.infrastructure.feishu_outbox_recovery import sdk_window_hash
from commerceops.infrastructure.feishu_sdk_ledger import PersistentSDKLedger
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.worker_lock import WorkerSession
from psycopg import sql

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
from tests.test_p4_sender_recovery_pg import prepared_sender

pytestmark = pytest.mark.integration


class ReaderRecords(RecordedRecords):
    """新Fake调用用SDK response形状落ledger，再把ApiReply交adapter；不补写旧回执。"""

    async def list(self, *args: Any, **kwargs: Any) -> ApiReply:
        async def call() -> Any:
            reply = await super(RecordedRecords, self).list(*args, **kwargs)
            return SimpleNamespace(
                raw=SimpleNamespace(status_code=reply.http_status), code=reply.code, reply=reply
            )

        response = await self.ledger.invoke("bitable.v1.app_table_record.list", call)
        return cast(ApiReply, response.reply)


def gate(window: ControlledWorkerWindow, *, explicit: bool) -> DeliveryGate:
    assert window.recovery
    return DeliveryGate(
        window.organization_id,
        window.shop_id,
        window.task_ids,
        "test",
        window.expires_at,
        enabled=True,
        verification_mode="controlled_sdk",
        outbox_ids=frozenset(p.outbox_id for p in window.recovery.projections),
        explicit_ro_window_id=window.window_id if explicit else None,
    )


async def failed_reader(
    config_file: Path, window_file: Path, rows_file: Path, output: Path
) -> None:
    config = WebConfig.from_file(config_file)
    window = ControlledWorkerWindow.model_validate_json(window_file.read_text())
    from commerceops.adapters.feishu.business_config import BusinessSettings

    business = BusinessSettings.model_validate_json(
        (window_file.parent / "sender-business.json").read_text()
    )
    session = WorkerSession(config.database, window.organization_id)
    await session.start()
    try:
        await trusted_scope(config, business, window)
        ledger = PersistentSDKLedger(session, window.window(business))

        async def authentication() -> Any:
            return SimpleNamespace(raw=SimpleNamespace(status_code=200), code=0)

        with ledger.scope(SDKScope(window.window_id, None, "preflight")):
            await ledger.invoke("auth.v3.tenant_access_token.internal", authentication)
        rows = json.loads(rows_file.read_text())["rows"]
        # 新wire规则仍拒required缺失，制造真实失败RO3并保留真实ledger/audit/lifecycle。
        del rows[0]["fields"]["SKU"]
        fake = ReaderRecords(ledger, rows=rows)
        store = BaseDeliveryStore(
            session,
            BusinessBaseAdapter(fake, {"test": ("fake", "fake")}),
            gate(window, explicit=False),
            ledger,
        )
        with connect(config.database) as db:
            db.execute("UPDATE business.p4_base_deliveries SET next_attempt_at=clock_timestamp()")
        assert await store.dispatch_one() == "unknown"
        assert [c[0] for c in fake.calls] == ["query"]
        write_private(output, {"owner": session.owner})
    finally:
        await session.close(clean=True)


@contextmanager
def prepared_recheck(f: P3Fixture) -> Any:
    with prepared_sender(f) as (reader, _, rows_file):
        window_file, output = f.private / "reader-window.json", f.private / "reader-owner.json"
        write_private(window_file, reader.model_dump(mode="json"))
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import asyncio,sys;from pathlib import Path;"
                "from tests.test_p4_explicit_ro_pg import failed_reader;"
                "asyncio.run(failed_reader(*(Path(p) for p in sys.argv[1:])))",
                str(f.config_file),
                str(window_file),
                str(rows_file),
                str(output),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            _, errors = child.communicate(timeout=20)
            if child.returncode:
                diagnostic = f.private / "reader-failure.private.txt"
                diagnostic.write_bytes(errors)
                diagnostic.chmod(0o600)
                raise AssertionError("reader child failed; protected stderr preserved")
            asyncio.run(confirm_worker_child(f.config, reader.organization_id, child.pid))
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
    new = gateway(f, max_workflows=0)
    replacement = start_gateway(f, new)
    try:
        with connect(f.config.database) as db:
            sdk = db.execute(
                "SELECT * FROM business.p4_sdk_windows WHERE id=%s", (reader.window_id,)
            ).fetchone()
            claim = db.execute(
                "SELECT after_state FROM business.audit_events WHERE id=%s", (reader.window_id,)
            ).fetchone()
            gw_claim = db.execute(
                "SELECT after_state FROM business.audit_events WHERE id=%s",
                (reader.gateway_window_id,),
            ).fetchone()
            gw_end = db.execute(
                "SELECT id FROM business.audit_events WHERE entity_id=%s "
                "AND source='feishu_gateway' AND action='termination_confirmed'",
                (str(reader.gateway_window_id),),
            ).fetchone()
            owner = json.loads(output.read_text())["owner"]
            worker_end = db.execute(
                "SELECT id FROM business.audit_events WHERE entity_id=%s "
                "AND source='worker' AND action='termination_confirmed'",
                (owner,),
            ).fetchone()
            assert sdk and claim and gw_claim and gw_end and worker_end
        value = reader.model_dump(mode="json")
        value.update(
            window_id=str(uuid4()),
            gateway_window_id=str(new.window_id),
            expires_at=new.expires_at.isoformat(),
        )
        value["recovery"].update(
            worker_window_id=value["window_id"],
            gateway_window_id=value["gateway_window_id"],
            expires_at=value["expires_at"],
        )
        value["recovery"]["explicit_ro_recheck"] = {
            "recheck_count": 1,
            "reader_window_id": str(reader.window_id),
            "reader_window_hash": sdk_window_hash(sdk),
            "reader_claim_hash": facts_hash(claim["after_state"]),
            "reader_owner": owner,
            "reader_termination_id": str(worker_end["id"]),
            "reader_gateway": {
                "gateway_id": str(reader.gateway_window_id),
                "gateway_hash": facts_hash(gw_claim["after_state"]),
                "termination_id": str(gw_end["id"]),
            },
        }
        yield ControlledWorkerWindow.model_validate_json(json.dumps(value)), new, rows_file
    finally:
        stop_gateway(f, new, replacement)


def preserved_core_cp(f: P3Fixture) -> Any:
    with connect(f.config.database) as db:
        cp = {
            name: db.execute(
                sql.SQL("SELECT row_to_json(t) AS body FROM checkpoints.{} t").format(
                    sql.Identifier(name)
                )
            ).fetchall()
            for name in (
                "checkpoints",
                "checkpoint_blobs",
                "checkpoint_writes",
                "checkpoint_migrations",
            )
        }
    return preserved(f), cp


@pytest.mark.parametrize("missing_required", [False, True])
def test_explicit_ro_single_consumption_concurrent_repeat_and_failure_spent(
    fixture: P3Fixture,
    missing_required: bool,
) -> None:
    f = fixture
    with prepared_recheck(f) as (window, _, rows_file):
        before = preserved_core_cp(f)
        # 当前授权之前，逐项错误lineage/撤权都必须拒绝且0 SDK。
        for change in (
            "reader_window_hash",
            "reader_claim_hash",
            "reader_termination_id",
            "gateway_hash",
            "gateway_end",
            "reader_owner",
            "projection",
        ):
            value = window.model_dump(mode="json")
            reader = value["recovery"]["explicit_ro_recheck"]
            if change in ("gateway_hash", "gateway_end"):
                key = "gateway_hash" if change == "gateway_hash" else "termination_id"
                reader["reader_gateway"][key] = "c" * 64 if "hash" in key else str(uuid4())
            elif change == "projection":
                value["recovery"]["projections"][0]["request_hash"] = "c" * 64
            else:
                reader[change] = "c" * 64 if "hash" in change else str(uuid4())
            wrong = ControlledWorkerWindow.model_validate_json(json.dumps(value))
            with pytest.raises(PermissionError):
                asyncio.run(trusted_scope(f.config, settings(f), wrong))
            with connect(f.config.database) as db:
                assert db.execute(
                    "SELECT count(*) AS n FROM business.p4_sdk_calls WHERE window_id=%s",
                    (window.window_id,),
                ).fetchone() == {"n": 0}

        value = window.model_dump(mode="json")
        value["window_id"] = str(uuid4())
        value["recovery"]["worker_window_id"] = value["window_id"]
        other = ControlledWorkerWindow.model_validate_json(json.dumps(value))

        async def authorize_once() -> ControlledWorkerWindow:
            results = await asyncio.gather(
                trusted_scope(f.config, settings(f), window),
                trusted_scope(f.config, settings(f), other),
                return_exceptions=True,
            )
            from commerceops.infrastructure.feishu_outbox_recovery import ReaderStage

            allowed = {s.value for s in ReaderStage} | {"P4_APPROVED_OUTBOX_RECOVERY_DENIED"}
            safe = {
                "successes": sum(r is None for r in results),
                "exception_classes": [
                    type(r).__name__ if isinstance(r, BaseException) else None for r in results
                ],
                "fixed_stage_codes": [
                    str(r) if isinstance(r, PermissionError) and str(r) in allowed else None
                    for r in results
                ],
            }
            output = f.private / "manual-admission.safe.json"
            output.write_text(json.dumps(safe, indent=2) + "\n")
            output.chmod(0o600)
            assert sum(r is None for r in results) == 1
            assert sum(isinstance(r, PermissionError) for r in results) == 1
            return window if results[0] is None else other

        window = asyncio.run(authorize_once())

        async def repeated_authorize() -> None:
            results = await asyncio.gather(
                trusted_scope(f.config, settings(f), window),
                trusted_scope(f.config, settings(f), other),
                return_exceptions=True,
            )
            assert all(isinstance(r, PermissionError) for r in results)

        asyncio.run(repeated_authorize())
        due(f)

        async def run() -> None:
            session = WorkerSession(f.config.database, window.organization_id)
            await session.start()
            try:
                ledger = PersistentSDKLedger(session, window.window(settings(f)))
                rows = json.loads(rows_file.read_text())["rows"]
                fields = rows[0]["fields"]
                fields["Quantity"], fields["SyncVersion"] = str(fields["Quantity"]), "1"
                for key in ("ResolutionReason", "ResolvedBy", "ResolvedAt"):
                    del fields[key]
                if missing_required:
                    del fields["SKU"]
                fake = RecordedRecords(ledger, rows=rows)
                store = BaseDeliveryStore(
                    session,
                    BusinessBaseAdapter(fake, {"test": ("fake", "fake")}),
                    gate(window, explicit=True),
                    ledger,
                )
                outcomes = await asyncio.gather(store.dispatch_one(), store.dispatch_one())
                assert sorted(outcomes) == sorted(
                    ["idle", "unknown" if missing_required else "verified"]
                )
                assert await store.dispatch_one() == "idle"
                assert [c[0] for c in fake.calls] == ["query"]
            finally:
                await session.close(clean=True)

        asyncio.run(run())
        assert preserved_core_cp(f) == before
        with connect(f.config.database) as db:
            assert db.execute(
                "SELECT status,attempts FROM business.p4_base_deliveries"
            ).fetchall() == [
                {"status": "unknown" if missing_required else "verified", "attempts": 3}
            ]
            assert db.execute("SELECT count(*) AS n FROM business.p4_base_links").fetchone() == {
                "n": 0 if missing_required else 1
            }
            assert db.execute(
                "SELECT action,count(*) AS n FROM business.audit_events WHERE "
                "action LIKE 'explicit_ro_recheck_%' GROUP BY action ORDER BY action"
            ).fetchall() == [
                {"action": "explicit_ro_recheck_authorized", "n": 1},
                {"action": "explicit_ro_recheck_dispatched", "n": 1},
            ]
            assert db.execute(
                "SELECT method,count(*) AS n FROM business.p4_sdk_calls WHERE "
                "window_id=%s GROUP BY method",
                (window.window_id,),
            ).fetchall() == [{"method": "bitable.v1.app_table_record.list", "n": 1}]
        with pytest.raises(PermissionError):
            asyncio.run(trusted_scope(f.config, settings(f), other))


def test_revoked_approver_denies_manual_ro_before_any_request(fixture: P3Fixture) -> None:
    f = fixture
    with prepared_recheck(f) as (window, _, _):
        with connect(f.inventory.owner) as db:
            db.execute(
                "UPDATE business.principal_role_shop_grants SET enabled=false WHERE role='approver'"
            )
        with pytest.raises(PermissionError):
            asyncio.run(trusted_scope(f.config, settings(f), window))
        with connect(f.config.database) as db:
            assert db.execute(
                "SELECT count(*) AS n FROM business.p4_sdk_calls WHERE window_id=%s",
                (window.window_id,),
            ).fetchone() == {"n": 0}
            assert db.execute(
                "SELECT count(*) AS n FROM business.audit_events WHERE "
                "action LIKE 'explicit_ro_recheck_%'"
            ).fetchone() == {"n": 0}
            assert db.execute(
                "SELECT status,attempts FROM business.p4_base_deliveries"
            ).fetchall() == [{"status": "unknown", "attempts": 3}]
