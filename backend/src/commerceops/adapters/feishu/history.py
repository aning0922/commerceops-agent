"""官方历史 API 的固定两页取回；只复用原 Factory/ledger，失败不重试。"""

from datetime import UTC, datetime
from functools import partial

from lark_oapi.api.im.v1 import ListMessageRequest  # type: ignore[import-untyped]

from commerceops.adapters.feishu.business_factory import BusinessSDKFactory
from commerceops.application.feishu_business.history import (
    ORIGINAL_END,
    ORIGINAL_START,
    HistoryPage,
    HistoryRecoveryRequest,
    page_data,
)
from commerceops.application.feishu_business.sdk_window import SDKScope
from commerceops.infrastructure.feishu_history import HistoryRecoveryStore


async def collect_history(
    factory: BusinessSDKFactory, request: HistoryRecoveryRequest, store: HistoryRecoveryStore
) -> None:
    window = request.window(factory.settings)
    if factory.client is None or factory.ledger.window != window:
        raise PermissionError("HISTORY_FACTORY_BINDING_INVALID")
    token = None
    for _ in range(2):
        builder = (
            ListMessageRequest.builder()
            .container_id_type("chat")
            .container_id(request.chat_id)
            .start_time(str(int(ORIGINAL_START.timestamp())))
            .end_time(str(int(ORIGINAL_END.timestamp())))
            .sort_type("ByCreateTimeAsc")
            .page_size(50)
        )
        if token is not None:
            builder = builder.page_token(token)
        sdk_request = builder.build()
        with factory.ledger.scope(SDKScope(request.recovery_id, None, "history_read")):
            response = await factory.ledger.invoke(
                "im.v1.message.list",
                partial(factory.client.im.v1.message.alist, sdk_request, factory.option),
            )
        raw = getattr(response, "raw", None)
        body = getattr(raw, "content", None)
        if type(body) is not bytes or len(body) > 1024 * 1024:
            raise ValueError("HISTORY_RAW_RESPONSE_UNAVAILABLE")
        status = getattr(raw, "status_code", None)
        page = HistoryPage(body, status if type(status) is int else 0, datetime.now(UTC), token)
        store.observe(request, page)
        data = page_data(request, page)
        if not data["has_more"]:
            return
        next_token = data["page_token"]
        if next_token == token:
            raise ValueError("HISTORY_PAGE_TOKEN_LOOP")
        token = next_token
    raise ValueError("HISTORY_PAGES_INCOMPLETE")
