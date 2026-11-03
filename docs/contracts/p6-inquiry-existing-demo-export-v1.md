# 从现有 synthetic demo 导出询单配置（无 DB 操作）

2026-11-03。基于 Root `eff02e3` 与独立询单工具 `8d4747f` 的只读核对。
本文只提供配置构造步骤，**未执行导出、未启动任何进程**。原独立空库 CLI 的 namespace、
empty、目录边界保持；不把它串在 m3_daily_demo 后重复初始化账号。

## 当前已确认的映射前提

配置形状可以复用已生成 daily demo.json 中的 shop UUID、原账号和主 Worker，但当前默认
daily shop 的真实映射是 `external_shop_key=daily / timezone=Asia/Taipei`；
固定 inventory-v1 baseline 的映射是 `demo / Asia/Shanghai`，两者 CNY 相同。
来源：原[日报 fixture 构造器](../../tests/test_daily_pg.py) 的 prepare 使用
[metadata](../../tests/test_daily_source.py) 更新 shop；询单
[source](../../backend/src/commerceops/infrastructure/readonly_inquiry_store.py) 按当前 DB shop
严格比较上述字段。只生成 typed 配置不修改这个事实，当前默认 daily UUID 用该 baseline
受理时会返回 SERVICE_UNAVAILABLE/503；不能声称“配置可加载就能同 scope 跑通”。

Root 后续若保持固定 baseline，需在新 owned 组合 demo 中另行准备与原账号授权相符、映射为
demo/Asia/Shanghai 的询单店铺 UUID，账号/session 流程继续真实鉴权。新增授权可能递增
auth_version，浏览器需按实际状态重新登录。不要改写 daily 店铺为 demo 来回切换，这会
破坏原日报已登记来源。本文不执行新增店铺/授权，也不引入新的业务来源或改写 fixture。

## 纯配置导出步骤

下面按 Root 所要求，**原样从现有 daily demo.json 取 shop UUID**，输出可加载的
InquiryDeployment，留作形状核对；它不会修复上节已知的不匹配。实际运行前必须由 Root
解决来源映射并使用有真实权限的目标 UUID，不能放宽 source 校验。

在实际 API/Worker 容器的 `/app` 源码与同 UID 路径视图内，Root 传入本次新 synthetic
demo 绝对目录 TASK_M3_DEMO_DIR。只读取非秘密 demo.json 和固定仓库 synthetic fixture，
不读取 local-login、local-session、WebConfig 或密码文件，不连接 DB、不创建身份/session。

```sh
python - <<'PY'
import json
import os
from pathlib import Path
from uuid import UUID

from commerceops.adapters.commerce.mock import Fixture
from commerceops.infrastructure.readonly_inquiry_config import InquiryDeployment
from commerceops.infrastructure.web_config import private_bytes

directory = Path(os.environ["TASK_M3_DEMO_DIR"])
if not directory.is_absolute() or ".." in directory.parts:
    raise SystemExit("NEW_SYNTHETIC_DEMO_REQUIRED")
summary = json.loads(private_bytes(directory / "demo.json"))
if (summary.get("mode") != "local_synthetic_only"
    or summary.get("model_requests_enabled") is not False
    or summary.get("external_sender_enabled") is not False):
    raise SystemExit("NEW_SYNTHETIC_DEMO_REQUIRED")
shop = UUID(summary["shop_id"])
UUID(summary["organization_id"])
fixture_directory = Path("/app/tests/fixtures/commerce/inventory-v1")
fixture = Fixture.load(fixture_directory, "baseline")
if (fixture.source.shop_id, fixture.source.timezone, fixture.source.currency) != (
    "demo", "Asia/Shanghai", "CNY"
):
    raise SystemExit("FIXED_BASELINE_REQUIRED")
deployment = InquiryDeployment.model_validate_json(json.dumps({
    "schema_version": "p6-inquiry-deployment-v1",
    "shop_id": str(shop),
    "fixture_directory": str(fixture_directory),
    "fixture_case": "baseline",
    "enabled": True,
    "source_kind": "mock",
    "model_mode": "offline_stub",
    "model_requests_enabled": False,
    "external_sender_enabled": False,
}))
target = directory / "inquiry-deployment.json"
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
with os.fdopen(fd, "w") as stream:
    stream.write(deployment.model_dump_json())
print("Typed configuration exported; live source mapping remains a separate check.")
PY
```

此步骤不覆盖已有文件，配置加载仍由原 private reader 核 0600、属主和 no-follow。
若实际源码挂载根不是 `/app`，由 Root 在执行前固定唯一实际路径；API、Worker 必须读同一
fixture 与配置，不能由浏览器/POST 指定目录或外部 source key。

解决来源映射后，API 和**原唯一 Worker**增加同一个
`COMMERCEOPS_M3_INQUIRY_CONFIG_FILE=$TASK_M3_DEMO_DIR/inquiry-deployment.json`，保留原
`COMMERCEOPS_P3_CONFIG_FILE`，无需再次 initialize_p3 或启动另一 Worker；UI 保持 live
并设 `COMMERCEOPS_INQUIRY_UI_ENABLED=true`。当前默认 daily UUID 的业务来源前提尚未满足，
本说明只完成无 DB 配置生成方法，不签收组合 browser 或 E2E。
