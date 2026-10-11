"""受限preflight候选离线：真实SDK request结构/Fake response，无平台/私密配置。"""

import asyncio
import json
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import lark_oapi as lark  # type: ignore[import-untyped]
import pytest
from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.adapters.feishu.business_factory import BusinessSDKFactory, private_value
from commerceops.adapters.feishu.business_preflight import metadata_rows, validate_fields
from commerceops.application.feishu_business.contracts import BASE_FIELDS
from commerceops.application.feishu_business.preflight_window import PreflightWindow
from commerceops.application.feishu_business.sdk_window import SDKWindow
from lark_oapi.core.enum import AccessTokenType  # type: ignore[import-untyped]
from lark_oapi.core.exception import NoAuthorizationException  # type: ignore[import-untyped]
from lark_oapi.core.token import verify  # type: ignore[import-untyped]

pytestmark = pytest.mark.offline


def reply(body: dict[str, Any]) -> Any:
    return SimpleNamespace(
        code=body["code"], raw=SimpleNamespace(status_code=200, content=json.dumps(body).encode())
    )


def fields() -> list[dict[str, Any]]:
    return [
        {"field_name": name, "type": 2 if name in ("Quantity", "SyncVersion") else 1}
        for name in BASE_FIELDS
    ]


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "type", "bool_type", "extra"])
def test_field_schema_cannot_accept_missing_duplicate_wrong_type_or_extra(mutation: str) -> None:
    rows = fields()
    if mutation == "missing":
        rows.pop()
    elif mutation == "duplicate":
        rows.append(dict(rows[0]))
    elif mutation == "extra":
        rows.append({"field_name": "unapproved", "type": 1})
    else:
        rows[0]["type"] = True if mutation == "bool_type" else 7
    with pytest.raises(ValueError):
        validate_fields(rows)
    validate_fields(fields())


@pytest.mark.parametrize("case", ["complete", "repeat", "third_page", "total_changed"])
def test_two_page_metadata_requires_complete_unique_cursor_stable_total(case: str) -> None:
    calls: list[Any] = []

    async def send(request: Any, option: Any) -> Any:
        calls.append(request)
        n = len(calls)
        more = n == 1 or case in ("repeat", "third_page")
        return reply(
            {
                "code": 0,
                "data": {
                    "items": [{"name": "synthetic", "table_id": "synthetic"}],
                    "has_more": more,
                    "page_token": "same" if case == "repeat" else str(n),
                    "total": 3 if case == "third_page" or case == "total_changed" and n == 2 else 2,
                },
            }
        )

    client = SimpleNamespace(
        bitable=SimpleNamespace(
            v1=SimpleNamespace(
                app_table=SimpleNamespace(alist=send),
                app_table_field=SimpleNamespace(alist=send),
            )
        )
    )
    if case == "complete":
        assert len(asyncio.run(metadata_rows(client, object(), "synthetic", None))) == 2
    else:
        with pytest.raises(ValueError, match="P4_METADATA_INCOMPLETE"):
            asyncio.run(metadata_rows(client, object(), "synthetic", None))
    assert len(calls) == 2
    assert all(r.uri == "/open-apis/bitable/v1/apps/:app_token/tables" for r in calls)


def test_private_file_metadata_checked_and_errors_do_not_expose_path_or_contents(
    tmp_path: Path,
) -> None:
    file = tmp_path / "synthetic"
    file.write_text("synthetic value")
    file.chmod(0o600)
    assert private_value(file) == "synthetic value"
    link = tmp_path / "link"
    link.symlink_to(file)
    with pytest.raises(ValueError, match="^P4_PRIVATE_FILE_INVALID$"):
        private_value(link)
    file.chmod(0o644)
    with pytest.raises(ValueError, match="^P4_PRIVATE_FILE_INVALID$"):
        private_value(file)


