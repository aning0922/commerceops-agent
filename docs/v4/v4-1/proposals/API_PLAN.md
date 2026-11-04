# V4-1 API、SQL 与导入实施提案

状态：`PROPOSED_FOR_ROOT_CONTRACT_FREEZE`。记录日期 2026-11-04（台北）。本轮只读核查和本文件写入，不包含业务代码、迁移或运行验收。新用户授权覆盖 V41-01—06；本提案等待 Root 冻结接口后才实施。

工作树 `/Users/aipuli/.codex/worktrees/commerceops-v41-api/commerceops-agent`，分支 `codex/v41-api-20261104`，核查 base `1730194028a01ddea0bbc573774d740ea4a29d55` / tree `5f2a92dffb49ef21682077e89459c85db55b668d`。SCHEMA/API 为 schema、SQL、API、seed/reset 兼容的单一 owner。模型费用与实际 token 用量为 UNKNOWN，不启用付费 fallback。

## 1. 输入、六卡与阶段范围

已核资料包 `/Users/aipuli/Downloads/CommerceOps_V4_Codex_Development_Package` 中 `03_delivery/TASK_CARDS.md` 与 JSON 的六张 V41 卡、`PHASE_ROADMAP.md` V4-1、`02_architecture/DATA_AND_API_CONTRACTS.md` 和 `SECURITY_AND_DEMO.md`；并核四份 `docs/v4/baseline/{UI_ROUTES,DOMAIN_SOURCE,PERMISSION_DEMO,API_EVENTS}_CONTRACT.md`。这些基线的旧 PROPOSED/NOT_STARTED 标签保留原时点，现有能力以本次源码为准。资料包建议从 0023 迁移的旧描述已过时：当前 head 为 0024，下一迁移只能为 0025。

| 卡 | owner / 本阶段交付 | 对后端合同的要求 |
| --- | --- | --- |
| V41-01 | WEB：Shell、14 模块导航、主题与错误 | 服务端权限决定数据；规划模块不能假称业务已实现 |
| V41-02 | SCHEMA/API：KPI 和统一经营查询 | 同源、同币种、同快照与指标钻取 |
| V41-03 | WEB：首页及 Copilot 容器 | 真 API；规则分析与真实 read context，provider 调用为 0 |
| V41-04 | SCHEMA/API：商品订单、标签与演示履约 | 原来源只读，内部效果可读回、CAS/权限/回执 |
| V41-05 | WEB：列表、详情、筛选和导出 | 一套后端过滤/分页语义；详情关联相同 SKU |
| V41-06 | SCHEMA/API + QA：CSV/XLSX 导入 | 预览、映射、质量回执、确认后原子导入 |

V4-1 实现商品导入及内部履约，不增加采购、退款、库存流水、客服消息或 Agent 状态机。Copilot 只展示当前已授权对象、引用、规则解释和跳转；文案标明规则分析，不称真实 AI 推理。用户上传的文本始终作为数据，不成为指令或工具权限。

## 2. V4-0 实际结构及复用点

源码证据：`application/v4_demo/{contracts,seed_contract}.py`、`infrastructure/v4_demo_{sessions,store,seed}.py`、`entrypoints/v4_demo_http.py`、`backend/migrations/versions/0024_v4_demo_foundation.py`。以下为静态核查，不冒充本轮 SQL 查询。

