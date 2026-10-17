"""新owned PG/0016，F02真实事务+Fake sender；原库/平台/Secret/provider0。"""

import asyncio
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from commerceops.application.feishu_business.clarification import (
    ClarificationMessage,
    F02Message,
    NoticeResult,
)
from commerceops.application.feishu_business.sdk_window import SDKWindow
from commerceops.application.replenishment.contracts import WebFailure
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_clarification import ClarificationDeliveryStore
from commerceops.infrastructure.feishu_sdk_ledger import PersistentSDKLedger
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.worker_lock import WorkerSession
from psycopg import sql
from psycopg.errors import CheckViolation, InsufficientPrivilege
from psycopg.types.json import Jsonb

from tests.p3_support import P3Fixture
from tests.test_p3_pg import fixture as fixture
from tests.test_p4_clarification_pg import business_counts, policy
from tests.test_p4_gateway_pg import message, service

pytestmark = pytest.mark.integration


def incoming(f: P3Fixture, text: str) -> Any:
    return replace(message(f), text=text)


def start(f: P3Fixture, *, complete: bool = False) -> tuple[Any, dict[str, Any]]:
    s = service(f, f02_enabled=True)
    result = s.message(incoming(f, "分析库存 L=3 R=7 S=2" if complete else "分析库存 L=3"))
    assert "task_id" not in result and "source_task_id" not in result
    return s, result


def turn(
    f: P3Fixture, result: dict[str, Any], *, confirm: bool = False, block: str = "R=7 S=2"
) -> Any:
    return incoming(
        f,
        ("确认澄清" if confirm else "补充澄清")
        + f" {result['clarification_id']} 第{result['round']}轮"
        + ("" if confirm else " " + block),
    )


def request_row(f: P3Fixture, identifier: str) -> dict[str, Any]:
    with connect(f.config.database) as db:
        row = db.execute(
            "SELECT * FROM business.p4_clarification_requests WHERE id=%s", (UUID(identifier),)
        ).fetchone()
        assert row
        return row


