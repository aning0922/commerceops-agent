# CommerceOps Agent

电商运营智能体与企业自动化系统。面向 AI Agent / AI 应用 / 企业自动化工程岗位的工程作品，首要场景为库存分析、人工审批与内部补货任务闭环。

**当前阶段：Phase4/M1 持续开发与分层验收中。** Phase0–3 已结案，已核 main 基线为 `9d97c19009d932036809ac3e2638bb68f4b7f765`；当前候选沿 PR43 交付。用户已授权主控继续 Phase4，正式飞书业务闭环、真人和完整 M1 尚未验收；源码、离线、真实 PG、SDK、Web、CI 与 main 的证据分别记账，不能以部分通过签整个阶段。

当前依赖、实际测试、阻塞和合并事实见 [STATUS](docs/STATUS.md)、[Phase4 验收](docs/PHASE4_ACCEPTANCE.md)及 [PR43](https://github.com/aning0922/commerceops-agent/pull/43)。[Phase2](docs/PHASE2_ACCEPTANCE.md)与 [Phase3](docs/PHASE3_ACCEPTANCE.md)保留各自结案和失败历史。D1/D30、原 300h、P4 50h 估计和 18 页 M1 设计冻结不重置，人工工时 not_reported；后续阶段、生产、Woo 与扩权须按主控授权另行安排。

离线 M1 使用现成 [Compose 运行指引](docs/M1_OFFLINE_COMPOSE.md)：新私有目录与新 owned project → prepare → db-init/checkpointer/grant/revision → 一次 m1-seed → API/单 Worker/Web → ready → 新业务 T1/20SKU/完整未知确认/T4/同项 T6 → stop/down no-v。seed 的 technical_fixture 基线不是业务 T1；来源为 Mock、审批 simulated_web、投影 offline_fake、provider disabled。账号只从本次本地受保护文件读取。本文新增 N01 镜像输入后的 clean Compose closure 待精确独审及 Root 独立机器窗口，不预写通过。

收口范围、审核记录、未验证闸门和后续待办见 [PHASE0_CLOSEOUT](docs/PHASE0_CLOSEOUT.md)；归档入口为 [PR #1](https://github.com/aning0922/commerceops-agent/pull/1)。

当前技术栈：Python + FastAPI + Pydantic、LangGraph、PostgreSQL 持久任务队列与独立 Worker、飞书官方 SDK、MockCommerce、Next.js 操作台。WooCommerce 测试店、pgvector 和 RAG 按 ROADMAP 后续范围安排。

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
- 飞书使用企业自建应用、新版卡片回调与长连接；真实租户接入已在 Phase 1 受控技术探针验证，正式业务闭环留待后续阶段。
- Mock 数据、受控模型替身和真实测试店数据全程标识；不能用离线测试冒充真实联调。

工程底座实际安装、启动和检查命令见 [DEVELOPMENT](docs/DEVELOPMENT.md)。Compose/PG/迁移、持久 Worker 和 Checkpoint 已在集成分支实际验证；当前 main/集成提交及合并证据见 STATUS，不能把另一提交的测试直接算作当前 main 实跑。

Phase 1 已建立基础 CI/敏感检查，已完成 Docker/PG、LangGraph Checkpoint、飞书真实回调三个闸门的阶段验证。受限动态只读 Tool 组合展示放在 Phase 6，不改动 P0 写操作流程。

## 版本管理与审核

GitHub 版本与审核仓库：[aning0922/commerceops-agent](https://github.com/aning0922/commerceops-agent)。当前仓库授权、保护和 Hosted Actions 状态见 [STATUS](docs/STATUS.md)与 [AGENTS.md](AGENTS.md)。各阶段保留提交、独审、CI 和失败历史；阶段合并按主控已获授权及实际门禁裁决，每次合并不自动授权下一 Phase。

## P1-01 工程底座使用

本任务的本机 liveness 入口、锁文件安装和统一质量检查见 [开发说明](docs/DEVELOPMENT.md)，实际技术运行与保留边界见 [实施证据](docs/P1_01_EVIDENCE.md)。这份底座交付不代表业务、数据库恢复或真实平台 Gate 已通过。
