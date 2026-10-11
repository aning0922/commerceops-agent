"""同唯一Base已有15列表的窄schema读取；不写表/records/消息/权限。"""

import asyncio
from typing import Any

from lark_oapi.api.bitable.v1 import (  # type: ignore[import-untyped]
    ListAppTableFieldRequest,
    ListAppTableRequest,
)

from commerceops.adapters.feishu.business_factory import (
    BusinessSDKFactory,
    private_value,
    response_body,
)
from commerceops.application.feishu_business.contracts import BASE_FIELDS
from commerceops.application.feishu_business.sdk_window import SDKScope


def validate_fields(rows: list[dict[str, Any]]) -> None:
    names = [row.get("field_name") for row in rows]
    if any(type(name) is not str for name in names) or len(set(names)) != len(names):
        raise ValueError("P4_FIELD_NAMES_INVALID")
    if set(names) != set(BASE_FIELDS):
        raise ValueError("P4_FIELD_SET_INVALID")
    for row in rows:
        expected = 2 if row["field_name"] in ("Quantity", "SyncVersion") else 1
        if type(row.get("type")) is not int or row["type"] != expected:
            raise ValueError("P4_FIELD_TYPE_INVALID")


async def metadata_rows(
    client: Any, option: Any, app_token: str, table_id: str | None
) -> list[dict[str, Any]]:
    # 两页共用原10s操作截止，不能每页再申请新的10s。
    async with asyncio.timeout(10):
        return await _metadata_rows(client, option, app_token, table_id)


async def _metadata_rows(
    client: Any, option: Any, app_token: str, table_id: str | None
) -> list[dict[str, Any]]:
    # 最多两页且必须完整，不自动重试；实际SDKledger仍逐method预占原持久cap。
    rows: list[dict[str, Any]] = []
    page_token: str | None = None
    seen: set[str] = set()
    total: int | None = None
    for _ in range(2):
        if table_id is None:
            builder = ListAppTableRequest.builder().app_token(app_token).page_size(100)
            function = client.bitable.v1.app_table.alist
        else:
            builder = (
                ListAppTableFieldRequest.builder()
                .app_token(app_token)
                .table_id(table_id)
                .page_size(100)
                .text_field_as_array(False)
            )
            function = client.bitable.v1.app_table_field.alist
        if page_token is not None:
            builder.page_token(page_token)
        body = response_body(await function(builder.build(), option))
        data = body.get("data")
        if type(data) is not dict:
            raise ValueError("P4_METADATA_INCOMPLETE")
        items, more, size = data.get("items"), data.get("has_more"), data.get("total")
        if (
            type(items) is not list
            or any(type(row) is not dict for row in items)
            or len(items) > 100
            or type(more) is not bool
            or type(size) is not int
            or not 0 <= size <= 200
            or total is not None
            and size != total
            or more
            and not items
        ):
            raise ValueError("P4_METADATA_INCOMPLETE")
        total = size
        rows.extend(items)
        if len(rows) > total:
            raise ValueError("P4_METADATA_INCOMPLETE")
        if not more:
            if len(rows) != total:
                raise ValueError("P4_METADATA_INCOMPLETE")
            return rows
        token = data.get("page_token")
        if type(token) is not str or not token or token in seen:
            raise ValueError("P4_METADATA_INCOMPLETE")
        page_token = token
        seen.add(token)
    raise ValueError("P4_METADATA_INCOMPLETE")


async def preflight(factory: BusinessSDKFactory) -> dict[str, str | int | bool]:
    settings, ledger = factory.settings, factory.ledger
    # 私有定位只在live Factory已认证后读，不从旧env或probe回填。
    await factory.initialize()
    await factory.verify_bot()
    app_token = private_value(settings.base_app_token_file)
    client = factory.business_client()
    with ledger.scope(SDKScope(ledger.window.window_id, None, "preflight")):
        if settings.base_table_id_file is not None:
            table_id = private_value(settings.base_table_id_file)
        else:
            rows = await metadata_rows(client, factory.option, app_token, None)
            matches = [row for row in rows if row.get("name") == settings.base_table_name]
            if len(matches) != 1:
                raise ValueError("P4_TARGET_NOT_UNIQUE")
            selected = matches[0].get("table_id")
            if type(selected) is not str or not selected:
                raise ValueError("P4_TARGET_NOT_UNIQUE")
            table_id = selected
        fields = await metadata_rows(client, factory.option, app_token, table_id)
    validate_fields(fields)
    # 不输出定位/schema原值，不把bot结果当tenant/group/所有成员的API证据。
    return {
        "schema_version": "p4-v1",
        "authentication_observed": True,
        "bot_identity_observed": True,
        "target_unique": True,
        "field_count": len(fields),
        "field_types_valid": True,
        "tenant_verification": "not_run",
        "group_verification": "not_run",
        "member_verification": "not_run",
        "record_reads": 0,
        "record_writes": 0,
        "message_sends": 0,
        "external_sender_enabled": False,
    }