| 既有表/结构 | 实际字段与限制 | V4-1 处理 |
| --- | --- | --- |
| `v4_demo_fixture_versions` | 固定版本/生成器、canonical JSON、content_hash、snapshot_at；hash 与 JSON 一致，内容 ≤1 MiB | 保持不可变基线，不重生成或改固定 digest |
| `v4_demo_tenants` | 每 tenant 一个 organization，fixture_version/digest、reset_epoch、绝对 TTL 30min、retain_until=到期+24h | 业务查询与写入绑定当前 tenant/epoch |
| `v4_demo_shops` | 每 tenant 两个独立 shop UUID，模板键只作映射；tenant/shop 复合 FK | 客户端 shop UUID 仅是请求目标，逐次核授权 |
| `v4_demo_personas` | operator/approver/restricted_admin 对应独立 principal/identity | 不从 persona 字符串授予业务能力 |
| `v4_demo_sessions` | 一个 tenant 一个 session，独立 token_hash、私有 bound_web_session、auth_version、generation/epoch、CSRF nonce/digest | 复用 `DemoSessions.resolve_locked` 完整身份桥接 |
| `v4_demo_receipts/events` | 仅四种控制操作 session_create/persona/reset/logout，严格 SQL 请求/事件/状态联动 | 不能塞入商品或导入操作，也不扩其枚举 |
| `v4_demo_overlays` | tenant/shop/epoch/kind/key PK，version、canonical payload/digest；kind 仅 product_attribute/fixture_note | 当前运行时只有 SELECT/DELETE，无 INSERT/UPDATE；guard 禁一般 UPDATE，故不假称已有业务编辑 |
| `v4_demo_bootstraps/rate_attempts` | 短期创建控制和限流 | 不改变创建并发、TTL、密码 hash 限流或认证规则 |

每店实际 seed 为 8 products、10 SKU、10 inventory、12 orders、18 order lines、2 refunds、6 customers、2 suppliers、3 quotes、2 knowledge 和采购/客服/营销各 1 个引用。两店分别 Asia/Taipei/TWD 与 Asia/Shanghai/CNY；固定日期锚为 2026-11-01，snapshot_at 为 2026-11-02T00:00:00Z，数据覆盖 14 个本地自然日。资料包数百 SKU/90 天订单的规模仍是后续目标，不是现存数量或吞吐证据。

实体为 fixture JSON 中的强类型对象，并非独立商品/订单 SQL 行：TemplateRef 含 shop_key/kind/key/确定性 UUID/version=1；SKU 含 product_ref、variant_ref、stock_pool_ref、price/currency；Order 含 customer_ref、created_at、paid_at|null、net_amount、status_hint；OrderLine 含 order_ref、sku_ref、quantity、net_amount；Refund 含 order_ref、occurred_at、amount，退款数量/回库/网关结果 UNKNOWN。SKU 成本、部分库存和在途均明确未知。原订单净额等于其行金额总和；退款单列，不能再次从订单行回扣。

现有实际 grant：operator 两店 operator；approver 仅店 A approver；restricted_admin 没有业务店铺 grant。`role_scope` 调用 `business.lock_p3_permission`，`actor_guard` 锁当前 principal/session；不能替换为前端菜单判断。

## 3. 同源读取、金额与 KPI

新增纯服务一次加载经过 fixture hash/关系校验的 ShopFixture，再合并当前 tenant/shop/epoch 的已确认导入商品、标签及履约。所有列表、详情、KPI、导出和 Copilot read context 消费这一同源视图，禁止各页独立造数。模板 UUID 不是授权凭据；在当前 shop 模板内找不到或无权的资源统一 404。

响应公共部分采用新 `schema_version=v4-business-v1`，复用现有 strict/frozen/extra-forbid 基类和 Context 字段；独立 V41 DTO 不修改 V4-0 DTO 的 source/operation 枚举。Context 含当前 tenant/organization/principal/shop/epoch/generation/authorized_at（DB UTC）。source 包含 fixture_version/digest、baseline_snapshot_at、`data_mode=demo_fixture|demo_upload`、`evidence_mode=synthetic_demo`、对象来源和 import_job_id（上传对象才有）。业务读取不把旧 M3 source_mode 改成新枚举。

每次读取返回独立业务 `data_revision`（fixture digest、当前 epoch、有序有效业务效果 digest），以及包含查询口径/过滤的 `snapshot_id`；auth_generation 只表示身份变化，不能替代业务版本。`read_at` 是 DB 时间，不能把固定 seed snapshot_at 显示为实时同步。单次查询在同一事务、同一同源视图完成；全部 V41 读写、reset 和导入确认必须先取得同一 tenant 锁，多 SQL 读取期间不能穿插该 tenant 业务写，不能只依赖 READ COMMITTED 的逐语句快照。新 SQL apply function 同样先锁 tenant/session，不能绕过此顺序。分页携带签名 cursor，绑定 tenant/shop/epoch/generation、filter/sort、data_revision/snapshot_id 和最后稳定排序键；cursor 不是权限。当前数据变化返回 409 SNAPSHOT_CHANGED，禁止拼接两版页面。写 body 也包含 expected_data_revision，并同时核对象 expected_version；成功返回提交前/后 revision，receipt 绑定本次效果版本。

