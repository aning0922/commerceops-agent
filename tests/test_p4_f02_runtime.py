"""Gateway选择→原单Worker→原UUID发送的离线Fake；不读秘密或连接PG/SDK。"""

import asyncio
import json
import subprocess
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from commerceops.adapters.feishu import business_factory
from commerceops.adapters.feishu.ledgered_sdk import ledgered_client
from commerceops.application.feishu_business.f02_window import F02WorkerWindow
from commerceops.application.feishu_business.gateway_window import GatewayWindow
from commerceops.application.feishu_business.sdk_window import SDKScope
from commerceops.application.replenishment.nl_preflight import Scope
from commerceops.domain.commerce_values import facts_hash
from commerceops.entrypoints import feishu_business as parent
from commerceops.entrypoints import feishu_worker_child as child
from commerceops.infrastructure import feishu_clarification as clarification
from commerceops.infrastructure.feishu_clarification_requests import F02Requests
from commerceops.infrastructure.feishu_gateway_window import claimed_state
from commerceops.infrastructure.queue import JobQueue
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.worker import Worker
from pydantic import ValidationError

from tests.test_p4_controlled_worker import configured
from tests.test_p4_f02 import candidate

pytestmark = pytest.mark.offline


class Cursor:
    def __init__(self, value: Any):
        self.value = value

    async def fetchone(self) -> Any:
        return self.value

    async def fetchall(self) -> Any:
        return self.value


