"""新owned原生父/child/SQL/Factory；仅最底层 HTTP 为合成响应。"""

import asyncio
import json
import os
import signal
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from typing import Any
from uuid import uuid4

import pytest
from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.adapters.feishu.business_factory import BusinessSDKFactory
from commerceops.adapters.feishu.history import collect_history
from commerceops.application.feishu_business.history import ORIGINAL_START, HistoryRecoveryRequest
from commerceops.application.replenishment.contracts import WebFailure
from commerceops.entrypoints.database import grant_runtime, migrate
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.feishu_history import HistoryRecoveryStore
from commerceops.infrastructure.feishu_sdk_ledger import PersistentSDKLedger
from commerceops.infrastructure.worker_lock import WorkerSession
from psycopg import sql
from psycopg.errors import (
    CheckViolation,
    FeatureNotSupported,
    InsufficientPrivilege,
    UniqueViolation,
)

from scripts.p4_acceptance import read_reply_window_from_history, write_private
from tests.p3_support import P3Fixture, initialize_p3
from tests.p4_acceptance_support import FakeHTTPTransport
from tests.p4_parent_support import ParentInputs, prepare_parent
from tests.test_p3_pg import fixture as fixture
from tests.test_p4_acceptance_pg import database as database
from tests.test_p4_acceptance_pg import initialize_schema
from tests.test_p4_gateway_pg import message, service
from tests.test_p4_read_reply_pg import prepared

pytestmark = pytest.mark.integration


def required(row: dict[str, Any] | None) -> dict[str, Any]:
    assert row is not None
    return row


def setup_history(
    f: P3Fixture, behavior: str = "normal"
) -> tuple[ParentInputs, HistoryRecoveryRequest, list[dict[str, Any]]]:
    source = prepared(f)
    original = service(f)
    with connect(f.config.database) as db:
        actor = original.actor(db, message(f).identity, message(f).chat_id)
    inputs = prepare_parent(f, None, mode="history_recovery", behavior=behavior)
    settings = BusinessSettings.model_validate_json(inputs.business.read_bytes())
    start = datetime.now(UTC) - timedelta(seconds=1)
    texts = [
        f"查询任务{source['task_id']}进度",
        f"解释任务{source['task_id']}的报告{source['report_id']}",
    ]
    request = HistoryRecoveryRequest.model_validate_json(
        json.dumps(
            {
                "schema_version": "p4-original-query-history-v1",
                "recovery_id": str(uuid4()),
                "organization_id": str(settings.organization_id),
                "shop_id": str(settings.shop_id),
                "principal_id": str(actor.principal_id),
                "identity_id": str(actor.identity_id),
                "auth_version": actor.auth_version,
                "app_id": settings.app_id,
                "tenant_key": settings.tenant_key,
                "open_id": actor.open_id,
                "chat_id": actor.chat_id,
                "expected_texts": texts,
                "not_before": start.isoformat(),
                "expires_at": (start + timedelta(seconds=120)).isoformat(),
                "enabled": True,
            }
        )
    )
    rows = []
    for index, text in enumerate(texts):
        sent = str(int((ORIGINAL_START + timedelta(seconds=10 + index)).timestamp()) * 1000)
        rows.append(
            {
                "message_id": "owned-original-" + uuid4().hex,
                "chat_id": request.chat_id,
                "msg_type": "text",
                "create_time": sent,
                "update_time": sent,
                "deleted": False,
                "updated": False,
                "sender": {
                    "id": request.open_id,
                    "id_type": "open_id",
                    "sender_type": "user",
                    "tenant_key": request.tenant_key,
                },
                "body": {"content": json.dumps({"text": text})},
            }
        )
    cursor = "owned-page-two"
    state = {
        "behavior": behavior,
        "rows": [],
        "history_pages": [
            {"items": [rows[0]], "has_more": True, "page_token": cursor},
            {"items": [rows[1]], "has_more": False},
        ],
    }
    write_private(inputs.directory / "external-records.json", state)
    inputs.bind_window(request.model_copy(update={"enabled": False}).model_dump(mode="json"))
    return inputs, request, rows


