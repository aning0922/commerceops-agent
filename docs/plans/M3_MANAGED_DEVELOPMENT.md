# M3 托管开发与交付记录

## 当前事实

- 授权日期：2026-11-03（台北）。主控会话：01a19f1b-f4c0-75c1-a9f0-8f8b88db72d5。
- 远端 main 只读核对：6d3a8f7bf3d36c6c1dcfd5072a3297be4cc88265；Issue49 closed/completed。
- 状态：IN_PROGRESS / LOCAL_IMPLEMENTATION；S1实现待显示校验修复复审，其余功能、完整CI和部署未验收。
- 当前目录 README 分支 e06b665 保持原样；本阶段使用独立 control/backend/web 工作树。

## 交付顺序

1. 日报确定性指标与异常规则，冻结数据口径、快照来源及验收金标。
2. 复用单 Worker / PG jobs / outbox 的持久调度、去重、补最近一期及受控推送。
3. 报告绑定的证据追问与最小可用 UI。
4. 白名单动态只读工具及实际工具序列/权限/预算评测。
5. 版本化 SOP 检索、可定位引用、人工审核及幂等保存内部草稿。
6. 必要本地/PG/Web/真实模型或平台证据、独立审查、精确 CI 与主控核收。

原范围依据：PRD、AGENT_DESIGN、ROADMAP、30_DAY_EXECUTION；日期与工时均须按新实际记录，不能把历史计划余额当可用额度。缺少许可资料、模型预算、接收对象和真人操作时，相关真实 Gate 保持 NOT_RUN，离线候选不代替正式完成。

## 分工

- Root：本文件、阶段授权导航、集成工作树、任务依赖、模型调整、必要发布与最终核收。
- Backend：合同草案、确定性指标、持久化/API/Worker/共享 DTO 及相应测试；不改 frontend。
- Web：仅 frontend 与最小 UI 实施说明；消费冻结且已提交的共享合同，不虚构接口。
- Reviewer：先只读评审合同与范围，再评审精确实现提交；不接管作者源码。

各开发者不得修改 Root 的阶段导航、另一开发者文件或 Harness 资产。共享 schema/迁移、根配置和 CI 只由 Backend 提案并经 Root 协调；锁文件或 workflow 必须有实际必要性。Root 普通合入精确已审提交，不 reset/amend/force，不读他人未提交 WIP 作为交付。

## 模型调度

初始：Backend Sol/high，Web Terra/high，Reviewer Sol/xhigh。常规文档/机械接线可降为 medium；跨层恢复、权限或并发阻断可提高强度，必要时以独立专项使用 Astra。工具实际接受的设置与回执为准，额度不可用不自动转付费 API。

## 外部边界与验收

新开发授权不复活旧真人/SDK/Native/CI一次性窗口，不修改旧 once 或 UNKNOWN。真实外发须绑定已授权对象；当前没有新增 paid API 或业务凭据访问。开发者无 push/PR/Hosted/main 权限，统一由 Root 在具体可审交付就绪后处理。保留现有所有安全、业务、恢复、权限和全量 CI 要求。

## 证据账

本次启动仅核对 GitHub main 与 Issue 状态、创建工作树及本文件；未运行业务测试、模型评测或服务。后续按实际 source SHA、命令、退出码、资源与限制增记，不预写通过或完成。

## 可见会话与动态命名

用户追加要求：会话名必须随当前开发内容动态调整，让侧边栏直接展示正在做什么。统一格式为 CommerceOps M3｜具体任务 · 当前阶段或阻塞原因；职责切换/进入实现/待审/修复/验收/被外部依赖阻塞时更新，避免只写A/B/Worker等内部代号。模型与推理在主控消息中记录，以实际工具接收结果为准。

| 会话 | ID | 初始分配 | 当前阶段 |
| --- | --- | --- | --- |
| 日报与调度 · 合同设计 | 01a19f34-8596-7732-8ac4-09ad74df324d | GPT-6.1 Sol / high | 已派发，合同草案 |
| 日报界面 · 交互梳理 | 01a19f34-ce14-7f83-a9c3-11b3a224389d | GPT-6.1 Sol / high（Terra 容量不足后切换） | 最小交互文档 |
| 独立审查 · 等待合同提交 | 01a19f35-0999-72f1-89ad-cf1de5421b75 | GPT-6.1 Sol / xhigh | 范围核查已交付，合同未验收 |

三会话实际状态均由 wait_threads 首次快照确认 active；创建返回不代替开始证据。旧Harness主控已获边界通知，本阶段不重开旧真实窗口。

