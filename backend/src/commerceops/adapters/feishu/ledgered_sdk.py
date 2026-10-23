"""只包当前client实例的六个受限SDK方法；无认证/秘密读/全局monkeypatch。"""

from types import SimpleNamespace
from typing import Any

from commerceops.application.feishu_business.sdk_calls import SDKCallLedger, SDKMethod


def ledgered_client(client: Any, ledger: SDKCallLedger) -> Any:
    # 未调用ledger准入前不调用client函数，原request/option不落日志或ledger。
    def wrap(method: SDKMethod, function: Any) -> Any:
        async def invoke(request: Any, option: Any = None) -> Any:
            async def call() -> Any:
                return await function(request, option)

            return await ledger.invoke(method, call)

        return invoke

    records = client.bitable.v1.app_table_record
    return SimpleNamespace(
        im=SimpleNamespace(
            v1=SimpleNamespace(
                message=SimpleNamespace(
                    acreate=wrap("im.v1.message.create", client.im.v1.message.acreate)
                )
            )
        ),
        bitable=SimpleNamespace(
            v1=SimpleNamespace(
                app_table_record=SimpleNamespace(
                    acreate=wrap("bitable.v1.app_table_record.create", records.acreate),
                    alist=wrap("bitable.v1.app_table_record.list", records.alist),
                    aupdate=wrap("bitable.v1.app_table_record.update", records.aupdate),
                ),
                app_table=SimpleNamespace(
                    alist=wrap("bitable.v1.app_table.list", client.bitable.v1.app_table.alist)
                ),
                app_table_field=SimpleNamespace(
                    alist=wrap(
                        "bitable.v1.app_table_field.list", client.bitable.v1.app_table_field.alist
                    )
                ),
            )
        ),
    )