def protected(f: P3Fixture) -> dict[str, Any]:
    with connect(f.config.database) as db:
        return required(
            db.execute("""
SELECT (SELECT count(*) FROM business.business_tasks) AS tasks,
          (SELECT count(*) FROM business.jobs) AS jobs,(SELECT count(*) FROM
        business.executions) AS executions,
          (SELECT count(*) FROM business.replenishment_items) AS items,(SELECT
        count(*) FROM business.model_calls) AS model,
          (SELECT count(*) FROM business.outbox) AS outbox""").fetchone()
        )


def test_native_collect_two_originals_then_two_original_reply_windows(fixture: P3Fixture) -> None:
    f = fixture
    inputs, request, rows = setup_history(f)
    before = protected(f)
    assert inputs.run("disabled", disabled=True)[0] == 1
    code, result = inputs.run("collect")
    assert (
        code == 0
        and result["result"] == "window_stopped"
        and result["child_reaped"]
        and result["lifecycle_termination_confirmed"]
    )
    assert result["official_summary"]["result"] == "history_verified"
    assert protected(f) == before
    with connect(f.config.database) as db:
        messages = db.execute(
            "SELECT * FROM business.p4_history_messages WHERE recovery_id=%s ORDER BY kind DESC",
            (request.recovery_id,),
        ).fetchall()
        calls = db.execute(
            """SELECT method,status FROM business.p4_sdk_calls
            WHERE window_id=%s ORDER BY started_at""",
            (request.recovery_id,),
        ).fetchall()
        assert (
            len(messages) == 2 and len(calls) == 4 and all(v["status"] == "returned" for v in calls)
        )
        assert [v["method"] for v in calls] == [
            "auth.v3.tenant_access_token.internal",
            "bot.v3.info",
            "im.v1.message.list",
            "im.v1.message.list",
        ]
        assert (
            required(
                db.execute(
                    "SELECT count(*) AS n FROM business.inbox_events WHERE message_id=ANY(%s)",
                    ([r["message_id"] for r in rows],),
                ).fetchone()
            )["n"]
            == 0
        )
        for row in messages:
            reply = required(
                db.execute(
                    "SELECT * FROM business.p4_read_replies WHERE id=%s", (row["reply_id"],)
                ).fetchone()
            )
            assert reply["inbox_id"] is None and reply["history_message_id"] == row["id"]
            assert reply["as_of"] > row["sent_at"] and row["processed_at"] >= row["observed_at"]
    assert inputs.run("cold-collect")[0] == 1
    for index, row in enumerate(rows):
        next_private = f.private / ("send-" + str(index))
        next_private.mkdir(mode=0o700)
        sender = prepare_parent(replace(f, private=next_private), None, mode="read_reply")
        settings = BusinessSettings.model_validate_json(sender.business.read_bytes())
        with connect(f.config.database) as db:
            template = read_reply_window_from_history(
                db,
                settings,
                recovery_id=request.recovery_id,
                original_message_id=row["message_id"],
                expires_at=datetime.now(UTC) + timedelta(seconds=60),
            )
        sender.bind_window(template.model_dump(mode="json"))
        assert sender.run("send")[0] == 0
        assert sender.run("cold-send")[0] == 1
        with connect(f.config.database) as db:
            reply = required(
                db.execute(
                    "SELECT status,attempts FROM business.p4_read_replies WHERE id=%s",
                    (template.reply_id,),
                ).fetchone()
            )
            assert reply == {"status": "sent", "attempts": 1}
        rendered = list(sender.directory.glob("im-*.private.json"))
        assert len(rendered) == 1
        card = json.loads(json.loads(rendered[0].read_bytes())["content"])
        assert "原查询的延迟处理" in json.dumps(card, ensure_ascii=False)
    assert protected(f) == before


