# CommerceOps Agent

电商运营智能体与企业自动化系统。面向 AI Agent / AI 应用 / 企业自动化工程岗位的工程作品，首要场景为库存分析、人工审批与内部补货任务闭环。

**当前阶段：Phase 0 已完成调研与设计，等待架构评审。尚无业务实现、可运行服务或通过的业务测试。**

推荐方案：Python + FastAPI + Pydantic、LangGraph、PostgreSQL 持久任务队列与独立 Worker、飞书官方 SDK、MockCommerce，随后接入 WooCommerce 测试店铺。Next.js 提供精简操作台；pgvector 和 RAG 延后至 P1。

## 阅读顺序

1. [产品需求与验收](docs/PRD.md)
2. [整体架构](docs/ARCHITECTURE.md) → [核心数据模型](docs/DATA_MODEL.md) → [Agent 与恢复设计](docs/AGENT_DESIGN.md)
3. [飞书集成](docs/FEISHU_INTEGRATION.md)与[电商适配](docs/COMMERCE_INTEGRATION.md)
4. [测试计划](docs/TEST_PLAN.md) → [路线图与外部配置](docs/ROADMAP.md)
5. [复用审计及本地环境](docs/REUSE_AUDIT.md)、[架构决策](docs/DECISIONS.md)、[官方来源与版本核查](docs/RESEARCH.md)

## 评审重点

- P0 的“执行”定义为创建内部补货任务，并投影到飞书多维表格；不代表采购下单、支付或库存已增加。
- PostgreSQL 是业务状态权威来源，LangGraph checkpoint 是工作流进度；两者通过幂等业务命令和恢复协调衔接。
- 飞书使用企业自建应用、新版卡片回调与长连接；真实租户接入仍需 Phase 1 技术验证。
- Mock 数据、受控模型替身和真实测试店数据全程标识；不能用离线测试冒充真实联调。

当前仓库仅有设计文档及基础文件。启动命令、依赖锁文件和 Compose 将在评审通过后的阶段创建。

## 版本管理与审核

GitHub 审核仓库：[aning0922/commerceops-agent](https://github.com/aning0922/commerceops-agent)（Private，需要仓库访问权限）。Phase 0 作为首次 `main` 提交供架构审核；从下一阶段起使用独立分支和 PR，修复外部审核问题，经用户确认后合并。具体规范见 [AGENTS.md](AGENTS.md)。GitHub 接入不代表架构已通过，也不授权开始 Phase 1。
