# CommerceOps Agent

电商运营智能体与企业自动化系统。面向 AI Agent / AI 应用 / 企业自动化工程岗位的工程作品，首要场景为库存分析、人工审批与内部补货任务闭环。

**当前阶段：Phase 0 已收口；Phase 1 集中交付。G1/G2 已在集成分支验证，G3 必要真实技术探针证据已独立核对齐备，公开源码/证据已内部集成交付，最终 main 阶段门禁正在完成。G3 的 non@/self-bot 按最小权限的平台非投递边界记录，应用对应过滤分支未真机执行；不宣称正式业务审批、库存闭环或完整求职应用已经完成。main 合并和合后 CI 事实见 [STATUS](docs/STATUS.md) 及最终阶段 [PR #19](https://github.com/aning0922/commerceops-agent/pull/19)。用户已委托主控裁决本阶段合并，不自动进入 Phase 2，见 [执行方案](docs/PHASE1_MANAGED_EXECUTION.md)。**

任务依赖、执行顺序、Gate 证据与阻塞见 [STATUS](docs/STATUS.md)；阶段证据、判定与外部解锁清单见 [验收报告](docs/PHASE1_ACCEPTANCE.md)。实现与实际测试通过独立 PR 交付；主控按用户已委托的 Phase 1 合并门禁裁决；真实 Gate、独立审核和实际 CI 齐备前不确认最终 main 合并。

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

工程底座实际安装、启动和检查命令见 [DEVELOPMENT](docs/DEVELOPMENT.md)。Compose/PG/迁移、持久 Worker 和 Checkpoint 已在集成分支实际验证；当前 main/集成提交及合并证据见 STATUS，不能把另一提交的测试直接算作当前 main 实跑。

Phase 1 已建立基础 CI/敏感检查，继续按依赖验证 Docker/PG、LangGraph Checkpoint、飞书真实回调三个闸门。受限动态只读 Tool 组合展示放在 Phase 6，不改动 P0 写操作流程。

## 版本管理与审核

GitHub 审核仓库：[aning0922/commerceops-agent](https://github.com/aning0922/commerceops-agent)（Private，需要仓库访问权限）。Phase 0 首次提交与修订 PR 保留完整历史；后续阶段使用独立分支和 PR，修复独立审核问题，按当前授权裁决合并。Phase 1 全必要 Gate/审核/CI 通过后的合并裁决已委托主控，具体规范见 [AGENTS.md](AGENTS.md)。每次合并不自动授权进入下一 Phase。

## P1-01 工程底座使用

本任务的本机 liveness 入口、锁文件安装和统一质量检查见 [开发说明](docs/DEVELOPMENT.md)，实际技术运行与保留边界见 [实施证据](docs/P1_01_EVIDENCE.md)。这份底座交付不代表业务、数据库恢复或真实平台 Gate 已通过。
