"""真实隔离 PG + 官方 SDK，外部 Base 为离线替身；缺 PG 配置直接失败。"""

import copy
import json
import secrets
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import lark_oapi as lark  # type: ignore[import-untyped]
import pytest
from commerceops.adapters.feishu.base import PROBE_MARKER, ApiReply, BaseProbe
from commerceops.adapters.feishu.config import runtime_pool
from commerceops.adapters.feishu.contracts import ProbeContractError, ProbePlan, ProbePolicy
from commerceops.adapters.feishu.probe_schema import setup_probe_schema
from commerceops.adapters.feishu.repository import (
    ProbeConflict,
    ProbeDatabaseFailure,
    ProbeRepository,
)
from commerceops.adapters.feishu.sdk import ProbeGateway
from commerceops.adapters.feishu.send import CardSender
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.repository import TaskScope
from psycopg import Connection, errors, sql
from pytest import MonkeyPatch as Patch

from tests.pg_support import seed
from tests.test_feishu_contracts import fixture

pytestmark = pytest.mark.integration


@dataclass
class Store:
    owner: DatabaseSettings
    runtime: DatabaseSettings
    scope: TaskScope
    policy: ProbePolicy
    repository: ProbeRepository
    plan: ProbePlan
    actor_a: UUID

    def message(self) -> dict[str, Any]:
        payload = fixture("message_group")
        payload["header"].update(app_id=self.policy.app_id, tenant_key=self.policy.tenant_key)
        payload["header"]["event_id"] = str(uuid4())
        payload["event"]["sender"].update(tenant_key=self.policy.tenant_key)
        payload["event"]["message"]["message_id"] = str(uuid4())
        payload["event"]["message"]["chat_id"] = self.plan.chat_id
        payload["event"]["message"]["mentions"][0]["tenant_key"] = self.policy.tenant_key
        return payload

    def card(
        self, action: str = "approve_with_assumptions", actor: str = "probe-user-a"
    ) -> dict[str, Any]:
        payload = fixture("card_callback")
        payload["header"].update(app_id=self.policy.app_id, tenant_key=self.policy.tenant_key)
        payload["header"]["event_id"] = str(uuid4())
        payload["event"]["operator"].update(tenant_key=self.policy.tenant_key, open_id=actor)
        payload["event"]["context"].update(
            open_chat_id=self.plan.chat_id, open_message_id=self.plan.message_id
        )
        payload["event"]["action"]["value"] = self.plan.callback_value(action)
        return payload


@pytest.fixture
def store() -> Store:
    owner = DatabaseSettings()
    assert owner.runtime_password_file is not None
    setup_probe_schema(owner)
    runtime = owner.model_copy(
        update={"user": "commerceops_app", "password_file": owner.runtime_password_file}
    )
    with connect(owner) as connection:
        data = seed(connection)
        for subject, actor in (("probe-user-a", data.principal), ("probe-user-b", uuid4())):
            if actor == data.principal:
                connection.execute(
                    """UPDATE business.principals SET roles=ARRAY['operator','approver'],
                    auth_version=auth_version+1 WHERE id=%s""",
                    (actor,),
                )
            else:
                connection.execute(
                    """INSERT INTO business.principals(id,organization_id,display_name,roles)
                    VALUES (%s,%s,'probe actor',ARRAY['operator','approver'])""",
                    (actor, data.organization),
                )
            connection.execute(
                """INSERT INTO business.identities
                (id,organization_id,principal_id,provider,app_id,tenant_key,external_subject)
                VALUES (%s,%s,%s,'feishu',%s,%s,%s)""",
                (uuid4(), data.organization, actor, data.app, data.tenant, subject),
            )
    scope = TaskScope(data.organization, data.shop)
    policy = ProbePolicy(
        data.app,
        data.tenant,
        "probe-bot",
        frozenset({"probe-user-a", "probe-user-b"}),
        frozenset({"probe-group"}),
    )
    plan = ProbePlan(
        str(uuid4()),
        str(uuid4()),
        str(uuid4()),
        str(uuid4()),
        1,
        "a" * 64,
        ("inbound_unknown_zero:probe_sku_1", "inbound_unknown_zero:probe_sku_2"),
        secrets.token_urlsafe(32),
        datetime.now(UTC) + timedelta(minutes=5),
        "probe-group",
        str(uuid4()),
    )
    repository = ProbeRepository(lambda: connect(runtime), scope, policy)
    repository.register_card(plan)
    return Store(owner, runtime, scope, policy, repository, plan, data.principal)