| 指标/维度 | 提议精确定义 | 完整性与钻取 |
| --- | --- | --- |
| `created_order_count` | created_at 落入半开区间的订单数 | 明确订单创建口径，钻取原订单列表 |
| `paid_order_count` / `paid_order_amount` | paid_at 已知且落区间；金额为该订单 net_amount | 是演示付款记录金额，不宣称网关到账；缺付款日的可能相关订单使其 PARTIAL |
| `refund_event_count` / `refund_event_amount` | occurred_at 落区间的 Refund 笔数及 amount | 可关联更早订单；不按订单创建日挪移退款；网关状态 UNKNOWN，不能称已到账退款 |
| `average_paid_order_amount` | 同期间已知 paid amount / 已知 paid count | count=0 为 null/NO_DENOMINATOR；部分样本须标 PARTIAL |
| 商品/订单/低库存数量 | 商品总数合并已确认导入；低库存只比较已知库存与版本化阈值 | 库存未知另计；导入商品不凭空产生销量或库存 |
| 趋势与商品排行 | 本地日 bucket；付款金额按原订单行关联 SKU，退款独立列 | 日趋势可逐项定位订单/退款；不从金额退款推算退款件数或 SKU 归属 |

金额全程 Decimal（有界 precision，最多 6 位小数输入），wire 为 canonical 十进制字符串，禁止 float、指数、NaN/Infinity。求和后才做显示舍入，并保留精确值；跨币种只分组，拒绝全店合计货币金额或隐式换汇。首版不将退款事件直接扣成净收款：退款网关状态 UNKNOWN，quantity/restocked 也未知；不输出净收款、利润、退款件数率或回库增量。未知成本不出毛利，未知在途不按 0。展示退款事件金额可以 COMPLETE（完整覆盖演示事件集合），但独立的 settlement_status 必须 UNKNOWN，不能用聚合完整性推断实际到账。

时间输入为店铺本地 `from_date`/`to_date`（后者 exclusive），服务端 ZoneInfo 转 UTC，不允许客户端覆盖时区/币种；默认截至 fixture 2026-11-02 本地零点的最近 7 个完整日，支持 7/14 日或显式 ≤90 日。区间超出来源覆盖时返回 OUTSIDE_SOURCE_WINDOW/PARTIAL，不能以 0 表示已有完整记录。未知付款时间不能归入任何 paid bucket；保守报告可能影响当前区间的缺时记录数及已知小计。指标包含 value（完整且可定义时才有数值，否则 null）、known_value（已知范围小计）、COMPLETE/PARTIAL/UNAVAILABLE、reason_codes、included/excluded_count、口径版本和可复验 drilldown filters。缺成本、缺付款日、零分母或无可比期都须明确原因；不从 14 日小样本伪造同比或增长率，首版不提供未经完整性证明的比较数字。

## 4. 精确路由、DTO 与权限提案

所有路径都是待 Root 冻结的新路径。读请求带既有 `X-Demo-Epoch` / `X-Demo-Generation`，写 body 带 request_key、expected_epoch、expected_generation；写始终要求受信 Origin 和 CSRF。禁止客户端提交 tenant/principal/roles/auth_version/approved/server_time。现有 demo middleware 只匹配 `/api/v4/demo/**`，因此新 router 必须自行安装等强 Origin/CSRF/cache/error 边界，不能因同为 `/api/v4` 而默认受保护。

