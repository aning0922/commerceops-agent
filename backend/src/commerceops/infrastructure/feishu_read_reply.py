"""原入站事务冻结两种回复；原单 Worker lease 下仅发送一个原 UUID。"""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from pydantic import ValidationError

from commerceops.adapters.feishu.contracts import MessageProbe, ProbePolicy
from commerceops.application.feishu_business.clarification import NoticeResult
from commerceops.application.feishu_business.im_delivery import BusinessMessageSender
from commerceops.application.feishu_business.read_intents import ReadIntent
from commerceops.application.feishu_business.read_reply import ReadReplyPayload, ReadSource
from commerceops.application.feishu_business.sdk_window import SDKScope
from commerceops.application.replenishment.contracts import FeishuActor, WebFailure
from commerceops.domain.commerce_values import canonical_bytes, facts_hash
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_sdk_ledger import PersistentSDKLedger
from commerceops.infrastructure.inventory_repository import AnalysisUnsafe
from commerceops.infrastructure.replenishment_read import ReplenishmentReadStore, read_visible_task
from commerceops.infrastructure.replenishment_repository import ReplenishmentStore
from commerceops.infrastructure.web_sessions import DB
from commerceops.infrastructure.worker_lock import WorkerSession


def capture(
    db: DB, store: ReplenishmentStore, actor: FeishuActor, intent: ReadIntent, facts: dict[str, Any]
) -> ReadReplyPayload:
    task = read_visible_task(db, actor, intent.task_id)
    source = None
    explanation = facts.get("explanation")
    if explanation and explanation["schema_version"] == "p4-p3-template-read-v1":
        source = {key: explanation[key] for key in ReadSource.model_fields}
    else:
        original = ReplenishmentReadStore._source(db, task)
        if original:
            source = {
                "source_kind": "p2_original",
                "source_task_id": str(original["task_id"]),
                "observation_id": None,
                "report_id": str(original["id"]),
                "snapshot_id": str(original["snapshot_id"]),
                "facts_hash": original["facts_hash"],
            }
            if intent.kind == "explain_report" and original["id"] != intent.report_id:
                observation = db.execute(
                    """SELECT * FROM business.p3_observations WHERE task_id=%s
                    AND organization_id=%s AND shop_id=%s AND report_id=%s""",
                    (task["id"], task["organization_id"], task["shop_id"], intent.report_id),
                ).fetchone()
                binding = db.execute(
                    "SELECT * FROM business.p3_task_sources WHERE task_id=%s", (task["id"],)
                ).fetchone()
                if observation is None or binding is None:
                    raise WebFailure("RESOURCE_NOT_FOUND", 404)
                from commerceops.infrastructure.replenishment_execution import ExecutionStore

                ExecutionStore.verify_row(observation, binding)
                source = {
                    "source_kind": "p3_observation",
                    "source_task_id": str(observation["source_task_id"]),
                    "observation_id": str(observation["id"]),
                    "report_id": str(observation["report_id"]),
                    "snapshot_id": str(observation["id"]),
                    "facts_hash": observation["facts_hash"],
                }
    return ReadReplyPayload.model_validate_json(
        json.dumps(
            {
                "kind": intent.kind,
                "task_id": str(task["id"]),
                "task_version": task["version"],
                "task_state": task["state"],
                "as_of": facts["server_time"],
                "read_code": facts.get("error", {}).get("code", "OK"),
                "source": source,
                "explanation": explanation,
            }
        )
    )


def insert(
    db: DB,
    actor: FeishuActor,
    message: MessageProbe | None,
    inbox: UUID | None,
    identifier: UUID,
    payload: ReadReplyPayload,
    *,
    history_message_id: UUID | None = None,
) -> None:
    if (history_message_id is None) != (message is not None and inbox is not None):
        raise WebFailure("READ_REPLY_ORIGIN_INVALID")
    value = payload.model_dump(mode="json")
    source = payload.source
    task = db.execute(
        "SELECT shop_id FROM business.business_tasks WHERE id=%s", (payload.task_id,)
    ).fetchone()
    if task is None:
        raise WebFailure("RESOURCE_NOT_FOUND", 404)
    history_column = ",history_message_id" if history_message_id is not None else ""
    history_parameter = ",%s" if history_message_id is not None else ""
    db.execute(
        f"""INSERT INTO business.p4_read_replies
        (id,inbox_id,organization_id,shop_id,principal_id,identity_id,auth_version,
        app_id,tenant_key,open_id,chat_id,chat_type,kind,task_id,task_version,task_state,
        source_kind,source_task_id,observation_id,report_id,snapshot_id,facts_hash,as_of,
        payload,canonical_payload,payload_hash,provider_uuid{history_column})
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s{history_parameter})""",
        (
            identifier,
            inbox,
            actor.organization_id,
            task["shop_id"],
            actor.principal_id,
            actor.identity_id,
            actor.auth_version,
            actor.app_id,
            actor.tenant_key,
            actor.open_id,
            actor.chat_id,
            message.chat_type if message is not None else "p2p",
            payload.kind,
            payload.task_id,
            payload.task_version,
            payload.task_state,
            source.source_kind if source else None,
            source.source_task_id if source else None,
            source.observation_id if source else None,
            source.report_id if source else None,
            source.snapshot_id if source else None,
            source.facts_hash if source else None,
            payload.as_of,
            Jsonb(value),
            canonical_bytes(value).decode(),
            facts_hash(value),
            uuid4(),
        )
        + ((history_message_id,) if history_message_id is not None else ()),
    )