def count(store: Store, table: str) -> int:
    # 名称仅来自测试内固定允许集合，不插入任意用户输入。
    assert table in {"receipts", "cards", "base_operations"}
    with connect(store.runtime) as connection:
        row = connection.execute(
            sql.SQL("SELECT count(*) AS n FROM feishu_probe.{} WHERE organization_id=%s").format(
                sql.Identifier(table)
            ),
            (store.scope.organization_id,),
        ).fetchone()
        assert row is not None
        return int(row["n"])


def test_runtime_schema_permissions_and_no_business_side_effect(store: Store) -> None:
    with connect(store.runtime) as connection:
        assert connection.execute("SELECT current_user AS role").fetchone() == {
            "role": "commerceops_app"
        }
    with pytest.raises(errors.InsufficientPrivilege), connect(store.runtime) as connection:
        connection.execute("DELETE FROM feishu_probe.receipts")
    with pytest.raises(errors.InsufficientPrivilege), connect(store.runtime) as connection:
        connection.execute("CREATE TABLE feishu_probe.forbidden(id int)")
    store.repository.receive_card(store.card())
    with connect(store.runtime) as connection:
        for table in ("business_tasks", "jobs", "audit_events"):
            row = connection.execute(
                sql.SQL("SELECT count(*) AS n FROM business.{} WHERE organization_id=%s").format(
                    sql.Identifier(table)
                ),
                (store.scope.organization_id,),
            ).fetchone()
            assert row is not None
            assert row["n"] == (1 if table == "business_tasks" else 0)


def test_message_event_aliases_and_payload_conflicts_are_durable(store: Store) -> None:
    payload = store.message()
    first = store.repository.receive_message(payload)
    assert store.repository.receive_message(payload).result.startswith("duplicate")
    alias = copy.deepcopy(payload)
    alias["header"]["event_id"] = str(uuid4())
    assert store.repository.receive_message(alias).receipt_id == first.receipt_id
    assert count(store, "receipts") == 1
    changed = copy.deepcopy(alias)
    changed["event"]["message"]["message_id"] = str(uuid4())
    with pytest.raises(ProbeConflict):
        store.repository.receive_message(changed)
    assert count(store, "receipts") == 1
    with connect(store.runtime) as connection:
        row = connection.execute(
            "SELECT sanitized_payload FROM feishu_probe.receipts WHERE id=%s", (first.receipt_id,)
        ).fetchone()
        assert row is not None
        assert "token" not in json.dumps(row)
        assert "技术探针" not in json.dumps(row, ensure_ascii=False)


def test_card_same_message_multiple_callbacks_repeat_and_conflict(store: Store) -> None:
    payload = store.card()
    assert store.repository.receive_card(payload).result.startswith("probe_recorded")
    assert store.repository.receive_card(payload).result.startswith("duplicate:")
    repeated = store.card()
    repeated["event"]["action"]["value"]["acknowledged_assumption_keys"].reverse()
    assert store.repository.receive_card(repeated).result.startswith("duplicate_decision")
    assert (
        store.repository.receive_card(store.card("reject_assumptions", "probe-user-b")).result
        == "decision_conflict"
    )
    assert count(store, "receipts") == 3
    with connect(store.runtime) as connection:
        row = connection.execute(
            "SELECT decision,decided_by,binding FROM feishu_probe.cards WHERE id=%s",
            (UUID(store.plan.probe_id),),
        ).fetchone()
        assert row is not None and row["decided_by"] == store.actor_a
        assert row["decision"] == "approve_with_assumptions"
        assert store.plan.nonce not in json.dumps(row["binding"])


def test_two_actors_opposite_clicks_have_one_first_decision(store: Store) -> None:
    payloads = [store.card(), store.card("reject_assumptions", "probe-user-b")]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(store.repository.receive_card, payloads))
    assert sorted(result.result.split(":")[0] for result in results) == [
        "decision_conflict",
        "probe_recorded",
    ]
    assert count(store, "receipts") == 2


