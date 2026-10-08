# 复用审计与环境确认

审计日期：2026-10-08。只读研究旧项目；未复制旧代码、未运行旧项目、未安装其依赖，也没有对旧项目做任何写入。下列“可复用”是设计候选，不等于新项目已经实现或通过验证。

## 1. 新工程边界

最初工作目录 `/Users/aipuli/Documents/Projects/CommerceOpsAgent` 为空，`git status` 与 `git rev-parse` 表明不属于 Git 仓库；检查可访问祖先目录未发现适用 AGENTS.md。确认目标同级小写目录不存在后，将这个空目录更名为 `/Users/aipuli/Documents/Projects/commerceops-agent`，按用户要求初始化独立 `main` 仓库。

没有接触其他 Projects 工程内容，没有建立远程或推送，也没有修改全局 Git/语言环境。当前无业务代码。旧工程路径仅用于本审计引用，未来运行不得依赖它。

| 工具 | 实际读到的版本/状态 |
|---|---|
| Python | 3.12.13 |
| uv | 0.11.25 |
| Node | 20.20.1 |
| npm | 10.8.2 |
| Git | 2.50.1（Apple Git-155） |
| Docker CLI | 29.6.2 |
| Docker Compose | v5.3.1 |
| Docker daemon | `docker info` 无法连接；未尝试启动或安装 |
| 搜索工具 | rg 可用 |

本轮未启动数据库、未进行 dependency resolution、未运行容器/业务测试。Node 版本虽满足现行 Next 最低要求，推荐新项目容器使用 24 LTS，见 [调研记录](RESEARCH.md)。

## 2. 旧项目发现范围

只读搜索 Projects 同级目录以及 Documents/Desktop 可访问项目线索，发现 `Documents/AI应用学习/02_项目/findoc-rag`，读取时 HEAD 为 `b805eec`。评估依据为当时工作树具体文件，不保证工作树等同 HEAD。没有在本次搜索范围内发现独立 langgraph-demo 或另外命名的 FinDoc Workflow Agent；不能据此断言整台电脑不存在。

同时看到 learning-lab、private-deploy-report 目录，本次不需要深入研究。Developer/code/projects 等部分候选目录不存在；不阻塞新工程。未读取 `.env` 或敏感凭据。

## 3. 基于源码的复用结论

以下路径相对旧 `findoc-rag` 根，仅为研究索引。

| 分类 | 文件证据 | 实际观察 | 新项目用法 |
|---|---|---|---|
| 可复用设计 | `app/agent/langchain_adapter.py` | StructuredTool 从 registry 的参数 schema 生成，可信上下文由闭包注入 | 保留单一 ToolSpec 定义，不向模型开放 role/tenant |
| 可复用设计 | `app/agent/revenue_confirmation.py:257` | 确认前重读来源并比较 reviewed_snapshot_id；执行计算再核证 | 审批绑定 plan_hash，执行前重新观测关键事实 |
| 可复用设计 | `app/agent/run_service.py` | 将工具参数/结果投影为安全摘要，明确协议/工具/provider 等终态 | 借鉴脱敏日志与错误分类，换成电商状态和 PG |
| 可复用设计 | `app/rag/openai_compatible_llm.py` | 规范化模型结果与安全异常，受控 complete 路径关闭 SDK 重试 | 新适配器保留重试单一责任，补 Token/cost/async 合同 |
| 可复用测试方法 | `tests/test_event_loop_boundary.py` | 用 barrier 对比阻塞工作与 to_thread 对 health 的影响 | 验证 Gateway/API handler 不阻塞及同步 SDK 边界 |
| 可复用测试方法 | `tests/test_revenue_confirmation.py` | 明确 simulated_test 与真实路径区别，实际 SQLite+替身边界写清 | 新测试用真实 PG，保留证据模式与来源变化测试思路 |
| 需要改造 | `app/agent/revenue_graph.py:193–208` | 三个明确节点与条件路由；compile 未传 checkpointer，未见 interrupt/Command | 只能借鉴显式图结构，不能当持久审批恢复成品复用 |
| 需要改造 | `app/rag/evidence_gate.py` | top-1 cosine 阈值只决定可否生成，不证明证据充分 | P1 另建业务 SOP 引用/版本/召回评测，不能直接搬财报阈值 |
| 不建议复用 | `pyproject.toml` | 包含 PDF、MinerU、Milvus、FlagEmbedding、sentence-transformers 等依赖 | 不复制整依赖树；P0 不需要文档重解析或本地大 embedding 模型 |
| 不建议直接搬运 | SQLite run/facts repository、文档生命周期与财务领域 | 库/对象职责面向财报，目标持久层与业务不同 | 重新实现 PG 事务、inbox/outbox、SKU 模型与幂等键 |

未运行旧测试，因此“有测试文件”不等于测试当前通过；本次也没有对其产品成熟度做全面审计。不复制旧 fixture、真实财报、客户数据或本机路径配置。未来若提取小片段，先核实代码权属/许可证，保留必要版权和来源，再用新项目测试验证。

## 4. 开源组件复用

| 组件 | 复用程度 | 理由与成本 |
|---|---|---|
| FastAPI / Pydantic | 直接依赖 | 类型化 API/输入验证；仍需自己实现领域授权与持久任务 |
| LangGraph + checkpoint-postgres | 直接依赖 | 不重写图引擎；必须理解节点重放，不外包业务幂等 |
| PostgreSQL / psycopg / SQLAlchemy / Alembic | 直接依赖 | 同一存储承担业务、队列、checkpoint；保持迁移职责清晰 |
| 飞书 lark-oapi | 直接依赖底层 SDK | 官方事件、token、类型化 API；不采用样例中打印完整事件的日志习惯 |
| HTTPX | 直接依赖 | Woo 少量 API 直连与模型/接口测试边界可控 |
| Next.js / React / TypeScript | 阶段引入 | 用户已选技术；限制 UI 范围避免前后端双业务层 |
| pytest / Playwright | 直接依赖 | 规则与 Web E2E；飞书原生 UI 另有真机记录 |
| pgvector | P1 再依赖 | 小规模 SOP 与 PG 合并存储；先 exact search，数据规模证明需要再建 ANN |
| Celery / Redis / Temporal | 暂不引入 | 当前小规模不值得附加基础设施；如队列可靠性维护失控再评估 |
| Dify / ADK / MCP / 多 Agent 框架 | P2 研究 | 不作为 P0 运行前置，也不构建通用平台 |

官方版本/仓库更新信息可见 [RESEARCH](RESEARCH.md)，但维护活跃不等于所有组合已兼容。Phase 1 应固定版本、记录直接依赖许可证并运行兼容 probe；不用 stars 或“latest”标签代替验证。
