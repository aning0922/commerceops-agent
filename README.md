# CommerceOps Agent

电商运营智能体与企业自动化系统。面向 AI Agent / AI 应用 / 企业自动化工程岗位的工程作品，首要场景为库存分析、人工审批与内部补货任务闭环。

**当前阶段：Phase 0 设计与审核修订已收口并合入 main；Phase 1 主控规划已启动，6 个任务 Issue 已建立，任务实现待授权。尚无业务实现、可运行服务或通过的业务测试。**

任务依赖、执行顺序、Gate 证据与阻塞见 [STATUS](docs/STATUS.md)。本轮只交付规划；不会据此启动业务编码、CI workflow 或真实平台联调。

收口范围、审核记录、未验证闸门和后续待办见 [PHASE0_CLOSEOUT](docs/PHASE0_CLOSEOUT.md)；归档入口为 [PR #1](https://github.com/aning0922/commerceops-agent/pull/1)。

推荐方案：Python + FastAPI + Pydantic、LangGraph、PostgreSQL 持久任务队列与独立 Worker、飞书官方 SDK、MockCommerce，随后接入 WooCommerce 测试店铺。Next.js 提供精简操作台；pgvector 和 RAG 延后至 P1。

第一交付目标是“库存 Agent + 真实飞书审批”。M1 首个可面试版本预计 14–21 工作日；M2 完整 P0 累计 19–28 日；M3 完整求职版本（P0+P1）累计 29–43 日，外部配置与评审等待另计。具体范围及验收见 [ROADMAP](docs/ROADMAP.md)，不承诺全部功能 4–5 周完成。

## 阅读顺序

1. [产品需求与验收](docs/PRD.md)
2. [整体架构](docs/ARCHITECTURE.md) → [核心数据模型](docs/DATA_MODEL.md) → [Agent 与恢复设计](docs/AGENT_DESIGN.md)
3. [飞书集成](docs/FEISHU_INTEGRATION.md)与[电商适配](docs/COMMERCE_INTEGRATION.md)
4. [测试计划](docs/TEST_PLAN.md) → [路线图与外部配置](docs/ROADMAP.md)
5. [复用审计及本地环境](docs/REUSE_AUDIT.md)、[架构决策](docs/DECISIONS.md)、[官方来源与版本核查](docs/RESEARCH.md)

## 评审重点

- P0 的“执行”定义为创建内部补货项，并投影到飞书多维表格；显式完成/关闭操作使下一轮可重新分析审批，不代表采购下单、支付或库存已增加。
- 初始为单 Worker、全局单 Graph；多 Worker 验证单独后置。在途未知需使用绑定当前计划的专用确认批准动作。
- PostgreSQL 是业务状态权威来源，LangGraph checkpoint 是工作流进度；两者通过幂等业务命令和恢复协调衔接。
- 飞书使用企业自建应用、新版卡片回调与长连接；真实租户接入仍需 Phase 1 技术验证。
- Mock 数据、受控模型替身和真实测试店数据全程标识；不能用离线测试冒充真实联调。

当前仓库仅有设计文档及基础文件。启动命令、依赖锁文件和 Compose 将在用户另行授权开发阶段后创建。

Phase 1 任务实现获准后，首批建立基础 CI/敏感检查，尽早验证 Docker、LangGraph Checkpoint、飞书真实回调三个闸门；当前仅规划。受限动态只读 Tool 组合展示放在 Phase 6，不改动 P0 写操作流程。

## 版本管理与审核

GitHub 审核仓库：[aning0922/commerceops-agent](https://github.com/aning0922/commerceops-agent)（Private，需要仓库访问权限）。Phase 0 首次提交与修订 PR 保留完整历史；后续阶段继续使用独立分支和 PR，修复外部审核问题，经用户确认后合并。具体规范见 [AGENTS.md](AGENTS.md)。本次收口不授权开始 Phase 1。
