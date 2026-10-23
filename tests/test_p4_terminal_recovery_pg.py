"""新owned双schema原失败态→原生独立once→read-first恢复；HTTP以外不Fake。"""

import json
import os
import time
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from commerceops.application.feishu_business.worker_window import ControlledWorkerWindow
from commerceops.infrastructure.database import DatabaseSettings, connect
from psycopg import sql

from scripts.p4_acceptance import Deadline, terminal_window_from_native, write_private
from scripts.p4_terminal_state import terminal_recovery_from_native
from tests.p4_acceptance_support import AcceptanceFixture, worker_request
from tests.p4_queued_terminal_support import verified_queued_origin
from tests.test_p4_acceptance_pg import initialize_schema

pytestmark = pytest.mark.integration


def arm(template: ControlledWorkerWindow, gateway: Any) -> ControlledWorkerWindow:
    value = template.model_dump(mode="json")
    value.update(
        enabled=True,
        window_id=str(uuid4()),
        gateway_window_id=str(gateway.window_id),
        expires_at=gateway.expires_at.isoformat(),
    )
    value["terminal_update"].update(
        worker_window_id=value["window_id"],
        gateway_window_id=value["gateway_window_id"],
        expires_at=value["expires_at"],
    )
    return ControlledWorkerWindow.model_validate_json(json.dumps(value))


def prepare_failure(a: AcceptanceFixture) -> tuple[dict[str, Any], ControlledWorkerWindow]:
    known = verified_queued_origin(a)
    f = a.fixture
    item, task, key = known["delivery"]["item_id"], known["delivery"]["task_id"], uuid4()
    response = f.client.post(
        f"/api/v1/replenishment-items/{item}/resolve",
        json=dict(
            schema_version="p3-web-v1",
            request_key=str(key),
            action="close",
            expected_version=1,
            reason="synthetic recovery native close",
        ),
        headers=f.headers(),
    )
    assert response.status_code == 200
    context = dict(
        item_id=str(item),
        task_id=str(task),
        request_key=str(key),
        organization_id=str(f.actor.organization_id),
        shop_id=str(f.inventory.data.shop),
        principal_id=str(f.actor.principal_id),
        identity_id=str(f.actor.identity_id),
        auth_version=f.actor.auth_version,
    )
    gateway, child = a.gateway()
    try:
        with connect(f.config.database) as db:
            template = terminal_window_from_native(
                db, context, expires_at=gateway.expires_at, queued=True
            )
        window = arm(template, gateway)
        assert window.terminal_update is not None
        # 同当前原生命令真实失败；仅HTTP响应缺SKU，不伪造SQL或补历史ledger。
        a.external_behavior("missing_required")
        _, failed = a.worker(window)
        assert failed["exit_code"] == 1
        assert failed["native_summary"]["terminal_update_outcome"] == "unknown"
        with connect(f.config.database) as db:
            row = db.execute(
                "SELECT * FROM business.p4_base_deliveries WHERE outbox_id=%s",
                (window.terminal_update.projection.outbox_id,),
            ).fetchone()
            calls = db.execute(
                "SELECT method,status FROM business.p4_sdk_calls WHERE window_id=%s",
                (window.window_id,),
            ).fetchall()
        assert row is not None
        assert row["status"] == "unknown" and row["attempts"] == 1
        assert row["last_error"] == "INCOMPLETE_READBACK" and row["last_operation"] == "update"
        assert len(calls) == 5 and all(call["status"] == "returned" for call in calls)
        assert not any(call["method"].endswith((".create", ".update")) for call in calls)
    finally:
        a.stop_gateway(gateway, child)
    a.external_behavior("normal")
    return context, window