| 方法/路径 | DTO 源（拟 `application/v41/contracts.py`） | 能力/行为 |
| --- | --- | --- |
| GET `/api/v4/dashboard` | DashboardQuery → DashboardData | 有 operator 或 approver shop grant；KPI、趋势、异常、真实引用 |
| GET `/api/v4/dashboard/drilldown` | DrilldownQuery → DrilldownPage | metric 白名单、同查询窗口/快照，分页原对象 |
| GET `/api/v4/products` | ProductQuery → ProductPage | q、tag、origin、stable sort、limit/cursor |
| GET `/api/v4/products/{product_id}` | ResourceQuery → ProductDetail | SKU、来源、标签版本、库存已知/未知、可见关联订单 |
| POST `/api/v4/products/{product_id}/tags` | SetProductTags → ActionResult | 当前 operator grant；只改演示标签，不改价格、成本或 Woo |
| GET `/api/v4/orders` | OrderQuery → OrderPage | created/paid 时间基准枚举、日期、付款已知性、演示履约状态、q、分页 |
| GET `/api/v4/orders/{order_id}` | ResourceQuery → OrderDetail | 原订单行/商品/退款来源；演示履约与原事实分列 |
| POST `/api/v4/orders/{order_id}/fulfillment` | FulfillDemoOrder → ActionResult | 当前 operator；仅 `demo_unfulfilled → demo_fulfilled`，无物流/库存/付款效果 |
| GET `/api/v4/products/export`、`/api/v4/orders/export` | 同列表 Query → 安全 CSV | 同权同过滤同快照，≤500 行，不静默截断；静态路径先注册 |
| GET `/api/v4/read-context` | ReadContextQuery → ReadContextData | kind/id 或 dashboard 查询，纯只读白名单对象；当前 scope、引用和规则解释 |
| POST `/api/v4/imports/previews` | ImportPreviewInput → ImportPreviewData | operator；有界文件+mapping，只写临时质量作业，不写商品 |
| GET `/api/v4/imports/{import_job_id}` | ResourceQuery → ImportJobData | 当前 owner/epoch/operator；安全预览或确认结果 |
| POST `/api/v4/imports/{import_job_id}/confirm` | ConfirmImport → ActionResult | 当前 operator；绑定 job version/digest、限额、全批原子导入 |
| GET `/api/v4/actions/{operation}/{request_key}` | ActionLookup → ActionLookupData | 当前有效 owner + 原 principal/shop/epoch；COMMITTED 或 UNKNOWN，缺行不是回滚 |

操作枚举只含 product_tags、order_fulfillment、import_confirm。读取能力映射为当前 shop 的 operator 或 approver；全部写与导入要求 operator，approver 不能借审批身份编辑；admin 无默认业务读写。预览作业只对创建 owner/principal 可见。跨 tenant/shop/对象/作业 404；有权店铺但无对应写能力 403。表格默认 limit 20、最大 100；q ≤80、固定 sort 枚举，以 title/created_at/amount 与 UUID tie-breaker 排序。金额排序由 Decimal，不做字典序；cursor ≤2 KiB，参数不符 422，旧 snapshot 409。

产品标签仅 0–8 项、每项 1–24 字、去重和规范化，expected_version=0 表示尚无当前 epoch 覆盖；后续严格 +1。演示履约需要 known paid_at；付款日未知返回 409 PAYMENT_STATE_UNKNOWN，不补造“未付款”。原订单没有发货事实，因此默认是 demo_unfulfilled 标签，不解释为真实物流未发货；重复同 key 返回原效果，其他 key 重复状态为 409 STATE_CONFLICT，不减库存或调用 Woo。

共同写流程：解析当前 demo 身份 → 锁 tenant/session → `_cas` → 原 `role_scope` 锁当前权限 → 按稳定键锁目标/作业 → 查同 owner+operation+request_key 原 receipt → 同文回原回执、异文409 → 版本/来源/状态校验 → effect+receipt+event 同事务 → 提交前再次核身份/权限/DB TTL。锁顺序沿用 resolver 的 tenant/session、credential/principal、bound session/permission 顺序，不在新代码反向先锁商品。到期边界在 deferred guard 再核；不以事务开始时尚有效替代提交时判断。

