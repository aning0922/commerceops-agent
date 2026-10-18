"""正式Gateway短事务：可信身份/inbox/T1或T3同commit；没有外部调用。"""

from collections.abc import Callable
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from psycopg.errors import SerializationFailure, UniqueViolation
from psycopg.types.json import Jsonb

from commerceops.adapters.feishu.business_gateway import BusinessCard
from commerceops.adapters.feishu.contracts import MessageProbe, PlatformIdentity
from commerceops.application.feishu_business.read_intents import ReadIntent, parse_read_intent
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
from commerceops.infrastructure.web_sessions import DB, actor_guard, now, role_scope


class FeishuBusinessStore:
    def __init__(
        self,
        store: ReplenishmentStore,
        shop_id: UUID,
        parameters: Parameters,
        *,
        hook: Callable[[str], None] | None = None,
        allow_live_bindings: bool = False,
        gateway_guard: Callable[[DB, bool], None] | None = None,
        f02_enabled: bool = False,
        f02_gateway_window_id: UUID | None = None,
    ):
        self.store, self.shop, self.parameters, self.hook = store, shop_id, parameters, hook
        self.decisions = DecisionStore(store.config)
        if type(allow_live_bindings) is not bool:
            raise ValueError("INVALID_LIVE_BINDING_GATE")
        self.allow_live_bindings = allow_live_bindings
        self.gateway_guard = gateway_guard
        if type(f02_enabled) is not bool:
            raise ValueError("INVALID_F02_GATE")
        self.f02_enabled = f02_enabled
        if f02_gateway_window_id is not None and (
            type(f02_gateway_window_id) is not UUID or not f02_enabled or gateway_guard is None
        ):
            raise ValueError("INVALID_F02_GATEWAY_SELECTION")
        self.f02_gateway_window_id = f02_gateway_window_id

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
        self, db: DB, actor: FeishuActor, event: str | None, semantic: str, message: str | None
    ) -> dict[str, Any] | None:
        # 两层键统一排序锁；同message新event仍回同一原inbox/task。
        keys = [f"p4:event:{actor.app_id}:{actor.tenant_key}:{event}"] if event is not None else []
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
            schema = (
                db.execute("SELECT to_regclass('business.p4_history_messages') AS t").fetchone()
                if message
                else None
            )
            if message and schema and schema["t"] is not None:
                history = db.execute(
                    """SELECT m.*,b.request,b.organization_id,b.shop_id
                    FROM business.p4_history_messages m
                    JOIN business.p4_history_recoveries b ON b.id=m.recovery_id
                    JOIN business.p4_read_replies r ON r.history_message_id=m.id
                    WHERE m.app_id=%s AND m.tenant_key=%s
                    AND m.message_id=%s AND b.status='verified'""",
                    (actor.app_id, actor.tenant_key, message),
                ).fetchone()
                if history:
                    if (
                        history["organization_id"],
                        history["shop_id"],
                        history["semantic_hash"],
                        history["request"]["principal_id"],
                        history["request"]["identity_id"],
                    ) != (
                        actor.organization_id,
                        self.shop,
                        semantic,
                        str(actor.principal_id),
                        str(actor.identity_id),
                    ):
                        raise WebFailure("EVENT_CONFLICT")
                    actor_guard(db, actor)
                    current = db.execute(
                        "SELECT business.p4_read_reply_current(%s) AS ok", (history["reply_id"],)
                    ).fetchone()
                    if not current or not current["ok"]:
                        raise WebFailure("READ_REPLY_STALE")
                    return {**history["receipt"], "duplicate": True}
            return None
        if (
            len(rows) != 1
            or rows[0]["identity_id"] != actor.identity_id
            or rows[0]["sanitized_payload"].get("principal_id") != str(actor.principal_id)
            or (rows[0]["payload_hash"] != semantic or rows[0]["shop_id"] != self.shop)
        ):
            raise WebFailure("EVENT_CONFLICT")
        actor_guard(db, actor)
        if rows[0]["result"].get("read_intent"):
            value = rows[0]["result"]
            intent = ReadIntent(
                value["read_intent"],
                UUID(value["referenced_task_id"]),
                UUID(value["referenced_report_id"]) if value.get("referenced_report_id") else None,
            )
            try:
                self.read_facts(db, actor, intent)
            except WebFailure as error:
                if (
                    error.code != "NOT_READY"
                    or value.get("facts", {}).get("error", {}).get("code") != "NOT_READY"
                ):
                    raise
                from commerceops.infrastructure.feishu_read_reply import capture

                capture(
                    db,
                    self.store,
                    actor,
                    intent,
                    {"server_time": value["as_of"], "error": {"code": "NOT_READY"}},
                )
        elif not role_scope(db, actor, self.shop, "operator" if message else "approver"):
            raise WebFailure("ACCESS_DENIED", 403)
        if rows[0]["result"].get("clarification_id"):
            from commerceops.infrastructure.feishu_clarification_requests import F02Requests

            F02Requests(self).replay(db, actor, rows[0]["result"])
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
        *,
        inbox_id: UUID | None = None,
        link_task: bool = True,
    ) -> UUID:
        inbox = inbox_id or uuid4()
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
                UUID(receipt["task_id"]) if link_task and receipt.get("task_id") else None,
            ),
        )
        db.execute(
            "INSERT INTO business.p4_inbox_receipts(inbox_id,identity_id,result) VALUES(%s,%s,%s)",
            (inbox, actor.identity_id, Jsonb(receipt)),
        )
        if self.hook:
            self.hook("before_p4_commit")
        return inbox

    def message(self, message: MessageProbe) -> dict[str, Any]:
        if not parse_read_intent(message.text):
            return self._message(message)
        # RR snapshot 在并发原 inbox 提交后不可复用；只重启这一个入站事务，不重发 IM。
        for attempt in range(3):
            try:
                return self._message(message)
            except (SerializationFailure, UniqueViolation):
                if attempt == 2:
                    raise
        raise WebFailure("EVENT_CONFLICT")

    def _message(self, message: MessageProbe) -> dict[str, Any]:
        # 首切片确定性文法，模糊请求不生成任务/模型请求；正式路由另增量接线。
        semantic = facts_hash(
            {"open_id": message.identity.open_id, "chat": message.chat_id, "text": message.text}
        )
        with connect(self.store.settings) as db:
            if parse_read_intent(message.text):
                db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            actor = self.actor(db, message.identity, message.chat_id)
            if self.gateway_guard:
                self.gateway_guard(db, False)
            old = self._previous(db, actor, message.event_id, semantic, message.message_id)
            if old:
                return old
            if intent := parse_read_intent(message.text):
                try:
                    facts = self.read_facts(db, actor, intent)
                except WebFailure as error:
                    if error.code != "NOT_READY" or intent.kind != "explain_report":
                        raise
                    facts = {
                        "server_time": now(db).isoformat(),
                        "identity_mode": "feishu",
                        "error": {"code": "NOT_READY"},
                    }
                from commerceops.infrastructure.feishu_read_reply import capture, insert

                reply = uuid4()
                payload = capture(db, self.store, actor, intent, facts)
                receipt = {
                    "schema_version": "p4-v1",
                    "identity_mode": "feishu",
                    "state": "read_completed",
                    "read_intent": intent.kind,
                    "referenced_task_id": str(intent.task_id),
                    "referenced_report_id": str(intent.report_id) if intent.report_id else None,
                    "as_of": payload.model_dump(mode="json")["as_of"],
                    "facts": facts,
                    "model_mode": "not_used",
                    "reply_id": str(reply),
                    "reply_payload_hash": facts_hash(payload.model_dump(mode="json")),
                    "reply_delivery": "pending",
                    "duplicate": False,
                }
                read_inbox = self._record(
                    db,
                    actor,
                    message.event_id,
                    message.message_id,
                    semantic,
                    receipt,
                    {
                        "schema_version": "p4-v1",
                        "event_type": "p4.explicit_read",
                        "chat_id": message.chat_id,
                        "chat_type": message.chat_type,
                        "source_mode": "mock",
                        "model_mode": "not_used",
                        "text_sha256": facts_hash(message.text),
                    },
                )
                insert(db, actor, message, read_inbox, reply, payload)
                return receipt
            if not role_scope(db, actor, self.shop, "operator"):
                raise WebFailure("ACCESS_DENIED", 403)
            if self.f02_enabled:
                from commerceops.infrastructure.feishu_clarification_requests import F02Requests

                if accepted := F02Requests(self).accept(db, actor, message, semantic):
                    return accepted
            if self.f02_enabled or message.text not in (
                "分析最近七天库存并生成补货建议",
                "分析库存并生成补货建议",
            ):
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
                if self.gateway_guard:
                    self.gateway_guard(db, True)
                receipt = self._create_message_task(db, actor, message)
        if self.hook:
            self.hook("after_p4_commit")
        return receipt

    def read_facts(self, db: DB, actor: FeishuActor, intent: ReadIntent) -> dict[str, Any]:
        from commerceops.infrastructure.replenishment_read import (
            ReplenishmentReadStore,
            read_visible_task,
        )

        task = read_visible_task(db, actor, intent.task_id)
        if task["shop_id"] != self.shop:
            raise WebFailure("RESOURCE_NOT_FOUND", 404)
        reads = ReplenishmentReadStore(self.store)
        if intent.kind == "task_status":
            result = reads.task_in_transaction(db, actor, intent.task_id)
        elif intent.report_id is not None:
            result = reads.explanation_in_transaction(db, actor, intent.task_id, intent.report_id)
        else:
            raise WebFailure("INVALID_REQUEST", 422)
        # 复用业务投影但不把 Feishu 身份冒称 session；不调度/发送 IM。
        return {**result, "identity_mode": "feishu"}

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
            if self.gateway_guard:
                self.gateway_guard(db, False)
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
                    or binding["source_mode"]
                    != ("feishu" if self.allow_live_bindings else "offline_fake")
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
