"""已有App/单Base窄读取Factory；构造无IO，显式窗口内才读私配/认证一次。"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import lark_oapi as lark  # type: ignore[import-untyped]
from lark_oapi.api.auth.v3 import (  # type: ignore[import-untyped]
    InternalTenantAccessTokenRequest,
    InternalTenantAccessTokenRequestBody,
)
from lark_oapi.core.enum import AccessTokenType, HttpMethod  # type: ignore[import-untyped]

from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.adapters.feishu.ledgered_sdk import ledgered_client
from commerceops.adapters.feishu.sdk import restrict_sdk_logs
from commerceops.application.feishu_business.sdk_window import SDKScope
from commerceops.infrastructure.feishu_sdk_ledger import PersistentSDKLedger
from commerceops.infrastructure.web_config import private_bytes


def private_value(path: Path) -> str:
    try:
        body = private_bytes(path)
        if not body:
            raise ValueError
        value = body.decode().strip()
        if not value:
            raise ValueError
        return value
    except Exception:
        raise ValueError("P4_PRIVATE_FILE_INVALID") from None


def response_body(response: Any) -> dict[str, Any]:
    raw = getattr(response, "raw", None)
    status, content = getattr(raw, "status_code", None), getattr(raw, "content", None)
    try:
        if type(status) is not int or not 200 <= status < 300:
            raise ValueError
        if type(content) is not bytes or len(content) > 1024 * 1024:
            raise ValueError
        body = json.loads(content)
        if type(body) is not dict or type(body.get("code")) is not int or body["code"] != 0:
            raise ValueError
        return body
    except Exception:
        raise ValueError("P4_PLATFORM_RESPONSE_INVALID") from None


class BusinessSDKFactory:
    def __init__(self, settings: BusinessSettings, ledger: PersistentSDKLedger):
        window = ledger.window
        if (window.organization_id, window.shop_id) != (
            settings.organization_id,
            settings.shop_id,
        ):
            raise ValueError("P4_FACTORY_SCOPE_MISMATCH")
        self.settings, self.ledger = settings, ledger
        self.client: Any = None
        self.option: Any = None

    async def initialize(self) -> None:
        window = self.ledger.window
        if (
            self.client is not None
            or window.verification_mode != "controlled_sdk"
            or not window.allows("auth.v3.tenant_access_token.internal")
            or window.caps.get("auth.v3.tenant_access_token.internal") != 1
        ):
            raise PermissionError("P4_FACTORY_WINDOW_CLOSED")
        await self.ledger.session.check()
        secret = private_value(self.settings.app_secret_file)
        restrict_sdk_logs()
        # 不设置app_secret/client_assertion/cache，SDK verify缺显式token只会抛异常。
        # 锁定1.7.3的官方arequest/a*均单次Transport.aexecute，无重试/重定向默认。
        client = (
            lark.Client.builder()
            .app_id(self.settings.app_id)
            .enable_set_token(True)
            .timeout(10.0)
            .build()
        )
        request = (
            InternalTenantAccessTokenRequest.builder()
            .request_body(
                InternalTenantAccessTokenRequestBody.builder()
                .app_id(self.settings.app_id)
                .app_secret(secret)
                .build()
            )
            .build()
        )
        with self.ledger.scope(SDKScope(window.window_id, None, "preflight")):
            response = await self.ledger.invoke(
                "auth.v3.tenant_access_token.internal",
                lambda: client.auth.v3.tenant_access_token.ainternal(request),
            )
        body = response_body(response)
        token, lifetime = body.get("tenant_access_token"), body.get("expire")
        if (
            type(token) is not str
            or not token
            or type(lifetime) is not int
            or lifetime <= 60
            or datetime.now(UTC) + timedelta(seconds=lifetime - 60) <= window.expires_at
        ):
            raise ValueError("P4_TOKEN_WINDOW_UNSAFE")
        self.option = lark.RequestOption.builder().tenant_access_token(token).build()
        self.client = client

    def business_client(self) -> Any:
        if self.client is None:
            raise PermissionError("P4_FACTORY_NOT_INITIALIZED")
        return ledgered_client(self.client, self.ledger)

    async def verify_bot(self) -> None:
        if self.client is None:
            raise PermissionError("P4_FACTORY_NOT_INITIALIZED")
        request = (
            lark.BaseRequest.builder()
            .http_method(HttpMethod.GET)
            .uri("/open-apis/bot/v3/info")
            .token_types({AccessTokenType.TENANT})
            .build()
        )
        with self.ledger.scope(SDKScope(self.ledger.window.window_id, None, "preflight")):
            response = await self.ledger.invoke(
                "bot.v3.info", lambda: self.client.arequest(request, self.option)
            )
        body = response_body(response)
        bot = body.get("bot")
        if type(bot) is not dict or bot.get("open_id") != self.settings.bot_open_id:
            raise ValueError("P4_BOT_IDENTITY_MISMATCH")