@pytest.mark.parametrize("change", ["disabled", "role", "tenant", "nonce", "keys", "expired"])
def test_pg_identity_and_bound_contract_rejection(store: Store, change: str) -> None:
    payload = store.card()
    with connect(store.owner) as connection:
        if change == "disabled":
            connection.execute(
                """UPDATE business.principals SET enabled=false,
                auth_version=auth_version+1 WHERE id=%s""",
                (store.actor_a,),
            )
        elif change == "role":
            connection.execute(
                """UPDATE business.principals SET roles=ARRAY['operator'],
                auth_version=auth_version+1 WHERE id=%s""",
                (store.actor_a,),
            )
        elif change == "expired":
            connection.execute(
                """UPDATE feishu_probe.cards SET expires_at=clock_timestamp()-interval '1 second'
                WHERE id=%s""",
                (UUID(store.plan.probe_id),),
            )
    if change == "tenant":
        payload["event"]["operator"]["tenant_key"] = "other-tenant"
    elif change == "nonce":
        payload["event"]["action"]["value"]["nonce"] = "x" * 32
    elif change == "keys":
        payload["event"]["action"]["value"]["acknowledged_assumption_keys"] = []
    with pytest.raises(ProbeContractError):
        store.repository.receive_card(payload)
    assert count(store, "receipts") == 0


def test_real_commit_failure_rolls_back_and_sdk_cannot_return_success(store: Store) -> None:
    @contextmanager
    def commit_failure() -> Iterator[Connection[dict[str, Any]]]:
        with connect(store.runtime) as connection:
            yield connection
            # 真正延迟 FK 在 COMMIT 时失败：不是模拟 receive 返回值或仅抛内存异常。
            connection.execute(
                "INSERT INTO feishu_probe.event_keys VALUES (%s,%s,%s,%s)",
                (store.policy.app_id, store.policy.tenant_key, str(uuid4()), uuid4()),
            )

    repository = ProbeRepository(commit_failure, store.scope, store.policy)
    gateway = ProbeGateway(repository)
    with pytest.raises(ProbeDatabaseFailure, match="^PROBE_DATABASE_FAILURE$"):
        gateway.dispatcher()._do_without_validation(json.dumps(store.card()).encode())
    assert count(store, "receipts") == 0
    with connect(store.runtime) as connection:
        row = connection.execute(
            "SELECT decision FROM feishu_probe.cards WHERE id=%s", (UUID(store.plan.probe_id),)
        ).fetchone()
        assert row == {"decision": None}


def test_actual_pool_budget_and_commit_before_sdk_return(store: Store) -> None:
    pool = runtime_pool(store.runtime)
    try:
        repository = ProbeRepository(pool.connection, store.scope, store.policy)
        gateway = ProbeGateway(repository)
        started = time.monotonic()
        response = gateway.dispatcher()._do_without_validation(json.dumps(store.card()).encode())
        elapsed = time.monotonic() - started
        assert elapsed < 3
        assert json.loads(lark.JSON.marshal(response))["toast"]["type"] == "success"
        assert count(store, "receipts") == 1  # 另一条 PG 连接回读已提交结果。
        with pool.connection() as connection:
            assert connection.execute("SHOW transaction_timeout").fetchone() == {
                "transaction_timeout": "1500ms"
            }
        print(f"P105 controlled callback elapsed_ms={elapsed * 1000:.2f}; real_pg/offline_sdk")
    finally:
        pool.close()


class Transport:
    def __init__(self, replies: list[ApiReply | Exception]):
        self.replies = replies
        self.calls: list[tuple[str, str | None]] = []
        self.fields: dict[str, str] = {}

    def create(self, app_token: str, table_id: str, token: str, fields: dict[str, str]) -> ApiReply:
        self.calls.append(("create", token))
        self.fields = fields
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def list(self, app_token: str, table_id: str, page_token: str | None) -> ApiReply:
        self.calls.append(("list", page_token))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def update(
        self, app_token: str, table_id: str, record_id: str, fields: dict[str, str]
    ) -> ApiReply:
        self.calls.append(("update", record_id))
        self.fields = fields
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def prepare_base(
    store: Store, transport: Transport
) -> tuple[BaseProbe, UUID, UUID, dict[str, str]]:
    probe_id = uuid4()
    fields = {
        "ProbeID": str(probe_id),
        "ProbeMarker": PROBE_MARKER,
        "SourceMode": "feishu_technical_probe",
        "ApprovalMode": "simulated_probe",
        "State": "created",
        "UpdatedAt": datetime.now(UTC).isoformat(),
    }
    probe = BaseProbe(lambda: connect(store.runtime), store.scope, transport)
    token = probe.prepare(probe_id, "probe-base", "probe-table", fields)
    assert token.version == 4
    return probe, probe_id, token, fields


