# 官方资料、版本与验证记录

核查日期：2026-10-08（Asia/Shanghai）。这是 Phase 0 的证据索引；推荐设计见各专题文档。以下只列实际读取到的来源，不把搜索摘要或第三方教程当官方能力证明。

## 1. 核查方法与限制

- LangGraph、FastAPI、Next.js、PostgreSQL、Woo 官方站点通过 Web 工具读取；Pydantic 文档跳转到官方新域名后读取。
- 飞书普通 HTML 只返回页面框架；浏览器工具启动失败，Web 工具也不支持 `text/markdown`。页面 HTML 提供了官方 `.md` alternate 地址，随后用 Python 标准库 urllib 成功读取正文。不是只依据页面标题推断内容。
- 查询 PyPI 与 npm 注册表的公开包元数据，记录当时版本；用内存中的 wheel 压缩包静态检查 lark-oapi 1.7.3 的回调注册和 ws 分发代码。未安装/执行该包。
- 只读查看旧项目的具体源码及测试文件，未运行旧测试。工具/环境版本为本地命令结果。
- 没有 Docker daemon、应用凭证、测试店 URL 或模型 key 的运行证据。本轮未执行 LangGraph crash probe、数据库并发实验或真实平台联调。官方文档验证不等于运行验证。

## 2. 核心事实与来源