@contextmanager
def owned_database() -> Iterator[tuple[DatabaseSettings, DatabaseSettings]]:
    """原fixture相同的本轮临时数据库；不共享业务行、once或身份。"""
    settings = DatabaseSettings()
    assert settings.runtime_password_file is not None
    name = "p4_acceptance_" + uuid4().hex
    owner = settings.model_copy(update={"name": name})
    app = owner.model_copy(
        update={
            "user": "commerceops_app",
            "password_file": settings.runtime_password_file,
            "runtime_password_file": None,
        }
    )
    with psycopg.connect(**settings.kwargs(), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            yield owner, app
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture(scope="module")
def failed_cases(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[dict[str, Any]]:
    """先串行准备本命令实际选中节点，各自独立DB；让原30秒冷却自然经过，不改时钟/SQL。"""
    cases: dict[str, Any] = {}
    expires = datetime.now(UTC) + timedelta(minutes=15)
    if os.environ.get("COMMERCEOPS_ACCEPTANCE_DEADLINE"):
        expires = min(
            expires, datetime.fromisoformat(os.environ["COMMERCEOPS_ACCEPTANCE_DEADLINE"])
        )
    with ExitStack() as stack:
        try:
            for item in request.session.items:
                if not isinstance(item, pytest.Function) or item.module is not request.module:
                    continue
                owner, app = stack.enter_context(owned_database())
                revision = item.callspec.params["revision"]
                assert isinstance(revision, str)
                initialize_schema(owner, revision)
                directory = tmp_path_factory.mktemp("terminal-failure-")
                a = AcceptanceFixture.prepare(
                    owner,
                    app,
                    directory,
                    Deadline.register(expires),
                    case_kind="recover_single_item",
                )
                cases[item.nodeid] = dict(a=a, owner=owner, app=app, directory=directory)
                context, failed = prepare_failure(a)
                with connect(app) as db:
                    template = terminal_recovery_from_native(db, context, expires_at=expires)
                cases[item.nodeid].update(context=context, failed=failed, template=template)
            yield cases
        finally:
            cleaned = [case["a"].cleanup() for case in cases.values()]
            assert all(cleaned)


@pytest.mark.parametrize("revision", ["0015", "0016"])
@pytest.mark.parametrize("remote", ["nullable_digits", "already_v2"])
def test_unknown_terminal_read_first_native_once_and_cold_replay(
    failed_cases: dict[str, Any],
    request: pytest.FixtureRequest,
    revision: str,
    remote: str,
) -> None:
    case = failed_cases[request.node.nodeid]
    a, app, tmp_path, failed, template = (
        case[name] for name in ("a", "app", "directory", "failed", "template")
    )
    try:
        assert failed.terminal_update is not None
        with connect(app) as db:
            before = db.execute(
                "SELECT * FROM business.p4_base_deliveries WHERE outbox_id=%s",
                (failed.terminal_update.projection.outbox_id,),
            ).fetchone()
        assert not template.enabled and template.terminal_update is not None
        assert template.terminal_update.recovery_of is not None and before is not None
        transport = json.loads(a.external.read_bytes())
        if remote == "nullable_digits":
            for row in transport["rows"]:
                for name in ("ResolvedBy", "ResolvedAt", "ResolutionReason"):
                    row["fields"].pop(name)
                for name in ("Quantity", "SyncVersion"):
                    row["fields"][name] = str(row["fields"][name])
        else:
            # 仅模拟外端已完成v2；PG仍保留真实unknown1，恢复须读回结算/update0。
            from commerceops.application.feishu_business.contracts import ItemProjection

            transport["rows"][0]["fields"] = ItemProjection.model_validate_json(
                json.dumps(before["projection"])
            ).fields()
        write_private(a.external, transport)
        a.wait_due(before["outbox_id"])
        gateway, child = a.gateway()
        try:
            if remote == "nullable_digits":
                for field in (
                    "failed_window_hash",
                    "failed_sdk_window_hash",
                    "failed_ledger_hash",
                    "failed_delivery_hash",
                ):
                    changed = arm(template, gateway).model_dump(mode="json")
                    changed["terminal_update"]["recovery_of"][field] = "0" * 64
                    invalid = ControlledWorkerWindow.model_validate_json(json.dumps(changed))
                    _, denied = a.worker(invalid)
                    assert denied["exit_code"] == 1
                    assert denied["stages"]["PREFLIGHT"]["state"] == "NOT_RUN"
                    with connect(app) as db:
                        count = db.execute(
                            "SELECT count(*) AS n FROM business.p4_sdk_calls WHERE window_id=%s",
                            (invalid.window_id,),
                        ).fetchone()
                        assert count is not None and count["n"] == 0
                    a.stop_gateway(gateway, child)
                    gateway, child = a.gateway()
            window = arm(template, gateway)
            if remote == "nullable_digits":
                first = worker_request(a.fixture.config, a.business, window, tmp_path, a.external)
                other = dict(first, output_file=str(tmp_path / "competing-worker.json"))
                children = [a.start(first), a.start(other)]
                results = [child.wait(timeout=60) for child in children]
                for contender, value in zip(children, results, strict=True):
                    a.confirm_worker(contender, value, allow_no_start=True)
                assert sorted(value["exit_code"] for value in results) == [0, 1]
                winner = next(
                    index for index, value in enumerate(results) if value["exit_code"] == 0
                )
                native, result = children[winner], results[winner]
            else:
                native, result = a.worker(window)
            assert result["exit_code"] == 0
            assert result["native_summary"]["terminal_update_outcome"] == "verified"
            with connect(app) as db:
                after = db.execute(
                    "SELECT * FROM business.p4_base_deliveries WHERE outbox_id=%s",
                    (before["outbox_id"],),
                ).fetchone()
                calls = db.execute(
                    "SELECT * FROM business.p4_sdk_calls WHERE window_id=%s ORDER BY id",
                    (window.window_id,),
                ).fetchall()
                once = db.execute(
                    "SELECT action,after_state FROM business.audit_events WHERE trace_id=%s "
                    "AND source='feishu_recovery' ORDER BY action",
                    (window.window_id,),
                ).fetchall()
            assert after is not None
            assert after["status"] == "verified" and after["attempts"] == 2
            assert after["last_operation"] == "reconcile"
            assert after["first_attempt_at"] == before["first_attempt_at"]
            assert after["unknown_since"] == before["unknown_since"]
            assert [row["action"] for row in once] == [
                "terminal_recovery_authorized",
                "terminal_recovery_dispatched",
            ]
            assert len(calls) <= 11 and all(call["status"] == "returned" for call in calls)
            assert sum(
                call["method"] == "bitable.v1.app_table_record.update" for call in calls
            ) == (remote != "already_v2")
            assert not any(
                call["method"] in ("bitable.v1.app_table_record.create", "im.v1.message.create")
                for call in calls
            )
            _, replay = a.worker(window, replay_of=native)
            assert replay["exit_code"] == 1
            with connect(app) as db:
                assert (
                    db.execute(
                        "SELECT * FROM business.p4_sdk_calls WHERE window_id=%s ORDER BY id",
                        (window.window_id,),
                    ).fetchall()
                    == calls
                )
        finally:
            a.stop_gateway(gateway, child)
    finally:
        assert a.cleanup()


@pytest.mark.parametrize("revision", ["0015", "0016"])
@pytest.mark.parametrize("boundary", ["auth", "before-update", "after-update", "revoked"])
def test_terminal_recovery_stop_or_revoke_does_not_rearm_once(
    failed_cases: dict[str, Any],
    request: pytest.FixtureRequest,
    revision: str,
    boundary: str,
) -> None:
    case = failed_cases[request.node.nodeid]
    a, app, owner, tmp_path, failed, template = (
        case[name] for name in ("a", "app", "owner", "directory", "failed", "template")
    )
    try:
        assert failed.terminal_update is not None
        outbox = failed.terminal_update.projection.outbox_id
        a.wait_due(outbox)
        behavior = {
            "auth": "auth_pause",
            "before-update": "update_pause_before",
            "after-update": "update_pause_after",
            "revoked": "preupdate_pause",
        }[boundary]
        a.external_behavior(behavior)
        gateway, gateway_child = a.gateway()
        try:
            window = arm(template, gateway)
            native = a.start(
                worker_request(a.fixture.config, a.business, window, tmp_path, a.external)
            )
            ready = a.external.with_suffix(
                "." + ("preupdate" if boundary == "revoked" else boundary) + ".ready"
            )
            end = time.monotonic() + min(45, a.deadline.remaining())
            while not ready.exists():
                assert native.process.poll() is None and time.monotonic() < end
                time.sleep(0.02)
            if boundary == "revoked":
                with connect(owner) as db:
                    db.execute(
                        "UPDATE business.principals SET enabled=false,auth_version=auth_version+1 "
                        "WHERE id=%s",
                        (a.fixture.actor.principal_id,),
                    )
                a.external.with_suffix(".preupdate.release").touch(mode=0o600)
            else:
                native.process.terminate()
            result = native.wait(timeout=30)
            assert result["exit_code"] == 1
            a.confirm_worker(native, result)
            with connect(app) as db:
                calls = db.execute(
                    "SELECT * FROM business.p4_sdk_calls WHERE window_id=%s ORDER BY id",
                    (window.window_id,),
                ).fetchall()
                delivery = db.execute(
                    "SELECT * FROM business.p4_base_deliveries WHERE outbox_id=%s", (outbox,)
                ).fetchone()
                once = db.execute(
                    "SELECT action FROM business.audit_events WHERE trace_id=%s "
                    "AND source='feishu_recovery'",
                    (window.window_id,),
                ).fetchall()
            assert delivery is not None and delivery["attempts"] == (1 if boundary == "auth" else 2)
            assert "terminal_recovery_authorized" in {row["action"] for row in once}
            assert ("terminal_recovery_dispatched" in {row["action"] for row in once}) == (
                boundary != "auth"
            )
            assert sum(row["method"] == "bitable.v1.app_table_record.update" for row in calls) == (
                boundary in ("before-update", "after-update")
            )
            assert not any(
                row["method"] in ("bitable.v1.app_table_record.create", "im.v1.message.create")
                for row in calls
            )
            _, replay = a.worker(window, replay_of=native)
            assert replay["exit_code"] == 1
            with connect(app) as db:
                assert (
                    db.execute(
                        "SELECT * FROM business.p4_sdk_calls WHERE window_id=%s ORDER BY id",
                        (window.window_id,),
                    ).fetchall()
                    == calls
                )
        finally:
            a.stop_gateway(gateway, gateway_child)
    finally:
        assert a.cleanup()
