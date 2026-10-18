"""新自有PG：双schema实际role/query与同outer/原Factory/真实once及cold replay。"""

import asyncio
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from commerceops.entrypoints.database import grant_runtime, migrate, setup_checkpointer
from commerceops.infrastructure.database import DatabaseSettings, connect, migration_engine
from psycopg import sql

from scripts.p4_acceptance import CONTRACT, Deadline, _ro_schema, schema_contract, write_private
from tests.p4_acceptance_support import (
    AcceptanceFixture,
    prepare_batch_ro,
    prepare_single_ro,
    reference,
)

pytestmark = pytest.mark.integration


def initialize_schema(owner: DatabaseSettings, revision: str) -> None:
    if revision == "0017":
        migrate(owner)
    else:
        config = Config()
        config.set_main_option("script_location", "backend/migrations")
        engine = migration_engine(owner)
        try:
            with engine.begin() as db:
                config.attributes["connection"] = db
                command.upgrade(config, revision)
        finally:
            engine.dispose()
    asyncio.run(setup_checkpointer(owner))
    grant_runtime(owner, **({"legacy_revision": revision} if revision in ("0015", "0016") else {}))  # type: ignore[arg-type]


@pytest.fixture
def database() -> Iterator[tuple[DatabaseSettings, DatabaseSettings]]:
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


@pytest.mark.parametrize("revision", ["0015", "0016"])
def test_exact_schema_app_queries_and_expected_metadata_denial(
    database: tuple[DatabaseSettings, DatabaseSettings],
    revision: str,
) -> None:
    owner, app = database
    initialize_schema(owner, revision)
    result = schema_contract(owner, app, revision)
    assert result["exact_table_count"] == (55 if revision == "0015" else 56)
    assert result["alembic_read_denied_sqlstate"] == "42501"
    original_metadata = _ro_schema(owner, app, revision)
    assert original_metadata["exact_table_count"] == result["exact_table_count"]
    assert original_metadata["owner_connection_closed"] is True
    assert not any(
        original_metadata["app_role"][flag]
        for flag in ("rolsuper", "rolcreatedb", "rolcreaterole", "rolreplication", "rolbypassrls")
    )
    # 在昂贵RO历史前，以空库真实DDL/低权执行完整SELECT（含实际行锁权限）。
    # 只检查生产查询对schema/grant的兼容，不插入业务行或替换业务准入。
    from commerceops.infrastructure.feishu_outbox_recovery import terminal_intent

    from scripts.p4_acceptance import terminal_window_from_native

    checked = 0
    for operation in (terminal_intent, terminal_window_from_native):
        for statement in operation.__code__.co_consts:
            if not isinstance(statement, str) or not statement.startswith("SELECT "):
                continue
            with connect(app) as db:
                db.execute(statement, (None,) * statement.count("%s")).fetchall()
            checked += 1
    assert checked >= 10
    if revision == "0016":
        with pytest.raises(ValueError, match="revision mismatch"):
            grant_runtime(owner, legacy_revision="0015")


def test_same_outer_native_full_RO_once_and_fresh_process_original_key_replay(
    database: tuple[DatabaseSettings, DatabaseSettings],
    tmp_path: Path,
) -> None:
    owner, app = database
    initialize_schema(owner, "0016")
    schema_contract(owner, app, "0016")
    expiry = datetime.now(UTC) + timedelta(minutes=12)
    registered = os.environ.get("COMMERCEOPS_ACCEPTANCE_DEADLINE")
    if registered:
        expiry = min(expiry, datetime.fromisoformat(registered))
    lease = Deadline.register(expiry)
    a = AcceptanceFixture.prepare(owner, app, tmp_path, lease, case_kind="recover_single_item")
    try:
        result = prepare_single_ro(a, concurrent_once=True)
        assert result["verified"]["exit_code"] == 0
        assert result["verified"]["counts"]["real_network_egress"] == 0
        assert result["replay"]["exit_code"] == 1
        assert sorted(result["concurrent_once"]["actual_child_exits"]) == [0, 1]
        continuation = a.save_continuation(result)
        item_id = result["delivery"]["item_id"]
        task_id = next(iter(result["window"].task_ids))
        # 这里只验证原生API事务与v2装配；真实浏览器T6必须由C完整预演另签。
        response = a.fixture.client.post(
            f"/api/v1/replenishment-items/{item_id}/resolve",
            json={
                "schema_version": "p3-web-v1",
                "request_key": str(uuid4()),
                "action": "close",
                "expected_version": 1,
                "reason": "LAB native API regression",
            },
            headers=a.fixture.headers(),
        )
        assert response.status_code == 200
        with connect(app) as db:
            outbox = db.execute(
                "SELECT * FROM business.outbox WHERE aggregate_id=%s AND aggregate_version=2",
                (item_id,),
            ).fetchone()
        assert outbox is not None
        t6 = tmp_path / "native-api-only.json"
        write_private(t6, dict(item_id=str(item_id), task_id=str(task_id), v2_outbox=outbox))
        child = a.start(
            {
                "contract": CONTRACT,
                "action": "project_v2",
                "continuation_ref": continuation,
                "t6_result_ref": reference(t6),
                "output_file": str(tmp_path / "native-v2-result.json"),
            }
        )
        v2 = child.wait(timeout=min(90, a.deadline.remaining()))
        assert v2["exit_code"] == 0, v2.get("failure")
        assert v2["value"]["witnesses"][0]["request"]["operation"] == "update"
    finally:
        assert a.cleanup()