def checkpoints(f: P3Fixture) -> Any:
    with connect(f.config.database) as db:
        return {
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


def child_supplement(config_file: str, payload_file: str, result_file: str) -> None:
    from commerceops.adapters.feishu.contracts import MessageProbe, PlatformIdentity
    from commerceops.application.replenishment.contracts import Parameters
    from commerceops.infrastructure.feishu_business import FeishuBusinessStore
    from commerceops.infrastructure.replenishment_repository import ReplenishmentStore

    payload = json.loads(Path(payload_file).read_text())
    config = WebConfig.from_file(Path(config_file))
    s = FeishuBusinessStore(
        ReplenishmentStore(config, Path(payload["fixture_directory"])),
        UUID(payload["shop"]),
        Parameters.model_validate_json(json.dumps(payload["parameters"])),
        f02_enabled=True,
    )
    m = MessageProbe(
        payload["event"],
        payload["message"],
        payload["chat"],
        "p2p",
        PlatformIdentity(payload["app"], payload["tenant"], payload["open"]),
        payload["text"],
    )
    result = s.message(m)
    output = Path(result_file)
    output.write_text(json.dumps(result))
    output.chmod(0o600)


def test_persistent_partial_cross_process_round_history_and_zero_business_until_confirm(
    fixture: P3Fixture,
) -> None:
    f = fixture
    before, cp = business_counts(f), checkpoints(f)
    s, result = start(f)
    first = request_row(f, result["clarification_id"])
    msg = turn(f, result)
    payload = {
        "shop": str(s.shop),
        "parameters": s.parameters.model_dump(mode="json"),
        "event": msg.event_id,
        "message": msg.message_id,
        "chat": msg.chat_id,
        "app": msg.identity.app_id,
        "tenant": msg.identity.tenant_key,
        "open": msg.identity.open_id,
        "text": msg.text,
        "fixture_directory": str(s.store.fixture_directory),
    }
    p, out = f.private / "f02-turn.json", f.private / "f02-result.json"
    p.write_text(json.dumps(payload))
    p.chmod(0o600)
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys;from tests.test_p4_f02_pg import child_supplement;"
            "child_supplement(*sys.argv[1:])",
            str(f.config_file),
            str(p),
            str(out),
        ],
        capture_output=True,
        timeout=15,
    )
    if child.returncode:
        log = f.private / "f02-child-failure.private.txt"
        log.write_bytes(child.stderr)
        log.chmod(0o600)
        raise AssertionError("F02 child failed; protected evidence retained")
    ready = json.loads(out.read_text())
    assert ready["round"] == 2 and ready["clarification_state"] == "awaiting_confirmation"
    assert business_counts(f) == before and checkpoints(f) == cp
    current = request_row(f, result["clarification_id"])
    assert (
        current["expires_at"] == first["expires_at"]
        and current["request_key"] == first["request_key"]
    )
    assert current["candidate"]["parameters"] == {"L": 3, "R": 7, "S": 2}
    with connect(f.config.database) as db:
        history = db.execute(
            "SELECT after_state FROM business.audit_events WHERE "
            "source='feishu_clarification' AND entity_id=%s ORDER BY occurred_at",
            (result["clarification_id"],),
        ).fetchall()
        assert [h["after_state"]["candidate"]["round"] for h in history] == [1, 2]
        assert all(h["after_state"]["candidate_hash"] for h in history)
    with connect(f.inventory.owner) as db:
        revision = db.execute("SELECT version_num FROM business.alembic_version").fetchone()
        assert revision == {"version_num": "0016_p4_clarification_requests"}
        tables = db.execute(
            "SELECT count(*) AS n FROM pg_tables WHERE schemaname IN ('business','checkpoints')"
        ).fetchone()
        assert tables == {"n": 56}
    with connect(f.config.database) as db:
        bits = db.execute(
            "SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user"
        ).fetchone()
        assert bits == {"rolsuper": False, "rolcreatedb": False, "rolcreaterole": False}
    with pytest.raises(WebFailure) as old:
        s.message(turn(f, result, confirm=True))
    assert old.value.code == "CLARIFICATION_ROUND_CONFLICT"
    assert business_counts(f) == before


def test_concurrent_confirm_same_T1_key_replay_and_consumed_never_new_round(
    fixture: P3Fixture,
) -> None:
    f = fixture
    s, ready = start(f, complete=True)
    before = business_counts(f)
    messages = [turn(f, ready, confirm=True) for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(s.message, messages))
    assert len({r["task_id"] for r in results}) == 1
    assert len({r["source_task_id"] for r in results}) == 1
    assert sum(not r["duplicate"] for r in results) == 1
    for m in messages:
        assert s.message(m)["task_id"] == results[0]["task_id"]
    assert s.message(turn(f, ready, confirm=True))["task_id"] == results[0]["task_id"]
    current = request_row(f, ready["clarification_id"])
    assert current["state"] == "consumed" and current["round"] == 1
    assert str(current["task_id"]) == results[0]["task_id"]
    after = business_counts(f)
    assert after["business_tasks"] - before["business_tasks"] == 2
    assert after["jobs"] - before["jobs"] == 2
    assert all(after[k] == before[k] for k in before if k not in ("business_tasks", "jobs"))
    with pytest.raises(WebFailure):
        s.message(turn(f, ready, block="L=4"))
    with connect(f.config.database) as db:
        rows = db.execute(
            "SELECT template_version,kind FROM business.p4_clarification_replies "
            "ORDER BY created_at"
        ).fetchall()
        assert rows == [
            {"template_version": "p4-f02-reply-v1", "kind": "ready"},
            {"template_version": "p4-f02-reply-v1", "kind": "created"},
        ]
        with pytest.raises(CheckViolation), db.transaction():
            db.execute(
                "UPDATE business.p4_clarification_requests SET round=2 WHERE id=%s",
                (UUID(ready["clarification_id"]),),
            )