@pytest.mark.parametrize(
    "behavior", ["history_timeout", "history_denied", "incomplete", "duplicate"]
)
def test_history_uncertain_response_is_spent_without_carriers_or_retry(
    fixture: P3Fixture, behavior: str
) -> None:
    f = fixture
    inputs, request, rows = setup_history(f, behavior)
    before = protected(f)
    state = json.loads((inputs.directory / "external-records.json").read_bytes())
    if behavior == "incomplete":
        state["history_pages"][1].update(has_more=True, page_token="another-page")  # noqa: S106
    if behavior == "duplicate":
        state["history_pages"][1]["items"] = [rows[0]]
    write_private(inputs.directory / "external-records.json", state)
    assert inputs.run("hold")[0] == 1
    with connect(f.config.database) as db:
        batch = required(
            db.execute(
                "SELECT * FROM business.p4_history_recoveries WHERE id=%s", (request.recovery_id,)
            ).fetchone()
        )
        assert batch["status"] == "hold"
        assert (
            required(
                db.execute(
                    "SELECT count(*) AS n FROM business.p4_history_messages WHERE recovery_id=%s",
                    (request.recovery_id,),
                ).fetchone()
            )["n"]
            == 0
        )
        calls = required(
            db.execute(
                "SELECT count(*) AS n FROM business.p4_sdk_calls WHERE window_id=%s",
                (request.recovery_id,),
            ).fetchone()
        )["n"]
    assert inputs.run("cold-hold")[0] == 1
    with connect(f.config.database) as db:
        assert (
            required(
                db.execute(
                    "SELECT count(*) AS n FROM business.p4_sdk_calls WHERE window_id=%s",
                    (request.recovery_id,),
                ).fetchone()
            )["n"]
            == calls
        )
    assert protected(f) == before


def test_history_first_live_cold_replay_keeps_reply_and_different_body_conflicts(
    fixture: P3Fixture,
) -> None:
    f = fixture
    inputs, request, rows = setup_history(f)
    assert inputs.run("collect")[0] == 0
    s = service(f)
    with connect(f.config.database) as db:
        originals = {
            x["message_id"]: x["reply_id"]
            for x in db.execute(
                "SELECT message_id,reply_id FROM business.p4_history_messages WHERE recovery_id=%s",
                (request.recovery_id,),
            ).fetchall()
        }
    for wire, text in zip(rows, request.expected_texts, strict=True):
        inbound = replace(message(f), message_id=wire["message_id"], text=text)
        result = s.message(inbound)
        assert result["duplicate"] and result["reply_id"] == str(originals[wire["message_id"]])
        with pytest.raises(WebFailure):
            s.message(replace(inbound, text=text + " "))
    with connect(f.config.database) as db:
        assert (
            required(
                db.execute(
                    "SELECT count(*) AS n FROM business.inbox_events WHERE message_id=ANY(%s)",
                    ([x["message_id"] for x in rows],),
                ).fetchone()
            )["n"]
            == 0
        )


def test_live_first_history_reuses_existing_carriers(fixture: P3Fixture) -> None:
    f = fixture
    inputs, request, rows = setup_history(f)
    s = service(f)
    before = [
        s.message(replace(message(f), message_id=wire["message_id"], text=text))["reply_id"]
        for wire, text in zip(rows, request.expected_texts, strict=True)
    ]
    assert inputs.run("collect")[0] == 0
    with connect(f.config.database) as db:
        after = db.execute(
            """
SELECT reply_id,existing_inbox_id FROM business.p4_history_messages WHERE
        recovery_id=%s ORDER BY kind DESC""",
            (request.recovery_id,),
        ).fetchall()
        assert {str(x["reply_id"]) for x in after} == set(before) and all(
            x["existing_inbox_id"] for x in after
        )