def test_twenty_items_ordinary_ro_is_separate_from_explicit_single_recovery(
    database: tuple[DatabaseSettings, DatabaseSettings], tmp_path: Path
) -> None:
    owner, app = database
    initialize_schema(owner, "0016")
    expiry = datetime.now(UTC) + timedelta(minutes=8)
    registered = os.environ.get("COMMERCEOPS_ACCEPTANCE_DEADLINE")
    if registered:
        expiry = min(expiry, datetime.fromisoformat(registered))
    a = AcceptanceFixture.prepare(
        owner, app, tmp_path, Deadline.register(expiry), case_kind="batch_twenty_items"
    )
    try:
        result = prepare_batch_ro(a)
        assert len(result["items"]) == 20
        assert sum(int(r["quantity"]) for r in result["items"]) == 2000
        assert result["explicit_recheck"] is False
        assert result["window"].recovery.explicit_ro_recheck is None
        assert result["window"].recovery.sender_gateway is None
    finally:
        assert a.cleanup()


def test_gateway_session_lock_held_until_actual_child_reap(
    database: tuple[DatabaseSettings, DatabaseSettings],
    tmp_path: Path,
) -> None:
    owner, app = database
    initialize_schema(owner, "0016")
    a = AcceptanceFixture.prepare(
        owner,
        app,
        tmp_path,
        Deadline.register(datetime.now(UTC) + timedelta(minutes=5)),
        case_kind="recover_single_item",
    )
    window = child = None
    try:
        window, child = a.gateway()
        with connect(app) as db:
            row = db.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS acquired",
                ("p4-gateway:" + a.business.app_id,),
            ).fetchone()
            assert row == {"acquired": False}
        a.stop_gateway(window, child)
        with connect(app) as db:
            assert db.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS acquired",
                ("p4-gateway:" + a.business.app_id,),
            ).fetchone() == {"acquired": True}
            assert db.execute(
                "SELECT pg_advisory_unlock(hashtextextended(%s,0)) AS released",
                ("p4-gateway:" + a.business.app_id,),
            ).fetchone() == {"released": True}
    finally:
        if window is not None and child is not None and not child.confirmed:
            a.stop_gateway(window, child)
        assert a.cleanup()


