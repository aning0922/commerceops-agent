"""唯一Worker协调固定澄清回复；发送前持久领取，unknown永久停止自动重发。"""

import asyncio
import json
from typing import Any
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
from commerceops.application.feishu_business.f02_window import F02Window
from commerceops.application.feishu_business.sdk_window import SDKScope
from commerceops.infrastructure.feishu_f02_runtime import trusted_f02_source
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
        f02_window: F02Window | None = None,
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
        self.f02_window = f02_window
        if f02_window is not None and (
            request_ids != frozenset({f02_window.request_id})
            or not controlled_sender
            or ledger is None
            or (
                ledger.window.window_id,
                ledger.window.organization_id,
                ledger.window.shop_id,
                ledger.window.expires_at,
            )
            != (
                f02_window.window_id,
                f02_window.organization_id,
                f02_window.shop_id,
                f02_window.expires_at,
            )
            or dict(ledger.window.caps) != f02_window.method_caps
            or ledger.window.verification_mode != "controlled_sdk"
        ):
            raise ValueError("INVALID_F02_RUNTIME_BINDING")

    async def recover_unknown(self) -> None:
        # WorkerSession.start已核旧PID终止，不能由租约/锁可获猜停止。
        await self.session.check()
        async with await open_async(self.session.settings) as db:
            await db.execute(
                """UPDATE business.p4_clarification_replies
                SET status='unknown',last_error='SEND_ACK_UNPROVEN'
                WHERE organization_id=%s AND status='sending' AND claimed_by<>%s
                AND ((%s::uuid[] IS NULL AND request_id IS NULL) OR request_id=ANY(%s))
                AND (%s::uuid IS NULL OR id=%s)""",
                (
                    self.session.organization,
                    self.session.owner,
                    None if self.request_ids is None else list(self.request_ids),
                    None if self.request_ids is None else list(self.request_ids),
                    None if self.f02_window is None else self.f02_window.reply_id,
                    None if self.f02_window is None else self.f02_window.reply_id,
                ),
            )

    async def pending(self, db: Any) -> Any:
        cur = await db.execute(
            """SELECT r.*,i.app_id,i.tenant_key,i.external_subject,p.auth_version,p.enabled,
                i.provider AS identity_provider
            FROM business.p4_clarification_replies r JOIN business.identities i
            ON i.id=r.identity_id AND i.principal_id=r.principal_id
            AND i.organization_id=r.organization_id JOIN business.principals p
            ON p.id=r.principal_id AND p.organization_id=r.organization_id
            WHERE r.organization_id=%s AND r.status='pending' AND r.attempts=0
            AND ((%s::uuid[] IS NULL AND r.request_id IS NULL) OR r.request_id=ANY(%s))
            AND (%s::uuid IS NULL OR r.id=%s)
            ORDER BY r.created_at,r.id LIMIT 1 FOR UPDATE OF r FOR SHARE OF p,i""",
            (
                self.session.organization,
                None if self.request_ids is None else list(self.request_ids),
                None if self.request_ids is None else list(self.request_ids),
                None if self.f02_window is None else self.f02_window.reply_id,
                None if self.f02_window is None else self.f02_window.reply_id,
            ),
        )
        return await cur.fetchone()

    async def dispatch_one(self) -> str:
        if not self.controlled_sender:
            return "disabled"
        await self.session.check()
        async with await open_async(self.session.settings) as db, db.transaction():
            row = await self.pending(db)
            if not row:
                return "idle"
            try:
                allowed = await self.current_allowed(db, row)
            except (ValueError, TypeError, KeyError):
                if self.f02_window is None:
                    raise
                allowed = False
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

    async def current_allowed(self, db: Any, row: dict[str, Any]) -> bool:
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
            and (row["app_id"], row["tenant_key"]) == (self.policy.app_id, self.policy.tenant_key)
            and row["external_subject"] in self.policy.allowed_open_ids
            and (row["chat_type"] == "p2p" or row["chat_id"] in self.policy.allowed_group_chat_ids)
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
            if self.f02_window is not None:
                try:
                    allowed = (
                        allowed
                        and current is not None
                        and clock is not None
                        and self.f02_window.enabled
                        and clock["t"] < self.f02_window.expires_at
                        and await trusted_f02_source(db, row, current, self.f02_window)
                    )
                except (ValueError, TypeError, KeyError, PermissionError):
                    allowed = False
        return allowed

    async def prepare_selected(self) -> str:
        """与dispatch同选择/同权限/来源谓词，须先于Factory或Secret。"""
        if self.f02_window is None:
            raise ValueError("F02_RUNTIME_SELECTION_REQUIRED")
        await self.session.check()
        async with await open_async(self.session.settings) as db, db.transaction():
            row = await self.pending(db)
            if row is None:
                return "idle"
            try:
                allowed = await self.current_allowed(db, row)
            except (ValueError, TypeError, KeyError):
                allowed = False
            if not allowed:
                await db.execute(
                    "UPDATE business.p4_clarification_replies SET status='dead',"
                    "last_error='CURRENT_PERMISSION_DENIED' WHERE id=%s",
                    (row["id"],),
                )
                return "denied"
            return "ready"

    async def _send(self, request: ClarificationMessage | F02Message) -> NoticeResult:
        if isinstance(request, F02Message):
            if self.f02_sender is None:
                raise ValueError("F02_SELECTED_REQUESTS_REQUIRE_SENDER")
            return await self.f02_sender.send_f02(request)
        return await self.sender.send_clarification(request)

    async def reconcile(self) -> None:
        await self.recover_unknown()
        await self.dispatch_one()