| ID | 来源 | 已确认事实 / 设计影响 |
|---|---|---|
| L1 | [LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) | interrupt 的可序列化值、固定调用顺序、副作用幂等要求；不能用宽泛异常捕获吞掉中断 |
| L2 | [interrupt API](https://reference.langchain.com/python/langgraph/types/interrupt) | 相同 thread 恢复时节点从头执行，Command 携带 resume 值 |
| L3 | [Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers) | sync/async/exit 持久模式；本项目选 sync，仍需业务幂等 |
| L4 | [Postgres memory](https://docs.langchain.com/oss/python/langgraph/add-memory) | PostgresSaver / AsyncPostgresSaver、单独 checkpoint-postgres 依赖和首次 setup |
| L5 | [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence) | checkpointer 与跨线程 store 不同；内存 saver 不跨进程保留 |
| F1 | [FastAPI BackgroundTasks](https://fastapi.tiangolo.com/tutorial/background-tasks/) | 请求后执行机制；持久业务任务另用 Worker 为本项目架构判断 |
| P1 | [Pydantic strict mode](https://pydantic.dev/docs/validation/latest/concepts/strict_mode/) | 严格校验需要按字段/输入类型配置；金额仍显式 Decimal，不依赖隐式转换 |
| D1 | [PostgreSQL SELECT](https://www.postgresql.org/docs/current/sql-select.html) | SKIP LOCKED 跳过锁定行适合队列，但不是一致分析快照 |
| D2 | [PostgreSQL version policy](https://www.postgresql.org/support/versioning/) | 17 系列仍受支持；建议当前 minor，主版本升级不是原地透明操作 |
| V1 | [pgvector](https://github.com/pgvector/pgvector) | PostgreSQL 扩展支持向量检索，默认 exact；P1 再决定索引 |
| N1 | [Next installation](https://nextjs.org/docs/app/getting-started/installation) | 当前最低 Node 20.9，App Router/React 配套要求；未证明本项目组合构建成功 |
| N2 | [Node releases](https://nodejs.org/en/about/previous-releases) | 当前表格 Node 24 为 LTS、20 为 EOL，项目环境建议 24 |
| W1 | [Woo REST API](https://developer.woocommerce.com/docs/apis/rest-api/) | 管理 REST、分页响应头、错误结构与基本环境条件 |
| W2 | [Woo authentication](https://developer.woocommerce.com/docs/apis/rest-api/authentication) | REST key 权限与用户能力关联；HTTPS 凭据认证方案 |
| W3 | [Woo v3](https://developer.woocommerce.com/docs/apis/rest-api/v3/) | 新集成推荐 `/wp-json/wc/v3/` |
| W4 | [Orders](https://developer.woocommerce.com/docs/apis/rest-api/v3/orders/) | 状态、时间、金额/行项目等字段；不能假设按支付时间过滤可用 |
| W5 | [Products](https://developer.woocommerce.com/docs/apis/rest-api/v3/products/) | manage_stock、stock_quantity 可空、stock_status/backorders 等 |
| W6 | [Order refunds](https://developer.woocommerce.com/docs/apis/rest-api/v3/order-refunds/) | 退款独立资源及订单关联，不可由退款金额推定回库 |
| W7 | [Woo API overview](https://developer.woocommerce.com/docs/apis/) | 管理 REST 与面向顾客的 Store API 区别 |

`durable-execution` 旧路径本轮重定向到 Persistence；具体持久化模式从现行 Checkpointers 页面核实，不照抄旧页面目录或过期示例。

## 3. 飞书官方证据

| ID | 官方正文 | 已确认事项 |
|---|---|---|
| FS1 | [长连接事件](https://open.feishu.cn/document/server-docs/event-subscription-guide/event-subscription-configure-/request-url-configuration-case.md) | 自建应用、无需公网入站地址、3 秒处理、50 连接、集群投递 |
| FS2 | [长连接回调](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/event-subscription-guide/callback-subscription/configure-callback-request-address.md) | 新版回调方案；旧消息卡片回调不支持长连接 |
| FS3 | [Python 处理事件](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/server-side-sdk/python--sdk/handle-events.md) | SDK ws 客户端与事件 handler 配置 |
| FS4 | [Python 处理回调](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/server-side-sdk/python--sdk/handle-callbacks.md) | 新版注册示例；回传参数须为对象，旧回调限制 |
| FS5 | [卡片回传交互](https://open.feishu.cn/document/feishu-cards/card-callback-communication.md) | card.action.trigger、operator 身份、3 秒响应、回调 token 的限时更新 |
| FS6 | [处理卡片回调](https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/handle-card-callbacks.md) | 立即/延时更新与响应规则；不是无限期审批凭证 |
| FS7 | [JSON 2.0 变更](https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/card-json-v2-breaking-changes-release-notes.md) | 客户端 7.20 起支持、共享卡片、body.elements、不兼容属性 |
| FS8 | [接收消息](https://open.feishu.cn/document/server-docs/im-v1/message/events/receive.md) | 私聊和群 @ 的权限，敏感 user_id 额外 scope |
| FS9 | [发送消息](https://open.feishu.cn/document/server-docs/im-v1/message/create.md) | interactive 卡片、uuid 在 1 小时内的去重、可用范围错误 |
| FS10 | [Base 新增](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/create.md) | create scope、UUIDv4 client_token、同表并发冲突和 HTTP 200 内业务错误 |
| FS11 | [Base 更新](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/update.md) | update scope 与字段权限 |
| FS12 | [Base 读取](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/list.md) | 本次核实的 list 权限包括 bitable:app:readonly |
| FS13 | [官方 Python SDK](https://github.com/larksuite/oapi-sdk-python) | lark-oapi 官方来源；底层 API/事件模型可复用 |

卡片回调页概要写 Webhook，与专门回调长连接页面存在表述粒度差异；选择 FS2/FS4 的具体配置说明。未核实内容：个人测试组织的实际可申请权限/配额、客户端和应用发布组合、消息离线补投范围、Base client_token 永久保留保证、超长等待后的卡片更新效果。逐项进入 Phase 1 探针。

官方源码静态核查：仓库 v2_main 当时 SHA 为 `0b9e6e48b74bb4b34462fc67b7e738b27e73e697`；检查 [ws/client.py](https://github.com/larksuite/oapi-sdk-python/blob/0b9e6e48b74bb4b34462fc67b7e738b27e73e697/lark_oapi/ws/client.py)。另外直接读取发布包 `lark_oapi-1.7.3-py3-none-any.whl`，SHA256 为 `c91f00087b7977dc9059ab492e8fe435e1a873863dca1d4e660d2be5b801e4cd`：存在 register_p2_card_action_trigger 和 P2CardActionTriggerResponse；ws EVENT 分发可编码 handler 返回值，旧 CARD 分支直接返回。此为静态证据，未实测网络传输。

## 4. 版本快照与锁定策略

以下是 2026-10-08 查询包注册表返回的版本，不是已安装版本或已通过兼容测试的 lockfile。

| 组件 | 查得版本 | 元数据 / 官方来源 | Phase 1 决策 |
|---|---|---|---|
| langgraph | 1.2.14 | [PyPI](https://pypi.org/pypi/langgraph/json)，发布 2026-10-06，Python≥3.10 | 候选，与 checkpoint 配套试验 |
| langgraph-checkpoint-postgres | 3.1.2 | [PyPI](https://pypi.org/pypi/langgraph-checkpoint-postgres/json)，发布 2026-08-07 | 候选；首次 setup/恢复必须测试 |
| FastAPI | 0.142.4 | [PyPI](https://pypi.org/pypi/fastapi/json)，发布 2026-10-07 | 候选；不因刚发布就盲升全部依赖 |
| Pydantic | 2.13.5 | [PyPI](https://pypi.org/pypi/pydantic/json)，发布 2026-08-28 | v2 契约基线 |
| lark-oapi | 1.7.3 | [版本元数据](https://pypi.org/pypi/lark-oapi/1.7.3/json)，发布 2026-08-19 | 已静态检查，真实回调待测 |
| psycopg | 3.3.6 | [PyPI](https://pypi.org/pypi/psycopg/json) | 验证 pool/async 与 checkpointer |
| SQLAlchemy | 2.1.4 | [PyPI](https://pypi.org/pypi/sqlalchemy/json) | 最新候选；不锁定未经测试的新 minor/major 组合 |
| HTTPX | 0.28.1 | [PyPI](https://pypi.org/pypi/httpx/json) | Woo 网络适配候选 |
| pytest | 9.1.1 | [PyPI](https://pypi.org/pypi/pytest/json) | 需核插件兼容 |
| Next.js | 16.4.0 | [npm](https://registry.npmjs.org/next/latest) | Node≥20.9；项目用 Node 24 LTS |
| React | 19.3.0 | [npm](https://registry.npmjs.org/react/latest) | 需与 Next peerDependencies 一起锁 |
| TypeScript | 7.0.2 | [npm](https://registry.npmjs.org/typescript/latest) | 大版本兼容待 build/typecheck；不默认升级旧项目 |
| Playwright test | 1.64.0 | [npm](https://registry.npmjs.org/@playwright/test/latest) | Node≥20；浏览器版本随锁文件固定 |
| PostgreSQL | 17.11（17 系列当前 minor） | [版本政策](https://www.postgresql.org/support/versioning/) | 项目选支持中的 17 系列；镜像 digest 待验证 |
| pgvector | 未锁定 | [官方仓库](https://github.com/pgvector/pgvector) | P1 再查 release 与 PG 镜像兼容 |

Phase 1 使用项目虚拟环境与容器，解析依赖后提交 uv.lock 和前端 lockfile，固定实际镜像 digest；不得在 README 声称 `latest` 可保证复现。Alembic、模型 SDK、embedding 库等未在本轮全面检查版本，选入时再查官方支持范围。

## 5. 设计推论与验证闸门

“模块化单体、内部补货、PG 队列、RAG 后置”是本项目根据范围做出的架构判断，不是框架强制要求。“能在本地用新版卡片长连接”有官方能力依据，但特定测试组织/锁定版本仍须实际验证。

| 闸门 | 需取得的证据 | 当前状态 |
|---|---|---|
| G1 Docker / 本地环境 | Phase 1：Docker/PG 健康、卷重启、迁移/setup、依赖解析及锁文件 | 未执行；首次检查时 daemon 不可连接 |
| G2 LangGraph Checkpoint | Phase 1：单 Worker/单 Graph、真实 PG interrupt、旧进程终止后的同 thread 恢复、提交后 kill 幂等 | 未执行；多 Worker R02–R04 已移至后续 C-EXT |
| G3 飞书真实回调 | Phase 1：私聊/群 @、新版回调、专用确认/拒绝 action 及确认键往返、身份与延迟、Base 读写 | 无凭证，未执行；正式 AC10 在 Phase 3/4 验证 |
| G4 Woo | 测试店认证、分页、退款/变体/时间与金额样本 | 无测试店，未执行 |
| G5 模型 | 指定 provider 的结构化输出/usage、固定评测 | 无配置，未执行 |

所有闸门安排在架构评审之后；本轮没有用未发生的实验填补不确定性。

首次外部审核后的范围修订以 ROADMAP 为准：G4 Woo 安排 Phase 5/M2；G5 基础模型说明安排 Phase 2/M1，动态 Tool calling 再于 Phase 6 验证。多 Worker 接管与 checkpoint 双写为独立 C-EXT，没有运行证据，也不作为初始闸门。Phase 1 基础 CI/敏感检查属新增实施计划，本轮未配置或运行。

## 6. 本轮文档交付检查

十份指定核心文档及附加 RESEARCH 均已生成，README/AGENTS 本地链接可解析，Markdown 代码围栏成对；无遗留 TODO/TBD 和工具内部引用标识。人工交叉检查了任务/审批/执行状态、审批有效期与数据新鲜度、来源标识及阶段闸门。仅产生 Markdown 和 .gitignore，未生成业务代码、依赖清单或容器配置；Phase 0 首次交付时 Git 为无提交的本地 main，remote 为空。后续 GitHub 接入与审核规范见 [README](../README.md) 和 [AGENTS](../AGENTS.md)，不改变上述技术验证状态。
