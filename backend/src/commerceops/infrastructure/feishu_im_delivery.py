"""正式审批卡/固定终态通知伴随意图；只由现有Worker维护调用一次原UUID。"""

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from commerceops.adapters.feishu.business_cards import build_business_card
from commerceops.adapters.feishu.contracts import ProbePolicy
from commerceops.application.feishu_business.clarification import NoticeResult
from commerceops.application.feishu_business.delivery import DeliveryGate
from commerceops.application.feishu_business.im_delivery import (
    BusinessMessage,
    BusinessMessageSender,
)
from commerceops.application.feishu_business.sdk_window import SDKScope
from commerceops.domain.commerce_values import facts_hash
from commerceops.infrastructure.approval_decisions import nonce_for
from commerceops.infrastructure.feishu_sdk_ledger import PersistentSDKLedger
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.worker_lock import WorkerSession, open_async


class IMDeliveryStore:
    def __init__(
        self,
        session: WorkerSession,
        config: WebConfig,
        policy: ProbePolicy,
        sender: BusinessMessageSender,
        gate: DeliveryGate,
        ledger: PersistentSDKLedger | None = None,
    ):
        if gate.organization_id != session.organization:
            raise ValueError("INVALID_IM_ORGANIZATION")
        if gate.verification_mode == "controlled_sdk" and ledger is None:
            raise ValueError("CONTROLLED_IM_REQUIRES_METHOD_LEDGER")
        self.session, self.config, self.policy, self.sender, self.gate, self.ledger = (
            session,
            config,
            policy,
            sender,
            gate,
            ledger,
        )

    async def enroll(self) -> None:
        async with await open_async(self.session.settings) as db, db.transaction():
            cur = await db.execute(
                """SELECT t.id,t.organization_id,t.shop_id,t.version,t.state,
                (SELECT count(*) FROM business.replenishment_items i WHERE i.task_id=t.id) AS items
                FROM business.business_tasks t JOIN business.conversations c
                ON c.id=t.conversation_id
                WHERE t.organization_id=%s AND t.shop_id=%s AND t.id=ANY(%s)
                AND c.channel='feishu' AND t.kind='inventory_replenishment'
                AND t.state IN ('completed','rejected','expired')""",
                (self.gate.organization_id, self.gate.shop_id, list(self.gate.task_ids)),
            )
            for terminal in await cur.fetchall():
                key = f"p4-result:{terminal['id']}:{terminal['version']}"
                text = (
                    f"Mock演示：任务{terminal['id']}已进入{terminal['state']}，"
                    f"内部工作项{terminal['items']}个。不代表采购或库存修改。"
                    f"Web：{self.config.origins[0]}/tasks/{terminal['id']}"
                )
                payload = {
                    "schema_version": "p4-v1",
                    "task_id": str(terminal["id"]),
                    "task_version": terminal["version"],
                    "text": text,
                }
                await db.execute(
                    """INSERT INTO business.outbox(id,organization_id,shop_id,task_id,destination,
                    aggregate_id,aggregate_version,operation,dedupe_key,request_hash,payload,
                    provider_idempotency_key,status) VALUES(%s,%s,%s,%s,'feishu_im',%s,%s,
                    'task_result',%s,%s,%s,%s,'pending') ON CONFLICT(dedupe_key) DO NOTHING""",
                    (
                        uuid4(),
                        terminal["organization_id"],
                        terminal["shop_id"],
                        terminal["id"],
                        terminal["id"],
                        terminal["version"],
                        key,
                        facts_hash(payload),
                        Jsonb(payload),
                        uuid4(),
                    ),
                )
            cur = await db.execute(
                """SELECT o.*,t.requester_id,t.normalized_request,c.chat_id,
            i.sanitized_payload->>'chat_type' AS chat_type,r.identity_id,a.ready_at,
            a.status AS approval_status FROM business.outbox o
            JOIN business.business_tasks t ON t.id=o.task_id
            JOIN business.conversations c ON c.id=t.conversation_id AND c.channel='feishu'
            JOIN business.inbox_events i ON i.task_id=t.id AND i.source='feishu_business'
            AND i.sanitized_payload->>'event_type'='im.message.receive_v1'
            JOIN business.p4_inbox_receipts r ON r.inbox_id=i.id
            LEFT JOIN business.approvals a ON a.id=o.aggregate_id
            WHERE o.organization_id=%s AND o.shop_id=%s AND o.task_id=ANY(%s)
            AND o.operation IN ('approval_card','task_result') AND NOT o.sender_enabled
            AND o.source_mode='mock' AND o.status='pending'
            AND (o.operation<>'approval_card' OR (a.ready_at IS NOT NULL AND a.status='pending'))
            AND NOT EXISTS(SELECT 1 FROM business.p4_im_deliveries d WHERE d.outbox_id=o.id)
            ORDER BY o.created_at,o.id""",
                (self.gate.organization_id, self.gate.shop_id, list(self.gate.task_ids)),
            )
            for row in await cur.fetchall():
                payload = row["payload"]
                if row["chat_type"] not in ("p2p", "group"):
                    raise ValueError("INVALID_ORIGINAL_IM_ROUTE")
                await db.execute(
                    """INSERT INTO business.p4_im_deliveries(outbox_id,
                organization_id,shop_id,task_id,identity_id,approval_id,kind,chat_id,chat_type,
                provider_uuid,payload,payload_hash,verification_mode)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (
                        row["id"],
                        row["organization_id"],
                        row["shop_id"],
                        row["task_id"],
                        row["identity_id"],
                        row["aggregate_id"] if row["operation"] == "approval_card" else None,
                        row["operation"],
                        row["chat_id"],
                        row["chat_type"],
                        row["provider_idempotency_key"],
                        Jsonb(payload),
                        facts_hash(payload),
                        self.gate.verification_mode,
                    ),
                )
            await self.session.check()

    async def dispatch_one(self) -> str:
        await self.session.check()
        if self.session.connection is None:
            raise ValueError("IM_WORKER_NOT_READY")
        async with await open_async(self.session.settings) as db:
            await db.execute(
                """INSERT INTO business.p4_sender_state(organization_id,shop_id,destination_alias,
                configured_enabled,expires_at,worker_owner,worker_backend_pid,verification_mode)
                VALUES(%s,%s,'IM',%s,%s,%s,%s,%s)
                ON CONFLICT(organization_id,shop_id,destination_alias) DO UPDATE SET
                configured_enabled=EXCLUDED.configured_enabled,expires_at=EXCLUDED.expires_at,
                worker_owner=EXCLUDED.worker_owner,worker_backend_pid=EXCLUDED.worker_backend_pid,
                verification_mode=EXCLUDED.verification_mode,checked_at=clock_timestamp()""",
                (
                    self.gate.organization_id,
                    self.gate.shop_id,
                    self.gate.enabled,
                    self.gate.expires_at,
                    self.session.owner,
                    self.session.connection.info.backend_pid,
                    self.gate.verification_mode,
                ),
            )
        if not self.gate.active():
            return "disabled"
        await self.enroll()
        async with await open_async(self.session.settings) as db, db.transaction():
            await db.execute(
                """UPDATE business.p4_im_deliveries SET status='unknown',
            last_error='IM_ACK_UNPROVEN' WHERE organization_id=%s
            AND status='sending' AND claimed_by<>%s""",
                (self.session.organization, self.session.owner),
            )
            cur = await db.execute(
                """SELECT d.*,p.id AS principal_id,p.auth_version,i.app_id,i.external_subject,
            i.tenant_key FROM business.p4_im_deliveries d
            JOIN business.identities i ON i.id=d.identity_id AND i.organization_id=d.organization_id
            JOIN business.principals p ON p.id=i.principal_id
            AND p.organization_id=i.organization_id AND i.provider='feishu'
            WHERE d.organization_id=%s AND d.shop_id=%s AND d.task_id=ANY(%s)
            AND d.verification_mode=%s AND d.status='pending' AND d.attempts=0
            ORDER BY d.created_at,d.outbox_id LIMIT 1 FOR UPDATE OF d FOR SHARE OF p,i""",
                (
                    self.gate.organization_id,
                    self.gate.shop_id,
                    list(self.gate.task_ids),
                    self.gate.verification_mode,
                ),
            )
            row = await cur.fetchone()
            if not row:
                return "idle"
            cur = await db.execute(
                "SELECT business.lock_p3_permission(%s,%s,%s,%s,%s,'operator') AS ok",
                (
                    row["principal_id"],
                    row["organization_id"],
                    row["shop_id"],
                    row["identity_id"],
                    row["auth_version"],
                ),
            )
            permission = await cur.fetchone()
            permitted = bool(
                permission
                and permission["ok"]
                and (row["app_id"], row["tenant_key"])
                == (self.policy.app_id, self.policy.tenant_key)
                and row["external_subject"] in self.policy.allowed_open_ids
                and (
                    row["chat_type"] == "p2p"
                    or row["chat_id"] in self.policy.allowed_group_chat_ids
                )
            )
            if not permitted:
                await db.execute(
                    "UPDATE business.p4_im_deliveries SET status='dead',"
                    "last_error='CURRENT_PERMISSION_DENIED' WHERE outbox_id=%s",
                    (row["outbox_id"],),
                )
                return "denied"
            card = None
            text = None
            if facts_hash(row["payload"]) != row["payload_hash"]:
                raise ValueError("INVALID_PERSISTENT_IM_PAYLOAD")
            if row["kind"] == "approval_card":
                cur = await db.execute(
                    "SELECT * FROM business.approvals WHERE id=%s", (row["approval_id"],)
                )
                approval = await cur.fetchone()
                if (
                    not approval
                    or approval["status"] != "pending"
                    or not approval["ready_at"]
                    or approval["expires_at"] <= datetime.now(UTC)
                ):
                    await db.execute(
                        "UPDATE business.p4_im_deliveries SET status='dead',"
                        "last_error='APPROVAL_NOT_CURRENT' WHERE outbox_id=%s",
                        (row["outbox_id"],),
                    )
                    return "stale"
                cur = await db.execute(
                    "SELECT * FROM business.replenishment_plans WHERE id=%s AND status='current'",
                    (approval["plan_id"],),
                )
                plan = await cur.fetchone()
                if not plan or facts_hash(row["payload"]) != row["payload_hash"]:
                    raise ValueError("INVALID_PERSISTENT_CARD_BINDING")
                card = build_business_card(
                    plan["content"], approval, nonce_for(self.config, approval)
                )
            else:
                text = row["payload"]["text"]
            await db.execute(
                """UPDATE business.p4_im_deliveries SET status='sending',attempts=1,
            claimed_by=%s,first_attempt_at=clock_timestamp() WHERE outbox_id=%s""",
                (self.session.owner, row["outbox_id"]),
            )
            await self.session.check()
        request = BusinessMessage(
            outbox_id=row["outbox_id"],
            provider_uuid=row["provider_uuid"],
            chat_id=row["chat_id"],
            kind="interactive" if card else "text",
            card=card,
            text=text,
        )
        if not self.gate.active():
            result = NoticeResult(outcome="unknown", code="IM_WINDOW_EXPIRED")
        else:
            result = await self._send(request, row)
        await self.session.check()
        async with await open_async(self.session.settings) as db, db.transaction():
            await db.execute(
                """UPDATE business.p4_im_deliveries SET status=%s,message_id=%s,
            last_error=%s WHERE outbox_id=%s AND status='sending' AND claimed_by=%s""",
                (
                    "dead" if result.outcome == "rejected" else result.outcome,
                    result.message_id,
                    None if result.outcome == "sent" else result.code,
                    row["outbox_id"],
                    self.session.owner,
                ),
            )
            if result.outcome == "sent" and row["kind"] == "approval_card":
                await db.execute(
                    """INSERT INTO business.p4_card_bindings(approval_id,outbox_id,
                chat_id,message_id,source_mode) VALUES(%s,%s,%s,%s,%s)""",
                    (
                        row["approval_id"],
                        row["outbox_id"],
                        row["chat_id"],
                        result.message_id,
                        "offline_fake"
                        if self.gate.verification_mode == "offline_fake"
                        else "feishu",
                    ),
                )
            await self.session.check()
        return result.outcome

    async def _send(self, request: BusinessMessage, row: dict[str, Any]) -> NoticeResult:
        try:
            async with asyncio.timeout(10):
                if self.ledger:
                    with self.ledger.scope(SDKScope(row["outbox_id"], row["task_id"], row["kind"])):
                        result = await self.sender.send_message(request)
                else:
                    result = await self.sender.send_message(request)
            result = NoticeResult.model_validate(result.model_dump())
        except Exception:
            result = NoticeResult(outcome="unknown", code="IM_TRANSPORT_UNKNOWN")
        return result

    async def reconcile(self) -> None:
        await self.dispatch_one()
