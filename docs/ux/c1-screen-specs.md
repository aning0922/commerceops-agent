# Phase C1 · 页面详设

版本：`0.2.0-c1-review`，全部待评审、未映射Penpot。对应 [主方案](c1-product-design.md)、[机器清单](screens.yaml)。页面状态名除既有业务枚举外均为UI表现，不新增数据库状态。

## 所有页面共用的异常合同

- **loading**：骨架占位，不显示虚假0；副作用按钮禁用。
- **empty**：区分真正无记录、筛选无匹配、未授权；不泄露全店计数。
- **read_failure**：区域错误+safe_message/trace_id+重读；保留旧数据时标最后更新时间且禁止据此批准。
- **session_expired**：跳S01，保留安全站内return_to；重新登录后重读，不自动重放写操作。
- **forbidden**：S07；清理旧敏感内容，不展示其他对象名称。
- **stale**：显示时间/版本，重新获取；冻结历史不被新读覆盖。
- **submitting**：禁用同对象相反动作；不乐观显示业务成功。
- **result_unknown**：先读取原对象及回执；安全重投沿用原key/payload。
- **conflict**：展示授权范围内最新状态，禁止覆盖；用户重新理解后行动。

所有数据读失败的“重试”B42仅重新读取；不得触发新任务、审批或工作项。无权限与过期优先于保留旧内容。页内响应未知处理按主方案J04，审批页面不能把旧缓存当作有效计划。

## M1-S01 · 登录

拟议位置：`/login`。

| 设计维度 | 方案 |
|---|---|
| 业务目标 | 让预置身份进入授权工作区，恢复安全深链。 |
| 布局与功能区 | 居中紧凑表单：产品/Mock环境说明、账号密码、提交与错误；无第三方OAuth入口。 |
| 数据与指标 | 账号输入、会话校验状态、安全return_to；不展示角色选择、账号是否存在或密钥。 |
| 控件、菜单与跳转 | B11登录；已有会话按角色落地。 |
| 角色可见与权限 | operator/approver/admin/unauthorized均可见登录壳；真实授权由服务端会话取得；admin单角色默认S08，无业务权限去S07。 |
| 特有状态 | signed_out、submitting、invalid_credentials、session_expired、rate_limited、service_unavailable；同时覆盖全部适用共用异常 |

## M1-S02 · 任务中心

拟议位置：`/tasks`。

| 设计维度 | 方案 |
|---|---|
| 业务目标 | 找到需要关注的授权任务并发起库存分析。 |
| 布局与功能区 | 标题+新建按钮；少量授权范围状态计数；状态/日期/编号筛选；任务表与分页。无经营总览大屏。 |
| 数据与指标 | task_id、请求摘要、发起人显示名、created_at、销量窗口、source_kind、state、active_plan版本、sync摘要；计数与列表同scope。 |
| 控件、菜单与跳转 | B10新建；B13筛选/排序/分页；B14任务行到S09；B39/B40/B41全局导航。 |
| 角色可见与权限 | operator可新建；approver只看授权任务；admin仅兼任/明确业务读授权才可见；无权限不返回数据。 |
| 特有状态 | loading、empty、filter_empty、queued、analyzing、awaiting_approval、executing、completed、rejected、expired、needs_reapproval、failed、needs_attention；同时覆盖全部适用共用异常 |

## M1-S03 · 库存分析报告

拟议位置：`/tasks/:task_id/report?version=:version`。

| 设计维度 | 方案 |
|---|---|
| 业务目标 | 理解风险、计算依据、可执行范围与阻断因素。 |
| 布局与功能区 | 任务子导航；来源/版本/完整性条；风险与资格计数；简短解释；SKU事实表；行详情；固定下一步区。 |
| 数据与指标 | snapshot_id、report_id、window_start/end、shop timezone、inventory_observed_at、complete/quality_flags、rule_version、L/R/S、facts_hash；每SKU原始需求/退款、D、A、raw/effective inbound、T、Q、风险、资格、open item引用；覆盖天数仅D>0且有已知A时展示并说明A/D。 |
| 控件、菜单与跳转 | B17查看审批；B18口径；B19解释；B06提出重算；B33历史版本；B43行详情；B15/B16页签。筛选不改变审批范围。 |
| 角色可见与权限 | 授权operator/approver可读；重算仅operator且对象授权；admin不默认可读；历史报告只读。 |
| 特有状态 | loading、not_generated、ready、no_action、data_incomplete、unknown_inventory、negative_inventory、zero_demand、unknown_inbound_draft、scope_over_20、narrative_fallback、stale_version；同时覆盖全部适用共用异常 |