def test_T1_consume_fault_rolls_back_every_task_job_and_receipt_then_same_key_succeeds(
    fixture: P3Fixture,
) -> None:
    f = fixture
    s, ready = start(f, complete=True)
    before = business_counts(f)
    original = request_row(f, ready["clarification_id"])
    m = turn(f, ready, confirm=True)

    def failure(stage: str) -> None:
        if stage == "before_f02_consume":
            raise RuntimeError("synthetic F02 transactional fault")

    s.hook = failure
    with pytest.raises(RuntimeError):
        s.message(m)
    assert business_counts(f) == before
    assert request_row(f, ready["clarification_id"]) == original
    s.hook = None
    result = s.message(m)
    assert result["clarification_state"] == "consumed"
    assert s.message(m)["task_id"] == result["task_id"]


@pytest.mark.parametrize(
    "wrong", ["chat", "app", "tenant", "actor", "revoke_restore", "identity", "round", "scope"]
)
def test_full_current_scope_and_initial_auth_guard_denies_without_candidate_or_business_mutation(
    fixture: P3Fixture,
    wrong: str,
) -> None:
    f = fixture
    s, ready = start(f, complete=True)
    m = turn(f, ready, confirm=True)
    if wrong == "chat":
        m = replace(m, chat_id="wrong-synthetic-chat")
    elif wrong in ("app", "tenant", "actor"):
        identity = m.identity
        m = replace(
            m,
            identity=replace(
                identity,
                **{
                    {"app": "app_id", "tenant": "tenant_key", "actor": "open_id"}[
                        wrong
                    ]: "wrong-synthetic"
                },
            ),
        )
    elif wrong == "round":
        m = replace(m, text=m.text.replace("第1轮", "第2轮"))
    elif wrong == "scope":
        s.parameters = s.parameters.model_copy(update={"L": 4})
    elif wrong == "revoke_restore":
        with connect(f.inventory.owner) as db:
            db.execute(
                "UPDATE business.principal_role_shop_grants SET enabled=false WHERE role='operator'"
            )
            db.execute(
                "UPDATE business.principal_role_shop_grants SET enabled=true WHERE role='operator'"
            )
    else:
        with connect(f.inventory.owner) as db:
            db.execute(
                "UPDATE business.identities SET external_subject='remapped-synthetic' "
                "WHERE provider='feishu'"
            )
    before, row = business_counts(f), request_row(f, ready["clarification_id"])
    with pytest.raises(WebFailure):
        s.message(m)
    assert business_counts(f) == before and request_row(f, ready["clarification_id"]) == row


class Sender:
    def __init__(self, ledger: PersistentSDKLedger, *, unknown: bool = False):
        self.ledger, self.unknown = ledger, unknown
        self.calls: list[F02Message] = []

    async def send_clarification(self, request: ClarificationMessage) -> NoticeResult:
        raise AssertionError("F02 selected mode must not send legacy or other pending rows")

    async def send_f02(self, request: F02Message) -> NoticeResult:
        self.calls.append(request)

        async def actual_fake() -> Any:
            return SimpleNamespace(raw=SimpleNamespace(status_code=200), code=0)

        await self.ledger.invoke("im.v1.message.create", actual_fake)
        return NoticeResult(
            outcome="unknown" if self.unknown else "sent",
            code="SYNTHETIC_F02",
            message_id=None if self.unknown else "synthetic-message",
        )