def test_new_history_tables_have_narrow_immutable_low_role_contract(fixture: P3Fixture) -> None:
    f = fixture
    inputs, request, _ = setup_history(f)
    assert inputs.run("collect")[0] == 0
    with connect(f.inventory.owner) as db:
        fk = db.execute("""SELECT condeferrable,condeferred FROM pg_constraint
            WHERE conrelid='business.p4_history_messages'::regclass
            AND confrelid='business.p4_read_replies'::regclass AND contype='f'""").fetchall()
        assert fk == [{"condeferrable": True, "condeferred": True}]
        reply_before = db.execute(
            """SELECT row_to_json(r)::text AS body
                    FROM business.p4_read_replies r ORDER BY id"""
        ).fetchall()
        history_before = db.execute(
            """SELECT row_to_json(m)::text AS body
                    FROM business.p4_history_messages m ORDER BY id"""
        ).fetchall()
        assert len(history_before) == 2
        with pytest.raises(FeatureNotSupported) as refused, db.transaction():
            db.execute("TRUNCATE business.p4_read_replies")
        actual_state = refused.value.sqlstate
        assert actual_state == "0A000"
        with pytest.raises(CheckViolation) as cascade_refused, db.transaction():
            db.execute("TRUNCATE business.p4_read_replies CASCADE")
        assert cascade_refused.value.sqlstate == "23514"
        assert (
            db.execute(
                """SELECT row_to_json(r)::text AS body
                    FROM business.p4_read_replies r ORDER BY id"""
            ).fetchall()
            == reply_before
        )
        assert (
            db.execute(
                """SELECT row_to_json(m)::text AS body
                    FROM business.p4_history_messages m ORDER BY id"""
            ).fetchall()
            == history_before
        )
        write_private(
            inputs.directory / "history-FK-truncate-rejection.safe.json",
            {
                "plain_actual_sqlstate": actual_state,
                "cascade_actual_sqlstate": cascade_refused.value.sqlstate,
                "native_FK_deferrable_initially_deferred": True,
                "reply_rows": len(reply_before),
                "history_rows": len(history_before),
                "all_related_row_bytes_unchanged": True,
            },
        )
    for table in ("p4_history_messages", "p4_read_message_sources"):
        with connect(f.config.database) as db, pytest.raises(InsufficientPrivilege):
            db.execute("DELETE FROM business." + table)  # noqa: S608
    with connect(f.config.database) as db, pytest.raises(CheckViolation):
        db.execute(
            """
UPDATE business.p4_history_recoveries SET status='collecting',
        completed_at=NULL WHERE id=%s""",
            (request.recovery_id,),
        )
    with pytest.raises(UniqueViolation):
        HistoryRecoveryStore(service(f)).register(request)


def captured_without_materialization(
    f: P3Fixture, inputs: ParentInputs, request: HistoryRecoveryRequest
) -> HistoryRecoveryStore:
    store = HistoryRecoveryStore(service(f))
    store.register(request)
    settings = BusinessSettings.model_validate_json(inputs.business.read_bytes())

    async def collect() -> None:
        session = WorkerSession(f.config.database, settings.organization_id)
        await session.start()
        try:
            factory = BusinessSDKFactory(
                settings, PersistentSDKLedger(session, request.window(settings))
            )
            with FakeHTTPTransport(
                inputs.directory / "external-records.json", settings
            ).installed():
                await factory.initialize()
                await factory.verify_bot()
                await collect_history(factory, request, store)
        finally:
            await session.close(clean=True)

    asyncio.run(collect())
    return store


@pytest.mark.parametrize("first", ["history", "live"])
def test_concurrent_live_and_history_use_same_reply_even_with_waiting_RR_snapshot(
    fixture: P3Fixture, first: str
) -> None:
    f = fixture
    inputs, request, rows = setup_history(f)
    history = captured_without_materialization(f, inputs, request)
    s = service(f)
    entered, release = Event(), Event()

    def pause(stage: str) -> None:
        if stage == ("before_history_commit" if first == "history" else "before_p4_commit"):
            entered.set()
            assert release.wait(15)

    inbound = replace(message(f), message_id=rows[0]["message_id"], text=request.expected_texts[0])
    if first == "history":
        history.business.hook = pause
    else:
        s.hook = pause
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = (
            pool.submit(history.finish, request)
            if first == "history"
            else pool.submit(s.message, inbound)
        )
        try:
            assert entered.wait(10)
            b = (
                pool.submit(s.message, inbound)
                if first == "history"
                else pool.submit(history.finish, request)
            )
            deadline = time.monotonic() + 10
            while True:
                with connect(f.config.database) as db:
                    waiting = required(
                        db.execute(
                            """
SELECT count(*) AS n FROM pg_stat_activity WHERE datname=current_database()
        AND wait_event='advisory'"""
                        ).fetchone()
                    )["n"]
                if waiting:
                    break
                assert time.monotonic() < deadline
                time.sleep(0.02)
        finally:
            release.set()
        left, right = a.result(timeout=15), b.result(timeout=15)
    history_receipts, live = (left, right) if first == "history" else (right, left)
    assert isinstance(history_receipts, tuple)
    assert isinstance(live, dict)
    assert history_receipts[0]["reply_id"] == live["reply_id"]
    with connect(f.config.database) as db:
        source = db.execute(
            """
SELECT * FROM business.p4_read_message_sources WHERE app_id=%s AND
        tenant_key=%s AND message_id=%s""",
            (request.app_id, request.tenant_key, rows[0]["message_id"]),
        ).fetchall()
        assert len(source) == 1
        if first == "history":
            assert source[0]["history_message_id"] is not None and source[0]["inbox_id"] is None
        else:
            assert source[0]["inbox_id"] is not None and source[0]["history_message_id"] is None