class Memory:
    def __init__(self) -> None:
        self.settings, _, self.config = configured()
        self.settings = self.settings.model_copy(update={"f02_enabled": True})
        self.window = F02WorkerWindow.model_validate(
            {
                "schema_version": "p4-f02-worker-window-v1",
                "window_id": uuid4(),
                "gateway_window_id": uuid4(),
                "organization_id": self.settings.organization_id,
                "shop_id": self.settings.shop_id,
                "enabled": True,
                "expires_at": datetime.now(UTC) + timedelta(seconds=120),
                "method_caps": {
                    "auth.v3.tenant_access_token.internal": 1,
                    "bot.v3.info": 1,
                    "im.v1.message.create": 3,
                },
            }
        )
        self.gateway = GatewayWindow.model_validate(
            {
                "schema_version": "p4-gateway-v1",
                "window_id": self.window.gateway_window_id,
                "organization_id": self.window.organization_id,
                "shop_id": self.window.shop_id,
                "expires_at": self.window.expires_at,
                "enabled": True,
                "parameters": {
                    "source_mode": "mock",
                    "dataset_version": "inventory-v1",
                    "fixture_case": "baseline",
                    "L": 3,
                    "R": 7,
                    "S": 2,
                },
            }
        )
        self.claim: Any = {
            "after_state": claimed_state(self.gateway),
            "occurred_at": datetime.now(UTC) - timedelta(seconds=1),
        }
        self.principal, self.identity, self.task = uuid4(), uuid4(), uuid4()
        self.inbox_ids = [uuid4() for _ in range(3)]
        first = candidate(complete=False).model_copy(
            update={"scope": Scope(shop_id=self.window.shop_id)}
        )
        source = first.parameter_sources["L"].model_copy(update={"inbox_id": self.inbox_ids[0]})
        first = first.model_copy(update={"parameter_sources": {"L": source}})
        ready = candidate().model_copy(
            update={
                "request_id": first.request_id,
                "scope": first.scope,
                "round": 2,
                "parameter_sources": {
                    "L": source,
                    **{
                        k: source.model_copy(update={"inbox_id": self.inbox_ids[1]})
                        for k in ("R", "S")
                    },
                },
            }
        )
        created = ready.model_copy(update={"kind": "created", "task_id": self.task})
        self.candidates = [first, ready, created]
        self.rows: list[dict[str, Any]] = []
        self.selections: list[dict[str, Any]] = []
        self.receipts: dict[Any, dict[str, Any]] = {}
        for index, value in enumerate(self.candidates):
            identifier = uuid4()
            row: dict[str, Any] = {
                "id": identifier,
                "provider_uuid": uuid4(),
                "request_id": value.request_id,
                "inbox_id": self.inbox_ids[index],
                "organization_id": self.window.organization_id,
                "shop_id": self.window.shop_id,
                "principal_id": self.principal,
                "identity_id": self.identity,
                "chat_id": "synthetic-chat",
                "chat_type": "p2p",
                "app_id": self.settings.app_id,
                "tenant_key": self.settings.tenant_key,
                "external_subject": next(iter(self.settings.allowed_open_ids)),
                "auth_version": 1,
                "enabled": True,
                "identity_provider": "feishu",
                "status": "pending",
                "attempts": 0,
                "round": value.round,
                "kind": value.kind,
                "frozen_payload": value.model_dump(mode="json"),
                "frozen_payload_hash": facts_hash(value.model_dump(mode="json")),
            }
            self.rows.append(row)
            statements: list[Any] = []
            db = SimpleNamespace(
                execute=lambda query, params, statements=statements: statements.append(
                    (query, params)
                )
            )
            business = SimpleNamespace(
                shop=self.window.shop_id, f02_gateway_window_id=self.window.gateway_window_id
            )
            actor = SimpleNamespace(
                organization_id=self.window.organization_id,
                principal_id=self.principal,
                identity_id=self.identity,
            )
            message = SimpleNamespace(chat_id=row["chat_id"], chat_type="p2p")
            F02Requests(cast(Any, business))._reply(
                cast(Any, db),
                cast(Any, actor),
                cast(Any, message),
                row["inbox_id"],
                identifier,
                value,
            )
            assert len(statements) == 2 and "reply_selected" in statements[1][0]
            self.selections.append(statements[1][1][3].obj)
            self.receipts[row["inbox_id"]] = {
                "identity_id": self.identity,
                "task_id": self.task if index == 2 else None,
                "payload_hash": "a" * 64,
                "sanitized_payload": {
                    "principal_id": str(self.principal),
                    "auth_version": 1,
                    "chat_id": row["chat_id"],
                    "chat_type": "p2p",
                    "text_sha256": source.text_hash,
                },
                "result": {
                    "clarification_id": str(first.request_id),
                    "round": value.round,
                    "reply_id": str(identifier),
                    "candidate_hash": value.confirmation_hash(),
                    "clarification": value.model_dump(mode="json"),
                },
            }
        self.index = 0
        self.permitted = True
        self.calls: list[tuple[str, SDKScope]] = []
        self.messages: list[Any] = []
        self.factories = 0
        self.sessions: list[Any] = []
        self.workers: list[Any] = []
        self.outcome = "sent"
        self.stop_gateway_after_auth = False
        self.query_log: list[tuple[str, Any]] = []

    @property
    def row(self) -> dict[str, Any]:
        return self.rows[min(self.index, 2)]

    @property
    def current(self) -> dict[str, Any]:
        value = self.candidates[min(self.index, 1)]
        return {
            **{
                k: self.row[k]
                for k in (
                    "organization_id",
                    "shop_id",
                    "principal_id",
                    "identity_id",
                    "chat_id",
                    "chat_type",
                    "app_id",
                    "tenant_key",
                    "auth_version",
                )
            },
            "id": value.request_id,
            "origin_inbox_id": self.inbox_ids[0],
            "source_hash": "a" * 64,
            "request_key": uuid5(NAMESPACE_URL, f"p4-f02-t1:{value.request_id}"),
            "round": value.round,
            "candidate": value.model_dump(mode="json"),
            "candidate_hash": value.confirmation_hash(),
            "context": {k: value.model_dump(mode="json")[k] for k in ("source", "window", "scope")},
            "state": "consumed"
            if self.index == 2
            else ("awaiting_parameters" if self.index == 0 else "awaiting_confirmation"),
            "task_id": self.task if self.index == 2 else None,
            "expires_at": datetime.now(UTC) + timedelta(minutes=10),
        }

    async def __aenter__(self) -> "Memory":
        return self

    async def __aexit__(self, *_: Any) -> None:
        pass

    def transaction(self) -> "Memory":
        return self

    async def execute(self, query: str, params: Any = None) -> Cursor:
        self.query_log.append((query, params))
        if "gateway_start_claimed" in query:
            return Cursor(self.claim)
        if "reply_selected" in query:
            if "JOIN business.p4_clarification_replies" not in query:
                return Cursor({"after_state": self.selections[0]})
            return Cursor(
                {"after_state": self.selections[self.index]}
                if self.index < 3 and self.row["status"] in ("pending", "sending")
                else None
            )
        if "SELECT r.*" in query:
            assert params[0] == self.window.organization_id
            assert params[1] == params[2] == [self.row["request_id"]]
            if params[3] != self.row["id"]:
                return Cursor(None)
            return Cursor(
                self.row if self.row["status"] == "pending" and self.row["attempts"] == 0 else None
            )
        if "lock_p3_permission" in query:
            return Cursor({"allowed": self.permitted})
        if "SELECT * FROM business.p4_clarification_requests" in query:
            return Cursor(self.current)
        if "SELECT clock_timestamp" in query:
            return Cursor({"t": datetime.now(UTC)})
        if "FROM business.inbox_events" in query:
            return Cursor(self.receipts.get(params[0]))
        if "candidate_frozen" in query:
            return Cursor([{"after_state": {"candidate": self.current["candidate"]}}])
        if "SET status='unknown'" in query:
            assert params[-2:] == (self.row["id"], self.row["id"])
            if self.row["status"] == "sending":
                self.row["status"] = "unknown"
            return Cursor(None)
        if "SET status='dead'" in query:
            self.row["status"] = "dead"
            return Cursor(None)
        if "SET status='sending'" in query:
            assert self.row["status"] == "pending" and self.row["attempts"] == 0
            self.row.update(status="sending", attempts=1)
            return Cursor(None)
        if "SET status=%s" in query:
            assert self.row["status"] == "sending" and params[-1] == self.row["provider_uuid"]
            self.row["status"] = params[0]
            if params[0] == "sent":
                self.index += 1
            return Cursor(None)
        raise AssertionError("unexpected Fake SQL path")


