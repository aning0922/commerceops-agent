# 电商数据契约与平台适配

状态：Phase 0 设计。Woo 官方文档与 API 版本已核实，未访问任何真实店铺。P0 不请求店铺写权限。

## 1. 端口与数据权威

CommercePort 提供 `list_products`、`list_order_lines`、`list_refunds`、`get_inventory` 和 `capabilities`。所有列表统一返回 items、next_cursor、source、observed_at、complete、warnings；分页游标为适配器内部不透明值，核心不能解释 Woo page。

领域服务只接受标准模型；HTTP 状态、平台错误码、SDK 对象在 adapter 内映射。可复现测试以相同输入跑 Mock 与 Woo 录制响应的合同测试。模拟补货任务与真实测试订单永不混为同一来源。

| 模型 | 必需字段与语义 |
|---|---|
| Product/SKU | source、shop_id、product_id、variant_id?、sku_key、sku_label?、title、active、stock_pool_key；唯一身份依赖平台 ID，SKU 文本可空/重复 |
| OrderLine | order_id、line_id、sku_key、status、created_at、paid_at?、quantity、net_amount、tax_amount、currency |
| Refund | refund_id、order_id、created_at、refund_amount（归一成正数）、currency、关联原 line_id 与 refunded_quantity? |
| Inventory | sku_key、stock_pool_key、manage_stock、available_stock?、stock_status、backorders、stock_semantics、observed_at、source_version? |
| Provenance | source_kind=mock/woocommerce_test、fixture_version?、captured_at、raw_hash、quality_flags、schema_version |
| Error | code、safe_message、retryable、provider_code?、request_id?、partial_page?；禁止暴露认证信息 |

不人为构造 Woo 不提供的 reserved 或可靠在途库存。核心按 adapter 明确的库存语义计算，不能再减一次已由平台扣掉的订单。共享父商品库存要识别同一个 stock_pool；P0 对无法准确聚合的共享库存池仅生成“需人工核对”，不对每个变体各生成一份补货。

未知在途保留 `inbound_units=null`，计划单独记录 effective_inbound_units=0 和每 SKU 的 required_assumptions；只有 PRD 4.1 定义的当前版本显式确认才允许创建内部工作项。确认不是平台在途事实，不能回写来源为已知零；执行前在途状态变化必须重批。内部项完成/关闭也不改变平台库存或在途字段。

## 2. 可复现 MockCommerce

未来 fixture 固定 `dataset_version=inventory-v1`、随机种子、业务时区 Asia/Shanghai、冻结 now（如 `2026-10-08T10:00:00+08:00`）。所有日期从显式 clock 生成，不用当前系统日期让测试每天变化。提供 fixture manifest、预期 totals、原始数据及黄金结果。

| 场景组 | 数据 / 行为 | 预期 |
|---|---|---|
| 正常 | 高销量低库存、正常覆盖、多个变体 | 风险与数量固定可复核 |
| 空数据 | 真正零订单、零商品、无风险 | 与 HTTP 失败区分，不伪造建议 |
| 边界 | 零销量、零/负库存、null 库存、补货线等值 | 分类明确；unknown 不当 0 |
| 订单 | pending、processing、completed、cancelled、failed、refunded、on-hold | 按口径纳入或排除 |
| 退款 | 整单、部分、纯金额、跨期、退款未回库 | 不重复减件数/金额，不凭退款修改库存 |
| 标识 | 空/重复 SKU 文本、父子库存、已删商品引用 | 用平台 ID 关联，异常显式展示 |
| 数据质量 | 非法币种、小数件数、缺失时区、NaN、bool 数量 | 拒绝或隔离，不能静默 coercion |
| 分页 | 两页重复 ID、漏页、中途新增/修改、相同时间戳 | 去重、重拉或 incomplete，不能当完整 |
| 故障 | 第 N 次调用超时/429/500、恢复后成功 | 持久重试可预测，call counter 可重置 |
| 执行 | 重复消息/审批、返回前断线、已有开放补货项 | 内部唯一执行，未知外部结果独立处理 |

Mock 本体先用 Python adapter；HTTPX MockTransport/小型测试服务验证真实网络 adapter 行为。无需给每个 mock 场景部署一套电商服务。真实店铺验证用独立 WordPress+Woo 测试库，绝不在生产店 seed。

## 3. WooCommerce 已验证基线