class ReadReplyDeliveryStore:
    def __init__(
        self,
        session: WorkerSession,
        store: ReplenishmentStore,
        policy: ProbePolicy,
        sender: BusinessMessageSender,
        ledger: PersistentSDKLedger,
        reply_id: UUID,
        task_id: UUID,
    ):
        if (
            (session.organization, store.settings)
            != (ledger.window.organization_id, session.settings)
            or store.settings != session.settings
            or ledger.session is not session
        ):
            raise ValueError("READ_REPLY_WORKER_BINDING_INVALID")
        self.session, self.store, self.policy, self.sender, self.ledger = (
            session,
            store,
            policy,
            sender,
            ledger,
        )
        self.reply_id, self.task_id = reply_id, task_id

    def current(self, db: DB, row: dict[str, Any]) -> ReadReplyPayload:
        payload = ReadReplyPayload.model_validate_json(row["canonical_payload"])
        value = payload.model_dump(mode="json")
        source = payload.source
        columns = {
            "kind": payload.kind,
            "task_id": payload.task_id,
            "task_version": payload.task_version,
            "task_state": payload.task_state,
            "as_of": payload.as_of,
            **{key: getattr(source, key) if source else None for key in ReadSource.model_fields},
        }
        if (
            any(row[key] != expected for key, expected in columns.items())
            or row["task_id"] != self.task_id
            or row["id"] != self.reply_id
            or row["organization_id"] != self.session.organization
            or row["shop_id"] != self.ledger.window.shop_id
            or row["payload"] != value
            or canonical_bytes(value).decode() != row["canonical_payload"]
            or facts_hash(value) != row["payload_hash"]
        ):
            raise WebFailure("READ_REPLY_BINDING_INVALID")
        identity = db.execute(
            """SELECT i.*,p.auth_version FROM business.identities i
            JOIN business.principals p ON p.id=i.principal_id
            AND p.organization_id=i.organization_id
            WHERE i.id=%s FOR SHARE OF i,p""",
            (row["identity_id"],),
        ).fetchone()
        if (
            identity is None
            or identity["provider"] != "feishu"
            or any(
                identity[key] != row[key]
                for key in (
                    "principal_id",
                    "organization_id",
                    "app_id",
                    "tenant_key",
                    "auth_version",
                )
            )
            or identity["external_subject"] != row["open_id"]
            or (row["app_id"], row["tenant_key"]) != (self.policy.app_id, self.policy.tenant_key)
            or row["open_id"] not in self.policy.allowed_open_ids
            or row["chat_type"] == "group"
            and row["chat_id"] not in self.policy.allowed_group_chat_ids
        ):
            raise WebFailure("READ_REPLY_CURRENT_PERMISSION_DENIED")
        actor = FeishuActor(
            row["principal_id"],
            row["identity_id"],
            row["organization_id"],
            row["auth_version"],
            row["app_id"],
            row["tenant_key"],
            row["open_id"],
            row["chat_id"],
        )
        task = db.execute(
            "SELECT * FROM business.business_tasks WHERE id=%s FOR SHARE", (row["task_id"],)
        ).fetchone()
        if not task or (task["version"], task["state"]) != (
            payload.task_version,
            payload.task_state,
        ):
            raise WebFailure("READ_REPLY_STALE")
        receipt = db.execute(
            """SELECT r.result,i.sanitized_payload,i.app_id,i.tenant_key
            FROM business.p4_inbox_receipts r JOIN business.inbox_events i ON i.id=r.inbox_id
            WHERE r.inbox_id=%s AND r.identity_id=%s""",
            (row["inbox_id"], row["identity_id"]),
        ).fetchone()
        if row.get("history_message_id") is not None:
            origin = db.execute(
                """SELECT business.p4_read_reply_origin_current(r) AS ok
                FROM business.p4_read_replies r WHERE r.id=%s""",
                (row["id"],),
            ).fetchone()
            if not origin or not origin["ok"]:
                raise WebFailure("READ_REPLY_RECEIPT_INVALID")
        elif (
            receipt is None
            or receipt["result"].get("reply_id") != str(row["id"])
            or receipt["result"].get("reply_payload_hash") != row["payload_hash"]
            or receipt["result"].get("as_of") != value["as_of"]
            or (receipt["app_id"], receipt["tenant_key"]) != (row["app_id"], row["tenant_key"])
            or receipt["sanitized_payload"].get("chat_id") != row["chat_id"]
            or receipt["sanitized_payload"].get("chat_type") != row["chat_type"]
        ):
            raise WebFailure("READ_REPLY_RECEIPT_INVALID")
        reads = ReplenishmentReadStore(self.store)
        intent = ReadIntent(
            payload.kind,
            payload.task_id,
            source.report_id if source and payload.kind == "explain_report" else None,
        )
        if payload.kind == "task_status":
            facts = reads.task_in_transaction(db, actor, payload.task_id)
        else:
            if source is None:
                raise WebFailure("READ_REPLY_BINDING_INVALID")
            try:
                facts = reads.explanation_in_transaction(
                    db, actor, payload.task_id, source.report_id
                )
            except WebFailure as error:
                if error.code != "NOT_READY":
                    raise
                facts = {"server_time": payload.as_of.isoformat(), "error": {"code": "NOT_READY"}}
        actual = capture(db, self.store, actor, intent, facts).model_copy(
            update={"as_of": payload.as_of}
        )
        if actual != payload:
            raise WebFailure("READ_REPLY_STALE")
        return payload

    async def recover_unknown(self) -> None:
        await self.session.check()
        with connect(self.store.settings) as db:
            db.execute(
                """UPDATE business.p4_read_replies SET status='unknown',
                last_error='SEND_ACK_UNPROVEN'
                WHERE id=%s AND organization_id=%s AND task_id=%s AND status='sending'
                AND claimed_by<>%s""",
                (self.reply_id, self.session.organization, self.task_id, self.session.owner),
            )

    async def dispatch_one(self) -> str:
        if not self.ledger.window.allows("im.v1.message.create"):
            return "disabled"
        await self.session.check()
        with connect(self.store.settings) as db:
            row = db.execute(
                """SELECT * FROM business.p4_read_replies
                WHERE id=%s AND organization_id=%s AND task_id=%s
                AND status='pending' AND attempts=0
                FOR UPDATE""",
                (self.reply_id, self.session.organization, self.task_id),
            ).fetchone()
            if not row:
                return "idle"
            try:
                payload = self.current(db, row)
            except (WebFailure, AnalysisUnsafe, ValidationError):
                db.execute(
                    """UPDATE business.p4_read_replies SET status='dead',
                    last_error='READ_REPLY_CURRENT_SOURCE_DENIED' WHERE id=%s""",
                    (row["id"],),
                )
                return "denied"
            if not self.ledger.window.allows("im.v1.message.create"):
                return "disabled"
            db.execute(
                """UPDATE business.p4_read_replies SET status='sending',attempts=1,
                claimed_by=%s,first_attempt_at=clock_timestamp() WHERE id=%s""",
                (self.session.owner, row["id"]),
            )
        # 不持网络事务；started 预占由原 ledger 在 SDK 前单独 commit。
        original_sent_at = None
        if row.get("history_message_id") is not None:
            with connect(self.store.settings) as db:
                original = db.execute(
                    "SELECT sent_at FROM business.p4_history_messages WHERE id=%s",
                    (row["history_message_id"],),
                ).fetchone()
                if original is None:
                    raise WebFailure("READ_REPLY_RECEIPT_INVALID")
                original_sent_at = original["sent_at"]
        request = payload.message(
            row["id"], row["provider_uuid"], row["chat_id"], original_sent_at=original_sent_at
        )
        try:
            await self.session.check()
            remaining = (self.ledger.window.expires_at - datetime.now(UTC)).total_seconds()
            async with asyncio.timeout(min(10, remaining)):
                with self.ledger.scope(SDKScope(row["id"], row["task_id"], "read_reply")):
                    result = await self.sender.send_message(request)
            result = NoticeResult.model_validate(result.model_dump())
        except Exception:
            result = NoticeResult(outcome="unknown", code="READ_REPLY_ACK_UNKNOWN")
        await self.session.check()
        if not self.ledger.window.allows("im.v1.message.create"):
            result = NoticeResult(outcome="unknown", code="READ_REPLY_LATE_ACK")
        with connect(self.store.settings) as db:
            possible_call = db.execute(
                """SELECT 1 FROM business.p4_sdk_calls WHERE subject_id=%s
                AND scope_kind='read_reply' AND status<>'not_called' LIMIT 1""",
                (row["id"],),
            ).fetchone()
            if result.outcome == "unknown" and possible_call is None:
                result = NoticeResult(outcome="rejected", code="READ_REPLY_NOT_CALLED")
            db.execute(
                """UPDATE business.p4_read_replies SET status=%s,message_id=%s,last_error=%s
                WHERE id=%s AND status='sending' AND claimed_by=%s AND provider_uuid=%s""",
                (
                    "dead" if result.outcome == "rejected" else result.outcome,
                    result.message_id,
                    None if result.outcome == "sent" else result.code,
                    row["id"],
                    self.session.owner,
                    row["provider_uuid"],
                ),
            )
        return result.outcome