def install(monkeypatch: pytest.MonkeyPatch, db: Memory) -> None:
    class Session:
        def __init__(self, settings: Any, organization: Any):
            self.settings, self.organization, self.owner = settings, organization, "synthetic-owner"
            self.started = False
            self.closed = False
            db.sessions.append(self)

        async def start(self) -> None:
            self.started = True

        async def check(self) -> None:
            assert self.started and not self.closed

        async def close(self, **_: Any) -> None:
            self.closed = True

    class Ledger:
        def __init__(self, session: Any, window: Any):
            self.session, self.window = session, window
            self.current: Any = None

        @contextmanager
        def scope(self, value: SDKScope) -> Any:
            old, self.current = self.current, value
            try:
                yield
            finally:
                self.current = old

        async def invoke(self, method: str, call: Any) -> Any:
            assert self.current is not None and self.window.allows(method)
            assert sum(m == method for m, _ in db.calls) < self.window.caps[method]
            db.calls.append((method, self.current))
            return await call()

    class Factory:
        def __init__(self, settings: Any, ledger: Any):
            db.factories += 1
            self.ledger, self.option = ledger, None

        async def initialize(self) -> None:
            with self.ledger.scope(SDKScope(db.window.window_id, None, "preflight")):
                await self.ledger.invoke("auth.v3.tenant_access_token.internal", AsyncMock())

        async def verify_bot(self) -> None:
            with self.ledger.scope(SDKScope(db.window.window_id, None, "preflight")):
                await self.ledger.invoke("bot.v3.info", AsyncMock())
            if db.stop_gateway_after_auth:
                db.claim = None

        def business_client(self) -> Any:
            async def send(request: Any, option: Any) -> Any:
                assert db.row["status"] == "sending" and db.row["attempts"] == 1
                db.messages.append(request.request_body)
                if db.outcome == "unknown":
                    raise RuntimeError("synthetic ACK loss")
                return SimpleNamespace(
                    raw=SimpleNamespace(status_code=200),
                    code=0,
                    data=SimpleNamespace(message_id="synthetic-ack", chat_id="synthetic-chat"),
                )

            forbidden = AsyncMock(side_effect=AssertionError("Base request forbidden"))
            client = SimpleNamespace(
                im=SimpleNamespace(v1=SimpleNamespace(message=SimpleNamespace(acreate=send))),
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

    class ActualWorker(Worker):
        def __init__(self, *args: Any, **kwargs: Any):
            assert kwargs["dispatch_jobs"] is False and args[1] is None
            db.workers.append(self)
            self.maintenance = kwargs["reconcile"]
            kwargs["reconcile"] = self.bounded_test_maintenance
            super().__init__(*args, **kwargs)

        async def bounded_test_maintenance(self) -> None:
            await self.maintenance()
            if db.index == 3 or db.row["status"] in ("dead", "unknown"):
                self.stop.set()

        async def run(self, stop: asyncio.Event) -> None:
            self.stop = stop
            await super().run(stop)

    async def connect(_: Any) -> Memory:
        return db

    monkeypatch.setattr(child, "WorkerSession", Session)
    monkeypatch.setattr(child, "PersistentSDKLedger", Ledger)
    monkeypatch.setattr(child, "BusinessSDKFactory", Factory)
    monkeypatch.setattr(child, "Worker", ActualWorker)
    monkeypatch.setattr(child, "open_async", connect)
    monkeypatch.setattr(clarification, "open_async", connect)
    monkeypatch.setattr(JobQueue, "claim", AsyncMock(side_effect=AssertionError("no job claim")))
    monkeypatch.setattr(
        JobQueue, "recover_confirmed", AsyncMock(side_effect=AssertionError("no job recovery"))
    )


def test_gateway_committed_selection_question_ready_created_uses_one_original_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = Memory()
    install(monkeypatch, db)
    result = asyncio.run(child.controlled_f02(db.settings, db.window, db.config))
    assert result["result"] == "window_stopped" and result["sent"] == 3
    assert result["business_graphs"] == result["base_requests"] == result["model_requests"] == 0
    assert len(db.sessions) == len(db.workers) == db.factories == 1 and db.sessions[0].closed
    assert [m for m, _ in db.calls] == ["auth.v3.tenant_access_token.internal", "bot.v3.info"] + [
        "im.v1.message.create"
    ] * 3
    assert [s.subject_id for m, s in db.calls if m == "im.v1.message.create"] == [
        r["id"] for r in db.rows
    ]
    assert [b.uuid for b in db.messages] == [str(r["provider_uuid"]) for r in db.rows]
    assert all(
        c.text() == json.loads(b.content)["text"]
        for c, b in zip(db.candidates, db.messages, strict=True)
    )
    assert all(r["status"] == "sent" and r["attempts"] == 1 for r in db.rows)


@pytest.mark.parametrize(
    "change",
    [
        "role",
        "actor",
        "origin_hash",
        "origin_principal",
        "origin_auth",
        "reply_id",
        "reply_hash",
        "provider",
        "scope",
        "parameter_receipt",
    ],
)
def test_invalid_current_actor_or_original_source_denied_before_factory(
    monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    db = Memory()
    if change == "role":
        db.permitted = False
    elif change == "actor":
        db.row["external_subject"] = "not-allowed"
    elif change == "origin_hash":
        db.receipts[db.inbox_ids[0]]["payload_hash"] = "b" * 64
    elif change == "origin_principal":
        db.receipts[db.inbox_ids[0]]["sanitized_payload"]["principal_id"] = str(uuid4())
    elif change == "origin_auth":
        db.receipts[db.inbox_ids[0]]["sanitized_payload"]["auth_version"] = 2
    elif change == "reply_id":
        db.receipts[db.inbox_ids[0]]["result"]["reply_id"] = str(uuid4())
    elif change == "reply_hash":
        db.row["frozen_payload_hash"] = "b" * 64
    elif change == "provider":
        db.row["identity_provider"] = "other"
    elif change == "scope":
        db.row["shop_id"] = uuid4()
    else:
        db.receipts[db.inbox_ids[0]]["sanitized_payload"]["text_sha256"] = "b" * 64
    install(monkeypatch, db)
    result = asyncio.run(child.controlled_f02(db.settings, db.window, db.config))
    assert result["sent"] == 0 and db.factories == 0 and db.calls == db.messages == []
    assert db.row["status"] == "dead" and db.row["attempts"] == 0 and db.sessions[0].closed


def test_ACK_loss_keeps_original_UUID_unknown_and_does_not_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = Memory()
    db.outcome = "unknown"
    install(monkeypatch, db)
    result = asyncio.run(child.controlled_f02(db.settings, db.window, db.config))
    assert result["result"] == "delivery_stopped" and result["sent"] == 0
    assert db.row["status"] == "unknown" and db.row["attempts"] == 1
    assert len(db.messages) == 1 and db.messages[0].uuid == str(db.row["provider_uuid"])
    assert len(db.calls) == 3 and db.sessions[0].closed
    again = asyncio.run(child.controlled_f02(db.settings, db.window, db.config))
    assert again["sent"] == 0 and len(db.calls) == 3 and len(db.messages) == 1
    assert db.row["status"] == "unknown" and db.row["attempts"] == 1


def test_selected_sending_orphan_is_unknown_before_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    db = Memory()
    db.row.update(status="sending", attempts=1, claimed_by="old-owner")
    install(monkeypatch, db)
    result = asyncio.run(child.controlled_f02(db.settings, db.window, db.config))
    assert result["sent"] == 0 and db.row["status"] == "unknown"
    assert db.factories == 0 and db.calls == db.messages == []
    assert db.row["attempts"] == 1 and db.sessions[0].closed


@pytest.mark.parametrize(
    "change", ["missing", "scope", "changed", "expiry", "selection_scope", "selection_extra"]
)
def test_current_gateway_and_exact_selection_fail_before_factory(
    monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    db = Memory()
    if change == "missing":
        db.claim = None
    elif change == "scope":
        db.claim["after_state"]["shop_id"] = str(uuid4())
    elif change == "changed":
        db.claim["after_state"]["verification_mode"] = "fake"
    elif change == "expiry":
        shorter = db.gateway.model_copy(
            update={"expires_at": db.window.expires_at - timedelta(seconds=1)}
        )
        db.claim["after_state"] = claimed_state(shorter)
    elif change == "selection_scope":
        db.selections[0]["gateway_window_id"] = str(uuid4())
    else:
        db.selections[0]["enabled"] = True
    install(monkeypatch, db)
    result = asyncio.run(child.controlled_f02(db.settings, db.window, db.config))
    assert result["result"] == "failed" and result["sent"] == 0
    assert db.factories == 0 and db.calls == db.messages == [] and db.sessions[0].closed


def test_gateway_termination_after_auth_still_denies_IM(monkeypatch: pytest.MonkeyPatch) -> None:
    db = Memory()
    db.stop_gateway_after_auth = True
    install(monkeypatch, db)
    result = asyncio.run(child.controlled_f02(db.settings, db.window, db.config))
    assert result["sent"] == 0 and db.row["status"] == "dead" and db.row["attempts"] == 0
    assert [m for m, _ in db.calls] == ["auth.v3.tenant_access_token.internal", "bot.v3.info"]
    assert db.messages == [] and db.sessions[0].closed


@pytest.mark.parametrize(
    "change", ["feature_off", "off", "scope", "method", "cap", "bool", "expired", "long", "naive"]
)
def test_default_off_bounded_caps_and_explicit_window_reject_before_runtime(change: str) -> None:
    db = Memory()
    value = db.window.model_dump()
    if change == "feature_off":
        db.settings = db.settings.model_copy(update={"f02_enabled": False})
    elif change == "off":
        value["enabled"] = False
    elif change == "scope":
        value["shop_id"] = uuid4()
    elif change == "method":
        value["method_caps"]["bitable.v1.app_table_record.list"] = 1
    elif change == "cap":
        value["method_caps"]["im.v1.message.create"] = 6
    elif change == "bool":
        value["method_caps"]["im.v1.message.create"] = True
    elif change == "expired":
        value["expires_at"] = datetime.now(UTC)
    elif change == "long":
        value["expires_at"] = datetime.now(UTC) + timedelta(seconds=301)
    else:
        value["expires_at"] = datetime.now()
    with pytest.raises((PermissionError, ValidationError)):
        F02WorkerWindow.model_validate(value).window(db.settings)


def test_gateway_selection_is_only_added_to_formal_trusted_mode() -> None:
    db = Memory()
    statements: list[Any] = []
    original = db.rows[0]
    value = db.candidates[0]
    business = SimpleNamespace(shop=db.window.shop_id, f02_gateway_window_id=None)
    F02Requests(cast(Any, business))._reply(
        cast(Any, SimpleNamespace(execute=lambda query, params: statements.append(query))),
        cast(
            Any,
            SimpleNamespace(
                organization_id=db.window.organization_id,
                principal_id=db.principal,
                identity_id=db.identity,
            ),
        ),
        cast(Any, SimpleNamespace(chat_id=original["chat_id"], chat_type="p2p")),
        original["inbox_id"],
        original["id"],
        value,
    )
    assert len(statements) == 1 and "reply_selected" not in statements[0]


def test_original_parent_enters_F02_child_with_gateway_window_and_no_business_ID_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = Memory()
    calls: list[Any] = []
    metadata = {
        Path("/synthetic/config"): db.settings.model_dump_json(),
        Path("/synthetic/window"): db.window.model_dump_json(),
    }
    assert "request_id" not in json.loads(metadata[Path("/synthetic/window")])
    assert "reply_id" not in json.loads(metadata[Path("/synthetic/window")])
    monkeypatch.setenv("COMMERCEOPS_MODE", "p4-controlled-test")
    monkeypatch.setattr(business_factory, "private_value", lambda path: metadata[path])
    monkeypatch.setattr(WebConfig, "from_file", staticmethod(lambda path: db.config))
    monkeypatch.setattr(parent, "confirm_worker_child", AsyncMock())

    class Process:
        returncode = 0
        pid = 123

        def communicate(self, **_: Any) -> Any:
            return json.dumps(
                {
                    "result": "window_stopped",
                    "verification_mode": "controlled_sdk",
                    "sent": 3,
                    "base_requests": 0,
                    "business_graphs": 0,
                }
            ).encode(), b""

        def poll(self) -> int:
            return 0

    def spawn(args: Any, **kwargs: Any) -> Any:
        calls.append((args, kwargs))
        return Process()

    monkeypatch.setattr(subprocess, "Popen", spawn)
    result = parent.run_worker(
        Path("/synthetic/config"), Path("/synthetic/window"), mode="f02_clarification"
    )
    assert result["result"] == "window_stopped" and result["child_reaped"] is True
    assert len(calls) == 1 and calls[0][0][-2:] == ["--mode", "f02_clarification"]
    assert calls[0][0][2] == "commerceops.entrypoints.feishu_worker_child"
    assert cast(dict[str, Any], result["official_summary"])["sent"] == 3