def test_history_IM_unknown_keeps_original_UUID_and_attempt_without_retry(
    fixture: P3Fixture,
) -> None:
    f = fixture
    inputs, request, rows = setup_history(f)
    assert inputs.run("collect")[0] == 0
    next_private = f.private / "unknown-send"
    next_private.mkdir(mode=0o700)
    sender = prepare_parent(
        replace(f, private=next_private), None, mode="read_reply", behavior="im_timeout"
    )
    settings = BusinessSettings.model_validate_json(sender.business.read_bytes())
    with connect(f.config.database) as db:
        template = read_reply_window_from_history(
            db,
            settings,
            recovery_id=request.recovery_id,
            original_message_id=rows[0]["message_id"],
            expires_at=datetime.now(UTC) + timedelta(seconds=60),
        )
    sender.bind_window(template.model_dump(mode="json"))
    assert sender.run("unknown")[0] == 1
    with connect(f.config.database) as db:
        original = required(
            db.execute(
                """SELECT status,attempts,provider_uuid
                    FROM business.p4_read_replies WHERE id=%s""",
                (template.reply_id,),
            ).fetchone()
        )
        assert original["status"] == "unknown" and original["attempts"] == 1
        calls = required(
            db.execute(
                "SELECT count(*) AS n FROM business.p4_sdk_calls WHERE window_id=%s",
                (template.window_id,),
            ).fetchone()
        )["n"]
        assert calls == 3
    assert sender.run("cold-unknown")[0] == 1
    with connect(f.config.database) as db:
        assert (
            required(
                db.execute(
                    """SELECT status,attempts,provider_uuid
                    FROM business.p4_read_replies WHERE id=%s""",
                    (template.reply_id,),
                ).fetchone()
            )
            == original
        )
        assert (
            required(
                db.execute(
                    "SELECT count(*) AS n FROM business.p4_sdk_calls WHERE window_id=%s",
                    (template.window_id,),
                ).fetchone()
            )["n"]
            == calls
        )
    assert len(list(sender.directory.glob("im-*.private.json"))) == 1


def test_current_revocation_precedes_history_registration_and_Secret(fixture: P3Fixture) -> None:
    f = fixture
    inputs, request, _ = setup_history(f)
    with connect(f.inventory.owner) as db:
        db.execute(
            "UPDATE business.principals SET enabled=false,auth_version=auth_version+1 WHERE id=%s",
            (request.principal_id,),
        )
    settings = BusinessSettings.model_validate_json(inputs.business.read_bytes())
    settings.app_secret_file.unlink()
    assert inputs.run("revoked")[0] == 1
    with connect(f.config.database) as db:
        assert (
            required(
                db.execute("SELECT count(*) AS n FROM business.p4_history_recoveries").fetchone()
            )["n"]
            == 0
        )
        assert (
            required(db.execute("SELECT count(*) AS n FROM business.p4_sdk_calls").fetchone())["n"]
            == 0
        )


