# P6 动态只读 Tool facade 与确定性答案合同候选

2026-11-03（台北）。状态 `DESIGN / REVIEW_REQUIRED`。消费 [受限查询合同](p6-readonly-inquiry-v1.md)的 `ReadPort`，不扩大四项工具集合。本文件是下一片接口设计；`f0ceb20816508cb78155258416157c6dcb4480f4` 的执行器及测试仍按原提交交 Root 独审，本批未修改其源码。真实模型、来源 API、Worker 和对外业务路由均待后续单独接线。

## 现有端口事实与待冻结接口

[CommercePort](../../backend/src/commerceops/application/commerce/ports.py) 已提供分页 `list_products`、按 `Window` 的 `list_order_lines`、按订单 cohort 的 `list_refunds` 和单 SKU 的 `get_inventory`。MockCommerce 的订单窗口按 `OrderLine.created_at` 过滤；它的退款查询按 `order_id`，不以退款发生日裁剪。`Page.complete=false` 可以是正常的中间页，也可以是终页缺损；只有最终页 `next_cursor=None、complete=true、warnings/error 均空` 才证明该次完整遍历。[原 Commerce DTO](../../backend/src/commerceops/application/commerce/contracts.py) 带来源、观测时间、金额 Decimal、币种及质量标志，适配器原始对象不能直接交模型。

建议新增一个仅处理四个工具的 `CommerceReadFacade`，实现当前 [ReadPort](../../backend/src/commerceops/application/commerce/readonly_inquiry_contracts.py) 所需 `read(context, call, deadline, rows_remaining)`。它只接收服务端注入且已绑定身份/组织/店铺的 `CommercePort`、单调时钟和当前对象读权限，不能接收模型提供的来源 URL、Woo 配置、裸 SQL 或原始平台 cursor。端口返回 [ReadResult](../../backend/src/commerceops/application/commerce/readonly_inquiry_contracts.py)，填完整的 `tool_call_id / shop_id / source_binding / snapshot_id / as_of / scanned_rows / sku_keys / facts / windows / report_id`，由执行器再次绑定核验。结果只包含脱敏数字事实和安全的商品标识，不带客户、地址、电话、邮件或原始订单响应。

当前 `ReadResult` 的 `complete` 是执行器的安全门，返回 false 会终止本次询问。底层 `InventoryResult.complete=false` 也可能表示 **库存数量未知但行已成功读取**，因此不能机械映射两者。下一片须在 Root 审查后冻结一项显式语义：`ReadResult.complete` 仅表示所需来源遍历/读取成功且无结构性缺口；业务质量另增固定 `quality_flags` 与 null Fact。若尚不能安全区分“未知库存”与来源不完整，就返回 `source_incomplete` 并显示明确原因，不能谎称有完整数字。该 DTO 增量需要 Root 对原冻结执行器的独立增量审查。

## 四类 facade 行为

| Tool | 有界读取 | 可向模型提供的安全结果 |
|---|---|---|
| `commerce.read_products` | 从服务端绑定的 `list_products` 从首 cursor 穷尽；每页检查来源、店铺、cursor 前进、完整性及截止。按 Unicode NFKC + casefold 的确定性比较分别匹配精确 SKU 与商品名，保留全部匹配集合；任何重名/变体歧义返回澄清，不选第一项 | 限定 `sku_key`、脱敏名称、产品/变体安全 ID 与来源引用；原商品描述中的指令只作为不可信数据，不进系统 prompt |
| `commerce.read_orders` | 对 1–2 个已校验 UTC `[start,end)` 窗口逐个完整 `list_order_lines`；旧 `created_at` 口径不变。每页先把**扫描的所有订单行**计入询问级剩余额度，再筛选 SKU；窗口间重叠、订单 ID/行 ID 重复应按确定性规则拒绝或去重且保留异常说明，不能双计 | 按窗口、SKU、币种的订单行数、售出件数与已定义金额字段；每个窗口独立 `as_of` 和完整性。不会返还客户信息或原订单行 |
| `commerce.read_inventory` | 对每个已解析 SKU 调 `get_inventory`，继续检查共享库存池与原 `available_stock` 语义；数量 null 保留 null。每个 SKU 观测时间独立，跨时点不拼作原子快照 | 可用库存、在途及质量原因、stock pool 安全引用；在途未知不填 0，池分配未解不拆成多变体库存 |
| `reports.read` | 注入原授权报告读取端口，使用当前 principal、组织、店铺、report_id 与版本重查；只返回当前有权的冻结报告事实 | `report_id/snapshot_id/facts_hash`、指标事实及内部引用；不得调用重算、采集、发消息、审批或根据旧缓存越权 |

`read_products` 的商品名过滤目前不是 CommercePort 原生参数，必须在有界完整遍历后做；若容量/时限不足，返回不完整并停止，不把前几页说成“唯一匹配”。模型提议的 SKU 也要与当前店铺商品目录核实。`read_orders` 的 SKU 过滤同样只能在完整分页计数后做；`rows_remaining` 为执行器提供的本询问剩余**实际扫描行数**，facade 需要在每次取页前检查页/字节/剩余计数，页返回超过剩余额度时停止并报告不完整，不把筛后数作为 scanned_rows。若底层接口无法按剩余量限制一页，须预留整页容量或在下一页前停止，不能越上限后仍称合格。

每次翻页都检查同一来源绑定、游标未循环、观测时间语义、`Page.error/warnings`、绝对截止与适配器自身请求/页/字节上限。中间页 `complete=false` 且有合法 next_cursor 不是错误；终页 `complete=false` 或带 warning/error 不能产完整报告。对所见的所有行持续校验 shop/source、一致币种及唯一订单行身份；部分失败保留安全错误码/扫描行数而不返回可误用数字。同步 CommercePort 调用应由受控包装执行，并用独立绝对截止及来源自身超时确保外层 `asyncio.timeout` 不被线程中的阻塞 I/O 绕过；无法证明及时停机的来源保持禁用。

