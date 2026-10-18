"""固定历史取回 once、原 API 证明及两条原读取的同事务 materialization。"""

import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from commerceops.adapters.feishu.contracts import PlatformIdentity
from commerceops.application.feishu_business.history import (
    HistoryPage,
    HistoryRecoveryRequest,
    message_semantic,
    verify_pages,
)
from commerceops.application.feishu_business.read_intents import parse_read_intent
from commerceops.application.replenishment.contracts import FeishuActor, WebFailure
from commerceops.domain.commerce_values import canonical_bytes, facts_hash
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_read_reply import capture, insert
from commerceops.infrastructure.web_sessions import DB

if TYPE_CHECKING:
    from commerceops.infrastructure.feishu_business import FeishuBusinessStore


def read_time(db: DB) -> str:
    row = db.execute("SELECT clock_timestamp() AS t").fetchone()
    if row is None:
        raise WebFailure("HISTORY_DATABASE_TIME_UNAVAILABLE")
    return str(row["t"].isoformat())


class HistoryRecoveryStore:
    def __init__(self, business: "FeishuBusinessStore"):
        self.business = business

    def actor(self, db: DB, request: HistoryRecoveryRequest) -> FeishuActor:
        actor = self.business.actor(
            db,
            PlatformIdentity(request.app_id, request.tenant_key, request.open_id),
            request.chat_id,
        )
        if (
            actor.organization_id,
            actor.principal_id,
            actor.identity_id,
            actor.auth_version,
            self.business.shop,
        ) != (
            request.organization_id,
            request.principal_id,
            request.identity_id,
            request.auth_version,
            request.shop_id,
        ):
            raise WebFailure("HISTORY_CURRENT_IDENTITY_DENIED", 403)
        for text in request.expected_texts:
            intent = parse_read_intent(text)
            if intent is None:
                raise WebFailure("HISTORY_FIXED_CONTRACT_INVALID")
            try:
                self.business.read_facts(db, actor, intent)
            except WebFailure as error:
                if error.code != "NOT_READY" or intent.kind != "explain_report":
                    raise
                capture(
                    db,
                    self.business.store,
                    actor,
                    intent,
                    {
                        "server_time": read_time(db),
                        "error": {"code": "NOT_READY"},
                    },
                )
        return actor

    def register(self, request: HistoryRecoveryRequest) -> None:
        """独立 commit 的原取回机会；重复/unknown 不注册新窗口或重读 Secret。"""
        if not request.enabled or not request.not_before <= datetime.now(UTC) < request.expires_at:
            raise PermissionError("HISTORY_WINDOW_CLOSED")
        value = request.model_dump(mode="json")
        with connect(self.business.store.settings) as db:
            self.actor(db, request)
            db.execute(
                """
INSERT INTO business.p4_history_recoveries
                (id,organization_id,shop_id,app_id,tenant_key,chat_id,request,
        canonical_request,request_hash)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    request.recovery_id,
                    request.organization_id,
                    request.shop_id,
                    request.app_id,
                    request.tenant_key,
                    request.chat_id,
                    Jsonb(value),
                    canonical_bytes(value).decode(),
                    facts_hash(value),
                ),
            )
            current = db.execute(
                "SELECT business.p4_history_collection_current(%s) AS ok", (request.recovery_id,)
            ).fetchone()
            if not current or not current["ok"]:
                raise WebFailure("HISTORY_CURRENT_PERMISSION_DENIED", 403)

    def observe(self, request: HistoryRecoveryRequest, page: HistoryPage) -> None:
        # 只保存本 API 响应，不记录鉴权响应或 token；坏响应也保留后 HOLD。
        with connect(self.business.store.settings) as db:
            row = db.execute(
                "SELECT * FROM business.p4_history_recoveries WHERE id=%s FOR UPDATE",
                (request.recovery_id,),
            ).fetchone()
            if (
                not row
                or row["request"] != request.model_dump(mode="json")
                or row["status"] != "collecting"
                or len(row["pages"]) >= 2
            ):
                raise WebFailure("HISTORY_ONCE_CLOSED")
            db.execute(
                "UPDATE business.p4_history_recoveries SET pages=pages||%s::jsonb WHERE id=%s",
                (Jsonb([page.record()]), request.recovery_id),
            )

    def hold(self, request: HistoryRecoveryRequest) -> None:
        with connect(self.business.store.settings) as db:
            db.execute(
                """UPDATE business.p4_history_recoveries SET status='hold',
                completed_at=clock_timestamp(),
                error_code='HISTORY_COLLECTION_OR_CURRENT_SOURCE_UNPROVEN'
                WHERE id=%s AND status='collecting' AND request_hash=%s""",
                (request.recovery_id, facts_hash(request.model_dump(mode="json"))),
            )

    def finish(self, request: HistoryRecoveryRequest) -> tuple[dict[str, Any], dict[str, Any]]:
        with connect(self.business.store.settings) as db:
            # RC + 同原 message lock；实时 RR 的旧 snapshot 另由唯一来源键拒绝。
            batch = db.execute(
                "SELECT * FROM business.p4_history_recoveries WHERE id=%s FOR UPDATE",
                (request.recovery_id,),
            ).fetchone()
            if (
                not batch
                or batch["status"] != "collecting"
                or batch["request"] != request.model_dump(mode="json")
            ):
                raise WebFailure("HISTORY_ONCE_CLOSED")
            messages = verify_pages(request, [HistoryPage.from_record(v) for v in batch["pages"]])
            actor = self.actor(db, request)
            receipts: list[dict[str, Any]] = []
            pending = []
            for message in messages:
                semantic = message_semantic(request, message.text)
                previous = self.business._previous(db, actor, None, semantic, message.message_id)
                intent = parse_read_intent(message.text)
                if intent is None:
                    raise WebFailure("HISTORY_FIXED_CONTRACT_INVALID")
                payload = None
                existing_inbox = None
                if previous:
                    if (
                        previous.get("read_intent") != intent.kind
                        or previous.get("referenced_task_id") != str(intent.task_id)
                        or previous.get("referenced_report_id")
                        != (str(intent.report_id) if intent.report_id else None)
                    ):
                        raise WebFailure("EVENT_CONFLICT")
                    receipt = previous
                    reply = UUID(receipt["reply_id"])
                    old = db.execute(
                        "SELECT inbox_id FROM business.p4_read_replies WHERE id=%s", (reply,)
                    ).fetchone()
                    if not old or old["inbox_id"] is None:
                        raise WebFailure("HISTORY_ORIGINAL_CARRIER_UNPROVEN")
                    existing_inbox = old["inbox_id"]
                else:
                    try:
                        facts = self.business.read_facts(db, actor, intent)
                    except WebFailure as error:
                        if error.code != "NOT_READY" or intent.kind != "explain_report":
                            raise
                        facts = {
                            "server_time": read_time(db),
                            "identity_mode": "feishu",
                            "error": {"code": "NOT_READY"},
                        }
                    payload = capture(db, self.business.store, actor, intent, facts)
                    reply = uuid4()
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
                        "source": "verified_history",
                        "original_message_id": message.message_id,
                        "original_sent_at": message.sent_at.isoformat(),
                    }
                identifier = uuid4()
                db.execute(
                    """
INSERT INTO business.p4_history_messages
                    (id,recovery_id,app_id,tenant_key,message_id,text,
        text_hash,semantic_hash,canonical_semantic,
                    kind,task_id,report_id,sent_at,observed_at,page_sha256,
        wire_row,receipt,reply_id,existing_inbox_id)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
        %s,%s)""",
                    (
                        identifier,
                        request.recovery_id,
                        request.app_id,
                        request.tenant_key,
                        message.message_id,
                        message.text,
                        hashlib.sha256(message.text.encode()).hexdigest(),
                        semantic,
                        canonical_bytes(
                            {
                                "open_id": request.open_id,
                                "chat": request.chat_id,
                                "text": message.text,
                            }
                        ).decode(),
                        intent.kind,
                        intent.task_id,
                        intent.report_id,
                        message.sent_at,
                        message.observed_at,
                        message.page_sha256,
                        Jsonb(message.wire_row),
                        Jsonb(receipt),
                        reply,
                        existing_inbox,
                    ),
                )
                if payload is not None:
                    pending.append((identifier, reply, payload))
                receipts.append(receipt)
            db.execute(
                """UPDATE business.p4_history_recoveries SET status='verified',
                completed_at=clock_timestamp() WHERE id=%s""",
                (request.recovery_id,),
            )
            for identifier, reply, payload in pending:
                insert(db, actor, None, None, reply, payload, history_message_id=identifier)
            if self.business.hook:
                self.business.hook("before_history_commit")
        return receipts[0], receipts[1]