def test_base_persistent_key_known_rejection_replay_create_read_update(store: Store) -> None:
    transport = Transport(
        [
            ApiReply(200, 1254291, {}),
            ApiReply(200, 0, {"record": {"record_id": "probe-record"}}),
            ApiReply(200, 0, {"record": {"record_id": "probe-record"}}),
        ]
    )
    probe, probe_id, token, fields = prepare_base(store, transport)
    assert probe.prepare(probe_id, "probe-base", "probe-table", fields) == token
    assert probe.create_once(probe_id) == "blocked"
    assert probe.create_once(probe_id, retry_known_rejection=True) == "succeeded"
    assert [key for method, key in transport.calls if method == "create"] == [
        str(token),
        str(token),
    ]
    assert probe.create_once(probe_id) == "succeeded"
    assert len(transport.calls) == 2
    assert (
        probe.update_once(probe_id, state="updated", updated_at=datetime.now(UTC).isoformat())
        == "succeeded"
    )
    with pytest.raises(ProbeConflict):
        probe.prepare(probe_id, "different-base", "probe-table", fields)


@pytest.mark.parametrize(
    "failure",
    [
        TimeoutError("DO_NOT_OUTPUT"),
        ApiReply(500, 0, {}),
        ApiReply(200, None, {}),
        ApiReply(200, 0, {}),
    ],
)
def test_base_unknown_never_recreates_even_if_reconcile_finds_no_row(
    store: Store, failure: ApiReply | Exception
) -> None:
    transport = Transport([failure, ApiReply(200, 0, {"items": [], "has_more": False})])
    probe, probe_id, _, _ = prepare_base(store, transport)
    assert probe.create_once(probe_id) == "unknown"
    assert probe.create_once(probe_id, retry_known_rejection=True) == "unknown"
    assert probe.reconcile(probe_id) == "unknown"
    assert probe.create_once(probe_id) == "unknown"
    assert [method for method, _ in transport.calls] == ["create", "list"]


@pytest.mark.parametrize("duplicates", [False, True])
def test_base_unknown_full_pagination_unique_or_duplicate_result(
    store: Store, duplicates: bool
) -> None:
    transport = Transport([TimeoutError()])
    probe, probe_id, _, fields = prepare_base(store, transport)
    assert probe.create_once(probe_id) == "unknown"
    items = [{"record_id": "probe-record", "fields": fields}]
    if duplicates:
        items.append({"record_id": "probe-record-2", "fields": fields})
    transport.replies.extend(
        [
            ApiReply(200, 0, {"items": [], "has_more": True, "page_token": "second"}),
            ApiReply(200, 0, {"items": items, "has_more": False}),
        ]
    )
    assert probe.reconcile(probe_id) == ("conflict" if duplicates else "succeeded")
    assert transport.calls[-1] == ("list", "second")


def test_base_update_unknown_does_not_confuse_existing_row_with_applied_update(
    store: Store,
) -> None:
    transport = Transport(
        [ApiReply(200, 0, {"record": {"record_id": "probe-record"}}), TimeoutError()]
    )
    probe, probe_id, _, fields = prepare_base(store, transport)
    assert probe.create_once(probe_id) == "succeeded"
    pending_time = datetime.now(UTC).isoformat()
    assert probe.update_once(probe_id, state="updated", updated_at=pending_time) == "unknown"
    transport.replies.append(
        ApiReply(
            200, 0, {"items": [{"record_id": "probe-record", "fields": fields}], "has_more": False}
        )
    )
    assert probe.reconcile(probe_id) == "unknown"
    assert probe.update_once(probe_id, state="another", updated_at="later") == "unknown"


def test_pool_lock_failure_within_budget_has_no_positive_ack(store: Store) -> None:
    pool = runtime_pool(store.runtime)
    payload = store.card()
    try:
        repository = ProbeRepository(pool.connection, store.scope, store.policy)
        with connect(store.owner) as locker:
            locker.execute(
                "SELECT id FROM feishu_probe.cards WHERE id=%s FOR UPDATE",
                (UUID(store.plan.probe_id),),
            )
            started = time.monotonic()
            with pytest.raises(ProbeDatabaseFailure):
                ProbeGateway(repository).dispatcher()._do_without_validation(
                    json.dumps(payload).encode()
                )
            assert time.monotonic() - started < 3
            assert count(store, "receipts") == 0
        assert repository.receive_card(payload).result.startswith("probe_recorded")
    finally:
        pool.close()