## M1-S04 · 审批详情

拟议位置：`/approvals/:approval_id`。

| 设计维度 | 方案 |
|---|---|
| 业务目标 | 让审批人对完整冻结范围做一次知情决定并跟踪回执。 |
| 布局与功能区 | 面包屑+计划版本/期限；批准后会创建什么；全部≤20条SKU清单；假设逐项披露；历史决定/执行结果；底部明确决策按钮。无默认勾选。 |
| 数据与指标 | approval_id、plan_id/version/hash短展示、expires_at、eligible scope、全部canonical_items/required_assumptions、数据时点/参数、ready_at、决定人/时间/来源、execution结果与当前计划状态。nonce不在UI或日志显示。 |
| 控件、菜单与跳转 | B02/B05仅已知在途；B03/B04仅存在未知在途；B23核实结果；B15关联报告；B29任务结果；B33看历史版本。 |
| 角色可见与权限 | operator授权任务仅只读；approver必须当前eligible/同店铺；admin兼任才可批准；按钮可见性不代替服务端验证。 |
| 特有状态 | loading、pending_known_inbound、pending_unknown_inbound、preparing_delivery、submitting、result_unknown、approved_execution_pending、rejected、expired、superseded、decision_conflict、permission_revoked、plan_changed、assumption_ack_required、executed；同时覆盖全部适用共用异常 |

## M1-S05 · 内部补货管理

拟议位置：`/replenishment-items`。

| 设计维度 | 方案 |
|---|---|
| 业务目标 | 查找已由审批产生的内部工作项与跟进状态。 |
| 布局与功能区 | 标题含内部工作项说明；open/completed/closed筛选；SKU/任务搜索；表格分页；详情入口。无新建采购或批量操作。 |
| 数据与指标 | item_id、sku_key/label、stock_pool_key、quantity、status/version、源task/plan、approved_by、创建时间、resolution摘要、sync状态/版本。 |
| 控件、菜单与跳转 | B24筛选；B25打开S11；B26/B27打开单项原因弹窗；B38查看同步详情。 |
| 角色可见与权限 | operator只读授权派生项待D01；approver同店铺可完成/关闭open；admin无默认业务权；无权不见列表及计数。 |
| 特有状态 | loading、empty、filter_empty、open、completed、closed、sync_pending、sync_failed、sync_unknown、item_state_conflict；同时覆盖全部适用共用异常 |

## M1-S06 · Agent执行轨迹

拟议位置：`/tasks/:task_id/events`。

| 设计维度 | 方案 |
|---|---|
| 业务目标 | 解释任务经历的事实、失败边界和恢复证据。 |
| 布局与功能区 | 任务页签；当前业务结果摘要；按实际时间排序的节点/尝试时间线；点击步骤展现脱敏详情；模型用量与审批审计折叠区。 |
| 数据与指标 | workflow_version、node/run_attempt、tool_name/version/status/duration、safe_args、result_ref、snapshot/plan/decision/execution引用、模型/provider/prompt_version/usage/cost_estimate/pricing_version、等待与运行耗时、safe error/trace_id、outbox状态。 |
| 控件、菜单与跳转 | B43展开步骤；B34复制安全编号；B29返回业务结果；B09恢复仅D04批准后；B38同步说明。 |
| 角色可见与权限 | 授权operator/approver看任务级脱敏事实；admin异常元信息在S08，完整轨迹需业务读授权；不展示秘密、原始回调、SQL、客户PII、模型思维链。 |
| 特有状态 | loading、empty、queued、running、interrupted、recovering、failed、needs_attention、completed、usage_unknown、sync_pending、sync_failed、sync_unknown、result_unknown；同时覆盖全部适用共用异常 |

