"""自有真实PG formal inbox/T1/T3事务切片；approval_mode=simulated_feishu。"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

import pytest
from commerceops.adapters.feishu.business_gateway import BusinessCard
from commerceops.adapters.feishu.contracts import MessageProbe, PlatformIdentity
from commerceops.application.replenishment.contracts import DecisionInput, Parameters, WebFailure
from commerceops.infrastructure.approval_decisions import nonce_for
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_business import FeishuBusinessStore
from psycopg import sql

from tests.p3_support import P3Fixture, run_graphs
from tests.test_p3_pg import fixture as fixture

pytestmark = pytest.mark.integration


def service(f: P3Fixture, case: str = "baseline", **kwargs: Any) -> FeishuBusinessStore:
    with connect(f.inventory.owner) as db:
        db.execute(
            """INSERT INTO business.identities
            (id,organization_id,principal_id,provider,app_id,tenant_key,external_subject)
            VALUES (%s,%s,%s,'feishu',%s,%s,'p4-synthetic-user') ON CONFLICT DO NOTHING""",
            (
                uuid4(),
                f.actor.organization_id,
                f.actor.principal_id,
                f.inventory.data.app,
                f.inventory.data.tenant,
            ),
        )
    return FeishuBusinessStore(
        f.store,
        f.inventory.data.shop,
        Parameters(
            source_mode="mock", dataset_version="inventory-v1", fixture_case=case, L=3, R=7, S=2
        ),
        **kwargs,
    )


def message(f: P3Fixture, *, kind: str = "p2p") -> MessageProbe:
    return MessageProbe(
        "event-" + uuid4().hex,
        "message-" + uuid4().hex,
        "p4-synthetic-chat",
        kind,
        PlatformIdentity(f.inventory.data.app, f.inventory.data.tenant, "p4-synthetic-user"),
        "分析库存并生成补货建议",
    )


def counts(f: P3Fixture) -> dict[str, int]:
    with connect(f.config.database) as db:
        result: dict[str, int] = {}
        for table in (
            "business_tasks",
            "jobs",
            "inbox_events",
            "p4_inbox_receipts",
            "web_requests",
        ):
            row = db.execute(
                sql.SQL("SELECT count(*) AS n FROM business.{}").format(sql.Identifier(table))
            ).fetchone()
            assert row
            result[table] = row["n"]
        return result


def prepared(f: P3Fixture, s: FeishuBusinessStore, action: str = "approve") -> BusinessCard:
    receipt = s.message(message(f))
    task = UUID(receipt["task_id"])
    asyncio.run(run_graphs(f, task))
    with connect(f.config.database) as db:
        approval = db.execute(
            "SELECT * FROM business.approvals WHERE task_id=%s", (task,)
        ).fetchone()
        assert approval and approval["ready_at"]
        plan = db.execute(
            "SELECT content FROM business.replenishment_plans WHERE id=%s", (approval["plan_id"],)
        ).fetchone()
        outbox = db.execute(
            "SELECT id,status FROM business.outbox WHERE aggregate_id=%s", (approval["id"],)
        ).fetchone()
        assert plan and outbox and outbox["status"] == "pending"
        db.execute(
            """INSERT INTO business.p4_card_bindings
            (approval_id,outbox_id,chat_id,message_id,source_mode)
            VALUES(%s,%s,%s,%s,'offline_fake')""",
            (approval["id"], outbox["id"], "p4-synthetic-chat", "p4-synthetic-card"),
        )
    request = DecisionInput.model_validate(
        dict(
            schema_version="p3-web-v1",
            request_key=uuid4(),
            approval_id=approval["id"],
            plan_id=approval["plan_id"],
            plan_version=approval["plan_version"],
            plan_hash=approval["plan_hash"],
            action=action,
            acknowledged_assumption_keys=tuple(
                a["key"] for a in plan["content"]["required_assumptions"]
            )
            if action == "approve_with_assumptions"
            else (),
            nonce=nonce_for(f.config, approval),
        )
    )
    return BusinessCard(
        "event-card-" + uuid4().hex,
        message(f).identity,
        "p4-synthetic-chat",
        "p4-synthetic-card",
        request,
    )


@pytest.mark.parametrize("kind", ["p2p", "group"])
def test_formal_t1_ten_events_and_logical_message_replay_one_atomic_task_pair(
    fixture: P3Fixture, kind: str
) -> None:
    f = fixture
    s = service(f)
    before = counts(f)
    original = message(f, kind=kind)
    first = s.message(original)
    for _ in range(10):
        assert s.message(original)["task_id"] == first["task_id"]
        assert (
            s.message(replace(original, event_id="event-" + uuid4().hex))["task_id"]
            == first["task_id"]
        )
    after = counts(f)
    assert after["business_tasks"] - before["business_tasks"] == 2
    assert after["jobs"] - before["jobs"] == 2
    assert after["inbox_events"] - before["inbox_events"] == 1
    assert after["p4_inbox_receipts"] - before["p4_inbox_receipts"] == 1
    assert first["identity_mode"] == "feishu" and first["state"] == "queued"
    with connect(f.config.database) as db:
        row = db.execute(
            """SELECT channel,chat_id,actor_id FROM business.conversations
            WHERE id=(SELECT conversation_id FROM business.business_tasks WHERE id=%s)""",
            (UUID(first["task_id"]),),
        ).fetchone()
        assert row and row["channel"] == "feishu" and row["actor_id"] == f.actor.principal_id


def test_concurrent_same_message_new_event_is_one_task_pair(fixture: P3Fixture) -> None:
    f = fixture
    s = service(f)
    original = message(f)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(s.message, [original, replace(original, event_id="different-event")])
        )
    assert results[0]["task_id"] == results[1]["task_id"]
    assert sum(bool(r["duplicate"]) for r in results) == 1


def test_before_commit_fault_rolls_back_inbox_and_task_and_retry_uses_same_key(
    fixture: P3Fixture,
) -> None:
    f = fixture

    def hook(stage: str) -> None:
        if stage == "before_p4_commit":
            raise RuntimeError("controlled before commit")

    s = service(f, hook=hook)
    original = message(f)
    before = counts(f)
    with pytest.raises(RuntimeError, match="controlled"):
        s.message(original)
    assert counts(f) == before
    s.hook = None
    assert not s.message(original)["duplicate"]


def test_after_commit_ack_loss_replays_original_persistent_receipt(fixture: P3Fixture) -> None:
    f = fixture

    def hook(stage: str) -> None:
        if stage == "after_p4_commit":
            raise RuntimeError("controlled ACK loss")

    s = service(f, hook=hook)
    original = message(f)
    with pytest.raises(RuntimeError, match="ACK loss"):
        s.message(original)
    before = counts(f)
    s.hook = None
    assert s.message(original)["duplicate"]
    assert counts(f) == before


@pytest.mark.parametrize("change", ["identity", "tenant", "content", "revoked", "remapped"])
def test_formal_t1_current_identity_scope_and_event_conflict(
    fixture: P3Fixture, change: str
) -> None:
    f = fixture
    s = service(f)
    original = message(f)
    s.message(original)
    altered = original
    if change in ("identity", "tenant"):
        altered = replace(
            original,
            identity=replace(
                original.identity,
                **(
                    {"open_id": "forged"}
                    if change == "identity"
                    else {"tenant_key": "cross-tenant"}
                ),
            ),
        )
    elif change == "content":
        altered = replace(original, text="分析最近七天库存并生成补货建议")
    elif change == "remapped":
        principal = uuid4()
        with connect(f.inventory.owner) as db:
            db.execute(
                """INSERT INTO business.principals(id,organization_id,display_name,roles)
                VALUES(%s,%s,'remapped synthetic operator',ARRAY['operator'])""",
                (principal, f.actor.organization_id),
            )
            db.execute(
                "INSERT INTO business.principal_shop_scopes VALUES(%s,%s,%s,true)",
                (f.actor.organization_id, f.inventory.data.shop, principal),
            )
            db.execute(
                "INSERT INTO business.principal_role_shop_grants VALUES(%s,%s,%s,'operator',true)",
                (f.actor.organization_id, f.inventory.data.shop, principal),
            )
            db.execute(
                "UPDATE business.identities SET principal_id=%s WHERE provider='feishu'",
                (principal,),
            )
    else:
        with connect(f.inventory.owner) as db:
            db.execute(
                "UPDATE business.principals SET enabled=false,auth_version=auth_version+1 "
                "WHERE id=%s",
                (f.actor.principal_id,),
            )
    before = counts(f)
    with pytest.raises(WebFailure):
        s.message(altered)
    assert counts(f) == before


@pytest.mark.parametrize(
    "case,action",
    [
        ("baseline", "approve"),
        ("unknown_inbound", "approve_with_assumptions"),
        ("unknown_inbound", "reject_assumptions"),
    ],
)
def test_formal_t3_same_p3_decision_and_exact_ten_duplicate_receipts(
    fixture: P3Fixture, case: str, action: str
) -> None:
    f = fixture
    s = service(f, case)
    card = prepared(f, s, action)
    receipt = s.card(card)
    assert receipt["decision_source"] == "feishu"
    for _ in range(10):
        assert s.card(card)["decision_id"] == receipt["decision_id"]
    with connect(f.config.database) as db:
        for table in ("approval_resumes",):
            row = db.execute(
                sql.SQL("SELECT count(*) AS n FROM business.{} WHERE decision_id=%s").format(
                    sql.Identifier(table)
                ),
                (UUID(receipt["decision_id"]),),
            ).fetchone()
            assert row and row["n"] == 1
        jobs = db.execute(
            "SELECT count(*) AS n FROM business.jobs WHERE task_id=%s AND kind='resume'",
            (UUID(receipt["task_id"]),),
        ).fetchone()
        assert jobs and jobs["n"] == 1
        if action == "reject_assumptions":
            assert receipt["reason_code"] == "INBOUND_ASSUMPTION_DECLINED"


@pytest.mark.parametrize("change", ["message", "chat", "nonce", "hash", "version", "ordinary"])
def test_callback_binding_and_unknown_assumptions_are_server_authoritative(
    fixture: P3Fixture, change: str
) -> None:
    f = fixture
    s = service(f, "unknown_inbound")
    card = prepared(f, s, "approve_with_assumptions")
    if change in ("message", "chat"):
        card = (
            replace(card, message_id="forwarded-card")
            if change == "message"
            else replace(card, chat_id="another-chat")
        )
    else:
        updates: dict[str, Any] = (
            {"nonce": "wrong" * 8 + "xxx"}
            if change == "nonce"
            else {"plan_hash": "a" * 64}
            if change == "hash"
            else {"plan_version": 2}
            if change == "version"
            else {"action": "approve", "acknowledged_assumption_keys": ()}
        )
        card = replace(card, request=card.request.model_copy(update=updates))
    before = counts(f)
    with pytest.raises(WebFailure):
        s.card(card)
    assert counts(f) == before
    with connect(f.config.database) as db:
        row = db.execute(
            "SELECT status,decision_id FROM business.approvals WHERE id=%s",
            (card.request.approval_id,),
        ).fetchone()
        assert row and row["status"] == "pending" and row["decision_id"] is None


def test_feishu_created_task_and_original_decision_are_readable_by_same_principal_web_session(
    fixture: P3Fixture,
) -> None:
    f = fixture
    s = service(f)
    card = prepared(f, s)
    detail = f.client.get(f"/api/v1/tasks/{card.request.approval_id}")
    assert detail.status_code == 404
    with connect(f.config.database) as db:
        row = db.execute(
            "SELECT task_id FROM business.approvals WHERE id=%s", (card.request.approval_id,)
        ).fetchone()
        assert row
        task = row["task_id"]
    detail = f.client.get(f"/api/v1/tasks/{task}")
    assert detail.status_code == 200 and detail.json()["task"]["task_id"] == str(task)
    assert detail.json()["actions"]["can_decide"]
    identity = f.client.get("/api/v1/auth/session").json()
    assert identity["principal"]["principal_id"] == str(f.actor.principal_id)
    receipt = s.card(card)
    view = f.client.get(f"/api/v1/approvals/{card.request.approval_id}")
    assert view.status_code == 200
    assert view.json()["decision"]["decision_source"] == "feishu"
    assert view.json()["decision"]["decision_id"] == receipt["decision_id"]
    payload = card.request.model_dump(mode="json") | {"request_key": str(uuid4())}
    duplicate = f.client.post(
        f"/api/v1/approvals/{card.request.approval_id}/decision", json=payload, headers=f.headers()
    )
    assert duplicate.status_code == 200 and duplicate.json()["duplicate"]
    assert duplicate.json()["decision_id"] == receipt["decision_id"]
    with connect(f.config.database) as db:
        resume = db.execute(
            "SELECT count(*) AS n FROM business.approval_resumes WHERE task_id=%s", (task,)
        ).fetchone()
        assert resume and resume["n"] == 1


def test_principal_revocation_denies_both_feishu_and_original_web_session(
    fixture: P3Fixture,
) -> None:
    f = fixture
    s = service(f)
    card = prepared(f, s)
    headers = f.headers()
    with connect(f.inventory.owner) as db:
        db.execute(
            "UPDATE business.principals SET enabled=false,auth_version=auth_version+1 WHERE id=%s",
            (f.actor.principal_id,),
        )
    before = counts(f)
    with pytest.raises(WebFailure):
        s.card(card)
    result = f.client.get(f"/api/v1/approvals/{card.request.approval_id}")
    assert result.status_code == 401
    result = f.client.post(
        f"/api/v1/approvals/{card.request.approval_id}/decision",
        json=card.request.model_dump(mode="json"),
        headers=headers,
    )
    assert result.status_code == 401 and counts(f) == before
