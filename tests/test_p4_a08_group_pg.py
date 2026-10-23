"""正式T1/P2/T2/T3/T4 group20矩阵，simulated_feishu/owned PG，无SDK。"""

from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

import pytest
from commerceops.adapters.feishu.business_gateway import BusinessCard
from commerceops.application.replenishment.contracts import DecisionInput, WebFailure
from commerceops.domain.commerce_values import sku_key
from commerceops.infrastructure.approval_decisions import nonce_for
from commerceops.infrastructure.database import connect

from tests.p3_support import P3Fixture, P3Process
from tests.test_p3_approval_pg import wait_state
from tests.test_p3_pg import fixture as fixture
from tests.test_p4_gateway_pg import counts, message, service

pytestmark = pytest.mark.integration


def approver(f: P3Fixture) -> UUID:
    principal = uuid4()
    with connect(f.inventory.owner) as db:
        db.execute(
            """INSERT INTO business.principals(id,organization_id,display_name,roles)
        VALUES(%s,%s,'synthetic independent B',ARRAY['approver'])""",
            (principal, f.actor.organization_id),
        )
        db.execute(
            "INSERT INTO business.principal_shop_scopes VALUES(%s,%s,%s,true)",
            (f.actor.organization_id, f.inventory.data.shop, principal),
        )
        db.execute(
            "INSERT INTO business.principal_role_shop_grants VALUES(%s,%s,%s,'approver',true)",
            (f.actor.organization_id, f.inventory.data.shop, principal),
        )
        db.execute(
            """INSERT INTO business.identities
        (id,organization_id,principal_id,provider,app_id,tenant_key,external_subject)
        VALUES(%s,%s,%s,'feishu',%s,%s,'p4-synthetic-B')""",
            (
                uuid4(),
                f.actor.organization_id,
                principal,
                f.inventory.data.app,
                f.inventory.data.tenant,
            ),
        )
    return principal


def group_card(f: P3Fixture) -> tuple[Any, UUID, BusinessCard, UUID, P3Process]:
    independent = approver(f)
    gateway = service(f)
    incoming = message(f, kind="group")
    task = UUID(gateway.message(incoming)["task_id"])
    child = P3Process(f, "worker", {"task_id": str(task), "p4_demo": True}, "never")
    try:
        return ready_group_card(f, gateway, incoming, task, independent, child)
    except BaseException:
        if child.process.poll() is None:
            child.stop_clean()
        raise


def ready_group_card(
    f: P3Fixture, gateway: Any, incoming: Any, task: UUID, independent: UUID, child: P3Process
) -> tuple[Any, UUID, BusinessCard, UUID, P3Process]:
    child.until("after_ready")
    with connect(f.config.database) as db:
        approval = db.execute(
            "SELECT * FROM business.approvals WHERE task_id=%s", (task,)
        ).fetchone()
        assert (
            approval and approval["ready_at"] and independent in approval["eligible_principal_ids"]
        )
        plan = db.execute(
            "SELECT content FROM business.replenishment_plans WHERE id=%s", (approval["plan_id"],)
        ).fetchone()
        assert plan
        content = plan["content"]
        assert content["item_count"] == 20 and content["total_units"] == 2000
        assert all(i["quantity"] == 100 for i in content["items"])
        assert len(content["required_assumptions"]) == 1
        unknown = next(i for i in content["items"] if i["fact"]["inbound_units"] is None)
        assert unknown["sku_key"] == sku_key("demo", "b02-19", None)
        outbox = db.execute(
            "SELECT id FROM business.outbox WHERE aggregate_id=%s", (approval["id"],)
        ).fetchone()
        assert outbox
        db.execute(
            """INSERT INTO business.p4_card_bindings
        (approval_id,outbox_id,chat_id,message_id,source_mode)
        VALUES(%s,%s,%s,'synthetic-group-card','offline_fake')""",
            (approval["id"], outbox["id"], incoming.chat_id),
        )
    request = DecisionInput.model_validate(
        dict(
            schema_version="p3-web-v1",
            request_key=uuid4(),
            approval_id=approval["id"],
            plan_id=approval["plan_id"],
            plan_version=approval["plan_version"],
            plan_hash=approval["plan_hash"],
            action="approve_with_assumptions",
            nonce=nonce_for(f.config, approval),
            acknowledged_assumption_keys=tuple(a["key"] for a in content["required_assumptions"]),
        )
    )
    card = BusinessCard(
        "group-event-" + uuid4().hex,
        replace(incoming.identity, open_id="p4-synthetic-B"),
        incoming.chat_id,
        "synthetic-group-card",
        request,
    )
    return gateway, task, card, independent, child