## M1-S07 · 访问限制与会话过期

拟议位置：`/access`。

| 设计维度 | 方案 |
|---|---|
| 业务目标 | 给出可理解但不泄露资源存在性的访问反馈。 |
| 布局与功能区 | 简洁状态图标+原因类别+返回/登录按钮；不渲染受限业务壳中的旧数据。 |
| 数据与指标 | 安全错误类别、当前身份、trace_id；无SKU/报告/对象所有者。 |
| 控件、菜单与跳转 | B31回授权首页；B11重新登录；B12退出。不存在与跨scope对象统一安全提示。 |
| 角色可见与权限 | 任何身份可见提示；不提供申请新业务权限按钮、不因失败自动提权。 |
| 特有状态 | forbidden、not_found_or_forbidden、session_expired、permission_revoked；同时覆盖全部适用共用异常 |

## M1-S08 · 管理员配置摘要与异常说明

拟议位置：`/admin/operations`。

| 设计维度 | 方案 |
|---|---|
| 业务目标 | 管理员了解当前配置版本和需按既有流程处理的异常。 |
| 布局与功能区 | 只读店铺/来源与规则摘要；集成配置状态；安全异常表；单条说明及现有运维文档入口。无密钥编辑器或通用用户管理。 |
| 数据与指标 | environment、rule/workflow版本、时区、角色配置摘要（不列不必要个人信息）、脱敏错误码/时间/trace_id、投影unknown/failed；不返回业务SKU金额或秘密。 |
| 控件、菜单与跳转 | B43展开异常；B34复制trace_id；B42重读；B30进入；无“重启Worker/重新发送/修改权限”写动作。 |
| 角色可见与权限 | admin可见只读运维元信息；其他角色S07；兼任业务角色按其scope另打开业务页。配置写入口D05未授权。 |
| 特有状态 | loading、read_config、empty、read_failure、permission_restricted、recovery_requires_attention、config_unavailable；同时覆盖全部适用共用异常 |

## M1-S09 · 任务概览与结果

拟议位置：`/tasks/:task_id`。

| 设计维度 | 方案 |
|---|---|
| 业务目标 | 回答这次请求做到哪一步、谁需行动、最终产生什么。 |
| 布局与功能区 | 任务标题/请求/编号；阶段摘要；当前下一步卡；报告/审批/内部项关联；同步状态；概览/报告/轨迹页签。 |
| 数据与指标 | normalized_request、requester、source channel、state/failure_code、当前plan、审批决定、execution result_refs、内部项数量、last_updated、sync摘要；已完成结果不因图重试丢失。 |
| 控件、菜单与跳转 | B15报告；B16轨迹；B17审批；B25派生项；B38同步；B34编号。报告未生成时相应入口解释原因，不跳空报告。 |
| 角色可见与权限 | 授权任务读范围同D01；按当前身份仅提供有权动作；批准仍在S04。 |
| 特有状态 | loading、queued、analyzing、needs_clarification_ui_proposal、awaiting_approval、executing、completed、no_action、rejected、expired、needs_reapproval、failed、needs_attention、sync_failed、sync_unknown；同时覆盖全部适用共用异常 |

## M1-S10 · 审批列表

拟议位置：`/approvals`。

| 设计维度 | 方案 |
|---|---|
| 业务目标 | 让审批人找到可处理和已处理的冻结计划。 |
| 布局与功能区 | 待我处理/已处理/全部可见标签；任务/状态/期限筛选；表格、空态与分页。 |
| 数据与指标 | approval_id、task摘要、plan版本、pending状态、expires_at、条目数、未知假设标识、decided_by/time；计数与eligible授权一致。 |
| 控件、菜单与跳转 | B20筛选；B21打开S04；不在列表直接一键批准、批量决定或预勾选。 |
| 角色可见与权限 | approver看到eligible范围；operator仅授权任务审批只读；admin无默认权；不是全组织审批中心。 |
| 特有状态 | loading、empty、filter_empty、pending、approved、rejected、expired、superseded、read_failure；同时覆盖全部适用共用异常 |

