"""所有数据均为合成，禁止读取真实配置或调用外部资源。"""

import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from commerceops.adapters.feishu.base import PROBE_MARKER, BaseProbe
from commerceops.adapters.feishu.contracts import ProbePlan
from commerceops.adapters.feishu.repository import ProbeReceipt
from commerceops.infrastructure.repository import TaskScope
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1  # type: ignore[import-untyped]
from lark_oapi.event.callback.model.p2_card_action_trigger import (  # type: ignore[import-untyped]
    P2CardActionTrigger,
)

from scripts.feishu_probe_harness.base_live_core import ScopedRecordSDK

MEMBERS = {a: "ou_synthetic_" + a for a in "ABC"}
CANARY = "SYNTHETIC_PRIVATE_CANARY"
FAKE_UUID = UUID("11111111-1111-4111-8111-111111111111")
ROLES = {"A": ["operator", "approver"], "B": ["approver"], "C": []}


class Store:
    def __init__(self: Any) -> None:
        self.row = None
        self.locked = 0
        self.committed_inflight = False
        self.queries: list[Any] = []

    def connection(self: Any) -> Any:
        return Conn(self)


class Conn:
    def __init__(self: Any, store: Any) -> None:
        self.store = store

    def __enter__(self: Any) -> Any:
        return self

    def __exit__(self: Any, kind: Any, *a: Any) -> Any:
        if kind is None:
            self.commit()

    def commit(self: Any) -> Any:
        if self.store.row and self.store.row["status"] == "inflight":
            self.store.committed_inflight = True

    def execute(self: Any, query: Any, params: Any = None) -> Any:
        self.store.queries.append(query)
        assert not any(
            v in query.upper()
            for v in ("CREATE TABLE", "ALTER TABLE", "DELETE ", "COMMERCEOPS_OWNER")
        )
        s = self.store
        if query.lstrip().startswith("INSERT"):
            pid, org, shop, app, table, token, digest, fields = params
            if s.row is None:
                s.row = dict(
                    id=pid,
                    organization_id=org,
                    shop_id=shop,
                    app_token=app,
                    table_id=table,
                    client_token=token,
                    request_sha256=digest,
                    fields=fields.obj,
                    status="ready",
                    pending_kind="create",
                    pending_fields=None,
                    pending_sha256=None,
                    record_id=None,
                    last_code=None,
                )
        elif "pg_advisory_unlock" in query:
            s.locked -= 1
        elif "pg_advisory_lock" in query:
            s.locked += 1
        elif query.lstrip().startswith("SELECT *"):
            assert params == (s.row["id"], s.row["organization_id"], s.row["shop_id"])
            return SimpleNamespace(fetchone=lambda: s.row)
        elif "pending_kind='update'" in query:
            pending, digest, *scope = params
            s.row.update(
                status="inflight",
                pending_kind="update",
                pending_fields=pending.obj,
                pending_sha256=digest,
            )
            s.committed_inflight = False
        elif query.lstrip().startswith("UPDATE"):
            state, record, code, *scope = params
            s.row.update(status=state, record_id=record, last_code=code)
            if state == "inflight":
                s.committed_inflight = False
        else:
            raise AssertionError("UNEXPECTED_SQL")
        return SimpleNamespace(fetchone=lambda: None)


class SDK:
    def __init__(self: Any, store: Any, failure: Any = None) -> None:
        self.store = store
        self.failure = failure
        self.calls: list[Any] = []
        self.remote = None
        self.bitable = SimpleNamespace(v1=SimpleNamespace(app_table_record=self))

    def reply(self: Any, data: Any, code: Any = 0, status: Any = 200) -> Any:
        return SimpleNamespace(
            raw=SimpleNamespace(status_code=status, content=json.dumps(dict(data=data)).encode()),
            code=code,
        )

    def create(self: Any, request: Any, option: Any = None) -> Any:
        self.calls.append(("create", request))
        assert self.store.locked == 1 and self.store.committed_inflight
        assert request.client_token == str(self.store.row["client_token"])
        self.remote = copy.deepcopy(request.body.fields)
        if self.failure == "create_unknown":
            raise TimeoutError("PRIVATE_CANARY")
        if self.failure == "known_rejection":
            self.remote = None
            return self.reply({}, 1254291)
        if self.failure == "HTTP_500":
            self.remote = None
            return self.reply({}, 0, 500)
        return self.reply(dict(record=dict(record_id="rec_synthetic", fields=self.remote)))

    def list(self: Any, request: Any, option: Any = None) -> Any:
        self.calls.append(("list", request))
        assert self.store.locked == 1
        expected = 'AND(CurrentValue.[ProbeID]="' + str(self.store.row["id"]) + '")'
        assert request.filter == expected
        assert set(json.loads(request.field_names)) == set(self.store.row["fields"])
        items = (
            []
            if self.remote is None
            else [dict(record_id="rec_synthetic", fields=copy.deepcopy(self.remote))]
        )
        if self.failure == "foreign_row" and items:
            items[0]["fields"]["ProbeID"] = str(uuid4())
        if self.failure == "duplicate_row" and items:
            items.append(dict(record_id="rec_synthetic_other", fields=copy.deepcopy(self.remote)))
        if self.failure == "missing_row":
            items = []
        if self.failure == "content_mismatch" and items:
            items[0]["fields"]["State"] = "probe_complete"
        if self.failure == "infinite_pagination":
            return self.reply(dict(items=items, has_more=True, page_token="synthetic_next"))  # noqa: S106 -- Synthetic pagination.
        return self.reply(dict(items=items, has_more=False))

    def update(self: Any, request: Any, option: Any = None) -> Any:
        self.calls.append(("update", request))
        assert self.store.locked == 1 and self.store.committed_inflight
        assert request.record_id == "rec_synthetic"
        self.remote = copy.deepcopy(request.body.fields)
        if self.failure == "update_unknown":
            raise TimeoutError("PRIVATE_CANARY")
        return self.reply(
            dict(
                record=dict(
                    record_id="wrong_synthetic"
                    if self.failure == "wrong_update_record"
                    else "rec_synthetic",
                    fields=self.remote,
                )
            )
        )


