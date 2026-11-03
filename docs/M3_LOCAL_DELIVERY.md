# M3 本地功能与配置说明

2026-11-03（台北）。静态说明绑定 Root 普通合入的源码
`6216316f397f987463049e4062d453ff75961b28`。本说明集中描述当前本地装配及已登记组件证据，
不构成 M3 完成、完整验收或发布回执。最终完整门禁由 Root 按实际源码与结果补记。
本次文档任务没有运行检查、测试、PG、API、Worker、浏览器或真实服务。

## 1. 功能与合同入口

| 功能 | 当前本地行为 | 合同与接口依据 |
|---|---|---|
| 日报 | 显式来源绑定、确定性指标与冻结报告；模板追问及脱敏证据分页；配置允许时由原单 Worker 调度与 Fake 投递 | [总合同](contracts/p6-m3-v1.md)、[存储](contracts/p6-daily-storage-v1.md)、[操作](contracts/p6-daily-operations-v1.md)、[原键回执](contracts/p6-daily-receipts-v1.md)、[独立 OpenAPI](contracts/p6-daily-read-v1.openapi.json) |
| 只读询单 | 显式 Mock baseline 配置、受限只读工具与事实/引用；固定 `offline_stub`，真实模型和外发关闭 | [执行器合同](contracts/p6-readonly-inquiry-v1.md)、[只读工具](contracts/p6-readonly-tools-v1.md)、[持久服务](contracts/p6-inquiry-service-v1.md)、[应用接线](contracts/p6-inquiry-application-wiring-v1.md) |
| knowledge/copy | 已登记合成知识与商品来源、固定查询绑定、候选与指定审核人审核；approve 保存内部草稿，reject 不产生草稿 | [知识/文案合同](contracts/p6-knowledge-copy-v1.md)、[存储与审核](contracts/p6-knowledge-storage-v1.md)、[精确接线](contracts/p6-knowledge-wiring-v1.md)、[主应用接线](contracts/p6-copy-application-wiring-v1.md)、[独立 OpenAPI](contracts/p6-copy-web-v1.openapi.json) |