@pytest.mark.parametrize(
    "action,target,items",
    [
        ("approve_with_assumptions", "completed", 20),
        ("reject_assumptions", "rejected", 0),
    ],
)
def test_independent_complete_joint_or_reject_ten_replays_and_conflicting_actor_action(
    fixture: P3Fixture,
    action: str,
    target: str,
    items: int,
) -> None:
    f = fixture
    gateway, task, card, independent, child = group_card(f)
    try:
        check_decision(f, gateway, task, card, independent, action, target, items)
    finally:
        if child.process.poll() is None:
            child.stop_clean()


def check_decision(
    f: P3Fixture,
    gateway: Any,
    task: UUID,
    card: BusinessCard,
    independent: UUID,
    action: str,
    target: str,
    items: int,
) -> None:
    if action == "approve_with_assumptions":
        acks = card.request.acknowledged_assumption_keys
    else:
        acks = ()
    request = card.request.model_copy(
        update={
            "action": action,
            "acknowledged_assumption_keys": acks,
        }
    )
    card = replace(card, request=request)
    first = gateway.card(card)
    for _ in range(10):
        repeated = replace(
            card,
            event_id="repeat-" + uuid4().hex,
            request=request.model_copy(update={"request_key": uuid4()}),
        )
        assert gateway.card(repeated)["decision_id"] == first["decision_id"]
    for changed in (
        replace(
            card,
            event_id="conflict-action",
            request=request.model_copy(
                update={
                    "request_key": uuid4(),
                    "action": "reject_assumptions"
                    if action == "approve_with_assumptions"
                    else "approve_with_assumptions",
                    "acknowledged_assumption_keys": ()
                    if action == "approve_with_assumptions"
                    else card.request.acknowledged_assumption_keys,
                }
            ),
        ),
        replace(
            card,
            event_id="conflict-actor",
            identity=replace(card.identity, open_id="p4-synthetic-user"),
            request=request.model_copy(update={"request_key": uuid4()}),
        ),
    ):
        with pytest.raises(WebFailure, match="DECISION_CONFLICT"):
            gateway.card(changed)
    wait_state(f, task, target)
    with connect(f.config.database) as db:
        assert db.execute(
            "SELECT state FROM business.business_tasks WHERE id=%s", (task,)
        ).fetchone() == {"state": target}
        assert db.execute(
            "SELECT count(*) AS n FROM business.replenishment_items WHERE task_id=%s", (task,)
        ).fetchone() == {"n": items}
        assert db.execute(
            "SELECT count(*) AS n FROM business.executions WHERE task_id=%s", (task,)
        ).fetchone() == {"n": 1 if items else 0}
        assert db.execute(
            "SELECT count(*) AS n FROM business.approval_resumes WHERE task_id=%s", (task,)
        ).fetchone() == {"n": 1}
        assert db.execute(
            "SELECT decided_by FROM business.approvals WHERE task_id=%s", (task,)
        ).fetchone() == {"decided_by": independent}
        assert db.execute("SELECT count(*) AS n FROM business.p4_sdk_calls").fetchone() == {"n": 0}


@pytest.mark.parametrize(
    "change",
    [
        "ordinary",
        "missing_set",
        "extra_set",
        "hash",
        "version",
        "nonce",
        "chat",
        "message",
        "permission",
    ],
)
def test_group20_incomplete_joint_stale_context_and_current_role_reject_atomically(
    fixture: P3Fixture,
    change: str,
) -> None:
    f = fixture
    gateway, task, card, independent, child = group_card(f)
    try:
        check_invalid(f, gateway, task, card, independent, change)
    finally:
        if child.process.poll() is None:
            child.stop_clean()


def check_invalid(
    f: P3Fixture, gateway: Any, task: UUID, card: BusinessCard, independent: UUID, change: str
) -> None:
    if change in ("chat", "message"):
        card = (
            replace(card, chat_id="forwarded")
            if change == "chat"
            else replace(card, message_id="forwarded")
        )
    elif change == "permission":
        with connect(f.inventory.owner) as db:
            db.execute(
                "UPDATE business.principal_role_shop_grants SET enabled=false "
                "WHERE principal_id=%s",
                (independent,),
            )
    else:
        mutations: dict[str, dict[str, Any]] = {
            "ordinary": {"action": "approve", "acknowledged_assumption_keys": ()},
            "missing_set": {"acknowledged_assumption_keys": ()},
            "extra_set": {
                "acknowledged_assumption_keys": (
                    *card.request.acknowledged_assumption_keys,
                    "forged",
                )
            },
            "hash": {"plan_hash": "0" * 64},
            "version": {"plan_version": 2},
            "nonce": {"nonce": "x" * 43},
        }
        update = mutations[change]
        card = replace(card, request=card.request.model_copy(update=update))
    before = counts(f)
    with pytest.raises(WebFailure):
        gateway.card(card)
    assert counts(f) == before
    with connect(f.config.database) as db:
        assert db.execute(
            "SELECT status,decision_id FROM business.approvals WHERE task_id=%s", (task,)
        ).fetchone() == {"status": "pending", "decision_id": None}
        assert db.execute("SELECT count(*) AS n FROM business.executions").fetchone() == {"n": 0}