动作摘要包含 method/path、完整规范 body、shop/object/source/version、actor/epoch/generation，request_key 跨 reset 仍不能被解释为新的执行许可。网络错误/503 保留原 key；客户端只读查询，不自动重发 POST。persona 改变、reset、到期/撤权后不返回旧业务结果；当前权限复核失败不由旧 receipt 绕过。失败信封复用既有错误语义，新码限 VERSION_CONFLICT、STATE_CONFLICT、PAYMENT_STATE_UNKNOWN、SNAPSHOT_CHANGED、IMPORT_INVALID、IMPORT_EXPIRED、LIMIT_EXCEEDED；retryable=false。

## 5. CSV/XLSX 预览、映射与原子导入

首版仅商品导入，每行一新 product + 一 SKU；不导订单、客户、退款、库存或同 SKU 多变体。字段闭集 `sku,title,price,currency,tags`；SKU 为 1–64 ASCII 字母数字及 `_-.`，canonical key 为去两端空白后的 ASCII casefold，展示保留原文。已有 fixture 的 SKU label 与已导入 SKU 一并检查，重复全部拒绝，不做静默 upsert；同 SKU 在不同 shop 可分别存在。

现有直接 runtime 依赖没有 openpyxl、defusedxml 或 python-multipart；本次 frozen/offline 同步发现 dev 依赖闭包已有 defusedxml 0.7.1，但不能把 dev 间接依赖当成生产保证。本提案采用 stdlib csv / zipfile / 有界 XML，暂不增锁依赖。协议为 strict JSON：format=csv|xlsx、filename（仅显示、不作路径）、file_base64、mapping（目标字段→源表头）、mapping_version=1、request_key、expected_epoch/generation。HTTP body 最多 3 MiB，解码文件最多 2 MiB；流式计数后才 JSON decode，base64 strict 校验。协议仍须 Root 与 WEB 冻结，不能直接复用现有 4 KiB 控制命令读取器。

提议硬限额：每次最多 500 数据行/500 新 SKU、24 列、单字段 512 字（title ≤120）、每 tenant/shop 当前 epoch 总导入 ≤500 SKU；每 tenant 最多 3 个未过期预览，每预览 TTL 10min 且不晚于 session 截止。解析预算 2 秒，DB statement 5 秒/lock 1 秒沿用原 bounded；这些是待验上限，不是测得容量。parse 前短事务核身份/Origin/CSRF与准入，释放锁后解析，落预览前新事务重新核权限、epoch/TTL；不持 PG 锁做 ZIP/XML 解析。

- CSV 仅 UTF-8（可 BOM），固定逗号、严格引号、拒绝 NUL/非法控制字符、重复/空表头、列宽不齐和额外尾列；不自动猜编码/分隔符。映射每目标唯一、必需 sku/title/price/currency 齐全，映射未知字段 422；缺可选 tags 用空数组并明确显示。
- 公式防护覆盖全部文本单元格，去前导空白/控制字符后以 `= + - @` 开头即拒绝，不计算或“清洗后接受”；price 单独严格非负 Decimal 文本，禁止科学计数法/百分比/日期转换。导出字符串同样做公式安全转义且由 CSV writer 正确引用。
- XLSX 只接受受限无宏单工作表 OOXML 子集；ZIP 不落盘、不 extract。拒绝加密、重复/路径穿越/绝对路径/符号链接 entry、未知压缩方法、宏/VBA、外链、嵌套包和非白名单 parts。最多 32 entries、解压总计 8 MiB、单 entry 2 MiB、压缩比 ≤100；实际流式读取计数，不能只信 ZIP 中声明的 size/CRC。
- XML 只接受 UTF-8，有界解析前拒绝 DOCTYPE/ENTITY；拒绝 XML declaration 以外的 processing instruction、外部关系 TargetMode、公式节点（包括有缓存值）、DDE、数据连接/嵌入对象。限制节点总数、深度、attribute、sharedStrings 数量和字符数；worksheet 行列索引不能稀疏跳过限额，重复单元格/越界引用拒绝。仅支持普通 string/inlineStr/shared-string 和严格 decimal 值；日期/布尔/error/复杂格式不自动转成商品字段。
- stdlib 实现必须按上述子集 fail closed，格式不支持给明确质量原因；如无法在审查中证明资源界限，再由 Root 裁定一个必要依赖，不能为了接受复杂 Excel 隐式扩格式或放宽 XML 安全。

