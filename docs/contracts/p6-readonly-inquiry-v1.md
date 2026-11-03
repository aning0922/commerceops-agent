# P6/M3 受限动态只读查询 v1 合同候选

状态：`PROPOSED / REVIEW_REQUIRED`，2026-11-03（台北）。本文件只定义可实现的窄合同；没有注册新业务入口、模型、Tool、数据库或 API。Root 转交独审结论后再实施。依据：[PRD](../PRD.md) P1、[AGENT_DESIGN §9](../AGENT_DESIGN.md)、[TEST_PLAN D01–D05](../TEST_PLAN.md) 与现有源码。

## 1. 现有边界与实施取舍

现有 [GuardedRouter](../../backend/src/commerceops/application/commerce/inventory_routing.py) 只接受五种固定意图，`readonly_inquiry` 尚未注册；原库存请求继续原路由和审批合同。现有 [CommercePort](../../backend/src/commerceops/application/commerce/ports.py) 有 `list_products / list_order_lines / get_inventory`，但暂无 M3 ToolSpec registry。`list_refunds` 是底层端口，不加入本能力的模型可选工具。`reports.read` 必须接已有授权报告读取能力，不能直接按报告 ID 绕开对象 scope。

现有 [DeepSeekAdapter](../../backend/src/commerceops/adapters/model_explanation/deepseek.py) 对 `tool_calls` / `function_call` 返回 `UNSAFE_EXPLANATION`；[DeepSeekRoutingPort](../../backend/src/commerceops/adapters/commerce/deepseek_routing.py) 只解析固定 `{intent,candidates}`。因此不能把 `readonly_inquiry` 塞进旧五意图枚举后直接宣称已有 tool calling。实现时在同一主 Agent 路由后增一个专用 `ReadonlyChoicePort`；复用现有模型适配层的安全配置、超时、usage 解析、token 计数与准入原则，但为合法工具提案定义单独的严格响应解析。旧解释/路由 adapter 的拒绝规则保持。若 provider 实际 tool-calling 形状未独立验证，先用受限 JSON 提案协议的替身演练，不宣称真实 tool calling Gate 通过。

既有 [PersistentAdmission](../../backend/src/commerceops/infrastructure/model_budget_repository.py) 绑定 P204 请求、prompt、facts_hash 与原阶段预算，不可拿旧剩余调用次数给 M3 使用。M3 真实模型在单独账本/预算、价格版本、授权模型和调用回执接入前关闭；不能因 `offline_stub` 通过便自动开启付费调用。既有 Woo 只读 adapter 的测试店来源和固定文件绑定也不能从旧窗口继承真实授权。

## 2. 窄输入、输出与选择协议

`ReadonlyInquiryInput`（提案，strict/frozen/extra=forbid）：`schema_version=p6-readonly-inquiry-v1`、最多 2000 字的 `question`、可选有权 `context_report_id`、服务端构造的 `principal_id / organization_id / shop_id / identity_id / auth_version`、来源绑定引用、`request_id`。Web/飞书文本不提供 actor、role、shop、source、allowlist、budget 或审批字段；外部请求只含问题和服务端允许的显式目标店铺/报告选择，身份由原会话/Gateway 绑定并在执行时重查。

入口由同一主 Agent 判定：明确查询库存、销量、已有报告事实 → `readonly_inquiry`；补货、审批、关闭、支付、订单修改等写意图 → `unsupported`/澄清，不在本次执行中自动转写流程；混合“查一下并顺便批准”不得部分执行后触发写操作。**第一轮模型调用同时提出路由和首批工具**，计入总共 3 次模型调用；不能先额外调用旧 `GuardedRouter` 再把其调用藏在预算外。若由已有路由先产生模型调用，该次也必须计入 3 次，无法在剩余次数内完成安全追问就停止/澄清。路由模型提案仅作为候选，服务端再核意图、当前身份与请求范围。跨店铺或 SKU 歧义先澄清，不猜目标。

模型每轮只可返回严格联合类型；首轮还必须给固定 `intent`（`readonly_inquiry / clarify / unsupported`），后续轮次不得改路由：

| 类型 | 字段与约束 | 执行器动作 |
|---|---|---|
| `call_tools` | 1–4 个有序 `{tool_call_id, name, args}`；唯一 ID、仅白名单名、每种工具闭合参数 schema；无任意文本参数外字段 | 逐个串行复核并执行。一个模型响应可以提出多个独立工具，但后一工具不能读取同响应中前一工具的结果 |
| `final` | `answer_claims` 为引用已授权证据 ID 的结构化说明；或 `clarification`/`insufficient_evidence`/`unsupported`/安全错误 | 先核每条 claim 引用、数字与口径，再用确定性渲染；不原样输出自由模型数值 |

