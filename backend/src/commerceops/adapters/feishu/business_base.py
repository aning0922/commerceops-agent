"""正式 Base SDK 边界与有界完整分页；不读配置、不创建 client、不调度写入。"""

import asyncio
import json
import math
from typing import Any

from lark_oapi.api.bitable.v1 import (  # type: ignore[import-untyped]
    AppTableRecord,
    CreateAppTableRecordRequest,
    ListAppTableRecordRequest,
    UpdateAppTableRecordRequest,
)

from commerceops.adapters.feishu.projection_contract import (
    BASE_FIELDS,
    ApiReply,
    ProjectionContractError,
    ProjectionFields,
    RecordTransport,
    canonical_uuid,
)
from commerceops.adapters.feishu.projection_rules import Readback, ReadbackOutcome, readback_rows
from commerceops.adapters.feishu.sdk import restrict_sdk_logs


def operation_deadline(deadline: float | None = None) -> float:
    """当前事件循环的绝对截止；调用方可缩短，不能给单次操作加长至 >10s。"""
    now = asyncio.get_running_loop().time()
    if deadline is None:
        return now + 10.0
    if type(deadline) is not float or not math.isfinite(deadline) or deadline > now + 10.0:
        raise ProjectionContractError()
    return deadline


class BusinessRecordSDK:
    def __init__(self, client: Any, *, option: Any = None):
        restrict_sdk_logs()
        self.client, self.option = client, option

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
        fields: ProjectionFields,
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
            .request_body(AppTableRecord.builder().fields(fields.wire_fields()).build())
            .build()
        )
        # 1.7.3 Encoder 对 model.__dict__ 递归删 None；普通 dict body 保留显式 null。
        # 继续使用官方 request/鉴权/transport，不修改 SDK 或全局 Encoder。
        request.body = {"fields": fields.wire_fields()}
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
        fields: ProjectionFields,
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
            .request_body(AppTableRecord.builder().fields(fields.wire_fields()).build())
            .build()
        )
        request.body = {"fields": fields.wire_fields()}
        try:
            async with asyncio.timeout_at(deadline):
                return self._reply(
                    await self.client.bitable.v1.app_table_record.aupdate(request, self.option)
                )
        except Exception:
            return ApiReply(None, None)


async def reconcile(
    transport: RecordTransport,
    app_token: str,
    table_id: str,
    fields: ProjectionFields,
    *,
    expected_record_id: str | None = None,
    max_pages: int = 100,
    deadline: float | None = None,
) -> Readback:
    """全表/十五字段扫描完才恢复原键；最多 100 页/10,000 行，无写请求。"""
    if type(max_pages) is not int or not 1 <= max_pages <= 100:
        raise ProjectionContractError()
    deadline = operation_deadline(deadline)
    rows: list[dict[str, Any]] = []
    cursor: str | None = None
    seen: set[str] = set()
    total: int | None = None
    for _ in range(max_pages):
        if asyncio.get_running_loop().time() >= deadline:
            return Readback(ReadbackOutcome.INCOMPLETE)
        try:
            async with asyncio.timeout_at(deadline):
                reply = await transport.list(app_token, table_id, cursor, deadline=deadline)
        except Exception:
            return Readback(ReadbackOutcome.INCOMPLETE)
        if asyncio.get_running_loop().time() >= deadline:
            return Readback(ReadbackOutcome.INCOMPLETE)
        items, more = reply.data.get("items"), reply.data.get("has_more")
        observed_total = reply.data.get("total")
        if (
            not reply.success
            or type(items) is not list
            or type(more) is not bool
            or any(type(row) is not dict for row in items)
            or len(items) > 100
            or (more and not items)
            or type(observed_total) is not int
            or observed_total < 0
            or (total is not None and total != observed_total)
        ):
            return Readback(ReadbackOutcome.INCOMPLETE)
        total = observed_total
        rows.extend(items)
        if len(rows) > 10000 or len(rows) > total:
            return Readback(ReadbackOutcome.INCOMPLETE)
        if not more:
            if len(rows) != total:
                return Readback(ReadbackOutcome.INCOMPLETE)
            return readback_rows(fields, rows, expected_record_id=expected_record_id)
        next_cursor = reply.data.get("page_token")
        if type(next_cursor) is not str or not next_cursor or next_cursor in seen:
            return Readback(ReadbackOutcome.INCOMPLETE)
        seen.add(next_cursor)
        cursor = next_cursor
    return Readback(ReadbackOutcome.INCOMPLETE)