预览响应只返回最多 20 行安全样本、总数、字段映射、错误总数及最多 100 条行号/字段/原因；不回显完整原文件、PII、公式或异常 XML。预览作业保存 owner/tenant/shop/epoch/generation、文件 SHA256、mapping digest、normalized rows、质量结果及到期时间，原始文件不入 Git、日志或公开下载。无效预览不能确认；更换映射生成新版本作业，旧版本不就地改写。

确认只接受 job id/version/digest，不接收客户端重新提交的行内容。事务锁 tenant/session/shop/作业，复核当前 operator、epoch/generation、期限、文件/映射/normalized digest、所有重复 SKU、总量与币种；一次写全部新 product/SKU、唯一 receipt/event。任一错行、并发冲突或失败注入整批回滚，不留部分商品或 COMMITTED。两作业并发争同 SKU 由唯一约束及同 tenant 锁决定一胜一拒。已确认 preview 只对应一个 import_confirm receipt，换 key 不能再次导入；同原 key 同文十次仍一次效果。

确认后商品列表、详情、export、dashboard 商品数量和 read context 能查到同一新 ID/source_ref；销量 KPI 不增加。没有可靠库存的导入商品显示 UNKNOWN_STOCK；价格只允许本店 currency，Woo 调用次数必须 0。

## 6. 最小 0025 / ACL 与共享文件地图

拟唯一新增 `backend/migrations/versions/0025_v41_catalog_operations.py`，down_revision 精确为 `0024_v4_demo_foundation`。不编辑旧迁移或其 trigger/function；不扩旧控制 receipts/events，也不授予旧 overlays INSERT/UPDATE。

| 拟新表（business schema） | 最小数据/约束 | runtime ACL 提案 |
| --- | --- | --- |
| `v41_product_tags` | tenant/shop/epoch/product_id PK，base source/digest、version、tags、last_receipt | SELECT；只允许固定 apply function 内受控 INSERT/列 UPDATE |
| `v41_order_fulfillments` | tenant/shop/epoch/order_id PK，base source、version、demo status、last_receipt | 同上，无原订单/库存写权限 |
| `v41_import_jobs` | owner/session/principal/tenant/shop/epoch/generation、job version、digests、规范行、quality、expires_at | SELECT；固定 preview function 有界 INSERT，内容不可变 |
| `v41_import_products` | tenant/shop/epoch、product_id/sku_id、canonical_sku、title/price/currency/tags、job/receipt/source | SELECT；confirm function 内 INSERT，唯一 tenant/shop/epoch/canonical_sku |
| `v41_action_receipts` | owner/op/key unique、actor/shop/object、epoch/generation、canonical request/digest、effect digest、DB time/retain_until | SELECT；apply function 内 INSERT，禁止 UPDATE/DELETE/TRUNCATE |
| `v41_action_events` | receipt 复合 FK、对象/版本/前后摘要、事件类型、DB time；一 receipt 对应精确效果数 | 同上，不引入队列/Worker |

新表使用 tenant/shop、owner-session/tenant、receipt/object 的复合 FK，避免把单个合法 UUID 搭成跨 tenant 引用。product/SKU ID 由服务端在 job 下稳定生成，不能由表格指定；fixture ID 必须核当前 template membership。新 receipts/events deferred guard 验 canonical hash、权限当前值、版本单调、效果/receipt/event 完整性、active epoch 和 DB TTL；缺任一组件回滚。SECURITY DEFINER 仅固定函数、固定 search_path/显式对象名、无动态 SQL，REVOKE PUBLIC；传参不含可任意授予角色的 authority 字段。runtime 不能直接改效果表或历史，owner 才能在 retain_until 后精确 tenant GC。实际函数 SQL/锁序需独审，计划表不等于 ACL 已成立。

Reset 不改旧控制事务：它已推进 tenant/session epoch，V41 所有读写强制当前 epoch，使旧 V41 效果和预览立即不可用；保留旧 epoch 证据至 retention。reset 不物理删除新历史，不能删掉去重记录。GC 按原 retain_until/owner/tenant 顺序先清 V41 子表，再走原 V4 tenant 清理，禁止全库 cascade/truncate。

