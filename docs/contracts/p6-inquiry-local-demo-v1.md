# 询单本地真实 Web / 单 Worker 演示准备单

2026-11-03，基于普通合入的 Root `eff02e3b4c2ba023d09ddde9b4b131720a98fcf6`。
状态：**候选 / OFFLINE_CHECKED / SEED_PG_AND_E2E_NOT_RUN**。Root 已回交组件真实 38 SQL
通过；它不证明本新增 seed/exporter 或 Web/Worker/UI 进程闭环。具体新 owned 对象、UTC
绝对截止、镜像、监听端口、进程 native wait 与保卷清理由 Root 单独登记。

## 已有能力与真实缺项

当前 API、Worker 都消费 `COMMERCEOPS_M3_INQUIRY_CONFIG_FILE`，严格加载
`InquiryDeployment`；真实 SessionStore、HTTP 路由及同一 Composite 单槽已具备。
前端 live 模式还需要 `COMMERCEOPS_INQUIRY_UI_ENABLED=true`，入口 `/inquiries`。

现有日报种子会把同一 shop 的外部标识改为 `daily`、时区改为 Asia/Taipei；询单固定
baseline 要求 `demo`、Asia/Shanghai、CNY。不能把日报种子的 UUID 直接填入询单配置。
此前没有专用询单 seed/export CLI。新增 [m3_inquiry_demo](../../scripts/m3_inquiry_demo.py)
仅补这个缺口：复用已审 `initialize_p3` 创建新的合成 org/shop/principal/identity/credential
及真实 SessionStore 会话，保留种子原 `demo` 映射，导出既有固定 Mock 三文件与配置。
本片不修改共享 API/Worker/database、业务模块、原日报种子或任何旧数据。

## Root 新窗口前提与种子产物

仅限全新数据库名 `m3_inquiry_demo_` 加 1–40 位小写字母/数字/下划线，显式
`COMMERCEOPS_MODE=m3-inquiry-demo`，且 `business.organizations=0`。Root 先在新 owned
pgvector PG 上完成完整线性 0019→0023 迁移、setup-checkpointer、grant-runtime 及实际 revision
核验。owner/runtime 密码均为本次新文件，沿现有 COMMERCEOPS_DB_* 设置，不打印内容。
种子不迁移数据库、不启动 PG、API、Worker 或浏览器。

`TASK_M3_INQUIRY_DIR` 必须是尚不存在的绝对目录，无 `..`/符号链接路径，父目录已存在。
目录创建为 0700、所有新文件创建即 0600；失败保留本次新资源，不自动重试或覆盖。

```sh
export COMMERCEOPS_MODE=m3-inquiry-demo
uv run --frozen --offline python -m scripts.m3_inquiry_demo --directory "$TASK_M3_INQUIRY_DIR" --web-port 3410
```

| 新产物 | 用途 |
|---|---|
| configuration.json、csrf-material、nonce-material | 原真实 WebConfig 和新随机私有材料，runtime DB 连接与密码文件引用 |
| local-login.json | 新 login/password，仅本次 UI/HTTP 驱动读取，禁止打印；没有导出会话 token |
| fixture/datasets.json、manifest.json、goldens.json | 逐字节复制仓库既有合成 fixture，保持原 manifest 校验；仅 baseline 被配置启用 |
| inquiry-deployment.json | typed deployment，内部 shop UUID、绝对 fixture 目录、enabled=true、mock/offline_stub、模型/外发 literal false |
| demo.json | 非秘密 org/shop UUID、两配置路径、commerce 外部标识 demo 与固定来源时间域 |

UUID 来自本次服务端种子；POST 的 shop_id 使用 demo.json 内部 UUID。`demo` 是服务端
Commerce source key，不能替代该 UUID。fixture 时钟仍为 2026-10-08，七个完整店铺自然日
覆盖域保持原样；不改成“当前库存”、不平移窗口制造新来源。API/Worker 须同 UID、相同绝对
路径视图，WebConfig 内的 DB 地址和密码文件引用在两者环境均可达。

## 前台启动形状（本片未执行）

Root 从 demo.json 读取 `organization_id` 赋给 `TASK_M3_ORG`。以下是分别交给 Root
受控父进程的前台命令，使用只包含本次必要配置的环境；不继承其他 demo/source/model/sender
配置。示例 API8000/UI3410；若 Root 换 UI 端口，seed 的 --web-port 与实际端口必须相同。

API：

```sh
export COMMERCEOPS_P3_CONFIG_FILE="$TASK_M3_INQUIRY_DIR/configuration.json"
export COMMERCEOPS_M3_INQUIRY_CONFIG_FILE="$TASK_M3_INQUIRY_DIR/inquiry-deployment.json"
export COMMERCEOPS_HOST=127.0.0.1
export COMMERCEOPS_PORT=8000
uv run --frozen --offline python -m commerceops.entrypoints.api
```

唯一 Worker 带同样两份私配，沿原启动锁、终止确认及 Composite 单槽运行：

```sh
export COMMERCEOPS_MODE=test
uv run --frozen --offline python -m commerceops.entrypoints.worker test-run --organization "$TASK_M3_ORG"
```

Web 使用已安装、锁定的仓库依赖：

```sh
export COMMERCEOPS_UI_MODE=live
export COMMERCEOPS_API_ORIGIN=http://127.0.0.1:8000
export COMMERCEOPS_WEB_TRANSPORT=local_http
export COMMERCEOPS_INQUIRY_UI_ENABLED=true
npm --prefix frontend run dev -- --port 3410
```

真实浏览器在 `http://127.0.0.1:3410/inquiries` 使用本次 local-login.json 登录，获取实际
Cookie/CSRF。种子初始化时的 TestClient 登录不能作为浏览器已登录证据，也没有假身份 resolver。
本独立询单 demo 不登记日报或知识来源；需要组合验收时由 Root 另分店铺/配置，不能在同一个
shop 上互相覆盖 external key/timezone。

## Root 后续最小验收

1. 提交“库存 合成演示商品 100”或“库存 DEMO”，报告上下文留空，记录实际 202、原 key/task。
2. 由唯一 Worker 处理并通过“读取原请求结果”核同记录终态与确定性答案：固定可用库存 20，
   真实结果 model3/tool2/scanned3，并显示本地演示/离线替身及原来源时间。
3. 新请求“销量 DEMO”核 baseline 有效下单件数 70、原七日窗口、SKU与证据引用；不把 fixture
   事实称为真实店铺经营数据。日报 report_id 不可填作此处分析报告上下文。
4. 核未知商品/不支持语句的安全缺证据或澄清，以及原 key 读取、撤权后拒绝、当前 response
   schema。种子初始 technical_fixture 无 job，另记；本次真正任务/job/结果数按实际 SQL 核对。
5. 先停止并 native wait API/UI/Worker，再停新 PG、保卷；端口、进程、容器与网络退出由 Root
   独立核验。若不能完成，保留失败/UNKNOWN，不以组件 SQL38 或离线导出测试代签 E2E。

作者只跑 namespace 拒绝、文件权限、固定 fixture复制/typed 配置加载/拒绝覆盖八项离线测试，
Ruff/format/mypy及文档检查；没有执行 seed、连接 PG、启动服务、访问浏览器、模型或外发。