如使用原生 provider tool-call wire，只有 `call_tools` 形状可进上述验证；`finish_reason`、并行工具、重复 ID、额外字段、未知工具和内容/调用混杂均拒绝。实际 provider 对这些字段的支持须单测。provider-neutral Fake 使用相同中立 `ChoicePort` 结构、同一执行器和同一业务 guards，不绕过校验。模型可根据上轮的安全结果选择下一工具或澄清，不强迫固定三工具序列。

`ReadonlyInquiryResult` 必须区分 `complete / clarification / insufficient_evidence / unsupported / budget_exceeded / timeout / source_incomplete / access_denied / provider_failed` 等安全结果（精确枚举实现前冻结）；带 `workflow_version`、授权范围标识、工具轨迹、每条 claim 的 `evidence_refs`、每来源独立 `as_of`、`completeness`、`usage`/费用证据模式。失败/无证据不生成貌似完整的数字回答；原始模型全文、客户信息、凭据和自由 URL 不进入公开轨迹。

## 3. 固定 ToolSpec 与逐次准入

静态 registry 仅四个名字，固定版本且 `effect=read`。查找采用精确键；不能通过反射、动态 import、模型参数里的 endpoint/SQL/URL/shell 扩充。`approval.prepare`、`replenishment.create_internal / resolve_internal`、飞书发送、Base 投影、支付/退款及一切写工具均不在 registry。模型不能自行传 `effect`；即使有人错误注册白名单名但 `effect!=read`，执行器也必须拒绝。

| 名称 | 模型可提议的最小参数 | 服务端执行与来源边界 |
|---|---|---|
| `commerce.read_products` | 有界商品名或 SKU 查询、最多 100 个显式 SKU；不接 URL/cursor/任意过滤表达式 | 用服务端绑定的 CommercePort 分页读取并确定性筛选；商品名重名返回歧义，不静默选首项；仅脱敏标识/名称/来源 |
| `commerce.read_orders` | 经已解析 SKU 集合、UTC `[start,end)` 且≤30天；不接任意店铺、SQL、状态表达式 | `list_order_lines(Window)` 完整分页后确定性聚合；最多 10,000 行；退款或净额需要的底层关联查询由确定性服务内完成，不把 `read_refunds` 暴露给模型 |
| `commerce.read_inventory` | 经当前店铺验证的 `sku_key` 集合≤100 | 对每个 SKU `get_inventory`；库存/在途未知保持 null；来源时间各自标记，不把“当前”写成无延迟实时事实 |
| `reports.read` | 当前有权的精确 `report_id`，可选既有版本标识 | 原业务授权读路径复查组织、店铺、对象可见范围及版本；只返回脱敏冻结事实与引用，不触发重算/采集/外发 |

这些参数是待冻结的窄 schema，不表示当前端口已有按名搜索或按 SKU 过滤能力。现有 `list_products` 仅分页，因此商品名搜索初版必须在服务端有界完整读取后筛选；容量不足返回不完整/澄清，不假称唯一匹配。订单行也是窗口分页接口，SKU 筛选和汇总由确定性层在已完整扫描的有界数据上执行；不能为了达到 10,000 行而静默丢尾页。`reports.read` 的报告对象资格需由后端合同给出，不按旧 operator 任务范围自动推全店日报权限。

每个逻辑 Tool 前按顺序执行：检查总截止与调用计数 → 精确 registry 与 `effect=read` → strict schema/类型/长度/日期范围 → 从服务端上下文重查身份、auth_version、组织/店铺及该对象当前权限 → 来源配置/测试店资格与服务端绑定 → 预算余量 → 在该截止内执行端口并记录来源、分页、行数、完整性。拒绝发生在任何 I/O 前，拒绝记录为安全事件，不回显不可信 args 原文。重复同一个 model proposal 不形成无界重试。

上下文在每次 Tool 前重查，最终回答前再次校验身份与已引用报告的对象资格；撤权后清可见结果。不能把第一轮查到的角色、店铺或报告引用作为后续轮次授权，也不能把不同店铺的数据拼在同一回答。组合查询结果有不同 `as_of` 时逐来源标注，明确“这些不是同一原子快照”。

## 4. 总量、时间与故障封口