## M1-S11 · 内部工作项详情

拟议位置：`/replenishment-items/:item_id`。

| 设计维度 | 方案 |
|---|---|
| 业务目标 | 核对单个内部项的来源、状态、跟进记录及同步结果。 |
| 布局与功能区 | 标题SKU+内部项状态；数量与依据；源任务/报告/审批链接；跟进历史；Base投影状态；有权时完成/关闭动作。 |
| 数据与指标 | item_id/version、stock_pool_key、quantity、approved_plan_id/approved_by、source_snapshot、resolved_by/time/reason、sync/version/external_link是否可用。 |
| 控件、菜单与跳转 | B26完成/B27关闭→M01；B37来源报告；B38同步详情；B34复制item_id；终态不重开。 |
| 角色可见与权限 | approver同店铺可resolve；operator授权派生项只读；admin显式兼任才有动作；外链仅返回已授权且存在的投影引用。 |
| 特有状态 | loading、open、completed、closed、sync_pending、sync_failed、sync_unknown、item_state_conflict、permission_revoked；同时覆盖全部适用共用异常 |

## M1-F01 · 飞书审批卡片

拟议位置：`feishu://existing-allowed-conversation`。

| 设计维度 | 方案 |
|---|---|
| 业务目标 | 在已有授权协作渠道查看完整计划并显式审批。 |
| 布局与功能区 | 标题任务/环境/版本；窗口/库存时点；全部SKU逐项；风险/参数/假设；期限；两枚适用决策按钮；Web详情/结果链接。 |
| 数据与指标 | 与S04相同冻结计划；≤20条完整批准范围；不展示token/nonce；共享更新只能用共同可见内容。 |
| 控件、菜单与跳转 | B02/B05或B03/B04；B21 Web详情；B29结果；重复显示既有决定；关闭无效果。 |
| 角色可见与权限 | 卡片可能被转发或无权成员看到，客户端不能按角色隐藏而当作保护；可信回调逐次认证操作者；外发范围遵循既有允许群/用户，不扩大授权。 |
| 特有状态 | pending_known_inbound、pending_unknown_inbound、submitting、approved_execution_pending、rejected、expired、superseded、duplicate_existing_decision、unauthorized、conflict、sync_failed、client_unsupported；同时覆盖全部适用共用异常 |

## M1-M01 · 单项完成/关闭原因

拟议位置：`overlay:S11`。

| 设计维度 | 方案 |
|---|---|
| 业务目标 | 记录明确的单项终态动作和必填原因。 |
| 布局与功能区 | 标题明确“内部跟进完成”或“关闭内部工作项”；SKU/数量/当前版本摘要；原因文本域；取消与对应提交按钮；无默认原因。 |
| 数据与指标 | item_id、status=open、expected_version、action、reason、固定本次request_key；提示不表示入库。 |
| 控件、菜单与跳转 | B07或B08提交；B28取消/Esc；失败留原输入；unknown先重读，不能换键或改payload假装重试。 |
| 角色可见与权限 | 只允许当前同店铺approver；权限撤销清理并S07；非open只能看冲突说明。 |
| 特有状态 | reason_empty、reason_valid、submitting、result_unknown、success、conflict、permission_revoked；同时覆盖全部适用共用异常 |

## M1-M02 · 自然语言新建分析

拟议位置：`overlay:S02`。

| 设计维度 | 方案 |
|---|---|
| 业务目标 | 用自然语言提出受支持的库存分析并理解有效范围和自动送审。 |
| 布局与功能区 | 桌面宽抽屉/窄屏整页：示例请求、输入、已知默认窗口/店铺/规则、范围提示、自动送审说明、创建按钮；澄清区域D02。 |
| 数据与指标 | 原请求；默认最近7完整日/时区；显式SKU范围；规则演示标签；解析完成前不得把候选参数写成已确认；无价格或供应商字段。 |
| 控件、菜单与跳转 | B01创建；B35澄清补充为待定协议；B45关闭并确认丢弃未提交输入（若有）；示例填入不自动提交。 |
| 角色可见与权限 | operator可用，角色兼任同样校验；无operator无入口；自然语言“同意”不能成为审批动作。 |
| 特有状态 | draft、invalid_input、submitting、result_unknown、clarification_proposal、unsupported_intent、ambiguous_sku、scope_over_capacity、accepted；同时覆盖全部适用共用异常 |

