"""正式Gateway短事务：可信身份/inbox/T1或T3同commit；没有外部调用。"""

from collections.abc import Callable
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from psycopg.types.json import Jsonb

from commerceops.adapters.feishu.business_gateway import BusinessCard
from commerceops.adapters.feishu.contracts import MessageProbe, PlatformIdentity
from commerceops.application.replenishment.contracts import (
    CreateNewCycle,
    FeishuActor,
    Parameters,
    WebFailure,
)
from commerceops.domain.commerce_values import facts_hash
from commerceops.infrastructure.approval_decisions import DecisionStore
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.replenishment_repository import ReplenishmentStore
from commerceops.infrastructure.web_sessions import DB, actor_guard, role_scope


class FeishuBusinessStore:
    def __init__(
        self,
        store: ReplenishmentStore,
        shop_id: UUID,
        parameters: Parameters,
        *,
        hook: Callable[[str], None] | None = None,
    ):
        self.store, self.shop, self.parameters, self.hook = store, shop_id, parameters, hook
        self.decisions = DecisionStore(store.config)

    @staticmethod
    def actor(db: DB, identity: PlatformIdentity, chat: str) -> FeishuActor:
        # 不持identity/principal锁进入T3 task→plan→approval→principal锁序。
        row = db.execute(
            """SELECT i.*,p.auth_version FROM business.identities i
            JOIN business.principals p ON p.id=i.principal_id
            AND p.organization_id=i.organization_id
            WHERE i.provider='feishu' AND i.app_id=%s AND i.tenant_key=%s
            AND i.external_subject=%s AND p.enabled""",
            (identity.app_id, identity.tenant_key, identity.open_id),
        ).fetchone()
        if not row:
            raise WebFailure("IDENTITY_DENIED", 403)
        return FeishuActor(
            row["principal_id"],
            row["id"],
            row["organization_id"],
            row["auth_version"],
            identity.app_id,
            identity.tenant_key,
            identity.open_id,
            chat,
        )

    def _previous(
        self, db: DB, actor: FeishuActor, event: str, semantic: str, message: str | None
    ) -> dict[str, Any] | None:
        # 两层键统一排序锁；同message新event仍回同一原inbox/task。
        keys = [f"p4:event:{actor.app_id}:{actor.tenant_key}:{event}"]
        if message:
            keys.append(f"p4:message:{actor.app_id}:{actor.tenant_key}:{message}")
        for key in sorted(keys):
            db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (key,))
        rows = db.execute(
            """SELECT e.*,r.identity_id,r.result FROM business.inbox_events e
            JOIN business.p4_inbox_receipts r ON r.inbox_id=e.id
            WHERE e.source='feishu_business' AND e.app_id=%s AND e.tenant_key=%s
            AND (e.event_id=%s OR (%s::text IS NOT NULL AND e.message_id=%s))""",
            (actor.app_id, actor.tenant_key, event, message, message),
        ).fetchall()
        if not rows:
            return None
        if (
            len(rows) != 1
            or rows[0]["identity_id"] != actor.identity_id
            or rows[0]["sanitized_payload"].get("principal_id") != str(actor.principal_id)
            or (rows[0]["payload_hash"] != semantic or rows[0]["shop_id"] != self.shop)
        ):
            raise WebFailure("EVENT_CONFLICT")
        actor_guard(db, actor)
        if not role_scope(db, actor, self.shop, "operator" if message else "approver"):
            raise WebFailure("ACCESS_DENIED", 403)
        return {**rows[0]["result"], "duplicate": True}

    def _record(
        self,
        db: DB,
        actor: FeishuActor,
        event: str,
        message: str | None,
        semantic: str,
        receipt: dict[str, Any],
        sanitized: dict[str, Any],
    ) -> None:
        inbox = uuid4()
        db.execute(
            """INSERT INTO business.inbox_events
            (id,organization_id,shop_id,source,app_id,tenant_key,event_id,message_id,
            payload_hash,sanitized_payload,status,task_id)
            VALUES (%s,%s,%s,'feishu_business',%s,%s,%s,%s,%s,%s,'processed',%s)""",
            (
                inbox,
                actor.organization_id,
                self.shop,
                actor.app_id,
                actor.tenant_key,
                event,
                message,
                semantic,
                Jsonb({**sanitized, "principal_id": str(actor.principal_id)}),
                UUID(receipt["task_id"]) if receipt.get("task_id") else None,
            ),
        )
        db.execute(
            "INSERT INTO business.p4_inbox_receipts(inbox_id,identity_id,result) VALUES(%s,%s,%s)",
            (inbox, actor.identity_id, Jsonb(receipt)),
        )
        if self.hook:
            self.hook("before_p4_commit")

    def message(self, message: MessageProbe) -> dict[str, Any]:
        # 首切片确定性文法，模糊请求不生成任务/模型请求；正式路由另增量接线。
        semantic = facts_hash(
            {"open_id": message.identity.open_id, "chat": message.chat_id, "text": message.text}
        )
        with connect(self.store.settings) as db:
            actor = self.actor(db, message.identity, message.chat_id)
            old = self._previous(db, actor, message.event_id, semantic, message.message_id)
            if old:
                return old
            if not role_scope(db, actor, self.shop, "operator"):
                raise WebFailure("ACCESS_DENIED", 403)
            if message.text not in ("分析最近七天库存并生成补货建议", "分析库存并生成补货建议"):
                reply, provider_uuid = uuid4(), uuid4()
                receipt = {
                    "schema_version": "p4-v1",
                    "identity_mode": "feishu",
                    "state": "needs_clarification",
                    "reason_code": "REQUEST_NEEDS_CLARIFICATION",
                    "reply_id": str(reply),
                    "duplicate": False,
                }
                self._record(
                    db,
                    actor,
                    message.event_id,
                    message.message_id,
                    semantic,
                    receipt,
                    {
                        "schema_version": "p4-v1",
                        "source_mode": "mock",
                        "model_mode": "not_used",
                        "event_type": "im.message.receive_v1",
                        "text_sha256": facts_hash(message.text),
                    },
                )
                inbox = db.execute(
                    """SELECT id FROM business.inbox_events WHERE source='feishu_business'
                    AND app_id=%s AND tenant_key=%s AND event_id=%s""",
                    (actor.app_id, actor.tenant_key, message.event_id),
                ).fetchone()
                if not inbox:
                    raise WebFailure("SERVICE_UNAVAILABLE", 503)
                db.execute(
                    """INSERT INTO business.p4_clarification_replies
                    (id,inbox_id,organization_id,shop_id,principal_id,identity_id,chat_id,chat_type,
                    reason_code,template_version,provider_uuid)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'REQUEST_NEEDS_CLARIFICATION',
                    'p4-clarification-v1',%s)""",
                    (
                        reply,
                        inbox["id"],
                        actor.organization_id,
                        self.shop,
                        actor.principal_id,
                        actor.identity_id,
                        message.chat_id,
                        message.chat_type,
                        provider_uuid,
                    ),
                )
            else:
                receipt = self._create_message_task(db, actor, message)
        if self.hook:
            self.hook("after_p4_commit")
        return receipt

    def _create_message_task(
        self,
        db: DB,
        actor: FeishuActor,
        message: MessageProbe,
    ) -> dict[str, Any]:
        semantic = facts_hash(
            {"open_id": message.identity.open_id, "chat": message.chat_id, "text": message.text}
        )
        request = CreateNewCycle(
            schema_version="p3-web-v1",
            mode="new_cycle",
            shop_id=self.shop,
            request_key=uuid5(
                NAMESPACE_URL,
                f"p4-message:{actor.app_id}:{actor.tenant_key}:{message.message_id}",
            ),
            parameters=self.parameters,
        )
        receipt = self.store.create_in_transaction(db, actor, request)
        receipt = {**receipt, "identity_mode": "feishu", "schema_version": "p4-v1"}
        self._record(
            db,
            actor,
            message.event_id,
            message.message_id,
            semantic,
            receipt,
            {
                "schema_version": "p4-v1",
                "source_mode": "mock",
                "model_mode": "not_used",
                "event_type": "im.message.receive_v1",
                "chat_type": message.chat_type,
                "text_sha256": facts_hash(message.text),
            },
        )
        return receipt

    def card(self, card: BusinessCard) -> dict[str, Any]:
        request = card.request
        semantic = facts_hash(
            {
                "identity": card.identity.open_id,
                "chat": card.chat_id,
                "message": card.message_id,
                "request": request.model_dump(mode="json", exclude={"request_key"}),
            }
        )
        with connect(self.store.settings) as db:
            actor = self.actor(db, card.identity, card.chat_id)
            old = self._previous(db, actor, card.event_id, semantic, None)
            if old:
                return old

            def binding_check(connection: DB, approval: dict[str, Any]) -> None:
                binding = connection.execute(
                    """SELECT b.* FROM business.p4_card_bindings b JOIN business.outbox o
                    ON o.id=b.outbox_id WHERE b.approval_id=%s AND o.aggregate_id=%s
                    AND o.task_id=%s AND o.organization_id=%s AND o.shop_id=%s
                    AND o.operation='approval_card' AND o.aggregate_version=%s""",
                    (
                        approval["id"],
                        approval["id"],
                        approval["task_id"],
                        actor.organization_id,
                        self.shop,
                        approval["plan_version"],
                    ),
                ).fetchone()
                if (
                    not approval["ready_at"]
                    or not binding
                    or binding["source_mode"] != "offline_fake"
                    or (binding["chat_id"], binding["message_id"])
                    != (
                        card.chat_id,
                        card.message_id,
                    )
                ):
                    raise WebFailure("CARD_CONTEXT_MISMATCH", 403)

            receipt = self.decisions.decide_in_transaction(
                db,
                actor,
                request.approval_id,
                request,
                binding_check=binding_check,
            )
            receipt = {**receipt, "identity_mode": "feishu", "schema_version": "p4-v1"}
            self._record(
                db,
                actor,
                card.event_id,
                None,
                semantic,
                receipt,
                {
                    "schema_version": "p4-v1",
                    "source_mode": "mock",
                    "model_mode": "not_used",
                    "event_type": "card.action.trigger",
                    "approval_id": str(request.approval_id),
                    "decision_source": "feishu",
                    "approval_mode": "simulated_feishu",
                },
            )
        if self.hook:
            self.hook("after_p4_commit")
        return receipt