def test_killed_native_auth_window_keeps_committed_once_and_does_not_retry(
    fixture: P3Fixture,
) -> None:
    f = fixture
    inputs, request, _ = setup_history(f, "auth_pause")
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(inputs.run, "interrupted")
        deadline = time.monotonic() + 15
        ready = inputs.directory / "external-records.auth.ready"
        while not ready.exists():
            assert time.monotonic() < deadline
            time.sleep(0.02)
        pid = json.loads((inputs.directory / "interrupted.spawn.safe.json").read_bytes())["PID"]
        os.killpg(pid, signal.SIGKILL)
        assert future.result(timeout=10)[0] == -signal.SIGKILL
        # Linux pytest PID1 adopts the killed canonical child. Reap only this
        # registered group; a zombie must not stand in for verified absence.
        reaped = []
        reap_deadline = time.monotonic() + 5
        while time.monotonic() < reap_deadline:
            try:
                child_pid, status = os.waitpid(-pid, os.WNOHANG)
            except ChildProcessError:
                child_pid = 0
            if child_pid:
                assert os.WIFSIGNALED(status) and os.WTERMSIG(status) == signal.SIGKILL
                reaped.append(child_pid)
                continue
            try:
                os.killpg(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.02)
        with pytest.raises(ProcessLookupError):
            os.killpg(pid, 0)
        write_private(
            inputs.directory / "interrupted-group-reaped.safe.json",
            {"PGID": pid, "adopted_children_reaped": reaped, "group_absent": True},
        )
    with connect(f.config.database) as db:
        assert (
            required(
                db.execute(
                    "SELECT status FROM business.p4_history_recoveries WHERE id=%s",
                    (request.recovery_id,),
                ).fetchone()
            )["status"]
            == "collecting"
        )
        calls = db.execute(
            "SELECT method,status FROM business.p4_sdk_calls WHERE window_id=%s",
            (request.recovery_id,),
        ).fetchall()
        assert calls == [{"method": "auth.v3.tenant_access_token.internal", "status": "started"}]
    assert inputs.run("cold-interrupted")[0] == 1
    with connect(f.config.database) as db:
        assert (
            db.execute(
                "SELECT method,status FROM business.p4_sdk_calls WHERE window_id=%s",
                (request.recovery_id,),
            ).fetchall()
            == calls
        )


def test_0016_upgrade_preserves_original_rows_payload_and_unknown_attempt(
    database: tuple[DatabaseSettings, DatabaseSettings], tmp_path: Path
) -> None:
    owner, app = database
    initialize_schema(owner, "0016")
    f = initialize_p3(owner, app, tmp_path)
    try:
        original = prepared(f)

        def snapshot() -> dict[str, list[str]]:
            result: dict[str, list[str]] = {}
            with connect(owner) as db:
                tables = db.execute("""SELECT schemaname,tablename FROM pg_tables
                  WHERE schemaname IN ('business','checkpoints') AND tablename NOT IN
                  ('alembic_version','web_credentials','web_sessions','web_login_attempts')""").fetchall()
                for table in tables:
                    expression = (
                        sql.SQL("(to_jsonb(t)-'history_message_id')::text")
                        if table["tablename"] == "p4_read_replies"
                        else sql.SQL("row_to_json(t)::text")
                    )
                    rows = db.execute(
                        sql.SQL("SELECT {} AS body FROM {}.{} t").format(
                            expression,
                            sql.Identifier(table["schemaname"]),
                            sql.Identifier(table["tablename"]),
                        )
                    ).fetchall()
                    result[table["schemaname"] + "." + table["tablename"]] = sorted(
                        row["body"] for row in rows
                    )
            return result

        # Preserve an actual spent/unknown original carrier across the additive migration.
        with connect(owner) as db:
            db.execute(
                """UPDATE business.p4_read_replies SET status='unknown',attempts=1,
              claimed_by='owned-stopped-writer',first_attempt_at=clock_timestamp(),last_error='SEND_ACK_UNPROVEN'
              WHERE id=%s""",
                (original["id"],),
            )
        before = snapshot()
        migrate(owner)
        grant_runtime(owner)
        after = snapshot()
        assert set(after) - set(before) == {
            "business.p4_history_recoveries",
            "business.p4_history_messages",
            "business.p4_read_message_sources",
        }
        assert all(after[key] == value for key, value in before.items())
        assert (
            not after["business.p4_history_recoveries"]
            and not after["business.p4_history_messages"]
        )
        assert len(after["business.p4_read_message_sources"]) == 1
        with connect(app) as db:
            row = required(
                db.execute(
                    "SELECT * FROM business.p4_read_replies WHERE id=%s", (original["id"],)
                ).fetchone()
            )
            assert (
                row["history_message_id"] is None
                and row["status"] == "unknown"
                and row["attempts"] == 1
            )
            assert (row["canonical_payload"], row["payload_hash"], row["provider_uuid"]) == (
                original["canonical_payload"],
                original["payload_hash"],
                original["provider_uuid"],
            )
            assert required(
                db.execute(
                    "SELECT business.p4_read_reply_current(%s) AS ok", (original["id"],)
                ).fetchone()
            )["ok"]
    finally:
        f.client.close()