## M1-M03 · 数据口径与来源

拟议位置：`overlay:S03`。

| 设计维度 | 方案 |
|---|---|
| 业务目标 | 让用户无需离开报告即可复算关键数字。 |
| 布局与功能区 | 只读侧栏/窄屏面板：来源与完整性、统计窗口、公式/参数、SKU示例、限制；返回触发位置。 |
| 数据与指标 | snapshot/report/rule版本；D=原始需求/7；T=ceil(D*(L+R+S))；Q=max(0,T-A-effective_inbound)；退款独立、未知/负库存、演示参数、假设说明。 |
| 控件、菜单与跳转 | B22关闭/Esc；B43展开字段定义；不提供直接编辑冻结参数。 |
| 角色可见与权限 | 继承报告读权限；数据不可读时不缓存展示；admin不默认可读。 |
| 特有状态 | loading、ready、missing_evidence、read_failure；同时覆盖全部适用共用异常 |

## M1-M04 · 解释本报告

拟议位置：`overlay:S03`。

| 设计维度 | 方案 |
|---|---|
| 业务目标 | 对已有结论进行受限追问并给出可定位事实引用。 |
| 布局与功能区 | 固定上下文标签task/report/version；2–3个问题建议；消息区与引用；输入/发送；关闭回报告。 |
| 数据与指标 | 只读已授权report和SKU事实引用、narrative_mode、解释错误/超限状态；不混入别人的任务或不同快照。 |
| 控件、菜单与跳转 | B32解释请求，API待契约；B22关闭；事实引用B43定位行；要求改数量/批准/新查询时说明边界并引导合适页面，不自动执行。 |
| 角色可见与权限 | 继承报告读权限；仅explain_report路由；无动态Tool自由查数/RAG/全局对话写操作。 |
| 特有状态 | loading、ready、explaining、explanation_failed、template_fallback、unsupported_request、budget_exceeded、context_expired；同时覆盖全部适用共用异常 |

## M1-M05 · 重算影响预览

拟议位置：`overlay:S03`。

| 设计维度 | 方案 |
|---|---|
| 业务目标 | 在重算前明确版本与重新授权影响。 |
| 布局与功能区 | 原task/版本及状态；待调整范围；新采集说明；旧确认不继承和旧pending处置提示；取消/确认（合同待定禁用）。 |
| 数据与指标 | 当前任务/plan状态、拟请求变化、现有open项提示；不允许手填最终Q；真实差异需新报告生成后比对。 |
| 控件、菜单与跳转 | B36确认（D03待定）；B22取消；已完成任务使用“开始下一周期分析”标签，新task入口仍须operator。 |
| 角色可见与权限 | operator及对象授权；approver需兼任；重算不是恢复retry，不自动移用批准。 |
| 特有状态 | review、contract_pending、submitting、result_unknown、version_conflict、scope_invalid；同时覆盖全部适用共用异常 |

## 状态覆盖与验收责任

审批S04/F01覆盖已知/未知在途、完整假设披露、同人重复/他人冲突、过期、superseded、执行前事实变化、权限撤销和已批准但不可执行。工作项S11/M01覆盖必填原因、重复回执、版本冲突、终态不可重开与同步未知。任务S09/S06覆盖排队/中断释放执行槽、报告降级、服务端恢复和内部结果已提交但图落后。

这些为C2原型及Phase 3–4业务验收输入；本轮未执行点击/角色/响应式/可访问性业务测试。详细控件守卫与异常见 [interactions](interactions.yaml)，设计评审清单见 [C1验收](c1-validation.md)。