### 启动核查结果

- 主控文档检查：当前118份Markdown，errors=0，命令退出0；仅文档检查，不代替业务测试。
- Web 的 Terra 调用返回模型容量已满；原会话切 Sol/high 继续，未改用付费API、未新建替代任务。
- 独审首轮范围意见：首批范围合理，但库存创建日cohort不能替代支付日/退款发生日完整采集；现OrderLine缺订单级运费。新日报合同应明确独立订单事实与完整性，不放宽旧inventory/P4约束。调度须绑定版本/时区/接收对象，最多补最近一期；报告唯一与外发唯一分开验证，UNKNOWN不自动重发。
- 合同与主体实现尚待精确提交独审；本记录不签M3或任何功能完成。

### S1 实施放行

独立Reviewer只读核对 Backend cfd3ef2d38c3c84c8d2c3a0dcd79616f8680c5c7 与 Web 27a11f211f39f767ae2916b8a447d7b6f914f37c，结论 ACCEPT_S1；只放行严格日报DTO、纯聚合/异常/证据hash和独立金标，不代表完整M3合同或实现通过。Root普通合入两份文档，组合Markdown检查120files/errors0/exit0。

Backend 已获S1实施指令，模型调整为Sol/xhigh；当前可见名为“CommerceOps M3｜日报聚合 · S1实现与金标”。Reviewer为“CommerceOps M3｜独立审查 · 等待S1与扫描候选”。Web方案依赖S4冻结接口，当前暂停UI接线，同一可见会话暂转“CommerceOps M3｜历史扫描 · 精确核收同步”，唯一写入新scan工作树，允许范围仅已有扫描器精确历史审批元数据/必要最小机制与针对性契约测试。

旧Harness owner只读回执确认固定b9ceaf3的审批索引含20项，后增17项已分别独审；尚须逐项集合/摘要对齐，不凭数量判定相同。扫描候选不得改变222条规则、dir/index门禁、扫描范围、历史refs或广泛allowlist，后续精确独审及实际全扫描仍待。历史M2规则扫描20命中/3已审/17blocking保留，不回填。

此时S1代码、scanner兼容、PG/Web/模型/实际推送、完整本地/Hosted/main核收均未验收。

### 连续托管与用户补充边界

用户于同日明确纠正主控“需要按照设定目标一直开发到完成”。Root建立持续目标，接回提交/审查/修复/集成/后续派发，不再把启动分工当开发终点。

用户已明确答复：SOP/商品资料暂未准备；真实模型及embedding预算稍后确定；暂不实际发送，先完成可验证实现。本阶段继续全部本地代码与替身/合成资料/新owned资源的验证，真实资料、真实模型/embedding评测与实际推送保持NOT_RUN，不能自动访问旧秘密、套用旧真实窗口或宣称正式全M3验收。

独审接收扫描兼容f1ad601：仅已审20项精确历史元数据，算法/222规则/全历史边界不变；Root已普通合入，完整实际扫描进行中。日报e073独审1项P2阻断：display未验证派生值/完整集合，作者已接回最小修复；旧135pass及失败反例分记。

增加可见知识检索/草稿会话01a19f5b-4424-7413-8933-58980c0c4155（Sol/high），在独立knowledge树先做最小合同；无许可资料时仅自创合成fixture。动态只读会话01a19f34-ce14-7f83-a9c3-11b3a224389d已由扫描任务转为inquiry树，按原D01–D05准备执行器合同。所有共享DDL/ACL仍由Backend统一协调，避免迁移号冲突。

### 首轮扫描与执行器进展

Root在扫描集成提交7db2b69be0bcab8d9a2b85f600858e0b63d702d3实际执行完整scan：dir0/index0/git20全部精确已审/阻断0，aggregate exit0；原生history scanner exit1保留。独立针对性quality gate 30pass/93deselected/8.78s/native0，包括原缺工具的合成扫描反例；不代替完整工程/PG。工具node24.21.0与gitleaks8.30.1均按固定官方归档SHA256 bootstrap到新control树。

动态查询合同cd2caad已独审ACCEPT_IMPLEMENTATION，Root已释放application/commerce/readonly_inquiry_*纯模块与专用测试；查询级累计窗口/实际扫描行/SKU、每次鉴权、第三模型轮停止、迟到/partial与错引拒绝为明确约束。API/Worker/真实provider后续，当前真实预算关闭。知识合同3097d60已转独审，尚未放行K1。