@pytest.mark.parametrize(
    "name", ["config", "window", "app_secret", "base_token", "table_id", "web_config"]
)
def test_each_preflight_private_input_rejects_symlink_in_parent_before_leaf_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    import os

    directory = tmp_path / "canonical"
    directory.mkdir(mode=0o700)
    file = directory / name
    file.write_text("synthetic-private-value")
    file.chmod(0o600)
    parent = tmp_path / "linked-parent"
    parent.symlink_to(directory, target_is_directory=True)
    opened = []
    original = os.fdopen

    def observe(*args: Any, **kwargs: Any) -> Any:
        opened.append("leaf opened")
        return original(*args, **kwargs)

    monkeypatch.setattr(os, "fdopen", observe)
    with pytest.raises(ValueError, match="^P4_PRIVATE_FILE_INVALID$"):
        private_value(parent / name)
    assert opened == []
    assert private_value(file) == "synthetic-private-value"
    assert opened == ["leaf opened"]


def test_preflight_caps_forbid_writes_extra_auth_and_long_window() -> None:
    spec = {
        "schema_version": "p4-preflight-v1",
        "window_id": str(uuid4()),
        "organization_id": str(uuid4()),
        "shop_id": str(uuid4()),
        "expires_at": (datetime.now(UTC) + timedelta(seconds=60)).isoformat(),
        "caps": {
            "auth.v3.tenant_access_token.internal": 1,
            "bot.v3.info": 1,
            "bitable.v1.app_table_field.list": 2,
        },
    }
    window = PreflightWindow.model_validate_json(json.dumps(spec)).window()
    assert not window.enabled
    for changes in (
        {"caps": {**spec["caps"], "im.v1.message.create": 1}},  # type: ignore[dict-item]
        {"expires_at": (datetime.now(UTC) + timedelta(seconds=180)).isoformat()},
        {"caps": {"auth.v3.tenant_access_token.internal": 2}},
    ):
        with pytest.raises(ValueError):
            PreflightWindow.model_validate_json(json.dumps({**spec, **changes})).window()


def test_factory_explicit_auth_once_and_client_cannot_auto_refresh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = json.loads(Path("docs/contracts/p4-config.example.json").read_text())
    secret = tmp_path / "synthetic-secret"
    secret.write_text("synthetic-app-secret")
    secret.chmod(0o600)
    body["app_secret_file"] = str(secret)
    settings = BusinessSettings.model_validate_json(json.dumps(body))
    window = SDKWindow(
        uuid4(),
        settings.organization_id,
        settings.shop_id,
        datetime.now(UTC) + timedelta(seconds=60),
        {"auth.v3.tenant_access_token.internal": 1, "bot.v3.info": 1},
        enabled=True,
        verification_mode="controlled_sdk",
    )
    methods: list[str] = []

    async def check() -> None:
        pass

    async def invoke(method: str, call: Any) -> Any:
        methods.append(method)
        return await call()

    ledger: Any = SimpleNamespace(
        window=window,
        session=SimpleNamespace(check=check),
        scope=lambda _: nullcontext(),
        invoke=invoke,
    )
    client = lark.Client.builder().app_id(settings.app_id).enable_set_token(True).build()
    builder = lark.Client.builder()
    monkeypatch.setattr(builder, "build", lambda: client)
    monkeypatch.setattr(lark.Client, "builder", lambda: builder)

    async def auth(request: Any) -> Any:
        assert request.token_types == {} and request.body.app_id == settings.app_id
        assert request.uri == "/open-apis/auth/v3/tenant_access_token/internal"
        return reply({"code": 0, "tenant_access_token": "synthetic-token", "expire": 7200})

    async def bot(request: Any, option: Any) -> Any:
        assert request.uri == "/open-apis/bot/v3/info" and option.tenant_access_token
        return reply({"code": 0, "bot": {"open_id": settings.bot_open_id}})

    monkeypatch.setattr(client.auth.v3.tenant_access_token, "ainternal", auth)
    monkeypatch.setattr(client, "arequest", bot)
    factory = BusinessSDKFactory(settings, ledger)

    async def run() -> None:
        await factory.initialize()
        await factory.verify_bot()
        with pytest.raises(PermissionError, match="P4_FACTORY_WINDOW_CLOSED"):
            await factory.initialize()

    asyncio.run(run())
    assert client.config.app_secret is None and client.config.enable_set_token is True
    assert methods == ["auth.v3.tenant_access_token.internal", "bot.v3.info"]
    request = lark.BaseRequest.builder().token_types({AccessTokenType.TENANT}).build()
    with pytest.raises(NoAuthorizationException):
        verify(client.config, request, lark.RequestOption())
    verify(client.config, request, factory.option)
    assert request.token_types == {AccessTokenType.TENANT}