一次询问从进入同一主 Agent 的 M3 路由起有单调时钟绝对截止 60 秒，不含原队列等待；包含路由模型调用、所有工具内部分页、确定性计算和最终整理。每个网络/DB调用、分页循环及模型调用都取剩余时长；超时停止，不能通过新子调用续窗。硬上限为逻辑 Tool≤4、模型调用≤3（含最终说明）、跨度≤30天、累计唯一 SKU≤100、累计订单行≤10,000。额外保留适配器自身页数、请求数、字节数上限；任何底层上限先到都返回明确 `source_incomplete`。行数上限对所有订单调用累计，不能每次刷新 10,000 行；SKU 上限也跨工具累计。bool 不当整数、无时区/逆序/零长窗口拒绝；不按用户文本截断至上限。

模型调用次数在请求发出前消耗，未知响应也计入；第三次模型调用若仍提议工具而不能再给出最终说明，则执行器停止并给确定性“不足以安全回答/预算已用尽”，不得隐式第四次调用。第一轮可提出多个独立只读 Tool，第二轮看前次结果再选择，第三轮结束。例如商品名问题可第 1 轮 `read_products`、第 2 轮根据匹配 SKU 选 `read_orders` 与 `read_inventory`、第 3 轮给带引用的结论；已知 SKU 库存可第 1 轮单 `read_inventory`、第 2 轮结束。模型提案里多 Tool 仍严格串行执行；一条调用失败时不继续其后依赖项，按安全结果返回。

如果此前模型调用失败、usage 缺失、token 上界不能证明、成本/余额未知或实际 provider 限额未获 Root 释放，真实模式 fail closed。`offline_stub` 的 usage 和成本与实际 provider 分开记；不把估算费用当实际账单。持久重放/网络结果未知时不能盲发另一模型调用；需先有本能力独立的预留/结果核实合同。当前文档不复用 P204 的一次性真实额度、旧 PG 或真人窗口。

## 5. 证据、脱敏与确定性计算

每个工具结果返回固定 `tool_call_id / args_hash / source_kind / snapshot_id|report_id / as_of / completeness / quality_flags / evidence_refs / redacted_facts`；`args_hash` 是规范化服务器参数摘要，不记录原始敏感输入。订单结果只给 SKU、日期、数量、精确金额与币种等允许字段，不给姓名、地址、邮箱、电话、原始订单响应。报告结果只给调用人当前可见的冻结事实。引用使用类型化内部 ID，模型不能制造任意 URI；全部引用须属于本次已校验工具结果及同组织/店铺。

销量、退款、比率和区间比较由纯函数从经校验的完整 facts 算出，金额用 Decimal 且按币种分组。零分母输出 `not_computable`，部分分页或质量失败输出 `incomplete`，不能让模型填 0 或计算“利润”。`as_of` 在每个结果和每条 claim 的证据旁保留；窗口、来源、币种、规则版本随结果保留。模型只选工具、提出说明和引用，最终渲染从确定性结果填数字。冲突或不足时澄清/停止，不能用语言流畅度盖过证据缺口。

轨迹只展示安全字段：`workflow_version / model_turn / tool_call_id / tool_name / args_hash / status / safe_error_code / snapshot_id|report_id / as_of / rows_seen / completeness / usage / latency / evidence_mode`。模型原始响应与工具结果不作公开日志。可复算金标引用同一确定性计算版本；旧事实和本次现查不得混写为一份冻结快照。

## 6. 可立即实现的纯切片与后续接线

Root 先协调独占目录；建议在 `backend/src/commerceops/application/commerce/` 下新增 `readonly_inquiry_contracts.py`（strict DTO、四项注册名/参数、结果和证据）、`readonly_inquiry_executor.py`（纯状态机、逐次准入、计数/截止/串行、引用验证）及窄纯测试 `tests/test_p6_readonly_inquiry.py`。这些是建议路径，尚未授权本会话写生产代码。工具执行端口通过类型化 `ReadToolPort` 注入，Fake 只能提供脱敏的固定事实/时钟/身份回读；测试不依赖 PG 或真实网络。

后续由 Backend/Root 统一协调：实际 `CommercePort` 的服务端过滤/分页安全包装、`reports.read` 当前权限路径、当前身份与来源绑定、已有主路由新增意图的版本兼容、必要 API/Worker 接线、独立真实模型预算账本、原适配层的专用受限 tool-call parser 及真实 provider 能力验证。新业务入口不可借旧 `DeepSeekAdapter.complete()` 直接执行工具；不修改旧 P0 审批、迁移或 Worker 合同来凑演示。