@pytest.mark.parametrize("unknown", [False, True])
def test_selected_v2_skips_stale_and_other_requests_and_unknown_never_resends(
    fixture: P3Fixture,
    unknown: bool,
) -> None:
    f = fixture
    s, original = start(f)
    ready = s.message(turn(f, original))
    _, other = start(f, complete=True)
    before = business_counts(f)

    async def run() -> None:
        session = WorkerSession(f.config.database, f.actor.organization_id)
        await session.start()
        try:
            ledger = PersistentSDKLedger(
                session,
                SDKWindow(
                    uuid4(),
                    f.actor.organization_id,
                    f.inventory.data.shop,
                    datetime.now(UTC) + timedelta(seconds=60),
                    {"im.v1.message.create": 1},
                    enabled=True,
                    verification_mode="controlled_sdk",
                ),
            )
            sender = Sender(ledger, unknown=unknown)
            store = ClarificationDeliveryStore(
                session,
                policy(f),
                sender,
                controlled_sender=True,
                ledger=ledger,
                request_ids=frozenset({UUID(ready["clarification_id"])}),
                f02_sender=sender,
            )
            assert await store.dispatch_one() == "denied"
            assert await store.dispatch_one() == ("unknown" if unknown else "sent")
            assert await store.dispatch_one() == "idle"
            await store.reconcile()
            assert len(sender.calls) == 1 and sender.calls[0].candidate.round == 2
            assert sender.calls[0].text == sender.calls[0].candidate.text()
            with connect(f.config.database) as db:
                assert db.execute(
                    "SELECT count(*) AS n FROM business.p4_sdk_calls WHERE window_id=%s",
                    (ledger.window.window_id,),
                ).fetchone() == {"n": 1}
        finally:
            await session.close(clean=True)

    asyncio.run(run())
    assert business_counts(f) == before
    with connect(f.config.database) as db:
        assert db.execute(
            "SELECT status FROM business.p4_clarification_replies WHERE request_id=%s",
            (UUID(other["clarification_id"]),),
        ).fetchall() == [{"status": "pending"}]


def test_fixed_15min_DB_expired_synthetic_request_and_immutable_expiry(fixture: P3Fixture) -> None:
    f = fixture
    s, result = start(f)
    original = request_row(f, result["clarification_id"])
    with connect(f.config.database) as db:
        with pytest.raises(InsufficientPrivilege), db.transaction():
            db.execute(
                "UPDATE business.p4_clarification_requests "
                "SET expires_at=expires_at+interval '1 minute' "
                "WHERE id=%s",
                (UUID(result["clarification_id"]),),
            )
    with connect(f.inventory.owner) as db:
        with pytest.raises(CheckViolation), db.transaction():
            db.execute(
                "UPDATE business.p4_clarification_requests "
                "SET expires_at=expires_at+interval '1 minute' WHERE id=%s",
                (UUID(result["clarification_id"]),),
            )
    # 新自有库仅本测试合成fixture，明确预置已过期时间；不改实际或旧来源时间证明。
    m = incoming(f, "synthetic expiry fixture")
    identifier, inbox = uuid4(), uuid4()
    with connect(f.inventory.owner) as db:
        actor = s.actor(db, m.identity, m.chat_id)
        copy = dict(original)
        copy.update(id=identifier, origin_inbox_id=inbox, request_key=uuid4(), source_hash="c" * 64)
        copy["candidate"] = {**copy["candidate"], "request_id": str(identifier)}
        from commerceops.application.feishu_business.clarification import F02Candidate

        candidate = F02Candidate.model_validate_json(json.dumps(copy["candidate"]))
        copy["candidate_hash"] = candidate.confirmation_hash()
        s._record(
            db,
            actor,
            m.event_id,
            m.message_id,
            "c" * 64,
            {
                "schema_version": "p4-v1",
                "clarification_id": str(identifier),
                "round": 1,
                "candidate_hash": copy["candidate_hash"],
                "clarification": copy["candidate"],
            },
            {"schema_version": "p4-v1", "auth_version": actor.auth_version},
            inbox_id=inbox,
        )
        clock = db.execute("SELECT clock_timestamp() AS t").fetchone()
        assert clock
        timestamp = clock["t"]
        copy.update(
            created_at=timestamp - timedelta(minutes=16),
            expires_at=timestamp - timedelta(minutes=1),
        )
        keys = list(copy)
        db.execute(
            sql.SQL("INSERT INTO business.p4_clarification_requests ({}) VALUES ({})").format(
                sql.SQL(",").join(map(sql.Identifier, keys)),
                sql.SQL(",").join(sql.Placeholder() for _ in keys),
            ),
            [Jsonb(copy[k]) if isinstance(copy[k], dict) else copy[k] for k in keys],
        )
    before = business_counts(f)
    with pytest.raises(WebFailure) as expired:
        s.message(incoming(f, f"确认澄清 {identifier} 第1轮"))
    assert expired.value.code == "CLARIFICATION_EXPIRED" and business_counts(f) == before


