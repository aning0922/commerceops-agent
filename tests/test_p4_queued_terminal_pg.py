"""双schema真实queued v1→停写后T6结算→唯一v2；进程重放不能再update。"""

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from commerceops.application.feishu_business.worker_window import ControlledWorkerWindow
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.worker_lock import TerminationRequired

from scripts.p4_acceptance import Deadline, terminal_window_from_native, write_private
from scripts.p4_terminal_state import classify_t6, collect_final_t6
from tests.p4_acceptance_support import AcceptanceFixture, reference
from tests.p4_queued_terminal_support import verified_queued_origin
from tests.test_p4_acceptance_pg import database as database
from tests.test_p4_acceptance_pg import initialize_schema

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("revision", ["0015", "0016"])
def test_queued_v1_late_T6_final_capture_once_and_native_v2(
    database: tuple[DatabaseSettings, DatabaseSettings],
    tmp_path: Path,
    revision: str,
) -> None:
    owner, app = database
    initialize_schema(owner, revision)
    expires = datetime.now(UTC) + timedelta(minutes=10)
    if os.environ.get("COMMERCEOPS_ACCEPTANCE_DEADLINE"):
        expires = min(
            expires, datetime.fromisoformat(os.environ["COMMERCEOPS_ACCEPTANCE_DEADLINE"])
        )
    a = AcceptanceFixture.prepare(
        owner, app, tmp_path, Deadline.register(expires), case_kind="recover_single_item"
    )
    writer = None
    try:
        known = verified_queued_origin(a)
        f = a.fixture
        task, item = known["delivery"]["task_id"], known["delivery"]["item_id"]
        with connect(app) as db:
            writers = [
                r["after_state"]
                for r in db.execute(
                    "SELECT after_state FROM business.audit_events WHERE organization_id=%s "
                    "AND source IN ('worker','feishu_gateway') AND action='started'",
                    (f.actor.organization_id,),
                ).fetchall()
            ]
        first = collect_final_t6(
            app,
            f.actor.organization_id,
            f.inventory.data.shop,
            task,
            writers=writers,
            output=tmp_path / "first.json",
        )
        assert first == dict(state="UNCOMMITTED", permit_human_close=True, request_key=None)
        key = uuid4()

        def request(name: str, *, version: int, pause: bool) -> dict[str, Any]:
            value: dict[str, Any] = dict(
                config=str(f.config_file),
                session=f.client.cookies.get("commerceops_session"),
                item_id=str(item),
                request=dict(
                    schema_version="p3-web-v1",
                    request_key=str(key),
                    action="close",
                    reason="synthetic late native T6",
                    expected_version=version,
                ),
                pause=pause,
                ready=str(tmp_path / (name + "-ready.json")),
                release=str(tmp_path / (name + "-release")),
                result=str(tmp_path / (name + "-result.json")),
            )
            p = tmp_path / (name + "-input.json")
            write_private(p, value)
            value["argv"] = [
                sys.executable,
                "-m",
                "tests.p4_t6_writer_process",
                str(p),
                reference(p)["sha256"],
            ]
            return value

        rejected = request("rejected", version=2, pause=False)
        assert (
            subprocess.run(
                rejected["argv"], check=False, capture_output=True, timeout=20
            ).returncode
            == 1
        )
        assert (
            collect_final_t6(
                app,
                f.actor.organization_id,
                f.inventory.data.shop,
                task,
                writers=writers,
                output=tmp_path / "after-reject.json",
            )["state"]
            == "UNCOMMITTED"
        )
        pending = request("late", version=1, pause=True)
        writer = subprocess.Popen(
            pending["argv"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        end = time.monotonic() + 20
        while not Path(pending["ready"]).exists():
            assert writer.poll() is None and time.monotonic() < end
            time.sleep(0.02)
        process = json.loads(Path(pending["ready"]).read_text())
        with pytest.raises(TerminationRequired, match="old process still exists"):
            collect_final_t6(
                app,
                f.actor.organization_id,
                f.inventory.data.shop,
                task,
                writers=[*writers, process],
                output=tmp_path / "too-early.json",
            )
        assert not (tmp_path / "too-early.json").exists()
        # 此时旧式提前快照仍是open；真实事务随后commit，最终收集必须等writer退出。
        with connect(app) as db:
            assert db.execute(
                "SELECT status FROM business.replenishment_items WHERE id=%s", (item,)
            ).fetchone() == {"status": "open"}
        Path(pending["release"]).touch(mode=0o600)
        assert writer.wait(timeout=20) == 0
        state = collect_final_t6(
            app,
            f.actor.organization_id,
            f.inventory.data.shop,
            task,
            writers=[*writers, process],
            output=tmp_path / "final-T6.json",
        )
        assert state == dict(state="COMMITTED", permit_human_close=False, request_key=str(key))
        assert classify_t6(json.loads((tmp_path / "final-T6.json").read_bytes())) == state
        assert classify_t6(json.loads((tmp_path / "first.json").read_bytes())) == first
        # 新进程只读分支确认已提交，不再发任何POST或换key。
        assert (
            collect_final_t6(
                app,
                f.actor.organization_id,
                f.inventory.data.shop,
                task,
                writers=[*writers, process],
                output=tmp_path / "cold-read.json",
            )
            == state
        )
        context = dict(
            item_id=str(item),
            organization_id=str(f.actor.organization_id),
            shop_id=str(f.inventory.data.shop),
            task_id=str(task),
            request_key=str(key),
            principal_id=str(f.actor.principal_id),
            identity_id=str(f.actor.identity_id),
            auth_version=f.actor.auth_version,
        )
        gateway, child = a.gateway()
        try:
            with connect(app) as db:
                template = terminal_window_from_native(
                    db, context, expires_at=gateway.expires_at, queued=True
                )

            def arm(current: Any) -> ControlledWorkerWindow:
                value = template.model_dump(mode="json")
                value.update(
                    enabled=True,
                    window_id=str(uuid4()),
                    gateway_window_id=str(current.window_id),
                    expires_at=current.expires_at.isoformat(),
                )
                value["terminal_update"].update(
                    worker_window_id=value["window_id"],
                    gateway_window_id=value["gateway_window_id"],
                    expires_at=value["expires_at"],
                )
                return ControlledWorkerWindow.model_validate_json(json.dumps(value))

            for changed in ("queued_hash", "sdk_hash", "record", "semantic"):
                rejected_value = arm(gateway).model_dump(mode="json")
                rejected_value["window_id"] = str(uuid4())
                rejected_value["terminal_update"]["worker_window_id"] = rejected_value["window_id"]
                terminal = rejected_value["terminal_update"]
                if changed == "queued_hash":
                    terminal["verified_recovery"]["queued_start"]["task_binding_hash"] = "0" * 64
                elif changed == "sdk_hash":
                    terminal["verified_sdk_window_hash"] = "0" * 64
                elif changed == "record":
                    terminal["external_id"] = "synthetic-wrong-anchor"
                else:
                    terminal["semantic_hash"] = "0" * 64
                denied_window = ControlledWorkerWindow.model_validate_json(
                    json.dumps(rejected_value)
                )
                _, denied = a.worker(denied_window)
                assert denied["exit_code"] == 1
                assert denied["stages"]["PREFLIGHT"]["state"] == "NOT_RUN"
                a.stop_gateway(gateway, child)
                gateway, child = a.gateway()
            window = arm(gateway)
            native, result = a.worker(window)
            assert result["exit_code"] == 0
            assert result["native_summary"]["terminal_update_outcome"] == "verified"
            with connect(app) as db:
                rows = db.execute(
                    "SELECT version,status,external_id FROM business.p4_base_deliveries "
                    "WHERE item_id=%s ORDER BY version",
                    (item,),
                ).fetchall()
                counts = db.execute(
                    "SELECT method,count(*) AS n FROM business.p4_sdk_calls "
                    "WHERE window_id=%s GROUP BY method",
                    (window.window_id,),
                ).fetchall()
            assert [r["status"] for r in rows] == ["verified", "verified"]
            assert rows[0]["external_id"] == rows[1]["external_id"]
            assert sum(r["n"] for r in counts) <= 11
            assert not any(
                r["method"] in ("im.v1.message.create", "bitable.v1.app_table_record.create")
                for r in counts
            )
            _, replay = a.worker(window, replay_of=native)
            assert replay["exit_code"] == 1
            a.stop_gateway(gateway, child)
            gateway, child = a.gateway()
            with connect(owner) as db:
                db.execute(
                    "UPDATE business.principals SET enabled=false,auth_version=auth_version+1 "
                    "WHERE id=%s",
                    (f.actor.principal_id,),
                )
            revoked_value = arm(gateway).model_dump(mode="json")
            revoked_value["window_id"] = str(uuid4())
            revoked_value["terminal_update"]["worker_window_id"] = revoked_value["window_id"]
            _, revoked = a.worker(
                ControlledWorkerWindow.model_validate_json(json.dumps(revoked_value))
            )
            assert revoked["exit_code"] == 1
            assert revoked["stages"]["PREFLIGHT"]["state"] == "NOT_RUN"
            assert any(x["function"] == "terminal_intent" for x in revoked["failure"]["locations"])
        finally:
            a.stop_gateway(gateway, child)
    finally:
        if writer is not None and writer.poll() is None:
            writer.terminate()
            writer.wait(timeout=10)
        assert a.cleanup()
