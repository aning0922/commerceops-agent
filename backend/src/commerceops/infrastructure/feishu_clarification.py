"""唯一Worker协调固定澄清回复；发送前持久领取，unknown永久停止自动重发。"""

import asyncio
import json
from uuid import UUID

from commerceops.adapters.feishu.contracts import ProbePolicy
from commerceops.application.feishu_business.clarification import (
    ClarificationMessage,
    ClarificationSender,
    F02Candidate,
    F02Message,
    F02Sender,
    NoticeResult,
)
from commerceops.application.feishu_business.sdk_window import SDKScope
from commerceops.infrastructure.feishu_sdk_ledger import PersistentSDKLedger
from commerceops.infrastructure.worker_lock import WorkerSession, open_async


class ClarificationDeliveryStore:
    def __init__(
        self,
        session: WorkerSession,
        policy: ProbePolicy,
        sender: ClarificationSender,
        *,
        controlled_sender: bool = False,
        ledger: PersistentSDKLedger | None = None,
        request_ids: frozenset[UUID] | None = None,
        f02_sender: F02Sender | None = None,
    ):
        self.session, self.policy, self.sender = session, policy, sender
        self.controlled_sender = controlled_sender
        self.ledger = ledger
        if request_ids is not None and (
            type(request_ids) is not frozenset
            or not 1 <= len(request_ids) <= 5
            or any(type(i) is not UUID for i in request_ids)
        ):
            raise ValueError("INVALID_F02_SELECTED_REQUESTS")
        self.request_ids = request_ids
        if request_ids is not None and f02_sender is None:
            raise ValueError("F02_SELECTED_REQUESTS_REQUIRE_SENDER")
        self.f02_sender = f02_sender

    async def recover_unknown(self) -> None:
        # WorkerSession.start已核旧PID终止，不能由租约/锁可获猜停止。
        await self.session.check()
        async with await open_async(self.session.settings) as db:
            await db.execute(
                """UPDATE business.p4_clarification_replies
                SET status='unknown',last_error='SEND_ACK_UNPROVEN'
                WHERE organization_id=%s AND status='sending' AND claimed_by<>%s
                AND ((%s::uuid[] IS NULL AND request_id IS NULL) OR request_id=ANY(%s))""",
                (
                    self.session.organization,
                    self.session.owner,
                    None if self.request_ids is None else list(self.request_ids),
                    None if self.request_ids is None else list(self.request_ids),
                ),
            )

    async def dispatch_one(self) -> str:
        if not self.controlled_sender:
            return "disabled"
        await self.session.check()
        async with await open_async(self.session.settings) as db, db.transaction():
            cur = await db.execute(
                """SELECT r.*,i.app_id,i.tenant_key,i.external_subject,p.auth_version,p.enabled
                FROM business.p4_clarification_replies r JOIN business.identities i
                ON i.id=r.identity_id AND i.principal_id=r.principal_id
                AND i.organization_id=r.organization_id JOIN business.principals p
                ON p.id=r.principal_id AND p.organization_id=r.organization_id
                WHERE r.organization_id=%s AND r.status='pending' AND r.attempts=0
                AND ((%s::uuid[] IS NULL AND r.request_id IS NULL) OR r.request_id=ANY(%s))
                ORDER BY r.created_at,r.id LIMIT 1 FOR UPDATE OF r FOR SHARE OF p,i""",
                (
                    self.session.organization,
                    None if self.request_ids is None else list(self.request_ids),
                    None if self.request_ids is None else list(self.request_ids),
                ),
            )
            row = await cur.fetchone()
            if not row:
                return "idle"
            cur = await db.execute(
                "SELECT business.lock_p3_permission(%s,%s,%s,%s,%s,'operator') AS allowed",
                (
                    row["principal_id"],
                    row["organization_id"],
                    row["shop_id"],
                    row["identity_id"],
                    row["auth_version"],
                ),
            )
            permission = await cur.fetchone()
            allowed = bool(
                row["enabled"]
                and permission
                and permission["allowed"]
                and (row["app_id"], row["tenant_key"])
                == (self.policy.app_id, self.policy.tenant_key)
                and row["external_subject"] in self.policy.allowed_open_ids
                and (
                    row["chat_type"] == "p2p"
                    or row["chat_id"] in self.policy.allowed_group_chat_ids
                )
            )
            if row["request_id"] is not None:
                cur = await db.execute(
                    "SELECT * FROM business.p4_clarification_requests WHERE id=%s FOR SHARE",
                    (row["request_id"],),
                )
                current = await cur.fetchone()
                cur = await db.execute("SELECT clock_timestamp() AS t")
                clock = await cur.fetchone()
                payload = F02Candidate.model_validate_json(json.dumps(row["frozen_payload"]))
                allowed = bool(
                    allowed
                    and current
                    and (
                        current["organization_id"],
                        current["shop_id"],
                        current["principal_id"],
                        current["identity_id"],
                        current["chat_id"],
                        current["chat_type"],
                        current["app_id"],
                        current["tenant_key"],
                        current["auth_version"],
                    )
                    == (
                        row["organization_id"],
                        row["shop_id"],
                        row["principal_id"],
                        row["identity_id"],
                        row["chat_id"],
                        row["chat_type"],
                        row["app_id"],
                        row["tenant_key"],
                        row["auth_version"],
                    )
                    and current["round"] == row["round"] == payload.round
                    and current["candidate_hash"] == payload.confirmation_hash()
                    and (
                        current["state"] == "consumed"
                        and row["kind"] == "created"
                        and str(current["task_id"]) == str(payload.task_id)
                        or current["state"] in ("awaiting_parameters", "awaiting_confirmation")
                        and row["kind"] in ("question", "ready")
                        and current["state"]
                        == (
                            "awaiting_parameters"
                            if row["kind"] == "question"
                            else "awaiting_confirmation"
                        )
                        and clock is not None
                        and current["expires_at"] > clock["t"]
                    )
                )
            if not allowed:
                await db.execute(
                    "UPDATE business.p4_clarification_replies SET status='dead',"
                    "last_error='CURRENT_PERMISSION_DENIED' WHERE id=%s",
                    (row["id"],),
                )
                return "denied"
            await db.execute(
                """UPDATE business.p4_clarification_replies SET status='sending',attempts=1,
                claimed_by=%s,first_attempt_at=clock_timestamp() WHERE id=%s""",
                (self.session.owner, row["id"]),
            )
            await self.session.check()
        # 网络调用不持业务事务；完整固定文本/原UUID来自已提交窄行。
        request: ClarificationMessage | F02Message
        if row["request_id"] is None:
            request = ClarificationMessage(
                reply_id=row["id"], provider_uuid=row["provider_uuid"], chat_id=row["chat_id"]
            )
        else:
            request = F02Message(
                reply_id=row["id"],
                provider_uuid=row["provider_uuid"],
                chat_id=row["chat_id"],
                candidate=F02Candidate.model_validate_json(json.dumps(row["frozen_payload"])),
                payload_hash=row["frozen_payload_hash"],
            )
        result: NoticeResult
        try:
            async with asyncio.timeout(10):
                if self.ledger:
                    with self.ledger.scope(SDKScope(request.reply_id, None, "clarification")):
                        result = await self._send(request)
                else:
                    result = await self._send(request)
            result = NoticeResult.model_validate(result.model_dump())
        except Exception:
            result = NoticeResult(outcome="unknown", code="NOTICE_ACK_UNKNOWN")
        await self.session.check()
        async with await open_async(self.session.settings) as db:
            await db.execute(
                """UPDATE business.p4_clarification_replies
                SET status=%s,message_id=%s,last_error=%s WHERE id=%s AND status='sending'
                AND claimed_by=%s AND provider_uuid=%s""",
                (
                    "dead" if result.outcome == "rejected" else result.outcome,
                    result.message_id,
                    None if result.outcome == "sent" else result.code,
                    request.reply_id,
                    self.session.owner,
                    request.provider_uuid,
                ),
            )
            await self.session.check()
        return result.outcome

    async def _send(self, request: ClarificationMessage | F02Message) -> NoticeResult:
        if isinstance(request, F02Message):
            if self.f02_sender is None:
                raise ValueError("F02_SELECTED_REQUESTS_REQUIRE_SENDER")
            return await self.f02_sender.send_f02(request)
        return await self.sender.send_clarification(request)

    async def reconcile(self) -> None:
        await self.recover_unknown()
        await self.dispatch_one()