发现必须由 Root 精确释放的兼容点：`infrastructure/v4_demo_seed.py::require_owner` 当前只准 0024，升级后原初始化/grant/GC 会拒绝；`gc_tenant` 尚不知道 V41 子表。建议单 owner 最小扩为明确 0024/0025 allowlist，并在 0025 路径调用窄 V41 GC helper；0024 行为、版本以外环境/owner 校验原样。这是待批准的共享文件例外，不能在本轮暗改或复制另一套身份/seed manager。

| 路径 | 唯一 owner / 修改边界 |
| --- | --- |
| `application/v41/**` | SCHEMA/API：strict DTO、同源视图、Decimal KPI、纯解析与规则分析 |
| `infrastructure/v41_*.py` | SCHEMA/API：store、SQL adapter、窄导入/GC owner helper |
| `entrypoints/v41_*.py` | SCHEMA/API：router、单独 OpenAPI、显式 V41 安全边界 |
| `entrypoints/api.py` | SCHEMA/API 独占：仅 enabled demo 配置下安装 V41，不改变旧 schema/auth |
| `0025_v41_catalog_operations.py` | SCHEMA/API 唯一线性迁移；无其他 owner 新建 revision |
| `infrastructure/v4_demo_seed.py` | 仅 Root 冻结上述精确兼容例外后修改 |
| `tests/v41/backend/**` | SCHEMA/API 作者测试；QA 在独立路径消费冻结 DTO/提交 |
| `docs/v4/v4-1/proposals/API_PLAN.md` | 本次已授权文档；正式 OpenAPI/接口冻结由 Root 裁定位置 |
| frontend、锁文件、CI、旧 PG tests、Worker/Graph | 本轮不改；后续必要兼容先登记精确路径，不自行放宽 |

## 7. 实施切片与本地 Gate

1. Root 冻结本提案的路径、DTO、金额/期间口径、导入子集/限额、权限地图、六表与共享文件例外；Reviewer 先审 SQL/ACL/锁序，再编写受测源码。
2. 纯 DTO/同源查询/KPI：同源金额金标、付款与退款事件跨日、未知网关/退款数量/回库、零分母、未知成本/库存、无可比期、跨币种拒绝、固定 source snapshot、稳定分页和 stale cursor。不得改 seed 来配合预期；多 SQL 与并发覆盖更新证明不混合 revision。
3. 0025 + 查询/标签/履约：新 owned PG 升级真实 0024→0025、精确新表/列/ACL、旧行/bytes/角色权限不变；current-head expected table list 在单独最小兼容切片更新，不修改固定历史迁移段或删断言。
4. 导入：正常 CSV/XLSX→映射→预览→确认→同源查询；畸形/公式/zip/XML/超限/重复/跨店/币种/过期/撤权、确认失败回滚、并发唯一 SKU、同 key 十次/异文冲突、COMMIT 前后失败与原键只读恢复、reset 竞争/跨 session 隔离。
5. 独立 API/真实 PG/浏览器：Origin/CSRF/401/403/404、admin 无权、approver 店 B 404/写403、旧 epoch/gen/CSRF 失效、迟到响应清屏；1440/390（并复用现有 1280 标准）下列表/详情/标签/履约/导入和完整 Shell 六卡证据由 WEB/QA 提供。
6. Root 在冻结精确组合源码释放新 owned 资源 UTC 窗口及完整旧 M3 回归。动态 collect 当前全部 PG，既有 existing+phase3 精确配对、全部 G1/G2、原 Web24/N01 和必要完整工程检查不减少；新增节点按实际所属分区计，不把 745 或旧五绿当永久集合或新 SHA 结果。清理/镜像/架构/源码绑定按新窗口实测归档。

本轮 Docker/PG/API/Web/provider/Woo/外部/Hosted/push 均未运行。旧 V40/M3/Harness 工作树、提交和 `.audit` 未改；旧失败、UNKNOWN、预算及等待分账不重置。后续代码作者自检不代替独立审查；V4-1 六卡完成须有实际 API/PG/浏览器及同源导入闭环，不能用本提案签完成。