## 7. 冻结 Fake 金标与验收分层

同一执行器下固定 provider-neutral `ChoicePort` 脚本，每轮输入包含前轮安全结果摘要；按结构比较“合理且必要的序列”，不强制唯一序列：

| 用例 | 合法序列示意 | 必要断言 |
|---|---|---|
| D01a 已知 SKU 库存 | `read_inventory → final` | 无商品/订单多余调用；库存来源与 `as_of` 可追溯 |
| D01b 商品名两期销量+库存 | `read_products → read_orders + read_inventory → final` | 第二轮取产品实际解析 SKU；两期确定性统计与库存引用齐全 |
| D02 注入/夹带写动作 | 无调用或只读调用后安全停止 | 白名单外及 effect!=read 拒绝；零业务写，网页/订单文本指令不改变注册表 |
| D03 范围/预算极限 | 按具体越界点停止 | 第 5 Tool/第 4 模型、31 天/101 SKU/10001 行/60 秒、跨店、非法类型、分页未尽均拒绝或不完整 |
| D04 两时点与证据缺口 | 有来源的只读结果；不足则澄清 | 各 `as_of` 不合并，Decimal/零分母金标一致，错引及无证据数字拒绝 |
| D05 轨迹与模式 | 同一冻结集分别替身与真实 provider | 记录意图、逐次工具、引用、usage/耗时/费用证据模式；真实部分仍待另行预算与平台准入 |

边界测试还要注入撤权发生在两个 Tool 之间、Tool 完成与最终回答之间、模型迟到、重复 call ID、混合 final+tool、额外参数、响应截断、来源 partial page、同 SKU 不同时间和未知模型 usage。Fake 全绿只证明执行器合同候选；真实 tool calling、PG、API/Worker、生产店铺、D05 provider 及全 M3 Gate 均 `NOT_RUN`。

本次交付仅为合同草案；未读凭据、未调用模型/平台、未启动服务或 PG、未修改生产代码。独审应先评定路由版本兼容、当前报告读取范围及新模型预算策略，再释放独占实施路径。

## 8. 首片纯执行器作者交付（2026-11-03，待独审）

在本合同精确 `cd2caad` 获 Root 转交的 `ACCEPT_IMPLEMENTATION` 后，新增 `readonly_inquiry_contracts.py` 和 `readonly_inquiry_executor.py`、同前缀测试。strict JSON 联合解析拒绝额外字段、重复 JSON key、未知/写工具和混合 final+tool；静态四项 registry 逐次核 read effect。注入的 IdentityPort 在读取前后、下一模型消费旧结果前以及最终披露前重查对象权限；ReadPort 接收同绝对截止和剩余扫描行数，违规超报则结果不披露。参数与工具结果的 SKU、窗口、店铺/来源、报告 ID 均有绑定检查。

全局累计跨度取全部窗口最早 start 到最晚 end，SKU 集合跨提案/结果累计，扫描行数取端口的实际扫描计数而非筛后 facts。模型第三轮再提 Tool 时拒绝执行；批次超过四工具在任何该批读取前拒绝。端口负责在剩余扫描额度内停页，后续真实来源包装仍须单独核验实际扫描统计可信性，不能凭纯执行器测试推导真实 adapter 已满足。

当前输出只有来自已校验端口的数字事实与引用，没有自由模型叙述，不实现任意数值 claim。聚合/币种/零分母由后续确定性 ReadPort 包装提供；本首片只验证引用、精确数值字符串/null 的保留，不宣称已实现电商聚合。测试手工金标为两期 3+5=8 件与库存 12 件；Fake 给确定性事实，Choice Fake 读上一轮真实安全返回的 SKU 再构造下一轮参数，改变 A/B 解析结果确实改变下一调用。

作者检查最终结果：`pytest -q tests/test_p6_readonly_inquiry.py` 30 passed；目标两生产文件及测试的 Ruff/format、mypy（三文件）通过。初轮21项通过；随后 Ruff 的断言/闭包/行长提示及 mypy TypeAdapter 注解错误已修正；新增绑定与边界覆盖后最终30项通过。测试包含 D01 单库存/商品解析后两期订单与库存、D02非法写/额外参数、D03累计限制与第三轮拒绝、D04多观测时间/null/错引及撤权、D05同一中立Fake轨迹模式；真实 provider D05 `NOT_RUN`。未启动服务/PG、未接 Router/Worker/API/迁移或真实 provider；全量 CI 和独立审查由 Root 另行核收。