@pytest.mark.parametrize("outcome", ["sent", "unknown"])
def test_runtime_gateway_selected_chain_original_worker_ledger_and_no_Base(
    fixture: P3Fixture, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    """本源码批只collect；由后续精确CI在新库执行，Factory/transport始终Fake。"""
    from commerceops.adapters.feishu.business_config import BusinessSettings
    from commerceops.adapters.feishu.ledgered_sdk import ledgered_client
    from commerceops.application.feishu_business.f02_window import F02WorkerWindow
    from commerceops.application.feishu_business.gateway_window import GatewayWindow
    from commerceops.application.feishu_business.sdk_window import SDKScope
    from commerceops.entrypoints import feishu_worker_child as child
    from commerceops.entrypoints.feishu_gateway_child import BoundedReceiver
    from commerceops.infrastructure.feishu_business import FeishuBusinessStore
    from commerceops.infrastructure.feishu_gateway_window import claimed_state, guard_gateway

    f = fixture
    original = service(f)
    gateway = GatewayWindow.model_validate(
        {
            "schema_version": "p4-gateway-v1",
            "window_id": uuid4(),
            "organization_id": f.inventory.data.organization,
            "shop_id": f.inventory.data.shop,
            "expires_at": datetime.now(UTC) + timedelta(seconds=120),
            "enabled": True,
            "parameters": original.parameters,
        }
    )
    with connect(f.inventory.owner) as db:
        db.execute(
            """INSERT INTO business.audit_events(id,organization_id,source,action,
            entity_type,entity_id,after_state,trace_id) VALUES(%s,%s,'feishu_gateway',
            'gateway_start_claimed','gateway_window',%s,%s,%s)""",
            (
                gateway.window_id,
                gateway.organization_id,
                str(gateway.window_id),
                Jsonb(claimed_state(gateway)),
                gateway.window_id,
            ),
        )
    s = FeishuBusinessStore(
        original.store,
        original.shop,
        original.parameters,
        f02_enabled=True,
        f02_gateway_window_id=gateway.window_id,
        gateway_guard=lambda db, create: guard_gateway(db, gateway, create),
    )
    receiver = BoundedReceiver(s, gateway)
    before, cp = business_counts(f), checkpoints(f)
    first = receiver.message(incoming(f, "分析库存 L=3"))
    assert business_counts(f) == before
    sdk_settings = BusinessSettings.model_validate(
        {
            "schema_version": "p4-v1",
            "organization_id": gateway.organization_id,
            "shop_id": gateway.shop_id,
            "app_id": f.inventory.data.app,
            "tenant_key": f.inventory.data.tenant,
            "bot_open_id": "synthetic-bot",
            "allowed_open_ids": policy(f).allowed_open_ids,
            "allowed_group_chat_ids": policy(f).allowed_group_chat_ids,
            "app_secret_file": Path("/never-read/f02-secret"),
            "web_config_file": Path("/never-read/f02-web-config"),
            "base_target_key": "unused-f02",
            "base_app_token_file": Path("/never-read/f02-base"),
            "base_table_name": "unused-f02",
            "f02_enabled": True,
        }
    )
    window = F02WorkerWindow.model_validate(
        {
            "schema_version": "p4-f02-worker-window-v1",
            "window_id": uuid4(),
            "gateway_window_id": gateway.window_id,
            "organization_id": gateway.organization_id,
            "shop_id": gateway.shop_id,
            "expires_at": gateway.expires_at,
            "enabled": True,
            "method_caps": {
                "auth.v3.tenant_access_token.internal": 1,
                "bot.v3.info": 1,
                "im.v1.message.create": 3,
            },
        }
    )
    sent: list[Any] = []
    turn_result = first

    class Factory:
        def __init__(self, settings: Any, ledger: Any):
            self.ledger, self.option = ledger, None

        async def initialize(self) -> None:
            with self.ledger.scope(SDKScope(window.window_id, None, "preflight")):
                await self.ledger.invoke(
                    "auth.v3.tenant_access_token.internal",
                    AsyncMock(
                        return_value=SimpleNamespace(raw=SimpleNamespace(status_code=200), code=0)
                    ),
                )

        async def verify_bot(self) -> None:
            with self.ledger.scope(SDKScope(window.window_id, None, "preflight")):
                await self.ledger.invoke(
                    "bot.v3.info",
                    AsyncMock(
                        return_value=SimpleNamespace(raw=SimpleNamespace(status_code=200), code=0)
                    ),
                )

        def business_client(self) -> Any:
            async def create(request: Any, option: Any) -> Any:
                nonlocal turn_result
                sent.append(request.request_body)
                if outcome == "unknown":
                    raise RuntimeError("synthetic ACK loss")
                if len(sent) == 1:
                    turn_result = receiver.message(turn(f, turn_result, block="R=7 S=2"))
                elif len(sent) == 2:
                    turn_result = receiver.message(turn(f, turn_result, confirm=True))
                return SimpleNamespace(
                    raw=SimpleNamespace(status_code=200),
                    code=0,
                    data=SimpleNamespace(
                        message_id="synthetic-ack", chat_id=request.request_body.receive_id
                    ),
                )

            forbidden = AsyncMock(side_effect=AssertionError("no Base method"))
            client = SimpleNamespace(
                im=SimpleNamespace(v1=SimpleNamespace(message=SimpleNamespace(acreate=create))),
                bitable=SimpleNamespace(
                    v1=SimpleNamespace(
                        app_table_record=SimpleNamespace(
                            acreate=forbidden, alist=forbidden, aupdate=forbidden
                        ),
                        app_table=SimpleNamespace(alist=forbidden),
                        app_table_field=SimpleNamespace(alist=forbidden),
                    )
                ),
            )
            return ledgered_client(client, self.ledger)

    monkeypatch.setattr(child, "BusinessSDKFactory", Factory)
    result = asyncio.run(child.controlled_f02(sdk_settings, window, f.config))
    assert result["business_graphs"] == result["base_requests"] == result["model_requests"] == 0
    assert checkpoints(f) == cp
    with connect(f.config.database) as db:
        replies = db.execute(
            "SELECT provider_uuid,status,attempts FROM business.p4_clarification_replies "
            "WHERE request_id=%s ORDER BY created_at,id",
            (UUID(first["clarification_id"]),),
        ).fetchall()
        calls = db.execute(
            "SELECT method,count(*) AS n FROM business.p4_sdk_calls WHERE window_id=%s "
            "GROUP BY method",
            (window.window_id,),
        ).fetchall()
    assert [body.uuid for body in sent] == [str(r["provider_uuid"]) for r in replies]
    assert all(r["attempts"] == 1 for r in replies)
    assert {r["method"]: r["n"] for r in calls} == {
        "auth.v3.tenant_access_token.internal": 1,
        "bot.v3.info": 1,
        "im.v1.message.create": 3 if outcome == "sent" else 1,
    }
    after = business_counts(f)
    if outcome == "sent":
        assert result["result"] == "window_stopped" and result["sent"] == 3
        assert [r["status"] for r in replies] == ["sent"] * 3
        assert after["business_tasks"] - before["business_tasks"] == 2
        assert after["jobs"] - before["jobs"] == 2
        assert all(after[k] == before[k] for k in before if k not in ("business_tasks", "jobs"))
        assert (
            receiver.message(turn(f, turn_result, confirm=True))["task_id"]
            == turn_result["task_id"]
        )
        assert business_counts(f) == after
    else:
        assert result["result"] == "delivery_stopped" and replies[0]["status"] == "unknown"
        assert after == before and len(sent) == 1
