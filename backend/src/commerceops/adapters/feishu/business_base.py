"""正式 Base SDK 边界与有界完整分页；不读配置、不创建 client、不调度写入。"""

import asyncio
import json
import math
from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager, nullcontext
from types import MappingProxyType
from typing import Any, Literal

from lark_oapi.api.bitable.v1 import (  # type: ignore[import-untyped]
    AppTableRecord,
    CreateAppTableRecordRequest,
    ListAppTableRecordRequest,
    UpdateAppTableRecordRequest,
)

from commerceops.adapters.feishu.projection_contract import (
    BASE_FIELDS,
    ApiReply,
    ItemProjection,
    ProjectionContractError,
    ProjectionRequest,
    ProjectionResult,
    RecordTransport,
    bind_projection_result,
    canonical_uuid,
)
from commerceops.adapters.feishu.projection_rules import (
    WriteOutcome,
    can_update_older,
    readback_rows,
    write_outcome,
)
from commerceops.adapters.feishu.sdk import restrict_sdk_logs
from commerceops.application.feishu_business.contracts import ReadbackDiagnostic


def operation_deadline(deadline: float | None = None) -> float:
    """当前事件循环的绝对截止；调用方可缩短，不能给单次操作加长至 >10s。"""
    now = asyncio.get_running_loop().time()
    if deadline is None:
        return now + 10.0
    if type(deadline) is not float or not math.isfinite(deadline) or deadline > now + 10.0:
        raise ProjectionContractError()
    return deadline


class BusinessRecordSDK:
    def __init__(
        self,
        client: Any,
        *,
        option: Any = None,
        before_update: Callable[[], AbstractAsyncContextManager[None]] | None = None,
    ):
        restrict_sdk_logs()
        self.client, self.option = client, option
        self.before_update = before_update

    @staticmethod
    def _reply(response: Any) -> ApiReply:
        status = getattr(getattr(response, "raw", None), "status_code", None)
        code = getattr(response, "code", None)
        content = getattr(getattr(response, "raw", None), "content", None)
        status = status if type(status) is int else None
        code = code if type(code) is int else None
        if type(content) is bytes and len(content) <= 4 * 1024 * 1024:
            try:
                body = json.loads(content)
                if type(body) is dict and type(body.get("code")) is int and body["code"] == code:
                    data = body.get("data")
                    return ApiReply(status, code, data if type(data) is dict else {})
            except (ValueError, UnicodeError, RecursionError):
                pass
        return ApiReply(status, None)

    async def create(
        self,
        app_token: str,
        table_id: str,
        token: str,
        fields: ItemProjection,
        *,
        deadline: float | None = None,
    ) -> ApiReply:
        deadline = operation_deadline(deadline)
        canonical_uuid(token, v4=True)
        if asyncio.get_running_loop().time() >= deadline:
            return ApiReply(None, None)
        request = (
            CreateAppTableRecordRequest.builder()
            .app_token(app_token)
            .table_id(table_id)
            .client_token(token)
            .ignore_consistency_check(False)
            .request_body(AppTableRecord.builder().fields(fields.fields()).build())
            .build()
        )
        # 1.7.3 Encoder 对 model.__dict__ 递归删 None；普通 dict body 保留显式 null。
        # 继续使用官方 request/鉴权/transport，不修改 SDK 或全局 Encoder。
        request.body = {"fields": fields.fields()}
        try:
            async with asyncio.timeout_at(deadline):
                return self._reply(
                    await self.client.bitable.v1.app_table_record.acreate(request, self.option)
                )
        except Exception:
            return ApiReply(None, None)

    async def list(
        self,
        app_token: str,
        table_id: str,
        page_token: str | None,
        *,
        deadline: float | None = None,
    ) -> ApiReply:
        deadline = operation_deadline(deadline)
        if asyncio.get_running_loop().time() >= deadline:
            return ApiReply(None, None)
        builder = (
            ListAppTableRecordRequest.builder()
            .app_token(app_token)
            .table_id(table_id)
            .page_size(100)
            .field_names(json.dumps(BASE_FIELDS))
            .text_field_as_array(False)
            .automatic_fields(False)
        )
        if page_token is not None:
            builder.page_token(page_token)
        try:
            async with asyncio.timeout_at(deadline):
                return self._reply(
                    await self.client.bitable.v1.app_table_record.alist(
                        builder.build(), self.option
                    )
                )
        except Exception:
            return ApiReply(None, None)

    async def update(
        self,
        app_token: str,
        table_id: str,
        record_id: str,
        fields: ItemProjection,
        *,
        deadline: float | None = None,
    ) -> ApiReply:
        deadline = operation_deadline(deadline)
        if type(record_id) is not str or not record_id:
            raise ProjectionContractError()
        if asyncio.get_running_loop().time() >= deadline:
            return ApiReply(None, None)
        request = (
            UpdateAppTableRecordRequest.builder()
            .app_token(app_token)
            .table_id(table_id)
            .record_id(record_id)
            .ignore_consistency_check(False)
            .request_body(AppTableRecord.builder().fields(fields.fields()).build())
            .build()
        )
        request.body = {"fields": fields.fields()}
        try:
            async with asyncio.timeout_at(deadline):
                async with (
                    self.before_update() if self.before_update is not None else nullcontext()
                ):
                    return self._reply(
                        await self.client.bitable.v1.app_table_record.aupdate(request, self.option)
                    )
        except Exception:
            return ApiReply(None, None)


