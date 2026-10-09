# P2-01 Commerce 合同与 inventory-v1 冻结样本

日期：2026-10-10（Asia/Shanghai）。授权来源：[Issue29](https://github.com/aning0922/commerceops-agent/issues/29) 的当前授权段及本实施会话的人类任务输入；历史“等待 Phase2 授权”不作为本次阻断。开工基线 main `f19281f1163f828448ad9404620d68e0f1afaa66`，隔离 Worktree `/Users/aipuli/.codex/worktrees/5fdb/commerceops-agent`，分支 `codex/phase2-inventory`。本包仅实现标准输入/端口/Mock 和冻结 fixtures，独立审核由既有总控协调。具体运行模型及推理档位在本会话工具上下文不可核实，记 `not_observable`，不冒称合同推荐配置。

## 交付与依赖方向

- [领域值对象](../backend/src/commerceops/domain/commerce_values.py)：严格整数、平台 ID 身份、Decimal、IANA/UTC、自然日窗口与 canonical-facts-v1；仅 Python 标准库。
- [标准 DTO](../backend/src/commerceops/application/commerce/contracts.py) 与 [五个只读端口](../backend/src/commerceops/application/commerce/ports.py)：Pydantic strict/frozen/extra-forbid；adapter 对象不进入领域。
- [MockCommerce](../backend/src/commerceops/adapters/commerce/mock.py)：进程内确定性实现，无 DB、模型、网络、审批/补货副作用。复用既有依赖，未改锁文件、迁移、Worker/Graph、飞书、UI、AGENTS 或规划文件。
- [原始样本](../tests/fixtures/commerce/inventory-v1/datasets.json)、[纸面金标](../tests/fixtures/commerce/inventory-v1/goldens.json)、[manifest](../tests/fixtures/commerce/inventory-v1/manifest.json) 与三个离线测试文件，均为合成数据。

P202 规则计算、P203 采集用例/迁移/API 和 P204 模型说明保持 `not_implemented`。没有新增任务状态、补货项、approval/outbox 或通用 Mock 服务/调度平台。`open_items` 只存在于原始 fixture 中，供后续规则包只读输入，不是已实现业务实体。正式 T2～T6、真实 Woo/飞书业务测试、模型调用与阶段 Gate 均不由本包外推。

## 标准合同

五端口为 `list_products`、`list_order_lines(window)`、`list_refunds(order_ids)`、`get_inventory(sku_key)`、`capabilities`。列表 Page 含 `items/next_cursor/source/observed_at/complete/warnings/error`；库存用单资源 InventoryResult，能力明确 read-only、observational、opaque_cursor、order_cohort。协议同步调用只适用于当前进程内 Mock；真实网络 adapter 在后续包按同一标准输出转换。

`source` 固定店铺、IANA 时区、币种及 Provenance；每条记录另有 source Provenance，保留 source_kind、fixture_version、captured_at、raw_hash、quality_flags、schema_version。manifest 的 file hash 为原始文件字节 SHA256；记录 raw_hash 为源记录 canonical 内容 SHA256；二者不可互换。DTO 时间归一成 aware UTC，fixture 的显式冻结 now 为 `2026-10-08T10:00:00+08:00`。没有读取机器当天时间。DST场景是历史边界测试，窗口推导另使用goldens中的显式March clock，不作为同一演示now下的最近七日业务结果。

平台 ID 保持字符串。`sku/{escaped_shop}/{escaped_product}/p` 为独立商品，`sku/{escaped_shop}/{escaped_product}/v/{escaped_variant}` 为变体，每个分段独立 percent-escape；空 variant 无效，缺省为 null。SKU 文本可空、null 或重复，不作为身份。`pool/{escaped_shop}/{escaped_owner}` 为库存池，可被父商品与变体共用。真实 Woo 的 variation_id=0 归一为无变体须由未来 Woo adapter 完成，本包不声称已验证 Woo 映射。

金额仅接受有限 Decimal 或无指数的十进制字符串，最多六位小数、绝对值小于 10^14，对齐设计 numeric(20,6)；拒 float/bool/NaN/Infinity，不隐式量化。JSON 金额为规范十进制字符串。当前冻结能力支持 ISO 4217 子集 CNY/USD/EUR/JPY/GBP/AUD/CAD/HKD/CHF/SGD，其他币种显式报 UNSUPPORTED_CURRENCY，演示样本单一 CNY。fixtures 加载拒订单或退款币种与店铺币种不符，没有跨币合并功能。扩大币种集合需要明确合同和测试更新。

件数只接受 Python/JSON 整数，拒 bool、字符串、小数、NaN。订单 quantity>0，退款件数允许 null/0；库存允许负/null。未知库存或在途必须有 reason；已知不能同时携带未知 reason。在途另有 reliable/unknown quality；unknown 不转换成已知零。退款金额为已归一的非负数；源平台负值归一在未来网络 adapter 内做，本 Mock 使用已归一合成数据。无行的纯金额退款必须有 quantity_reason；restocked 可 null/false/true，不凭金额猜件数或回库。

Mock 的 order 端口仅按 created_at 的 `[start,end)` 过滤，保留全部采集时原始 status、paid_at、completed_at；不在 adapter 内执行库存规则。processing/completed 纳入与 refunded 的付款/完成证据资格，以及自定义状态需核对等口径，冻结在金标及未来 P202 合同中。退款接口为指定订单 cohort，不按退款发生日裁剪：窗口订单的窗外退款仍返回，旧订单的窗口内现金流退款不混入。库存直接返回 adapter 已调整的 available_stock，没有二次扣销量或退款。

## 完整性、游标与故障

Page.complete 表示该查询在收齐所有页后可认定完整。非末页为 false、有 next_cursor；调用方必须累积所有成功页并保留任一错误/警告。末页 true 仅表示当前 Mock 脚本无已知异常且所有页可用，不证明真实平台原子快照。库存 null 或 pool_allocation=unresolved 均 complete=false 且有硬质量警告；未知在途本身保留 null/reason/quality，不伪造成已知零。订单引用不存在的商品为 DELETED_PRODUCT 并保留订单行。

游标由 Mock 解释并绑定 endpoint、查询、source 内容、page_size 与故障行为。核心只回传，不解析页号；游标不是授权凭据。坏游标、不同查询/版本/端点/页大小的游标安全拒绝；不调用来源计数。冻结文件顺序定义稳定页顺序，订单行唯一键为 order_id+line_id；商品为 sku_key、退款为 refund_id。原始 fixture 重复 ID 加载失败，故障脚本另模拟第二页重复上一页 ID，返回时去重并持续保留 DUPLICATE_ID。

Behavior 可对单一端点注入第 N 次调用 TIMEOUT/429/500，计数包括该端点的成功与失败调用；reset_call_counts 清空计数，复现同一脚本。失败返回空 items、complete=false、PARTIAL_FAILURE、安全 Error 和当前游标，重试同一页下一次可成功。首个失败页的游标为 null，必须结合 error 判断，不与完整空数据混淆。429 提供固定测试 retry_after_seconds=2；本包没有睡眠、自动重试或持久恢复实现。

第二页重复/漏页/修改，以及 max_pages 容量上限用最小脚本模拟；警告从首个响应起保守保留，末页也 false，不能因最终无游标而伪称完整。中途修改订单数量或商品标题/退款标记后对应记录 raw_hash 变化；脚本不是生产网络故障证据，也没有重采/事务快照能力。真正空产品、空订单、空 cohort 是 error=null、items=()、complete=true。加载、schema、金额、时间或币种错误抛固定分类 CommerceFailure，不把错误伪造成空结果，不暴露原值、本地路径或平台 body。

## 静态金标与 canonical 约定

版本为 dataset/fixture=inventory-v1、schema=commerce-v1、rule=inventory-rule-v1、canonical=canonical-facts-v1，seed=not_used。manifest 记录25场景、原始/金标哈希及纸面来源。基础/等值/正常/负库存/已知与未知在途、循环小数边界和混合退款的数字来自 Issue29 与本次人类授权输入；扩展项由实施 Agent 手工复算，独审及额外人工签收仍 pending。金标 JSON 为静态字面量，生成冻结文件时未导入或调用任何待测模块，测试也不动态写回金标。

| 样本 | 纸面期望（均 analysis-only，执行资格 false） |
|---|---|
| gross70，A20，已知在途0，3/7/2 | D10，T120，trigger50，risk，Q100，coverage2 |
| A50 / A51 | 等值 risk/Q70；A51 normal，无自动建议 |
| A-5 / A0 | stockout/Q125/coverage=null BACKLOG_STOCK；A0 Q120/coverage0 |
| A20，可靠在途30 | Q70，effective30 |
| 在途未知 | raw null，effective0，估算100，required_assumptions 有本 SKU 键，执行资格 false |
| gross8，3/2/2，A5 / A6 | D8/7，T8，trigger40/7；A5 risk/Q3/coverage35/8，A6 normal/无建议 |
| D0 / unknown stock / negative stock | coverage null；分别保留 NO_RECENT_DEMAND / UNKNOWN_STOCK / BACKLOG_STOCK；D0无自动建议 |
| gross70，已知退款2另有未知数量退款 | known2，quantity_complete=false，完整 refund/net null，D仍10 |

D0 且负库存的静态扩展样本以 NO_RECENT_DEMAND 为 coverage 原因，同时保留负 A/manual_check；这一优先级须由 P202 独审核对，不改变来源库存。来源不完整、null库存、共享池无法归属及已有open项的硬阻断分别有fixture/Mock证据或静态期望；本包没有实现候选资格服务或执行授权。没有将 open 工作项当在途扣减。

canonical JSON 使用排序字符串键、无空白、UTF-8、ensure_ascii=false、null保留、数组原顺序；Decimal 去掉无意义尾零、负零为 "0"；aware时间转 UTC ISO（零微秒省略微秒）且 Z 后缀；精确比值为已约分的 numerator/denominator 十进制整数字符串对象；float/非字符串key拒绝。facts_hash=SHA256(canonical_bytes)。展示舍入不会进入本包的事实编码；P202 展示精度版本尚待冻结。没有为金标新增生产 D/T/trigger/Q/risk/coverage 计算模块。

## 实际验证与待审范围

source_mode=mock，model_mode=not_used，approval_mode=not_used。锁环境用 `uv sync --frozen`，Python3.12.13、uv0.11.25，Pydantic2.13.5、pytest9.1.1、ruff0.16.10、mypy2.4.0；项目工具用 `python3 -m scripts.bootstrap_tools` 下载并校验固定 Node/Gitleaks。未改全局环境。

实际专项命令：

```sh
uv run --frozen ruff check backend/src/commerceops/domain/commerce_values.py backend/src/commerceops/application/commerce backend/src/commerceops/adapters/commerce tests/test_commerce_contracts.py tests/test_commerce_mock.py tests/test_commerce_fixtures.py
uv run --frozen ruff format --check backend/src/commerceops/domain/commerce_values.py backend/src/commerceops/application/commerce backend/src/commerceops/adapters/commerce tests/test_commerce_contracts.py tests/test_commerce_mock.py tests/test_commerce_fixtures.py
uv run --frozen mypy backend/src/commerceops/domain/commerce_values.py backend/src/commerceops/application/commerce backend/src/commerceops/adapters/commerce tests/test_commerce_contracts.py tests/test_commerce_mock.py tests/test_commerce_fixtures.py
uv run --frozen pytest tests/test_commerce_contracts.py tests/test_commerce_mock.py tests/test_commerce_fixtures.py -q
```

专项结果：passed，124 tests（最终专项复跑0.29秒）；ruff与strict mypy通过。初轮自检出现类型/lint失败后已修正，未将失败命令记为通过。fixtures 的纸面复算测试是合同核对，不是 P202 实现验收。测试覆盖正常/真正空数据、全部状态与refunded证据、负/零/null库存、纯金额/部分/整单/跨期cohort退款、空重复SKU/已删商品/共享池、UTC与DST起含终排、异常币种/件数/金额、schema/hash/重复JSON键/NaN失败、分页故障及计数恢复。

仓库全套 `uv run --frozen python -m scripts.check` 已实际 passed（75.26秒墙钟）：全局ruff/format、strict mypy、Markdown、锁一致性、469离线测试通过/79非离线未选择（52.91秒、既有SDK两项deprecation warnings）、Node安装/工具/typecheck、前后端漏洞查询通过，Python audit 90包零已知漏洞。初次全套检查因6个新合成SKU标识被generic-api-key扫描命中而failed（9.21秒），确认均为本包合成标识后缩短演示父/变体ID、重冻结manifest；未改scanner规则/豁免，后续当前/index/完整可达history扫描均零命中。文档48文件零错误，git diff检查通过。暂存后追加index敏感扫描及远端 CI 的精确结果由本包 PR/Issue29 的提交回执记录，避免在代码提交前编造冻结 SHA。独立 Review pending，由总控读取冻结提交协调。DB/模型/平台实测为本包 not_run；远端现有 CI 仍原样运行其真实 PG 门禁，不改 CI 跳过。

估计6～10有效开发小时保留为规划值。本会话开始核对约2026-10-10 03:12（Asia/Shanghai）；Agent实际墙钟、机器测试耗时、CI等待在PR回执分别记录，不能把6～10小时伪填为人工工作量。D1仍10-10、D30仍11-08，P201提前开工不改D3～D6目标。