官方推荐管理接口 `/wp-json/wc/v3`。Store API 面向顾客购物车/公开商品，不能替代后台订单与库存管理 API。HTTPS Basic Auth 使用 consumer key/secret；key 的权限与所属 WP 用户权限共同生效。选择只读 key，日志不得记录 URL 中的密钥，不使用 query string 凭据作为默认补救方案。来源：[REST v3](https://developer.woocommerce.com/docs/apis/rest-api/v3/)、[API 分类](https://developer.woocommerce.com/docs/apis/)、[认证](https://developer.woocommerce.com/docs/apis/rest-api/authentication)。

API 前提包括正确固定链接、可访问的 WordPress/Woo 版本与 REST 路由。获取真实测试店版本、插件清单与 `/wp-json/wc/v3` index 后再锁定兼容性，不把 REST v3 误认为 WooCommerce 软件版本 3。

| 标准字段 | Woo 来源 | 适配要点 |
|---|---|---|
| sku_key | product.id + variation.id | variation_id=0 使用 product；不可只用 sku 字符串 |
| quantity / amount | orders.line_items.quantity/total/total_tax | total 为行折扣后的未税金额，税额单列；Decimal 解析 |
| 状态 | orders.status | 原始状态保留；未知插件状态不猜 |
| 日期 | date_created_gmt/date_paid_gmt/date_modified_gmt | `_gmt` 优先，明确 UTC；缺失时结合店铺时区，歧义需告警 |
| 库存 | products/variations.manage_stock, stock_quantity, stock_status | null 不代表零；需识别变体是否由父级管理 |
| 退款 | orders/{id}/refunds 与关联 line_items | 独立金额、数量和回库标识；负数源值归一化并验证 |

来源：[Orders](https://developer.woocommerce.com/docs/apis/rest-api/v3/orders/)、[Products](https://developer.woocommerce.com/docs/apis/rest-api/v3/products/)、[Refunds](https://developer.woocommerce.com/docs/apis/rest-api/v3/order-refunds/)。字段存在不代表测试店插件实现完全一致，必须采样核对。

## 4. 统计口径与时间边界

P0 v1 采用**创建时间窗口内、采集时状态有效的订单原始需求量**，报告写明“有效下单件数”，不冒充支付时间口径。

- 纳入 processing/completed；refunded 若存在明确已付款/已完成证据，原成交数量纳入需求，退款件数独立展示；缺少证据的状态标为需核对。
- 排除 pending/on-hold/cancelled/failed/trash。自定义状态需在店铺映射配置中明确决定，默认不纳入。
- 窗口 `[start,end)` 按店铺时区换算到 UTC，先服务端日期过滤再客户端边界校验；处理秒/毫秒精度，避免 end 包含重复。
- 退款不是销量需求的简单负数：需求 gross_units、窗口订单相关 refunded_units、net_units 分列；纯金额退款 quantity=null，不按价格猜退款件数。
- 库存为采集时点观测值，销量为过去七个完整日；这是简化启发式，不是完整库存流量平衡或预测。停售/促销/缺货截断需求均加质量说明。

P1 支付日报必须独立定义支付时间口径。只用订单 `after/before` 创建时间筛选会遗漏“很早创建、今天付款”的订单；不能由字段 `date_paid` 存在推断服务端一定支持按其过滤。小测试店可首次全量分页导入后本地按 paid_at 过滤，并用修改时间重叠窗口刷新状态/退款；若目标店端点不支持所需增量过滤，则限量全量扫描或显式声明未覆盖，直到验证完成。

P1 指标最小集：支付订单数（distinct）、商品净额（折扣后未税）、税、运费、当日实际退款额分别展示；客单价明确分子/分母，分母为 0 返回 null；不称为利润。跨期退款用退款发生日计数，订单 cohort 退款与现金流退款不混算。

## 5. 分页、误差与一致性

REST API 默认分页，可用 page/per_page，读取 X-WP-Total/X-WP-TotalPages/Link；不能仅取第一页。固定排序并以稳定资源 ID 去重，分页总数变化、重复/缺口、达到配置页数上限均记录完整性问题；获取所有页成功后才提交完整 snapshot。若跟随 Link，只允许原店铺 host 和认证范围，防止跨 host 携带凭据。参考 [官方 REST API 总览](https://developer.woocommerce.com/docs/apis/rest-api/)。

Woo 多请求不构成数据库一致快照。保存 collection_started_at/collected_at 和 consistency=observational，重读有变更标记的资源并在不稳定时最多重采一次；仍不一致则停止生成可执行计划。稳定分页计数不能证明严格快照。本项目以可控测试店和短采集窗口验收，不承诺生产高并发时的库存锁定。

## 6. 请求错误、重试与执行

401/403 为凭据或权限错误，停止并提示配置；400/404 通常需纠正请求/资源；429 尊重 Retry-After；5xx/读取超时才进入有上限重试。JSON schema/金额/时间解析失败为数据错误，不能伪造空列表。TLS、DNS、分页、HTTP status 和业务 error.code 分开记录。

暂不引入第三方 Woo Python SDK：本项目只需要少量只读端点，HTTPX + Pydantic 可统一超时、脱敏与标准错误；优先直接适配官方 REST 文档，避免再包一层不确定维护状态的 SDK。

内部补货用例位于 application/replenishment，不属于 CommercePort。无论 Mock 还是真实测试 Woo，批准之后只创建 PG 工作项并同步 Bitable；Woo API key 继续只读。真实库存变更或采购集成属于后续单独评审范围。

## 7. Phase 5 / M2 的 Woo 接入验证清单

锁定店铺版本与插件；HTTPS key 认证；分页超过一页；跨时区订单；变体/父库存；空 SKU；退款金额/数量；错误与超时；只读权限确实禁止写入；标准模型输出与 Woo 后台样本核对。保留脱敏录制响应而非客户数据；当前这些均未实测。

M1 首个可面试版本采用 MockCommerce，真实飞书审批必须验证；不以 Woo 待配置阻塞 M1，也不能把 Mock 结果称为真实店结果。Phase 6 动态只读展示复用此契约，白名单参数和范围由服务端限制，不向模型暴露 Woo 原始请求或任何写接口。