MockCommerce 可以先在新 owned Fake 上验证这些边界，源配置由服务端固定的 fixture/source binding 给定。后续新 owned Woo 测试来源仍须同店铺绑定、低权只读配置和原自身 18 秒/页数/请求数上限；不从历史 Woo 测试店授权推导新的在线窗口。当前没有真实来源读取或平台凭据授权。

## 两期销量、退款和库存的口径

初版只接受 1–2 个明确窗口，跨两个窗口的并集跨度仍受执行器 30 天上限；同一区间的多个调用也计入询问级全局跨度。对一件商品的“两周相比”须固定两个不重叠的七个完整店铺自然日窗口，再转 UTC 边界，标注店铺时区及结束不含。不能按浏览器时区偷换日期。

先按订单 `created_at` 落窗口计订单行，再用完整的订单 ID cohort 查退款。`Refund.created_at` 可以在窗口外，仍归到原订单 cohort，并明确写“对应这些订单的退款”，不能称“本窗口发生的退款”。`list_refunds` 留在 facade 内部，不加入模型工具白名单。退款分页也计入独立来源页/请求/截止容量；询问级 `10,000` 的“订单行”上限不因为退款查询重置。若需要更小的总数据条数限制，由 Root 在实际来源接线时冻结，不能忽略退款容量。

所有数量求和用整数，金额按 `OrderLine.net_amount` 与 `Refund.refund_amount` 分别以 Decimal 汇总并按币种拆开；当前不定义利润或未经业务确认的净收益。部分退款、未知退款数量、跨币种和同一订单重复行均明确列质量状态，不能把缺失转 0。比较率只有前期分母完整且非 0、两个窗口同币种同口径时计算，否则是 `不可计算`，不补 `0%`。报告事实已有其冻结规则版本，不在此层重算替换。

库存来自每次独立观测的 `Inventory.observed_at`。商品、订单、退款、库存和报告若各有不同 `as_of`，答案逐项列出；不能用“截至最新”掩盖旧值。不同来源快照不可称同一个事务快照。来源质量旗标、空且完整的集合、未知数值、分页失败和对象无权四种情况各自保持不同状态。

## Fact、引用与可读答案

每条 Fact 的 ID 应由服务端规范化 `{source_binding, tool_call_id, snapshot_id|report_id, metric, sku_key?, window?, currency?, rule_version}` 后形成稳定摘要，并在本次 `ReadResult` 中唯一。当前 DTO 只有 `evidence_id/metric/value/unit/currency`，不足以在单个 Fact 内复原 SKU、窗口和独立 `as_of`；下一片建议补 `sku_key? / window? / as_of? / quality_flags` 或新增一个窄 `Evidence` 映射，保持向旧执行器只暴露可校验的精确引用，不让模型发明 URL。新增结构须与 Root 审查后的执行器绑定规则一并评估，避免同名 Fact 跨工具或跨窗口碰撞。

最终回答使用 `Outcome.evidence_refs` 选择本询问的已授权 Fact。纯 `AnswerRenderer` 在**最终对象权限重查后立即**按固定 metric 词典和稳定顺序渲染中文句子：例如“SKU-A：可用库存 12 件（观测于…，来源…）”；两期完整销量为“前期 3 件，本期 5 件，变化 +2 件”；金额始终带原币种。数值只取确定性 Facade Fact；模型没有自由数值插入位，无法将库存 12 改写成 120。未知显示“未知（原因…）”，证据不足显示“证据不足：缺少…”，零分母显示“不可计算（前期为 0）”。每句跟随内部证据引用，点击时再次检查当前读取资格；长答案只按固定布局分段，不省略异常、窗口或币种。

若 renderer 在纯执行器返回后异步等待、排队或缓存，必须重新核当前身份与每个报告对象授权；不能只信执行器最终一刻的检查。拒绝或失败结果只给安全原因及可重读的原请求标识，不输出 `Outcome.results` 的残留数据。展示模式为 `offline_stub / actual_provider` 及真实 usage/估算成本；当前纯切片只有 `offline_stub`，不得显示成已跑真实模型。

## 接线责任与可复核 Fake 金标

建议独占的新文件为 `backend/src/commerceops/application/commerce/readonly_inquiry_tools.py`（只含四个 facade 分支及确定性聚合）、`readonly_inquiry_render.py` 和 `tests/test_p6_readonly_tools.py`；若 DTO 必须增量，仅触及既有同前缀 contracts/executor 与其测试，先由 Root 协调独占与独审。Facade 不建通用 registry DSL，也不增加任意 HTTP/SQL/shell 出口。实际 `reports.read` 对象授权、当前来源工厂、API/Worker、共享持久化及真实模型 admission 由 Backend/Root 统一接入；本合同不启动这些入口。

Fake 金标采用同一执行器、固定 Choice 脚本和真实 MockCommerce fixture：已知 SKU 仅库存；商品名唯一时先穷尽商品再依据解析 SKU 查两期订单与库存；把产品解析 SKU 从 A 改为 B，下一轮参数及引用必须随之改变；两个同名商品必须澄清；分页中间页、末页失败、cursor 循环、11,000 扫描/10 筛后、跨时区与两个窗口总跨度、退款晚于订单窗口、未知库存/null、混币种、重复订单行、跨店/撤权、模型错引均逐例查金标。手工真值写成独立 fixture 明细和期望表，不由生产求和函数生成同一套 expected。替身通过只证明离线合同；真实 provider D05、真实来源和正式 Web/飞书完整 Gate 均 `NOT_RUN`。