async def reconcile(
    transport: RecordTransport,
    app_token: str,
    table_id: str,
    request: ProjectionRequest,
    *,
    max_pages: int = 100,
    deadline: float | None = None,
) -> ProjectionResult:
    """全表/十五字段扫描完才恢复原键；最多 100 页/10,000 行，无写请求。"""
    if type(max_pages) is not int or not 1 <= max_pages <= 100:
        raise ProjectionContractError()
    deadline = operation_deadline(deadline)
    rows: list[dict[str, Any]] = []
    cursor: str | None = None
    seen: set[str] = set()
    total: int | None = None

    def incomplete(
        reason: Literal["transport", "envelope", "cursor", "total", "limit"],
    ) -> ProjectionResult:
        return ProjectionResult(
            outcome="unknown",
            code="INCOMPLETE_READBACK",
            diagnostic=ReadbackDiagnostic(stage="pagination", reason=reason),
        )

    for _ in range(max_pages):
        if asyncio.get_running_loop().time() >= deadline:
            return incomplete("limit")
        try:
            async with asyncio.timeout_at(deadline):
                reply = await transport.list(app_token, table_id, cursor, deadline=deadline)
        except Exception:
            return incomplete("transport")
        if asyncio.get_running_loop().time() >= deadline:
            return incomplete("limit")
        items, more = reply.data.get("items"), reply.data.get("has_more")
        observed_total = reply.data.get("total")
        if (
            not reply.success
            or type(items) is not list
            or type(more) is not bool
            or any(type(row) is not dict for row in items)
            or len(items) > 100
            or (more and not items)
        ):
            return incomplete("envelope")
        if (
            type(observed_total) is not int
            or observed_total < 0
            or total is not None
            and total != observed_total
        ):
            return incomplete("total")
        total = observed_total
        rows.extend(items)
        if len(rows) > 10000 or len(rows) > total:
            return incomplete("total")
        if not more:
            if len(rows) != total:
                return incomplete("total")
            return readback_rows(request, rows)
        next_cursor = reply.data.get("page_token")
        if type(next_cursor) is not str or not next_cursor or next_cursor in seen:
            return incomplete("cursor")
        seen.add(next_cursor)
        cursor = next_cursor
    return incomplete("limit")


class _OperationRecords:
    """仅本次调用的方法次数上限；不持久化、不重试、不调度。"""

    def __init__(self, transport: RecordTransport, max_pages: int):
        self.transport, self.max_pages = transport, max_pages
        self.queries = 0
        self.writes = 0

    async def list(
        self,
        app_token: str,
        table_id: str,
        page_token: str | None,
        *,
        deadline: float | None = None,
    ) -> ApiReply:
        if self.queries >= self.max_pages:
            return ApiReply(None, None)
        self.queries += 1
        return await self.transport.list(app_token, table_id, page_token, deadline=deadline)

    async def create(
        self,
        app_token: str,
        table_id: str,
        token: str,
        projection: ItemProjection,
        *,
        deadline: float | None = None,
    ) -> ApiReply:
        if self.writes:
            return ApiReply(None, None)
        self.writes += 1
        return await self.transport.create(
            app_token, table_id, token, projection, deadline=deadline
        )

    async def update(
        self,
        app_token: str,
        table_id: str,
        record_id: str,
        projection: ItemProjection,
        *,
        deadline: float | None = None,
    ) -> ApiReply:
        if self.writes:
            return ApiReply(None, None)
        self.writes += 1
        return await self.transport.update(
            app_token, table_id, record_id, projection, deadline=deadline
        )