def fixture(failure: Any = None) -> Any:
    store = Store()
    sdk = SDK(store, failure)
    pid = uuid4()
    target = ("app_synthetic", "table_synthetic")
    scope = TaskScope(uuid4(), uuid4())
    transport = ScopedRecordSDK(sdk, pid, target, 9999999999)
    probe = BaseProbe(store.connection, scope, transport, target=target)
    fields = dict(
        ProbeID=str(pid),
        ProbeMarker=PROBE_MARKER,
        SourceMode="feishu_technical_probe",
        ApprovalMode="simulated_probe",
        State="created",
        UpdatedAt=datetime(2026, 10, 9, tzinfo=UTC).isoformat(),
    )
    updated = {
        **fields,
        "State": "updated",
        "UpdatedAt": datetime(2026, 10, 9, 0, 0, 1, tzinfo=UTC).isoformat(),
    }
    return (store, sdk, pid, probe, transport, fields, updated)


def dto(kind: Any = "message", alias: Any = "A") -> Any:
    header = {
        "event_type": "im.message.receive_v1" if kind == "message" else "card.action.trigger",
        "app_id": "cli_synthetic",
        "tenant_key": "tenant_synthetic",
        "event_id": CANARY,
    }
    if kind == "message":
        body = {
            "sender": {
                "sender_type": "user",
                "tenant_key": "tenant_synthetic",
                "sender_id": {"open_id": MEMBERS[alias]},
            },
            "message": {
                "chat_type": "p2p",
                "chat_id": "oc_synthetic",
                "message_id": "om_synthetic",
                "message_type": "text",
                "content": json.dumps({"text": CANARY}),
            },
        }
        return P2ImMessageReceiveV1({"schema": "2.0", "header": header, "event": body})
    return P2CardActionTrigger(
        {
            "schema": "2.0",
            "header": header,
            "event": {
                "operator": {"tenant_key": "tenant_synthetic", "open_id": MEMBERS[alias]},
                "context": {"open_chat_id": "oc_synthetic", "open_message_id": "om_synthetic"},
                "action": {"tag": "button", "value": {"probe_id": str(FAKE_UUID), "nonce": CANARY}},
                "token": CANARY,
            },
        }
    )


class Delegate:
    def __init__(self: Any, result: Any = None, error: Any = None) -> None:
        self.result = result or ProbeReceipt(FAKE_UUID, "message_received")
        self.error = error
        self.calls: list[Any] = []

    def receive_message(self: Any, payload: Any) -> Any:
        self.calls.append(payload)
        if self.error:
            raise self.error
        return self.result

    receive_card = receive_message


def plan() -> Any:
    identifiers = tuple(str(uuid4()) for _ in range(4))
    return ProbePlan(
        identifiers[0],
        identifiers[1],
        identifiers[2],
        identifiers[3],
        plan_version=1,
        plan_hash=hashlib.sha256(b"synthetic simulated M2").hexdigest(),
        required_assumption_keys=("inbound_unknown_zero:synthetic_M2",),
        nonce="n" * 40,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        chat_id="oc_synthetic_group",
        message_id="pending_synthetic",
    )


def identity_body() -> Any:
    org, shop = (str(uuid4()), str(uuid4()))
    return {
        "schema_version": 1,
        "human_verified": True,
        "source_result_sha256": "a" * 64,
        "confirmation_sha256": "b" * 64,
        "organization": {
            "id": org,
            "name": "Synthetic P105",
            "feishu_app_id": "cli_synthetic",
            "feishu_tenant_key": "synthetic-tenant",
        },
        "shop": {
            "id": shop,
            "organization_id": org,
            "adapter_kind": "mock",
            "external_shop_key": "-".join(("p105", "feishu", "identity", "sandbox")),
            "timezone": "Asia/Shanghai",
            "currency": "CNY",
            "config_ref": "p105-feishu-probe-local",
            "environment": "mock",
        },
        "members": [
            {
                "alias": a,
                "principal_id": str(uuid4()),
                "identity_id": str(uuid4()),
                "display_name": "synthetic-" + a,
                "open_id": "ou_synthetic_" + a,
                "enabled": True,
                "roles": roles.copy(),
                "auth_version": 1,
            }
            for a, roles in ROLES.items()
        ],
        "audit": {"id": str(uuid4()), "trace_id": str(uuid4())},
    }