def test_base_client_token_conflict_never_changes_key_or_retries(store: Store) -> None:
    transport = Transport([ApiReply(400, 1255006, {})])
    probe, probe_id, token, fields = prepare_base(store, transport)
    assert probe.create_once(probe_id) == "conflict"
    assert probe.prepare(probe_id, "probe-base", "probe-table", fields) == token
    assert probe.create_once(probe_id, retry_known_rejection=True) == "conflict"
    assert transport.calls == [("create", str(token))]


def test_base_reconcile_cycle_and_config_target_mismatch_fail_closed(store: Store) -> None:
    transport = Transport(
        [
            TimeoutError(),
            ApiReply(200, 0, {"items": [], "has_more": True, "page_token": "same"}),
            ApiReply(200, 0, {"items": [], "has_more": True, "page_token": "same"}),
        ]
    )
    probe, probe_id, _, _ = prepare_base(store, transport)
    assert probe.create_once(probe_id) == "unknown"
    assert probe.reconcile(probe_id) == "unknown"
    changed = BaseProbe(
        lambda: connect(store.runtime),
        store.scope,
        transport,
        target=("different-base", "probe-table"),
    )
    with pytest.raises(ProbeConflict):
        changed.reconcile(probe_id)


def test_base_same_table_is_serial_across_independent_pg_connections(store: Store) -> None:
    class SerialTransport(Transport):
        def __init__(self) -> None:
            super().__init__([])
            self.guard = threading.Lock()
            self.active = 0
            self.maximum = 0

        def create(
            self, app_token: str, table_id: str, token: str, fields: dict[str, str]
        ) -> ApiReply:
            with self.guard:
                self.active += 1
                self.maximum = max(self.maximum, self.active)
            time.sleep(0.03)
            with self.guard:
                self.active -= 1
            return ApiReply(200, 0, {"record": {"record_id": "probe-" + fields["ProbeID"]}})

    transport = SerialTransport()
    first, first_id, _, _ = prepare_base(store, transport)
    second, second_id, _, _ = prepare_base(store, transport)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(first.create_once, first_id),
            executor.submit(second.create_once, second_id),
        ]
        assert [future.result() for future in futures] == ["succeeded", "succeeded"]
    assert transport.maximum == 1


@pytest.mark.parametrize("failure", [False, True])
def test_card_send_persistent_uuid_once_and_unknown_no_resend(
    store: Store, failure: bool, monkeypatch: Patch
) -> None:
    from types import SimpleNamespace

    import requests

    plan = replace(store.plan, probe_id=str(uuid4()), message_id="pending-send")
    store.repository.register_card(plan, outbound=True)
    calls: list[dict[str, Any]] = []

    def request(method: str, url: str, **kwargs: Any) -> SimpleNamespace:
        with connect(store.runtime) as connection:
            row = connection.execute(
                "SELECT send_uuid,send_status FROM feishu_probe.cards WHERE id=%s",
                (UUID(plan.probe_id),),
            ).fetchone()
            assert row is not None and row["send_status"] == "inflight"
            body = json.loads(kwargs["data"])
            assert body["uuid"] == str(row["send_uuid"])
        calls.append(body)
        if failure:
            raise TimeoutError("DO_NOT_OUTPUT")
        return SimpleNamespace(
            status_code=200,
            headers={},
            content=json.dumps(
                {"code": 0, "data": {"message_id": "probe-sent-card", "chat_id": plan.chat_id}}
            ).encode(),
        )

    monkeypatch.setattr(requests, "request", request)
    client = lark.Client.builder().enable_set_token(True).build()
    option = lark.RequestOption.builder().tenant_access_token("REDACTED").build()
    sender = CardSender(store.repository, client, option=option)
    expected = "unknown" if failure else "sent"
    assert sender.send_once(plan) == expected
    assert sender.send_once(plan) == expected
    assert len(calls) == 1
    if not failure:
        payload = store.card()
        payload["event"]["action"]["value"] = plan.callback_value("reject_assumptions")
        payload["event"]["context"]["open_message_id"] = "probe-sent-card"
        assert store.repository.receive_card(payload).result == "probe_recorded:reject_assumptions"
