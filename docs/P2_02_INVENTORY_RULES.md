# P2-02 确定性库存规则与 analysis-only facts

日期：2026-10-10（Asia/Shanghai）。总控在P201冻结eddda43独立复审解除3P2、精确CI37982390868成功后按用户已有01→04授权接续P202，正式复审见[PR30 review](https://github.com/aning0922/commerceops-agent/pull/30#pullrequestreview-5474714719)。本包同顶层、Worktree `/Users/aipuli/.codex/worktrees/5fdb/commerceops-agent`、`codex/phase2-inventory` / [Draft PR30](https://github.com/aning0922/commerceops-agent/pull/30)，main基线仍caffe117，已合入的交接文档不改写。

## 边界与文件

仅新增 [纯领域规则](../backend/src/commerceops/domain/inventory_rules.py)、[analysis-only输入/事实DTO](../backend/src/commerceops/application/commerce/inventory_facts.py)、[纯聚合函数](../backend/src/commerceops/application/commerce/inventory_analysis.py)、[规则测试](../tests/test_inventory_rules.py)、[分析测试](../tests/test_inventory_analysis.py)及本说明。domain仅标准库与已审值对象，不导入Pydantic/SDK/DB/LangGraph；application使用已有Pydantic标准DTO。

没有采集循环、migration/SQL/API/persistence、Graph/Worker、plan/approval/outbox/补货实体、飞书/UI、依赖/锁或模型调用。OpenWorkItemInput只是已有mock fixture的只读观测，不是业务实体/创建方法。P203尚未开始。已审25组原始datasets/goldens/manifest字节保持不变；扩展边界只在新测试内构造自有标准输入，不改金标迎合算法。

## 规则与参数

版本为inventory-rule-v1；L/R/S只接受严格非负整数，拒bool/字符串/小数/NaN/Infinity/负数，没有另造天数或数量上限。默认3/7/2固定标记demo_assumption，不能冒称生产配置或授权；不支持其他rule/parameter_mode或未知参数。输入数量复用已审整数语义，available_stock保留负/null，在途非负/null。

D=gross_units/7，以Fraction求T=ceil(D*(L+R+S))、trigger=D*(L+S)。D>0/A<=0为stockout，0<A<=trigger为risk，A>trigger为normal；D0/A>0为no_recent_demand，D0/A<=0为manual_check。只无硬阻断的risk/stockout计算Q=max(0,T-A-effectiveInbound)；normal即使T>A也不自动建议，D0不猜Q。Q=0可保留数学结果，但不形成正数候选。

coverage用精确A/D；D0优先NO_RECENT_DEMAND（包括已审D0负库存样本），库存null为UNKNOWN_STOCK、负库存为BACKLOG_STOCK，均null；A0且D>0为精确0。完整需求未知则D/T/trigger/coverage为null，coverage_reason=INCOMPLETE_DEMAND；known_gross_units仍展示已观测部分，不冒称完整gross。

在途unknown保留raw null/reason、effective0；仅产生正数且无硬阻断的估算草案时生成`inbound_unknown_zero:{sku_key}`。normal、无需求、零建议或硬阻断不生成无用途确认提案。没有“已确认”字段或确认动作，全部item固定analysis_only=true、execution_available=false、eligible_for_execution=false；客户approved/role等额外字段拒绝。

## 聚合口径与质量

显式now与店铺IANA时区推导最近7个完整自然日，`[start,end)`；传入不同窗口标WINDOW_MISMATCH并阻断，不按另一个窗口除以7。复用P201已修的首次午夜边界，不继承now.fold。DST历史专用fixture使用其显式历史clock，只验证时间边界，不声称库存审批新鲜度已实现；事实保留库存观测时点/原因/source_version。

按created_at窗口与采集时状态：processing/completed纳入；refunded需付款或完成时间存在且处于created_at至采集时间之间；不可能的未来/创建前时间不作为成交证据。pending/on-hold/cancelled/failed/trash排除；refunded无证据和未知自定义状态进入review_order_ids，该SKU的ORDER_STATUS_REVIEW硬阻断建议，保留明确有效的gross，不猜未知状态。ID集合输出用字符串排序，golden的ID列表按集合语义核对，数值18组按原始字段逐项相等。

退款只关联窗口有效订单cohort，窗外后续退款仍计入，旧订单在窗口内的现金流不混入；不按退款金额推件数/回库，不二次扣adapter库存。known_refunded_units为明确关联已知部分；存在数量null或无行纯金额退款，quantity_complete=false、完整refunded_units/net_units=null；D仍按gross。无法关联原行/累计退款超过原行件数均硬阻断并保留异常，不产出负完整net或错误Q。金额沿用Decimal/JSON字符串合同，本包不汇总支付/退款金额；跨店铺币种的订单或退款全源硬阻断，禁止混币生成完整需求。

分析入口在任何计数/序列化前保留原始类型重验标准输入，含内部model_copy绕过验证的值；bool数量、金额float等不能先被serializer变成“合法”值。安全错误固定INVALID_INVENTORY_INPUT，不回显来源值。Source kind/fixture/schema/captured_at一致性、canonical SKU/pool店铺归属、库存与商品池映射、重复ID、数据来源quality_flags均核对。

集合失败/DUPLICATE_ID/MISSING_PAGE/SOURCE_CHANGED/CAPACITY_LIMIT/PARTIAL_FAILURE等全源硬阻断完整gross/D与建议。保留known部分和显式原因；不能用在途假设豁免。已收齐但库存null、共享归属不明、已删商品引用、未映射状态等按SKU保留hard_blocks。source_complete表示集合/来源一致；complete另表示质量可完整解释；OPEN_WORK_ITEM、INACTIVE_PRODUCT、SCOPE_TOO_LARGE业务阻断本身不伪称分页/采集失败，requires_review保留核对需要。

当前DTO没有可证实的每SKU库存份额/聚合归属证据；同池关联多个SKU或pool_allocation=unresolved均manual_check，不凭exact标签猜池的拆分/代表SKU，不为父子变体重复生成建议。已有open观测按池阻断所有相关SKU，数量只展示、不当可靠在途扣减。Inactive商品不自动建议。源完整的其他SKU可展示其计算事实，执行权限始终false。

20为已有合同候选容量：正数、无硬阻断且可形成估算/在途假设草案的候选计数；20可展示，21以上scope_required=true，保留全部SKU与候选总数、撤下全部正数建议并标SCOPE_TOO_LARGE，不能截前20或暗自执行。没有MOQ/包装/供应商择优等参数。

## 精确facts/hash与展示

schema=inventory-analysis-v1，canonical=canonical-facts-v1；复用已审canonical JSON排序键/UTF-8/null/Decimal规则。Ratio为约分后的numerator/denominator十进制整数字符串。事实绑定Source、window、显式clock、顶层L/R/S/mode/version、全部SKU指标/证据ID/质量/假设、input_hash；空商品报告也绑定参数。

input_hash对标准输入数组按内容排序并归一显式/默认等价窗口；包含原始标准DTO及来源证据。相同来源证据下重排输入/重跑结果逐字稳定，数量/参数/来源变化改变hash。来源raw_hash不同会保留其证据差异，不声称不同采集证据必为同一hash。

展示版本inventory-display-v1为六位ROUND_HALF_EVEN，直接整数divmod精确舍入，无float或提前截断Fraction。display字段排除于canonical facts/hash，展示文本不能回流D/T/trigger/Q或资格；report DTO验证facts_hash与canonical内容一致，JSON回读保持同一事实。

## 实际验证与待审

source_mode=mock、model_mode=not_used、approval_mode=not_used。实际执行配置为总控工具核验gpt-6.1-sol/high；未读取秘密文件或访问旧P1/UX/规划Worktree。预计6～8有效开发小时是规划值，人工工时未报告；本轮从约03:56开始，Agent墙钟/机器/CI等待在PR回执分列，不伪填人工。

专项命令：

```sh
uv run --frozen ruff check backend/src/commerceops/domain/inventory_rules.py backend/src/commerceops/application/commerce/inventory_facts.py backend/src/commerceops/application/commerce/inventory_analysis.py tests/test_inventory_rules.py tests/test_inventory_analysis.py
uv run --frozen ruff format --check backend/src/commerceops/domain/inventory_rules.py backend/src/commerceops/application/commerce/inventory_facts.py backend/src/commerceops/application/commerce/inventory_analysis.py tests/test_inventory_rules.py tests/test_inventory_analysis.py
uv run --frozen mypy backend/src/commerceops/domain/inventory_rules.py backend/src/commerceops/application/commerce/inventory_facts.py backend/src/commerceops/application/commerce/inventory_analysis.py tests/test_inventory_rules.py tests/test_inventory_analysis.py
uv run --frozen pytest tests/test_inventory_rules.py tests/test_inventory_analysis.py -q
```

专项119 passed（最终结果见本包交付回执）、适用ruff/format/strict mypy通过。18组数值金标逐项完全相等；其余状态、空数据、窗口/DST、标识/父子池/open场景语义均匹配，未改已审样本。新增params/件数异常、退款关联矛盾、真实Mock分页故障输入、20/21、硬错误不能假设豁免、重跑/排序/hash/显示隔离、午夜fold与客户审批字段拒绝等回归。初轮104 passed/1 failed揭露JSON serializer先将内部bool转int，已用原始类型重验修复；测试导入/type/lint初轮失败也已修正，以最终结果为准。

首批9ca0的原样scripts.check实际passed（60.97秒）：613 offline passed / 79 deselected、全局ruff/format/strict mypy、51份文档、锁/工具/前后端漏洞门禁通过；初次全套扫描因stock_pool_key字段对应的代码属性表达式被generic-api-key命中failed（8.89秒），核实不是凭据后提取局部pool变量，未改scanner规则/豁免，重跑当前/index/可达history均0。暂存后敏感扫描、精确提交/tree/新CI结果在PR30/Issue29交付回执记录；独立Review由总控安排，作者自检不替代。DB/平台/模型本包not_run；既有CI原样运行其PG基础Gate，不能外推业务/T3/真实模型或P1旧timeout根因。P202提交/PR/CI不代表阶段完成，P203与main业务合并仍待对应门禁/裁决。

提交后交付核对补测嵌套dict内Pydantic实例的source_kind bool，定向修复前实际1 failed（0.08秒）；本地原始类型重验增加dict/list递归，保留容器类型，不让嵌套实例绕过字段验证。此补充用普通后继提交，不改写首批历史；修复后实际119专项passed（0.19秒）、原样全套614离线passed/79 deselected（41.45秒，全套53.88秒）、全部适用门禁通过，当前/index/历史敏感0；最后暂存扫描及最终CI/SHA见新回执，不将9ca0的旧通过外推。
