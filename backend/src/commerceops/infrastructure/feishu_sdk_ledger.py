"""SDK实际方法层账本：持久预占原cap后只调用一次；started孤儿保持unknown。"""

import asyncio
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from commerceops.application.feishu_business.sdk_calls import SDKMethod
from commerceops.application.feishu_business.sdk_window import SDKScope, SDKWindow
from commerceops.infrastructure.worker_lock import WorkerSession, open_async


class PersistentSDKLedger:
    def __init__(self, session: WorkerSession, window: SDKWindow):
        if window.organization_id != session.organization:
            raise ValueError("INVALID_SDK_WINDOW_ORGANIZATION")
        self.session, self.window = session, window
        self.current: ContextVar[SDKScope | None] = ContextVar("p4-sdk-scope", default=None)

    @contextmanager
    def scope(self, scope: SDKScope) -> Iterator[None]:
        token = self.current.set(scope)
        try:
            yield
        finally:
            self.current.reset(token)

    async def authorize_history(self) -> None:
        """历史取回 once 已提交且当前权限成立，才允许 Factory 读取 Secret。"""
        from commerceops.application.feishu_business.history import HISTORY_CAPS

        if dict(self.window.caps) != HISTORY_CAPS or not self.window.enabled:
            raise PermissionError("SDK_HISTORY_CAP_MISMATCH")
        await self.session.check()
        async with await open_async(self.session.settings) as db:
            cur = await db.execute(
                """SELECT 1 FROM business.p4_history_recoveries
                WHERE id=%s AND organization_id=%s AND shop_id=%s
                AND (request->>'expires_at')::timestamptz=%s
                AND business.p4_history_collection_current(id)""",
                (
                    self.window.window_id,
                    self.window.organization_id,
                    self.window.shop_id,
                    self.window.expires_at,
                ),
            )
            if not await cur.fetchone():
                raise PermissionError("SDK_HISTORY_ONCE_CLOSED")

    async def invoke(self, method: SDKMethod, call: Callable[[], Awaitable[Any]]) -> Any:
        scope = self.current.get()
        if scope is None or not self.window.allows(method):
            raise PermissionError("SDK_WINDOW_CLOSED")
        if (
            method == "im.v1.message.list"
            or scope.kind == "history_read"
            or "im.v1.message.list" in self.window.caps
        ):
            await self.authorize_history()
            if not (
                (scope.kind == "history_read" and method == "im.v1.message.list")
                or (
                    scope.kind == "preflight"
                    and method in ("auth.v3.tenant_access_token.internal", "bot.v3.info")
                )
            ):
                raise PermissionError("SDK_HISTORY_METHOD_MISMATCH")
        if scope.kind == "read_reply":
            from commerceops.application.feishu_business.read_reply import READ_REPLY_CAPS

            if dict(self.window.caps) != READ_REPLY_CAPS:
                raise PermissionError("SDK_READ_REPLY_CAP_MISMATCH")
        if scope.kind == "preflight" and method not in (
            "auth.v3.tenant_access_token.internal",
            "bot.v3.info",
            "bitable.v1.app_table.list",
            "bitable.v1.app_table_field.list",
        ):
            raise PermissionError("SDK_PREFLIGHT_WRITE_DENIED")
        if (
            scope.kind in ("approval_card", "task_result", "clarification", "read_reply")
            and method != "im.v1.message.create"
        ):
            raise PermissionError("SDK_IM_METHOD_MISMATCH")
        if scope.kind == "base_projection" and method not in (
            "bitable.v1.app_table_record.create",
            "bitable.v1.app_table_record.list",
            "bitable.v1.app_table_record.update",
        ):
            raise PermissionError("SDK_BASE_METHOD_MISMATCH")
        await self.session.check()
        call_id = uuid4()
        async with await open_async(self.session.settings) as db, db.transaction():
            await db.execute(
                """INSERT INTO business.p4_sdk_windows(id,organization_id,shop_id,
            expires_at,configured_enabled,method_caps,verification_mode)
            VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (
                    self.window.window_id,
                    self.window.organization_id,
                    self.window.shop_id,
                    self.window.expires_at,
                    self.window.enabled,
                    Jsonb(dict(self.window.caps)),
                    self.window.verification_mode,
                ),
            )
            cur = await db.execute(
                "SELECT * FROM business.p4_sdk_windows WHERE id=%s FOR UPDATE",
                (self.window.window_id,),
            )
            original = await cur.fetchone()
            if not original or (
                original["organization_id"],
                original["shop_id"],
                original["expires_at"],
                original["configured_enabled"],
                original["method_caps"],
                original["verification_mode"],
            ) != (
                self.window.organization_id,
                self.window.shop_id,
                self.window.expires_at,
                self.window.enabled,
                dict(self.window.caps),
                self.window.verification_mode,
            ):
                raise PermissionError("SDK_ORIGINAL_WINDOW_MISMATCH")
            cur = await db.execute(
                "SELECT count(*) AS n FROM business.p4_sdk_calls WHERE window_id=%s AND method=%s",
                (self.window.window_id, method),
            )
            count = await cur.fetchone()
            if (
                not count
                or count["n"] >= self.window.caps[method]
                or not self.window.allows(method)
            ):
                raise PermissionError("SDK_METHOD_CAP_EXHAUSTED")
            if scope.kind in ("preflight", "history_read"):
                if scope.subject_id != self.window.window_id:
                    raise PermissionError("SDK_PREFLIGHT_WINDOW_MISMATCH")
            else:
                if scope.kind == "read_reply":
                    cur = await db.execute(
                        """SELECT 1 FROM business.p4_read_replies WHERE id=%s
                        AND organization_id=%s AND shop_id=%s AND task_id=%s
                        AND status='sending' AND attempts=1 AND claimed_by=%s
                        AND NOT EXISTS(SELECT 1 FROM business.p4_sdk_calls c
                            WHERE c.subject_id=business.p4_read_replies.id
                            AND c.scope_kind='read_reply')
                        AND business.p4_read_reply_current(id)""",
                        (
                            scope.subject_id,
                            self.window.organization_id,
                            self.window.shop_id,
                            scope.task_id,
                            self.session.owner,
                        ),
                    )
                elif scope.kind == "clarification":
                    cur = await db.execute(
                        """SELECT 1 FROM business.p4_clarification_replies WHERE id=%s
                        AND organization_id=%s AND shop_id=%s AND status='sending'""",
                        (scope.subject_id, self.window.organization_id, self.window.shop_id),
                    )
                else:
                    operation = "item_projection" if scope.kind == "base_projection" else scope.kind
                    cur = await db.execute(
                        """SELECT 1 FROM business.outbox WHERE id=%s AND organization_id=%s
                        AND shop_id=%s AND task_id=%s AND operation=%s""",
                        (
                            scope.subject_id,
                            self.window.organization_id,
                            self.window.shop_id,
                            scope.task_id,
                            operation,
                        ),
                    )
                if not await cur.fetchone():
                    raise PermissionError("SDK_SUBJECT_SCOPE_MISMATCH")
            await db.execute(
                """INSERT INTO business.p4_sdk_calls(id,window_id,subject_id,
            task_id,scope_kind,method) VALUES(%s,%s,%s,%s,%s,%s)""",
                (
                    call_id,
                    self.window.window_id,
                    scope.subject_id,
                    scope.task_id,
                    scope.kind,
                    method,
                ),
            )
            await self.session.check()
        # committed started是预占/可能调用，不当作已完成wire。异常/取消/PG失败不退预算。
        if not self.window.allows(method):
            await self._finish(call_id, "not_called", None, None)
            raise PermissionError("SDK_WINDOW_CLOSED")
        try:
            budget = min(10.0, (self.window.expires_at - datetime.now(UTC)).total_seconds())
            async with asyncio.timeout(budget):
                result = await call()
        except BaseException:
            await self._finish(call_id, "raised", None, None)
            raise
        raw = getattr(result, "raw", None)
        status, code = getattr(raw, "status_code", None), getattr(result, "code", None)
        await self._finish(
            call_id,
            "returned",
            status if type(status) is int else None,
            code if type(code) is int else None,
        )
        return result

    async def _finish(
        self, identifier: Any, outcome: str, status: int | None, code: int | None
    ) -> None:
        await self.session.check()
        async with await open_async(self.session.settings) as db:
            await db.execute(
                """UPDATE business.p4_sdk_calls SET status=%s,http_status=%s,
            provider_code=%s,completed_at=clock_timestamp() WHERE id=%s AND status='started'""",
                (outcome, status, code, identifier),
            )
        # 不写request/option/raw body/URL/token/record/chat/user ID；业务回执另由同Worker持久。