上述合同包含各自记录时点的候选、失败与 pending；当前组件证据仅按
[托管计划“本地组件核收、应用接线与完整门禁准备”](plans/M3_MANAGED_DEVELOPMENT.md#本地组件核收应用接线与完整门禁准备2026-11-03)
归并于第 6 节，不用后续局部结果改写历史整批结果。

## 2. 主 API 与唯一 Worker

实际入口是 [api.py](../backend/src/commerceops/entrypoints/api.py)、
[worker.py](../backend/src/commerceops/entrypoints/worker.py) 与
[database.py](../backend/src/commerceops/entrypoints/database.py)。以下仅为命令形状与配置关系，
本说明不启动进程或增加运行窗口。

主 API：`uv run --frozen --offline python -m commerceops.entrypoints.api`。
原 Web/session 配置入口为 `COMMERCEOPS_P3_CONFIG_FILE`；日报、询单和 copy 复用当前身份、
Origin/CSRF 与服务端权限边界，各自导出独立 OpenAPI，旧公开合同保持隔离。

| 配置项 | 实际消费方式 |
|---|---|
| `COMMERCEOPS_M3_DAILY_CONFIG_FILE` | API 与 Worker 加载 `DailyDeployment`；API 在原 Web 配置装配中启用日报；Worker 注册日报/模板追问。schedule/Fake 是否开启继续由该配置的显式布尔值决定 |
| `COMMERCEOPS_M3_INQUIRY_CONFIG_FILE` | API 与同一 Worker 加载 `InquiryDeployment`；需要原 Web 配置，`enabled` 默认 false；内部 shop UUID、绝对 fixture 目录、`baseline`、`offline_stub` 受严格校验 |
| `COMMERCEOPS_M3_COPY_ENABLED` | API 只接受字面 `true` 或 `false`，默认 false；true 必须有原 Web 配置 |
| `COMMERCEOPS_M3_COPY_CONFIG_FILE` / `COMMERCEOPS_M3_COPY_CONFIG_SHA256` | copy 开启时显式加载并核对完整文件摘要及逐查询语义摘要；关闭时不读取 copy 文件 |

唯一 Worker 命令形状为：

```sh
COMMERCEOPS_MODE=test uv run --frozen --offline python -m commerceops.entrypoints.worker test-run --organization "$TASK_M3_ORG"
```

同一 API/Worker 使用同源 Web、日报与询单配置；Worker 持有原 organization 唯一锁，
在原 `InventoryCompositeRunner` 串行槽内消费任务，保留原 termination gate。
没有第二 Worker、独立 cron 或并行 Graph。copy 当前是同步有限的 PG 检索、模板重建与人工审核保存，
不向 Worker 注册空 runner、模型任务或发布 outbox。

实际数据库 owner 的初始化顺序是迁移、checkpointer 初始化、原 runtime grant，再按需显式授予 knowledge/copy：

```sh
uv run --frozen --offline python -m commerceops.entrypoints.database grant-knowledge-copy-runtime
```

这是实际存在的独立 CLI action，转交既有窄权限 helper；普通 `grant-runtime` 不隐式打开 copy 写权限，
有表或已迁移也不等于已授权/启用。runtime 权限与 owner 登记职责仍按合同分离。
这里不增加秘密配置、真实资料输入或自动授权步骤。

## 3. 固定 pgvector 扩展与诊断旗标

[本地 runtime 合同](contracts/p6-local-runtime-v1.md)、[README 本地 PG 说明](../README.md)、
[compose.m3.yml](../compose.m3.yml) 与 [m3_pgvector.py](../scripts/m3_pgvector.py)
规定 PG17.11 + pgvector0.8.7。override 只替换原 `postgres` 的 image/build，
固定 tag 为 `commerceops-m3-pgvector:8ee1df0-v1`，Dockerfile 为
`infrastructure/knowledge_pgvector.Dockerfile`；stock Compose 与 M2 备份合同保持。

在 Root 登记的新 owned 对象与同一个绝对 UTC 截止内，实际命令形状为：

```sh
uv run --frozen python -m scripts.m3_pgvector --stop-at-utc "$COMMERCEOPS_M3_STOP_AT_UTC"
uv run --frozen python -m scripts.pg_diagnostic --session initial --round 1 --combined --full-smoke --m3-pgvector --deadline "$COMMERCEOPS_M3_STOP_AT_UTC"
```

准备入口没有 `prepare` 子命令；`--m3-pgvector` 是现有诊断器实际旗标。
准备阶段只显式构建、校验并绑定 source commit/tree、构建输入、native 架构和 image ID，
不启动 PG，也不证明 SQL extension 已安装。现有 receipt 拒绝覆盖，源码变化不能复用旧来源绑定。

Compose 文件顺序固定为 `compose.yml`、`compose.m3.yml`、最后才是本次私有 port overlay；
M3 启动禁止隐式 build/pull。应用就绪仍需实际迁移/checkpointer/授权及 revision/extension 核验，
不由 health 或 `pg_isready` 推定。标准 PG helper 按原 ephemeral 合同删除其新测试卷；
private diagnostic 的保卷记录单列，不碰旧卷，不把两种清理策略混记。

## 4. UI 公开开关与两店铺来源绑定

实际公开开关来自 [前端页面入口](../frontend/app/[[...path]]/page.tsx)：

| 名称 | 本地取值与作用 |
|---|---|
| `COMMERCEOPS_UI_MODE` | `live`，使用主 API |
| `COMMERCEOPS_API_ORIGIN` | 本次登记 API origin，例如 `http://127.0.0.1:8000`；不能含凭据、路径或尾随斜杠 |
| `COMMERCEOPS_WEB_TRANSPORT` | `local_http`，只允许 loopback HTTP；来源与 WebConfig 的允许 Origin 须一致 |
| `COMMERCEOPS_INQUIRY_UI_ENABLED` | 字面 `true` 才展示询单入口 |
| `COMMERCEOPS_COPY_UI_ENABLED` | 字面 `true` 才展示 copy 入口 |

UI 开关只控制展示，不替代后端显式配置、owner grant 或当前服务端授权。
日报按 capabilities/source 显示可用状态；询单内部 shop UUID 与 commerce external key 分开处理。

合成本地演示需要明确区分两个 shop：

| 来源 | 绑定要求 | 当前证据边界 |
|---|---|---|
| 日报原 shop | external key=`daily`，timezone=`Asia/Taipei`；日报 metadata、manifest、digest 与 `DailyDeployment` 绑定一致 | `m3_daily_demo` 复用 `tests/test_daily_pg.py::prepare`，将原技术 shop 改为日报来源 |
| copy/询单另一个 Mock baseline shop | external key=`demo`，timezone=`Asia/Shanghai`，原技术 baseline 的 config_ref=`technical_fixture`；独立内部 shop UUID | copy exporter 要求 fresh synthetic `demo` shop；询单核 adapter/environment、external key、currency、timezone 与 baseline fixture 一致。第二 shop 的登记/seed 实跑尚未核收 |

两店铺属于同一新合成 organization，复用同一个原 Web 账号，并在两店铺显式登记相应 scope 与
operator/approver role grant；已有 org 角色不能代替 shop scope。不能把日报 shop UUID 直接传入 copy
exporter，也不能把日报来源改回 baseline 或放宽来源校验来凑闭环。

静态依据为 [日报种子](../scripts/m3_daily_demo.py)、[日报 fixture](../tests/test_daily_pg.py)、
[原技术 fixture](../tests/pg_support.py)、[库存 fixture](../tests/inventory_support.py)、
[copy exporter](../scripts/m3_copy_demo.py) 与
[询单 source 校验](../backend/src/commerceops/infrastructure/readonly_inquiry_store.py)。
copy exporter 只在 owner COMMIT 后逐文件独占写入/fsync；不是三文件整体原子发布。
导出失败可能留下登记与部分文件，须保留核实，不自动重试。完整两店铺 seed、登记/导出与应用组合仍待 Root 实测。

## 5. UNKNOWN、内部草稿与外发边界

日报创建/追问以及 copy 创建/审核在传输结果未知时保留原 operation、request_key、shop、hash 与原引用，
只通过各合同固定 GET 查询原键。404/缺行不能证明事务已回滚；503 或 DB 不可读继续 UNKNOWN。
恢复身份后仍查原键，不自动 POST、不换 key、不把当前修改表单套入原回执。
UI 的 sessionStorage 仅当前 tab 恢复，不构成服务端保存或跨设备恢复证明。

询单失败不披露 facts/claims/refs/options；允许显示的计数只代表本次已知 attempt 用量，
历史尝试用量仍 UNKNOWN。日报 Fake 的 sent 只指 PG Fake receiver 回执；reply 丢失或遗留 sending
按合同保留 unknown，不换 key/正文/目标再发。报告完成与投递状态分列。

copy approve 仅保存内部草稿，不发布；其前端不能独立重算浮点候选 hash 或向量排名。
本地配置中的真实 provider/model/embedding、publication 与 external sender 保持关闭。
真实 SOP、商品资料、真实账号/平台与秘密配置不由本说明引入。

## 6. 已登记组件证据及完整门禁边界

以下仅转述托管计划最新上述段落的组件记录，source 不向当前文档树或其他 worktree 转签。

| 组件 | 精确来源与已登记结果 | 限定 |
|---|---|---|
| K2 | `b828c6f0993550e899760c9a836f6ee848538ae6`：新 owned 30 passed/47.75s，native/outer0，cleanup0，容器网络0/保留新卷1 | 只签本地 synthetic SQL 组件 |
| 询单主应用/早期组合 | 接线 `1d5d1bb` 已独审；Core `8748e326f73a293674f26ed9445e362ca7ac2a81`：38 询单 callpass、16 日报 callpass；整批 95 为55pass/11fail/29setup错误，outer1 | 保留整批失败，不称整批通过 |
| K3 | `8933f85ba2c121dd25892947d1dd19a02305ade6`：29 passed/61.99s，native/outer0，cleanup0，容器网络0/新卷1保留 | 使用旧固定镜像4eb，不转签后续标准镜像 SQL；前批28pass/1fail及原setup错误保留 |
| S3 标准镜像组件 | `eff02e3b4c2ba023d09ddde9b4b131720a98fcf6`：显式 `--m3-pgvector`，升级0023/初始化0、legacy79 collect；operations12passed/26.25s、receipts2passed/7.13s，native/outer0，cleanup0/stopping true，独立容器网络卷0 | 标准 helper 删除本次新卷；不签完整旧回归 |
| 固定扩展准备 | 入口 `0e94d3f` 已审；`3a4f90c` 首次 prepare 成功，arm64 image `94630f25cd59b9b2bfc1fbfe5d630b71f38122e9d52701c27b29c6ecca639a03` | native arm64；新 source 须重新绑定，amd64/Hosted NOT_RUN |
| copy 主 API | `1e30c9994c2d9f034ce516d0d5453f4dac165150` 独审接受，独立30offline/四开关边界通过；正确 docs 检查132files/errors0 | 原误用不存在检查入口且末commit掩盖退出的失败保留；不等于真实组合通过 |
| 显式 owner grant + API 单例组合 | validation `42af9ab3f4a13aa018a89ff8f120c767b9ed2183`：标准 image946，1passed/4.04s；K3 INSERT=false→owner CLI→true，真实session/CSRF/创建→原键GET→approve→receipt，1candidate/1decision/1draft/outbox0，cleanup/native/outer0 | 只签该组合用例；先前202误期望200的HOLD保留 |
| UI / schema 准备 | 询单`128e43d`、S3只读`dbdc16c`、日报写`cfd620c`、copy审核`cc7e646` 已审合入；head测试`85ba0b4`已审，精确75business+4CP=79、68PG仅collect | 新 UI 实际浏览器/真实 API 组合待；旧 UI_FIXTURE/zoom 不代签 |
| 敏感扫描与 exporter | `ac6edf` 树实际扫描 native1：dir/index各15blocking、history156总/20精确已审/136blocking；exporter `a9e3dc1` 已独审准备通过 | 候选豁免独审与实际重扫尚待；实际登记/导出未完成 |

当前完整工程检查、同源完整 PG（含旧回归）、完整 Web/浏览器组合与最终集成核收均 **pending**；
Hosted/amd64、真实 SOP/商品许可、真实 provider/embedding/model、实际 sender/发布及人工质量验收均 **NOT_RUN**。
组件测试、collect、静态接线、Fake 或局部组合不抵扣这些门禁。Root 后续按实际冻结源码、运行与清理回执
统一补最终结果；所有旧失败、UNKNOWN、NOT_CAPTURED、未跑项、预算与账本继续保留。
