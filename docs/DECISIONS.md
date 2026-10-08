# 架构决策记录

日期：2026-10-08。所有业务/架构项状态为 **Proposed（推荐，待用户评审）**，不表示用户已批准 Phase 1。环境隔离与文档初始化属于本轮已授权工作。

## ADR-001：模块化单体、一个主 Agent

问题：需要展示 Agent 工程能力，但首个业务只有一个闭环。决定：单主 Agent 做意图与路由，专用 LangGraph workflow 执行业务；API、Worker、Gateway 是同仓进程。替代：微服务、多 Agent、通用编排平台。取舍：暂不独立扩容每个领域，换取更少部署边界和清晰依赖。重新评估条件：出现多个独立团队或明显不同的扩容/隔离需求。

## ADR-002：PostgreSQL 作为业务权威，队列独立 Worker

问题：任务必须在进程重启后继续，不能只用内存和 HTTP 后台任务。决定：业务表、jobs、outbox 和 checkpoint 使用同一个 PG 实例，schema/职责分开；独立 Worker 轮询。替代：FastAPI BackgroundTasks、Celery/Redis、Temporal。依据：[FastAPI 后台任务](https://fastapi.tiangolo.com/tutorial/background-tasks/)及 [PG 队列锁语义](https://www.postgresql.org/docs/current/sql-select.html)。

代价：必须自己实现有限的租约、重试、恢复和监控。边界：不做通用队列框架；若 Phase 1 无法可靠验证租约/checkpoint 单写者，先简化为单 Worker 严格串行，不硬上并发；如规模超出当前目标再评估成熟任务系统。

## ADR-003：业务事务与 checkpoint 分开，副作用必须幂等

决定：官方 PG checkpointer、相同 thread_id、sync durability；approval/执行/outbox 是显式业务事务。节点提交后重放通过唯一键取回原回执。拒绝“LangGraph 可以恢复，所以副作用恰好一次”的推论。官方 [interrupt 语义](https://reference.langchain.com/python/langgraph/types/interrupt)明确恢复重跑节点。

代价：需要业务与图的恢复协调器；不追求跨 PG/飞书/Woo 的分布式事务。外部未知写入结果允许停在 needs_attention，优先防重复。图部署版本和单 thread 并发约束必须测试。

## ADR-004：P0 执行目标为内部补货工作项

决定：审批后创建 PG 补货项，异步投影 Bitable；不创建 Woo 销售订单来伪装采购，也不直接增加 stock_quantity。Woo 使用只读测试 key。理由：采购、入库和库存更新不是同一业务行为，当前接口/供应商/权限未定义。

代价：不能展示“一键真实采购”，但能完整展示审批、幂等与失败恢复。以后接采购系统须另建明确的 PurchasePort、权限和结果对账，重新评审。

## ADR-005：审批批准冻结计划，执行前再次检查

决定：审批绑定 plan_id/version/hash、明确 SKU 数量和假设，服务端检查 operator；pending 条件更新保证先有效决定生效。默认 24 小时审批有效期、15 分钟数据新鲜度，执行前重新观测并校验实际权限。实质变化必须新计划重批。

取舍：可能增加审批次数，避免旧数据/过期权限驱动执行。发起人与审批人可兼任用于个人演示，是否职责分离留给用户业务确认。不能从自然语言“继续”“好的”推断业务批准。

## ADR-006：飞书新版回调优先长连接

决定：企业自建应用、消息 `im.message.receive_v1` 与新版 `card.action.trigger` 分别订阅；不订阅旧回调。官方 [回调长连接文档](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/event-subscription-guide/callback-subscription/configure-callback-request-address.md)明确旧回调不支持、企业自建应用支持。JSON 2.0 另行固定，不能与回调类型混淆。

代价：依赖本地在线和 SDK 行为；Phase 1 必须真机核验。备选为受鉴权 HTTPS 回调，公网入口/隧道另需用户授权；不提前购买服务器。

## ADR-007：多维表格是异步投影

决定：PG 成功提交即内部执行成功，sync 状态独立显示；同 table_id 串行、固定 client_token、外部业务 ID 对账。表格人工改状态不构成审批。依据：[创建记录](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/create.md)的幂等参数与并发写限制。

取舍：可能短暂不同步，但不会因为表格超时重复内部补货。永久 API 幂等期限未确认，必须保留 unknown 与人工处理路径。

## ADR-008：确定性库存规则，模型只做受约束语言任务

决定：固定窗口/订单状态/Decimal/库存公式与版本；程序渲染数字、模型解释与路由；LLM 不接触写权限。P0 用有效下单件数估计需求，退款单列、未知库存不得执行。

代价：启发式不包含季节性、促销弹性、断货造成的被抑制需求；不能宣传预测算法。后续要引入预测，先建立标签、误差评估和业务收益证据。

## ADR-009：Mock 标准端口先行，Woo 只读直接 REST 适配

决定：Mock 与 Woo 共享领域契约，HTTPX 调官方 REST v3，不依赖额外 Woo Python wrapper；冻结证据用于复现，source_mode 全程展示。依据：[Woo 官方 API](https://developer.woocommerce.com/docs/apis/rest-api/)。

取舍：需要少量手工字段映射，换取错误/超时和金额精度的可控性。Mock 不刻意提供真实平台没有的供应链数据；在途等演示字段必须标出假设。

## ADR-010：RAG / pgvector 后置，避免 P0 依赖膨胀

决定：P0 使用版本化本地 SOP；P1 文案才引入 pgvector 与 embedding。小数据先 exact search，必要时再 ANN。理由：库存风险来自结构化订单/库存，不需要向量检索。依据：[pgvector 官方说明](https://github.com/pgvector/pgvector)。

替代：直接迁移 FinDoc 的 Milvus/本地 embedding/PDF 解析链。拒绝原因：业务无需求、启动重、复现成本高。RAG 的召回阈值必须用电商 SOP 样本重评。

## ADR-011：保留 Next.js，但只做薄操作台

决定：前端仅负责输入、报告、审批、轨迹；所有授权/业务执行在 FastAPI/application。以 Node 24 LTS 项目容器为候选，不修改全局 Node。当前 Next 最低 Node 20.9 不代表 Node 20 仍受维护，官方版本表已将 20 标为 EOL。来源：[Next 要求](https://nextjs.org/docs/app/getting-started/installation)、[Node 生命周期](https://nodejs.org/en/about/previous-releases)。

替代：React/Vite 更轻，但切换用户技术基线收益有限，先控制界面范围。如果前端影响主闭环，延后 UI，不另建第二个后端。

## ADR-012：离线可复现与真实集成分开验收

决定：固定 fixtures、clock 和模型替身覆盖 CI；真实飞书、Woo、模型各留证据。缺凭证时显式 skipped，不将模型替身、模拟审批或未执行脚本称为实际成功。

代价：多一层验收记录；收益是作品可信、能够定位外部问题。不开启托管追踪平台为默认依赖，先用 PG 审计与 JSON 日志。

## 待评审项

| 项目 | 推荐 | 变更影响 |
|---|---|---|
| P0 执行范围 | 内部补货项与 Base 同步 | 实际采购/库存写入将扩大业务、权限和测试范围 |
| 业务规则 | 先演示 L=3/R=7/S=2，真实参数由用户确认 | 参数进入审批 hash 和规则版本 |
| 在途未知 | 允许显式假设经人确认；真实执行仍只创建工作项 | 要求可靠在途会新增供应链数据源 |
| 审批职责 | 一个有效审批决定；角色可兼任 | 四眼原则需另一个真实审批身份 |
| 模型与预算 | 可配置 provider，无默认付费调用 | 需用户提供服务和限额 |

无需用户现在决定普通模块命名、锁字段或重试次数。架构通过后按路线图推进；重要范围或权限变化再提交决策。
