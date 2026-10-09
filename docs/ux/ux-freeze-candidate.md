# M1 UX 设计冻结候选与前端交接

**状态：中断草稿，未就绪；最终Viewer/命名版本/刷新回读未完成。**

候选：`m1-ui/0.4.0-b3`，C1 合同 `0.2.1-c1-revision`。用户在 2026-10-09（Asia/Shanghai）确认 B2 外部产品与交互评审通过并授权 B3。**这是设计冻结候选，不是业务 Gate 或正式冻结结论；最终评审及用户合并确认尚未取得。**

本轮沿用原 UX 工作树、分支 `codex/ux-penpot-toolchain`、[PR #24](https://github.com/aning0922/commerceops-agent/pull/24) 和正式 Penpot file `7fd0f7d0-fdda-81c5-8008-c340d1377488`。主 Page `7fd0f7d0-fdda-81c5-8008-c340d1377489`；Foundations 与状态 Page 沿用原 UUID。基线 head `38b3e2578bf0dd4c1e509dabddf4e0a8320f8ee4`，main `a0d521ed79505287fa61bb6ddf82640e97824257`。后端、Phase 1 状态及共享锁文件不在本次变更范围。

## 1. 交接材料与使用顺序

1. [C1 产品合同](c1-product-design.md)、[修订决策](c1-decisions.md)是产品语义依据。
2. [screens.yaml](screens.yaml)定义 18 个逻辑页面/辅助层、角色、状态和数据边界；一个逻辑页面可以对应多个布局/局部面板 UUID。
3. [interactions.yaml](interactions.yaml)定义 B01–B47 / E01–E47；B09 历史保留但不可渲染，不接通用恢复动作。
4. 当前原生 UUID、控件所属页面及实际 navigation/overlay 目标以本批回读映射为准；历史 B1/B2 证据不能冒充 B3 的保存后回读或实点结果。
5. 本文件规定 Next.js 组件、数据需求和待确认协议；所有业务 implementation 仍为 `not_implemented`。

## 2. 页面、路由、组件与数据

路径是前端设计候选。方括号表示 Next.js 动态 segment；不能据此创建未确认 API、数据库枚举或迁移。

| ID | Next.js 路由 / 放置位置 | 建议组件与复用 | 最小数据需求 | 合同 |
|---|---|---|---|---|
| S01 | `/login` | LoginForm、SessionBoundary | 会话建立、当前 principal；原型身份选择器仅评审 | BC01/05 |
| S02 | `/tasks` | AppShell、TaskList、ReadState、NewAnalysisDrawer | 有权 task 列表、范围、分页/筛选及实际计数 | BC01/05 |
| S09 | `/tasks/[taskId]` | TaskContext、BusinessStatus、RelatedResults | task 状态；report/approval/execution/item/sync 各自事实与链接 | BC01/02/03/05 |
| S03 | `/tasks/[taskId]/report?version=…` | FrozenReport、SkuFactRow、RiskDisclosure、VersionHistory | report/snapshot/plan 的冻结版本、全部 SKU、公式与来源/时间 | BC01/05/07 |
| S04 | `/approvals/[approvalId]` | ApprovalDisclosure、DecisionActions、RequestReceipt | 当前及历史 approval、全量计划、精确假设集合、hash/nonce、期限与 eligible | BC01/05/06/07 |
| S10 | `/approvals` | ApprovalList、ReadState | 待我处理 / 历史；服务端 eligible 与范围过滤 | BC01/05 |
| S05 | `/replenishment-items` | InternalItemList、SyncStatus | 内部项与独立同步事实，不显示采购/库存已变更 | BC01/05 |
| S11 | `/replenishment-items/[itemId]` | InternalItemDetail、ReasonDialog、SourceLinks | 状态、数量、来源、expected version、原因记录与同步状态 | BC01/05 |
| S06 | `/tasks/[taskId]/events` | BusinessTimeline、TechnicalDetails、RecoveryFacts | 默认业务步骤；按需展开节点/Tool/时间/Token/Checkpoint/恢复记录 | BC01/04/05 |
| S07 | `/access` | AccessBoundary、SessionExpired | 不透露对象是否存在、编号、SKU 或计数的安全反馈 | BC01/05 |
| S08 | `/admin/operations` | AppShell、ReadOnlyConfigSummary、ExceptionExplanation | 脱敏运行元信息、规则/模型版本、实际期限/新鲜度、既有恢复状态 | BC01/04/05/07 |
| M01 | S11 Dialog | ReasonDialog、VersionSummary | 单项 complete/close、必填原因、原请求键与 payload、版本 | BC01/05 |
| M02 | S02 Drawer；新周期仅开草稿 | NewAnalysisDraft、ParameterSummary | 提交前本地输入/确认；没有 task_id、不占 Worker、不继承批准 | BC01/02/03/05 |
| M03 | S03 Dialog | ProvenanceDialog | 当前指定 report 的口径、公式、数据来源 | BC01/05 |
| M04 | S03 Drawer，窄屏整页呈现 | ReportExplanation、ReadState、TemplateFallback | 指定 report_id/version 的已有冻结上下文、依据与安全错误 | BC01/05 |
| M05 | S03/S09 局部 Dialog | ReanalysisImpactPreview | 原 task/plan/approval/execution 状态；拟调整范围；禁用说明 | BC01/03/05 |
| F01 | 原允许飞书会话 | FullApprovalCardSpec、DisclosureGate、WebDeepLink | 与 Web 同版本全部 SKU/风险、身份及期限；容量能力检测 | BC01/05/06/07 |
| F02 | 原允许飞书会话的任务关联消息提案 | TaskClarificationProposal | 原请求、问题/候选；组织/聊天/发起人/话题/任务/轮次关联 | BC01/02 |

## 3. API 边界和 BC01–BC07

[ARCHITECTURE](../ARCHITECTURE.md)规划的 `POST /tasks`、`GET /tasks/{id}`、`GET /tasks/{id}/report`、`GET /tasks/{id}/events`、`POST /approvals/{id}/decision`、`POST /replenishment-items/{id}/resolve` 是设计依据，不是本分支的实现证据。`POST /tasks/{id}/retry` 不成为 M1 的通用恢复按钮。健康探针不替代管理摘要读取合同。

| BC | 前端接入前必须确认 | 当前处理 |
|---|---|---|
| BC01 | 身份/会话、组织店铺、owner/eligible、对象过滤、兼任并集、撤权与计数一致性 | Mock 角色样例；admin 无默认业务读/审批权；不能拼接动作权与对象范围 |
| BC02 | Web 预解析/候选来源；提交后歧义；飞书关联/轮次/去重/持久化/超时/续跑 | B35 只确认本地草稿；F02/B47 proposal 禁用；不发明续答 API/业务状态 |
| BC03 | 重算新版本、旧计划失效、批准/T4原子竞态、拒绝过期再发起、失败回退与历史关联 | B36 禁用；执行中/unknown 先核实；B46 仅开新草稿，B01才创建新task |
| BC04 | 自动恢复/对账可读状态、attempt/Checkpoint 与实际副作用回执关系 | S06/S08 只展示既有事实；unknown 不换键重发；无重启 Worker |
| BC05 | 会话、列表/详情/版本、管理摘要、指定报告解释的传输及错误合同 | 不虚构 endpoint；report version 绑定读取；解释无动态查数/RAG/写操作 |
| BC06 | 真实卡片容量与20条完整披露、客户端能力、身份与同版本Web回退 | 支持完整披露后可直接审批 / 不支持则转Web；当前卡片决定禁用，真实 G3 待验 |
| BC07 | 部署 expires_at、新鲜度配置、服务端时间与时区、到期错误 | 未取得值显示未知；不硬编码 24h / 15min 为产品承诺 |

金额、统计、库存、权限和幂等由确定性代码负责。LLM 只能解释已有事实和受限意图路由；不能计算权威 Q、决定角色、猜测 unknown 成功或改变批准集合。审批响应、内部项创建与飞书投影三个事实分别显示。

## 4. 状态与导航合同

- B19：指定 report → M04；加载/失败/模板为只读局部状态。加载失败不代表报告计算失败，模板降级不改变风险/数量；关闭返回同 report/version。
- B06：原报告 → M05。待执行重算与 rejected/expired 重新发起分开；B36 直到 BC03 确认均无业务交互目标。执行中/unknown 只读原事实，不覆盖执行。
- B33：版本列表 → 指定冻结历史；历史只读，旧批准不复用到当前版本或下一周期；回当前版本不改变历史事实。
- B46：仅源 task completed → M02 新草稿。旧 task 仍 completed；旧 execution 不再创建内部项；旧批准、nonce、假设确认、请求键均不继承。已有 open 项约束保留。草稿尚无 task_id，B01须重新显式提交。
- B31：当前 admin 有权时 → S08 脱敏只读摘要。没有配置写、密钥编辑、权限管理、手工重试或 Worker 重启。
- B47：仅 F02 proposal 的禁用关联回复。产品方向已接受，真实消息关联协议尚未确认；无伪造续答请求或成功闭环。
- 评审索引/身份选择、Mock 示例响应选择不进入正式路由与侧边导航，不用原型站点地图证明服务端鉴权。

## 5. Token 与组件复用

沿用 [design-tokens.json](design-tokens.json) 的 `m1_candidate` 和原 Foundations 18 组件 / 33 Native Token。POC 样式字段是历史，不用来覆盖 M1。背景 `#F6F8FA`、正文 `#344554`、标题 `#172B3A`、主动作 `#0F766E`、警示 `#8A5700`、错误 `#B42332`；所有颜色按原 Native Token 绑定。

AppShell 224px sidebar / 72px header；桌面 1440 和现有 1280 布局；Drawer 600；窄屏 390 为独立布局样例。正文14–16px，标题22–28px，行高1.5；按钮至少44px，间距复用4/8/12/16/24/32。Source Sans Pro 的中文 fallback 已有原型观察，正式 CJK 字体打包须前端再验。

按钮实例复用 primary/secondary/quiet；状态复用 pending/risk/unknown/complete/running 等；加载/空/错误、SKU事实行、AppShell均复用原组件。新增内容采用局部面板及复用按钮，不创建第二组件库。Native Token 存在不等于 CSS 自动同步；前端从合同导出语义 CSS 变量，逐项确认字体、间距、圆角和绑定覆盖。

## 6. 真实前端验收（均待执行）

| 场景 | 必要断言 |
|---|---|
| 键盘与焦点 | Tab顺序、可见 focus、Enter/Space动作；Dialog focus trap、关闭后还原触发控件；Esc取消不能触发业务动作 |
| 输入与校验 | 原因 pristine空白不报错，提交后字段错误关联；草稿输入/候选来源失败不自动猜选或提交；disabled说明可读取 |
| 解释面板 | report/version切换取消或隔离旧响应；只用既有上下文；加载/失败/模板分别可读，无事实或审批副作用 |
| 历史/新周期 | 深链读取固定版本；历史只读；completed→新空草稿不继承批准/假设/request_key；退出无副作用 |
| 响应式 | 1440/1280/390、缩放200%、长中文/SKU、20条全部风险；没有横向裁切或浮动批准旁路 |
| 权限与缓存 | 四角色/兼任；所有入口服务端鉴权；admin不能审批；scope过滤一致；撤权/过期清旧缓存与决定，不泄露计数 |
| 状态/竞态 | stale/expired/conflict/duplicate/unknown独立；原键原payload核实；同步异常不回滚内部项；旧批准不可跨版本 |
| 无障碍 | 语义heading/表格/状态、live announcement、字段错误、读屏原因/禁用说明；颜色不是唯一状态标识 |

这些要求交给真实 Next.js/Playwright/服务端测试。原型点击及截图不能证明真实键盘、焦点、读屏、鉴权或响应式通过。

## 7. 真实飞书 G3 合同与验收（均待确认/执行）

保留 M1 的真实飞书直接审批能力目标。客户端实际支持完整披露且后端校验成立时，卡片使用本版本正确的 B02/B05 或 B03/B04。不能完整呈现时禁止在截断卡片批准，转 Web 同版本详情后重新鉴权与完整披露；不是永久删除飞书审批。

必须实测：1条/20条、最长SKU、多个未知在途、全部风险、末项与末端动作区；真实发送payload容量、桌面/移动客户端展示与更新；转发/他人/撤权/过期/跨店铺深链；eligible批准/拒绝、明确假设集合、hash/nonce/版本、重复与冲突/unknown回读；Web和飞书同一计划事实。不能把已通过的技术探针当作20条M1产品卡片容量通过。F02另需 BC02 的发起人/任务/轮次、迟到/重复/跨任务回复与续跑证据，当前仍 proposal。

## 8. 冻结与退出

冻结需：本批完整映射和实际证据齐备、外部最终评审、用户明确确认。BC01–BC07 的 pending 项不因设计冻结自动启用；实现时以已确认合同补接，不扩建底层系统。停止于本轮 UX PR，不合 main、不修改 Phase 1、不写正式 Next.js、不启动下一批或30天后续日报/SKU深析/风险/RAG界面。

实际命名版本、Viewer次数、截图、刷新UUID及私有备份以 [B3交付](c2-b3-delivery.md) 中最终证据为准；未执行项明确记录，不从历史成功外推。