@pytest.mark.parametrize("revision", ["0015", "0016"])
def test_terminal_native_enrollment_same_anchor_once_and_cold_replay(
    database: tuple[DatabaseSettings, DatabaseSettings],
    tmp_path: Path,
    revision: str,
) -> None:
    from tests.p4_acceptance_support import terminal_update_manifest

    owner, app = database
    initialize_schema(owner, revision)
    expiry = datetime.now(UTC) + timedelta(minutes=15)
    registered = os.environ.get("COMMERCEOPS_ACCEPTANCE_DEADLINE")
    if registered:
        expiry = min(expiry, datetime.fromisoformat(registered))
    a = AcceptanceFixture.prepare(
        owner, app, tmp_path, Deadline.register(expiry), case_kind="recover_single_item"
    )
    gateway = child = None
    try:
        ro = prepare_single_ro(a)
        item = ro["delivery"]["item_id"]
        response = a.fixture.client.post(
            f"/api/v1/replenishment-items/{item}/resolve",
            json=dict(
                schema_version="p3-web-v1",
                request_key=str(uuid4()),
                action="close",
                expected_version=1,
                reason="synthetic native terminal update",
            ),
            headers=a.fixture.headers(),
        )
        assert response.status_code == 200
        with connect(app) as db:
            assert db.execute(
                "SELECT count(*) AS n FROM business.p4_base_deliveries WHERE version=2"
            ).fetchone() == {"n": 0}
        import json

        from commerceops.application.feishu_business.worker_window import ControlledWorkerWindow

        from tests.p4_acceptance_support import worker_request

        # 每个真实准入拒绝均在新进程执行；不得消耗SDK或登记v2 delivery。
        for field in (
            "external_id",
            "semantic_hash",
            "request_key",
            "resolver_identity_id",
            "verified_sdk_window_hash",
            "verified_worker_owner",
        ):
            gateway, child = a.gateway()
            window = terminal_update_manifest(a, ro, gateway)
            value = window.model_dump(mode="json")
            value["window_id"] = str(uuid4())
            value["terminal_update"]["worker_window_id"] = value["window_id"]
            value["terminal_update"][field] = (
                "synthetic-wrong-record"
                if field == "external_id"
                else "0" * 64
                if field.endswith("hash")
                else str(uuid4())
            )
            rejected = ControlledWorkerWindow.model_validate_json(json.dumps(value))
            _, denial = a.worker(rejected)
            assert denial["exit_code"] == 1
            assert denial["stages"]["PREFLIGHT"]["state"] == "NOT_RUN"
            with connect(app) as db:
                assert db.execute(
                    "SELECT count(*) AS n FROM business.p4_base_deliveries WHERE version=2"
                ).fetchone() == {"n": 0}
            a.stop_gateway(gateway, child)
        gateway, child = a.gateway()
        window = terminal_update_manifest(a, ro, gateway)
        a.external_behavior("normal")
        first = a.start(
            worker_request(a.fixture.config, a.business, window, a.fixture.private, a.external)
        )
        other_request = dict(first.request)
        other_request["output_file"] = str(a.fixture.private / "terminal-concurrent-other.json")
        second = a.start(other_request)
        pairs = [(c, c.wait(timeout=min(60, a.deadline.remaining()))) for c in (first, second)]
        for c, v in pairs:
            a.confirm_worker(c, v, allow_no_start=True)
        assert sorted(v["exit_code"] for _, v in pairs) == [0, 1], json.dumps(
            [v for _, v in pairs], default=str
        )
        process, result = next((c, v) for c, v in pairs if v["exit_code"] == 0)
        loser = next(v for _, v in pairs if v["exit_code"] == 1)
        assert loser["stages"]["PREFLIGHT"]["state"] == "NOT_RUN"
        assert result["exit_code"] == 0, __import__("json").dumps(result, default=str)
        assert result["native_summary"]["terminal_update_outcome"] == "verified"
        assert len(result["witnesses"]) == 1
        witness = result["witnesses"][0]
        assert witness["request"]["operation"] == "update"
        assert witness["result"]["external_id"] == ro["links"][0]["external_id"]
        with connect(app) as db:
            before = db.execute(
                "SELECT * FROM business.p4_sdk_calls WHERE window_id=%s ORDER BY id",
                (window.window_id,),
            ).fetchall()
            assert db.execute(
                "SELECT version,status,attempts FROM business.p4_base_deliveries ORDER BY version"
            ).fetchall() == [
                {"version": 1, "status": "verified", "attempts": 3},
                {"version": 2, "status": "verified", "attempts": 1},
            ]
            assert sum(x["method"] == "bitable.v1.app_table_record.update" for x in before) == 1
            assert not any(
                x["method"] in ("bitable.v1.app_table_record.create", "im.v1.message.create")
                for x in before
            )
        _, replay = a.worker(window, replay_of=process)
        assert replay["exit_code"] == 1
        assert replay["stages"]["PREFLIGHT"]["state"] == "NOT_RUN"
        with connect(app) as db:
            assert (
                db.execute(
                    "SELECT * FROM business.p4_sdk_calls WHERE window_id=%s ORDER BY id",
                    (window.window_id,),
                ).fetchall()
                == before
            )
        a.stop_gateway(gateway, child)
        gateway, child = a.gateway()
        replacement = terminal_update_manifest(a, ro, gateway)
        _, denial = a.worker(replacement)
        assert denial["exit_code"] == 1 and denial["stages"]["PREFLIGHT"]["state"] == "NOT_RUN"
        a.stop_gateway(gateway, child)
        gateway, child = a.gateway()
        revoked = terminal_update_manifest(a, ro, gateway)
        assert revoked.terminal_update is not None
        with connect(owner) as db:
            db.execute(
                "UPDATE business.principals SET enabled=false,"
                "auth_version=auth_version+1 WHERE id=%s",
                (revoked.terminal_update.resolver_id,),
            )
        _, denial = a.worker(revoked)
        assert denial["exit_code"] == 1 and denial["stages"]["PREFLIGHT"]["state"] == "NOT_RUN"
        assert any(x["function"] == "terminal_intent" for x in denial["failure"]["locations"])
    finally:
        if gateway is not None and child is not None and not child.confirmed:
            a.stop_gateway(gateway, child)
        assert a.cleanup()