class BusinessBaseAdapter:
    """A 唯一 Worker 调用的正式共享接口；一次调用，未持有任何 PG 或调度状态。"""

    def __init__(self, transport: RecordTransport, targets: Mapping[str, tuple[str, str]]):
        if not targets or any(
            type(key) is not str
            or not key
            or type(value) is not tuple
            or len(value) != 2
            or any(type(part) is not str or not part for part in value)
            for key, value in targets.items()
        ):
            raise ProjectionContractError()
        self.transport = transport
        self.targets = MappingProxyType(dict(targets))

    async def project(self, request: ProjectionRequest) -> ProjectionResult:
        # 防止 model_copy/model_construct 绕过共享 DTO；不复制该 DTO 的校验规则。
        try:
            request = ProjectionRequest.model_validate(request.model_dump())
        except ValueError:
            return ProjectionResult(outcome="fatal", code="INVALID_PROJECTION_REQUEST")
        target = self.targets.get(request.target_key)
        if target is None:
            return bind_projection_result(
                request,
                ProjectionResult(
                    outcome="fatal",
                    code="TARGET_NOT_CONFIGURED",
                ),
            )
        deadline = operation_deadline(
            asyncio.get_running_loop().time() + float(request.timeout_seconds)
        )
        try:
            async with asyncio.timeout_at(deadline):
                result = await self._project(request, target, deadline)
        except Exception:
            result = ProjectionResult(outcome="unknown", code="BASE_OPERATION_UNKNOWN")
        return bind_projection_result(request, result)

    async def _project(
        self,
        request: ProjectionRequest,
        target: tuple[str, str],
        deadline: float,
    ) -> ProjectionResult:
        app_token, table_id = target
        records = _OperationRecords(self.transport, request.max_pages)
        before = await reconcile(
            records,
            app_token,
            table_id,
            request,
            max_pages=request.max_pages,
            deadline=deadline,
        )
        if request.operation == "reconcile" or before.outcome in {"verified", "conflict", "stale"}:
            return before
        if request.operation == "create":
            if not (before.code == "ITEM_MISSING" and before.complete):
                return before
        elif not can_update_older(request, before):
            return before
        if records.queries >= records.max_pages:
            return ProjectionResult(outcome="unknown", code="READBACK_BUDGET_EXHAUSTED")
        if asyncio.get_running_loop().time() >= deadline:
            return ProjectionResult(outcome="unknown", code="BASE_DEADLINE_EXCEEDED")
        if request.operation == "create":
            reply = await records.create(
                app_token,
                table_id,
                str(request.client_token),
                request.projection,
                deadline=deadline,
            )
        else:
            if request.external_id is None:
                return ProjectionResult(outcome="fatal", code="INVALID_PROJECTION_REQUEST")
            reply = await records.update(
                app_token, table_id, request.external_id, request.projection, deadline=deadline
            )
        if asyncio.get_running_loop().time() >= deadline:
            return ProjectionResult(outcome="unknown", code="BASE_DEADLINE_EXCEEDED")
        outcome = write_outcome(reply)
        if outcome == WriteOutcome.DEFERRED:
            # 只按具体已知供应商拒绝合同；HTTP429/未知code本身不作无写证明。
            return ProjectionResult(
                outcome="retryable",
                code="BASE_WRITE_REJECTED",
                write_rejected=True,
                retry_after_seconds=1,
            )
        if outcome == WriteOutcome.REJECTED:
            return ProjectionResult(outcome="fatal", code="BASE_REQUEST_REJECTED")
        if outcome == WriteOutcome.CONFLICT:
            return ProjectionResult(outcome="conflict", code="BASE_TOKEN_CONFLICT")
        if outcome != WriteOutcome.ACKNOWLEDGED:
            return ProjectionResult(outcome="unknown", code="BASE_WRITE_UNKNOWN")
        record_id = reply.data["record"]["record_id"]
        if request.external_id is not None and record_id != request.external_id:
            return ProjectionResult(outcome="conflict", code="ACK_RECORD_MISMATCH")
        result = await reconcile(
            records,
            app_token,
            table_id,
            request,
            max_pages=request.max_pages,
            deadline=deadline,
        )
        if result.external_id is not None and result.external_id != record_id:
            return ProjectionResult(outcome="conflict", code="ACK_RECORD_MISMATCH")
        return result
