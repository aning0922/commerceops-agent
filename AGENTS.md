# 工程约束

- Phase0/Phase1已结案，P1有限真实G1/G2/G3/精确main CI及#23 not_identified/risk_accepted保留；M1设计m1-ui/0.4.1-freeze-rc（18页）已冻结，不追加视觉批次。Phase2 P201–04验收Gate、最终source45db独审5478361118/精确CI38038626351及一次actual DeepSeek解释Gate已由Root核定通过；2026-10-10 17:11候选快照ready_for_phase2_merge，正式main SHA/合后CI/Issue29结案以GitHub实时回执为准，不提前宣称。caffe11770a54135900633edf4db0df5458fd195仅实施基线。A唯一schema/业务/Worker/Graph/API/预算/集成，B组件已普通内部合；完整文法用户批准的一次收口及历史三轮失败/暂停保留。实际provider次数1，local_fault仅offline1，key仅Factory在Root明确窗口读、.env未读，剩余9次不自动继续；自有实际PG/window/ledger保留待Root核收。用户已委托Root全Phase2必要Gate后正常合main，A不自行合；Phase3/飞书扩权/生产未授权。BC只读/有限参数为切片，正式T3/补货/库存/生产auth/前端/M1/40×3/95%/p95/自然故障/wire/长期TTL/G3收到后过滤仍not_run。D1/D30/300h与原目标日期保持、人工H/L not_reported。阶段权威候选与剩余收口见docs/STATUS.md第35节/PHASE2_ACCEPTANCE及Issue29；旧章节为历史，不复活旧未授权标记。
- 工程独立运行；旧项目只读研究，不复制整项目、不依赖旧项目绝对路径。不擅自修改全局开发环境。
- 确定性代码负责金额、统计、库存规则、权限与幂等；LLM 负责意图、解释及受限流程路由。
- PostgreSQL 为业务权威来源。副作用必须有身份校验、审批约束、持久幂等键及失败恢复；不能把 checkpoint 当作副作用事务。
- P0 仅管理内部补货工作项（创建/完成/关闭），不涉及真实采购或库存修改。未经明确人工确认不执行退款、支付、真实订单批量修改或不可逆操作。
- 初始采用单 Worker、全局单 Graph 执行并发；在途未知必须按 PRD 的版本绑定显式确认合同审批，不能以普通批准替代。
- 密钥不入库、不写日志；Mock、模拟审批、真实测试分别标识。区分设计、官方文档验证、源码验证和实际运行证据。
- 按阶段运行必要测试并记录结果；禁止将未执行测试描述为通过。使用中文文档，保留必要技术术语。

## GitHub 与外部审核

- 使用 `aning0922/commerceops-agent` Private 仓库进行版本管理和外部审核；已授权在该仓库提交、推送及创建 PR，不擅自变更可见性或协作者权限。
- 首次将现有 Phase 0 文档提交到无历史的 `main` 并推送供审核，不制造空基线 PR。从下一开发阶段起，每个主要阶段使用独立分支。
- 完成功能、必要测试和文档后提交、推送并创建 PR；描述变更、实际测试结果、风险及未验证事项，等待外部审核。修复审核问题后更新同一 PR。
- 合并进入 `main` 须有用户明确授权。2026-10-08 用户已将 Phase 1 合并裁决委托主控：全部必要 Gate、独立审查和实际 CI 通过后，主控可确认最终阶段 PR 合入 main；其他阶段仍须新授权。禁止强制推送或擅自改写已有提交历史。
- 提交前检查待提交内容及已有 Git 历史中的敏感信息；发现凭据先停止上传并处理，不把删除当前文件当作清理历史。

## Phase 1 主控与交接

- ROADMAP 负责阶段目标/Gate，GitHub Issue/PR 负责任务事实，docs/STATUS.md 负责阶段状态；每次重要交付同步实际测试、依赖、阻塞和 main commit。
- 主控只负责规划、派发、依赖、状态/证据、PR 审核协调及阶段验收，不承担 P1-02–P1-05 主体编码。每项具体开发由独立上下文的执行 Agent 在明确分支和隔离 Worktree 完成；独立 Review Agent 审核冻结 SHA，开发者自检不替代独立审查。子 Agent 默认共享文件系统，须显式隔离 checkout；原 P1-02 顶层会话/Worktree 是唯一实施负责人，禁止重复派发或并写。
- 迁移、业务状态机、Worker/恢复合同和共享锁文件由主控协调单一负责人，避免无协调并行修改。
- P1-02–P1-05 主要实施使用独立顶层 Codex 会话；独立审核与专项检查使用子 Agent。每项交付须有实际测试、精确 SHA 独立审核、CI 与主控集成核对；阶段内依赖可使用已审核/验证的 phase/1-integration commit，main 状态单独记账。PR 创建或代码合并不自动表示真实 Gate 通过；阶段验收后仍须用户另行授权下一 Phase。

## Phase 1 托管执行授权

- 用户已批准最新混合编排方案，并回复“包含 main：全部必要 Gate、独立审查和实际 CI 通过后，由主控确认合入 main；不进入 Phase 2”。范围、门禁及无历史改写迁移见 docs/PHASE1_MANAGED_EXECUTION.md。
- 主控可创建 phase/1-integration、迁移任务 PR base、更新 Issue #3–#7 的阶段内依赖合同，并在全部门禁满足后确认内部合并。最终阶段 PR 只有 G1/G2/G3 全部真实证据、独立审核和最终 CI 通过后才可合入 main；任何 Gate 外部阻塞时不得降低条件。

## 文档索引

[需求](docs/PRD.md) · [架构](docs/ARCHITECTURE.md) · [数据](docs/DATA_MODEL.md) · [Agent](docs/AGENT_DESIGN.md) · [飞书](docs/FEISHU_INTEGRATION.md) · [电商](docs/COMMERCE_INTEGRATION.md) · [测试](docs/TEST_PLAN.md) · [路线图](docs/ROADMAP.md) · [复用](docs/REUSE_AUDIT.md) · [决策](docs/DECISIONS.md) · [调研证据](docs/RESEARCH.md)
