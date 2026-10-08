# 架构决策记录

日期：2026-10-08。首次外部架构审核结论为 **有条件通过**：总体方向保留，本稿落实六项审核意见。下列修订仍待最终确认，不表示获准开始 Phase 1；本轮仅提交文档 PR，不改 main、不实现业务或 CI。

## ADR-001：模块化单体、一个主 Agent

问题：需要展示 Agent 工程能力，但首个业务只有一个闭环。决定：单主 Agent 做意图与路由，专用 LangGraph workflow 执行业务；API、Worker、Gateway 是同仓进程。替代：微服务、多 Agent、通用编排平台。取舍：暂不独立扩容每个领域，换取更少部署边界和清晰依赖。重新评估条件：出现多个独立团队或明显不同的扩容/隔离需求。

## ADR-002：PostgreSQL 作为业务权威，队列独立 Worker

问题：任务必须在进程重启后继续，不能只用内存和 HTTP 后台任务。决定：业务表、jobs、outbox 和 checkpoint 使用同一个 PG 实例，schema/职责分开；独立 Worker 轮询。替代：FastAPI BackgroundTasks、Celery/Redis、Temporal。依据：[FastAPI 后台任务](https://fastapi.tiangolo.com/tutorial/background-tasks/)及 [PG 队列锁语义](https://www.postgresql.org/docs/current/sql-select.html)。

修订决定：从 Phase 1 起明确采用单 Worker、全局单 Graph 执行并发，M1/M2 保持，M3 默认沿用；不是实验失败后的备选。用启动互斥拒绝第二实例，确认旧进程终止后恢复。保留持久 jobs、幂等回执、checkpoint 和入站审批 CAS；per-thread 锁、epoch/fencing、多 Worker 接管及 R02–R04 移至 C-EXT。代价是排队时延，换取更小的初始验证范围；达到实际吞吐瓶颈再评审扩展。

## ADR-003：业务事务与 checkpoint 分开，副作用必须幂等

决定：官方 PG checkpointer、相同 thread_id、sync durability；approval/执行/outbox 是显式业务事务。节点提交后重放通过唯一键取回原回执。拒绝“LangGraph 可以恢复，所以副作用恰好一次”的推论。官方 [interrupt 语义](https://reference.langchain.com/python/langgraph/types/interrupt)明确恢复重跑节点。

代价：需要业务与图的恢复协调器；不追求跨 PG/飞书/Woo 的分布式事务。外部未知写入结果允许停在 needs_attention，优先防重复。初始必须测试单执行槽、图版本、真实中断/重启与“业务提交后 checkpoint 前”崩溃；不能因降低并发范围而删掉业务恢复测试。

## ADR-004：P0 执行目标为内部补货工作项

决定：审批后创建 PG 补货项，异步投影 Bitable；Phase 3 加最小完成/关闭操作（ADR-014）。不创建 Woo 销售订单来伪装采购，也不直接增加 stock_quantity。Woo 使用只读测试 key。理由：采购、入库和库存更新不是同一业务行为，当前接口/供应商/权限未定义。

代价：不能展示“一键真实采购”，但能完整展示审批、幂等与失败恢复。以后接采购系统须另建明确的 PurchasePort、权限和结果对账，重新评审。

## ADR-005：审批批准冻结计划，执行前再次检查

决定：审批绑定 plan_id/version/hash、明确 SKU 数量和假设，服务端检查 operator；pending 条件更新保证先有效决定生效。默认 24 小时审批有效期、15 分钟数据新鲜度，执行前重新观测并校验实际权限。实质变化必须新计划重批。

未知在途增加统一合同：原始 null 保留、effective_inbound_units=0；每 SKU 的 required_assumptions 进入 plan_hash。只有“确认在途未知按 0 估算并批准本版本”对应的 `approve_with_assumptions` 才能批准，服务端精确校验 `acknowledged_assumption_keys` 与当前版本、身份、nonce/有效期；普通 approve 返回 ASSUMPTION_ACK_REQUIRED。确认与决定同事务保存，不创建可跨人/版本继承的中间状态。`reject_assumptions` 明确拒绝整个计划；同 actor/版本/语义请求重复返回原决定，冲突不覆盖。PRD 4.1、DATA_MODEL T3、FEISHU 4.1 与 TEST_PLAN A01–A08 共用该合同。

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

## ADR-013：拆分首个可面试版本与完整求职版本

决定：M1（Phase 1–4）以库存 Agent+真实飞书审批为第一目标，Mock 数据、内部工作项生命周期、Base、最小 Web 和恢复演示完整可验收，估算 14–21 工作日。M2 加 Woo 只读与完整 P0 交付，累计 19–28 日；M3 加 P1 日报/动态只读 Tool/RAG 文案，累计 29–43 日，另加外部等待。不能宣称全部功能 4–5 周完成。工期以 ROADMAP 为唯一拆分来源，Phase 1 后重估。

取舍：M1 不展示真实 Woo，却必须展示真实飞书审批及失败恢复。M2 才满足全部 P0 AC，M3 才是完整求职版本；P2 和 C-EXT 不计入上述范围。

## ADR-014：为内部补货项增加最小完成/关闭

决定：Phase 3 增加显式 Web/API resolve，当前同店铺 approver 可带原因将 open 转为 completed/closed。状态、actor/time/reason、请求幂等回执、审计及投影同事务保存；终态不可重开。下一轮同库存池可以创建新 item，但须新分析/新审批；旧 execution 键保留，不能因关闭而再次执行旧计划。

取舍：少量生命周期设计换取可重复业务演示，不做采购、到货确认、真实库存改动、批量任务平台。权限暂沿用 approver，是否另需运营关闭权限留待用户确认。

## ADR-015：P1 展示受限动态只读 Tool 组合

决定：Phase 6 在同一主 Agent 内增加 readonly_inquiry。根据意图选择/组合 read_products/read_orders/read_inventory/reports.read，确定性函数计算数值；执行器限制身份、店铺、参数、4 次 Tool/3 次模型调用及查询范围/时间预算。参见 AGENT_DESIGN 第 9 节及 D01–D05。

取舍：展示动态选择能力，但不提供写工具、SQL/shell/任意 URL，不引入多 Agent；不影响 P0 固定审批和安全写流程。该展示不阻塞 M1，实际 provider 的 tool calling 能力在实施时验证。

## ADR-016：基础 CI 和敏感检查前移到 Phase 1

决定：Phase 1 首批提交建立 PR/main push 的文档检查和敏感扫描，后端骨架出现即加 lint/typecheck、离线测试和真实 PG checkpoint smoke，后续随前端/依赖增长扩展。扫描当前内容与历史、权限只读、无真实业务密钥，并验证合成凭据能触发阻断。

取舍：增加早期配置成本，尽早暴露回归与泄密风险；飞书/Woo 真机验证仍单独留证据。当前文档 PR 不创建 CI 文件或伪称有 CI 结果，平台分支保护未配置时由用户合并前核查。

## 审核意见落实映射

| 外部意见 | 决策 | 主要验收/证据 |
|---|---|---|
| 必须 1：交付范围与工期 | ADR-013 | ROADMAP M1/M2/M3、PRD AC 分层 |
| 必须 2：在途未知显式确认 | ADR-005 | PRD 4.1、T3、卡片 4.1、A01–A08 / AC10 |
| 必须 3：单 Worker/单 Graph | ADR-002/003 | G2、S01–S03；R02–R04 后置 C-EXT |
| 建议 4：工作项关闭 | ADR-014 | T6、C01–C05 / AC11 |
| 建议 5：动态只读 Tool | ADR-015 | Phase 6、D01–D05 |
| 建议 6：早期 CI/敏感检查 | ADR-016 | Phase 1 CI 记录及合成凭据阻断样例 |

## 待评审项

| 项目 | 推荐 | 变更影响 |
|---|---|---|
| 交付范围 | M1 库存+飞书优先，M3 累计 29–43 工作日再加外部等待 | 改变范围需同步阶段与验收，不压缩为全部 4–5 周 |
| P0 执行范围 | 内部补货项创建/完成/关闭与 Base 同步 | 实际采购/库存写入将扩大业务、权限和测试范围 |
| 业务规则 | 先演示 L=3/R=7/S=2，真实参数由用户确认 | 参数进入审批 hash 和规则版本 |
| 在途未知 | 专用确认批准动作，精确绑定当前假设集合与版本 | 若不接受按 0 估算，则此类计划全部阻止执行；可靠在途需数据源 |
| 完成/关闭权限 | 同店铺 approver，原因必填 | 若允许运营独立关闭需修改权限与测试合同 |
| 审批职责 | 一个有效审批决定；角色可兼任 | 四眼原则需另一个真实审批身份 |
| 模型与预算 | 可配置 provider，无默认付费调用 | 需用户提供服务和限额 |

无需用户现在决定普通模块命名、锁字段或重试次数。架构通过后按路线图推进；重要范围或权限变化再提交决策。
